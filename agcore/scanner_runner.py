"""
Test-runner override for the Scanner lab.

Most scanner-lab test cases are graded with the default exact-stdout
matcher (in agcore.grader._run_test_case). One exception: the
"throws on $ / ^" test case is supposed to produce a clean token
prefix followed by a runtime error -- the student's ScanErrorException
caught and re-emitted as `ERROR: <msg>` by the synthetic driver. We
can't predict the exact message text per student, so exact-match would
incorrectly fail a correct submission.

This runner adds one matching mode -- "prefix_then_error" -- which
passes when the actual stdout starts with the listed prefix tokens AND
contains at least one ERROR-prefixed line after them. The mode is
selected by adding `match_mode="prefix_then_error"` on the TestCase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .grader import TestOutcome, _run_test_case

if TYPE_CHECKING:
    from .grader import GradedSubmission, TestCase


def run_scanner_test(case: "TestCase",
                     graded: "GradedSubmission") -> TestOutcome:
    """Delegate to the default runner, then re-grade prefix_then_error cases.

    The default runner already handles JVM launch, the main-class probe,
    the timeout, and stderr collection. We just override the
    pass/fail verdict for cases that declared a non-exact match mode.
    """
    base = _run_test_case(case, graded)
    mode = getattr(case, "match_mode", "exact")
    if mode == "exact":
        return base
    if mode == "prefix_then_error":
        return _grade_prefix_then_error(case, base)
    # Unknown mode: surface the configuration error in the report
    # rather than silently passing.
    return TestOutcome(
        case=case, passed=False,
        actual_stdout=base.actual_stdout, stderr=base.stderr,
        error=f"unknown match_mode {mode!r} on test {case.name!r}",
        timed_out=base.timed_out,
    )


def _grade_prefix_then_error(case: "TestCase",
                             base: TestOutcome) -> TestOutcome:
    """Pass iff actual starts with expected and then has an ERROR line.

    Implementation notes:
      * `base.actual_stdout` is already cleaned of blank/banner lines by
        java_runner.extract_interesting_lines, so prefix comparison is
        direct.
      * "ERROR" matches case-insensitively: students who name the
        exception differently still get credit as long as the driver's
        catch-all path emits the well-known prefix.
      * If the prefix is wrong we keep the original mismatch reason so
        the teacher sees WHICH token diverged, not just "no error
        line".
    """
    prefix = case.expected_stdout
    actual = base.actual_stdout
    if actual[:len(prefix)] != prefix:
        return TestOutcome(
            case=case, passed=False, actual_stdout=actual,
            stderr=base.stderr,
            error=(f"prefix mismatch: expected first {len(prefix)} "
                   f"tokens to be {prefix!r}, got {actual[:len(prefix)]!r}"),
            timed_out=base.timed_out,
        )
    tail = actual[len(prefix):]
    if not any(line.upper().startswith("ERROR") for line in tail):
        return TestOutcome(
            case=case, passed=False, actual_stdout=actual,
            stderr=base.stderr,
            error=("expected an ERROR-prefixed line after the good "
                   "prefix; got " + (repr(tail) if tail else "no further output")),
            timed_out=base.timed_out,
        )
    return TestOutcome(
        case=case, passed=True, actual_stdout=actual,
        stderr=base.stderr, error="", timed_out=base.timed_out,
    )
