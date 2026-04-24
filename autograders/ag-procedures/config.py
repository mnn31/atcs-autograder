"""
Procedures Lab specific configuration. Every check, keyword set, and hidden
test case that the Procedures Lab rubric requires is wired up here and handed
to the generic agcore.grader.

The rubric text below is taken verbatim from the ATCS-Compilers Procedures
Peer Review sheet so the teacher can compare row-for-row.

AIRTIGHTNESS NOTE
-----------------
Every rubric checker that depends on AST-resolved classes or methods has a
text-level fallback for the case where a student's file has a syntax error
and javalang can't build an AST for it. Without that fallback, a single
missing semicolon silently converts every rubric row that touches that
file into "role unfilled / method missing" -- the exact bug teachers kept
hitting on real submissions. Helpers:

    * _role_source(g, role)        -> str | None   (raw source, with
                                                     unparsed-file fallback)
    * _role_unparseable_note(g, role) -> str       (teacher-visible note if
                                                     the file didn't parse)
    * _grep_extends(src, sup)      -> bool
    * _grep_method(src, aliases)   -> bool

Each checker consults these before deciding "genuinely missing vs. file
broken", so a student never loses credit for something their code
actually contains.
"""

from __future__ import annotations

import json
import re
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
    """Rubric row 1: both ProcedureDeclaration and ProcedureCall exist.

    Credit is awarded per-role: 5 pts for PD, 5 pts for PC. This keeps
    the rubric fair when a student has one class and not the other --
    previously a missing PC zeroed out credit for an otherwise-present
    PD, which violates the "independent parts stay independent"
    principle.

    Parse-failure fallback: if a role is missing AST-wise but there's
    an unparseable file whose basename matches the role, award 3 pts
    (of the 5) -- the class is almost certainly present, we just
    can't see it. Teacher-visible note explains exactly which file
    failed so they can spot-check.
    """
    roles = (("ProcedureDeclaration", 5.0), ("ProcedureCall", 5.0))
    score = 0.0
    notes: List[str] = []
    missing = []
    for role, points in roles:
        cls = g.class_for_role(role)
        if cls is not None:
            score += points
            continue
        missing.append(role)
        fail = g.failure_for_role(role)
        if fail is not None:
            where = f" near line {fail.line}" if fail.line else ""
            score += points * 0.6  # 3 of 5
            notes.append(
                f"{role}: {fail.file} failed to parse{where}: "
                f"{fail.reason} -- structural checks skipped "
                f"(partial credit awarded)")
        else:
            notes.append(f"{role}: no class matched this role")
    earned = round(score, 1)
    if earned >= 10:
        severity = 0
    elif earned >= 5:
        severity = SEVERITY_MEDIUM
    else:
        severity = SEVERITY_MAJOR
    return CheckResult(earned=earned, notes="; ".join(notes),
                       severity=severity)


