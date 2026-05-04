"""
CodeGen Lab specific configuration.

Mirrors the 12-row ATCS CodeGen Peer Review sheet (4+8+6+20+4+6+6+6+10+10+10+10
= 100 pts) one row at a time. Each rubric checker is independent: a
broken Emitter doesn't zero out the per-AST-class compile checks, and
a missing variable declaration doesn't blunt the testing row.

Pipeline shape
==============
The autograder generates a per-submission `parser/_AGCodeGenTester.java`
that imports the student's Parser + Program (under whatever names they
used) and exposes:

    main(args[0] = in.pas, args[1] = out.asm)

We compile that into the student's classes/ dir, then for each hidden
test:

    1. Run the synthetic tester to produce a .asm.
    2. Run the .asm through MARS 4.5; capture stdout.
    3. Compare stdout to the expected lines in tests/expected.json.

The TWO peer-review-required test programs (parserTest9.txt / max.txt)
ship as test08_combined.pas / test07_max.pas with the exact same
content. Any rubric row that says "works on parserTest9 / max" reads
those two tests' outcomes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Sequence

from agcore import codegen_runner
from agcore.grader import GradedSubmission, LabConfig, TestCase
from agcore.proximity import ProximityFinding, check_class, check_method
from agcore.role_resolver import RoleSpec
from agcore.rubric import (CheckResult, RubricItem, SEVERITY_MAJOR,
                           SEVERITY_MEDIUM, SEVERITY_MINOR)


# --------------------------------------------------------------------------- #
# Class + method roles (renamed-class tolerance)
# --------------------------------------------------------------------------- #

CLASS_ROLES = {
    "Emitter": RoleSpec(
        preferred_name="Emitter",
        aliases=("AsmEmitter", "MipsEmitter", "CodeEmitter", "CodeGenEmitter"),
        name_tokens=[("emitter",), ("asm", "writer"), ("mips", "writer")],
        required_methods=("emit",),
        # Lab spec says Emitter lives in its own package OR in the AST
        # package; we accept either via preferred_dir + a fallback.
        preferred_dir="emitter",
    ),
    "Program": RoleSpec(
        preferred_name="Program",
        aliases=("PascalProgram", "Programme", "Root"),
        name_tokens=[("program",)],
        required_methods=("compile", "exec", "execute"),
        preferred_dir="ast",
    ),
    "Parser": RoleSpec(
        preferred_name="Parser",
        aliases=("PascalParser",),
        name_tokens=[("parser",)],
        preferred_dir="parser",
    ),
    # Abstract base classes the rubric checks for compile() overrides.
    "Statement": RoleSpec(
        preferred_name="Statement",
        aliases=("Stmt",),
        name_tokens=[("statement",), ("stmt",)],
        preferred_dir="ast",
    ),
    "Expression": RoleSpec(
        preferred_name="Expression",
        aliases=("Expr",),
        name_tokens=[("expression",), ("expr",)],
        preferred_dir="ast",
    ),
}


METHOD_ALIASES = {
    ("Emitter", "emit"): ("emit",),
    ("Emitter", "nextLabelID"): (
        "nextLabelID", "nextLabel", "newLabel", "freshLabelID", "labelID"),
    ("Emitter", "emitPush"): ("emitPush", "push"),
    ("Emitter", "emitPop"): ("emitPop", "pop"),
    ("Program", "compile"): ("compile", "emit", "generate", "codegen"),
    ("Parser", "parseProgram"): ("parseProgram", "parseProg"),
    ("Statement", "compile"): ("compile",),
    ("Expression", "compile"): ("compile",),
}


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

AG_ROOT = Path(__file__).resolve().parent
REPO_ROOT = AG_ROOT.parents[1]   # autograder-work/
VENDOR = REPO_ROOT / "vendor"
TESTS_DIR = AG_ROOT / "tests"


# --------------------------------------------------------------------------- #
# Proximity rule
# --------------------------------------------------------------------------- #

CLASS_KEYWORDS = {
    "Emitter": (
        ["emitter", "file", "write", "output", "mips", "register", "label"],
        3),
    "Program": (
        ["program", "compile", "main", "statement", "data", "text"], 3),
    "Parser": (
        ["parser", "token", "statement", "expression"], 3),
}

METHOD_KEYWORDS = {
    ("Emitter", "emit"): (["emit", "line", "output", "tab", "label"], 2),
    ("Emitter", "nextLabelID"): (
        ["label", "id", "unique", "counter", "next"], 2),
    ("Emitter", "emitPush"): (
        ["push", "register", "stack", "$sp"], 2),
    ("Emitter", "emitPop"): (
        ["pop", "register", "stack", "$sp"], 2),
    ("Program", "compile"): (
        ["compile", "emit", "main", "data", "variable", "global"], 3),
    ("Parser", "parseProgram"): (
        ["parse", "program", "variable", "statement"], 3),
}


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
        findings.append(check_method(method, kws, threshold))
        audited.add((method.class_name, method.method_name))

    # Audit every other method for the @-tag basics. Don't double-audit
    # methods we already keyword-scored above, and don't bother with
    # constructors (they don't need @return).
    for cls in graded.classes:
        for m in cls.methods:
            if (cls.name, m.method_name) in audited:
                continue
            if m.method_name == cls.name:   # skip ctors
                continue
            findings.append(check_method(m, [], 0, require_return=True))
    return findings


# --------------------------------------------------------------------------- #
# Helpers used by multiple rubric rows
# --------------------------------------------------------------------------- #

def _read(path: Path | None) -> str:
    """Read a file's text or return empty on any error."""
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _emitter_file_text(g: GradedSubmission) -> str:
    cls = g.class_for_role("Emitter")
    if cls is None:
        return ""
    return _read(g.submission.compiler_root / cls.file)


