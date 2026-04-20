"""
Pulls a student submission out of a zip archive and locates the Compiler root
(the directory that holds ast/, parser/, scanner/, environment/, and
checkstyle.xml). Some students zip the folder itself, some zip its contents,
some leave macOS __MACOSX junk behind -- this module normalises all of that.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


REQUIRED_SUBDIRS = ("ast", "parser", "scanner", "environment")


@dataclass
class Submission:
    """The extracted, normalised view of a student's Compiler folder.

    Attributes:
        workdir: temp dir where we extracted the zip. Caller owns cleanup via
            cleanup().
        compiler_root: directory that contains ast/, parser/, scanner/, ...
        student_name: best-effort identifier scraped from the zip filename.
    """

    workdir: Path
    compiler_root: Path
    student_name: str

    def cleanup(self) -> None:
        """Wipe the temp directory created for this submission."""
        shutil.rmtree(self.workdir, ignore_errors=True)


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

    student_name = _student_name_from_zip(zip_path)
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
    """
    stem = zip_path.stem
    for junk in ("_Compiler", "_compiler", "_procedures", "_Procedures",
                 "_submission", "_Submission", "_final", "_FINAL"):
        if stem.endswith(junk):
            stem = stem[: -len(junk)]
    return stem.replace("_", " ").strip() or "Unknown Student"
