"""
Compiles a student's Compiler project and runs the parser/interpreter on
test input files. The student's expected layout is:

    Compiler/
        ast/*.java
        parser/*.java          <- may contain Parser.java, ParserTester.java
        scanner/*.java
        environment/*.java

We compile the whole thing into a temp classes/ dir and then invoke whichever
class the student put their `public static void main(String[])` in. The
location varies by student:

  * some put main in parser.Parser                       (quick-test hatch)
  * some put main in parser.ParserTester                 (dedicated driver)
  * some put main in a top-level Main / Driver class

`detect_main_candidates` scans the parsed sources (and falls back to text
grep for unparsed files) and returns an ordered list of plausible main
classes so the grader can probe each one rather than assume a single
canonical location.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from . import extractor


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
    # Skip directories listed in extractor.EXCLUDED_DIRS (notably ll1parser/,
    # which is from the optional LL1 lab and must not influence grading).
    java_files = sorted(
        str(p) for p in extractor.iter_graded_java_files(compiler_root)
    )
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


_MAIN_SIG_RE = re.compile(
    r"public\s+static\s+void\s+main\s*\(\s*(?:final\s+)?String\s*(?:\[\s*\]"
    r"|\.\.\.)\s*\w+\s*\)")


def _package_of(file_path: str) -> str:
    """Derive a package name from a relative .java file path.

    "parser/Parser.java" -> "parser"; "ast/Foo.java" -> "ast"; a class in
    the compiler root with no subdirectory -> "" (default package).
    """
    if "/" not in file_path:
        return ""
    return file_path.rsplit("/", 1)[0].replace("/", ".")


def _score_main_candidate(class_name: str, file_path: str, body: str) -> int:
    """Heuristic score for how likely this class is the student's entry point.

    Higher = more likely. Negative means "avoid this candidate".
    Signals:
      + main body calls parseProgram / constructs a Parser
      + class name hints the role (ParserTester, Main, Driver)
      - ScannerTester: wrong tester for this lab
      - ll1parser/: excluded lab
    """
    score = 0
    # Name-based preferences.
    if class_name == "Main":
        score += 5
    elif class_name == "Driver":
        score += 4
    elif class_name == "ParserTester":
        score += 5
    elif class_name.endswith("Tester") and "Parser" in class_name:
        score += 4
    elif class_name == "Parser":
        score += 3
    elif class_name.endswith("Tester"):
        score += 1
    # Known wrong testers.
    if class_name == "ScannerTester":
        score -= 20
    # Excluded packages (defensive; extractor should have filtered them).
    if file_path.startswith("ll1parser/") or "/ll1parser/" in file_path:
        score -= 20
    # Body signals: does main look like it parses a program?
    if "parseProgram" in body or "parseprogram" in body.lower():
        score += 4
    if re.search(r"new\s+Parser\b", body):
        score += 3
    if "args[0]" in body or "args [0]" in body:
        score += 1  # Accepts a file path from the command line.
    if "Scanner" in body and "FileInputStream" in body:
        score += 2  # Opens the file the autograder passes it.
    if "exec" in body or "execute" in body:
        score += 1  # Runs the resulting AST.
    return score


def detect_main_candidates(
    classes: Sequence,
    unparsed_files: Sequence,
    compiler_root: Path,
) -> List[str]:
    """Return fully-qualified class names that plausibly host the main method.

    Ordered most-likely-correct first. The grader probes each in turn so a
    student who keeps their main in ParserTester (or a top-level Main, or
    just inside Parser.java) isn't falsely marked as "tests don't run".

    Parsing covers AST-visible classes; for unparseable files we fall back
    to regex on the raw source text so a syntax error elsewhere in the file
    doesn't hide the main method.
    """
    candidates: List[tuple] = []   # (score, fq_name)
    seen: set = set()

    # 1) AST-visible classes.
    for cls in classes:
        for m in cls.methods:
            if m.method_name != "main":
                continue
            # javalang doesn't hand us the method source, so grab it from
            # the file. We want a rough body blob for scoring.
            src_path = compiler_root / cls.file
            try:
                body = src_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = ""
            # Only count classes with a real main(String[]) signature --
            # javalang gives every method named "main" regardless of args,
            # so verify with a regex before crediting.
            if not _MAIN_SIG_RE.search(body):
                continue
            pkg = _package_of(cls.file)
            fq = f"{pkg}.{cls.name}" if pkg else cls.name
            if fq in seen:
                continue
            seen.add(fq)
            candidates.append(
                (_score_main_candidate(cls.name, cls.file, body), fq))

    # 2) Unparsed files: regex-detect main method + class name.
    for fail in unparsed_files:
        src_path = compiler_root / fail.file
        try:
            body = src_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _MAIN_SIG_RE.search(body):
            continue
        # Find the enclosing class name via the first `class Foo` we see.
        m = re.search(r"\bclass\s+(\w+)\b", body)
        if not m:
            continue
        cname = m.group(1)
        pkg = _package_of(fail.file)
        fq = f"{pkg}.{cname}" if pkg else cname
        if fq in seen:
            continue
        seen.add(fq)
        # Text-grepped candidates get a small penalty -- the file didn't
        # compile, so this candidate probably won't run anyway, but keep
        # it in the list for completeness (javac might still produce a
        # classfile for an incomplete file, in rare cases).
        score = _score_main_candidate(cname, fail.file, body) - 2
        candidates.append((score, fq))

    # Sort: highest score first; stable within ties.
    candidates.sort(key=lambda t: t[0], reverse=True)
    return [fq for _, fq in candidates]


def _looks_like_jvm_class_load_error(stderr: str) -> bool:
    """True iff stderr indicates the JVM couldn't find/load the main class.

    Used by the grader to skip dud candidates and try the next one rather
    than report every test as failed with a cryptic "no main" error.
    """
    if not stderr:
        return False
    s = stderr.strip()
    markers = (
        "Could not find or load main class",
        "main method not found",
        "Main method not found",
        "NoClassDefFoundError",
        "no main manifest attribute",
        "ClassNotFoundException",
    )
    return any(mark in s for mark in markers)


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