def _first_emitted_asm(g: GradedSubmission) -> str:
    """Return the body of the FIRST .asm produced by any hidden test.

    Most rubric rows that look at "the output asm" need just one
    representative file -- they're checking shape (sections, header,
    inline comments) not behaviour. Picking the first lets a row score
    even if some tests crashed downstream of emit.
    """
    for outcome in g.test_outcomes:
        if outcome.artifact_path and outcome.artifact_path.exists():
            return _read(outcome.artifact_path)
    return ""


def _all_emitted_asm(g: GradedSubmission) -> str:
    """Concatenate every emitted .asm into one string.

    Used by checkers whose signal might be present in only some files
    (push/pop inline comments only show up in programs that use
    BinOps; var declarations only show up in programs with VAR). Any
    one match anywhere in the run is enough to credit the student.
    """
    parts: List[str] = []
    for outcome in g.test_outcomes:
        if outcome.artifact_path and outcome.artifact_path.exists():
            parts.append(_read(outcome.artifact_path))
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Rubric checkers (12 rows)
# --------------------------------------------------------------------------- #

def _emitter_packaging(g: GradedSubmission) -> CheckResult:
    """Row 1 (4 pts): Emitter in own package or ast package; rest of
    structure unchanged.

    We accept emitter/, ast/, or codegen/ as package locations -- some
    students keep the file directly under ast/ per the lab's "or" wording.
    """
    cls = g.class_for_role("Emitter")
    if cls is None:
        return CheckResult(earned=0, notes="no Emitter class found",
                           severity=SEVERITY_MAJOR)
    pkg = cls.file.rsplit("/", 1)[0] if "/" in cls.file else ""
    notes: List[str] = []
    score = 0.0
    if pkg in ("emitter", "ast", "codegen"):
        score += 3.0
    else:
        notes.append(f"Emitter is in package '{pkg}'; lab asks for "
                     f"'emitter' or 'ast'")
    # Other directories should still exist (parser/, scanner/, ast/,
    # environment/) -- if they're all there, give the last point.
    expected = {"parser", "scanner", "ast"}
    have = {p for p in (cls.file.rsplit("/", 1)[0] for cls in g.classes)
            if p}
    have_short = {p.split("/")[-1] for p in have}
    if expected.issubset(have_short):
        score += 1.0
    else:
        notes.append(f"missing expected dirs: "
                     f"{sorted(expected - have_short)}")
    severity = 0 if score >= 4 else SEVERITY_MINOR if score >= 2 else SEVERITY_MEDIUM
    return CheckResult(earned=round(score, 1), notes="; ".join(notes),
                       severity=severity)


