"""
Generate a fresh Java driver class per submission so the autograder can run
hidden tests against the student's pipeline directly, instead of relying on
the student's own ParserTester / CompilerTester.

The point of this module
========================
Students hardcode test filenames into their own driver:

    Scanner s = new Scanner(new FileInputStream("parser/parserTest9.txt"));
    Parser  p = new Parser(s);
    Program prog = p.parseProgram();
    prog.exec(new Environment());

When the old autograder dropped a hidden test next to that file and ran the
student's `main`, the JVM ignored `args[0]` and silently re-ran whatever
file the student baked in. Every hidden test then "matched" the student's
hardcoded file, so the report said WRONG OUTPUT while the terminal showed
the student's expected answer for parserTest9. Exactly the bug the
teacher flagged.

The fix: synthesize a fresh `_AGTester.java` (or `_AGCodeGenTester.java`)
per submission that imports the student's resolved classes -- using
whatever names they actually used -- reads the test path from `args[0]`,
and drives the pipeline end-to-end. We compile that file alongside the
student's tree and lock it in as the main class for the hidden suite.

Why per-submission code-gen and not a single hardcoded driver?
---------------------------------------------------------------
Student renames break a hardcoded driver:
  * Parser may be parser.Parser, parser.PascalParser, ...
  * Program may be ast.Program, ast.PascalProgram, ...
  * Environment may be environment.Environment, environment.Env, ...
  * parseProgram may be parseProg, parseRoot, ...
  * exec may be execute, run, ...
  * Some students take (Scanner, Environment) on Parser, others (Scanner)
  * Some Program ctors take 0 args; some 3.

We resolve every signal off the parsed AST + role resolver and emit a
driver that uses the student's actual names. If signals are too thin to
emit a confident driver (no Parser, no parseProgram-like method, etc.),
build_for_procedures returns None and the orchestrator falls back to the
student's own main -- the old behaviour, no worse than before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .javadoc_parser import ClassRecord, MethodRecord


# Class name we drop into the student's parser/ folder. Underscore prefix
# makes collisions with student-written classes implausible while still
# being a legal Java identifier.
PROCEDURES_TESTER_CLASS = "_AGTester"
CODEGEN_TESTER_CLASS = "_AGCodeGenTester"
SCANNER_TESTER_CLASS = "_AGScannerTester"
PARSER_TESTER_CLASS = "_AGParserTester"
AST_TESTER_CLASS = "_AGASTTester"


@dataclass
class SyntheticTester:
    """The on-disk artifact the synthetic-tester pass produced.

    Attributes:
        source_path: where the .java was written (under compiler_root). The
            grader compiles it as part of the student's tree.
        fq_class: fully-qualified class name to invoke as `java <cp> <fq>`.
        notes: human-readable diagnostics ("used Parser ctor (Scanner)",
            "Environment lacks no-arg ctor; passing null") that the rubric
            and PDF can surface so the teacher knows which driver shape ran.
    """

    source_path: Path
    fq_class: str
    notes: List[str]


def _package_of_file(rel_file: str) -> str:
    """Convert a class's relative file path to its package name.

    `parser/Parser.java` -> "parser"; a top-level file -> "". javalang
    doesn't always carry the package decl through, and we trust the
    extractor's directory layout more anyway -- students who break their
    package declaration tend to leave the file in the right folder.
    """
    if "/" not in rel_file:
        return ""
    return rel_file.rsplit("/", 1)[0].replace("/", ".")


def _fq(cls: ClassRecord) -> str:
    pkg = _package_of_file(cls.file)
    return f"{pkg}.{cls.name}" if pkg else cls.name


def _parser_ctor_takes_env(parser: ClassRecord) -> bool:
    """True iff the resolved Parser has a constructor whose param list
    mentions an environment-like type.

    Some students follow an older lab variant where the Parser ctor wires
    in the environment up front: `new Parser(scanner, environment)`. We
    pass `null` in that case -- the student's ctor typically just stores
    the reference, and our driver constructs its own environment to drive
    `program.exec`.
    """
    for m in parser.methods:
        if m.method_name != parser.name:
            continue
        joined = " ".join(m.params).lower()
        if any(tok in joined for tok in ("environment", "env", "scope")):
            return True
    return False


def _ctor_param_count(cls: ClassRecord) -> List[int]:
    """Sorted distinct parameter counts of cls's constructors.

    A class with both `Foo()` and `Foo(Foo parent)` returns [0, 1]. Used
    to pick "no-arg if available, else single-arg with null" without
    hand-coding ctor preferences per role.
    """
    counts = sorted({len(m.params) for m in cls.methods if m.method_name == cls.name})
    return counts


def _find_method_alias(cls: ClassRecord, aliases: Sequence[str],
                       *, must_be_zero_arg: bool = False
                       ) -> Optional[MethodRecord]:
    """Return the first method on cls whose name matches any alias.

    Matches case-sensitively; aliases earlier in the sequence win. Used
    to find parseProgram / exec / compile under student renames. The
    `must_be_zero_arg` flag is for parseProgram-like calls where we
    don't want to pick up a helper that takes a parameter.
    """
    by_name = {m.method_name: m for m in cls.methods}
    for alias in aliases:
        m = by_name.get(alias)
        if m is None:
            continue
        if must_be_zero_arg and m.params:
            continue
        return m
    return None


def build_for_procedures(
    classes: Sequence[ClassRecord],
    compiler_root: Path,
    parser_role: Optional[ClassRecord],
    program_role: Optional[ClassRecord],
    environment_role: Optional[ClassRecord],
) -> Optional[SyntheticTester]:
    """Emit `_AGTester.java` driving a Procedures-lab submission.

    Returns None if the signals aren't strong enough to produce a working
    driver -- the orchestrator then falls back to probing the student's
    own main candidates. The bar is intentionally permissive: we tolerate
    renamed Program/Environment classes, but we WILL bail if there's no
    Parser-shaped class with a ctor we can call.
    """
    if parser_role is None:
        return None

    parse_method = _find_method_alias(
        parser_role,
        ("parseProgram", "parseProg", "parseRoot", "parsePascal", "parse"),
        must_be_zero_arg=True,
    )
    if parse_method is None:
        return None

    notes: List[str] = []

    parser_fq = _fq(parser_role)
    scanner_fq = _scanner_class_fq(classes)
    if scanner_fq is None:
        scanner_fq = "scanner.Scanner"
        notes.append("scanner role not resolved; assuming scanner.Scanner")

    parser_takes_env = _parser_ctor_takes_env(parser_role)
    parser_ctor_args = "scanner, env" if parser_takes_env else "scanner"
    if parser_takes_env:
        notes.append("parser ctor takes (Scanner, Environment); passing env")

    program_decl, exec_call = _program_exec_snippets(
        parse_method, program_role, notes,
    )

    env_fq, env_init = _environment_init(environment_role, notes)

    src = _render(_PROC_TEMPLATE, {
        "PARSER_FQ": parser_fq,
        "SCANNER_FQ": scanner_fq,
        "ENV_FQ": env_fq,
        "ENV_INIT": env_init,
        "PARSER_CTOR_ARGS": parser_ctor_args,
        "PROGRAM_DECL": program_decl,
        "EXEC_CALL": exec_call,
        "TESTER_CLASS": PROCEDURES_TESTER_CLASS,
    })

    out = compiler_root / "parser" / f"{PROCEDURES_TESTER_CLASS}.java"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf-8")
    return SyntheticTester(
        source_path=out,
        fq_class=f"parser.{PROCEDURES_TESTER_CLASS}",
        notes=notes,
    )


def build_for_codegen(
    classes: Sequence[ClassRecord],
    compiler_root: Path,
    parser_role: Optional[ClassRecord],
    program_role: Optional[ClassRecord],
    emitter_role: Optional[ClassRecord],
) -> Optional[SyntheticTester]:
    """Emit `_AGCodeGenTester.java` driving a CodeGen-lab submission.

    The driver reads args[0] as the input .pas file, args[1] as the
    output .asm path, parses, then asks the resulting Program to
    compile to args[1]. Two compile shapes are supported, in order:
      1. `program.compile(String)` -- the canonical lab-doc signature.
      2. `program.compile(Emitter)` -- some students expose only the
         emitter-flavoured overload; we new-up an emitter on args[1]
         and pass it.

    Returns None if neither shape can be wired up.
    """
    if parser_role is None or program_role is None:
        return None

    parse_method = _find_method_alias(
        parser_role,
        ("parseProgram", "parseProg", "parseRoot", "parsePascal", "parse"),
        must_be_zero_arg=True,
    )
    if parse_method is None:
        return None

    compile_method = _find_method_alias(
        program_role,
        ("compile", "emit", "generate", "codegen", "compileTo"),
    )
    if compile_method is None:
        return None

    notes: List[str] = []

    parser_fq = _fq(parser_role)
    program_fq = _fq(program_role)
    scanner_fq = _scanner_class_fq(classes) or "scanner.Scanner"

    parser_takes_env = _parser_ctor_takes_env(parser_role)
    parser_ctor_args = "scanner, null" if parser_takes_env else "scanner"
    if parser_takes_env:
        notes.append("parser ctor takes (Scanner, Environment); passing null")

    # Pick the compile shape. A single-arg method whose param mentions a
    # File/Path/String type is the lab-canonical "filename" form. Anything
    # else we treat as an Emitter-style overload and synthesize an Emitter.
    param_text = " ".join(compile_method.params).lower()
    is_filename_shape = (
        len(compile_method.params) == 1
        and any(t in param_text for t in ("string", "file", "path", "filename"))
    )

    if is_filename_shape:
        compile_call = f'program.{compile_method.method_name}(args[1]);'
        notes.append(
            f"program.{compile_method.method_name}(String) detected"
        )
    else:
        emitter_fq = _fq(emitter_role) if emitter_role else "emitter.Emitter"
        compile_call = (
            f'{emitter_fq} _ag_e = new {emitter_fq}(args[1]);\n'
            f'        program.{compile_method.method_name}(_ag_e);\n'
            f'        try {{ _ag_e.close(); }} catch (Throwable __) {{}}'
        )
        notes.append(
            f"using emitter overload program.{compile_method.method_name}"
            f"({emitter_fq})"
        )

    src = _render(_CODEGEN_TEMPLATE, {
        "PARSER_FQ": parser_fq,
        "PROGRAM_FQ": program_fq,
        "SCANNER_FQ": scanner_fq,
        "PARSER_CTOR_ARGS": parser_ctor_args,
        "PARSE_METHOD": parse_method.method_name,
        "COMPILE_CALL": compile_call,
        "TESTER_CLASS": CODEGEN_TESTER_CLASS,
    })

    out = compiler_root / "parser" / f"{CODEGEN_TESTER_CLASS}.java"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf-8")
    return SyntheticTester(
        source_path=out,
        fq_class=f"parser.{CODEGEN_TESTER_CLASS}",
        notes=notes,
    )


def build_for_scanner(
    classes: Sequence[ClassRecord],
    compiler_root: Path,
    scanner_role: Optional[ClassRecord],
) -> Optional[SyntheticTester]:
    """Emit `_AGScannerTester.java` driving a Scanner-lab submission.

    The driver opens args[0] as a FileInputStream, wraps it in the
    student's Scanner, and prints one token per line until "EOF" is
    returned or hasNext() goes false. ScanErrorException (or any
    runtime exception) is caught and printed as `ERROR: <msg>` on its
    own line so the matcher can verify "throws on $/^" without
    crashing the JVM.

    Returns None if no Scanner-shaped class is resolvable.
    """
    if scanner_role is None:
        # Last-ditch: try the canonical name even when role resolution failed
        # (eg. javalang choked on Scanner.java due to a syntax error).
        scanner_fq = _scanner_class_fq(classes)
        if scanner_fq is None:
            return None
        scanner_pkg = scanner_fq.rsplit(".", 1)[0] if "." in scanner_fq else ""
    else:
        scanner_fq = _fq(scanner_role)
        scanner_pkg = _package_of_file(scanner_role.file)

    notes: List[str] = []
    # The synthetic driver lives in the SAME package as the resolved Scanner,
    # so we don't have to worry about package visibility for the Scanner
    # ctor. If the Scanner lives in the default package (rare but legal),
    # the driver lands there too.
    pkg_line = f"package {scanner_pkg};\n\n" if scanner_pkg else ""
    src = _render(_SCANNER_TEMPLATE, {
        "PACKAGE_LINE": pkg_line,
        "SCANNER_FQ": scanner_fq,
        "TESTER_CLASS": SCANNER_TESTER_CLASS,
    })

    out_dir = compiler_root / scanner_pkg if scanner_pkg else compiler_root
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{SCANNER_TESTER_CLASS}.java"
    out.write_text(src, encoding="utf-8")
    fq = f"{scanner_pkg}.{SCANNER_TESTER_CLASS}" if scanner_pkg \
        else SCANNER_TESTER_CLASS
    return SyntheticTester(source_path=out, fq_class=fq, notes=notes)


def build_for_parser(
    classes: Sequence[ClassRecord],
    compiler_root: Path,
    parser_role: Optional[ClassRecord],
) -> Optional[SyntheticTester]:
    """Emit `_AGParserTester.java` for the Pascal Parser lab.

    In this lab the parser EXECUTES Pascal as it parses (no AST).
    parseStatement is a `void` method with the side-effect of printing
    WRITELN values to stdout. The driver creates a Parser, then calls
    parseStatement repeatedly while scanner.hasNext() returns true.

    Returns None if no Parser class with a parseStatement-shaped method
    is resolvable -- the orchestrator then falls back to the student's
    own main.
    """
    if parser_role is None:
        return None

    parse_method = _find_method_alias(
        parser_role,
        ("parseStatement", "parseStmt", "parseStatements"),
        must_be_zero_arg=True,
    )
    if parse_method is None:
        # Some lab variants only expose parseProgram / runProgram. Accept
        # those too so a slightly-different submission can still be tested.
        parse_method = _find_method_alias(
            parser_role,
            ("parseProgram", "runProgram", "parseProg",
             "parsePascal", "parse"),
            must_be_zero_arg=True,
        )
        if parse_method is None:
            return None
        loop_body = (
            f"parser.{parse_method.method_name}();\n"
            f"            break;  // single-call entry; no loop needed"
        )
    else:
        loop_body = f"parser.{parse_method.method_name}();"

    notes: List[str] = []
    parser_fq = _fq(parser_role)
    scanner_fq = _scanner_class_fq(classes) or "scanner.Scanner"

    src = _render(_PARSER_TEMPLATE, {
        "PARSER_FQ": parser_fq,
        "SCANNER_FQ": scanner_fq,
        "LOOP_BODY": loop_body,
        "TESTER_CLASS": PARSER_TESTER_CLASS,
    })

    out = compiler_root / "parser" / f"{PARSER_TESTER_CLASS}.java"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf-8")
    return SyntheticTester(
        source_path=out,
        fq_class=f"parser.{PARSER_TESTER_CLASS}",
        notes=notes,
    )


def build_for_ast(
    classes: Sequence[ClassRecord],
    compiler_root: Path,
    parser_role: Optional[ClassRecord],
    environment_role: Optional[ClassRecord],
) -> Optional[SyntheticTester]:
    """Emit `_AGASTTester.java` for the AST lab.

    The Parser produces AST nodes; parseStatement returns a Statement
    whose `exec(env)` we then call. The driver creates a fresh
    Environment, then loops calling parseStatement + stmt.exec while
    scanner.hasNext() is true.

    If parseStatement isn't visible (e.g. the student went straight to
    a parseProgram-shaped entry point that returns a Program with an
    exec method) we degrade gracefully to that shape -- same as the
    procedures driver does.
    """
    if parser_role is None:
        return None

    notes: List[str] = []

    parse_stmt = _find_method_alias(
        parser_role,
        ("parseStatement", "parseStmt"),
        must_be_zero_arg=True,
    )
    parse_prog = _find_method_alias(
        parser_role,
        ("parseProgram", "runProgram", "parseProg",
         "parsePascal", "parse"),
        must_be_zero_arg=True,
    )

    if parse_stmt is None and parse_prog is None:
        return None

    parser_fq = _fq(parser_role)
    scanner_fq = _scanner_class_fq(classes) or "scanner.Scanner"
    env_fq, env_init = _environment_init(environment_role, notes)

    if parse_stmt is not None:
        # Loop: read statement-by-statement, exec each.
        rt = (parse_stmt.return_type or "").split(".")[-1].strip()
        # Most students name the parent class Statement; tolerate Stmt too.
        stmt_type = rt if rt and rt != "void" else "ast.Statement"
        if stmt_type == "Statement":
            stmt_type = "ast.Statement"
        loop_body = (
            f"{stmt_type} stmt = parser.{parse_stmt.method_name}();\n"
            f"            if (stmt != null) stmt.exec(env);"
        )
    else:
        # Single parseProgram entry. If it returns void, just call it; if
        # it returns a Program-shaped object, call exec on it.
        rt = (parse_prog.return_type or "").strip()
        rt_short = rt.split(".")[-1] if rt else ""
        if rt_short in ("void", ""):
            loop_body = (
                f"parser.{parse_prog.method_name}();\n"
                f"            break;  // single-call entry; no loop needed"
            )
        else:
            # Try exec on the returned object; fall back to ignoring it.
            loop_body = (
                f"{rt} _ag_prog = parser.{parse_prog.method_name}();\n"
                f"            if (_ag_prog != null) {{\n"
                f"                try {{ _ag_prog.getClass().getMethod(\"exec\","
                f" {env_fq}.class).invoke(_ag_prog, env); }}\n"
                f"                catch (NoSuchMethodException __) {{ /* no exec; ok */ }}\n"
                f"            }}\n"
                f"            break;"
            )
            notes.append(
                f"parseProgram returns {rt!r}; using reflective exec"
            )

    src = _render(_AST_TEMPLATE, {
        "PARSER_FQ": parser_fq,
        "SCANNER_FQ": scanner_fq,
        "ENV_FQ": env_fq,
        "ENV_INIT": env_init,
        "LOOP_BODY": loop_body,
        "TESTER_CLASS": AST_TESTER_CLASS,
    })

    out = compiler_root / "parser" / f"{AST_TESTER_CLASS}.java"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src, encoding="utf-8")
    return SyntheticTester(
        source_path=out,
        fq_class=f"parser.{AST_TESTER_CLASS}",
        notes=notes,
    )


def _environment_init(env_cls: Optional[ClassRecord],
                      notes: List[str]) -> tuple:
    """Pick `new Environment(...)` shape based on what ctors exist.

    Order of preference: zero-arg, single-arg-null, anything-else-null.
    A return value of (env_fq, init_expr) where init_expr fills in the
    `<env_fq> env = <init_expr>;` line in the template.
    """
    if env_cls is None:
        return ("environment.Environment", "new environment.Environment()")
    fq = _fq(env_cls)
    counts = _ctor_param_count(env_cls)
    if 0 in counts:
        return (fq, f"new {fq}()")
    if 1 in counts:
        notes.append("Environment has no no-arg ctor; passing null")
        return (fq, f"new {fq}(null)")
    # Last resort -- pad with the right number of nulls. Java compilation
    # may still fail if any param is a primitive; rubric will surface
    # that and the fallback main-class path will be used instead.
    n = counts[0] if counts else 0
    notes.append(f"Environment ctor needs {n} args; padding with nulls")
    args = ", ".join(["null"] * n)
    return (fq, f"new {fq}({args})")


def _program_exec_snippets(
    parse_method: MethodRecord,
    program_role: Optional[ClassRecord],
    notes: List[str],
) -> tuple:
    """Decide how to run the parsed program.

    Returns (program_decl, exec_call) -- the two lines that go between
    "create parser" and "done" in the procedures driver. Both strings
    are inserted verbatim into the template, so they must be valid Java
    on their own.

    Cases handled:
      * parseProgram returns the resolved Program -> declare it, call
        exec/execute/run, passing env iff the method takes a parameter.
      * parseProgram returns void / Statement / something else -> just
        invoke the parse method for its side effects. Older starter
        code runs the program from inside parseProgram itself, so this
        still drives the pipeline correctly even though we never get
        a Program reference.
    """
    rt = (parse_method.return_type or "").strip()
    rt_short = rt.split(".")[-1]
    parse_call = f"parser.{parse_method.method_name}()"

    if program_role is not None and rt_short == program_role.name:
        program_fq = _fq(program_role)
        exec_method = _find_method_alias(
            program_role, ("exec", "execute", "run"),
        )
        method_name = exec_method.method_name if exec_method else "exec"
        if exec_method is not None and not exec_method.params:
            return (
                f"{program_fq} program = {parse_call};",
                f"program.{method_name}();",
            )
        return (
            f"{program_fq} program = {parse_call};",
            f"program.{method_name}(env);",
        )

    if rt_short in ("void", ""):
        notes.append("parseProgram returns void; running for side-effects")
        return (
            f"{parse_call};",
            "/* exec performed inside parseProgram */",
        )

    # Unknown return type. Drop the value and rely on side-effects.
    notes.append(
        f"parseProgram return type {rt!r} not recognised; "
        f"running for side-effects only"
    )
    return (
        f"Object _ag_unused = {parse_call};",
        "/* no exec call */",
    )


def _render(template: str, mapping: dict) -> str:
    """Replace `__KEY__` tokens in template with the mapped values.

    We use this instead of str.format() because the templates contain
    Java braces (`{` and `}`) that would otherwise need painful
    {{/}} escaping. Any token not provided in mapping passes through
    unchanged -- callers should always supply every key.
    """
    out = template
    for key, value in mapping.items():
        out = out.replace(f"__{key}__", str(value))
    return out


def _scanner_class_fq(classes: Sequence[ClassRecord]) -> Optional[str]:
    """Find a class named Scanner-ish and return its FQ name.

    Looks for a class whose name contains 'scanner' (case-insensitive)
    and is NOT java.util.Scanner. We don't import java.util.Scanner into
    the driver -- the student's Scanner is what we want.
    """
    for cls in classes:
        if cls.name.lower().endswith("scanner") and cls.name != "Scanner":
            # Custom-named Scanner-like class (PascalScanner, MyScanner).
            return _fq(cls)
    for cls in classes:
        if cls.name == "Scanner":
            return _fq(cls)
    return None


# --------------------------------------------------------------------------- #
# Java templates. Kept here as plain strings (rather than separate .java
# resource files) so a contributor can read the entire driver shape inline.
# --------------------------------------------------------------------------- #

# Procedures driver. Imports student classes by FQ name so we can stay
# in package "parser" without naming conflicts. The InputStream-based
# Scanner ctor is the universal one -- students may also expose a
# String-based ctor, but every Scanner.java in the lab still has the
# InputStream form.
_PROC_TEMPLATE = """\
package parser;

