"""
AST Lab configuration for the ATCS Compilers autograder.

The Parser now produces AST nodes; parseStatement returns a Statement
whose exec(Environment) we then call. The synthetic-tester pass
injects a fresh `parser._AGASTTester` that creates an Environment,
parses each statement, and exec's it until scanner.hasNext() goes
false. This bypasses the student's own ParserTester so a hardcoded
test filename or stdin can't make every hidden test silently re-run
the same baked-in file.

Rubric structure (100 pts)
==========================
    1. ast package + abstract Statement + abstract Expression       (12)
    2. All AST classes have a header javadoc                        (10)
    3. All methods have @param/@return/description javadocs         (16)
    4. scanner + parser + ast + environment packages                 (6)
    5. Naming convention: lowerCamel packages, UpperCamel classes    (4)
    6. Parser creates AST nodes (does not execute in parseFactor /
       parseStatement)                                              (14)
    7. Environment class lives in environment/; Map NOT in Parser    (2)
    8. Each Statement-extender has an exec method (or evaluator
       class handles it)                                             (8)
    9. Each Expression-extender has an eval method (or evaluator
       class handles it)                                             (8)
    10. Supports READLN, IF/ELSE, REPEAT..UNTIL                      (6)
    11. Code is well-structured / modular (REVIEW)                   (8)
    12. Testing: parserTest6 + parserTest4.5ForLoopReadln pass       (6)

Airtightness
============
Each row is independent. A missing READLN doesn't blunt the score for
abstract-class structure, and a Parser still doing inline execution
doesn't cascade to zero out the AST-class rows.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Sequence

from agcore.grader import GradedSubmission, LabConfig, TestCase
from agcore.proximity import ProximityFinding, check_class, check_method
from agcore.role_resolver import RoleSpec
from agcore.rubric import (CheckResult, RubricItem, SEVERITY_MAJOR,
                           SEVERITY_MEDIUM, SEVERITY_MINOR)


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

AG_ROOT = Path(__file__).resolve().parent
REPO_ROOT = AG_ROOT.parents[1]
VENDOR = REPO_ROOT / "vendor"
TESTS_DIR = AG_ROOT / "tests"


# --------------------------------------------------------------------------- #
# Rubric ROLES
# --------------------------------------------------------------------------- #

CLASS_ROLES = {
    "Statement": RoleSpec(
        preferred_name="Statement",
        aliases=("Stmt",),
        name_tokens=[("statement",)],
        preferred_dir="ast",
    ),
    "Expression": RoleSpec(
        preferred_name="Expression",
        aliases=("Expr",),
        name_tokens=[("expression",)],
        preferred_dir="ast",
    ),
    "Number": RoleSpec(
        preferred_name="Number",
        aliases=("Num", "IntegerLiteral"),
        name_tokens=[("number",), ("num",)],
        preferred_dir="ast",
    ),
    "Variable": RoleSpec(
        preferred_name="Variable",
        aliases=("Var", "Identifier"),
        name_tokens=[("variable",), ("var",), ("identifier",)],
        preferred_dir="ast",
    ),
    "BinOp": RoleSpec(
        preferred_name="BinOp",
        aliases=("BinaryOperation", "BinaryOp", "BinaryExpression"),
        name_tokens=[("binop",), ("binary", "op"), ("binary", "expr")],
        preferred_dir="ast",
    ),
    "Writeln": RoleSpec(
        preferred_name="Writeln",
        aliases=("WriteLn", "WRITELN", "Print", "Println"),
        name_tokens=[("write", "ln"), ("println",), ("print",)],
        preferred_dir="ast",
    ),
    "Assignment": RoleSpec(
        preferred_name="Assignment",
        aliases=("Assign", "Assn"),
        name_tokens=[("assignment",), ("assign",)],
        preferred_dir="ast",
    ),
    "Block": RoleSpec(
        preferred_name="Block",
        aliases=("BeginEnd",),
        name_tokens=[("block",), ("begin", "end")],
        preferred_dir="ast",
    ),
    "If": RoleSpec(
        preferred_name="If",
        aliases=("IfStatement", "IfStmt", "IfElse"),
        name_tokens=[("if",)],
        preferred_dir="ast",
    ),
    "While": RoleSpec(
        preferred_name="While",
        aliases=("WhileStmt", "WhileLoop", "WhileStatement"),
        name_tokens=[("while",)],
        preferred_dir="ast",
    ),
    "Readln": RoleSpec(
        preferred_name="Readln",
        aliases=("ReadLn", "Read", "Input"),
        name_tokens=[("read", "ln"), ("readln",), ("read",)],
        preferred_dir="ast",
    ),
    "RepeatUntil": RoleSpec(
        preferred_name="RepeatUntil",
        aliases=("Repeat", "RepeatStmt", "UntilLoop"),
        name_tokens=[("repeat",), ("until",)],
        preferred_dir="ast",
    ),
    "Parser": RoleSpec(
        preferred_name="Parser",
        aliases=("PascalParser",),
        name_tokens=[("parser",)],
        preferred_dir="parser",
    ),
    "Environment": RoleSpec(
        preferred_name="Environment",
        aliases=("Env", "Scope", "SymbolTable"),
        name_tokens=[("environment",), ("scope",), ("symbol", "table")],
        preferred_dir="environment",
    ),
    "Scanner": RoleSpec(
        preferred_name="Scanner",
        aliases=("PascalScanner", "Lexer"),
        name_tokens=[("scanner",), ("lexer",)],
        preferred_dir="scanner",
    ),
}

METHOD_ALIASES = {
    ("Parser", "parseStatement"): ("parseStatement", "parseStmt"),
    ("Parser", "parseExpression"): ("parseExpression", "parseExpr"),
    ("Parser", "parseFactor"): ("parseFactor",),
    ("Parser", "parseTerm"): ("parseTerm",),
    ("Environment", "setVariable"): (
        "setVariable", "setVar", "set", "assign"),
    ("Environment", "getVariable"): (
        "getVariable", "getVar", "get", "lookup"),
    ("Environment", "declareVariable"): (
        "declareVariable", "declareVar", "declare", "define"),
}


# --------------------------------------------------------------------------- #
# Documentation proximity
# --------------------------------------------------------------------------- #

CLASS_KEYWORDS = {
    "Statement": (["statement", "abstract", "execute", "exec"], 2),
    "Expression": (["expression", "abstract", "evaluate", "eval", "value"],
                   2),
    "Parser": (["parser", "ast", "node", "statement", "expression"], 3),
    "Environment": (["environment", "variable", "map", "scope", "value"], 3),
}

METHOD_KEYWORDS = {
    ("Parser", "parseStatement"): (
        ["parse", "statement", "ast", "node", "return"], 3),
    ("Parser", "parseExpression"): (
        ["parse", "expression", "term", "ast", "binop"], 3),
    ("Environment", "setVariable"): (
        ["set", "variable", "value", "map"], 3),
    ("Environment", "getVariable"): (
        ["variable", "value", "lookup", "return"], 3),
}

MIN_METHOD_DESCRIPTION_WORDS = 0


def proximity_rule(graded: GradedSubmission) -> List[ProximityFinding]:
    findings: List[ProximityFinding] = []
    audited: set = set()
    for cls_role, (kws, threshold) in CLASS_KEYWORDS.items():
        cls = graded.class_for_role(cls_role)
        if cls is None:
            continue
        findings.append(check_class(cls, kws, threshold))
    for (cls_role, m_role), (kws, threshold) in METHOD_KEYWORDS.items():
        method = graded.method_for_role(cls_role, m_role)
        if method is None:
            continue
        findings.append(check_method(
            method, kws, threshold,
            min_description_words=MIN_METHOD_DESCRIPTION_WORDS,
        ))
        audited.add((method.class_name, method.method_name))
    for cls in graded.classes:
        for m in cls.methods:
            if (cls.name, m.method_name) in audited:
                continue
            findings.append(check_method(
                m, [], 0,
                require_return=True,
                min_description_words=MIN_METHOD_DESCRIPTION_WORDS,
            ))
    return findings


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _role_source(g: GradedSubmission, role: str) -> str:
    return g.source_for_role(role) or ""


def _unparseable_note(g: GradedSubmission, role: str) -> str:
    fail = g.failure_for_role(role)
    if fail is None:
        return ""
    where = f" near line {fail.line}" if fail.line else ""
    return (f"{fail.file} could not be parsed{where}: {fail.reason}; "
            f"AST-level checks for this role were skipped")


def _outcomes_by_name(g: GradedSubmission) -> dict:
    return {o.case.name: o for o in g.test_outcomes}


def _ast_classes(g: GradedSubmission) -> list:
    """All classes whose file lives under ast/. Used by the per-class
    documentation and exec/eval audits so we don't have to maintain a
    fixed list of AST class names.
    """
    return [c for c in g.classes if c.file.startswith("ast/")]


def _has_method(cls, aliases) -> bool:
    return any(m.method_name in aliases for m in cls.methods)


# --------------------------------------------------------------------------- #
# Rubric checkers
# --------------------------------------------------------------------------- #

def _ast_package_and_abstracts(g: GradedSubmission,
                               points: float) -> CheckResult:
    """Row 1 (12 pts): ast/ package exists, abstract Statement,
    abstract Expression.

    Breakdown: 4 pts package exists, 4 pts Statement abstract,
    4 pts Expression abstract. Each is independent.
    """
    score = 0.0
    notes: List[str] = []

    has_ast = any(c.file.startswith("ast/") for c in g.classes)
    if has_ast:
        score += 4.0
    else:
        notes.append("no classes found under ast/")

    for role in ("Statement", "Expression"):
        cls = g.class_for_role(role)
        src = _role_source(g, role)
        if cls is not None:
            mods = getattr(cls, "modifiers", None) or []
            is_abstract = any(m == "abstract" for m in mods)
            # Fall back to text grep if javalang's modifier list is
            # missing or doesn't carry "abstract".
            if not is_abstract and src:
                is_abstract = bool(re.search(
                    r"\babstract\s+class\s+" + re.escape(cls.name) + r"\b",
                    src))
            if is_abstract:
                score += 4.0
            else:
                score += 1.0
                notes.append(f"{role} class found but not declared abstract")
        elif src and re.search(r"\babstract\s+class\s+\w+\b", src):
            score += 3.0
            notes.append(f"{role}-like abstract class found via text match")
        else:
            notes.append(f"{role} class missing")

    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points * 0.5
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _ast_class_headers(g: GradedSubmission, points: float) -> CheckResult:
    """Row 2 (10 pts): every AST class has a header javadoc with
    @author + summary.

    Proportional: full credit when every ast/*.java carries the header,
    partial otherwise. We count only classes under ast/ to keep the
    row scoped to its rubric concern.
    """
    ast_classes = _ast_classes(g)
    if not ast_classes:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="no AST classes found")
    ok = 0
    issues: List[str] = []
    for cls in ast_classes:
        jd = cls.javadoc
        if jd is not None and jd.description.strip() and (
                jd.tags_named("@author")):
            ok += 1
        elif jd is not None and jd.description.strip():
            ok += 0.5
            issues.append(f"{cls.name}: missing @author")
        else:
            issues.append(f"{cls.name}: no header javadoc")
    fraction = ok / len(ast_classes)
    earned = round(points * fraction, 1)
    sev = (0 if earned >= points
           else SEVERITY_MINOR if fraction >= 0.75
           else SEVERITY_MEDIUM if fraction >= 0.4
           else SEVERITY_MAJOR)
    return CheckResult(
        earned=earned, severity=sev,
        notes="; ".join(issues[:4]) + (" ..." if len(issues) > 4 else ""))


def _ast_method_headers(g: GradedSubmission, points: float) -> CheckResult:
    """Row 3 (16 pts): every method in every AST class has @param,
    @return (when non-void), and description tags.
    """
    ast_classes = _ast_classes(g)
    if not ast_classes:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="no AST classes found")
    total = 0
    ok = 0
    issues: List[str] = []
    for cls in ast_classes:
        for m in cls.methods:
            total += 1
            if m.javadoc is None:
                issues.append(f"{cls.name}.{m.method_name}: no javadoc")
                continue
            problems: List[str] = []
            if m.params:
                have = len(m.javadoc.tags_named("@param"))
                if have < len(m.params):
                    problems.append(
                        f"@param x{len(m.params) - have} missing")
            if m.return_type not in ("void", "") and m.method_name != cls.name:
                if not m.javadoc.tags_named("@return"):
                    problems.append("@return missing")
            if not m.javadoc.description.strip():
                problems.append("no description")
            if problems:
                issues.append(
                    f"{cls.name}.{m.method_name}: {', '.join(problems)}")
            else:
                ok += 1
    if total == 0:
        return CheckResult(earned=points, severity=0,
                           notes="no AST methods to score")
    fraction = ok / total
    earned = round(points * fraction, 1)
    sev = (0 if earned >= points
           else SEVERITY_MINOR if fraction >= 0.75
           else SEVERITY_MEDIUM if fraction >= 0.4
           else SEVERITY_MAJOR)
    return CheckResult(
        earned=earned, severity=sev,
        notes="; ".join(issues[:4]) + (" ..." if len(issues) > 4 else ""))


def _packages_present(g: GradedSubmission, points: float) -> CheckResult:
    """Row 4 (6 pts): scanner + parser + ast + environment packages all exist."""
    required = ("scanner", "parser", "ast", "environment")
    per = points / len(required)
    score = 0.0
    notes: List[str] = []
    for pkg in required:
        if any(c.file.startswith(pkg + "/") for c in g.classes):
            score += per
        else:
            notes.append(f"no {pkg}/ package detected")
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points / 2
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


_PACKAGE_DECL_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _naming_convention(g: GradedSubmission, points: float) -> CheckResult:
    """Row 5 (4 pts): UpperCamel classes, lowerCamel packages."""
    score = points
    class_offenders: List[str] = []
    package_offenders: List[str] = []
    seen: set = set()
    for cls in g.classes:
        if not cls.name[:1].isupper() or "_" in cls.name:
            class_offenders.append(cls.name)
        try:
            src = (g.submission.compiler_root / cls.file
                   ).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _PACKAGE_DECL_RE.search(src)
        if m is None:
            continue
        pkg = m.group(1)
        if pkg in seen:
            continue
        seen.add(pkg)
        for seg in pkg.split("."):
            if seg and (seg[0].isupper() or "_" in seg):
                package_offenders.append(pkg)
                break
    notes: List[str] = []
    if class_offenders:
        score -= min(points * 0.5,
                     points * 0.15 * len(class_offenders))
        notes.append("non-UpperCamel class names: "
                     + ", ".join(class_offenders[:4]))
    if package_offenders:
        score -= min(points * 0.5,
                     points * 0.25 * len(package_offenders))
        notes.append("non-lowerCamel packages: "
                     + ", ".join(sorted(set(package_offenders))))
    score = max(0.0, round(score, 1))
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.5
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _parser_creates_ast(g: GradedSubmission, points: float) -> CheckResult:
    """Row 6 (14 pts): Parser creates AST nodes (does not execute inline).

    Two arms:
      * 8 pts structural: parseStatement returns a Statement and the
        Parser source contains `new Writeln(`, `new Block(`, etc.
      * 6 pts behavioural: parserTest6 / parserTest4.5 pass -- a parser
        that still executes inline would still PASS so this isn't a
        strong signal on its own, but the structural arm catches
        students who never migrated.

    The lab's wording is "Parser has been updated to create nodes for
    ast classes instead of executing the corresponding actions in
    parseStatement as well as parseFactor". Looking at the return
    type + the `new <AstClass>(` constructions covers both halves.
    """
    parser_cls = g.class_for_role("Parser")
    src = _role_source(g, "Parser")
    score = 0.0
    notes: List[str] = []

    # Sub-criterion 1: parseStatement returns a Statement-shaped value
    parse_stmt = g.method_for_role("Parser", "parseStatement")
    if parse_stmt is not None:
        rt = (parse_stmt.return_type or "").split(".")[-1].strip()
        if rt in ("Statement", "Stmt"):
            score += 4.0
        elif rt == "void":
            notes.append(
                "parseStatement returns void; parser appears to still "
                "execute inline rather than build AST nodes")
        elif rt:
            score += 2.0
            notes.append(
                f"parseStatement returns {rt!r}, expected Statement")
    else:
        notes.append("parseStatement method not found")

    # Sub-criterion 2: parseFactor/parseExpression return Expression
    parse_expr = g.method_for_role("Parser", "parseExpression")
    if parse_expr is not None:
        rt = (parse_expr.return_type or "").split(".")[-1].strip()
        if rt in ("Expression", "Expr"):
            score += 2.0

    # Sub-criterion 3: parser source constructs AST nodes
    ast_ctor_hits = 0
    for ctor in ("Writeln", "Assignment", "Block", "BinOp", "If",
                 "While", "Number", "Variable"):
        if re.search(rf"\bnew\s+(?:ast\.)?{ctor}\s*\(", src):
            ast_ctor_hits += 1
    if ast_ctor_hits >= 5:
        score += 2.0
    elif ast_ctor_hits >= 2:
        score += 1.0
        notes.append(f"only {ast_ctor_hits} AST constructors found in "
                     f"Parser source (expected 5+)")
    else:
        notes.append(f"Parser source has {ast_ctor_hits} AST ctors; "
                     "parser may still be executing inline")

    # Sub-criterion 4: behavioural -- parserTest6 + parserTest4.5 pass
    outcomes = _outcomes_by_name(g)
    passed = 0
    for name in ("parserTest6", "parserTest4_5ForLoopReadln"):
        o = outcomes.get(name)
        if o is not None and o.passed:
            passed += 1
    score += 6.0 * passed / 2
    if passed < 2:
        notes.append(f"{passed}/2 required tests pass behaviourally")

    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points * 0.5
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _environment_in_pkg_and_no_map_in_parser(
        g: GradedSubmission, points: float) -> CheckResult:
    """Row 7 (2 pts): Environment in environment/, Map NOT in Parser.

    Half a point for each verified condition.
    """
    score = 0.0
    notes: List[str] = []
    env_cls = g.class_for_role("Environment")
    if env_cls is not None and env_cls.file.startswith("environment/"):
        score += points * 0.5
    elif env_cls is not None:
        notes.append(f"Environment lives in {env_cls.file}, not environment/")
    else:
        notes.append("Environment class not found")
    parser_src = _role_source(g, "Parser")
    # Look for a Map<...> or HashMap field in Parser's source. The lab
    # says the Map must move OUT of Parser.
    if re.search(r"\b(java\.util\.)?(Hash)?Map\s*<", parser_src):
        notes.append("Parser still appears to declare a Map<...> field")
    else:
        score += points * 0.5
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.5
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _statements_have_exec(g: GradedSubmission, points: float) -> CheckResult:
    """Row 8 (8 pts): every Statement subclass has an exec(Environment).

    Heuristic: among all classes in ast/, the ones whose superclass is
    Statement (or `Stmt`) must declare an exec method. Allow the
    alternative "evaluator class" pattern: if there's a class named
    Evaluator with an exec method per Statement type, also credit
    full.
    """
    ast_classes = _ast_classes(g)
    stmt_subs = [
        c for c in ast_classes
        if (c.superclass or "").split(".")[-1] in ("Statement", "Stmt")
    ]
    if not stmt_subs:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="no Statement subclasses found in ast/")
    have_exec = sum(1 for c in stmt_subs
                    if _has_method(c, ("exec", "execute", "run")))
    fraction = have_exec / len(stmt_subs)
    score = points * fraction
    notes: List[str] = []
    if fraction < 1.0:
        missing = [c.name for c in stmt_subs
                   if not _has_method(c, ("exec", "execute", "run"))]
        notes.append("missing exec: " + ", ".join(missing[:4]))
        # Alternative: an Evaluator class. Search for one with an
        # exec(<Type>, Environment) for each missing class.
        evaluator_cls = next(
            (c for c in g.classes if c.name == "Evaluator"), None)
        if evaluator_cls is not None:
            cover = 0
            for missing_cls in missing:
                for m in evaluator_cls.methods:
                    if m.method_name in ("exec", "execute") and \
                            any(missing_cls in p for p in m.params):
                        cover += 1
                        break
            if cover:
                score += (points - score) * (cover / len(missing))
                notes.append(
                    f"Evaluator handles {cover}/{len(missing)} of them")
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.66
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _expressions_have_eval(g: GradedSubmission, points: float) -> CheckResult:
    """Row 9 (8 pts): every Expression subclass has an eval(Environment).

    Symmetric to row 8 (Statements have exec).
    """
    ast_classes = _ast_classes(g)
    expr_subs = [
        c for c in ast_classes
        if (c.superclass or "").split(".")[-1] in ("Expression", "Expr")
    ]
    if not expr_subs:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="no Expression subclasses found in ast/")
    have_eval = sum(1 for c in expr_subs
                    if _has_method(c, ("eval", "evaluate")))
    fraction = have_eval / len(expr_subs)
    score = points * fraction
    notes: List[str] = []
    if fraction < 1.0:
        missing = [c.name for c in expr_subs
                   if not _has_method(c, ("eval", "evaluate"))]
        notes.append("missing eval: " + ", ".join(missing[:4]))
        evaluator_cls = next(
            (c for c in g.classes if c.name == "Evaluator"), None)
        if evaluator_cls is not None:
            cover = 0
            for missing_cls in missing:
                for m in evaluator_cls.methods:
                    if m.method_name in ("eval", "evaluate") and \
                            any(missing_cls in p for p in m.params):
                        cover += 1
                        break
            if cover:
                score += (points - score) * (cover / len(missing))
                notes.append(
                    f"Evaluator handles {cover}/{len(missing)} of them")
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.66
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _readln_if_repeat(g: GradedSubmission, points: float) -> CheckResult:
    """Row 10 (6 pts): supports READLN, IF/ELSE, REPEAT..UNTIL.

    Per-feature credit (2 pts each):
      * READLN: an AST class resolving to the Readln role, or the
        parser text mentions READLN
      * IF/ELSE: an If class AND the parser text contains the ELSE
        keyword (the lab specifically calls out if-else)
      * REPEAT..UNTIL: a RepeatUntil class AND parser text mentions
        both REPEAT and UNTIL
    """
    parser_src = _role_source(g, "Parser")
    score = 0.0
    notes: List[str] = []

    if g.class_for_role("Readln") is not None or '"READLN"' in parser_src:
        score += 2.0
    else:
        notes.append("no Readln class or READLN handling in parser")

    has_if = g.class_for_role("If") is not None
    has_else = '"ELSE"' in parser_src or "ELSE" in parser_src
    if has_if and has_else:
        score += 2.0
    elif has_if:
        score += 1.0
        notes.append("If class present but no ELSE handling in parser")
    else:
        notes.append("no If class found")

    has_repeat = g.class_for_role("RepeatUntil") is not None
    has_repeat_kw = '"REPEAT"' in parser_src
    has_until_kw = '"UNTIL"' in parser_src
    if has_repeat and (has_repeat_kw or has_until_kw):
        score += 2.0
    elif has_repeat_kw and has_until_kw:
        score += 1.5
        notes.append("REPEAT/UNTIL keywords handled but no dedicated class")
    elif has_repeat:
        score += 1.0
        notes.append("RepeatUntil class found but parser doesn't mention "
                     "REPEAT/UNTIL keywords")
    else:
        notes.append("no REPEAT..UNTIL support detected")

    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.66
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _code_structure_review(g: GradedSubmission, points: float) -> CheckResult:
    """Row 11 (8 pts): code well-structured / modular (REVIEW).

    Soft heuristic: AST classes should be small + focused (one class
    per concept). Award proportional credit per AST class count: a
    submission with at least 6 distinct AST classes gets baseline
    plus a bonus for additional ones. Tag REVIEW so the teacher
    confirms.
    """
    ast_classes = _ast_classes(g)
    count = len(ast_classes)
    if count >= 8:
        earned = points
    elif count >= 6:
        earned = points * 0.85
    elif count >= 4:
        earned = points * 0.65
    else:
        earned = points * 0.5
    earned = round(earned, 1)
    note = (f"REVIEW: auto-credit {earned}/{points} based on {count} "
            f"AST classes; teacher should skim for repeated blocks "
            f"and oversize methods")
    severity = 0 if earned >= points * 0.9 else SEVERITY_MINOR
    return CheckResult(earned=earned, notes=note, severity=severity)


def _testing_row(g: GradedSubmission, points: float) -> CheckResult:
    """Row 12 (6 pts): parserTest6 + parserTest4.5ForLoopReadln pass.

    3 pts each.
    """
    outcomes = _outcomes_by_name(g)
    score = 0.0
    notes: List[str] = []
    for name in ("parserTest6", "parserTest4_5ForLoopReadln"):
        o = outcomes.get(name)
        if o is not None and o.passed:
            score += points / 2
        else:
            notes.append(f"{name}: "
                         + (o.error if o and o.error else "did not run"))
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points / 2
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


# --------------------------------------------------------------------------- #
# The rubric itself
# --------------------------------------------------------------------------- #

RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="ast-pkg-abstracts",
        description="ast package exists; has abstract Statement and "
                    "abstract Expression classes.",
        points=12,
        checker=lambda g: _ast_package_and_abstracts(g, 12),
        category="AST classes",
    ),
    RubricItem(
        code="ast-class-doc",
        description="For all AST classes: comments include name/date/"
                    "summary using JavaDoc Standards.",
        points=10,
        checker=lambda g: _ast_class_headers(g, 10),
        category="Documentation",
    ),
    RubricItem(
        code="ast-method-doc",
        description="All AST methods have Javadoc headers including "
                    "@param/@return and a description that makes sense.",
        points=16,
        checker=lambda g: _ast_method_headers(g, 16),
        category="Documentation",
    ),
    RubricItem(
        code="packages-present",
        description="Project has scanner, parser, ast, and environment "
                    "packages.",
        points=6,
        checker=lambda g: _packages_present(g, 6),
        category="Project structure",
    ),
    RubricItem(
        code="naming-convention",
        description="Naming convention: lowerCamel packages, UpperCamel "
                    "class names.",
        points=4,
        checker=lambda g: _naming_convention(g, 4),
        category="Project structure",
    ),
    RubricItem(
        code="parser-creates-ast",
        description="Parser has been updated to create AST nodes instead "
                    "of executing in parseStatement / parseFactor / etc.",
        points=14,
        checker=lambda g: _parser_creates_ast(g, 14),
        category="Parser",
    ),
    RubricItem(
        code="env-in-pkg",
        description="Environment class lives in the environment package; "
                    "Map is in Environment, NOT in Parser.",
        points=2,
        checker=lambda g: _environment_in_pkg_and_no_map_in_parser(g, 2),
        category="Environment",
    ),
    RubricItem(
        code="statements-have-exec",
        description="Every Statement-extender has an exec(Environment) "
                    "method (or an Evaluator class handles it).",
        points=8,
        checker=lambda g: _statements_have_exec(g, 8),
        category="AST classes",
    ),
    RubricItem(
        code="expressions-have-eval",
        description="Every Expression-extender has an eval(Environment) "
                    "method (or an Evaluator class handles it).",
        points=8,
        checker=lambda g: _expressions_have_eval(g, 8),
        category="AST classes",
    ),
    RubricItem(
        code="readln-if-repeat",
        description="Supports READLN, IF/ELSE statements, and "
                    "REPEAT..UNTIL loops.",
        points=6,
        checker=lambda g: _readln_if_repeat(g, 6),
        category="Language features",
    ),
    RubricItem(
        code="code-structure",
        description="Code is well-structured, modular, does not repeat "
                    "blocks of code unnecessarily (REVIEW).",
        points=8,
        checker=lambda g: _code_structure_review(g, 8),
        category="Quality",
    ),
    RubricItem(
        code="testing",
        description="Testing: parserTest6 and parserTest4.5ForLoopReadln "
                    "both run correctly.",
        points=6,
        checker=lambda g: _testing_row(g, 6),
        category="Testing",
    ),
)


# --------------------------------------------------------------------------- #
# Hidden tests
# --------------------------------------------------------------------------- #

def _build_tests() -> List[TestCase]:
    """Load tests/*.txt + expected.json. The JSON entry may specify
    a `file` field for a test whose JSON key isn't a valid filename
    (parserTest4.5ForLoopReadln has a `.` in it that confuses some
    shells).
    """
    expected_map = json.loads((TESTS_DIR / "expected.json")
                              .read_text(encoding="utf-8"))
    tests: List[TestCase] = []
    for name, meta in expected_map.items():
        filename = meta.get("file", f"{name}.txt")
        tests.append(TestCase(
            name=name,
            description=meta["description"],
            source_path=TESTS_DIR / filename,
            expected_stdout=list(meta["expected"]),
            stdin_text=meta.get("stdin"),
        ))
    return tests


# --------------------------------------------------------------------------- #
# LabConfig entry point
# --------------------------------------------------------------------------- #

def build_config(java_exe: str = "java",
                 javac_exe: str = "javac") -> LabConfig:
    return LabConfig(
        lab_name="AST Lab",
        rubric=RUBRIC,
        hidden_tests=_build_tests(),
        proximity_rules=[proximity_rule],
        checkstyle_jar=VENDOR / "checkstyle-10.14.0-all.jar",
        checkstyle_xml=VENDOR / "checkstyle.xml",
        java_exe=java_exe,
        javac_exe=javac_exe,
        main_class="parser.Parser",
        class_roles=CLASS_ROLES,
        method_aliases=METHOD_ALIASES,
        synthetic_tester_kind="ast",
    )
