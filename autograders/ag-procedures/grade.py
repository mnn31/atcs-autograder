#!/usr/bin/env python3
"""
ag-procedures: command-line autograder for the ATCS Compilers PROCEDURES lab.

Usage:
    ag-procedures STUDENT.zip [-o OUTPUT_DIR]
    ag-procedures STUDENTS_DIR/ [-o OUTPUT_DIR]

Either pass a single .zip file or a directory containing many .zip files;
one PDF report is produced per submission. The reports are placed under
OUTPUT_DIR (default: ./reports/) and named after the zip basename.

The autograder needs:
    - python 3.8+ with reportlab and javalang
    - a JDK on the PATH (javac + java)
    - the bundled checkstyle jar at vendor/checkstyle-10.14.0-all.jar

Run with --help for full options.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from pathlib import Path

# Allow running this script directly without installing the package: add the
# repository root to sys.path so "import agcore" works.
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agcore.grader import grade   # noqa: E402  (path tweak above)
from agcore.report import render  # noqa: E402

import config  # noqa: E402  -- local config.py next to this script


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ag-procedures",
        description="ATCS Compilers Procedures-lab autograder. "
                    "Produces a colour-coded PDF report for each "
                    "student submission zip.",
    )
    p.add_argument("input",
                   help="Path to a student submission .zip OR a directory "
                        "containing many .zip files.")
    p.add_argument("-o", "--output", default="reports",
                   help="Directory to write PDF reports into. "
                        "Defaults to ./reports/.")
    p.add_argument("--java", default=shutil.which("java") or "java",
                   help="Path to the java executable (auto-detected by default).")
    p.add_argument("--javac", default=shutil.which("javac") or "javac",
                   help="Path to the javac executable (auto-detected by default).")
    p.add_argument("--keep-temp", action="store_true",
                   help="Don't delete the per-student temp dir after grading "
                        "(useful for debugging a weird submission).")
    return p


def _grade_one(zip_path: Path, out_dir: Path, args) -> Path | None:
    """Grade a single zip and return the path to the resulting PDF."""
    cfg = config.build_config(java_exe=args.java, javac_exe=args.javac)
    print(f"[ag-procedures] Grading: {zip_path.name}")
    graded = None
    try:
        graded = grade(zip_path, cfg)
        out_path = out_dir / f"{zip_path.stem}_procedures_report.pdf"
        render(graded, out_path)
        print(f"[ag-procedures]   -> {out_path}  "
              f"({graded.percent:.1f}%)")
        return out_path
    except Exception as exc:
        print(f"[ag-procedures]   FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return None
    finally:
        if graded is not None and not args.keep_temp:
            graded.submission.cleanup()


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        print(f"input not found: {in_path}", file=sys.stderr)
        return 2

    if in_path.is_file():
        zips = [in_path]
    else:
        zips = sorted(p for p in in_path.glob("*.zip") if p.is_file())
    if not zips:
        print(f"no .zip files found under {in_path}", file=sys.stderr)
        return 2

    failed = 0
    for z in zips:
        if _grade_one(z, out_dir, args) is None:
            failed += 1
    if failed:
        print(f"[ag-procedures] Done. {failed}/{len(zips)} report(s) failed.")
        return 1
    print(f"[ag-procedures] Done. {len(zips)} report(s) written to {out_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