def _all_methods_javadoc(g: GradedSubmission) -> CheckResult:
    """Row 2 (8 pts): every method has @param/@return/pre+post/desc.

    Method-level proximity finding targets are formatted "Class.method";
    class-level targets end with " (class)". Filter to method findings
    and grade the proportion that came back clean.
    """
    method_findings = [
        f for f in g.proximity
        if f.target and "(class)" not in f.target
    ]
    if not method_findings:
        return CheckResult(earned=4.0,
                           notes="no methods seen by proximity pass",
                           severity=SEVERITY_MEDIUM)
    issues = sum(1 for f in method_findings if f.missing or not f.passed)
    total = len(method_findings)
    fraction = max(0.0, 1.0 - issues / total)
    earned = round(8.0 * fraction, 1)
    severity = (0 if fraction >= 1.0 else SEVERITY_MINOR
                if fraction >= 0.66 else SEVERITY_MEDIUM)
    notes = (f"{total - issues}/{total} methods cleared the documentation "
             f"check")
    return CheckResult(earned=earned, notes=notes, severity=severity)


def _stmt_expr_have_compile(g: GradedSubmission) -> CheckResult:
    """Row 3 (6 pts): Statement and Expression both define compile()."""
    notes: List[str] = []
    score = 0.0
    for role in ("Statement", "Expression"):
        cls = g.class_for_role(role)
        if cls is None:
            notes.append(f"{role} role not resolved")
            continue
        if any(m.method_name == "compile" for m in cls.methods):
            score += 3.0
        else:
            notes.append(f"{role}.compile() missing")
    severity = 0 if score >= 6 else SEVERITY_MEDIUM if score >= 3 else SEVERITY_MAJOR
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


# AST classes Lab 6 explicitly walks through. Other AST classes may
# exist (BreakStmt, ContinueStmt, ProcedureCall/Declaration, RepeatUntil)
# from earlier or later labs; the rubric's "appropriately" wording is
# about what the lab covers, not literally every Statement/Expression
# subclass that happens to be in the tree.
_LAB_REQUIRED_COMPILE_TARGETS = (
    ("Number",      ("Number",)),
    ("Writeln",     ("Writeln",)),
    ("BinOp",       ("BinOp", "BinaryOp")),
    ("Block",       ("Block",)),
    ("Variable",    ("Variable", "Var")),
    ("Assignment",  ("Assignment", "Assign")),
    ("Condition",   ("Condition", "Cond")),
    ("If",          ("If", "IfStmt", "IfStatement")),
    ("While",       ("While", "WhileStmt", "WhileStatement")),
)


