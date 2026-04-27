"""
Wrap the MARS 4.5 MIPS simulator's command-line interface so the
ag-mips grader can assemble + run a student's .asm file and capture
its stdout.

MARS CLI cheat sheet
====================
The jar accepts a tiny set of flags before the source filename:

    java -jar Mars4_5.jar [opts...] <file.asm>

We use:
    nc          -- "no copyright" banner (clean stdout for diffing)
    ae<N>       -- exit with code <N> if assembly fails (we use 1)
    <integer>   -- maximum number of instructions to execute
                   (1_000_000 by default; our infinite-loop guard)

The jar reads syscall-5/8/12 input from JVM stdin and writes
syscall-1/4/11 output to JVM stdout, so we just pipe via subprocess.

Why a separate runner module
============================
The Procedures lab needed `java_runner.py` to compile a tree of .java
sources and probe several main-class candidates. A MIPS submission is
a flat folder of .asm files: one file in, one stdout out, no compile
step, no class-load probe. That's a different enough shape to warrant
its own thin wrapper rather than overloading java_runner.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Default cap on instructions executed by MARS before it gives up. Far
# more than any well-formed Lab 5 program needs; small enough that an
# accidental infinite loop terminates in well under our wall-clock
# timeout. MARS will print "Number of instructions executed exceeded the
# limit" on stderr if it hits this, which the grader treats as failure.
DEFAULT_INSTRUCTION_LIMIT = 1_000_000


@dataclass
class MarsResult:
    """Outcome of a single MARS invocation on one .asm source file."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    assemble_error: bool   # True iff MARS exited with our chosen ae<N>.
    error: Optional[str] = None  # Set if we couldn't even launch the JVM.


def run_asm(
    asm_path: Path,
    mars_jar: Path,
    java_exe: str = "java",
    stdin_text: Optional[str] = None,
    timeout: int = 10,
    instruction_limit: int = DEFAULT_INSTRUCTION_LIMIT,
    extra_args: tuple = (),
) -> MarsResult:
    """Assemble + run one .asm file and capture its stdout/stderr.

    @param asm_path absolute path to the student's .asm source.
    @param mars_jar absolute path to vendor/Mars4_5.jar.
    @param java_exe `java` binary to invoke; override for non-default JDKs.
    @param stdin_text text piped into the simulator's syscall-5/8 reads.
                      Newline-terminated lines map directly to one
                      syscall-5 read each.
    @param timeout wall-clock seconds before we kill the JVM and return
                   timed_out=True.
    @param instruction_limit hard ceiling on instructions executed
                             inside MARS itself. The 1_000_000 default
                             is generous enough for every Lab 5 program.
    @param extra_args additional MARS CLI flags appended before the
                      source filename (e.g. `("dec",)` to force decimal
                      register dumps). The standard nc / ae1 / limit
                      flags are always supplied.
    @return MarsResult bundling stdout, stderr, JVM returncode, and the
            two failure modes (timed_out, assemble_error).
    """
    cmd = [
        java_exe,
        "-jar", str(mars_jar),
        "nc",                       # suppress copyright banner
        "ae1",                      # exit 1 on assemble error
        str(instruction_limit),     # cap simulated instructions
        *extra_args,
        str(asm_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return MarsResult(
            stdout="", stderr="", returncode=-1, timed_out=False,
            assemble_error=False, error=f"could not run java ({exc})",
        )
    except subprocess.TimeoutExpired:
        return MarsResult(
            stdout="", stderr="", returncode=-1, timed_out=True,
            assemble_error=False, error=None,
        )
    # `ae1` was passed: a returncode of 1 means MARS's assembler rejected
    # the file before any simulation happened. MARS otherwise exits 0 --
    # even runtime traps (div by zero, out-of-bounds memory) come back
    # as exit 0 with the trap message routed through stdout. Any other
    # non-zero would indicate a JVM-level failure, not student code.
    # NOTE: the assembler writes its "Error in <file> line N" message
    # to STDOUT, not stderr, so we MUST NOT condition on stdout being
    # empty here.
    assemble_error = proc.returncode == 1
    return MarsResult(
        stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode,
        timed_out=False, assemble_error=assemble_error, error=None,
    )


def assemble_only(
    asm_path: Path,
    mars_jar: Path,
    java_exe: str = "java",
    timeout: int = 10,
) -> MarsResult:
    """Run MARS in assemble-only mode (`a` flag) without simulating.

    Used by the rubric checker for "does this file at least pass the
    assembler" -- a cheap, deterministic check that doesn't depend on
    stdin/stdout shape. Returns the same MarsResult with stdout
    typically empty and stderr listing any assemble errors.
    """
    cmd = [
        java_exe,
        "-jar", str(mars_jar),
        "nc",
        "a",                        # assemble only, do not simulate
        "ae1",
        str(asm_path),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        return MarsResult(
            stdout="", stderr="", returncode=-1, timed_out=False,
            assemble_error=False, error=f"could not run java ({exc})",
        )
    except subprocess.TimeoutExpired:
        return MarsResult(
            stdout="", stderr="", returncode=-1, timed_out=True,
            assemble_error=False, error=None,
        )
    assemble_error = proc.returncode != 0
    return MarsResult(
        stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode,
        timed_out=False, assemble_error=assemble_error, error=None,
    )


def java_available(java_exe: str = "java") -> bool:
    """Quick check: is the configured `java` binary on PATH at all?

    Used at startup so the grader can fail loudly with a friendly
    message before it tries to grade a hundred submissions and finds
    every single one labelled "could not run java".
    """
    return shutil.which(java_exe) is not None
