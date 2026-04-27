"""
Top-level MIPS-lab grading orchestrator.

Mirrors agcore/grader.py in shape but for MIPS submissions: a flat
folder of .asm files instead of a Compiler/ tree. The lab-specific
config builds an MipsLabConfig with a rubric of MipsRubricItem and a
list of MipsTestSpec; this orchestrator does the rest:

    1. extract the zip
    2. discover .asm files + parse their headers
    3. match each rubric "exercise role" to a student .asm file
    4. run MARS on each matched file with each test's stdin
    5. score every rubric item
    6. hand a MipsGradedSubmission to the report module

The MIPS path deliberately does NOT share the GradedSubmission /
LabConfig dataclasses with the Procedures path. Their inputs (Java
classes vs. .asm files), their compile model (whole-tree javac vs.
per-file MARS assemble), and their rubric checks (javadoc proximity
vs. output diffs) overlap too little to share a struct without a
mess of "if mips else procedures" branches in every checker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import asm_header_parser, extractor, mars_runner
from .rubric import CheckResult, GradedItem, RubricItem


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #


@dataclass
class MipsTestSpec:
    """One stdin/expected-substring pair to feed a MARS-run program.

    A rubric row can reference 0..N test specs. Each spec runs the
    student's .asm with `stdin_text` piped in and looks for every
    string in `expected_substrings` to appear in stdout, in order
    (case-insensitive). This relaxed matching is on purpose: students
    decorate output with prompts ("Enter a number: ", "Result is: ")
    and trailing punctuation, and grading on exact-line equality
    would penalise stylistic choices the lab doesn't care about.
    """

    name: str                           # short id for the appendix
    stdin_text: str = ""                # piped to MARS via JVM stdin
    expected_substrings: Sequence[str] = ()
    timeout: int = 10                   # wall-clock seconds
    description: str = ""               # human-readable for the PDF


@dataclass
class MipsTestOutcome:
    """Result of one MARS invocation against one MipsTestSpec."""

    spec: MipsTestSpec
    passed: bool
    stdout: str
    stderr: str
    error: str = ""                     # short reason for a failure
    timed_out: bool = False
    assemble_error: bool = False


@dataclass
class FileRoleMatch:
    """How a rubric exercise role got bound to a concrete .asm file.

    Stored on MipsGradedSubmission so the rubric checkers (and the
    PDF) can show which file they actually scored, and so multiple
    rubric rows that share an exercise (e.g. evenodd's pair of
    even/odd tests) reuse the same matched file without re-scanning.

    `score` and `reason` are diagnostic: if a role didn't match any
    file, FileRoleMatch.summary will hold a teacher-readable
    explanation (e.g. "no .asm file with 'array', 'sum', or 'mean' in
    the name and no leftover unused .asm with array-shaped contents").
    """

    role: str                                       # rubric role id
    file: Optional[asm_header_parser.AsmFileSummary]   # winning file or None
    score: int = 0                                  # heuristic score
    reason: str = ""                                # why we picked it


@dataclass
class MipsLabConfig:
    """Pluggable configuration the MIPS lab provides to this orchestrator."""

    lab_name: str
    rubric: Sequence[RubricItem]
    mars_jar: Path
    # role_id -> ExerciseRole describing how to match a student file
    file_roles: Dict[str, "ExerciseRole"] = field(default_factory=dict)
    # role_id -> tuple of MipsTestSpec to run against that role's file
    role_tests: Dict[str, Sequence[MipsTestSpec]] = field(default_factory=dict)
    java_exe: str = "java"


@dataclass
class ExerciseRole:
    """Filename-fuzzy spec for matching a student .asm file to a rubric row.

    @param preferred_basenames basenames the rubric expects to see most
                               often (e.g. "evenodd.asm", "even.asm").
    @param name_tokens any of these token sets in the basename's stem
                       counts as a match, lowercased. Example for
                       even/odd: [("even",), ("odd",), ("parity",)] --
                       a file named "ParityCheck.asm" still matches.
    @param content_substrings if no name match wins, look for any of
                              these substrings in the file body. Used
                              as a last resort so a student who named
                              their array file "ex7.asm" still gets it
                              matched as the array exercise.
    @param description short description used in the PDF when a row is
                       missing entirely.
    """

    preferred_basenames: Sequence[str] = ()
    name_tokens: Sequence[Sequence[str]] = ()
    content_substrings: Sequence[str] = ()
    description: str = ""


@dataclass
class MipsGradedSubmission:
    """Everything the renderer needs to draw a MIPS blanksheet."""

    config: MipsLabConfig
    submission: extractor.Submission
    asm_files: List[asm_header_parser.AsmFileSummary] = field(
        default_factory=list)
    role_matches: Dict[str, FileRoleMatch] = field(default_factory=dict)
    # role_id -> list of outcomes (one per spec on that role)
    test_outcomes: Dict[str, List[MipsTestOutcome]] = field(
        default_factory=dict)
    graded_items: List[GradedItem] = field(default_factory=list)
    # Fatal-environment notes (e.g. "java not found") shown at the top of
    # the report so the teacher knows why everything else is zero.
    environment_notes: List[str] = field(default_factory=list)

    # ---- helpers used by lab-specific checkers ---------------------------
    def file_for_role(
        self, role: str
    ) -> Optional[asm_header_parser.AsmFileSummary]:
        """Return the AsmFileSummary matched to `role`, or None."""
        match = self.role_matches.get(role)
        return match.file if match else None

    def outcomes_for_role(self, role: str) -> List[MipsTestOutcome]:
        """Return the list of test outcomes for `role` (empty if untested)."""
        return self.test_outcomes.get(role, [])

    @property
    def total_earned(self) -> float:
        return sum(g.earned for g in self.graded_items)

    @property
    def total_possible(self) -> float:
        return sum(g.item.points for g in self.graded_items)

    @property
    def percent(self) -> float:
        if self.total_possible <= 0:
            return 0.0
        return 100.0 * self.total_earned / self.total_possible


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #


def grade(zip_path: Path, config: MipsLabConfig,
          submission: Optional[extractor.Submission] = None
          ) -> MipsGradedSubmission:
    """Run the full MIPS grading pipeline on one student zip.

    @param zip_path path to the student submission zip.
    @param config MIPS lab configuration.
    @param submission optional pre-extracted submission (caller already
                      called extractor.extract_mips). Useful when the
                      caller wants to peek at @author for filenames
                      before grading.
    @return MipsGradedSubmission with every stage's results attached.
    @postcondition caller must eventually call graded.submission.cleanup().
    """
    if submission is None:
        submission = extractor.extract_mips(zip_path)
    asm_files = asm_header_parser.discover_asm_files(submission.compiler_root)

    graded = MipsGradedSubmission(
        config=config,
        submission=submission,
        asm_files=asm_files,
    )

    # Up-front sanity check: java available? If not, every MARS run will
    # fail with the same "could not run java" message, so we surface a
    # single clear environment note once and keep grading (file-presence
    # and header-doc rows still mean something without a working JVM).
    if not mars_runner.java_available(config.java_exe):
        graded.environment_notes.append(
            f"`{config.java_exe}` not found on PATH; MARS could not run. "
            "All execution-based rubric rows scored 0.")

    # Step 1: bind every rubric exercise role to a candidate .asm file.
    # Done up front so multiple rubric rows that share a role reuse the
    # same match instead of independently re-scoring every file.
    used_files: set = set()
    for role_id, role_spec in config.file_roles.items():
        match = _match_role(role_id, role_spec, asm_files, used_files)
        graded.role_matches[role_id] = match
        if match.file is not None:
            used_files.add(match.file.relative)

    # Step 2: run every test spec against the matched file for its role.
    # Each spec is isolated so a hang in test A doesn't poison test B.
    for role_id, specs in config.role_tests.items():
        match = graded.role_matches.get(role_id)
        outcomes: List[MipsTestOutcome] = []
        if match is None or match.file is None:
            graded.test_outcomes[role_id] = outcomes
            continue
        for spec in specs:
            outcomes.append(_run_one_test(spec, match.file.path, config))
        graded.test_outcomes[role_id] = outcomes

    # Step 3: rubric pass. One bad checker must not nuke the others, so
    # every grade() call is wrapped in defensive error handling.
    for item in config.rubric:
        try:
            graded.graded_items.append(item.grade(graded))
        except Exception as exc:
            graded.graded_items.append(GradedItem(
                item=item, earned=0.0,
                notes=f"grader error: {exc}", severity=3,
            ))
    return graded


# --------------------------------------------------------------------------- #
# Matching + running helpers
# --------------------------------------------------------------------------- #

def _match_role(role_id: str, spec: ExerciseRole,
                asm_files: Sequence[asm_header_parser.AsmFileSummary],
                used_files: set) -> FileRoleMatch:
    """Pick the best .asm file for a rubric exercise role.

    Scoring (higher is better):
      * exact basename match (case-insensitive) ............... +10
      * basename stem contains all tokens in any token-set ....  +6
      * file body contains any content_substring ..............  +3
      * file is NOT already bound to another role .............  +2
      * file lives at the submission root (not nested) ........  +1

    A candidate must score at least 6 to be accepted -- bare "untaken
    file" credit alone is not enough. This avoids handing the
    "interesting program" role to a stub file that just happens to be
    leftover.
    """
    best: Optional[asm_header_parser.AsmFileSummary] = None
    best_score = 0
    best_reason = ""
    preferred = {b.lower() for b in spec.preferred_basenames}
    for f in asm_files:
        score = 0
        reasons: List[str] = []
        bn = f.path.name.lower()
        stem = f.path.stem.lower()
        if bn in preferred:
            score += 10
            reasons.append(f"basename matches {f.path.name}")
        for token_set in spec.name_tokens:
            if all(tok.lower() in stem for tok in token_set):
                score += 6
                reasons.append("name tokens match")
                break
        body_lower: Optional[str] = None
        if spec.content_substrings:
            try:
                body_lower = f.path.read_text(
                    encoding="utf-8", errors="replace").lower()
            except OSError:
                body_lower = ""
            if any(sub.lower() in body_lower
                   for sub in spec.content_substrings):
                score += 3
                reasons.append("body contains expected keywords")
        if f.relative not in used_files:
            score += 2
        # Slight preference for top-level files (no subdirectory).
        if "/" not in f.relative:
            score += 1
        if score > best_score:
            best, best_score, best_reason = f, score, "; ".join(reasons)
    if best is None or best_score < 6:
        return FileRoleMatch(role=role_id, file=None, score=best_score,
                             reason="no file matched this exercise")
    return FileRoleMatch(role=role_id, file=best, score=best_score,
                         reason=best_reason)


def _run_one_test(spec: MipsTestSpec, asm_path: Path,
                  config: MipsLabConfig) -> MipsTestOutcome:
    """Execute one MipsTestSpec via MARS and decide pass/fail.

    Pass = every expected substring appears in stdout in the order
    listed (case-insensitive). Failures populate the `error` field
    with a short, teacher-friendly reason -- the appendix shows the
    full stdout/stderr separately so the teacher can dig in if they
    want.
    """
    if not mars_runner.java_available(config.java_exe):
        return MipsTestOutcome(
            spec=spec, passed=False, stdout="", stderr="",
            error="java not available",
        )
    res = mars_runner.run_asm(
        asm_path=asm_path,
        mars_jar=config.mars_jar,
        java_exe=config.java_exe,
        stdin_text=spec.stdin_text or None,
        timeout=spec.timeout,
    )
    if res.error:
        return MipsTestOutcome(
            spec=spec, passed=False, stdout="", stderr="",
            error=res.error,
        )
    if res.timed_out:
        return MipsTestOutcome(
            spec=spec, passed=False, stdout="", stderr=res.stderr,
            error=f"timed out after {spec.timeout}s (infinite loop?)",
            timed_out=True,
        )
    if res.assemble_error:
        return MipsTestOutcome(
            spec=spec, passed=False, stdout=res.stdout, stderr=res.stderr,
            error="assembler rejected the file",
            assemble_error=True,
        )
    found_in_order = _all_substrings_in_order(
        res.stdout, spec.expected_substrings)
    error = ""
    if not found_in_order:
        error = _describe_substring_miss(res.stdout, spec.expected_substrings)
    return MipsTestOutcome(
        spec=spec, passed=found_in_order, stdout=res.stdout,
        stderr=res.stderr, error=error,
    )


def _all_substrings_in_order(haystack: str,
                             needles: Sequence[str]) -> bool:
    """True iff every needle appears in haystack in the given order.

    Case-insensitive. Empty needle list trivially passes (used for
    "the program just has to run without error" tests).
    """
    if not needles:
        return True
    pos = 0
    low = haystack.lower()
    for needle in needles:
        idx = low.find(needle.lower(), pos)
        if idx < 0:
            return False
        pos = idx + len(needle)
    return True


def _describe_substring_miss(haystack: str,
                             needles: Sequence[str]) -> str:
    """Short reason string describing the FIRST missing substring."""
    if not needles:
        return ""
    pos = 0
    low = haystack.lower()
    for needle in needles:
        idx = low.find(needle.lower(), pos)
        if idx < 0:
            preview = re.sub(r"\s+", " ", haystack).strip()[:80] or "(empty)"
            return (f"expected to find {needle!r} in stdout but did not "
                    f"(stdout starts with {preview!r})")
        pos = idx + len(needle)
    return "output differed in an unexpected way"
