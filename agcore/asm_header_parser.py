"""
Parse the leading comment block of a MARS .asm file, the way the
ag-mips rubric needs to see it.

What we extract per file
========================
The Lab 5 handout asks every program to start with a header comment
block similar to the Java-side @author / @version style. A
well-formed header looks like:

    #
    # Reads two integers from the user and prints their product.
    #
    # Uses syscall 5 ... mflo ... syscall 1.
    #
    # @author Manan Gupta
    # @version 04/26/2026
    #

This module pulls out:

    * description    -- the prose lines from the leading # block, with
                        the leading "# " stripped.
    * author         -- value of the first `# @author <name>` line.
    * version        -- value of the first `# @version <date|str>` line.
    * has_block      -- True iff the file even has a leading # comment.
    * comment_density -- ratio of comment-bearing lines to non-blank
                         total lines. The Lab 5 PDF says "you should
                         plan on writing a comment every 2 or 3 lines",
                         so the rubric uses this ratio as a soft signal.

We intentionally do NOT try to AST-parse MIPS. The rubric only ever
needs three things from each file: "is the header doc there", "did
the student name themselves", "is there roughly the right amount of
commenting". Everything else is judged from the program's runtime
behaviour, not its structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class AsmHeader:
    """Structured view of the leading comment block of an .asm file."""

    description: str = ""
    author: Optional[str] = None
    version: Optional[str] = None
    has_block: bool = False         # any `#` lines at all at the top
    raw_lines: List[str] = field(default_factory=list)  # the # lines, verbatim


@dataclass
class AsmFileSummary:
    """Everything the rubric checkers need from one .asm file."""

    path: Path                      # absolute path on disk
    relative: str                   # path relative to the submission root
    header: AsmHeader
    total_lines: int                # non-blank lines (any kind)
    instruction_lines: int          # non-blank lines that aren't comments
    comment_lines: int              # lines that are # comments OR have an inline #
    comment_density: float          # comment_lines / max(total_lines, 1)
    parse_error: Optional[str] = None  # set if we couldn't even read the file


# Lines that look like assembler directives or labels rather than real
# instructions. Used to sanity-check "is this file completely empty of
# code" rather than to score anything. A file with header docs but zero
# instructions is almost certainly a stub.
_DIRECTIVE_RE = re.compile(r"^\s*\.\w+")
_LABEL_ONLY_RE = re.compile(r"^\s*[A-Za-z_]\w*:\s*(?:#.*)?$")
_AUTHOR_RE = re.compile(r"^\s*#\s*@author\s+(.+?)\s*$")
_VERSION_RE = re.compile(r"^\s*#\s*@version\s+(.+?)\s*$")


def parse_header(text: str) -> AsmHeader:
    """Extract description / @author / @version from a leading # block.

    The "header" is the contiguous run of `#`-prefixed lines (with
    optional empty lines between them) at the top of the file. Lines
    after the first non-`#` content line are NOT considered part of
    the header even if they happen to be comments -- a comment
    decorating an instruction in the middle of the file is not the
    file's documentation.

    @param text raw file contents.
    @return AsmHeader describing what was found.
    """
    header = AsmHeader()
    raw: List[str] = []
    desc_parts: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            # Blank lines are fine inside a # block, but only if we've
            # already seen at least one # line; otherwise we're still
            # in pre-header whitespace and continue scanning.
            if raw:
                raw.append(line)
            continue
        if not stripped.startswith("#"):
            break  # first real (non-comment, non-blank) line ends the header
        raw.append(line)
        # Recognise the @-tag lines first; everything else is description.
        m = _AUTHOR_RE.match(line)
        if m:
            if header.author is None:
                header.author = m.group(1)
            continue
        m = _VERSION_RE.match(line)
        if m:
            if header.version is None:
                header.version = m.group(1)
            continue
        # Strip the leading "#" plus optional whitespace. A bare "#"
        # line becomes an empty string -- treat it as paragraph break,
        # not as content.
        body = re.sub(r"^\s*#+\s?", "", line)
        if body.strip():
            desc_parts.append(body.strip())
    header.raw_lines = raw
    header.has_block = bool(raw)
    header.description = " ".join(desc_parts).strip()
    return header


def summarise(asm_path: Path, submission_root: Path) -> AsmFileSummary:
    """Build an AsmFileSummary for one .asm file.

    @param asm_path absolute path to the .asm file.
    @param submission_root the extracted submission root, used to
                           compute a stable relative path for display.
    @return AsmFileSummary; on read failure, parse_error is set and
            the other counts default to zero.
    """
    try:
        text = asm_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return AsmFileSummary(
            path=asm_path,
            relative=_safe_relative(asm_path, submission_root),
            header=AsmHeader(),
            total_lines=0, instruction_lines=0, comment_lines=0,
            comment_density=0.0,
            parse_error=f"could not read {asm_path.name}: {exc}",
        )

    header = parse_header(text)
    total = 0
    instructions = 0
    comments = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        total += 1
        if stripped.startswith("#"):
            comments += 1
            continue
        # Inline comment? The line counts as both an instruction line
        # AND a comment-bearing line; this matches what a teacher
        # eyeballing the file would call "well commented".
        if "#" in stripped:
            comments += 1
        # Directive (.text / .data / .globl) and bare-label lines
        # don't count as "real instructions" but they're not comment
        # lines either. We still count them in the total (so a file
        # of pure directives doesn't look 100% commented).
        if _DIRECTIVE_RE.match(line) or _LABEL_ONLY_RE.match(line):
            continue
        instructions += 1
    density = (comments / total) if total else 0.0
    return AsmFileSummary(
        path=asm_path,
        relative=_safe_relative(asm_path, submission_root),
        header=header,
        total_lines=total,
        instruction_lines=instructions,
        comment_lines=comments,
        comment_density=density,
    )


def discover_asm_files(submission_root: Path) -> List[AsmFileSummary]:
    """Find every .asm file under submission_root and summarise each.

    Non-recursive scan would miss students who nest their work in a
    `MIPS/` subfolder; we recurse but skip OS junk (`__MACOSX`, dot
    files) so we don't accidentally treat resource forks as
    submissions. Returns the list sorted by relative path for stable
    rubric output.
    """
    found: List[AsmFileSummary] = []
    for path in sorted(submission_root.rglob("*.asm")):
        # Skip macOS resource forks and hidden-directory junk.
        rel_parts = path.relative_to(submission_root).parts
        if any(p == "__MACOSX" or p.startswith("._") for p in rel_parts):
            continue
        if any(p.startswith(".") and p not in (".", "..") for p in rel_parts):
            continue
        found.append(summarise(path, submission_root))
    return found


def _safe_relative(path: Path, root: Path) -> str:
    """Best-effort relative path; falls back to the basename on mismatch.

    `Path.relative_to` raises if `path` isn't actually under `root`,
    which can happen if a caller passes in a stale root. We never want
    a display-only helper to crash a grading run, hence the guard.
    """
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name
