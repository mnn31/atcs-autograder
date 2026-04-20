"""
Pulls a student submission out of a zip archive and locates the Compiler root
(the directory that holds ast/, parser/, scanner/, environment/, and
checkstyle.xml). Some students zip the folder itself, some zip its contents,
some leave macOS __MACOSX junk behind -- this module normalises all of that.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set


REQUIRED_SUBDIRS = ("ast", "parser", "scanner", "environment")

# Matches a single-line @author tag. Group 1 is the name, up to the end of
# the line OR the closing "*/" / trailing "*" (for both single-line javadoc
# like "/** @author X */" and multi-line "* @author X" forms). A lazy
# match plus the explicit terminators avoids slurping the next tag, the
# closing marker, or any trailing code on the same line.
_AUTHOR_RE = re.compile(
    r"@author[ \t]+(.+?)(?:\s*\*+/?\s*$|\s*\*/|[\n\r])",
    re.MULTILINE,
)

# Instructor / reference-code names that should NOT be used as the student's
# identity. Matched case-insensitively with whitespace collapsed.
# Add aliases for the same person as separate entries.
TEACHER_NAMES: Set[str] = {
    "anu datar",
    "mr. datar",
    "mr datar",
    "marina peregrino",
    "ms. peregrino",
    "ms peregrino",
}


@dataclass
class Submission:
    """The extracted, normalised view of a student's Compiler folder.

    Attributes:
        workdir: temp dir where we extracted the zip. Caller owns cleanup via
            cleanup().
        compiler_root: directory that contains ast/, parser/, scanner/, ...
        student_name: best-effort identifier. Preferred source is the most
            common non-teacher @author tag found in the .java sources; falls
            back to a cleaned-up version of the zip basename.
    """

    workdir: Path
    compiler_root: Path
    student_name: str

    def cleanup(self) -> None:
        """Wipe the temp directory created for this submission."""
        shutil.rmtree(self.workdir, ignore_errors=True)

    @property
    def student_slug(self) -> str:
        """Filesystem-safe slug derived from student_name.

        Lowercase, alphanumerics and hyphens only, spaces/underscores mapped
        to single hyphens. Example: "Manan Gupta" -> "manan-gupta".
        Returns "student" for an empty name so filenames never collapse to
        an empty string.
        """
        return name_to_filename_slug(self.student_name)


def extract(zip_path: str | Path) -> Submission:
    """Unzip the submission and locate the Compiler folder.

    Args:
        zip_path: path to the student's .zip submission.

    Returns:
        Submission with workdir, compiler_root, and student_name filled in.

    Raises:
        FileNotFoundError: zip_path doesn't exist.
        ValueError: extraction did not yield a Compiler-looking folder (no
            ast/ or parser/ could be located anywhere inside).
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"zip not found: {zip_path}")

    workdir = Path(tempfile.mkdtemp(prefix="autograder_"))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(workdir)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise ValueError(f"not a valid zip file: {zip_path}") from exc

    compiler_root = _find_compiler_root(workdir)
    if compiler_root is None:
        shutil.rmtree(workdir, ignore_errors=True)
        raise ValueError(
            f"could not locate a Compiler folder inside {zip_path.name}. "
            f"Expected subdirs: {', '.join(REQUIRED_SUBDIRS)}."
        )

    student_name = (most_common_student_author(compiler_root)
                    or _student_name_from_zip(zip_path))
    return Submission(workdir=workdir, compiler_root=compiler_root,
                      student_name=student_name)


def _find_compiler_root(root: Path) -> Path | None:
    """Walk under root looking for the directory that holds the required
    subdirs. Skips __MACOSX junk.

    Returns the deepest matching directory, or None if none found.
    """
    candidates = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__MACOSX"]
        names = set(dirnames)
        hits = sum(1 for want in REQUIRED_SUBDIRS if want in names)
        if hits >= 3:
            candidates.append((hits, Path(dirpath)))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: (-pair[0], len(str(pair[1]))))
    return candidates[0][1]


def _student_name_from_zip(zip_path: Path) -> str:
    """Scrape a best-guess student name from the zip filename.

    Strips common suffixes like _Compiler, _procedures, _submission, etc.
    Used as a fallback when no usable @author tag is found in the sources.
    """
    stem = zip_path.stem
    for junk in ("_Compiler", "_compiler", "_procedures", "_Procedures",
                 "_submission", "_Submission", "_final", "_FINAL"):
        if stem.endswith(junk):
            stem = stem[: -len(junk)]
    return stem.replace("_", " ").strip() or "Unknown Student"


def most_common_student_author(
    compiler_root: Path,
    teachers: Optional[Set[str]] = None,
) -> Optional[str]:
    """Return the most common non-teacher @author tag in the submission.

    Scans every .java file under compiler_root, pulls @author values, drops
    any that match TEACHER_NAMES (case/whitespace-insensitive), and returns
    the remaining value that appears most often. Ties are broken by the
    first occurrence encountered during traversal.

    @param compiler_root directory holding the student's Compiler tree
    @param teachers override set of names to exclude; defaults to
                    TEACHER_NAMES module constant
    @return the student's name as written in the javadoc, or None if no
            non-teacher @author could be found
    """
    exclude = {_normalize_name(t) for t in (teachers or TEACHER_NAMES)}
    counts: Dict[str, int] = {}
    first_display: Dict[str, str] = {}
    for path in sorted(compiler_root.rglob("*.java")):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _AUTHOR_RE.finditer(source):
            raw = match.group(1).strip()
            # Trim trailing " *" / "*/" / stray stars that end a doc line.
            raw = re.sub(r"\s*\*+/?\s*$", "", raw).strip()
            if not raw:
                continue
            key = _normalize_name(raw)
            if key in exclude:
                continue
            counts[key] = counts.get(key, 0) + 1
            # Collapse internal whitespace for the display form, but keep
            # the student's preferred casing from the first occurrence.
            first_display.setdefault(key, re.sub(r"\s+", " ", raw))
    if not counts:
        return None
    # Highest count wins; ties broken by first-seen order via sorted keys.
    best_key = max(counts, key=lambda k: counts[k])
    return first_display[best_key]


def name_to_filename_slug(name: str) -> str:
    """Turn a display name into a filesystem-safe slug.

    Lowercases, keeps word characters and hyphens, collapses any run of
    whitespace/underscores/hyphens into a single hyphen, and strips leading
    or trailing hyphens. Returns "student" for an empty result so callers
    never produce a path with an empty segment.
    """
    if not name:
        return "student"
    cleaned = re.sub(r"[^\w\s-]", "", name)
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned.lower() or "student"


def _normalize_name(name: str) -> str:
    """Lowercase + collapse internal whitespace, for name comparisons."""
    return re.sub(r"\s+", " ", name.strip().lower())