import java.io.FileInputStream;

/**
 * Autograder-generated driver. Loads args[0] as the test source file,
 * drives the student's parsing pipeline, and execs the resulting AST.
 * Replaces the student's own ParserTester for hidden-test runs so that
 * a hardcoded test filename in their tester doesn't make every test
 * silently re-run the same baked-in file.
 */
public class __TESTER_CLASS__
{
    public static void main(String[] args) throws Exception
    {
        if (args.length < 1)
        {
            System.err.println("usage: __TESTER_CLASS__ <test-file>");
            System.exit(2);
        }
        FileInputStream in = new FileInputStream(args[0]);
        __SCANNER_FQ__ scanner = new __SCANNER_FQ__(in);
        __ENV_FQ__ env = __ENV_INIT__;
        __PARSER_FQ__ parser = new __PARSER_FQ__(__PARSER_CTOR_ARGS__);
        __PROGRAM_DECL__
        __EXEC_CALL__
    }
}
"""

# CodeGen driver. args[0] = input .pas, args[1] = output .asm path.
# Drives the student's compile pipeline only -- we do NOT exec the
# program here. The runner takes the .asm we wrote and feeds it to MARS
# in a separate step.
_CODEGEN_TEMPLATE = """\
package parser;

import java.io.FileInputStream;

