"""
Runs checkstyle against a student's Java sources. We bundle a specific
checkstyle.jar under vendor/ so the result is deterministic across graders.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from . import extractor


VIOLATION_RE = re.compile(
    r"^\[(?P<level>WARN|ERROR)\]\s+(?P<path>.+?):"
    r"(?P<line>\d+)(?::(?P<col>\d+))?\s*:\s*(?P<msg>.+?)\s*"
    r"\[(?P<rule>[A-Za-z]+)\]\s*$"
)


@dataclass
class Violation:
    """One checkstyle violation tied to a source file."""

    level: str
    path: str
    line: int
    col: int | None
    message: str
    rule: str


@dataclass
class CheckstyleResult:
    """Aggregate checkstyle output for a submission."""

    violations: List[Violation] = field(default_factory=list)
    raw_output: str = ""
    error: str | None = None  # Non-None if checkstyle itself failed.

    @property
    def passed(self) -> bool:
        """True iff checkstyle reported zero violations and didn't error out."""
        return self.error is None and not self.violations

    def by_file(self) -> dict[str, List[Violation]]:
        """Group violations by file path for per-file reporting."""
        grouped: dict[str, List[Violation]] = {}
        for v in self.violations:
            grouped.setdefault(v.path, []).append(v)
        return grouped


def run_checkstyle(
    compiler_root: Path,
    checkstyle_jar: Path,
    checkstyle_xml: Path,
    java_exe: str = "java",
    timeout: int = 120,
) -> CheckstyleResult:
    """Invoke checkstyle on every .java file under compiler_root.

    Args:
        compiler_root: the Compiler/ dir that holds ast/, parser/, ... etc.
        checkstyle_jar: path to the bundled checkstyle jar.
        checkstyle_xml: path to the checkstyle configuration.
        java_exe: java executable (override for non-standard installs).
        timeout: seconds to wait before aborting.

    Returns:
        A CheckstyleResult with parsed violations and the raw stdout/stderr.
    """
    # Skip extractor.EXCLUDED_DIRS (e.g. the optional ll1parser/ directory).
    java_files = sorted(
        str(p) for p in extractor.iter_graded_java_files(compiler_root)
    )
    result = CheckstyleResult()
    if not java_files:
        result.error = "no .java files found under the Compiler root"
        return result

    cmd = [java_exe, "-jar", str(checkstyle_jar),
           "-c", str(checkstyle_xml)] + java_files
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        result.error = f"could not run java ({exc}). Install a JDK and retry."
        return result
    except subprocess.TimeoutExpired:
        result.error = f"checkstyle timed out after {timeout}s"
        return result

    result.raw_output = proc.stdout + proc.stderr
    for line in result.raw_output.splitlines():
        match = VIOLATION_RE.match(line.strip())
        if match:
            result.violations.append(Violation(
                level=match.group("level"),
                path=match.group("path"),
                line=int(match.group("line")),
                col=int(match.group("col")) if match.group("col") else None,
                message=match.group("msg"),
                rule=match.group("rule"),
            ))
    return result
