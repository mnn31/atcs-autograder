"""
Pascal Parser Lab configuration for the ATCS Compilers autograder.

The rubric below mirrors the official Parser Lab peer-review sheet
row-for-row (sum = 100 pts). In this lab the parser EXECUTES Pascal
as it parses -- parseStatement is void and side-effects WRITELN
output to stdout. The synthetic-tester pass injects a fresh
`parser._AGParserTester` that calls parser.parseStatement() in a
loop while scanner.hasNext() returns true, so a student whose own
ParserTester hardcodes a filename can't make every hidden test
silently re-run the same baked-in file.

Rubric structure (100 pts)
==========================
    1. Parser javadoc + ParserTester/Main present                (6)
    2. All methods have javadoc headers                          (6)
    3. Project has scanner + parser packages                     (4)
    4. Naming convention: lowerCamel packages, UpperCamel        (4)
    5. currentToken stored as an instance variable               (2)
    6. Scanner returns <=, >=, <>, := as single tokens           (6)
    7. EOF/period + hasNext + tester uses hasNext                (6)
    8. parseTerm/parseFactor/parseExpression/parseNumber +
        parseStatement handles WRITELN + assignment             (35)
    9. Handles BEGIN/END blocks                                  (8)
    10. Code is well-structured / modular                       (8) REVIEW
    11. Testing: parserTest0 through parserTest4                 (15)

Airtightness
============
Every row is independent. A missing parseStatement doesn't blunt
credit for currentToken or for the scanner-side multi-char-token
behaviour, and a single failing parserTest doesn't cascade to zero
out unrelated parser rows.
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
    "Parser": RoleSpec(
        preferred_name="Parser",
        aliases=("PascalParser",),
        name_tokens=[("parser",)],
        required_methods=("parseStatement", "parseStmt", "parse"),
        preferred_dir="parser",
    ),
    "ParserTester": RoleSpec(
        preferred_name="ParserTester",
        aliases=("Main", "ParserMain", "Driver", "Tester"),
        name_tokens=[("parser", "tester"), ("main",), ("driver",),
                     ("tester",)],
        required_methods=("main",),
        preferred_dir="parser",
    ),
    "Scanner": RoleSpec(
        preferred_name="Scanner",
        aliases=("PascalScanner", "Lexer", "Tokenizer"),
        name_tokens=[("scanner",), ("lexer",), ("tokenizer",)],
        required_methods=("nextToken", "hasNext"),
        preferred_dir="scanner",
    ),
}

METHOD_ALIASES = {
    ("Parser", "parseStatement"): (
        "parseStatement", "parseStmt", "parseStatements"),
    ("Parser", "parseExpression"): (
        "parseExpression", "parseExpr", "parseExp"),
    ("Parser", "parseTerm"): ("parseTerm",),
    ("Parser", "parseFactor"): ("parseFactor",),
    ("Parser", "parseNumber"): (
        "parseNumber", "parseNum", "parseInt", "parseInteger"),
    ("Parser", "eat"): ("eat", "match", "consume"),
    ("Scanner", "nextToken"): ("nextToken", "next", "getNextToken"),
    ("Scanner", "hasNext"): ("hasNext", "hasNextToken", "hasMore"),
}


# --------------------------------------------------------------------------- #
# Keyword sets for documentation proximity checking
# --------------------------------------------------------------------------- #

CLASS_KEYWORDS = {
    "Parser": (
        ["parser", "token", "grammar", "expression", "statement",
         "recursive"], 3),
    "ParserTester": (
        ["parser", "tester", "test", "file", "scanner", "main"], 2),
    "Scanner": (
        ["scanner", "token", "input", "character", "lexical"], 3),
}

METHOD_KEYWORDS = {
    ("Parser", "parseStatement"): (
        ["parse", "statement", "writeln", "begin", "end", "assignment"], 3),
    ("Parser", "parseExpression"): (
        ["parse", "expression", "term", "plus", "minus", "left", "factor"],
        3),
    ("Parser", "parseTerm"): (
        ["parse", "term", "factor", "multiply", "divide"], 3),
    ("Parser", "parseFactor"): (
        ["parse", "factor", "number", "parenthesis", "identifier"], 3),
    ("Parser", "parseNumber"): (
        ["parse", "number", "integer", "eat"], 2),
    ("Parser", "eat"): (
        ["expected", "advance", "match", "scanner", "current"], 2),
    ("Scanner", "nextToken"): (
        ["token", "next", "return", "scan", "white", "space"], 3),
    ("Scanner", "hasNext"): (
        ["end", "file", "eof", "false", "return"], 2),
}

MIN_METHOD_DESCRIPTION_WORDS = 0


# --------------------------------------------------------------------------- #
# Proximity rule
# --------------------------------------------------------------------------- #

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


def _grep_class_javadoc(src: str) -> tuple:
    """(has_summary, has_author, has_version) text-extracted from src.

    Picks the last /** ... */ block before the first `class X` -- the
    conventional class header location. Used when javalang can't parse
    a file but the javadoc is plainly there.
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
# Rubric checkers
# --------------------------------------------------------------------------- #

