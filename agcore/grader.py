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
from .role_resolver import RoleSpec, resolve_class_role, resolve_method
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

    # Role-based class + method resolution. class_roles maps a rubric-level
    # role name (e.g. "ProcedureCall") to a RoleSpec that tells the resolver
    # how to find that class even when the student renamed it. method_aliases
    # maps a (class_role, method_role) pair to an ordered sequence of
    # acceptable method names -- the first hit wins, so rubric-preferred
    # spellings go first. Both default to empty; a lab that wants strict-name
    # behaviour simply leaves them out and keeps calling class_by_name.
    class_roles: Dict[str, RoleSpec] = field(default_factory=dict)
    method_aliases: Dict[tuple, Sequence[str]] = field(default_factory=dict)


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
    # .java files javalang couldn't parse. A missing semicolon on line 1
    # makes the whole file invisible to the role resolver, which then
    # reports "parseProgram missing" etc. -- extremely misleading. The
    # rubric checkers consult this list so they can report "file
    # unparseable" instead.
    unparsed_files: List[javadoc_parser.ParseFailure] = field(
        default_factory=list)
    # Memoisation for class_for_role so each rubric checker doesn't re-score
    # every class. Populated lazily on first lookup per role name.
    _role_cache: Dict[str, Optional[javadoc_parser.ClassRecord]] = field(
        default_factory=dict, repr=False)

    # Lookup helpers used by lab-specific checkers:
    def class_by_name(self, name: str) -> Optional[javadoc_parser.ClassRecord]:
        """Return the first class record matching name exactly, or None.

        Kept for rare lookups where the rubric genuinely cares about the
        literal name. Prefer class_for_role() for anything driven off the
        peer-review rubric so student renames don't nuke the score.
        """
        for cls in self.classes:
            if cls.name == name:
                return cls
        return None

    def class_for_role(
        self, role: str
    ) -> Optional[javadoc_parser.ClassRecord]:
        """Fuzzy-resolve a rubric role (e.g. "ProcedureCall") to a class.

        Falls back to exact-name lookup if the lab didn't configure a
        RoleSpec for the role; returns None if nothing matches. Results
        are cached per-submission so repeated calls from multiple rubric
        checkers don't re-score every class.
        """
        if role in self._role_cache:
            return self._role_cache[role]
        spec = self.config.class_roles.get(role)
        if spec is None:
            resolved = self.class_by_name(role)
        else:
            resolved = resolve_class_role(self.classes, spec)
        self._role_cache[role] = resolved
        return resolved

    def all_methods(self) -> List[javadoc_parser.MethodRecord]:
        """Flat list of every method across every class."""
        return [m for cls in self.classes for m in cls.methods]

    def method(self, class_name: str,
               method_name: str) -> Optional[javadoc_parser.MethodRecord]:
        """Find one method by class and name (strict, both names literal)."""
        cls = self.class_by_name(class_name)
        if not cls:
            return None
        for m in cls.methods:
            if m.method_name == method_name:
                return m
        return None

    def method_for_role(
        self, class_role: str, method_role: str
    ) -> Optional[javadoc_parser.MethodRecord]:
        """Fuzzy-resolve a rubric method role inside a class role.

        The class is resolved via class_for_role; the method name is
        matched against config.method_aliases[(class_role, method_role)]
        (falling back to [method_role] if no aliases are configured).
        """
        cls = self.class_for_role(class_role)
        if cls is None:
            return None
        aliases = self.config.method_aliases.get(
            (class_role, method_role), (method_role,))
        return resolve_method(cls, aliases)

    def failure_for_role(
        self, role: str
    ) -> Optional[javadoc_parser.ParseFailure]:
        """Return the ParseFailure entry for the file that WOULD hold role, if any.

        Used by rubric checkers to distinguish "class genuinely missing"
        from "class's file didn't parse so we can't see it". The heuristic
        is simple: we check every failed file's basename against the
        role's preferred_name and aliases. A match means "this is
        probably where the role lived before the file broke". Returns the
        first match or None.

        A lab with no RoleSpec for the given role falls back to matching
        role itself against the basename ("Parser" against "Parser.java").
        """
        if not self.unparsed_files:
            return None
        spec = self.config.class_roles.get(role)
        names: List[str] = []
        if spec is None:
            names.append(role)
        else:
            names.append(spec.preferred_name)
            names.extend(spec.aliases)
        for fail in self.unparsed_files:
            stem = fail.file.rsplit("/", 1)[-1]
            if stem.endswith(".java"):
                stem = stem[:-5]
            if stem in names:
                return fail
        return None

    def source_for_role(self, role: str) -> Optional[str]:
        """Read the source text of the file that defines role, or None.

        Priority order (in order of preference):
          1. An unparsed file whose basename EXACTLY matches the role's
             preferred_name -- that's almost certainly the file the
             student meant as this role. This branch wins over AST
             resolution on purpose: otherwise a sibling class (e.g.
             ParserTester) can steal the Parser role via the
             name_tokens match, pointing every grep check at the wrong
             file.
          2. class_for_role(role).file -- AST-verified location.
          3. Any unparsed file whose basename matches preferred_name or
             an alias, even when class_for_role returned None.

        The first branch is load-bearing: when a student has a syntax
        error in their real Parser.java, the actual method bodies we're
        grepping for are still in that file, not in ParserTester.java.
        """
        spec = self.config.class_roles.get(role)
        preferred_stem = spec.preferred_name if spec else role
        fail = self.failure_for_role(role)

        # Priority 1: unparsed file whose basename is exactly
        # <preferred_name>.java. Reading it gives the grep pass the
        # source it actually wants.
        if fail is not None:
            fail_basename = fail.file.rsplit("/", 1)[-1]
            if fail_basename == f"{preferred_stem}.java":
                path = self.submission.compiler_root / fail.file
                try:
                    return path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass

        # Priority 2: AST-resolved class's file.
        cls = self.class_for_role(role)
        if cls is not None:
            rel = cls.file
        elif fail is not None:
            # Priority 3: any unparsed file matching by alias/name.
            rel = fail.file
        else:
            return None
        path = self.submission.compiler_root / rel
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
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


def grade(zip_path: Path, config: LabConfig,
          submission: Optional[extractor.Submission] = None
          ) -> GradedSubmission:
    """Run the full grading pipeline on one student zip.

    @param zip_path path to the student submission zip
    @param config lab-specific configuration
    @param submission optional pre-extracted submission. When provided, the
                      grader will not unzip again -- handy for callers that
                      want to inspect the extracted tree (e.g. to pick an
                      output filename based on @author) before grading.
    @return GradedSubmission with every stage's results attached.
    @postcondition caller must eventually call graded.submission.cleanup()
                   to wipe the temp workdir.
    """
    if submission is None:
        submission = extractor.extract(zip_path)
    checkstyle = checkstyle_runner.run_checkstyle(
        submission.compiler_root, config.checkstyle_jar,
        config.checkstyle_xml, java_exe=config.java_exe,
    )
    classes, unparsed_files = javadoc_parser.parse_tree_with_failures(
        submission.compiler_root)
    compile_result = java_runner.compile_project(
        submission.compiler_root, javac_exe=config.javac_exe,
    )
    graded = GradedSubmission(
        config=config, submission=submission, checkstyle=checkstyle,
        classes=classes, compile_result=compile_result,
        unparsed_files=unparsed_files,
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
