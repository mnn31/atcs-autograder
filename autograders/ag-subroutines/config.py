"""
Subroutines Lab specific configuration for the ATCS Compilers autograder.

Rubric structure
================
The official ATCS Subroutines Peer Review sheet has 6 rows summing to
85 pts. This config mirrors them one-for-one (re-normalised to a
percent on the report just like the other labs); the row codes keep
the lab-document order so the teacher can scan top-to-bottom:

    1. all-headers   -- every .asm has @author/@version/summary       (10)
    2. max2          -- nice prompt + nice message + negatives        (10)
    3. max3          -- prompt + message + calls max2 + negatives     (10)
    4. fact          -- recursive + pushes/pops stack + prints right  (15)
    5. fib           -- implemented and works well                    (20)
    6. linkedlist    -- linked list (heap or stack) -- REVIEW         (20)

Every row is independent -- a missing fib doesn't blunt the score for
max2, and a missing linked list doesn't blunt fact. Same airtightness
principle as the rest of the autograder.

How student renames are tolerated
=================================
Students name their files inconsistently. max2 shows up as
max2.asm / maxoftwo.asm / maximum2.asm / ex_max2.asm. Each EXERCISES
entry below carries a list of preferred basenames, loose name-token
matchers, and content substrings as a last resort. The orchestrator
scores every candidate and binds the highest scorer.

How output matching works
=========================
We do NOT exact-match stdout. Students decorate output with prompts
("Enter first integer:") and trailing punctuation. Each MipsTestSpec
lists `expected_substrings` that must appear in stdout in the given
order, case-insensitively.

Subroutine-specific signals
===========================
The peer rubric calls out specific structural features that go beyond
"the program produces the right output":

  * max3 must call max2 via jal rather than re-comparing locally.
  * fact must be recursive AND must push/pop $ra via the stack.
  * fib is graded primarily on behaviour but recursion+stack are
    natural for it (same shape as fact).
  * The linked list row is a CIRCLE-APPLICABLE row -- the peer
    reviewer marks heap-or-stack. We detect which approach the
    student used (syscall 9 -> heap, $sp manipulation in node
    context -> stack) and tag the row REVIEW.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, List, Sequence

from agcore.mips_grader import (ExerciseRole, MipsGradedSubmission,
                                MipsLabConfig, MipsTestSpec)
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
# Exercise -> file matching
# --------------------------------------------------------------------------- #

EXERCISES = {
    "sub_max2": ExerciseRole(
        preferred_basenames=("max2.asm", "maximum2.asm", "maxoftwo.asm",
                             "maximumof2.asm", "maximumOfTwo.asm"),
        name_tokens=[("max", "2"), ("maximum", "2"), ("max", "two"),
                     ("maximum", "two")],
        content_substrings=("max2:",),
        description="Subroutine max2 (maximum of two ints)",
    ),
    "sub_max3": ExerciseRole(
        preferred_basenames=("max3.asm", "maximum3.asm", "maxofthree.asm",
                             "maximumof3.asm", "maximumOfThree.asm"),
        name_tokens=[("max", "3"), ("maximum", "3"), ("max", "three"),
                     ("maximum", "three")],
        content_substrings=("max3:", "jal max2"),
        description="Subroutine max3 (maximum of three ints; calls max2)",
    ),
    "sub_fact": ExerciseRole(
        preferred_basenames=("fact.asm", "factorial.asm"),
        name_tokens=[("fact",), ("factorial",)],
        content_substrings=("fact:", "factorial:"),
        description="Subroutine fact (recursive factorial)",
    ),
    "sub_fib": ExerciseRole(
        preferred_basenames=("fib.asm", "fibonacci.asm"),
        name_tokens=[("fib",), ("fibonacci",)],
        content_substrings=("fib:", "fibonacci:"),
        description="Subroutine fib (recursive Fibonacci)",
    ),
    "sub_linkedlist": ExerciseRole(
        # The lab makes newlistnode optional but expects sumlist as the
        # main deliverable. Match on either name.
        preferred_basenames=("sumlist.asm", "linkedlist.asm",
                             "linked_list.asm", "list.asm",
                             "newlistnode.asm", "ll.asm"),
        name_tokens=[("sumlist",), ("list",), ("link",), ("node",),
                     ("newlist",)],
        content_substrings=("sumlist:", "newlistnode:", "newListNode:"),
        description="Linked-list subroutine(s): newlistnode and/or sumlist",
    ),
}


# --------------------------------------------------------------------------- #
# Per-subroutine verification cases
# --------------------------------------------------------------------------- #
#
# Each MipsTestSpec drives the student's program with `stdin_text` and
# looks for `expected_substrings` in stdout (in order, case-insensitively).
# The student's driver in each file is expected to prompt for the
# subroutine's inputs and print its return value -- which is exactly
# what the peer-review rubric demands ("nice prompt for accepting input
# from user and has a nice message to display ...").
# --------------------------------------------------------------------------- #

ROLE_TESTS = {
    "sub_max2": (
        MipsTestSpec(
            name="max2_basic",
            stdin_text="5\n8\n",
            expected_substrings=("8",),
            description="max2(5, 8) -> 8",
            timeout=10,
        ),
        MipsTestSpec(
            name="max2_first_bigger",
            stdin_text="42\n7\n",
            expected_substrings=("42",),
            description="max2(42, 7) -> 42 (first arg wins)",
            timeout=10,
        ),
        MipsTestSpec(
            name="max2_negatives",
            stdin_text="-3\n-7\n",
            expected_substrings=("-3",),
            description="Peer-review: works with negatives. max2(-3, -7) -> -3",
            timeout=10,
        ),
        MipsTestSpec(
            name="max2_mixed_sign",
            stdin_text="-5\n3\n",
            expected_substrings=("3",),
            description="max2(-5, 3) -> 3 (mixed signs)",
            timeout=10,
        ),
    ),
    "sub_max3": (
        MipsTestSpec(
            name="max3_middle",
            stdin_text="1\n9\n4\n",
            expected_substrings=("9",),
            description="max3(1, 9, 4) -> 9",
            timeout=10,
        ),
        MipsTestSpec(
            name="max3_last",
            stdin_text="2\n5\n11\n",
            expected_substrings=("11",),
            description="max3(2, 5, 11) -> 11 (last arg wins)",
            timeout=10,
        ),
        MipsTestSpec(
            name="max3_first",
            stdin_text="100\n2\n5\n",
            expected_substrings=("100",),
            description="max3(100, 2, 5) -> 100 (first arg wins)",
            timeout=10,
        ),
        MipsTestSpec(
            name="max3_negatives",
            stdin_text="-1\n-5\n-3\n",
            expected_substrings=("-1",),
            description="Peer-review: works with negatives. "
                        "max3(-1, -5, -3) -> -1",
            timeout=10,
        ),
    ),
    "sub_fact": (
        # The peer rubric says "works with positive numbers greater than 0",
        # so we focus on n>=1. fact(0)==1 is mathematically correct but
        # the rubric doesn't require it; we don't penalise either way.
        MipsTestSpec(
            name="fact_one",
            stdin_text="1\n",
            expected_substrings=("1",),
            description="fact(1) -> 1 (base of recursion)",
            timeout=10,
        ),
        MipsTestSpec(
            name="fact_three",
            stdin_text="3\n",
            expected_substrings=("6",),
            description="fact(3) -> 6",
            timeout=10,
        ),
        MipsTestSpec(
            name="fact_five",
            stdin_text="5\n",
            expected_substrings=("120",),
            description="fact(5) -> 120",
            timeout=10,
        ),
        MipsTestSpec(
            name="fact_seven",
            stdin_text="7\n",
            expected_substrings=("5040",),
            description="fact(7) -> 5040",
            timeout=15,
        ),
    ),
    "sub_fib": (
        MipsTestSpec(
            name="fib_zero",
            stdin_text="0\n",
            expected_substrings=("0",),
            description="fib(0) -> 0",
            timeout=10,
        ),
        MipsTestSpec(
            name="fib_one",
            stdin_text="1\n",
            expected_substrings=("1",),
            description="fib(1) -> 1",
            timeout=10,
        ),
        MipsTestSpec(
            name="fib_six",
            stdin_text="6\n",
            expected_substrings=("8",),
            description="fib(6) -> 8",
            timeout=10,
        ),
        MipsTestSpec(
            name="fib_ten",
            stdin_text="10\n",
            expected_substrings=("55",),
            description="fib(10) -> 55",
            timeout=15,
        ),
        MipsTestSpec(
            name="fib_fifteen",
            stdin_text="15\n",
            expected_substrings=("610",),
            description="fib(15) -> 610",
            timeout=20,
        ),
    ),
    # sub_linkedlist intentionally has no behavioural specs -- list
    # construction depends on the student's driver shape (do they
    # build a fixed list? do they prompt for elements?) and there's
    # no rubric-defined input contract. The row is graded by file
    # presence + heap-vs-stack detection + REVIEW.
}


# --------------------------------------------------------------------------- #
# Source-shape detectors
# --------------------------------------------------------------------------- #

def _file_text(g: MipsGradedSubmission, role: str) -> str:
    """Return the .asm file body bound to `role`, or "" if unmatched.

    Read errors fall back to the empty string -- the rubric row will
    then say the feature is missing, which is the correct behaviour
    for a file that can't even be opened.
    """
    match = g.role_matches.get(role)
    if match is None or match.file is None:
        return ""
    try:
        return match.file.path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _has_data_strings(src: str) -> bool:
    """True iff the file declares at least one .asciiz string.

    Used as a proxy for "has nice prompt / nice message" -- a program
    that prints integers without strings has no prompts, no labels, no
    feedback messages.
    """
    return bool(re.search(r"\.asciiz\s*\"", src))


def _calls_subroutine(src: str, target: str) -> bool:
    """True iff `jal target` appears somewhere in src (case-insensitive)."""
    if not src:
        return False
    return bool(re.search(rf"\bjal\s+{re.escape(target)}\b", src,
                          flags=re.IGNORECASE))


def _is_recursive(src: str, label: str) -> bool:
    """True iff `<label>:` is defined AND `jal <label>` appears somewhere
    in the file -- the subroutine calls itself by name.

    A precise body-slice approach is fragile because real students use
    intermediate local labels inside a recursive subroutine
    (`fact_rec:`, `fact_base:`, ...) and a slice from `fact:` to "the
    next top-level label" would clip the recursive call out. Looking
    for *any* `jal fact` in a file that defines `fact:` gives almost
    no false positives in practice -- there's no reason a non-recursive
    routine in a file named fact.asm would say `jal fact`.
    """
    if not src:
        return False
    label_def = re.compile(rf"^\s*{re.escape(label)}\s*:",
                           flags=re.IGNORECASE | re.MULTILINE)
    if not label_def.search(src):
        return False
    return bool(re.search(rf"\bjal\s+{re.escape(label)}\b", src,
                          flags=re.IGNORECASE))


def _uses_stack(src: str) -> bool:
    """True iff the file does at least one stack push AND one pop.

    Recognises the canonical `subu $sp, $sp, 4 ; sw <reg>, ($sp)` push
    pattern and the matching `lw <reg>, ($sp) ; addu $sp, $sp, 4` pop.
    """
    if not src:
        return False
    has_push = bool(re.search(
        r"\b(subu|sub|addiu|addi)\s+\$sp\s*,", src))
    has_save_ra = bool(re.search(r"\bsw\s+\$ra\b", src))
    has_restore = bool(re.search(r"\blw\s+\$ra\b", src))
    has_pop = bool(re.search(r"\b(addu|add|addiu|addi)\s+\$sp\s*,", src))
    return (has_push and has_pop) or (has_save_ra and has_restore)


def _has_sbrk_heap_alloc(src: str) -> bool:
    """True iff the file invokes MARS syscall 9 (sbrk, heap allocation).

    syscall 9 with $a0 = size returns an address in $v0 -- the standard
    way to allocate heap memory for a ListNode.
    """
    if not src:
        return False
    return bool(re.search(r"li\s+\$v0\s*,?\s*9\b", src))


# --------------------------------------------------------------------------- #
# Rubric checkers
# --------------------------------------------------------------------------- #

def _header_doc_row(g: MipsGradedSubmission) -> CheckResult:
    """Row 1 (10 pts): every .asm has @author + @version + summary.

    Per-file proportional: complete header -> full per-file credit;
    partial -> 50%; missing -> 0.
    """
    points = next(item.points for item in RUBRIC if item.code == "all-headers")
    if not g.asm_files:
        return CheckResult(earned=0.0,
                           notes="no .asm files in submission",
                           severity=SEVERITY_MAJOR)
    per_file = points / len(g.asm_files)
    earned = 0.0
    issues: List[str] = []
    for f in g.asm_files:
        h = f.header
        if (h.has_block and (h.author or "").strip()
                and (h.version or "").strip()
                and h.description.strip()):
            earned += per_file
            continue
        if h.has_block and ((h.author or "").strip()
                            or (h.version or "").strip()):
            earned += per_file * 0.5
            missing = []
            if not (h.author or "").strip():
                missing.append("@author")
            if not (h.version or "").strip():
                missing.append("@version")
            if not h.description.strip():
                missing.append("description")
            issues.append(f"{f.relative}: missing {', '.join(missing)}")
        else:
            issues.append(f"{f.relative}: no header block")
    earned = round(min(earned, points), 1)
    severity = (0 if earned >= points
                else SEVERITY_MINOR if earned >= points * 0.66
                else SEVERITY_MEDIUM if earned >= points * 0.33
                else SEVERITY_MAJOR)
    notes = "; ".join(issues[:4]) + (" ..." if len(issues) > 4 else "")
    return CheckResult(earned=earned, notes=notes, severity=severity)


def _max2_row(g: MipsGradedSubmission) -> CheckResult:
    """Row 2 (10 pts): max2 with nice prompt/message, works on negatives.

      * 2 pts: file matched
      * 2 pts: file has .asciiz strings (prompts / messages)
      * 6 pts: test cases pass proportionally (includes negative case)
    """
    notes: List[str] = []
    score = 0.0
    match = g.role_matches.get("sub_max2")
    if match is None or match.file is None:
        return CheckResult(earned=0.0, notes="max2 file not found",
                           severity=SEVERITY_MAJOR)
    score += 2.0
    src = _file_text(g, "sub_max2")
    if _has_data_strings(src):
        score += 2.0
    else:
        notes.append("no .asciiz strings (rubric expects nice prompt + "
                     "nice 'greater of two' message)")
    outcomes = g.test_outcomes.get("sub_max2", [])
    if outcomes:
        passed = sum(1 for o in outcomes if o.passed)
        score += 6.0 * passed / len(outcomes)
        if passed < len(outcomes):
            failing = ", ".join(o.spec.name for o in outcomes if not o.passed)
            notes.append(f"max2 cases passed: {passed}/{len(outcomes)}; "
                         f"failing: {failing}")
    else:
        notes.append("no max2 verification cases ran")
    score = round(min(score, 10.0), 1)
    severity = (0 if score >= 10
                else SEVERITY_MEDIUM if score >= 5
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _max3_row(g: MipsGradedSubmission) -> CheckResult:
    """Row 3 (10 pts): max3 with prompts, calls max2, works on negatives.

      * 1 pt:  file matched
      * 1 pt:  has .asciiz strings (prompts / messages)
      * 3 pts: **calls max2 via jal** (the rubric explicitly forbids
               doing the comparison itself)
      * 5 pts: test cases pass proportionally (includes negative case)
    """
    notes: List[str] = []
    score = 0.0
    match = g.role_matches.get("sub_max3")
    if match is None or match.file is None:
        return CheckResult(earned=0.0, notes="max3 file not found",
                           severity=SEVERITY_MAJOR)
    score += 1.0
    src = _file_text(g, "sub_max3")
    if _has_data_strings(src):
        score += 1.0
    else:
        notes.append("no .asciiz strings (rubric expects nice prompt + "
                     "'greatest of three' message)")
    # Look for jal max2 either in the matched max3 file OR in any other
    # bound file -- a student who put max2 + max3 in the same file
    # should still be detected as "calls max2".
    calls_max2 = _calls_subroutine(src, "max2")
    if not calls_max2:
        # Try the max2 file too (some students put max3 in max2.asm).
        max2_src = _file_text(g, "sub_max2")
        if max2_src and _calls_subroutine(max2_src, "max2"):
            # If max3 lives in max2's file, the matched src above was
            # actually the max2 file. The max3 body is in there too;
            # just take the credit.
            calls_max2 = True
    if calls_max2:
        score += 3.0
    else:
        notes.append("could not find `jal max2` in max3 (rubric forbids "
                     "doing the 3-way comparison locally)")
    outcomes = g.test_outcomes.get("sub_max3", [])
    if outcomes:
        passed = sum(1 for o in outcomes if o.passed)
        score += 5.0 * passed / len(outcomes)
        if passed < len(outcomes):
            failing = ", ".join(o.spec.name for o in outcomes if not o.passed)
            notes.append(f"max3 cases passed: {passed}/{len(outcomes)}; "
                         f"failing: {failing}")
    else:
        notes.append("no max3 verification cases ran")
    score = round(min(score, 10.0), 1)
    severity = (0 if score >= 10
                else SEVERITY_MEDIUM if score >= 5
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _fact_row(g: MipsGradedSubmission) -> CheckResult:
    """Row 4 (15 pts): factorial -- recursive + uses stack + correct output.

      * 2 pts: file matched
      * 2 pts: header doc with @author + @version
      * 3 pts: **fact is recursive** (jal fact inside fact:)
      * 3 pts: **uses the stack** (sw $ra / lw $ra OR $sp manipulation)
      * 5 pts: test cases pass proportionally
    """
    notes: List[str] = []
    score = 0.0
    match = g.role_matches.get("sub_fact")
    if match is None or match.file is None:
        return CheckResult(earned=0.0, notes="fact file not found",
                           severity=SEVERITY_MAJOR)
    score += 2.0
    f = match.file
    h = f.header
    if (h.has_block and (h.author or "").strip()
            and (h.version or "").strip()):
        score += 2.0
    elif h.has_block:
        score += 1.0
        notes.append("header present but missing @author or @version")
    else:
        notes.append("no header block")
    src = _file_text(g, "sub_fact")
    # Accept either label ("fact:" or "factorial:")
    if _is_recursive(src, "fact") or _is_recursive(src, "factorial"):
        score += 3.0
    else:
        notes.append("could not find a recursive `jal fact` call inside the "
                     "fact subroutine (rubric requires recursion)")
    if _uses_stack(src):
        score += 3.0
    else:
        notes.append("could not find $ra-style stack push/pop (rubric "
                     "requires pushes and pops off the stack)")
    outcomes = g.test_outcomes.get("sub_fact", [])
    if outcomes:
        passed = sum(1 for o in outcomes if o.passed)
        score += 5.0 * passed / len(outcomes)
        if passed < len(outcomes):
            failing = ", ".join(o.spec.name for o in outcomes if not o.passed)
            notes.append(f"fact cases passed: {passed}/{len(outcomes)}; "
                         f"failing: {failing}")
    else:
        notes.append("no fact verification cases ran")
    score = round(min(score, 15.0), 1)
    severity = (0 if score >= 15
                else SEVERITY_MEDIUM if score >= 7
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _fib_row(g: MipsGradedSubmission) -> CheckResult:
    """Row 5 (20 pts): fibonacci -- implemented and works well.

    The peer rubric is short on fib; the natural shape is recursive
    with stack discipline, but we weight behaviour heavily here.

      * 3 pts: file matched
      * 2 pts: header doc with @author + @version
      * 2 pts: recursion detected (jal fib inside fib:)
      * 3 pts: stack usage detected
      * 10 pts: test cases pass proportionally
    """
    notes: List[str] = []
    score = 0.0
    match = g.role_matches.get("sub_fib")
    if match is None or match.file is None:
        return CheckResult(earned=0.0, notes="fib file not found",
                           severity=SEVERITY_MAJOR)
    score += 3.0
    f = match.file
    h = f.header
    if (h.has_block and (h.author or "").strip()
            and (h.version or "").strip()):
        score += 2.0
    elif h.has_block:
        score += 1.0
        notes.append("header present but missing @author or @version")
    else:
        notes.append("no header block")
    src = _file_text(g, "sub_fib")
    if _is_recursive(src, "fib") or _is_recursive(src, "fibonacci"):
        score += 2.0
    else:
        notes.append("could not find a recursive `jal fib` call (the lab "
                     "shows fib as a recursive routine)")
    if _uses_stack(src):
        score += 3.0
    else:
        notes.append("could not find $ra-style stack push/pop in fib")
    outcomes = g.test_outcomes.get("sub_fib", [])
    if outcomes:
        passed = sum(1 for o in outcomes if o.passed)
        score += 10.0 * passed / len(outcomes)
        if passed < len(outcomes):
            failing = ", ".join(o.spec.name for o in outcomes if not o.passed)
            notes.append(f"fib cases passed: {passed}/{len(outcomes)}; "
                         f"failing: {failing}")
    else:
        notes.append("no fib verification cases ran")
    score = round(min(score, 20.0), 1)
    severity = (0 if score >= 20
                else SEVERITY_MEDIUM if score >= 10
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _linkedlist_row(g: MipsGradedSubmission) -> CheckResult:
    """Row 6 (20 pts): linked list -- heap or stack. REVIEW.

    The peer-review wording is "Circle applicable - Linked List is /
    is not implemented using heap / stack". We can't fully verify list
    correctness mechanically, but we can detect the implementation
    approach (heap = syscall 9 / sbrk; stack = explicit $sp allocation
    in node-context) and surface which one the student picked.

      * 5 pts:  file matched
      * 3 pts:  header doc with @author + @version
      * 4 pts:  approach detectable (heap OR stack)
      * 4 pts:  file assembles cleanly under MARS
      * 4 pts:  REVIEW credit -- teacher confirms behaviour

    If the file is missing entirely the row scores 0 (linked list is
    not optional in the rubric -- only newlistnode is optional in the
    lab text, but the row is still on the sheet).
    """
    notes: List[str] = []
    score = 0.0
    match = g.role_matches.get("sub_linkedlist")
    if match is None or match.file is None:
        notes.append("REVIEW: confirm linked-list deliverable is genuinely "
                     "absent (not just renamed)")
        return CheckResult(earned=0.0,
                           notes="linked-list file not found; "
                                 + "; ".join(notes),
                           severity=SEVERITY_MEDIUM)
    score += 5.0
    f = match.file
    h = f.header
    if (h.has_block and (h.author or "").strip()
            and (h.version or "").strip()):
        score += 3.0
    elif h.has_block:
        score += 1.5
        notes.append("header present but missing @author or @version")
    else:
        notes.append("no header block")

    src = _file_text(g, "sub_linkedlist")
    if _has_sbrk_heap_alloc(src):
        score += 4.0
        notes.append("approach detected: HEAP (uses syscall 9 / sbrk)")
    elif _uses_stack(src):
        score += 4.0
        notes.append("approach detected: STACK ($sp allocation present)")
    else:
        notes.append("could not detect heap (syscall 9) or stack "
                     "allocation approach")

    # Quick assemble check -- a syntactically clean file is worth points
    # even though we don't drive it with stdin.
    from agcore import mars_runner
    res = mars_runner.assemble_only(
        f.path, g.config.mars_jar, java_exe=g.config.java_exe)
    if res.error:
        notes.append(f"could not invoke java: {res.error}")
    elif res.assemble_error:
        notes.append("MARS assembler rejected the file")
    else:
        score += 4.0

    score += 4.0   # REVIEW credit; teacher confirms list behaviour
    notes.append("REVIEW: skim the file to confirm list construction "
                 "and sumlist behave correctly")
    score = round(min(score, 20.0), 1)
    severity = (0 if score >= 20
                else SEVERITY_MINOR if score >= 12
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


# --------------------------------------------------------------------------- #
# The rubric itself -- mirrors the 6-row peer review (10+10+10+15+20+20 = 85)
# --------------------------------------------------------------------------- #

RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="all-headers",
        description="All Programs: comments include author name, date, "
                    "and purpose",
        points=10,
        checker=_header_doc_row,
        category="Documentation",
    ),
    RubricItem(
        code="max2",
        description="max2: nice prompt + nice message displaying the greater "
                    "of two numbers; works with negatives",
        points=10,
        checker=_max2_row,
        category="Subroutines",
    ),
    RubricItem(
        code="max3",
        description="max3: nice prompt + nice message; CALLS max2 (does not "
                    "do the comparison itself); works with negatives",
        points=10,
        checker=_max3_row,
        category="Subroutines",
    ),
    RubricItem(
        code="fact",
        description="Factorial: recursive, pushes/pops the stack effectively, "
                    "computes the right result and prints it",
        points=15,
        checker=_fact_row,
        category="Subroutines",
    ),
    RubricItem(
        code="fib",
        description="Fibonacci is implemented and works well",
        points=20,
        checker=_fib_row,
        category="Subroutines",
    ),
    RubricItem(
        code="linkedlist",
        description="Linked List implemented using heap or stack (REVIEW: "
                    "circle applicable -- is / is not, heap / stack)",
        points=20,
        checker=_linkedlist_row,
        category="Subroutines",
    ),
)


# --------------------------------------------------------------------------- #
# LabConfig entry point
# --------------------------------------------------------------------------- #

def build_config(java_exe: str = "java") -> MipsLabConfig:
    """Assemble the MipsLabConfig the orchestrator needs."""
    return MipsLabConfig(
        lab_name="Subroutines Lab",
        rubric=RUBRIC,
        mars_jar=VENDOR / "Mars4_5.jar",
        file_roles=EXERCISES,
        role_tests=ROLE_TESTS,
        java_exe=java_exe,
    )
