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

from agcore.grader import GradedSubmission, LabConfig, TestCase
from agcore.javadoc_parser import ClassRecord, MethodRecord
from agcore.proximity import ProximityFinding, check_class, check_method
from agcore.rubric import (CheckResult, RubricItem, SEVERITY_MAJOR,
                           SEVERITY_MEDIUM, SEVERITY_MINOR)


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
    """Apply the keyword packs above to the parsed submission."""
    findings: List[ProximityFinding] = []
    for cls_name, (kws, threshold) in CLASS_KEYWORDS.items():
        cls = graded.class_by_name(cls_name)
        if cls is None:
            # Missing class gets surfaced by rubric checks; skip silently here
            # so the report doesn't double-count.
            continue
        findings.append(check_class(cls, kws, threshold))

    for (cls_name, m_name), (kws, threshold) in METHOD_KEYWORDS.items():
        method = graded.method(cls_name, m_name)
        if method is None:
            continue
        findings.append(check_method(
            method, kws, threshold,
            min_description_words=MIN_METHOD_DESCRIPTION_WORDS,
        ))

    # Audit every other method: must have a javadoc, the right @param/@return
    # tags, and a non-trivial description. We deliberately do NOT require
    # @precondition/@postcondition here -- students often document pre/post
    # in prose or skip them for trivial getters, and mechanical enforcement
    # produces too many false-positive REVIEWs for a teacher to skim.
    audited = {(cls_n, m_n) for (cls_n, m_n) in METHOD_KEYWORDS}
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
# Rubric checkers -- one per row on the peer review PDF
# --------------------------------------------------------------------------- #

def _has_both_ast_classes(g: GradedSubmission) -> CheckResult:
    have_decl = g.class_by_name("ProcedureDeclaration") is not None
    have_call = g.class_by_name("ProcedureCall") is not None
    if have_decl and have_call:
        return CheckResult(earned=10, notes="", severity=0)
    missing = []
    if not have_decl:
        missing.append("ProcedureDeclaration")
    if not have_call:
        missing.append("ProcedureCall")
    return CheckResult(earned=0,
                       notes=f"missing AST class: {', '.join(missing)}",
                       severity=SEVERITY_MAJOR)


