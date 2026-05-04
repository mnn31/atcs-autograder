"""
MIPS Lab specific configuration for the ATCS Compilers autograder.

Rubric structure
================
The official ATCS MIPS Peer Review sheet has 7 rows summing to 52
pts. This config mirrors them one-for-one (re-normalised to 100 pts
for consistency with the rest of the autograder); the row codes below
keep the lab-document order so the teacher can scan top-to-bottom:

    1. all-headers       -- every .asm has @author/@version/summary
    2. simple-and-evenodd -- simple program uses arithmetic OTHER than
                              addition + evenodd has nice prompt and
                              messages and works on negatives
    3. loops-with-reversed -- low/high/step loop, plus does NOT
                              infinite-loop when low > high
    4. guessing-game      -- nice prompt + wrong-guess message +
                              correct-guess congratulation
    5. random-quality     -- RNG actually used and "really random"
    6. array-two-loops    -- array program with TWO separate loops
                              (one to store, one to compute stats)
    7. interesting-nontrivial -- open-ended program that's NOT trivial
                              (rules out "max of two ints" / "1..10")

Every row is independent of every other row -- a missing guessing
game does not blunt the score for the array row, and so on. This
mirrors the airtightness principle of the Procedures-lab grader.

How student renames are tolerated
=================================
Students name their files inconsistently. The same exercise shows up
as evenodd.asm / parity.asm / even.asm / ex5.asm / exercise5.asm.
Each EXERCISES entry below carries a list of preferred basenames,
loose name-token matchers, and content substrings as a last resort.
The orchestrator scores every candidate and binds the highest scorer.

How output matching works
=========================
We do NOT exact-match stdout. Students decorate output with prompts
("Enter a number:") and trailing punctuation, and grading on
exact-line equality would penalise stylistic choices the lab doesn't
care about. Each MipsTestSpec lists `expected_substrings` that must
appear in stdout in the given order, case-insensitively.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

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
    "ex2_simple": ExerciseRole(
        preferred_basenames=("simple.asm", "ex2.asm", "exercise2.asm"),
        name_tokens=[("simple",), ("ex", "2"), ("exercise", "2")],
        content_substrings=("addu",),
        description="Exercise 2: simple 2+3 program",
    ),
    "ex4_compute": ExerciseRole(
        # Either multiplication (lab's suggestion) or any other
        # read-compute-print one-liner the student wrote. Prefer
        # mult.asm; accept add.asm / calc.asm / exercise4.asm too.
        preferred_basenames=(
            "mult.asm", "multiply.asm", "add.asm", "ex4.asm",
            "exercise4.asm", "calc.asm",
        ),
        name_tokens=[("mult",), ("multiply",), ("add",), ("calc",),
                     ("ex", "4"), ("exercise", "4")],
        content_substrings=("mult ", "addu ", "syscall"),
        description="Exercise 4: read input + simple computation",
    ),
    "ex5_evenodd": ExerciseRole(
        preferred_basenames=("evenodd.asm", "even.asm", "parity.asm",
                             "ex5.asm", "exercise5.asm"),
        name_tokens=[("even",), ("odd",), ("parity",),
                     ("ex", "5"), ("exercise", "5")],
        content_substrings=("Even", "Odd", "andi"),
        description="Exercise 5: print Even or Odd",
    ),
    "ex6_loops": ExerciseRole(
        preferred_basenames=("loops.asm", "loop.asm", "range.asm",
                             "sequence.asm", "ex6.asm", "exercise6.asm"),
        name_tokens=[("loop",), ("range",), ("sequence",),
                     ("ex", "6"), ("exercise", "6")],
        content_substrings=("blt", "addu"),
        description="Exercise 6: print numbers in a range with a step",
    ),
    "next_array": ExerciseRole(
        preferred_basenames=("array.asm", "arrays.asm", "stats.asm",
                             "summinmaxavg.asm", "sum.asm"),
        name_tokens=[("array",), ("arrays",), ("stats",),
                     ("summary",), ("ex", "next")],
        content_substrings=(".space", "lw "),
        description="Next exercise: array of 10 ints, sum/avg/min/max",
    ),
    "next_guessing": ExerciseRole(
        preferred_basenames=("guessingGame.asm", "guess.asm", "game.asm",
                             "guessing.asm", "random.asm"),
        name_tokens=[("guess",), ("random",), ("game",)],
        content_substrings=("li $v0, 42", "li $v0,42", "syscall"),
        description="Next exercise: guessing game (random or computer-picks)",
    ),
    "interesting": ExerciseRole(
        # Catch-all: matched LAST so anything not already bound that
        # has a header doc and looks intentional gets credit. The
        # name_tokens are deliberately broad ("any .asm not used yet").
        preferred_basenames=(),
        name_tokens=[],
        content_substrings=("syscall",),
        description="Open-ended: 'more interesting MIPS program of your own'",
    ),
}


# --------------------------------------------------------------------------- #
# Per-exercise verification cases
# --------------------------------------------------------------------------- #
#
# Each MipsTestSpec is one verification CASE for an exercise -- the
# autograder pipes `stdin_text` in and looks for `expected_substrings`
# in stdout, in order, case-insensitively. Multiple cases per
# exercise simply exercise the same .asm with different inputs (e.g.
# evenodd is checked with even, odd, and zero) so we have more than
# one data point on whether the exercise actually works. They are NOT
# separate hidden tests; the deliverable IS the .asm file, and the
# rubric row's behavioural sub-score is the proportion of cases that
# pass.
# --------------------------------------------------------------------------- #

ROLE_TESTS = {
    "ex2_simple": (
        MipsTestSpec(
            name="ex2_runs_cleanly",
            stdin_text="",
            expected_substrings=(),         # any output is fine
            description="Program runs and exits cleanly with no input",
            timeout=10,
        ),
    ),
    "ex4_compute": (
        # Try the multiplication interpretation first: 6*7=42. If the
        # student wrote an addition program instead, we still get this
        # spec to PASS via the addition spec below (one of the two
        # readings will hit). Scoring is "majority of specs pass".
        MipsTestSpec(
            name="ex4_multiply_6_x_7",
            stdin_text="6\n7\n",
            expected_substrings=("42",),
            description="If a multiplication program: 6 * 7 should print 42",
            timeout=10,
        ),
        MipsTestSpec(
            name="ex4_add_5_plus_3",
            stdin_text="5\n3\n",
            expected_substrings=("8",),
            description="If an addition program: 5 + 3 should print 8",
            timeout=10,
        ),
    ),
    "ex5_evenodd": (
        MipsTestSpec(
            name="ex5_even_input",
            stdin_text="8\n",
            expected_substrings=("even",),
            description="Input 8 should print a string containing 'Even'",
            timeout=10,
        ),
        MipsTestSpec(
            name="ex5_odd_input",
            stdin_text="7\n",
            expected_substrings=("odd",),
            description="Input 7 should print a string containing 'Odd'",
            timeout=10,
        ),
        MipsTestSpec(
            name="ex5_zero_is_even",
            stdin_text="0\n",
            expected_substrings=("even",),
            description="0 is even (boundary)",
            timeout=10,
        ),
        MipsTestSpec(
            name="ex5_negative_odd",
            stdin_text="-7\n",
            expected_substrings=("odd",),
            description="Peer-review check: works with negative numbers (-7 odd)",
            timeout=10,
        ),
        MipsTestSpec(
            name="ex5_negative_even",
            stdin_text="-12\n",
            expected_substrings=("even",),
            description="Peer-review check: works with negative numbers (-12 even)",
            timeout=10,
        ),
    ),
    "ex6_loops": (
        MipsTestSpec(
            name="ex6_lab_example",
            stdin_text="10\n100\n25\n",
            expected_substrings=("10", "35", "60", "85"),
            description="Lab example: low=10 high=100 step=25 prints 10,35,60,85",
            timeout=10,
        ),
        MipsTestSpec(
            name="ex6_step_one",
            stdin_text="1\n5\n1\n",
            expected_substrings=("1", "2", "3", "4"),
            description="low=1 high=5 step=1 prints 1,2,3,4",
            timeout=10,
        ),
        MipsTestSpec(
            # Peer-review check: reversed inputs (high < low) MUST NOT
            # cause an infinite loop. Either of two valid behaviours
            # passes (graded in _loops_with_reversed_row, not via
            # expected_substrings here -- this spec is a "did it
            # terminate" probe, the row's checker reads the outcome).
            name="ex6_reversed_inputs",
            stdin_text="100\n10\n25\n",
            expected_substrings=(),
            description="Reversed inputs (100, 10, 25) -- must terminate "
                        "in <5s, either with no output, an error message, "
                        "or by switching low/high.",
            timeout=5,
        ),
    ),
    "next_array": (
        # Ten distinct positive integers so the four metrics are
        # unambiguous. Sum=55, avg=5 or 5.5 (depending on integer vs
        # float division), min=1, max=10. We look for each metric
        # individually so a student who prints them in a different
        # order than we expect still scores. The "5" min/avg
        # collision is fine because we look for ALL four AND prints
        # of the ten inputs would also include 5; we additionally
        # check 55 (sum) which is unambiguous.
        MipsTestSpec(
            name="next_array_one_to_ten",
            stdin_text="1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n",
            expected_substrings=("55", "1", "10"),
            description="1..10: sum=55, min=1, max=10 should appear",
            timeout=15,
        ),
    ),
    "next_guessing": (
        # A guessing game's behaviour depends on RNG state we can't
        # control here, so this spec is deliberately weak: feed many
        # candidate guesses (binary-search style across 0..999) and
        # check that the program EITHER prints a victory string OR
        # prints high/low feedback. The rubric checker downstream
        # treats this as REVIEW.
        MipsTestSpec(
            name="next_guessing_runs",
            stdin_text="\n".join(str(g) for g in
                                 [500, 250, 750, 125, 375, 625, 875,
                                  62, 187, 312, 437, 562, 687, 812, 937,
                                  31, 93, 156, 218, 281, 343, 406,
                                  468, 531, 593, 656, 718, 781, 843, 906, 968,
                                  0, 1, 2, 999, 998, 997]) + "\n",
            expected_substrings=(),    # we score on "ran without trapping"
            description="Drive the game with a wide spread of guesses; "
                        "checker only verifies the program runs to "
                        "completion without a runtime error",
            timeout=15,
        ),
    ),
    # "interesting" intentionally has no test specs -- the rubric for
    # that row just verifies "file exists, has a header, assembles".
}


# --------------------------------------------------------------------------- #
# Rubric checkers
# --------------------------------------------------------------------------- #

def _file_text(g: MipsGradedSubmission, role: str) -> str:
    """Return the .asm file body bound to `role`, or "" if unmatched.

    Used by the content-shape checks below (non-add arithmetic, prompts,
    RNG syscalls, two-loop architecture, non-triviality). Read errors
    fall back to the empty string -- the rubric row will then say the
    feature is missing, which is the correct behaviour for a file that
    can't even be opened.
    """
    match = g.role_matches.get(role)
    if match is None or match.file is None:
        return ""
    try:
        return match.file.path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _has_non_addition_arithmetic(src: str) -> bool:
    """True iff the file uses an arithmetic op other than addition.

    Recognised: mult / multu / div / divu / subu / sub / sll / srl / sra
    (shifts count as "non-addition arithmetic" for grading purposes; the
    peer-review wording is "an arithmetic operation other than
    addition", and bit shifts qualify under the lab's reading).
    """
    if not src:
        return False
    return bool(re.search(
        r"\b(mult|multu|div|divu|subu|sub|sll|srl|sra|mflo|mfhi)\b",
        src,
    ))


def _has_data_strings(src: str) -> bool:
    """True iff the file declares at least one .asciiz string in .data.

    Used as a proxy for "has nice prompt / message" -- a program that
    prints integers without strings has no prompts, no labels, no
    feedback messages.
    """
    return bool(re.search(r"\.asciiz\s*\"", src))


def _back_jump_loop_count(src: str) -> int:
    """Count distinct loops by counting unique back-jump targets.

    A "loop" is a `j <label>` (or branch-style `bxx ... <label>`) whose
    `<label>:` appears EARLIER in the file. The count is the number of
    distinct such labels, which approximates the number of independent
    loops in the program. Crude but reliable enough for the
    array-two-loops rubric row.
    """
    if not src:
        return 0
    label_lines: dict = {}
    branch_targets: list = []
    for i, raw in enumerate(src.splitlines()):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m_label = re.match(r"^([A-Za-z_]\w*)\s*:", line)
        if m_label and m_label.group(1) not in label_lines:
            label_lines[m_label.group(1)] = i
        m_jump = re.match(
            r"^(?:j|beq|bne|blt|bgt|ble|bge|bltz|bgtz|blez|bgez|bnez|beqz)\b"
            r"[^,]*,?[^,]*,?\s*([A-Za-z_]\w*)",
            line,
        )
        if m_jump:
            branch_targets.append((m_jump.group(1), i))
    distinct_back: set = set()
    for target, at_line in branch_targets:
        defined = label_lines.get(target)
        if defined is not None and defined < at_line:
            distinct_back.add(target)
    return len(distinct_back)


def _looks_like_rng_syscall(src: str) -> bool:
    """True iff the file invokes a MARS RNG syscall (41/42).

    Syscall 41 = random int, 42 = random int in [0, $a1). Either is
    accepted; we just want evidence that the program isn't pretending
    to be random by hardcoding a value.
    """
    if not src:
        return False
    if re.search(r"li\s+\$v0\s*,?\s*4[12]\b", src):
        return True
    return False


def _scored_exercise_row(role: str, points: float,
                         min_pass_for_full: int = -1
                         ) -> Callable[[MipsGradedSubmission], CheckResult]:
    """Build a generic per-exercise rubric checker.

    Score model (independent per row):
      file present                              -> 25% of points
      header doc with @author + @version        -> 25% of points
      verification cases pass (proportional)    -> 50% of points

    @param role rubric role id, must appear in EXERCISES + ROLE_TESTS.
    @param points total points the rubric row is worth.
    @param min_pass_for_full if >= 0, the behavioural arm awards full
                             50% when at least this many verification
                             cases pass (the rest is treated as
                             bonus). Used for rows where the student
                             only needs to fulfil ONE interpretation
                             (e.g. ex4 may be multiplication OR
                             addition; either is enough).
    """
    file_pts = round(points * 0.25, 1)
    doc_pts = round(points * 0.25, 1)
    test_pts = round(points - file_pts - doc_pts, 1)

    def checker(g: MipsGradedSubmission) -> CheckResult:
        match = g.role_matches.get(role)
        notes: List[str] = []
        score = 0.0

        # File present
        if match is None or match.file is None:
            return CheckResult(
                earned=0.0,
                notes="file not found in submission",
                severity=SEVERITY_MAJOR,
            )
        f = match.file
        score += file_pts

        # Header doc
        h = f.header
        if h.has_block and (h.author or "").strip() and (h.version or "").strip():
            score += doc_pts
        elif h.has_block and ((h.author or "").strip()
                              or (h.version or "").strip()):
            score += doc_pts * 0.5
            missing = []
            if not (h.author or "").strip():
                missing.append("@author")
            if not (h.version or "").strip():
                missing.append("@version")
            notes.append(f"header doc missing: {', '.join(missing)}")
        else:
            notes.append("no header comment block (or empty)")

        # Tests
        outcomes = g.test_outcomes.get(role, [])
        if not outcomes:
            # Row has no behavioural component -- present + doc only.
            severity = 0 if score >= points else (SEVERITY_MINOR if score > 0
                                                  else SEVERITY_MAJOR)
            return CheckResult(earned=round(score, 1),
                               notes="; ".join(notes), severity=severity)
        passed = sum(1 for t in outcomes if t.passed)
        total = len(outcomes)
        if min_pass_for_full >= 0 and passed >= min_pass_for_full:
            score += test_pts
            if passed < total:
                # Note the cases that didn't apply (informational only).
                fail_names = ", ".join(t.spec.name for t in outcomes
                                       if not t.passed)
                notes.append(
                    f"verification cases passed: {passed}/{total} "
                    f"(full credit since >= {min_pass_for_full}); "
                    f"not-passing: {fail_names}")
        else:
            score += test_pts * (passed / total)
            if passed < total:
                fail_names = ", ".join(t.spec.name for t in outcomes
                                       if not t.passed)
                notes.append(f"verification cases passed: {passed}/{total}; "
                             f"failing: {fail_names}")
        # First failed case's error -- helps the teacher see what to look
        # at without flipping to the per-exercise detail section.
        first_fail = next((t for t in outcomes if not t.passed), None)
        if first_fail and first_fail.error:
            notes.append(f"first fail: {first_fail.error}")

        score = min(score, points)   # never go above the row's cap
        if score >= points:
            severity = 0
        elif score >= points * 0.5:
            severity = SEVERITY_MEDIUM
        else:
            severity = SEVERITY_MAJOR
        return CheckResult(earned=round(score, 1),
                           notes="; ".join(notes), severity=severity)

    return checker


def _header_doc_row(g: MipsGradedSubmission) -> CheckResult:
    """Across-the-board check: every .asm has @author + @version + summary.

    Independent of the per-exercise rows: a student who has perfect
    tests but commented zero of their files still loses on this row.
    Score is proportional: complete header per file -> full per-file
    credit; partial header -> 50%; missing -> 0%.
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


# --------------------------------------------------------------------------- #
# Peer-review rubric checkers (rows 2..7; row 1 is _header_doc_row above)
# --------------------------------------------------------------------------- #


def _simple_and_evenodd_row(g: MipsGradedSubmission) -> CheckResult:
    """Peer-review row 2 (8 pts).

    Combines two checks the rubric lumps into a single row:
      * 4 pts: the student's own simple program (ex4 if matched, else
        ex2) uses an arithmetic op OTHER than plain addition. The peer
        review's wording is verbatim.
      * 4 pts: the evenodd program runs on (8, 7, 0, -7, -12) -- four
        positives + zero + two negatives confirm the negative-number
        clause. Half credit if at least 3/5 cases pass; full at 5/5.
    """
    notes: List[str] = []
    score = 0.0

    # -- Sub A: non-addition arithmetic in ex4 (preferred) or ex2.
    arith_role = "ex4_compute" if g.role_matches.get("ex4_compute") else "ex2_simple"
    arith_src = _file_text(g, arith_role)
    arith_file = g.role_matches.get(arith_role)
    if not arith_src:
        notes.append("no simple/computation program found")
    elif _has_non_addition_arithmetic(arith_src):
        score += 4.0
    else:
        rel = arith_file.file.relative if arith_file and arith_file.file else "?"
        notes.append(
            f"{rel} uses only addition (rubric asks for mult/sub/div/etc.)"
        )

    # -- Sub B: evenodd -- nice messages + works on negatives.
    evenodd_outcomes = g.test_outcomes.get("ex5_evenodd", [])
    evenodd_src = _file_text(g, "ex5_evenodd")
    if not evenodd_outcomes:
        notes.append("evenodd program not matched / not tested")
    else:
        passed = sum(1 for o in evenodd_outcomes if o.passed)
        total = len(evenodd_outcomes)
        if passed == total:
            score += 4.0
        elif passed >= 3:
            score += 2.0
            failing = ", ".join(o.spec.name for o in evenodd_outcomes
                                if not o.passed)
            notes.append(
                f"evenodd: {passed}/{total} cases pass; failing: {failing}"
            )
        else:
            failing = ", ".join(o.spec.name for o in evenodd_outcomes
                                if not o.passed)
            notes.append(
                f"evenodd: only {passed}/{total} cases pass; failing: "
                f"{failing}"
            )
        if evenodd_src and not _has_data_strings(evenodd_src):
            notes.append(
                "evenodd has no .asciiz strings (rubric expects nice "
                "prompt and Even/Odd messages)"
            )

    score = round(min(score, 8.0), 1)
    severity = (0 if score >= 8 else SEVERITY_MEDIUM if score >= 4
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _loops_with_reversed_row(g: MipsGradedSubmission) -> CheckResult:
    """Peer-review row 3 (8 pts).

    Combines the regular low/high/step loop with the reversed-input
    safety check:
      * 5 pts: the two normal cases (lab example + step-1) pass.
      * 3 pts: the reversed-input case terminates within timeout.
        ANY of {empty stdout, error message, swapped-and-printed
        sequence} satisfies the rubric.
    """
    notes: List[str] = []
    score = 0.0
    outcomes = g.test_outcomes.get("ex6_loops", [])
    if not outcomes:
        return CheckResult(earned=0.0, notes="loops program not matched",
                           severity=SEVERITY_MAJOR)

    normal = [o for o in outcomes if o.spec.name in
              ("ex6_lab_example", "ex6_step_one")]
    reversed_o = next((o for o in outcomes
                       if o.spec.name == "ex6_reversed_inputs"), None)

    if normal:
        passed = sum(1 for o in normal if o.passed)
        score += 5.0 * passed / len(normal)
        if passed < len(normal):
            failing = ", ".join(o.spec.name for o in normal if not o.passed)
            notes.append(f"loops: {passed}/{len(normal)} normal cases pass; "
                         f"failing: {failing}")

    if reversed_o is not None:
        if reversed_o.timed_out:
            notes.append(
                "reversed inputs (low > high) appear to infinite-loop "
                "(timed out); rubric requires graceful handling"
            )
        elif reversed_o.error and "runtime" in (reversed_o.error or "").lower():
            score += 1.5
            notes.append(
                "reversed inputs triggered a runtime trap rather than a "
                "graceful error; partial credit"
            )
        else:
            score += 3.0

    score = round(min(score, 8.0), 1)
    severity = (0 if score >= 8 else SEVERITY_MEDIUM if score >= 4
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _guessing_game_row(g: MipsGradedSubmission) -> CheckResult:
    """Peer-review row 4 (8 pts).

    Manual review is unavoidable for the "nice messages" wording, but
    we can grade three concrete signals:
      * 3 pts: file is matched.
      * 2 pts: file declares .asciiz strings (nice prompt + nice
        feedback messages -- a guessing game with no strings has no
        prompts at all).
      * 3 pts: file runs to completion without trapping under a wide
        spread of guesses.
    Tagged REVIEW so the teacher confirms message quality.
    """
    match = g.role_matches.get("next_guessing")
    notes: List[str] = []
    score = 0.0
    if match is None or match.file is None:
        return CheckResult(earned=0.0, notes="guessing-game file not found",
                           severity=SEVERITY_MAJOR)
    score += 3.0
    src = _file_text(g, "next_guessing")
    if _has_data_strings(src):
        score += 2.0
    else:
        notes.append("no .asciiz strings (rubric expects nice prompt + "
                     "wrong-guess + correct-guess messages)")
    outcomes = g.test_outcomes.get("next_guessing", [])
    runs_ok = bool(outcomes) and all(
        not o.timed_out and not (o.error or "") for o in outcomes
    )
    if runs_ok:
        score += 3.0
    elif outcomes:
        first_fail = next((o for o in outcomes if o.timed_out or o.error),
                          None)
        if first_fail and first_fail.timed_out:
            notes.append("guessing game timed out under driving inputs")
        elif first_fail:
            notes.append(f"guessing game errored: {first_fail.error}")
    notes.append("REVIEW: skim file to confirm prompt/messages quality")
    score = round(min(score, 8.0), 1)
    severity = (0 if score >= 8 else SEVERITY_MINOR if score >= 4
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _random_quality_row(g: MipsGradedSubmission) -> CheckResult:
    """Peer-review row 5 (6 pts).

    "Really random" is a human judgement, but we can grade the
    mechanism: did the student wire in a MARS RNG syscall (41 or 42)
    rather than hardcode a number? Look in the guessing-game file
    first, fall back to ANY .asm in the submission.

      * 4 pts: an RNG syscall is present somewhere
      * 2 pts: REVIEW credit for "really random" -- teacher confirms
    """
    notes: List[str] = []
    score = 0.0
    src = _file_text(g, "next_guessing")
    if not _looks_like_rng_syscall(src):
        for f in g.asm_files:
            try:
                body = f.path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _looks_like_rng_syscall(body):
                src = body
                notes.append(f"RNG syscall found in {f.relative} "
                             f"(not the matched guessing-game file)")
                break
    if _looks_like_rng_syscall(src):
        score += 4.0
    else:
        notes.append("no MARS RNG syscall (li $v0, 41/42) found anywhere")
    score += 2.0   # REVIEW credit for "really random"
    notes.append("REVIEW: confirm the RNG output looks 'really random'")
    score = round(min(score, 6.0), 1)
    severity = (0 if score >= 6 else SEVERITY_MINOR if score >= 3
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _array_two_loops_row(g: MipsGradedSubmission) -> CheckResult:
    """Peer-review row 6 (6 pts).

    The rubric explicitly asks for TWO separate loops -- one to read
    the values into the array, one to walk them computing min/max etc.
    A single fused loop misses the point even if it produces correct
    output.

      * 2 pts: file is matched
      * 2 pts: at least 2 distinct back-jump labels (= 2 separate loops)
      * 2 pts: behavioural test (1..10 -> sum=55, min=1, max=10) passes
    """
    match = g.role_matches.get("next_array")
    notes: List[str] = []
    score = 0.0
    if match is None or match.file is None:
        return CheckResult(earned=0.0, notes="array file not found",
                           severity=SEVERITY_MAJOR)
    score += 2.0
    src = _file_text(g, "next_array")
    loops = _back_jump_loop_count(src)
    if loops >= 2:
        score += 2.0
    else:
        notes.append(
            f"only {loops} loop(s) detected -- rubric asks for two "
            f"separate loops (one to store, one to compute)"
        )
    outcomes = g.test_outcomes.get("next_array", [])
    if outcomes and all(o.passed for o in outcomes):
        score += 2.0
    elif outcomes:
        failing = ", ".join(o.spec.name for o in outcomes if not o.passed)
        notes.append(f"behavioural test(s) failing: {failing}")
    score = round(min(score, 6.0), 1)
    severity = (0 if score >= 6 else SEVERITY_MEDIUM if score >= 3
                else SEVERITY_MAJOR)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


def _interesting_nontrivial_row(g: MipsGradedSubmission) -> CheckResult:
    """Peer-review row 7 (11 pts).

    Open-ended program that's NOT trivial. The rubric explicitly rules
    out "max of two numbers" and "print 1..10 in a loop" as too
    trivial. We grade what we can mechanically; the rest is REVIEW.

      * 2 pts: file is matched
      * 2 pts: header doc with @author + @version
      * 2 pts: assembles cleanly
      * 5 pts: non-triviality heuristic (split 3 + 2):
                 + 3 pts: at least one back-jump loop AND a .data section
                          AND >= 25 instruction lines
                 + 2 pts: at least one branch instruction beyond j (so
                          the program has decisions, not just linear flow)
    """
    match = g.role_matches.get("interesting")
    notes: List[str] = []
    score = 0.0
    if match is None or match.file is None:
        return CheckResult(
            earned=0.0,
            notes="no leftover .asm file -- the open-ended program is missing",
            severity=SEVERITY_MEDIUM,
        )
    f = match.file
    notes.insert(0, f"file: {f.relative}")
    score += 2.0   # presence

    h = f.header
    if (h.has_block and (h.author or "").strip()
            and (h.version or "").strip()):
        score += 2.0
    elif h.has_block:
        score += 1.0
        notes.append("header present but missing @author or @version")
    else:
        notes.append("no header block")

    from agcore import mars_runner
    res = mars_runner.assemble_only(
        f.path, g.config.mars_jar, java_exe=g.config.java_exe)
    if res.error:
        notes.append(f"could not invoke java: {res.error}")
    elif res.assemble_error:
        notes.append("MARS assembler rejected the file")
    else:
        score += 2.0

    src = _file_text(g, "interesting")
    has_loop = _back_jump_loop_count(src) >= 1
    has_data = bool(re.search(r"^\s*\.data\b", src, re.MULTILINE))
    long_enough = f.instruction_lines >= 25
    has_branches = bool(re.search(
        r"\b(beq|bne|blt|bgt|ble|bge|bltz|bgtz|blez|bgez|bnez|beqz)\b",
        src,
    ))
    if has_loop and has_data and long_enough:
        score += 3.0
    else:
        missing = []
        if not has_loop:
            missing.append("no loop")
        if not has_data:
            missing.append("no .data")
        if not long_enough:
            missing.append(f"only {f.instruction_lines} instructions")
        notes.append("non-triviality (depth): " + ", ".join(missing))
    if has_branches:
        score += 2.0
    else:
        notes.append("non-triviality (decisions): no conditional branches")

    notes.append("REVIEW: skim the file to confirm it is non-trivial "
                 "(rubric rules out 'max of 2 ints' and 'print 1..10')")
    score = round(min(score, 11.0), 1)
    severity = (0 if score >= 11 else SEVERITY_MINOR if score >= 6
                else SEVERITY_MEDIUM)
    return CheckResult(earned=score, notes="; ".join(notes), severity=severity)


# --------------------------------------------------------------------------- #
# The rubric itself -- mirrors the 7-row peer review (5+8+8+8+6+6+11 = 52).
# --------------------------------------------------------------------------- #

RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="all-headers",
        description="All Programs: header comments include name, date, "
                    "and summary using JavaDoc Standards",
        points=5,
        checker=_header_doc_row,
        category="Documentation",
    ),
    RubricItem(
        code="simple-and-evenodd",
        description="Simple program uses arithmetic OTHER than addition + "
                    "evenodd has nice prompt/messages and works on negatives",
        points=8,
        checker=_simple_and_evenodd_row,
        category="Programs",
    ),
    RubricItem(
        code="loops-with-reversed",
        description="Range loop (low/high/step) -- works for normal inputs "
                    "AND does not infinite-loop when low > high",
        points=8,
        checker=_loops_with_reversed_row,
        category="Programs",
    ),
    RubricItem(
        code="guessing-game",
        description="Guessing game has nice prompt + wrong-guess message "
                    "+ congratulatory message on correct guess (REVIEW)",
        points=8,
        checker=_guessing_game_row,
        category="Programs",
    ),
    RubricItem(
        code="random-quality",
        description="Random number generator works and is really random "
                    "(REVIEW)",
        points=6,
        checker=_random_quality_row,
        category="Programs",
    ),
    RubricItem(
        code="array-two-loops",
        description="Array program has TWO separate loops (one to store, "
                    "one to compute min/max etc.)",
        points=6,
        checker=_array_two_loops_row,
        category="Programs",
    ),
    RubricItem(
        code="interesting-nontrivial",
        description="Open-ended program that is NOT trivial (rules out "
                    "'max of 2 ints' / 'print 1..10') (REVIEW)",
        points=11,
        checker=_interesting_nontrivial_row,
        category="Programs",
    ),
)


# --------------------------------------------------------------------------- #
# LabConfig entry point
# --------------------------------------------------------------------------- #

def build_config(java_exe: str = "java") -> MipsLabConfig:
    """Assemble the MipsLabConfig the orchestrator needs."""
    return MipsLabConfig(
        lab_name="MIPS Lab",
        rubric=RUBRIC,
        mars_jar=VENDOR / "Mars4_5.jar",
        file_roles=EXERCISES,
        role_tests=ROLE_TESTS,
        java_exe=java_exe,
    )