def _ast_compile_overrides(g: GradedSubmission) -> CheckResult:
    """Row 4 (20 pts): the lab-walked AST classes have compile().

    The peer review's "appropriately" qualifier means we only require
    compile() on the AST nodes Lab 6 actually walks (Number, Writeln,
    BinOp, Block, Variable, Assignment, Condition, If, While). Extra
    AST classes from other labs aren't penalised for missing compile,
    but their absence in the submission is also not a credit.
    """
    by_name = {c.name: c for c in g.classes}
    have = 0
    missing: List[str] = []
    for canonical, aliases in _LAB_REQUIRED_COMPILE_TARGETS:
        cls = next((by_name[a] for a in aliases if a in by_name), None)
        if cls is not None and any(m.method_name == "compile"
                                   for m in cls.methods):
            have += 1
        else:
            missing.append(canonical)
    total = len(_LAB_REQUIRED_COMPILE_TARGETS)
    per = 20.0 / total
    earned = round(per * have, 1)
    fraction = have / total
    severity = (0 if fraction >= 1.0 else
                SEVERITY_MINOR if fraction >= 0.8 else
                SEVERITY_MEDIUM if fraction >= 0.5 else SEVERITY_MAJOR)
    notes = (f"compile() present on {have}/{total} lab-required AST "
             f"classes")
    if missing:
        notes += "; missing on: " + ", ".join(missing)
    return CheckResult(earned=earned, notes=notes, severity=severity)


def _output_extension(g: GradedSubmission) -> CheckResult:
    """Row 5 (4 pts): output files have .s / .a / .asm extension."""
    artifacts = [t.artifact_path for t in g.test_outcomes if t.artifact_path]
    if not artifacts:
        return CheckResult(earned=0.0,
                           notes="no .asm artifacts produced; emit pipeline "
                                 "did not run",
                           severity=SEVERITY_MAJOR)
    ok = sum(1 for p in artifacts if p.suffix.lower() in (".s", ".a", ".asm"))
    fraction = ok / len(artifacts)
    earned = round(4.0 * fraction, 1)
    severity = (0 if fraction >= 1.0 else SEVERITY_MINOR
                if fraction >= 0.5 else SEVERITY_MEDIUM)
    notes = f"{ok}/{len(artifacts)} artifacts have a valid extension"
    return CheckResult(earned=earned, notes=notes, severity=severity)


