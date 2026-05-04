"""
Two-phase test runner for the CodeGen lab.

A CodeGen test is fundamentally different from a Procedures test: the
student's program does not produce stdout directly, it produces a
MIPS assembly file that another tool (MARS) then runs. So one "test"
takes two JVM launches:

    1. java <classes> parser._AGCodeGenTester <in.pas> <out.asm>
       -- the synthetic driver asks the student's emitter to write
       MIPS assembly to <out.asm>.

    2. java -jar Mars4_5.jar <out.asm>
       -- MARS assembles + simulates the program; we capture stdout
       and match it against the test's expected_substrings.

Either phase can fail independently, and the report needs to know
which: a missing .asm means the student's compile() never finished;
a present-but-failing .asm means MARS rejected what they emitted; a
clean assemble with wrong output means the codegen logic itself is
buggy. The TestOutcome's `error` field carries a one-line tag for
each of those cases so the rubric can score them without re-running.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from . import java_runner, mars_runner
from .grader import GradedSubmission, TestCase, TestOutcome


def run_codegen_test(case: TestCase, graded: GradedSubmission) -> TestOutcome:
    """Drive one CodeGen test through emit + MARS and produce a TestOutcome.

    Compile must have succeeded and the synthetic _AGCodeGenTester
    must be available. Otherwise we short-circuit and return a stub
    outcome with the right error message -- never re-running a JVM
    that we know will fail.
    """
    if not graded.compile_result.success or not graded.compile_result.classes_dir:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error="code did not compile; see compile errors in the main report",
        )
    if graded.synthetic is None:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error=("could not synthesise a CodeGen driver for this "
                   "submission (Parser/Program role unresolved)"),
        )
    mars_jar = graded.config.mars_jar
    if mars_jar is None or not Path(mars_jar).exists():
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error=f"MARS jar not configured / missing: {mars_jar}",
        )

    asm_dir = Path(tempfile.mkdtemp(prefix="codegen_",
                                    dir=str(graded.submission.workdir)))
    asm_out = asm_dir / f"{case.name}.asm"

    # Phase 1: stage the input .pas inside parser/ (so the student's
    # FileInputStream(args[0]) resolves whether it's relative or
    # absolute) and run the synthetic driver.
    parser_dir = graded.submission.compiler_root / "parser"
    parser_dir.mkdir(parents=True, exist_ok=True)
    staged_in = parser_dir / f"_codegen_{os.getpid()}_{case.source_path.name}"
    staged_in.write_bytes(case.source_path.read_bytes())
    try:
        cmd = [
            graded.config.java_exe,
            "-cp", str(graded.compile_result.classes_dir),
            graded.synthetic.fq_class,
            f"parser/{staged_in.name}",
            str(asm_out),
        ]
        emit_proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(graded.submission.compiler_root),
            timeout=case.timeout, check=False,
        )
    except FileNotFoundError as exc:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error=f"could not run java ({exc})",
        )
    except subprocess.TimeoutExpired:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error=f"emit phase timed out after {case.timeout}s",
            timed_out=True,
        )
    finally:
        try:
            staged_in.unlink()
        except OSError:
            pass

    if emit_proc.returncode != 0 and not asm_out.exists():
        # Student's emitter blew up before writing the file. Surface
        # the first stderr line so the teacher knows what went wrong.
        first = (emit_proc.stderr or emit_proc.stdout or "").splitlines()
        first_line = first[0] if first else "(no error output)"
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr=emit_proc.stderr,
            error=f"emit failed: {first_line}",
            artifact_path=None,
        )
    if not asm_out.exists():
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr=emit_proc.stderr,
            error="emit phase ran but did not produce a .asm file",
            artifact_path=None,
        )

    # Phase 2: assemble + run the emitted .asm through MARS.
    mars_res = mars_runner.run_asm(
        asm_out, Path(mars_jar),
        java_exe=graded.config.java_exe,
        stdin_text=case.stdin_text,
        timeout=case.timeout,
    )
    if mars_res.error:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr="",
            error=mars_res.error, artifact_path=asm_out,
        )
    if mars_res.timed_out:
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr=mars_res.stderr,
            error=f"MARS run timed out after {case.timeout}s "
                  f"(emitted code may infinite-loop)",
            timed_out=True, artifact_path=asm_out,
        )
    if mars_res.assemble_error:
        # MARS prints "Error in <file> line N: ..." on stdout. Surface
        # the first such line as the error tag.
        bad_line = next(
            (ln.strip() for ln in mars_res.stdout.splitlines()
             if "Error" in ln),
            "MARS assemble error",
        )
        return TestOutcome(
            case=case, passed=False, actual_stdout=[], stderr=mars_res.stderr,
            error=f"MARS rejected emitted .asm: {bad_line}",
            artifact_path=asm_out,
        )

    actual = _interesting_lines(mars_res.stdout)
    expected = list(case.expected_stdout)
    passed = actual == expected
    error = "" if passed else _describe_mismatch(expected, actual,
                                                 mars_res.stderr)
    return TestOutcome(
        case=case, passed=passed, actual_stdout=actual,
        stderr=mars_res.stderr.strip(), error=error,
        artifact_path=asm_out,
    )


def _interesting_lines(stdout: str) -> List[str]:
    """Drop empty lines from MARS stdout to produce the comparison list."""
    return [ln.strip() for ln in stdout.splitlines() if ln.strip()]


def _describe_mismatch(expected: List[str], actual: List[str],
                       stderr: str) -> str:
    """Mirror the procedures-grader description style for fail rows."""
    stderr = (stderr or "").strip()
    if stderr:
        return f"runtime error: {stderr.splitlines()[0]}"
    if not actual:
        return f"no output; expected {len(expected)} line(s)"
    if len(expected) != len(actual):
        return (f"expected {len(expected)} output line(s) but got "
                f"{len(actual)}")
    for i, (exp, got) in enumerate(zip(expected, actual)):
        if exp != got:
            return f"line {i + 1} differed (expected {exp!r}, got {got!r})"
    return "output differed in an unexpected way"
