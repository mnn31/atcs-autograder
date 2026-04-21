"""
Procedures Lab specific configuration. Every check, keyword set, and hidden
test case that the Procedures Lab rubric requires is wired up here and handed
to the generic agcore.grader.

The rubric text below is taken verbatim from the ATCS-Compilers Procedures
Peer Review sheet so the teacher can compare row-for-row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Sequence

from agcore import java_runner
from agcore.grader import GradedSubmission, LabConfig, TestCase
from agcore.javadoc_parser import ClassRecord, MethodRecord
from agcore.proximity import ProximityFinding, check_class, check_method
from agcore.role_resolver import RoleSpec
from agcore.rubric import (CheckResult, RubricItem, SEVERITY_MAJOR,
                           SEVERITY_MEDIUM, SEVERITY_MINOR)


# --------------------------------------------------------------------------- #
# Rubric ROLES -- fuzzy class + method resolution
# --------------------------------------------------------------------------- #
#
# The peer-review rubric names specific classes ("ProcedureCall",
# "ProcedureDeclaration", etc.) and methods ("exec", "eval",
# "declareVariable", ...). Most students follow those names, but a few
# rename things (ProcedureDecl, Call, declareVar, parseProc, ...) and a
# human grading the peer review would still credit them. CLASS_ROLES and
# METHOD_ALIASES reproduce that mental step:
#
#   * CLASS_ROLES maps a role name -> RoleSpec. The resolver scores every
#     parsed class on name match (exact / alias / token-containment),
#     superclass, required methods, and directory, and returns the highest
#     scorer. See agcore/role_resolver.py for the exact weights.
#
#   * METHOD_ALIASES maps (class_role, method_role) -> ordered list of
#     acceptable method names. The first hit wins. Rubric-preferred
#     spellings go first so students who DID use the canonical name are
#     matched instantly.
#
# Result: a student who writes `class ProcCall extends Expression { public
# int eval(Environment env) { ... } }` resolves just like the canonical
# "ProcedureCall.eval" and still gets rubric credit.
# --------------------------------------------------------------------------- #

CLASS_ROLES = {
    "ProcedureDeclaration": RoleSpec(
        preferred_name="ProcedureDeclaration",
        aliases=("ProcedureDecl", "ProcDecl", "ProcDeclaration",
                 "ProcedureDef", "ProcedureDefinition", "ProcDef"),
        name_tokens=[("procedure", "decl"), ("procedure", "def"),
                     ("proc", "decl"), ("proc", "def")],
        superclass="Statement",
        required_methods=("exec", "execute"),
        preferred_dir="ast",
    ),
    "ProcedureCall": RoleSpec(
        preferred_name="ProcedureCall",
        aliases=("ProcCall", "ProcedureInvocation", "ProcedureInvoke",
                 "ProcInvocation"),
        name_tokens=[("procedure", "call"), ("proc", "call"),
                     ("procedure", "invoke"),
                     ("procedure", "invocation")],
        superclass="Expression",
        required_methods=("eval", "evaluate"),
        preferred_dir="ast",
    ),
    "Program": RoleSpec(
        preferred_name="Program",
        aliases=("PascalProgram", "Programme", "Root"),
        name_tokens=[("program",)],
        required_methods=("exec", "execute", "run"),
        preferred_dir="ast",
    ),
    "Environment": RoleSpec(
        preferred_name="Environment",
        aliases=("Env", "Scope", "SymbolTable"),
        name_tokens=[("environment",), ("scope",), ("symbol", "table")],
        preferred_dir="environment",
    ),
    "Parser": RoleSpec(
        preferred_name="Parser",
        aliases=("PascalParser",),
        name_tokens=[("parser",)],
        preferred_dir="parser",
    ),
}

METHOD_ALIASES = {
    ("ProcedureDeclaration", "exec"): ("exec", "execute", "run"),
    ("ProcedureDeclaration", "ProcedureDeclaration"): (
        "ProcedureDeclaration", "ProcedureDecl", "ProcDecl",
        "ProcedureDef", "ProcedureDefinition"),
    ("ProcedureCall", "eval"): ("eval", "evaluate"),
    ("ProcedureCall", "ProcedureCall"): (
        "ProcedureCall", "ProcCall", "ProcedureInvocation"),
    ("Program", "exec"): ("exec", "execute", "run"),
    ("Program", "Program"): ("Program", "PascalProgram"),
    ("Environment", "declareVariable"): (
        "declareVariable", "declareVar", "declare", "defineVariable",
        "define"),
    ("Environment", "setVariable"): (
        "setVariable", "setVar", "set", "assignVariable", "assign"),
    ("Environment", "getVariable"): (
        "getVariable", "getVar", "get", "lookupVariable", "lookup"),
    ("Environment", "setProcedure"): (
        "setProcedure", "setProc", "defineProcedure", "declareProcedure",
        "registerProcedure"),
    ("Environment", "getProcedure"): (
        "getProcedure", "getProc", "lookupProcedure"),
    ("Parser", "parseProgram"): (
        "parseProgram", "parseProg"),
    ("Parser", "parseProcedureDeclaration"): (
        "parseProcedureDeclaration", "parseProcedure", "parseProc",
        "parseProcedureDecl", "parseProcDecl", "parseProcDef"),
    ("Parser", "parseFactor"): ("parseFactor",),
}


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

AG_ROOT = Path(__file__).resolve().parent
REPO_ROOT = AG_ROOT.parents[1]   # autograder-work/
VENDOR = REPO_ROOT / "vendor"
TESTS_DIR = AG_ROOT / "tests"


# --------------------------------------------------------------------------- #
# Keyword sets for proximity checking
# --------------------------------------------------------------------------- #
#
# Each entry says: "documentation on this class or method should mention, at
# minimum, <threshold> of these keywords". Keep the sets short and domain-y
# so students can't cheat by stuffing every filler word into a javadoc.
# --------------------------------------------------------------------------- #

CLASS_KEYWORDS = {
    "ProcedureDeclaration": (
        ["procedure", "declaration", "parameter", "body", "name"], 3),
    "ProcedureCall": (
        ["procedure", "call", "argument", "environment", "evaluate",
         "return"], 3),
    "Program": (
        ["program", "procedure", "main", "statement", "root", "ast"], 3),
    "Environment": (
        ["environment", "variable", "procedure", "scope", "parent",
         "global"], 3),
    "Parser": (
        ["parser", "token", "statement", "expression", "procedure",
         "recursive"], 3),
}

# Per-method keyword packs for the most rubric-critical methods. Getters and
# trivial helpers fall back to "needs a short description + right @-tags".
METHOD_KEYWORDS = {
    ("ProcedureDeclaration", "exec"): (
        ["register", "procedure", "environment", "declaration", "symbol",
         "table", "name"], 3),
    ("ProcedureDeclaration", "ProcedureDeclaration"): (   # constructor
        ["procedure", "declaration", "parameter", "body", "name"], 3),
    ("ProcedureCall", "eval"): (
        ["evaluate", "procedure", "call", "argument", "environment",
         "parameter", "return", "body"], 3),
    ("ProcedureCall", "ProcedureCall"): (                   # constructor
        ["procedure", "call", "argument", "expression"], 2),
    ("Program", "exec"): (
        ["procedure", "declaration", "main", "statement", "environment",
         "register"], 3),
    ("Program", "Program"): (
        ["program", "procedure", "main", "statement"], 3),
    ("Environment", "declareVariable"): (
        ["declare", "variable", "current", "local", "environment", "scope"],
        3),
    ("Environment", "setVariable"): (
        ["set", "variable", "global", "local", "scope", "parent"], 3),
    ("Environment", "getVariable"): (
        ["variable", "lookup", "parent", "global", "return", "scope"], 3),
    ("Environment", "setProcedure"): (
        ["set", "procedure", "global", "environment"], 3),
    ("Environment", "getProcedure"): (
        ["procedure", "lookup", "global", "return"], 2),
    ("Parser", "parseProgram"): (
        ["parse", "program", "procedure", "declaration", "statement"], 3),
    ("Parser", "parseProcedureDeclaration"): (
        ["parse", "procedure", "declaration", "parameter", "body"], 3),
    ("Parser", "parseFactor"): (
        ["factor", "procedure", "call", "parse", "identifier"], 3),
}

# Minimum word-count for a method's description prose. Set to 0 to disable
# -- many perfectly adequate getters document in 3-4 words ("Returns the
# procedure's name."), so mechanical enforcement here creates noise without
# catching real problems. Raise to 3 or 5 if you want to flag one-word
# "TODO" stubs automatically.
MIN_METHOD_DESCRIPTION_WORDS = 0


# --------------------------------------------------------------------------- #
# Proximity rule: run class + method checks for every entry above
# --------------------------------------------------------------------------- #

def proximity_rule(graded: GradedSubmission) -> List[ProximityFinding]:
    """Apply the keyword packs above to the parsed submission.

    Lookups go through class_for_role / method_for_role so a renamed class
    (e.g. "ProcCall" instead of "ProcedureCall") is still matched and its
    docs are still scored against the right keyword pack.
    """
    findings: List[ProximityFinding] = []
    # Track which concrete (class_name, method_name) pairs were already
    # handled by the targeted METHOD_KEYWORDS pass, so the "audit the rest"
    # pass below doesn't score the same method twice with a different
    # configuration. We record the RESOLVED names, not the role names, so
    # the audit comparison is apples-to-apples with cls.methods.
    audited_pairs: set = set()

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
        audited_pairs.add((method.class_name, method.method_name))

    # Audit every other method: must have a javadoc, the right @param/@return
    # tags, and a non-trivial description. We deliberately do NOT require
    # @precondition/@postcondition here -- students often document pre/post
    # in prose or skip them for trivial getters, and mechanical enforcement
    # produces too many false-positive REVIEWs for a teacher to skim.
    for cls in graded.classes:
        for m in cls.methods:
            if (cls.name, m.method_name) in audited_pairs:
                continue
            findings.append(check_method(
                m, [], 0,
                require_return=True,
                min_description_words=MIN_METHOD_DESCRIPTION_WORDS,
            ))
    return findings


# --------------------------------------------------------------------------- #
# Rubric checkers -- one per row on the peer review PDF
# --------------------------------------------------------------------------- #

def _has_both_ast_classes(g: GradedSubmission) -> CheckResult:
    have_decl = g.class_for_role("ProcedureDeclaration") is not None
    have_call = g.class_for_role("ProcedureCall") is not None
    if have_decl and have_call:
        return CheckResult(earned=10, notes="", severity=0)
    missing = []
    parse_notes: List[str] = []
    for role, present in (("ProcedureDeclaration", have_decl),
                          ("ProcedureCall", have_call)):
        if present:
            continue
        missing.append(role)
        fail = g.failure_for_role(role)
        if fail is not None:
            where = f" near line {fail.line}" if fail.line else ""
            parse_notes.append(
                f"{fail.file} failed to parse{where}: {fail.reason}")
    # If BOTH the missing roles are explained by parse failures, award
    # partial credit (3/10) -- the class is almost certainly present, we
    # just can't see it. Zero credit for a truly absent class; half
    # credit for a syntactically broken one that still has the right
    # file name on disk.
    earned = 3.0 if parse_notes and len(parse_notes) == len(missing) else 0.0
    note = f"missing AST class (or unrecognised role): {', '.join(missing)}"
    if parse_notes:
        note = ("; ".join(parse_notes)
                + " -- structural checks skipped for these classes")
    severity = (SEVERITY_MEDIUM if earned > 0 else SEVERITY_MAJOR)
    return CheckResult(earned=earned, notes=note, severity=severity)


def _class_header_tags(g: GradedSubmission,
                       class_role: str, points: float) -> CheckResult:
    """Check class-level javadoc includes @author + @version + a summary.

    class_role is a rubric role name ("ProcedureCall") not a literal class
    name -- g.class_for_role handles student renames.
    """
    cls = g.class_for_role(class_role)
    if cls is None:
        return CheckResult(earned=0,
                           notes=f"{class_role} not found (no class matched "
                                 f"the expected role)",
                           severity=SEVERITY_MAJOR)
    if cls.javadoc is None:
        return CheckResult(earned=0, notes="no class javadoc",
                           severity=SEVERITY_MAJOR)
    has_author = bool(cls.javadoc.tags_named("@author"))
    has_version = bool(cls.javadoc.tags_named("@version"))
    has_summary = bool(cls.javadoc.description.strip())
    score = 0.0
    notes = []
    # Split the points three ways: summary / author / version.
    per = points / 3.0
    if has_summary:
        score += per
    else:
        notes.append("no summary prose")
    if has_author:
        score += per
    else:
        notes.append("missing @author")
    if has_version:
        score += per
    else:
        notes.append("missing @version")
    severity = 0 if score >= points else (SEVERITY_MEDIUM if score > 0
                                          else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _class_methods_tags(g: GradedSubmission, class_role: str,
                        points: float) -> CheckResult:
    """Check every method in the named class has a javadoc with @param (for
    each parameter) and @return (if non-void).
    """
    cls = g.class_for_role(class_role)
    if cls is None:
        return CheckResult(earned=0,
                           notes=f"{class_role} not found (no class matched "
                                 f"the expected role)",
                           severity=SEVERITY_MAJOR)
    if not cls.methods:
        return CheckResult(earned=points, notes="no methods",
                           severity=0)
    ok = 0
    issues: List[str] = []
    for m in cls.methods:
        if m.javadoc is None:
            issues.append(f"{m.method_name}: no javadoc")
            continue
        problems: List[str] = []
        if m.params:
            have_params = len(m.javadoc.tags_named("@param"))
            if have_params < len(m.params):
                problems.append(
                    f"@param x{len(m.params) - have_params} missing")
        # m.method_name == cls.name means this is a constructor -- no @return.
        if m.return_type not in ("void", "") and m.method_name != cls.name:
            if not m.javadoc.tags_named("@return"):
                problems.append("@return missing")
        if not m.javadoc.description.strip():
            problems.append("no description")
        if problems:
            issues.append(f"{m.method_name}: {', '.join(problems)}")
        else:
            ok += 1
    fraction = ok / len(cls.methods)
    earned = round(points * fraction, 1)
    severity = 0
    if earned < points:
        severity = SEVERITY_MINOR if fraction >= 0.66 else \
            SEVERITY_MEDIUM if fraction >= 0.33 else SEVERITY_MAJOR
    return CheckResult(earned=earned,
                       notes=("; ".join(issues[:3]) +
                              (" ..." if len(issues) > 3 else "")),
                       severity=severity)


def _procdecl_extends_and_exec(g: GradedSubmission) -> CheckResult:
    cls = g.class_for_role("ProcedureDeclaration")
    if cls is None:
        return CheckResult(earned=0, notes="ProcedureDeclaration role missing",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if cls.superclass == "Statement":
        score += 5
    else:
        notes.append(f"does not extend Statement (extends {cls.superclass!r})")
    exec_method = g.method_for_role("ProcedureDeclaration", "exec")
    if exec_method is None:
        notes.append("no exec method")
    else:
        score += 3
        # Heuristic: doc mentions registering / symbol table / setProcedure.
        doc_text = (exec_method.javadoc.plain_text()
                    if exec_method.javadoc else "")
        if any(k in doc_text for k in
               ("register", "procedure", "symbol", "setprocedure")):
            score += 2
        else:
            notes.append("exec javadoc does not mention registering the "
                         "procedure/symbol-table")
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _procdecl_params_and_body(g: GradedSubmission) -> CheckResult:
    cls = g.class_for_role("ProcedureDeclaration")
    if cls is None:
        return CheckResult(earned=0, notes="ProcedureDeclaration role missing",
                           severity=SEVERITY_MAJOR)
    # Look for a constructor taking (String name, List<String> params, Statement body)
    score = 0.0
    notes: List[str] = []
    # A Java constructor's method_name is always the class's own name. Since
    # the resolver may have matched a renamed class, use cls.name (not the
    # role name) to find the constructor.
    ctor = next((m for m in cls.methods
                 if m.method_name == cls.name), None)
    if ctor is None:
        notes.append("no constructor found")
    else:
        # Constructor should have three parameters named name, params, body
        # (or similar). We only require count.
        if len(ctor.params) >= 2:
            score += 3
        else:
            notes.append(f"constructor has {len(ctor.params)} params "
                         f"(expected >= 2)")
    # Look for a field list/params and a body.
    src = _role_source(g, "ProcedureDeclaration")
    if src is None:
        return CheckResult(earned=round(score, 1), notes="; ".join(notes),
                           severity=SEVERITY_MAJOR)
    if "List<" in src or "java.util.List" in src:
        score += 2
    else:
        notes.append("no List<> field for parameters")
    if "Statement" in src:
        score += 1
    else:
        notes.append("no Statement body field")
    severity = 0 if score >= 6 else (SEVERITY_MINOR if score >= 4
                                     else SEVERITY_MEDIUM)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _proccall_extends_and_eval(g: GradedSubmission) -> CheckResult:
    """Score ProcedureCall's eval() on BOTH structure and behaviour.

    Previously this was a pure grep: if the source contained the right
    keywords, it got the points. That gave surprisingly high scores to a
    stub eval() that merely called env.getProcedure and then ignored
    parameters -- semantically broken but structurally passable.

    New approach: award up to 6 pts on source structure, then apply a
    behavioural cap based on how many of the eval-sensitive hidden tests
    actually pass. If none pass (and the code compiled), eval is
    clearly wrong no matter what the source says; we cap the rubric
    score so the grep can't inflate it.
    """
    cls = g.class_for_role("ProcedureCall")
    if cls is None:
        return CheckResult(earned=0, notes="ProcedureCall role missing",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    # -- Structural sub-score, up to 6 pts. Spread the credit so no single
    # keyword can clear more than 2 pts by itself.
    if cls.superclass == "Expression":
        score += 2
    else:
        notes.append(f"does not extend Expression (extends {cls.superclass!r})")
    eval_m = g.method_for_role("ProcedureCall", "eval")
    if eval_m is None:
        notes.append("no eval method")
    else:
        score += 1
        src = _role_source(g, "ProcedureCall") or ""
        if "getProcedure" in src:
            score += 1
        else:
            notes.append("eval does not call getProcedure on the env")
        if "globalScope" in src or "getGlobal" in src or "new Environment" in src:
            score += 1
        else:
            notes.append("no child environment created off the global one")
        if "declareVariable" in src or "setVariable" in src:
            score += 1
        else:
            notes.append("parameters never bound via declare/setVariable")

    # -- Behavioural sub-score, up to 4 pts. Only counted if the project
    # compiled; otherwise we defer to the compile-failure rubric row and
    # don't double-penalise here.
    eval_sensitive = {
        "test04_return", "test05_recursion", "test07_return_in_expr",
        "test08_nested_call", "test09_conditional_return",
        "test10_fibonacci",
    }
    outcomes = [t for t in g.test_outcomes
                if t.case.name in eval_sensitive]
    if g.compile_result.success and outcomes:
        passed = sum(1 for t in outcomes if t.passed)
        total = len(outcomes)
        behavioural = round(4.0 * passed / total, 1)
        score += behavioural
        if passed < total:
            notes.append(
                f"eval-sensitive tests: only {passed}/{total} pass "
                f"(procedure calls / returns don't behave correctly)"
            )
        # When ZERO eval-sensitive tests pass the source grep is
        # coincidental: cap the whole rubric row at 4 so a well-
        # keyword-stuffed but broken eval can't scrape >50%.
        if passed == 0:
            cap = 4.0
            if score > cap:
                notes.append(f"no eval-sensitive tests passed; "
                             f"structural score capped at {cap}/10")
                score = cap
    elif not g.compile_result.success:
        notes.append("compile failed; behavioural sub-score not evaluated")
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _program_class(g: GradedSubmission) -> CheckResult:
    cls = g.class_for_role("Program")
    if cls is None:
        return CheckResult(earned=0, notes="no Program class (role unfilled)",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if cls.superclass in (None, "Object"):
        score += 2
    else:
        notes.append(f"Program should NOT extend Statement "
                     f"(currently extends {cls.superclass!r})")
    # Should hold procedure list + a main Statement. Use the resolved
    # ProcedureDeclaration class name so renamed classes (ProcedureDecl,
    # ProcDecl, ...) still get credit when referenced from Program.
    src = _role_source(g, "Program") or ""
    pd_cls = g.class_for_role("ProcedureDeclaration")
    pd_name = pd_cls.name if pd_cls is not None else "ProcedureDeclaration"
    if pd_name in src:
        score += 1
    else:
        notes.append(f"no {pd_name} field")
    if "Statement" in src:
        score += 1
    else:
        notes.append("no Statement main field")
    severity = 0 if score >= 4 else (SEVERITY_MINOR if score >= 2
                                     else SEVERITY_MEDIUM)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _parse_program_and_procedure(g: GradedSubmission) -> CheckResult:
    parse_prog = g.method_for_role("Parser", "parseProgram")
    parse_proc = g.method_for_role("Parser", "parseProcedureDeclaration")
    score = 0.0
    notes: List[str] = []

    # Text-level fallback. If javalang choked on Parser.java, the AST
    # lookups above return None even when the methods are visibly in
    # the file. Confirm presence with a source grep so we don't mark
    # "parseProgram missing" on a file that literally has it -- that
    # was the bug teachers kept hitting with students who forgot the
    # semicolon after `package parser`.
    src = _role_source(g, "Parser") or ""
    unparseable = _role_unparseable_note(g, "Parser")

    prog_aliases = g.config.method_aliases.get(
        ("Parser", "parseProgram"), ("parseProgram",))
    proc_aliases = g.config.method_aliases.get(
        ("Parser", "parseProcedureDeclaration"),
        ("parseProcedureDeclaration",))
    prog_by_grep = any(f"{a}(" in src or f"{a} (" in src for a in prog_aliases)
    proc_by_grep = any(f"{a}(" in src or f"{a} (" in src for a in proc_aliases)

    if parse_prog is not None:
        score += 5
    elif prog_by_grep:
        score += 5
        notes.append("parseProgram found via text match "
                     "(AST view unavailable)")
    else:
        notes.append("parseProgram missing")

    if parse_proc is not None:
        score += 3
    elif proc_by_grep:
        score += 3
        notes.append("parseProcedureDeclaration found via text match "
                     "(AST view unavailable)")
    else:
        notes.append("parseProcedure(Declaration) missing")

    # If tests passed at least the simple/args ones, give the final 2.
    # When compile failed we can't tell whether the methods actually work
    # or not -- don't penalise this sub-score for what's really a build
    # problem. Rubric row 14 (compile/test) already captures it.
    passed_names = {t.case.name for t in g.test_outcomes if t.passed}
    if {"test01_simple", "test02_args"} & passed_names:
        score += 2
    elif not g.compile_result.success:
        notes.append("simple/args tests not verified (compile failed)")
    elif (parse_prog or prog_by_grep) and (parse_proc or proc_by_grep):
        notes.append("method present but simple tests failed")

    if unparseable:
        notes.insert(0, unparseable)
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _env_hierarchy(g: GradedSubmission) -> CheckResult:
    cls = g.class_for_role("Environment")
    if cls is None:
        return CheckResult(earned=0, notes="Environment role missing",
                           severity=SEVERITY_MAJOR)
    src = _role_source(g, "Environment") or ""
    score = 0.0
    notes: List[str] = []
    # We look for the literal word "Environment" in the source even when the
    # class is renamed: an Environment-like class almost always still imports
    # or references the canonical superclass/parent type name somewhere.
    if "parent" in src and ("Environment" in src or cls.name in src):
        score += 3
    else:
        notes.append("no parent Environment reference")
    # Constructors: java constructor name == class name, so we count
    # constructors by comparing against the resolved class name, not the
    # role name.
    has_two_ctors = sum(1 for m in cls.methods
                        if m.method_name == cls.name) >= 2
    if has_two_ctors:
        score += 3
    else:
        notes.append("only one Environment constructor; need (no-arg) and "
                     "(Environment parent) or a chained init that sets parent")
    severity = 0 if score >= 6 else (SEVERITY_MINOR if score >= 3
                                     else SEVERITY_MEDIUM)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _env_declare_set_get(g: GradedSubmission) -> CheckResult:
    required = ["declareVariable", "setVariable", "getVariable"]
    present = [m for m in required
               if g.method_for_role("Environment", m) is not None]
    score = round(4 * len(present) / len(required), 1)
    missing = [m for m in required if m not in present]
    severity = 0 if not missing else (SEVERITY_MINOR if len(missing) == 1
                                      else SEVERITY_MEDIUM)
    return CheckResult(earned=score,
                       notes=("missing: " + ", ".join(missing))
                       if missing else "",
                       severity=severity)


def _parser_procedure_and_factor(g: GradedSubmission) -> CheckResult:
    # _role_source already falls back to reading the raw file when
    # javalang couldn't parse it, so text-level greps still work even
    # when the Parser class is invisible to the AST pass. If the fallback
    # fired, prepend an explanatory note so the teacher understands the
    # structural signals below are best-effort.
    src = _role_source(g, "Parser") or ""
    score = 0.0
    notes: List[str] = []
    unparseable = _role_unparseable_note(g, "Parser")
    if '"PROCEDURE"' in src:
        score += 4
    else:
        notes.append('parser does not mention the "PROCEDURE" keyword')
    # parseFactor should handle id(args) as a procedure call. Use the
    # resolved ProcedureCall role name so renamed classes (ProcCall,
    # ProcedureInvocation, ...) still get the grep credit.
    pc_cls = g.class_for_role("ProcedureCall")
    pc_name = pc_cls.name if pc_cls is not None else "ProcedureCall"
    if pc_name in src and "parseFactor" in src:
        score += 4
    elif pc_name in src:
        score += 2
        notes.append(f"parseFactor does not appear to construct {pc_name}")
    else:
        notes.append(f"parseFactor does not construct a {pc_name}")
    passed_names = {t.case.name for t in g.test_outcomes if t.passed}
    if "test04_return" in passed_names or "test05_recursion" in passed_names:
        score += 2
    elif pc_name in src:
        notes.append("procedure-call-heavy tests (return/recursion) failed")
    if unparseable:
        notes.insert(0, unparseable)
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _testing_parsertest_7_and_8(g: GradedSubmission) -> CheckResult:
    """Rubric item: 'Works well on parserTest7 and parserTest8'.

    These files are part of the LAB INSTRUCTIONS -- the teacher gives
    students parserTest7.txt and parserTest8.txt to validate their work.
    They are NOT the autograder's hidden test suite. A student who
    didn't bring those files into their zip loses this rubric point
    entirely, which is the peer-review rule.

    Scoring (5 pts per file, total 10):
      * 2 pts: file is present somewhere in the Compiler/ tree
      * 3 pts: file runs through the student's parser without a
               runtime error, crash, or timeout

    We can't judge output correctness (the expected output isn't in the
    repo), so this is only a "does it at least execute" check. A human
    still has to skim the actual output if the teacher wants more.
    """
    if not g.compile_result.success:
        return CheckResult(
            earned=0,
            notes="compile failure blocks the parserTest7/8 run",
            severity=SEVERITY_MAJOR,
        )

    compiler_root = g.submission.compiler_root
    expected_files = ("parserTest7.txt", "parserTest8.txt")
    score = 0.0
    notes: List[str] = []
    for fname in expected_files:
        matches = list(compiler_root.rglob(fname))
        if not matches:
            notes.append(f"{fname} not found in the submission")
            continue
        score += 2.0  # presence credit
        test_path = matches[0]
        try:
            run = java_runner.run_parser(
                compiler_root=compiler_root,
                classes_dir=g.compile_result.classes_dir,
                test_file=test_path,
                java_exe=g.config.java_exe,
                timeout=30,
                stdin_text=None,
                main_class=g.config.main_class,
            )
        except Exception as exc:   # defensive; must not kill the rubric
            notes.append(f"{fname} runner raised: {exc}")
            continue
        if run.timed_out:
            notes.append(f"{fname} timed out (infinite loop?)")
            continue
        if run.error:
            notes.append(f"{fname} run error: {run.error}")
            continue
        # A non-empty stderr is a soft failure -- execution completed but
        # the student's code printed errors. Half credit for that arm.
        if run.stderr.strip():
            score += 1.0
            notes.append(f"{fname} ran but wrote to stderr")
            continue
        score += 3.0
    score = round(score, 1)
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _role_source(g: GradedSubmission, class_role: str) -> str | None:
    """Read the source file that defines the class fulfilling class_role.

    Delegates to GradedSubmission.source_for_role, which first tries the
    AST-resolved class's file path and then falls back to any file in
    g.unparsed_files whose basename matches the role. This fallback is
    what keeps text-level grep checks honest when a student's file has
    a syntax error that blocks javalang but the method bodies we are
    scanning for are still right there in the source.
    """
    return g.source_for_role(class_role)


def _role_unparseable_note(g: GradedSubmission, class_role: str) -> str:
    """If the role's file is in g.unparsed_files, build a note fragment
    that explains "this file didn't parse" rather than let the grader
    pretend the class simply doesn't exist.
    """
    fail = g.failure_for_role(class_role)
    if fail is None:
        return ""
    where = f" near line {fail.line}" if fail.line else ""
    return (f"{fail.file} could not be parsed{where}: {fail.reason} "
            f"-- AST-level checks for this role were skipped")


# --------------------------------------------------------------------------- #
# The rubric itself (exact order + text from the peer review PDF).
# --------------------------------------------------------------------------- #

RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="ast-classes",
        description="Two new AST classes for ProcedureDeclaration and "
                    "ProcedureCall.",
        points=10,
        checker=_has_both_ast_classes,
        category="AST classes",
    ),
    RubricItem(
        code="procdecl-class-doc",
        description="ProcedureDeclaration: class javadoc includes name, "
                    "date and summary using JavaDoc Standards.",
        points=4,
        checker=lambda g: _class_header_tags(g, "ProcedureDeclaration", 4),
        category="Documentation",
    ),
    RubricItem(
        code="procdecl-method-doc",
        description="ProcedureDeclaration: all methods have Javadoc headers "
                    "(@param, @return, pre/post, description).",
        points=6,
        checker=lambda g: _class_methods_tags(g, "ProcedureDeclaration", 6),
        category="Documentation",
    ),
    RubricItem(
        code="procdecl-extends-exec",
        description="ProcedureDeclaration extends Statement and has exec() "
                    "that adds a procedure symbol table entry.",
        points=10,
        checker=_procdecl_extends_and_exec,
        category="AST classes",
    ),
    RubricItem(
        code="procdecl-params-body",
        description="ProcedureDeclaration parses a list of Variables as "
                    "parameters and a block of statements.",
        points=6,
        checker=_procdecl_params_and_body,
        category="AST classes",
    ),
    RubricItem(
        code="proccall-class-doc",
        description="ProcedureCall: class javadoc includes name, date and "
                    "summary using JavaDoc Standards.",
        points=4,
        checker=lambda g: _class_header_tags(g, "ProcedureCall", 4),
        category="Documentation",
    ),
    RubricItem(
        code="proccall-method-doc",
        description="ProcedureCall: all methods have Javadoc headers "
                    "(@param, @return, pre/post, description).",
        points=6,
        checker=lambda g: _class_methods_tags(g, "ProcedureCall", 6),
        category="Documentation",
    ),
    RubricItem(
        code="proccall-extends-eval",
        description="ProcedureCall extends Expression and has eval() that "
                    "evaluates args, substitutes them, spawns a child "
                    "environment off the global one, and runs the body.",
        points=10,
        checker=_proccall_extends_and_eval,
        category="AST classes",
    ),
    RubricItem(
        code="program-class",
        description="A new Program class is introduced into the AST package. "
                    "Program does NOT extend Statement.",
        points=4,
        checker=_program_class,
        category="AST classes",
    ),
    RubricItem(
        code="parse-program-procedure",
        description="parseProgram and parseProcedure(Declaration) are written "
                    "and work well.",
        points=10,
        checker=_parse_program_and_procedure,
        category="Parser",
    ),
    RubricItem(
        code="env-hierarchy",
        description="Environment has appropriate method and instance "
                    "variables to store the hierarchy of parent and child "
                    "environments.",
        points=6,
        checker=_env_hierarchy,
        category="Environment",
    ),
    RubricItem(
        code="env-declare-set-get",
        description="Environment has declareVariable, setVariable, and "
                    "getVariable methods that work well and handle scope "
                    "correctly.",
        points=4,
        checker=_env_declare_set_get,
        category="Environment",
    ),
    RubricItem(
        code="parser-procedure-factor",
        description="Parser handles PROCEDURE declarations and parseFactor "
                    "handles procedure calls.",
        points=10,
        checker=_parser_procedure_and_factor,
        category="Parser",
    ),
    RubricItem(
        code="testing",
        description="Testing: works well on parserTest7 and parserTest8 "
                    "(lab-provided test files; student must include them "
                    "in their submission).",
        points=10,
        checker=_testing_parsertest_7_and_8,
        category="Testing",
    ),
)


# --------------------------------------------------------------------------- #
# Hidden test cases
# --------------------------------------------------------------------------- #

def _build_tests() -> List[TestCase]:
    """Load tests/*.pas and tests/expected.json into TestCase records."""
    expected_map = json.loads((TESTS_DIR / "expected.json")
                              .read_text(encoding="utf-8"))
    tests: List[TestCase] = []
    for name, meta in expected_map.items():
        tests.append(TestCase(
            name=name,
            description=meta["description"],
            source_path=TESTS_DIR / f"{name}.pas",
            expected_stdout=list(meta["expected"]),
        ))
    return tests


# --------------------------------------------------------------------------- #
# LabConfig entry point
# --------------------------------------------------------------------------- #

def build_config(java_exe: str = "java",
                 javac_exe: str = "javac") -> LabConfig:
    """Assemble the LabConfig that the orchestrator needs."""
    return LabConfig(
        lab_name="Procedures Lab",
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
    )