def _output_well_formed(g: GradedSubmission) -> CheckResult:
    """Row 6 (6 pts): output has .data + .text + .globl main."""
    src = _first_emitted_asm(g)
    if not src:
        return CheckResult(earned=0.0,
                           notes="no .asm produced",
                           severity=SEVERITY_MAJOR)
    score = 0.0
    notes: List[str] = []
    if re.search(r"^\s*\.text\b", src, re.MULTILINE):
        score += 2.0
    else:
        notes.append("missing .text section")
    if re.search(r"^\s*\.data\b", src, re.MULTILINE):
        score += 2.0
    else:
        notes.append("missing .data section")
    if re.search(r"^\s*\.globl\s+main\b", src, re.MULTILINE):
        score += 2.0
    else:
        notes.append("missing .globl main")
    severity = 0 if score >= 6 else SEVERITY_MEDIUM if score >= 3 else SEVERITY_MAJOR
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _vars_in_data(g: GradedSubmission) -> CheckResult:
    """Row 7 (6 pts): variables declared and emitted to .data section.

    Use test04_variables (which declares two vars) as the canonical
    case: scan its emitted .asm for the var-naming convention varX
    inside .data.
    """
    target = next(
        (t for t in g.test_outcomes
         if t.case.name in ("test04_variables", "test07_max", "test08_combined")
         and t.artifact_path),
        None,
    )
    if target is None or not target.artifact_path:
        return CheckResult(earned=0.0,
                           notes="no variable-bearing .asm available",
                           severity=SEVERITY_MAJOR)
    src = _read(target.artifact_path)
    data_section = _data_section(src)
    score = 0.0
    notes: List[str] = []
    if data_section:
        score += 2.0
    else:
        notes.append("no .data section emitted")
    # The lab convention is varname-prefixed labels (varx, vary, ...);
    # accept either that or any "<id>:\s+\.word" style declaration.
    if re.search(r"^\s*var\w+\s*:", data_section, re.MULTILINE | re.IGNORECASE):
        score += 4.0
    elif re.search(r"^\s*\w+\s*:\s*\.word\b", data_section,
                   re.MULTILINE):
        score += 3.0
        notes.append("vars are declared but not under the 'var<name>' "
                     "convention recommended by the lab")
    else:
        notes.append("no variable labels in the .data section")
    severity = 0 if score >= 6 else SEVERITY_MEDIUM if score >= 3 else SEVERITY_MAJOR
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _output_javadoc_header(g: GradedSubmission) -> CheckResult:
    """Row 8 (6 pts): output asm has a Javadoc-style header with @author + date.

    The lab note says "no purpose/description is expected", so we only
    require @author and a date-shaped string.
    """
    src = _first_emitted_asm(g)
    if not src:
        return CheckResult(earned=0.0, notes="no .asm produced",
                           severity=SEVERITY_MAJOR)
    head = "\n".join(src.splitlines()[:30])
    score = 0.0
    notes: List[str] = []
    if "@author" in head:
        score += 3.0
    else:
        notes.append("no '@author' line in output header")
    if re.search(r"@(?:version|date)\b", head) or re.search(
            r"\b(20\d{2}|0\d/\d{2})\b", head):
        score += 3.0
    else:
        notes.append("no @version/@date or date-shaped string in output header")
    severity = 0 if score >= 6 else SEVERITY_MINOR if score >= 3 else SEVERITY_MEDIUM
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _inline_comments(g: GradedSubmission) -> CheckResult:
    """Row 9 (10 pts): output asm has inline comments like #push (register).

    Density is judged on the first emitted file (representative),
    but the push/pop style check scans EVERY emitted file -- only
    BinOp-containing programs use the stack, so a writeln-only test
    will never show #push regardless of how good the emitter is.
    """
    src = _first_emitted_asm(g)
    if not src:
        return CheckResult(earned=0.0, notes="no .asm produced",
                           severity=SEVERITY_MAJOR)
    inline_count = sum(1 for ln in src.splitlines()
                       if "#" in ln and not ln.lstrip().startswith("#"))
    instr_count = sum(1 for ln in src.splitlines()
                      if ln.strip()
                      and not ln.lstrip().startswith("#")
                      and not ln.strip().startswith(".")
                      and not ln.strip().endswith(":"))
    if instr_count == 0:
        return CheckResult(earned=0.0,
                           notes="output .asm has no instruction lines",
                           severity=SEVERITY_MAJOR)
    ratio = inline_count / instr_count
    all_src = _all_emitted_asm(g)
    has_push_comment = bool(re.search(r"#\s*push\b", all_src, re.IGNORECASE))
    has_pop_comment = bool(re.search(r"#\s*pop\b", all_src, re.IGNORECASE))
    score = 0.0
    notes: List[str] = []
    if ratio >= 0.30:
        score += 5.0
    elif ratio >= 0.15:
        score += 3.0
        notes.append(f"only {ratio*100:.0f}% of instructions have inline "
                     f"comments (aim for >= 30%)")
    else:
        notes.append(f"only {ratio*100:.0f}% of instructions have inline "
                     f"comments")
    if has_push_comment:
        score += 2.5
    else:
        notes.append("no '#push' inline comment style detected")
    if has_pop_comment:
        score += 2.5
    else:
        notes.append("no '#pop' inline comment style detected")
    severity = 0 if score >= 10 else SEVERITY_MINOR if score >= 5 else SEVERITY_MEDIUM
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _label_ids_unique(g: GradedSubmission) -> CheckResult:
    """Row 10 (10 pts): nextLabelID enables nested If/While correctly.

    Behavioural sub-score: did test05_if (nested IF) and test06_while
    pass? If both pass, full credit. Plus a structural check on the
    Emitter source for a counter that increments and is returned.
    """
    notes: List[str] = []
    score = 0.0
    src = _emitter_file_text(g)
    has_method = (g.method_for_role("Emitter", "nextLabelID") is not None
                  or "nextLabelID" in src)
    has_counter = bool(re.search(
        r"\b(labelCount|labelID|labelCounter|nextLabel)\s*\+\+", src
    )) or bool(re.search(
        r"\breturn\s+\+\+\s*\w+\b", src
    ))
    if has_method:
        score += 3.0
    else:
        notes.append("nextLabelID method not found")
    if has_counter:
        score += 2.0
    else:
        notes.append("counter increment not detected in Emitter")

    # Behavioural: nested IF + While are the rubric's specific concern.
    pass_names = {t.case.name for t in g.test_outcomes if t.passed}
    if {"test05_if", "test06_while"} & pass_names:
        score += 2.5 * len({"test05_if", "test06_while"} & pass_names) / 2
    if "test08_combined" in pass_names:
        score += 2.5    # the canonical "deeply nested" test
    else:
        notes.append("test08_combined (deep nesting) not passing")
    severity = 0 if score >= 10 else SEVERITY_MEDIUM if score >= 5 else SEVERITY_MAJOR
    return CheckResult(earned=round(min(score, 10.0), 1),
                       notes="; ".join(notes), severity=severity)


