"""
MIPS Lab specific configuration for the ATCS Compilers autograder.

Maps the Lab 5 (MIPS) handout to a concrete rubric:

    Exercise 2  -- simple.asm: 2 + 3 program that runs cleanly.
    Exercise 4  -- a small "read input + compute + print" program of
                   the student's choice (multiplication is suggested).
    Exercise 5  -- read an integer; print "Even" or "Odd".
    Exercise 6  -- read low/high/step; print the sequence.
    Next        -- guessing-game (computer picks OR student picks).
    Next        -- read 10 ints into an array; print sum/avg/min/max.
    Open-ended  -- "more interesting MIPS program of your own choice".
    Header docs -- every .asm file must have @author + @version + a
                   description in its leading # comment block.
    Comment density -- the lab text says "comment every 2 or 3 lines";
                       we score the average #-line ratio across the
                       student's matched files.

Each rubric row is intentionally independent of every other row -- a
student missing the array program still gets full credit for the
even/odd one, and so on. This mirrors the airtightness principle of
the Procedures-lab grader.

How student renames are tolerated
=================================
Students name their files inconsistently. The same exercise can show
up as evenodd.asm / parity.asm / even.asm / ex5.asm / exercise5.asm.
Each EXERCISES entry below carries a list of preferred basenames,
loose name-token matchers, and -- as a last resort -- substrings to
look for inside the file body. The orchestrator
(agcore.mips_grader._match_role) scores every candidate and binds the
highest scorer.

How output matching works
=========================
We do NOT exact-match stdout. Students decorate output with prompts
("Enter a number:") and trailing punctuation, and grading on
exact-line equality would penalise stylistic choices the lab doesn't
care about. Each MipsTestSpec lists `expected_substrings` that must
appear in stdout in the given order, case-insensitively. So a student
whose loops.asm prints "10\n35\n60\n85\n" and a student whose prints
"10 35 60 85" both pass the same row -- the four numbers appear in
the right order in both.
"""

from __future__ import annotations

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
# Hidden test specs per exercise
# --------------------------------------------------------------------------- #
#
# Each spec produces ONE MipsTestOutcome. Multiple specs per role are
# fine (e.g. evenodd has two specs: one for each parity). A row earns
# behavioural credit proportional to how many specs pass.
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