def _class_header_tags(g: GradedSubmission,
                       class_name: str, points: float) -> CheckResult:
    """Check class-level javadoc includes @author + @version + a summary."""
    cls = g.class_by_name(class_name)
    if cls is None:
        return CheckResult(earned=0, notes=f"{class_name} not found",
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


def _class_methods_tags(g: GradedSubmission, class_name: str,
                        points: float) -> CheckResult:
    """Check every method in the named class has a javadoc with @param (for
    each parameter) and @return (if non-void).
    """
    cls = g.class_by_name(class_name)
    if cls is None:
        return CheckResult(earned=0, notes=f"{class_name} not found",
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
        if m.return_type not in ("void", "") and m.method_name != class_name:
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
    cls = g.class_by_name("ProcedureDeclaration")
    if cls is None:
        return CheckResult(earned=0, notes="class missing",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if cls.superclass == "Statement":
        score += 5
    else:
        notes.append(f"does not extend Statement (extends {cls.superclass!r})")
    exec_method = g.method("ProcedureDeclaration", "exec")
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
    cls = g.class_by_name("ProcedureDeclaration")
    if cls is None:
        return CheckResult(earned=0, notes="class missing",
                           severity=SEVERITY_MAJOR)
    # Look for a constructor taking (String name, List<String> params, Statement body)
    score = 0.0
    notes: List[str] = []
    ctor = next((m for m in cls.methods
                 if m.method_name == "ProcedureDeclaration"), None)
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
    src = _class_source(g, "ProcedureDeclaration")
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
    cls = g.class_by_name("ProcedureCall")
    if cls is None:
        return CheckResult(earned=0, notes="class missing",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if cls.superclass == "Expression":
        score += 3
    else:
        notes.append(f"does not extend Expression (extends {cls.superclass!r})")
    eval_m = g.method("ProcedureCall", "eval")
    if eval_m is None:
        notes.append("no eval method")
    else:
        score += 2
        src = _class_source(g, "ProcedureCall") or ""
        # Check the key behaviours mentioned in the rubric.
        if "getProcedure" in src:
            score += 1
        else:
            notes.append("eval does not call getProcedure on the env")
        if "globalScope" in src or "getGlobal" in src or "new Environment" in src:
            score += 2
        else:
            notes.append("no child environment created off the global one")
        if "declareVariable" in src or "setVariable" in src:
            score += 1
        else:
            notes.append("parameters never bound via declare/setVariable")
        if ".exec(" in src or ".eval(" in src:
            score += 1
        else:
            notes.append("body is never exec'd / args never eval'd")
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _program_class(g: GradedSubmission) -> CheckResult:
    cls = g.class_by_name("Program")
    if cls is None:
        return CheckResult(earned=0, notes="no Program class",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if cls.superclass in (None, "Object"):
        score += 2
    else:
        notes.append(f"Program should NOT extend Statement "
                     f"(currently extends {cls.superclass!r})")
    # Should hold procedure list + a main Statement.
    src = _class_source(g, "Program") or ""
    if "ProcedureDeclaration" in src:
        score += 1
    else:
        notes.append("no ProcedureDeclaration field")
    if "Statement" in src:
        score += 1
    else:
        notes.append("no Statement main field")
    severity = 0 if score >= 4 else (SEVERITY_MINOR if score >= 2
                                     else SEVERITY_MEDIUM)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _parse_program_and_procedure(g: GradedSubmission) -> CheckResult:
    parse_prog = g.method("Parser", "parseProgram")
    parse_proc = (g.method("Parser", "parseProcedure")
                  or g.method("Parser", "parseProcedureDeclaration"))
    score = 0.0
    notes: List[str] = []
    if parse_prog is None:
        notes.append("parseProgram missing")
    else:
        score += 5
    if parse_proc is None:
        notes.append("parseProcedure(Declaration) missing")
    else:
        score += 3
    # If tests passed at least the simple/args ones, give the final 2.
    passed_names = {t.case.name for t in g.test_outcomes if t.passed}
    if {"test01_simple", "test02_args"} & passed_names:
        score += 2
    elif parse_prog and parse_proc:
        notes.append("method present but simple tests failed")
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _env_hierarchy(g: GradedSubmission) -> CheckResult:
    cls = g.class_by_name("Environment")
    if cls is None:
        return CheckResult(earned=0, notes="Environment class missing",
                           severity=SEVERITY_MAJOR)
    src = _class_source(g, "Environment") or ""
    score = 0.0
    notes: List[str] = []
    if "parent" in src and "Environment" in src:
        score += 3
    else:
        notes.append("no parent Environment reference")
    has_two_ctors = sum(1 for m in cls.methods
                        if m.method_name == "Environment") >= 2
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
               if g.method("Environment", m) is not None]
    score = round(4 * len(present) / len(required), 1)
    missing = [m for m in required if m not in present]
    severity = 0 if not missing else (SEVERITY_MINOR if len(missing) == 1
                                      else SEVERITY_MEDIUM)
    return CheckResult(earned=score,
                       notes=("missing: " + ", ".join(missing))
                       if missing else "",
                       severity=severity)


def _parser_procedure_and_factor(g: GradedSubmission) -> CheckResult:
    src = _class_source(g, "Parser") or ""
    score = 0.0
    notes: List[str] = []
    if '"PROCEDURE"' in src:
        score += 4
    else:
        notes.append('parser does not mention the "PROCEDURE" keyword')
    # parseFactor should handle id(args) as a procedure call.
    if "ProcedureCall" in src and "parseFactor" in src:
        score += 4
    elif "ProcedureCall" in src:
        score += 2
        notes.append("parseFactor does not appear to construct ProcedureCall")
    else:
        notes.append("parseFactor does not construct a ProcedureCall")
    passed_names = {t.case.name for t in g.test_outcomes if t.passed}
    if "test04_return" in passed_names or "test05_recursion" in passed_names:
        score += 2
    elif "ProcedureCall" in src:
        notes.append("procedure-call-heavy tests (return/recursion) failed")
    severity = 0 if score >= 10 else (SEVERITY_MEDIUM if score >= 5
                                      else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _testing_proc_tests(g: GradedSubmission) -> CheckResult:
    """Rubric item: 'Works well on parserTest7 and parserTest8' -- we map this
    onto our hidden test suite plus compile success."""
    total = len(g.test_outcomes) or 1
    passed = sum(1 for t in g.test_outcomes if t.passed)
    earned = round(10 * passed / total, 1)
    notes = (f"{passed}/{total} internal tests passed")
    if not g.compile_result.success:
        return CheckResult(earned=0, notes="compile failure blocks all tests",
                           severity=SEVERITY_MAJOR)
    severity = 0 if passed == total else (SEVERITY_MINOR
                                          if passed >= total - 1
                                          else SEVERITY_MEDIUM
                                          if passed >= total // 2
                                          else SEVERITY_MAJOR)
    return CheckResult(earned=earned, notes=notes, severity=severity)


def _class_source(g: GradedSubmission, class_name: str) -> str | None:
    """Helper: read the source file that defines a given class."""
    cls = g.class_by_name(class_name)
    if cls is None:
        return None
    path = g.submission.compiler_root / cls.file
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


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
                    "(mapped to the hidden Procedures suite).",
        points=10,
        checker=_testing_proc_tests,
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
    )