/**
 * Autograder-generated CodeGen driver. Reads a Pascal program from
 * args[0], drives the student's parser + emitter, and writes the
 * resulting MIPS assembly to args[1]. Replaces the student's own
 * CompilerTester so that a hardcoded input filename or hardcoded
 * output filename in their tester can't mask the real behaviour.
 */
public class __TESTER_CLASS__
{
    public static void main(String[] args) throws Exception
    {
        if (args.length < 2)
        {
            System.err.println("usage: __TESTER_CLASS__ <in.pas> <out.asm>");
            System.exit(2);
        }
        FileInputStream in = new FileInputStream(args[0]);
        __SCANNER_FQ__ scanner = new __SCANNER_FQ__(in);
        __PARSER_FQ__ parser = new __PARSER_FQ__(__PARSER_CTOR_ARGS__);
        __PROGRAM_FQ__ program = parser.__PARSE_METHOD__();
        __COMPILE_CALL__
    }
}
"""


# Scanner driver. Lands in the SAME package as the student's Scanner so we
# can call its package-private members without import gymnastics. Each
# token is printed on its own line; on ScanError (or any throwable) we
# print "ERROR: <msg>" so the test runner can verify "throws on $/^".
_SCANNER_TEMPLATE = """\
__PACKAGE_LINE__import java.io.FileInputStream;