def _structure_quality(g: GradedSubmission) -> CheckResult:
    """Row 11 (10 pts): code is structured, modular, no repeated blocks.

    Mechanical heuristic: look at the largest AST class file (usually
    Program.java once compile() is added) and count duplicated 4-line
    runs. > 4 duplicate runs is "lots of repetition", < 1 is "clean".
    Plus a tag for the teacher to confirm.
    """
    cls = g.class_for_role("Program")
    src = _read(g.submission.compiler_root / cls.file) if cls else ""
    if not src:
        return CheckResult(earned=0.0,
                           notes="Program class not found",
                           severity=SEVERITY_MAJOR)
    lines = [ln.rstrip() for ln in src.splitlines()]
    runs: dict = {}
    for i in range(len(lines) - 4):
        chunk = tuple(ln.strip() for ln in lines[i:i + 4]
                      if ln.strip() and not ln.strip().startswith("//"))
        if len(chunk) < 4:
            continue
        runs[chunk] = runs.get(chunk, 0) + 1
    duplicates = sum(1 for c in runs.values() if c >= 2)
    score = 8.0 if duplicates <= 1 else 5.0 if duplicates <= 4 else 2.0
    notes = [f"{duplicates} repeated 4-line block(s) detected in Program"]
    notes.append("REVIEW: the rubric word 'modularity' requires teacher "
                 "judgement; mechanical score is the floor")
    severity = 0 if score >= 8 else SEVERITY_MINOR if score >= 5 else SEVERITY_MEDIUM
    return CheckResult(earned=score + 2.0,    # 2pt REVIEW credit baked in
                       notes="; ".join(notes), severity=severity)


