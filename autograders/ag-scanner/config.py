"""
Scanner Lab specific configuration for the ATCS Compilers autograder.

The rubric below mirrors the official ATCS Scanner Peer Review sheet
row-for-row. Per-row points sum to 100. Rubric items 6-10 hinge on
running the student's Scanner against a small bank of test files in
tests/; the rest are structural/documentation checks that read the
parsed source tree.

Rubric structure (100 pts)
==========================
    1. Scanner class javadoc -- name, date, summary             (8)
    2. All methods have javadoc headers                          (8)
    3. Package structure with a `scanner` package                (8)
    4. Naming convention: lowerCamel packages, UpperCamel        (8)
    5. currentChar stored as an instance variable                (5)
    6. <=, >=, <>, := returned as single tokens                  (8)
    7. A period signifies EOF; hasNext() false at EOF            (6)
    8. Handles single-line comments (mandatory)                  (8)
    9. Code well-structured / modular -- REVIEW                  (8)
    10. Testing: scannerTest + scannerTestAdvanced behaviour    (25)
        Splits into:
            * basic-tokens cleanly                               (5)
            * raises ScanErrorException on $/^                  (10)
            * passes once bad line is removed                    (5)
            * passes once bad line is commented out              (5)
    11. Notebook entries -- to be checked off by teacher REVIEW  (8)

Airtightness
============
Each row is independent: a missing `currentChar` field doesn't blunt
the score for `<=` tokenization or for the comment-handling test, and
vice versa. Mirrors the same principle as ag-procedures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Sequence

from agcore import scanner_runner
from agcore.grader import GradedSubmission, LabConfig, TestCase
from agcore.proximity import ProximityFinding, check_class, check_method
from agcore.role_resolver import RoleSpec
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
# Rubric ROLES -- fuzzy class resolution
# --------------------------------------------------------------------------- #
#
# Most students name the class Scanner.java. A few rename to PascalScanner
# or Lexer. The resolver scores every parsed class on the signals below
# and picks the best fit; structural checks fall back to grep on a
# basename match when javalang can't parse the file.
# --------------------------------------------------------------------------- #

CLASS_ROLES = {
    "Scanner": RoleSpec(
        preferred_name="Scanner",
        aliases=("PascalScanner", "Lexer", "Tokenizer"),
        name_tokens=[("scanner",), ("lexer",), ("tokenizer",)],
        required_methods=("nextToken", "hasNext"),
        preferred_dir="scanner",
    ),
    "ScanErrorException": RoleSpec(
        preferred_name="ScanErrorException",
        aliases=("ScannerErrorException", "ScanError"),
        name_tokens=[("scan", "error"), ("scanner", "error")],
        preferred_dir="scanner",
    ),
}

METHOD_ALIASES = {
    ("Scanner", "nextToken"): ("nextToken", "next", "getNextToken"),
    ("Scanner", "hasNext"): ("hasNext", "hasNextToken", "hasMore"),
    ("Scanner", "getNextChar"): (
        "getNextChar", "advance", "readChar", "nextChar"),
    ("Scanner", "eat"): ("eat", "match", "consume"),
}


# --------------------------------------------------------------------------- #
# Keyword sets for documentation proximity checking
# --------------------------------------------------------------------------- #

CLASS_KEYWORDS = {
    "Scanner": (
        ["scanner", "token", "input", "character", "stream", "lexical"], 3),
}

METHOD_KEYWORDS = {
    ("Scanner", "nextToken"): (
        ["token", "next", "return", "scan", "white", "space"], 3),
    ("Scanner", "hasNext"): (
        ["end", "file", "eof", "false", "return"], 2),
    ("Scanner", "getNextChar"): (
        ["character", "read", "stream", "advance", "current"], 2),
    ("Scanner", "eat"): (
        ["expect", "advance", "match", "throw", "current"], 2),
}

MIN_METHOD_DESCRIPTION_WORDS = 0


# --------------------------------------------------------------------------- #
# Proximity rule
# --------------------------------------------------------------------------- #

def proximity_rule(graded: GradedSubmission) -> List[ProximityFinding]:
    """Score class + method javadocs against the keyword packs above.

    Anything outside the targeted lists gets an audit pass: a method
    must have a javadoc, the right @param/@return tags, and a
    non-empty description. We deliberately skip @precondition /
    @postcondition because students often write those in prose, and
    mechanical enforcement produces noisy false-positive REVIEWs.
    """
    findings: List[ProximityFinding] = []
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
# Helpers shared across rubric checkers
# --------------------------------------------------------------------------- #

def _scanner_source(g: GradedSubmission) -> str:
    """Read the Scanner class's source, falling back to unparseable files.

    Returns "" if the resolver can't find anything Scanner-shaped at
    all. Several rubric checkers grep this string for structural
    features (`currentChar`, comment handling, multi-char tokens), so
    a reliable accessor matters.
    """
    return g.source_for_role("Scanner") or ""


def _unparseable_note(g: GradedSubmission, role: str) -> str:
    """If the role's file is in unparsed_files, build a teacher-visible note."""
    fail = g.failure_for_role(role)
    if fail is None:
        return ""
    where = f" near line {fail.line}" if fail.line else ""
    return (f"{fail.file} could not be parsed{where}: {fail.reason} "
            f"-- AST-level checks for this role were skipped")