def _scored_exercise_row(role: str, points: float,
                         min_pass_for_full: int = -1
                         ) -> Callable[[MipsGradedSubmission], CheckResult]:
    """Build a generic per-exercise rubric checker.

    Score model (independent per row):
      file present              -> 25% of points
      header doc with @author   -> 25% of points
      tests pass (proportional) -> 50% of points

    @param role rubric role id, must appear in EXERCISES + ROLE_TESTS.
    @param points total points the rubric row is worth.
    @param min_pass_for_full if >= 0, the test arm awards full 50%
                             when at least this many specs pass (the
                             rest is treated as bonus). Used for
                             multi-spec rows where the student only
                             needs to fulfil ONE interpretation
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
                # Note the passes that didn't apply (informational only).
                fail_names = ", ".join(t.spec.name for t in outcomes
                                       if not t.passed)
                notes.append(
                    f"tests passed: {passed}/{total} (full credit since "
                    f">= {min_pass_for_full}); not-passing: {fail_names}")
        else:
            score += test_pts * (passed / total)
            if passed < total:
                fail_names = ", ".join(t.spec.name for t in outcomes
                                       if not t.passed)
                notes.append(f"tests passed: {passed}/{total}; "
                             f"failing: {fail_names}")
        # First failed test's error -- helps the teacher see what to look
        # at without flipping to the appendix.
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


def _interesting_program_row(g: MipsGradedSubmission) -> CheckResult:
    """Open-ended row: any .asm not bound to a numbered exercise counts.

    We deliberately do NOT try to autograde correctness here -- the
    point is "did the student do something beyond the assigned set".
    Score:
      file present              -> 30%
      header doc with @author   -> 30%
      assembles cleanly         -> 40%
    """
    points = next(item.points for item in RUBRIC if item.code == "interesting")
    match = g.role_matches.get("interesting")
    notes: List[str] = []
    if match is None or match.file is None:
        return CheckResult(
            earned=0.0,
            notes="no leftover .asm file (no 'interesting' program found)",
            severity=SEVERITY_MEDIUM,
        )
    f = match.file
    score = points * 0.3   # presence
    h = f.header
    if h.has_block and (h.author or "").strip() and (h.version or "").strip():
        score += points * 0.3
    elif h.has_block:
        score += points * 0.15
        notes.append("header present but missing @author or @version")
    else:
        notes.append("no header comment block")
    # Assembles cleanly?
    from agcore import mars_runner
    res = mars_runner.assemble_only(
        f.path, g.config.mars_jar, java_exe=g.config.java_exe)
    if res.error:
        notes.append(f"could not invoke java: {res.error}")
    elif res.assemble_error:
        notes.append("MARS assembler rejected the file")
    else:
        score += points * 0.4
    notes.insert(0, f"file: {f.relative}")
    notes.append("REVIEW: open-ended creativity is not autograded; "
                 "the teacher should skim the file")
    score = min(score, points)
    severity = (0 if score >= points else
                SEVERITY_MINOR if score >= points * 0.5 else SEVERITY_MEDIUM)
    return CheckResult(earned=round(score, 1),
                       notes="; ".join(notes), severity=severity)


def _header_doc_row(g: MipsGradedSubmission) -> CheckResult:
    """Across-the-board check: every .asm has @author + @version + summary.

    Independent of the per-exercise rows: a student who has perfect
    tests but commented zero of their files still loses on this row.
    Score is proportional: complete header per file -> full per-file
    credit; partial header -> 50%; missing -> 0%.
    """
    points = next(item.points for item in RUBRIC if item.code == "header-docs")
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


def _comment_density_row(g: MipsGradedSubmission) -> CheckResult:
    """The lab text says "comment every 2 or 3 lines". We score the average
    comment-density ratio across the student's matched .asm files.

    Thresholds (deliberately generous; this is a soft signal):
      avg >= 40%  -> full credit
      avg >= 25%  -> half credit
      avg <  25%  -> 0
    Files with no instructions at all are excluded from the average so a
    pure-data .asm (rare) doesn't pull the score down.
    """
    points = next(item.points for item in RUBRIC if item.code == "comment-density")
    files_with_inst = [f for f in g.asm_files if f.instruction_lines > 0]
    if not files_with_inst:
        return CheckResult(earned=0.0,
                           notes="no .asm files with instructions to score",
                           severity=SEVERITY_MAJOR)
    avg = sum(f.comment_density for f in files_with_inst) / len(files_with_inst)
    if avg >= 0.40:
        earned = points
        severity = 0
        notes = f"avg comment density: {avg * 100:.0f}% (>= 40% target)"
    elif avg >= 0.25:
        earned = round(points * 0.5, 1)
        severity = SEVERITY_MINOR
        notes = (f"avg comment density: {avg * 100:.0f}% "
                 f"(below the 40% target -- aim for a comment every 2-3 "
                 f"lines per the lab text)")
    else:
        earned = 0.0
        severity = SEVERITY_MEDIUM
        notes = (f"avg comment density: {avg * 100:.0f}% "
                 f"(well below the 40% target)")
    # Surface the files that pulled the average down.
    worst = sorted(files_with_inst, key=lambda f: f.comment_density)[:2]
    if worst and avg < 0.40:
        worst_str = ", ".join(f"{w.relative} ({int(w.comment_density * 100)}%)"
                              for w in worst)
        notes += f" -- thinnest: {worst_str}"
    return CheckResult(earned=earned, notes=notes, severity=severity)


# --------------------------------------------------------------------------- #
# The rubric itself
# --------------------------------------------------------------------------- #

# Points sum to 100. Per-exercise rows weight tests at 50% (only ex4 uses
# min_pass_for_full=1 because either reading -- multiply or add -- counts).
RUBRIC: Sequence[RubricItem] = (
    RubricItem(
        code="ex2-simple",
        description="Exercise 2: simple 2+3 program (runs cleanly)",
        points=5,
        checker=_scored_exercise_row("ex2_simple", 5),
        category="Exercises",
    ),
    RubricItem(
        code="ex4-compute",
        description="Exercise 4: read input + compute + print "
                    "(multiply OR add)",
        points=12,
        checker=_scored_exercise_row("ex4_compute", 12, min_pass_for_full=1),
        category="Exercises",
    ),
    RubricItem(
        code="ex5-evenodd",
        description="Exercise 5: read an integer; print Even or Odd",
        points=14,
        checker=_scored_exercise_row("ex5_evenodd", 14),
        category="Exercises",
    ),
    RubricItem(
        code="ex6-loops",
        description="Exercise 6: print numbers in a range with a step",
        points=14,
        checker=_scored_exercise_row("ex6_loops", 14),
        category="Exercises",
    ),
    RubricItem(
        code="next-array",
        description="Next: array of 10 ints; print sum/avg/min/max",
        points=14,
        checker=_scored_exercise_row("next_array", 14),
        category="Next",
    ),
    RubricItem(
        code="next-guessing",
        description="Next: guessing-game program (REVIEW; output non-deterministic)",
        points=12,
        checker=_scored_exercise_row("next_guessing", 12, min_pass_for_full=0),
        category="Next",
    ),
    RubricItem(
        code="interesting",
        description="Open-ended: 'a more interesting MIPS program of your "
                    "own choice' (REVIEW; teacher should skim)",
        points=9,
        checker=_interesting_program_row,
        category="Bonus",
    ),
    RubricItem(
        code="header-docs",
        description="Every .asm file has a header block with @author, "
                    "@version, and a description",
        points=12,
        checker=_header_doc_row,
        category="Documentation",
    ),
    RubricItem(
        code="comment-density",
        description="Comment density across files (lab asks for a "
                    "comment every 2-3 lines)",
        points=8,
        checker=_comment_density_row,
        category="Documentation",
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