def _testing_required_files(g: GradedSubmission) -> CheckResult:
    """Row 12 (10 pts): works on parserTest9.txt and max.txt.

    These two are the peer-review's named test files, shipped in
    tests/ as test08_combined.pas (parserTest9) and test07_max.pas
    (max). 5 pts each; the exact stdout match is what counts.
    """
    score = 0.0
    notes: List[str] = []
    targets = {
        "test07_max": "max.txt (max of 10, 20)",
        "test08_combined": "parserTest9.txt (full mixed program)",
    }
    for name, label in targets.items():
        outcome = next((t for t in g.test_outcomes
                        if t.case.name == name), None)
        if outcome is None:
            notes.append(f"{label}: not run")
            continue
        if outcome.passed:
            score += 5.0
        else:
            tag = outcome.error or "output mismatch"
            notes.append(f"{label}: {tag}")
    severity = (0 if score >= 10 else
                SEVERITY_MEDIUM if score >= 5 else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _data_section(src: str) -> str:
    """Return everything between `.data` and the next `.text` (or EOF)."""
    m = re.search(r"^\s*\.data\b(.*?)(?=^\s*\.text\b|\Z)",
                  src, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- #
# Rubric (12 rows in lab-document order, summing to 100 pts)
# --------------------------------------------------------------------------- #

RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="emitter-packaging",
        description="Emitter is in its own package or in the AST package; "
                    "rest of the package structure unchanged",
        points=4,
        checker=_emitter_packaging,
        category="Structure",
    ),
    RubricItem(
        code="all-methods-javadoc",
        description="All methods have Javadoc headers (params, returns, "
                    "pre/post, description) and it all makes sense",
        points=8,
        checker=_all_methods_javadoc,
        category="Documentation",
    ),
    RubricItem(
        code="stmt-expr-compile",
        description="Statement and Expression have the compile method",
        points=6,
        checker=_stmt_expr_have_compile,
        category="AST",
    ),
    RubricItem(
        code="ast-compile-overrides",
        description="All AST classes have the overridden compile method "
                    "appropriately",
        points=20,
        checker=_ast_compile_overrides,
        category="AST",
    ),
    RubricItem(
        code="output-extension",
        description="The output files have a .s, .a, or .asm extension",
        points=4,
        checker=_output_extension,
        category="Output",
    ),
    RubricItem(
        code="output-well-formed",
        description="The output asm has .data, .text and .globl main "
                    "(well-formed assembly)",
        points=6,
        checker=_output_well_formed,
        category="Output",
    ),
    RubricItem(
        code="vars-in-data",
        description="Variables are declared and emitted to the .data "
                    "section",
        points=6,
        checker=_vars_in_data,
        category="Output",
    ),
    RubricItem(
        code="output-javadoc-header",
        description="The output asm has a Javadoc-style header with author "
                    "and date (no description required)",
        points=6,
        checker=_output_javadoc_header,
        category="Output",
    ),
    RubricItem(
        code="inline-comments",
        description="The output asm has inline comments like '#push "
                    "(register)' / '#return value in (register)'",
        points=10,
        checker=_inline_comments,
        category="Output",
    ),
    RubricItem(
        code="label-ids",
        description="Emitter.nextLabelID() works and enables successful "
                    "nesting of statements",
        points=10,
        checker=_label_ids_unique,
        category="Emitter",
    ),
    RubricItem(
        code="structure-quality",
        description="Code is structured well, modular, does not repeat "
                    "blocks of code unnecessarily (REVIEW)",
        points=10,
        checker=_structure_quality,
        category="Quality",
    ),
    RubricItem(
        code="testing-required",
        description="Testing: works well on parserTest9.txt and max.txt "
                    "(the lab's required test files)",
        points=10,
        checker=_testing_required_files,
        category="Testing",
    ),
)


# --------------------------------------------------------------------------- #
# Hidden tests
# --------------------------------------------------------------------------- #

def _build_tests() -> List[TestCase]:
    expected_map = json.loads((TESTS_DIR / "expected.json")
                              .read_text(encoding="utf-8"))
    tests: List[TestCase] = []
    for name, meta in expected_map.items():
        tests.append(TestCase(
            name=name,
            description=meta["description"],
            source_path=TESTS_DIR / f"{name}.pas",
            expected_stdout=list(meta["expected"]),
            timeout=20,
        ))
    return tests


# --------------------------------------------------------------------------- #
# LabConfig factory
# --------------------------------------------------------------------------- #

def build_config(java_exe: str = "java",
                 javac_exe: str = "javac") -> LabConfig:
    return LabConfig(
        lab_name="CodeGen Lab",
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
        # Drive emit + MARS through our own driver so a hardcoded
        # filename in the student's CompilerTester can't mask wrong
        # emitted output.
        synthetic_tester_kind="codegen",
        # Each "test" emits a .asm via the synthetic driver and runs
        # it through MARS rather than diffing the synthetic driver's
        # own stdout (which is empty).
        test_runner=codegen_runner.run_codegen_test,
        mars_jar=VENDOR / "Mars4_5.jar",
    )