def _parser_doc_plus_tester(g: GradedSubmission) -> CheckResult:
    """Rubric row 1 (6 pts): Parser javadoc AND a tester class exists.

    Parses as two sub-criteria:
      * 3 pts: Parser class header javadoc has @author + summary
      * 3 pts: A tester class (ParserTester / Main / Driver) lives in
        parser/ or default package and constructs a Parser instance
    """
    cls = g.class_for_role("Parser")
    src = _role_source(g, "Parser")
    unparseable = _unparseable_note(g, "Parser")
    score = 0.0
    notes: List[str] = []
    if unparseable:
        notes.append(unparseable)

    # Parser header doc
    if cls is not None and cls.javadoc is not None:
        if cls.javadoc.description.strip() and (
                cls.javadoc.tags_named("@author")):
            score += 3.0
        elif cls.javadoc.description.strip():
            score += 1.5
            notes.append("Parser javadoc missing @author")
        else:
            notes.append("Parser javadoc has no summary")
    elif src:
        has_summary, has_author, _ = _grep_class_javadoc(src)
        if has_summary and has_author:
            score += 3.0
        elif has_summary:
            score += 1.5
            notes.append("Parser javadoc found (text scan) but no @author")
        else:
            notes.append("no Parser class javadoc detected")
    else:
        notes.append("Parser class missing or unreadable")

    # Tester class present and constructs a Parser
    tester_cls = g.class_for_role("ParserTester")
    parser_constructed = False
    if tester_cls is not None:
        try:
            tester_src = (g.submission.compiler_root / tester_cls.file
                          ).read_text(encoding="utf-8", errors="replace")
        except OSError:
            tester_src = ""
        if re.search(r"\bnew\s+(?:parser\.)?Parser\s*\(", tester_src):
            parser_constructed = True
    if tester_cls is not None and parser_constructed:
        score += 3.0
    elif tester_cls is not None:
        score += 1.5
        notes.append(f"tester {tester_cls.name} exists but does not "
                     f"construct a Parser instance")
    else:
        notes.append("no ParserTester / Main / Driver class found")

    score = round(score, 1)
    severity = (0 if score >= 6 else SEVERITY_MEDIUM if score >= 3
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _all_methods_javadoc(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 2 (6 pts): every method in Parser has a javadoc.

    Same shape as ag-procedures' method-javadoc check. Audits the
    Parser class; tester/scanner classes are covered by the proximity
    rule. Falls back to a /** */ block count when the file is
    unparseable.
    """
    cls = g.class_for_role("Parser")
    unparseable = _unparseable_note(g, "Parser")
    src = _role_source(g, "Parser")

    if cls is None and not src:
        return CheckResult(earned=0, severity=SEVERITY_MAJOR,
                           notes="Parser class not found")
    if cls is None:
        blocks = len(re.findall(r"/\*\*.*?\*/", src, re.DOTALL))
        method_like = len(re.findall(
            r"(?m)^\s*(?:public|private|protected|static|\s)*[\w<>\[\],\s]+\s"
            r"+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\{", src))
        if method_like == 0:
            return CheckResult(earned=points, severity=0,
                               notes=unparseable or "no methods")
        fraction = min(1.0, blocks / max(method_like, 1))
        earned = round(points * fraction, 1)
        return CheckResult(
            earned=earned,
            severity=(0 if earned >= points
                      else SEVERITY_MINOR if fraction >= 0.66
                      else SEVERITY_MEDIUM),
            notes=f"{unparseable}; {blocks} javadoc blocks for "
                  f"~{method_like} methods")

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
            have = len(m.javadoc.tags_named("@param"))
            if have < len(m.params):
                problems.append(f"@param x{len(m.params) - have} missing")
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
        notes="; ".join(issues[:3])
              + (" ..." if len(issues) > 3 else ""))


def _packages_present(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 3 (4 pts): both `scanner` and `parser` packages exist.

    Each package contributes half the row. Missing one drops to half
    credit; missing both is zero.
    """
    have_scanner = False
    have_parser = False
    for cls in g.classes:
        if cls.file.startswith("scanner/"):
            have_scanner = True
        if cls.file.startswith("parser/"):
            have_parser = True
    score = 0.0
    notes: List[str] = []
    if have_scanner:
        score += points / 2
    else:
        notes.append("no scanner/ package detected")
    if have_parser:
        score += points / 2
    else:
        notes.append("no parser/ package detected")
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points / 2
                else SEVERITY_MAJOR)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


_PACKAGE_DECL_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _naming_convention(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 4 (4 pts): UpperCamel classes, lowerCamel packages."""
    score = points
    class_offenders: List[str] = []
    package_offenders: List[str] = []
    seen_packages: set = set()
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
        if pkg in seen_packages:
            continue
        seen_packages.add(pkg)
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


def _current_token_field(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 5 (2 pts): currentToken (or token / curToken / next) stored
    as an instance field on the Parser class.
    """
    src = _role_source(g, "Parser")
    if not src:
        return CheckResult(earned=0, severity=SEVERITY_MEDIUM,
                           notes="Parser source unreadable")
    pat = re.compile(
        r"\b(private|protected|public|static|final|\s)+\s*String\s+"
        r"(?:currentToken|curToken|cur|token|current|next|nextToken)\s*[;=]")
    if pat.search(src):
        return CheckResult(earned=points, severity=0, notes="")
    if re.search(r"\bString\s+(?:currentToken|curToken|token|cur)\b", src):
        return CheckResult(
            earned=round(points * 0.6, 1), severity=SEVERITY_MINOR,
            notes="token-like field found but visibility/type uncertain")
    return CheckResult(
        earned=0, severity=SEVERITY_MEDIUM,
        notes="no currentToken-style instance field detected")


def _scanner_multichar(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 6 (6 pts): Scanner returns <=, >=, <>, := as single tokens.

    Behavioural via parserTest6+ in other labs, but here we lean on the
    fact that the included parserTest3/parserTest4 use := and any
    parser-lab Scanner that handles := correctly passes parserTest4.
    Light text-grep on the Scanner source to corroborate the intent.
    """
    src = _role_source(g, "Scanner")
    score = 0.0
    notes: List[str] = []
    matches = 0
    for op in ("<=", ">=", "<>", ":="):
        if op in src:
            matches += 1
    score = points * matches / 4
    # parserTest4 passing is a strong behavioural signal that := is handled
    outcomes = _outcomes_by_name(g)
    test4 = outcomes.get("parserTest4")
    if test4 is not None and test4.passed:
        # Bump to full credit -- assignment requires := tokenisation.
        score = points
    elif matches < 4:
        notes.append(f"only {matches}/4 multi-char operators detected in "
                     f"Scanner source")
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.66
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _eof_and_hasnext(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 7 (6 pts): Scanner returns 'EOF' on `.`, hasNext() goes
    false at EOF, and the tester uses hasNext() to drive its loop.
    """
    scanner_src = _role_source(g, "Scanner")
    tester_cls = g.class_for_role("ParserTester")
    score = 0.0
    notes: List[str] = []
    # Half: scanner's nextToken can return "EOF"
    if '"EOF"' in scanner_src or "'EOF'" in scanner_src or \
            "EOF" in scanner_src:
        score += points * 0.5
    else:
        notes.append("Scanner source does not mention an EOF token")
    # Half: the tester uses hasNext()
    if tester_cls is not None:
        try:
            tester_src = (g.submission.compiler_root / tester_cls.file
                          ).read_text(encoding="utf-8", errors="replace")
        except OSError:
            tester_src = ""
        if "hasNext" in tester_src:
            score += points * 0.5
        else:
            notes.append(f"{tester_cls.name} does not call hasNext() "
                         f"to drive its parse loop")
    else:
        notes.append("no tester class found, can't verify hasNext usage")
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MINOR if score >= points * 0.5
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _core_parse_methods(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 8 (35 pts): parseTerm / parseFactor / parseExpression /
    parseNumber present, parseStatement handles WRITELN + assignment.

    Two arms:
      * 20 pts: structural -- each of the 5 methods exists on Parser
      * 15 pts: behavioural -- proportional credit from parserTest0..4
        which collectively exercise parseStatement (WRITELN +
        assignment), parseExpression (+/-), parseTerm (*//), and
        parseFactor (numbers, parens, negation, identifiers).
    """
    score = 0.0
    notes: List[str] = []
    structural_methods = (
        ("parseTerm", 4),
        ("parseFactor", 4),
        ("parseExpression", 4),
        ("parseNumber", 4),
        ("parseStatement", 4),
    )
    src = _role_source(g, "Parser")
    for role, pts in structural_methods:
        m = g.method_for_role("Parser", role)
        if m is not None:
            score += pts
            continue
        aliases = g.config.method_aliases.get(("Parser", role), (role,))
        if any(f"{a}(" in src for a in aliases):
            score += pts
            notes.append(f"{role}: found via text match")
        else:
            notes.append(f"{role}: not found")
    # parseStatement WRITELN + assignment behavioural check via tests
    outcomes = _outcomes_by_name(g)
    behavioural_total = 15.0
    test_names = ("parserTest0", "parserTest1", "parserTest2",
                  "parserTest3", "parserTest4")
    passed = sum(1 for n in test_names
                 if (o := outcomes.get(n)) is not None and o.passed)
    behavioural = behavioural_total * passed / len(test_names)
    score += behavioural
    if passed < len(test_names):
        failing = [n for n in test_names
                   if (o := outcomes.get(n)) is not None and not o.passed]
        notes.append(f"parserTest pass rate: {passed}/{len(test_names)}"
                     + (f" (failing: {', '.join(failing)})"
                        if failing else ""))
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points * 0.5
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _begin_end_blocks(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 9 (8 pts): handles BEGIN/END blocks.

    Behavioural: parserTest3 and parserTest4 both use BEGIN/END blocks
    (nested in 3, single block in 4). Either passing gives partial
    credit; both passing gives full credit.
    """
    outcomes = _outcomes_by_name(g)
    score = 0.0
    notes: List[str] = []
    test3 = outcomes.get("parserTest3")
    test4 = outcomes.get("parserTest4")
    if test3 is not None and test3.passed:
        score += points / 2
    else:
        notes.append("parserTest3 (nested BEGIN/END) failed")
    if test4 is not None and test4.passed:
        score += points / 2
    else:
        notes.append("parserTest4 (BEGIN/END with assignments) failed")
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points / 2
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes),
                       severity=severity)


def _code_structure_review(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 10 (8 pts): code is well-structured (REVIEW).

    Heuristic: count canonical parse helpers and award proportional.
    Half-credit baseline so the teacher sees this as a soft signal.
    """
    cls = g.class_for_role("Parser")
    helper_aliases = {
        "eat": ("eat", "match", "consume"),
        "parseNumber": ("parseNumber", "parseNum", "parseInt"),
        "parseFactor": ("parseFactor",),
        "parseTerm": ("parseTerm",),
        "parseExpression": ("parseExpression", "parseExpr"),
        "parseStatement": ("parseStatement", "parseStmt"),
    }
    hits = 0
    if cls is not None:
        names = {m.method_name for m in cls.methods}
        for aliases in helper_aliases.values():
            if any(a in names for a in aliases):
                hits += 1
    base = points * 0.5
    bonus = (points - base) * (hits / len(helper_aliases))
    earned = round(base + bonus, 1)
    note = (f"REVIEW: auto-credit {earned}/{points} "
            f"({hits}/{len(helper_aliases)} canonical helpers detected); "
            "teacher should skim for repeated code")
    severity = 0 if earned >= points * 0.9 else SEVERITY_MINOR
    return CheckResult(earned=earned, notes=note, severity=severity)


def _testing_row(g: GradedSubmission, points: float) -> CheckResult:
    """Rubric row 11 (15 pts): parserTest0 through parserTest4 all pass.

    Proportional credit: 3 pts per passing file. Behavioural -- if a
    student passes 4/5 they earn 12/15.
    """
    outcomes = _outcomes_by_name(g)
    names = ("parserTest0", "parserTest1", "parserTest2",
             "parserTest3", "parserTest4")
    per = points / len(names)
    score = 0.0
    failing: List[str] = []
    for n in names:
        o = outcomes.get(n)
        if o is not None and o.passed:
            score += per
        else:
            failing.append(n + (f" ({o.error})" if o and o.error else ""))
    score = round(score, 1)
    severity = (0 if score >= points
                else SEVERITY_MEDIUM if score >= points * 0.5
                else SEVERITY_MAJOR)
    notes = "; ".join(failing[:5]) if failing else ""
    return CheckResult(earned=score, notes=notes, severity=severity)


# --------------------------------------------------------------------------- #
# The rubric itself
# --------------------------------------------------------------------------- #

RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="parser-doc-tester",
        description="Parser class javadoc (name/date/summary) AND a "
                    "ParserTester / Main class that creates a Parser "
                    "instance.",
        points=6,
        checker=_parser_doc_plus_tester,
        category="Documentation",
    ),
    RubricItem(
        code="all-methods-doc",
        description="All methods have Javadoc headers (parameters, "
                    "returns, pre/post, description).",
        points=6,
        checker=lambda g: _all_methods_javadoc(g, 6),
        category="Documentation",
    ),
    RubricItem(
        code="packages-present",
        description="Project has scanner + parser packages.",
        points=4,
        checker=lambda g: _packages_present(g, 4),
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
        code="current-token-field",
        description="currentToken stored in an instance variable; not "
                    "passed between methods unnecessarily.",
        points=2,
        checker=lambda g: _current_token_field(g, 2),
        category="Parser",
    ),
    RubricItem(
        code="scanner-multichar",
        description="Scanner returns <=, >=, <>, := as single tokens.",
        points=6,
        checker=lambda g: _scanner_multichar(g, 6),
        category="Scanner",
    ),
    RubricItem(
        code="eof-hasnext",
        description="Period (.) signals EOF; hasNext() false at EOF; "
                    "tester uses hasNext() to drive its parse loop.",
        points=6,
        checker=lambda g: _eof_and_hasnext(g, 6),
        category="Scanner",
    ),
    RubricItem(
        code="core-parse-methods",
        description="parseTerm, parseFactor, parseExpression, parseNumber "
                    "are written and work; parseStatement handles WRITELN "
                    "and assignment.",
        points=35,
        checker=lambda g: _core_parse_methods(g, 35),
        category="Parser",
    ),
    RubricItem(
        code="begin-end-blocks",
        description="Handles BEGIN/END blocks of statements.",
        points=8,
        checker=lambda g: _begin_end_blocks(g, 8),
        category="Parser",
    ),
    RubricItem(
        code="code-structure",
        description="Code is well-structured, modular, not repeated "
                    "unnecessarily (REVIEW).",
        points=8,
        checker=lambda g: _code_structure_review(g, 8),
        category="Quality",
    ),
    RubricItem(
        code="testing",
        description="Testing: works on parserTest0 through parserTest4.",
        points=15,
        checker=lambda g: _testing_row(g, 15),
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
            source_path=TESTS_DIR / f"{name}.txt",
            expected_stdout=list(meta["expected"]),
        ))
    return tests


# --------------------------------------------------------------------------- #
# LabConfig entry point
# --------------------------------------------------------------------------- #

def build_config(java_exe: str = "java",
                 javac_exe: str = "javac") -> LabConfig:
    return LabConfig(
        lab_name="Parser Lab",
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
        synthetic_tester_kind="parser",
    )
