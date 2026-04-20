"""
Compiles a student's Compiler project and runs the parser/interpreter on
test input files. The student's expected layout is:

    Compiler/
        ast/*.java
        parser/*.java          <- contains Parser.java and ParserTester.java
        scanner/*.java
        environment/*.java

We compile the whole thing into a temp classes/ dir and then invoke the
student's `parser.Parser` main with our hidden test file. Output and exit
status are captured for comparison against expected stdout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class CompileResult:
    """Outcome of `javac` on the student's sources."""

    success: bool
    classes_dir: Optional[Path]
    errors: str
    raw_output: str


@dataclass
class RunResult:
    """Outcome of `java ... parser.Parser <testfile>`."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    error: Optional[str] = None  # Set if we couldn't even launch the JVM.


def compile_project(
    compiler_root: Path,
    javac_exe: str = "javac",
    timeout: int = 120,
) -> CompileResult:
    """Compile every .java file under compiler_root to a fresh classes dir.

    The classes directory is created inside compiler_root.parent so we don't
    pollute the student's tree. Caller is responsible for cleanup.
    """
    java_files = sorted(str(p) for p in compiler_root.rglob("*.java"))
    if not java_files:
        return CompileResult(False, None, "no .java files found", "")
    classes_dir = Path(tempfile.mkdtemp(prefix="classes_",
                                        dir=str(compiler_root.parent)))
    cmd = [javac_exe, "-d", str(classes_dir), "-encoding", "UTF-8"] + java_files
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(compiler_root),
            timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        shutil.rmtree(classes_dir, ignore_errors=True)
        return CompileResult(
            False, None, f"could not run javac ({exc})", ""
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(classes_dir, ignore_errors=True)
        return CompileResult(False, None,
                             f"javac timed out after {timeout}s", "")
    raw = proc.stdout + proc.stderr
    if proc.returncode != 0:
        shutil.rmtree(classes_dir, ignore_errors=True)
        return CompileResult(False, None, raw.strip() or "unknown javac error",
                             raw)
    return CompileResult(True, classes_dir, "", raw)


def run_parser(
    compiler_root: Path,
    classes_dir: Path,
    test_file: Path,
    java_exe: str = "java",
    timeout: int = 30,
    stdin_text: Optional[str] = None,
    main_class: str = "parser.Parser",
) -> RunResult:
    """Run the student's Parser main on one test source file.

    We invoke main with the test file's path relative to the student's
    Compiler/ root (their main() tends to open relative paths like
    "parser/parserTest7.txt"). To make that work regardless of where the
    file actually lives, we copy the test file into the Compiler/parser/
    directory under a unique name, run, and then remove it.
    """
    # Stage the test file inside parser/ so the student's relative-path logic
    # can find it.
    parser_dir = compiler_root / "parser"
    parser_dir.mkdir(parents=True, exist_ok=True)
    staged = parser_dir / f"_autograder_{os.getpid()}_{test_file.name}"
    staged.write_bytes(test_file.read_bytes())

    # Run from Compiler/ so "parser/<file>" resolves.
    cmd = [java_exe, "-cp", str(classes_dir), main_class,
           f"parser/{staged.name}"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(compiler_root),
            input=stdin_text, timeout=timeout, check=False,
        )
        return RunResult(stdout=proc.stdout, stderr=proc.stderr,
                         returncode=proc.returncode, timed_out=False)
    except FileNotFoundError as exc:
        return RunResult("", "", -1, False, f"could not run java ({exc})")
    except subprocess.TimeoutExpired:
        return RunResult("", "", -1, True, None)
    finally:
        try:
            staged.unlink()
        except OSError:
            pass


def extract_interesting_lines(stdout: str) -> List[str]:
    """Drop the driver's "--- file ---" and "Parser completed successfully."
    lines so we can compare against a clean expected-output list.
    """
    keep: List[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("---") and stripped.endswith("---"):
            continue
        if stripped == "Parser completed successfully.":
            continue
        keep.append(stripped)
    return keep