/**
 * Autograder-generated Scanner driver. Loads args[0] as the test source
 * file and prints one token per line until EOF or hasNext()==false.
 * Replaces the student's own ScannerTester for hidden-test runs so a
 * hardcoded test filename in their tester can't make every test
 * silently re-run the same baked-in file.
 */
public class __TESTER_CLASS__
{
    public static void main(String[] args) throws Exception
    {
        if (args.length < 1)
        {
            System.err.println("usage: __TESTER_CLASS__ <test-file>");
            System.exit(2);
        }
        FileInputStream in = new FileInputStream(args[0]);
        __SCANNER_FQ__ s = new __SCANNER_FQ__(in);
        // Cap on tokens emitted so a buggy hasNext() that always returns
        // true can't fill the disk. 100k tokens is well above any real
        // scanner test file's worth.
        int safety = 100000;
        while (safety-- > 0)
        {
            String tok;
            try
            {
                tok = s.nextToken();
            }
            catch (Throwable t)
            {
                String msg = t.getMessage();
                if (msg == null) msg = t.getClass().getSimpleName();
                System.out.println("ERROR: " + msg);
                break;
            }
            if (tok == null)
            {
                System.out.println("EOF");
                break;
            }
            System.out.println(tok);
            if (tok.equals("EOF")) break;
            if (!s.hasNext()) break;
        }
    }
}
"""

# Parser driver (execute-while-parsing flavour, no AST). The
# student's parseStatement is void. We loop while scanner.hasNext().
_PARSER_TEMPLATE = """\
package parser;