def _outcomes_by_name(g: GradedSubmission) -> dict:
    """Index test outcomes by case name. Used by rubric checkers that
    look for specific test results without iterating the whole list.
    """
    return {o.case.name: o for o in g.test_outcomes}


# --------------------------------------------------------------------------- #
# Rubric checkers
# --------------------------------------------------------------------------- #

def _class_header_tags(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 1: Scanner class-level javadoc has @author + @version + summary.

    Same shape as ag-procedures' header check, scaled to whatever
    point value the rubric assigns. Each of {summary, @author,
    @version} is worth 1/3 of the row.
    """
    cls = g.class_for_role("Scanner")
    unparseable = _unparseable_note(g, "Scanner")
    src = _scanner_source(g)
    per = points / 3.0

    if cls is None and not src:
        return CheckResult(
            earned=0, severity=SEVERITY_MAJOR,
            notes="Scanner class not found in submission")

    if cls is not None and cls.javadoc is not None:
        has_author = bool(cls.javadoc.tags_named("@author"))
        has_version = bool(cls.javadoc.tags_named("@version"))
        has_summary = bool(cls.javadoc.description.strip())
    elif cls is not None:
        has_summary = has_author = has_version = False
    else:
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
        notes.append("missing @version (or @date)")
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score > 0
                else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _all_methods_javadoc(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 2: every method in the Scanner class has a javadoc with
    appropriate @param / @return tags + a description.

    Mirrors the ag-procedures method-javadoc check. If the Scanner file
    couldn't be parsed, the heuristic counts /** */ blocks vs.
    method-signature-looking lines and credits proportional.
    """
    cls = g.class_for_role("Scanner")
    unparseable = _unparseable_note(g, "Scanner")
    src = _scanner_source(g)

    if cls is None and not src:
        return CheckResult(
            earned=0, severity=SEVERITY_MAJOR,
            notes="Scanner class not found")

    if cls is None:
        blocks = len(re.findall(r"/\*\*.*?\*/", src, re.DOTALL))
        method_like = len(re.findall(
            r"(?m)^\s*(?:public|private|protected|static|\s)*[\w<>\[\],\s]+\s"
            r"+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\{", src))
        if method_like == 0:
            return CheckResult(
                earned=points,
                notes=(unparseable + "; no methods visible")
                if unparseable else "no methods", severity=0)
        fraction = min(1.0, blocks / max(method_like, 1))
        earned = round(points * fraction, 1)
        note = (f"{unparseable}; text-match heuristic: {blocks} javadoc "
                f"blocks for ~{method_like} methods "
                f"(scored {earned}/{points})")
        sev = 0 if earned >= points else (
            SEVERITY_MINOR if fraction >= 0.66 else SEVERITY_MEDIUM)
        return CheckResult(earned=earned, notes=note, severity=sev)

    if not cls.methods:
        return CheckResult(earned=points, notes="no methods", severity=0)

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
    sev = 0
    if earned < points:
        sev = (SEVERITY_MINOR if fraction >= 0.66
               else SEVERITY_MEDIUM if fraction >= 0.33
               else SEVERITY_MAJOR)
    return CheckResult(
        earned=earned, severity=sev,
        notes=("; ".join(issues[:3])
               + (" ..." if len(issues) > 3 else "")))


def _scanner_package(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 3: Scanner.java lives in a `scanner` package.

    Verified two ways:
      * The resolved Scanner class's file is under scanner/<...>.java
      * The source contains a `package scanner;` line (text grep -- so
        a file in the right folder with the wrong package declaration
        still gets the strucural credit but the package decl miss
        is noted).
    Full credit needs both signals.
    """
    cls = g.class_for_role("Scanner")
    src = _scanner_source(g)
    score = 0.0
    notes: List[str] = []
    if cls is not None and cls.file.startswith("scanner/"):
        score += points * 0.5
    else:
        notes.append("Scanner file not under scanner/ directory")
    if re.search(r"^\s*package\s+scanner\s*;", src, re.MULTILINE):
        score += points * 0.5
    elif src:
        notes.append("no `package scanner;` declaration in Scanner.java")
    else:
        notes.append("Scanner source unreadable")
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.5
                else SEVERITY_MEDIUM)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


_PACKAGE_DECL_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _naming_convention(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 4: package names lowerCamel, class names UpperCamel.

    We walk every parsed class. A class qualifies as UpperCamel iff its
    name starts with an upper-case letter and contains no underscores.
    Package names are read off the source's `package` declaration, not
    the directory path -- some students put files in the wrong folder
    on purpose.

    Each violation costs proportional credit. Score is clamped at 0.
    """
    score = points
    notes: List[str] = []
    seen_packages: set = set()
    class_offenders: List[str] = []
    package_offenders: List[str] = []

    for cls in g.classes:
        # Class names: must start with upper case, no underscores.
        if not cls.name[:1].isupper() or "_" in cls.name:
            class_offenders.append(cls.name)
        try:
            src = (g.submission.compiler_root / cls.file).read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _PACKAGE_DECL_RE.search(src)
        if m is None:
            continue
        pkg = m.group(1)
        if pkg in seen_packages:
            continue
        seen_packages.add(pkg)
        # Package: lowerCamel (no upper-case, no underscores).
        # Dots split sub-packages; each segment must obey the rule.
        for seg in pkg.split("."):
            if not seg:
                continue
            if seg[0].isupper() or "_" in seg:
                package_offenders.append(pkg)
                break

    # Each kind of offence loses up to half the row.
    if class_offenders:
        score -= min(points * 0.5,
                     points * 0.1 * len(class_offenders))
        notes.append("non-UpperCamel class names: "
                     + ", ".join(class_offenders[:4])
                     + (" ..." if len(class_offenders) > 4 else ""))
    if package_offenders:
        score -= min(points * 0.5,
                     points * 0.25 * len(package_offenders))
        notes.append("non-lowerCamel packages: "
                     + ", ".join(sorted(set(package_offenders))[:4]))

    score = max(0.0, round(score, 1))
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.66
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _current_char_field(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 5: currentChar (or equivalent) is an instance field.

    Heuristic: look for `private <type> currentChar` (or `curChar`,
    `current`, `ch`) at class level in Scanner.java. We don't insist
    on `private`; `protected`/no-modifier also count. We DO insist the
    field is declared outside any method body, which a top-of-class
    grep approximates.
    """
    src = _scanner_source(g)
    if not src:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="Scanner source unreadable")
    # Find the body of the class and consider the chunk before the
    # first method-body { to be the field-declaration region.
    # Approximate: take everything up to the first opening { of a
    # public/private method signature.
    pattern = re.compile(
        r"\b(private|protected|public|static|final|\s)+\s*"
        r"(?:char|Character|int|Integer)\s+"
        r"(?:currentChar|curChar|cur|currentCharacter|c|ch|next)\s*[;=]")
    if pattern.search(src):
        return CheckResult(earned=points, notes="", severity=0)
    # Fallback: a plain `char <name>` line at all (less strict)
    if re.search(r"\b(char|Character)\s+(currentChar|curChar|cur|ch)\b",
                 src):
        return CheckResult(
            earned=round(points * 0.6, 1), severity=SEVERITY_MINOR,
            notes="currentChar-ish field found but visibility/type uncertain")
    return CheckResult(
        earned=0, severity=SEVERITY_MEDIUM,
        notes="no `currentChar` (or `curChar`/`ch`) instance field detected; "
              "is the current char being passed between methods?")


def _multi_char_tokens(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 6: <=, >=, <>, := are returned as single tokens.

    Behavioural: re-uses the `test_multichar` hidden test outcome.
    Pass -> full credit. Partial passes are unusual (you either
    coalesce all four or you don't), so a fail goes to 0 with a
    teacher-visible explanation.
    """
    outcomes = _outcomes_by_name(g)
    o = outcomes.get("test_multichar")
    if o is None:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="test_multichar did not run")
    if o.passed:
        return CheckResult(earned=points, severity=0, notes="")
    return CheckResult(
        earned=0, severity=SEVERITY_MEDIUM,
        notes=(o.error or "test_multichar failed; check <=, >=, <>, :=")
        + (f"; actual: {o.actual_stdout!r}" if o.actual_stdout else ""))


def _period_eof(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 7: period returns 'EOF'; hasNext() false at EOF.

    Behavioural: `test_period_eof` covers both. The test file has
    tokens after the period; only the pre-period tokens (plus 'EOF')
    should be emitted.
    """
    outcomes = _outcomes_by_name(g)
    o = outcomes.get("test_period_eof")
    if o is None:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="test_period_eof did not run")
    if o.passed:
        return CheckResult(earned=points, severity=0, notes="")
    return CheckResult(
        earned=round(points * 0.3, 1), severity=SEVERITY_MEDIUM,
        notes=(o.error or "test_period_eof failed")
        + "; period must produce EOF and hasNext() must then be false")


def _single_line_comments(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 8: single-line comments (//) are skipped (mandatory).

    Behavioural via test_basic_comment. We also peek the source for
    block-comment handling; a student who implements `/* */` is the
    bonus arm of the rubric and we surface that detection in the
    notes (no extra credit -- the row only awards single-line).
    """
    outcomes = _outcomes_by_name(g)
    o = outcomes.get("test_basic_comment")
    if o is None:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="test_basic_comment did not run")
    notes: List[str] = []
    src = _scanner_source(g)
    if re.search(r"/\*", src):
        # Look for block-comment handling: a / -> peek and skip until */
        if "*/" in src and re.search(r"['\"]\*['\"]|\\*['\"]/['\"]", src) is None:
            # Only credit if the file actually peeks for it. This is a
            # weak signal -- the notes line is informational.
            notes.append("multi-line comment handling appears present (bonus)")
    if o.passed:
        return CheckResult(earned=points, severity=0,
                           notes="; ".join(notes))
    return CheckResult(
        earned=0, severity=SEVERITY_MEDIUM,
        notes=(o.error or "test_basic_comment failed; // comments not skipped")
        + (("; " + "; ".join(notes)) if notes else ""))


def _code_structure_review(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 9: code is well-structured / modular (REVIEW).

    We can't fully judge style automatically. Use a simple weighted
    signal: if Scanner has a reasonable number of small private
    helpers (scanNumber, scanIdentifier, scanOperand, eat,
    getNextChar) then award proportional credit; otherwise grant
    half-credit and tag REVIEW so the teacher confirms.
    """
    cls = g.class_for_role("Scanner")
    helpers_hit = 0
    helper_aliases = {
        "scanNumber": ("scanNumber", "scanInt", "scanInteger", "readNumber"),
        "scanIdentifier": ("scanIdentifier", "scanId", "readIdentifier"),
        "scanOperand": ("scanOperand", "scanOperator", "scanOp"),
        "eat": ("eat", "match", "consume"),
        "getNextChar": ("getNextChar", "advance", "readChar"),
    }
    if cls is not None:
        method_names = {m.method_name for m in cls.methods}
        for aliases in helper_aliases.values():
            if any(a in method_names for a in aliases):
                helpers_hit += 1
    # Half credit baseline + the rest proportional to helper count
    base = points * 0.5
    bonus = (points - base) * (helpers_hit / len(helper_aliases))
    earned = round(base + bonus, 1)
    note = (f"REVIEW: structure auto-credit {earned}/{points} "
            f"({helpers_hit}/{len(helper_aliases)} canonical helpers detected); "
            "teacher should skim for repeated blocks / oversized nextToken")
    severity = 0 if earned >= points * 0.9 else SEVERITY_MINOR
    return CheckResult(earned=earned, notes=note, severity=severity)


def _testing_row(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 10 (25 pts): scannerTest + scannerTestAdvanced behaviour.

    Breakdown:
        * 5 pts -- basic test (subsumes single-line comments + ops)
        * 10 pts -- throws ScanErrorException on $/^
        * 5 pts -- works when the bad line is removed
        * 5 pts -- works when the bad line is commented out

    Behavioural rows 6/7/8 also lean on these test outcomes; this row
    is the catch-all that mirrors the rubric's wording.
    """
    outcomes = _outcomes_by_name(g)

    def _credit(name: str, pts: float, what: str) -> tuple:
        o = outcomes.get(name)
        if o is None:
            return 0.0, f"{what}: not run"
        if o.passed:
            return pts, ""
        return 0.0, f"{what}: failed ({o.error or 'mismatch'})"

    score = 0.0
    notes: List[str] = []
    for name, pts, what in (
        ("test_basic_comment", 5.0, "basic+comments"),
        ("test_error_dollar", 10.0, "throws on $/^"),
        ("test_bad_removed", 5.0, "bad line removed"),
        ("test_bad_commented", 5.0, "bad line commented out"),
    ):
        got, note = _credit(name, pts, what)
        score += got
        if note:
            notes.append(note)
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points * 0.5
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _notebook_review(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 11: notebook entries -- REVIEW only (teacher checks off).

    We can't see the notebook. Award full points (the teacher will
    deduct manually if missing) and tag REVIEW so they don't forget
    to check.
    """
    return CheckResult(
        earned=points, severity=0,
        notes="REVIEW: teacher checks off notebook entries; full credit "
              "awarded by default -- adjust manually if missing")


# --------------------------------------------------------------------------- #
# Text-level helpers (re-used from ag-procedures)
# --------------------------------------------------------------------------- #

def _grep_class_javadoc(src: str) -> tuple:
    """Pull out (has_summary, has_author, has_version) from the class
    header javadoc block in src, doing best-effort regex extraction.

    Picks the LAST /** ... */ block before the first `class X`
    declaration -- that's conventionally the class header. Used as the
    text-level fallback when javalang couldn't parse the file.
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
    has_version = "@version" in header or "@date" in header
    inner = re.sub(r"^/\*\*|\*/$", "", header, flags=re.DOTALL)
    desc_part = inner.split("@", 1)[0]
    desc_clean = re.sub(r"(?m)^\s*\*\s?", "", desc_part).strip()
    has_summary = bool(desc_clean)
    return (has_summary, has_author, has_version)


# --------------------------------------------------------------------------- #
# The rubric itself
# --------------------------------------------------------------------------- #

RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="scanner-class-doc",
        description="Scanner class: comments include name, date, summary "
                    "using JavaDoc Standards.",
        points=8,
        checker=lambda g: _class_header_tags(g, 8),
        category="Documentation",
    ),
    RubricItem(
        code="all-methods-doc",
        description="All methods have Javadoc headers (parameters, "
                    "returns, pre/post, description) and they make sense.",
        points=8,
        checker=lambda g: _all_methods_javadoc(g, 8),
        category="Documentation",
    ),
    RubricItem(
        code="scanner-package",
        description="Package structure includes a `scanner` package.",
        points=8,
        checker=lambda g: _scanner_package(g, 8),
        category="Project structure",
    ),
    RubricItem(
        code="naming-convention",
        description="Naming convention: package names lowerCamel, class "
                    "names UpperCamel.",
        points=8,
        checker=lambda g: _naming_convention(g, 8),
        category="Project structure",
    ),
    RubricItem(
        code="current-char-field",
        description="currentChar stored in an instance variable; not "
                    "passed between methods unnecessarily.",
        points=5,
        checker=lambda g: _current_char_field(g, 5),
        category="Scanner",
    ),
    RubricItem(
        code="multi-char-tokens",
        description="<=, >=, <>, := are returned as single tokens.",
        points=8,
        checker=lambda g: _multi_char_tokens(g, 8),
        category="Scanner",
    ),
    RubricItem(
        code="period-eof",
        description="Period (.) signifies EOF and returns the EOF token; "
                    "hasNext() returns false at EOF.",
        points=6,
        checker=lambda g: _period_eof(g, 6),
        category="Scanner",
    ),
    RubricItem(
        code="single-line-comments",
        description="Handles single-line comments (//). Mandatory; "
                    "multi-line / nested are bonus.",
        points=8,
        checker=lambda g: _single_line_comments(g, 8),
        category="Scanner",
    ),
    RubricItem(
        code="code-structure",
        description="Code is well-structured, modular, does not repeat "
                    "blocks unnecessarily (REVIEW).",
        points=8,
        checker=lambda g: _code_structure_review(g, 8),
        category="Quality",
    ),
    RubricItem(
        code="testing",
        description="Testing: tokenizes scannerTest / scannerTestAdvanced "
                    "well; throws on $/^; passes after the bad line is "
                    "removed; passes after the bad line is commented out.",
        points=25,
        checker=lambda g: _testing_row(g, 25),
        category="Testing",
    ),
    RubricItem(
        code="notebook",
        description="Notebook entries -- to be checked off by teacher "
                    "(REVIEW).",
        points=8,
        checker=lambda g: _notebook_review(g, 8),
        category="Documentation",
    ),
)


# --------------------------------------------------------------------------- #
# Hidden test cases
# --------------------------------------------------------------------------- #

def _build_tests() -> List[TestCase]:
    """Load tests/*.txt + tests/expected.json into TestCase records.

    Each entry in expected.json may carry an optional `match_mode`
    field; the scanner_runner consults it to switch between exact
    match and the prefix_then_error rule used for the $-error case.
    """
    expected_map = json.loads((TESTS_DIR / "expected.json")
                              .read_text(encoding="utf-8"))
    tests: List[TestCase] = []
    for name, meta in expected_map.items():
        tests.append(TestCase(
            name=name,
            description=meta["description"],
            source_path=TESTS_DIR / f"{name}.txt",
            expected_stdout=list(meta["expected"]),
            match_mode=meta.get("match_mode", "exact"),
        ))
    return tests


# --------------------------------------------------------------------------- #
# LabConfig entry point
# --------------------------------------------------------------------------- #

def build_config(java_exe: str = "java",
                 javac_exe: str = "javac") -> LabConfig:
    """Assemble the LabConfig the orchestrator needs.

    The synthetic-tester pass injects a fresh `scanner._AGScannerTester`
    per submission so the student's hardcoded ScannerTester filenames
    can't make every hidden test silently re-run the same baked-in file.
    """
    return LabConfig(
        lab_name="Scanner Lab",
        rubric=RUBRIC,
        hidden_tests=_build_tests(),
        proximity_rules=[proximity_rule],
        checkstyle_jar=VENDOR / "checkstyle-10.14.0-all.jar",
        checkstyle_xml=VENDOR / "checkstyle.xml",
        java_exe=java_exe,
        javac_exe=javac_exe,
        main_class="scanner.Scanner",
        class_roles=CLASS_ROLES,
        method_aliases=METHOD_ALIASES,
        synthetic_tester_kind="scanner",
        test_runner=scanner_runner.run_scanner_test,
    )