def _class_header_tags(g: GradedSubmission,
                       class_role: str, points: float) -> CheckResult:
    """Check class-level javadoc includes @author + @version + a summary.

    class_role is a rubric role name ("ProcedureCall") not a literal class
    name -- g.class_for_role handles student renames.

    Unparseable-file fallback: if the class's file has a syntax error
    that blocked javalang, we text-scan the raw source for the class
    header javadoc and its @author/@version tags rather than report a
    spurious "not found". That way a student who wrote the javadoc but
    also has a missing semicolon still gets credit for the javadoc.
    """
    cls = g.class_for_role(class_role)
    unparseable = _role_unparseable_note(g, class_role)
    src = _role_source(g, class_role) or ""
    per = points / 3.0

    if cls is None and not src:
        return CheckResult(
            earned=0,
            notes=f"{class_role} not found (no class matched the expected role)",
            severity=SEVERITY_MAJOR,
        )

    if cls is not None and cls.javadoc is not None:
        has_author = bool(cls.javadoc.tags_named("@author"))
        has_version = bool(cls.javadoc.tags_named("@version"))
        has_summary = bool(cls.javadoc.description.strip())
    elif cls is not None and cls.javadoc is None:
        has_summary, has_author, has_version = False, False, False
    else:
        # AST view unavailable: fall back to text grep.
        has_summary, has_author, has_version = _grep_class_javadoc(src)

    score = 0.0
    notes: List[str] = []
    if unparseable:
        notes.append(unparseable)
        notes.append("javadoc scanned via text match (AST view unavailable)")
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

    Unparseable-file fallback: without an AST we can't enumerate methods,
    but we can count /** */ blocks and compare against the number of
    method-signature-looking lines. If the ratio is reasonable, award
    partial credit with a clear note so the teacher knows it wasn't
    verified structurally.
    """
    cls = g.class_for_role(class_role)
    unparseable = _role_unparseable_note(g, class_role)
    src = _role_source(g, class_role) or ""

    if cls is None and not src:
        return CheckResult(
            earned=0,
            notes=f"{class_role} not found (no class matched the expected role)",
            severity=SEVERITY_MAJOR,
        )

    if cls is None:
        # File unparseable. Approximate: count /** ... */ blocks and
        # method-signature lines; award proportional credit.
        blocks = len(re.findall(r"/\*\*.*?\*/", src, re.DOTALL))
        # Rough method-signature pattern: `public|private|protected ... name(...)`
        # or a constructor `ClassName(...)` before a `{`. Count lines that look
        # like method decls (have parens followed by a { on the same or next
        # non-blank line).
        # Non-f-string raw regex: use single { here. (Sibling grep helpers
        # that *are* f-strings escape it as {{ on purpose.)
        method_like = len(re.findall(
            r"(?m)^\s*(?:public|private|protected|static|\s)*[\w<>\[\],\s]+\s"
            r"+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\{", src))
        if method_like == 0:
            return CheckResult(
                earned=points, notes=(unparseable + "; no methods visible")
                if unparseable else "no methods",
                severity=0,
            )
        fraction = min(1.0, blocks / max(method_like, 1))
        earned = round(points * fraction, 1)
        note = (f"{unparseable}; text-match heuristic: {blocks} javadoc "
                f"blocks for ~{method_like} methods (scored {earned}/{points})")
        severity = 0 if earned >= points else (SEVERITY_MINOR if fraction >= 0.66
                                               else SEVERITY_MEDIUM)
        return CheckResult(earned=earned, notes=note, severity=severity)

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
    """Rubric row 4: ProcedureDeclaration extends Statement + has exec()
    that registers the procedure with the environment.

    Independent of every other row -- only looks at ProcedureDeclaration.
    Has a text-level fallback so a student whose ProcedureDeclaration.java
    has a syntax error still gets credit for the visible extends clause
    and exec method declaration.
    """
    cls = g.class_for_role("ProcedureDeclaration")
    unparseable = _role_unparseable_note(g, "ProcedureDeclaration")
    src = _role_source(g, "ProcedureDeclaration") or ""
    score = 0.0
    notes: List[str] = []

    if cls is None and not src:
        return CheckResult(earned=0, notes="ProcedureDeclaration role missing",
                           severity=SEVERITY_MAJOR)
    if unparseable:
        notes.append(unparseable)

    # -- Extends Statement
    if cls is not None:
        if cls.superclass == "Statement":
            score += 5
        else:
            notes.append(
                f"does not extend Statement (extends {cls.superclass!r})")
    else:
        if _grep_extends(src, "Statement"):
            score += 5
            notes.append("extends Statement found via text match")
        else:
            notes.append("does not appear to extend Statement")

    # -- exec method
    exec_method = (g.method_for_role("ProcedureDeclaration", "exec")
                   if cls is not None else None)
    if exec_method is not None:
        score += 3
        doc_text = (exec_method.javadoc.plain_text()
                    if exec_method.javadoc else "")
        if any(k in doc_text for k in
               ("register", "procedure", "symbol", "setprocedure")):
            score += 2
        else:
            notes.append("exec javadoc does not mention registering the "
                         "procedure/symbol-table")
    else:
        exec_aliases = g.config.method_aliases.get(
            ("ProcedureDeclaration", "exec"), ("exec",))
        if _grep_method(src, exec_aliases):
            score += 3
            notes.append("exec found via text match; javadoc not verified "
                         "(file unparseable)")
        else:
            notes.append("no exec method")

    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _procdecl_params_and_body(g: GradedSubmission) -> CheckResult:
    """Rubric row 5: constructor takes (name, params, body) + stores them.

    Independent of the exec-method row above. Uses AST for the constructor
    when available, falls back to text grep for unparseable files.
    """
    cls = g.class_for_role("ProcedureDeclaration")
    src = _role_source(g, "ProcedureDeclaration") or ""
    unparseable = _role_unparseable_note(g, "ProcedureDeclaration")
    score = 0.0
    notes: List[str] = []
    if cls is None and not src:
        return CheckResult(earned=0, notes="ProcedureDeclaration role missing",
                           severity=SEVERITY_MAJOR)
    if unparseable:
        notes.append(unparseable)

    # -- Constructor with >=2 params
    if cls is not None:
        ctor = next((m for m in cls.methods
                     if m.method_name == cls.name), None)
        if ctor is None:
            notes.append("no constructor found")
        elif len(ctor.params) >= 2:
            score += 3
        else:
            notes.append(f"constructor has {len(ctor.params)} params "
                         f"(expected >= 2)")
    else:
        if _grep_ctor(src, 2):
            score += 3
            notes.append("constructor (>=2 params) found via text match")
        else:
            notes.append("no constructor with >=2 params visible")

    # -- Parameter list field + Statement body (text-grep; works either way)
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
    src = _role_source(g, "ProcedureCall") or ""
    unparseable = _role_unparseable_note(g, "ProcedureCall")
    if cls is None and not src:
        return CheckResult(earned=0, notes="ProcedureCall role missing",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if unparseable:
        notes.append(unparseable)
    # -- Structural sub-score, up to 6 pts. Spread the credit so no single
    # keyword can clear more than 2 pts by itself.
    if cls is not None:
        if cls.superclass == "Expression":
            score += 2
        else:
            notes.append(
                f"does not extend Expression (extends {cls.superclass!r})")
    else:
        if _grep_extends(src, "Expression"):
            score += 2
            notes.append("extends Expression found via text match")
        else:
            notes.append("does not appear to extend Expression")
    eval_m = (g.method_for_role("ProcedureCall", "eval")
              if cls is not None else None)
    eval_aliases = g.config.method_aliases.get(
        ("ProcedureCall", "eval"), ("eval",))
    has_eval = eval_m is not None or (cls is None and _grep_method(src, eval_aliases))
    if not has_eval:
        notes.append("no eval method")
    else:
        score += 1
        if cls is None:
            notes.append("eval found via text match (AST view unavailable)")
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
    src = _role_source(g, "Program") or ""
    unparseable = _role_unparseable_note(g, "Program")
    if cls is None and not src:
        return CheckResult(earned=0, notes="no Program class (role unfilled)",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if unparseable:
        notes.append(unparseable)
    # -- Should NOT extend Statement
    if cls is not None:
        if cls.superclass in (None, "Object"):
            score += 2
        else:
            notes.append(f"Program should NOT extend Statement "
                         f"(currently extends {cls.superclass!r})")
    else:
        # Text-level: only lose the 2 pts if we can see `extends Statement`
        # on the Program class declaration; otherwise give benefit of the doubt.
        if re.search(r"class\s+\w+\s+extends\s+Statement\b", src):
            notes.append("Program appears to extend Statement (text match)")
        else:
            score += 2
    # -- Holds procedure list + a Statement main. Text-grep works either way.
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
    """Rubric row 11: Environment has parent-pointer + two constructors.

    Row 12 (declareVariable/setVariable/getVariable) is independent --
    even if the hierarchy check fails, a student can still get full
    credit for declare/set/get, and vice versa.
    """
    cls = g.class_for_role("Environment")
    src = _role_source(g, "Environment") or ""
    unparseable = _role_unparseable_note(g, "Environment")
    if cls is None and not src:
        return CheckResult(earned=0, notes="Environment role missing",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if unparseable:
        notes.append(unparseable)
    # We look for the literal word "Environment" in the source even when the
    # class is renamed: an Environment-like class almost always still imports
    # or references the canonical superclass/parent type name somewhere.
    cls_name = cls.name if cls is not None else "Environment"
    if "parent" in src and ("Environment" in src or cls_name in src):
        score += 3
    else:
        notes.append("no parent Environment reference")
    # -- Count constructors. AST is exact; text-grep fallback counts
    # `ClassName(...)` signatures (with a `{` following).
    if cls is not None:
        ctor_count = sum(1 for m in cls.methods if m.method_name == cls.name)
    else:
        # Find first class name in src and count its ctor signatures.
        m = re.search(r"\bclass\s+(\w+)\b", src)
        if m:
            cname = m.group(1)
            ctor_count = len(re.findall(
                rf"\b{re.escape(cname)}\s*\([^)]*\)\s*(?:throws[^{{]*)?\{{",
                src))
        else:
            ctor_count = 0
    if ctor_count >= 2:
        score += 3
    else:
        notes.append("only one Environment constructor; need (no-arg) and "
                     "(Environment parent) or a chained init that sets parent")
    severity = 0 if score >= 6 else (SEVERITY_MINOR if score >= 3
                                     else SEVERITY_MEDIUM)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _env_declare_set_get(g: GradedSubmission) -> CheckResult:
    """Rubric row 12: Environment has declareVariable/setVariable/getVariable.

    Fully independent of row 11 -- a student with a broken parent-ptr
    constructor still gets full credit here if the three methods are
    present, and vice versa. Unparseable-file fallback uses text grep.
    """
    required = ["declareVariable", "setVariable", "getVariable"]
    cls = g.class_for_role("Environment")
    src = _role_source(g, "Environment") or ""
    unparseable = _role_unparseable_note(g, "Environment")

    present: List[str] = []
    grep_only: List[str] = []
    for m in required:
        if cls is not None and g.method_for_role("Environment", m) is not None:
            present.append(m)
            continue
        # Text-level fallback: any alias visible in the source counts.
        aliases = g.config.method_aliases.get(
            ("Environment", m), (m,))
        if cls is None and _grep_method(src, aliases):
            present.append(m)
            grep_only.append(m)
    score = round(4 * len(present) / len(required), 1)
    missing = [m for m in required if m not in present]
    notes: List[str] = []
    if unparseable:
        notes.append(unparseable)
    if grep_only:
        notes.append("found via text match: " + ", ".join(grep_only))
    if missing:
        notes.append("missing: " + ", ".join(missing))
    severity = 0 if not missing else (SEVERITY_MINOR if len(missing) == 1
                                      else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
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
    elif not g.compile_result.success:
        # Don't accuse the student of failing behavioural tests when the
        # project didn't even build -- that's a compile-row issue. Credit
        # for the structural signals they DID show, flag as REVIEW.
        notes.append("procedure-call-heavy tests not verified "
                     "(compile failed)")
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
        # Use whichever main class the probe in _run_test_case has
        # already locked in; falling back to the first detected
        # candidate, then to the lab default. This mirrors the hidden
        # test runner so a student who keeps main in ParserTester
        # still gets the parserTest7/8 row evaluated correctly.
        main_class = (g.selected_main_class
                      or (g.main_class_candidates[0]
                          if g.main_class_candidates
                          else g.config.main_class))
        try:
            run = java_runner.run_parser(
                compiler_root=compiler_root,
                classes_dir=g.compile_result.classes_dir,
                test_file=test_path,
                java_exe=g.config.java_exe,
                timeout=30,
                stdin_text=None,
                main_class=main_class,
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


def _grep_extends(src: str, superclass: str) -> bool:
    """Text-level check: does src declare `class X extends superclass`?

    Used as a fallback when javalang couldn't parse the file so the AST
    check can't see the extends clause. Matches `class Foo extends Bar`
    with either a `{` or `implements` following -- an identifier after
    `extends` is enough.
    """
    if not src:
        return False
    pattern = re.compile(
        r"class\s+\w+\s+extends\s+" + re.escape(superclass) + r"\b")
    return bool(pattern.search(src))


def _grep_method(src: str, aliases: Sequence[str]) -> bool:
    """Text-level check: does src declare a method matching any alias?

    We look for `<alias>(` or `<alias> (` in the source -- Java allows
    either. This is a rough heuristic (won't distinguish a method
    declaration from a call site), but combined with the role's source
    file (not the call site) it's reliable enough to rescue an
    unparseable file's rubric row from a false "method missing".
    """
    if not src:
        return False
    return any(f"{a}(" in src or f"{a} (" in src for a in aliases)


def _grep_ctor(src: str, min_params: int) -> bool:
    """Text-level check: does src declare a constructor with >= min_params?

    Finds `class <Name>` then looks for `<Name>(` where the paren group
    contains at least (min_params - 1) commas. Approximate but catches
    the common case of a multi-arg constructor we can't see via AST.
    """
    if not src:
        return False
    m = re.search(r"class\s+(\w+)\b", src)
    if not m:
        return False
    cname = m.group(1)
    # (?: ) non-capturing. Match ctor with a body `{` following.
    ctor_pat = re.compile(
        rf"\b{re.escape(cname)}\s*\(([^)]*)\)\s*(?:throws[^{{]*)?\{{")
    for match in ctor_pat.finditer(src):
        args = match.group(1).strip()
        if not args and min_params == 0:
            return True
        # Count commas not inside angle brackets.
        depth = 0
        commas = 0
        for ch in args:
            if ch == "<":
                depth += 1
            elif ch == ">":
                depth -= 1
            elif ch == "," and depth == 0:
                commas += 1
        if commas + 1 >= min_params:
            return True
    return False


def _grep_class_javadoc(src: str) -> tuple:
    """Text-level extraction of the class-level javadoc.

    Returns (has_summary, has_author, has_version) as booleans. Picks
    the last /** ... */ block that appears before the first `class X`
    declaration in src -- that's conventionally the class header doc.
    If no block or no class decl is found, returns all False.
    """
    if not src:
        return (False, False, False)
    class_match = re.search(r"\bclass\s+\w+", src)
    cutoff = class_match.start() if class_match else len(src)
    blocks = []
    for m in re.finditer(r"/\*\*(.*?)\*/", src, re.DOTALL):
        if m.start() < cutoff:
            blocks.append(m.group(0))
    if not blocks:
        return (False, False, False)
    header = blocks[-1]
    has_author = "@author" in header
    has_version = "@version" in header
    # Description: content from "/**" up to the first @tag or closing */,
    # minus leading "*" chars on each line.
    inner = re.sub(r"^/\*\*|\*/$", "", header, flags=re.DOTALL)
    desc_part = inner.split("@", 1)[0]
    desc_clean = re.sub(r"(?m)^\s*\*\s?", "", desc_part).strip()
    has_summary = bool(desc_clean)
    return (has_summary, has_author, has_version)


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