import java.io.FileInputStream;

/**
 * Autograder-generated Parser driver. Loads args[0] as the test source
 * file and runs the student's parser through every statement until
 * scanner.hasNext() goes false. The parser's parseStatement side-effect
 * is to print WRITELN values.
 */
public class __TESTER_CLASS__
{
    public static void main(String[] args) throws Exception
    {
        if (args.length < 1)
        {
            System.err.println("usage: __TESTER_CLASS__ <test-file>");
            System.exit(2);
        }
        FileInputStream in = new FileInputStream(args[0]);
        __SCANNER_FQ__ scanner = new __SCANNER_FQ__(in);
        __PARSER_FQ__ parser = new __PARSER_FQ__(scanner);
        // Safety bound so a buggy hasNext() can't loop forever.
        int safety = 100000;
        while (scanner.hasNext() && safety-- > 0)
        {
            __LOOP_BODY__
        }
    }
}
"""

# AST driver. Parser returns AST nodes; we exec each one against a
# shared environment. The env may be split into Global/Local in some
# submissions, so the picker in build_for_ast hands us the one that
# looks most global.
_AST_TEMPLATE = """\
package parser;

import java.io.FileInputStream;

/**
 * Autograder-generated AST driver. Loads args[0] as the test source
 * file, parses each statement into an AST node, and execs it in a
 * shared Environment. Replaces the student's own ParserTester for the
 * hidden test suite.
 */
