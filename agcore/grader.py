"""
Top-level grading orchestrator. A lab-specific config module builds a
LabConfig instance and passes it here; the grader does the rest:

    1. extract the zip
    2. run checkstyle
    3. parse javadocs / methods / classes
    4. compile the student's Compiler
    5. run the hidden test suite
    6. run the proximity checks
    7. grade each rubric item
    8. hand a GradedSubmission to the report module

Each stage is wrapped in defensive error handling so a broken submission
still produces a sensible PDF rather than an uncaught exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from . import checkstyle_runner, extractor, java_runner, javadoc_parser
from .proximity import ProximityFinding
from .rubric import CheckResult, GradedItem, RubricItem


@dataclass
class TestCase:
    """One hidden functional test case for a lab."""

    name: str                        # Short stable id ("simple", "args", ...)
    description: str                 # Human-readable summary for the PDF.
    source_path: Path                # PASCAL program to feed the parser.
    expected_stdout: List[str]       # Exact lines expected (no "---" lines).
    stdin_text: Optional[str] = None
    timeout: int = 30


@dataclass
class TestOutcome:
    """Result of running one TestCase."""

    case: TestCase
    passed: bool
    actual_stdout: List[str]
    stderr: str
    error: str = ""   # High-level reason for a failure.
    timed_out: bool = False


@dataclass
class LabConfig:
    """Pluggable configuration a lab provides to drive this orchestrator."""

    lab_name: str                                 # "Procedures Lab"
    rubric: Sequence[RubricItem]
    hidden_tests: Sequence[TestCase]
    # Proximity rules. Each callable gets the GradedSubmission (mid-build) and
    # returns a list of ProximityFinding.
    proximity_rules: Sequence[Callable[["GradedSubmission"],
                                       List[ProximityFinding]]]
    checkstyle_jar: Path
    checkstyle_xml: Path
    # Optional overrides:
    java_exe: str = "java"
    javac_exe: str = "javac"
    main_class: str = "parser.Parser"


@dataclass
class GradedSubmission:
    """Everything the PDF renderer needs to draw the blanksheet."""

    config: LabConfig
    submission: extractor.Submission
    checkstyle: checkstyle_runner.CheckstyleResult
    classes: List[javadoc_parser.ClassRecord]
    compile_result: java_runner.CompileResult
    test_outcomes: List[TestOutcome] = field(default_factory=list)
    proximity: List[ProximityFinding] = field(default_factory=list)
    graded_items: List[GradedItem] = field(default_factory=list)

    # Lookup helpers used by lab-specific checkers:
    def class_by_name(self, name: str) -> Optional[javadoc_parser.ClassRecord]:
        """Return the first class record matching name, or None."""
        for cls in self.classes:
            if cls.name == name:
                return cls
        return None

    def all_methods(self) -> List[javadoc_parser.MethodRecord]:
        """Flat list of every method across every class."""
        return [m for cls in self.classes for m in cls.methods]

    def method(self, class_name: str,
               method_name: str) -> Optional[javadoc_parser.MethodRecord]:
        """Find one method by class and name."""
        cls = self.class_by_name(class_name)
        if not cls:
            return None
        for m in cls.methods:
            if m.method_name == method_name:
                return m
        return None

    @property
    def total_earned(self) -> float:
        """Total points earned across all rubric items."""
        return sum(g.earned for g in self.graded_items)

    @property
    def total_possible(self) -> float:
        """Total points possible across all rubric items."""
        return sum(g.item.points for g in self.graded_items)

    @property
    def percent(self) -> float:
        """Earned as a 0..100 percentage (0 if rubric is empty)."""
        if self.total_possible <= 0:
            return 0.0
        return 100.0 * self.total_earned / self.total_possible


def grade(zip_path: Path, config: LabConfig) -> GradedSubmission:
    """Run the full grading pipeline on one student zip.

    Caller is responsible for eventually calling
    graded.submission.cleanup() to wipe the temp workdir.
    """
    submission = extractor.extract(zip_path)
    checkstyle = checkstyle_runner.run_checkstyle(
        submission.compiler_root, config.checkstyle_jar,
        config.checkstyle_xml, java_exe=config.java_exe,
    )
    classes = javadoc_parser.parse_tree(submission.compiler_root)
    compile_result = java_runner.compile_project(
        submission.compiler_root, javac_exe=config.javac_exe,
    )
    graded = GradedSubmission(
        config=config, submission=submission, checkstyle=checkstyle,
        classes=classes, compile_result=compile_result,
    )

    # Functional test pass -- each test is isolated so one failure doesn't
    # poison the rest.
    for case in config.hidden_tests:
        graded.test_outcomes.append(_run_test_case(case, graded))

    # Documentation proximity pass.
    for rule in config.proximity_rules:
        try:
            graded.proximity.extend(rule(graded))
        except Exception as exc:  # defensive; one bad rule must not nuke all
            graded.proximity.append(ProximityFinding(
                target="(proximity rule error)", file="", line=0,
                expected=[], matched=[], missing=[], threshold=0,
                passed=False, note=f"rule exception: {exc}",
            ))

    # Rubric pass.
    for item in config.rubric:
        try:
            graded.graded_items.append(item.grade(graded))
        except Exception as exc:
            graded.graded_items.append(GradedItem(
                item=item, earned=0.0,
                notes=f"grader error: {exc}", severity=3,
            ))
    return graded


def _run_test_case(case: TestCase, graded: GradedSubmission) -> TestOutcome:
    """Compile must succeed before we attempt to run any tests."""
    if not graded.compile_result.success or not graded.compile_result.classes_dir:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error="code did not compile; see compile errors in the main report",
        )
    run = java_runner.run_parser(
        compiler_root=graded.submission.compiler_root,
        classes_dir=graded.compile_result.classes_dir,
        test_file=case.source_path,
        java_exe=graded.config.java_exe,
        timeout=case.timeout,
        stdin_text=case.stdin_text,
        main_class=graded.config.main_class,
    )
    if run.timed_out:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr=run.stderr,
            error=f"timed out after {case.timeout}s (infinite loop?)",
            timed_out=True,
        )
    if run.error:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error=run.error,
        )
    actual = java_runner.extract_interesting_lines(run.stdout)
    passed = actual == case.expected_stdout
    error = ""
    if not passed:
        error = _describe_mismatch(case.expected_stdout, actual, run.stderr)
    return TestOutcome(
        case=case, passed=passed, actual_stdout=actual,
        stderr=run.stderr.strip(), error=error,
    )


def _describe_mismatch(expected: List[str], actual: List[str],
                       stderr: str) -> str:
    """Produce a short, code-free description of where the output diverged."""
    stderr = stderr.strip()
    if stderr:
        # Prefer surfacing the runtime error -- the teacher cares more about
        # "why" than "what line diverged".
        first = stderr.splitlines()[0]
        return f"runtime error: {first}"
    if not actual:
        return f"no output; expected {len(expected)} line(s)"
    if len(expected) != len(actual):
        return (f"expected {len(expected)} output line(s) but got "
                f"{len(actual)}")
    for i, (exp, got) in enumerate(zip(expected, actual)):
        if exp != got:
            return f"line {i + 1} differed (expected {exp!r}, got {got!r})"
    return "output differed in an unexpected way"