public class __TESTER_CLASS__
{
    public static void main(String[] args) throws Exception
    {
        if (args.length < 1)
        {
            System.err.println("usage: __TESTER_CLASS__ <test-file>");
            System.exit(2);
        }
        FileInputStream in = new FileInputStream(args[0]);
        __SCANNER_FQ__ scanner = new __SCANNER_FQ__(in);
        __ENV_FQ__ env = __ENV_INIT__;
        __PARSER_FQ__ parser = new __PARSER_FQ__(scanner);
        int safety = 100000;
        while (scanner.hasNext() && safety-- > 0)
        {
            __LOOP_BODY__
        }
    }
}
"""


# --------------------------------------------------------------------------- #
# Light sanity check usable from tests / one-off scripts.
# --------------------------------------------------------------------------- #

_PARSE_PROGRAM_RE = re.compile(
    r"\bparse(?:Program|Prog|Root|Pascal)\s*\(\s*\)", re.IGNORECASE,
)


def parser_has_parseProgram(parser_src: str) -> bool:
    """Cheap text-level check: does the source declare a parse-program-ish
    zero-arg method? Used by ag-codegen / ag-procedures to decide whether
    the synthetic-tester pass is worth attempting when AST resolution
    failed (e.g. the file didn't parse).
    """
    return bool(_PARSE_PROGRAM_RE.search(parser_src or ""))
