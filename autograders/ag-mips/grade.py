#!/usr/bin/env python3
"""
ag-mips: command-line autograder for the ATCS Compilers MIPS lab.

Usage:
    ag-mips STUDENT.zip [-o OUTPUT_DIR]
    ag-mips STUDENTS_DIR/ [-o OUTPUT_DIR]

Either pass a single .zip file or a directory containing many .zip
files; one PDF report is produced per submission. Reports land in
OUTPUT_DIR (default: ./reports/) and are named after the student's
@author tag (falling back to the zip basename). A batch summary
overall.pdf is generated when grading more than one submission.

The autograder needs:
    - python 3.8+ with reportlab installed (pip install -r requirements.txt)
    - a JRE on the PATH (just `java`; MARS handles assembly itself, no
      separate javac step required for the MIPS lab)
    - the bundled simulator at vendor/Mars4_5.jar

Run with --help for full options.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from pathlib import Path

# Allow running this script directly without installing the package: add
# the repository root to sys.path so "import agcore" works.
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agcore import extractor                              # noqa: E402
from agcore.mips_grader import grade                      # noqa: E402
from agcore.mips_report import render                     # noqa: E402
from agcore.report import render_error_stub, render_overall  # noqa: E402

import config                                             # noqa: E402


# Lab slug used in the report filename: "<student-slug>-<LAB_SLUG>-report.pdf".
LAB_SLUG = "mips"

# Filename of the batch-level summary written next to the per-student PDFs
# when grading a whole directory.
OVERALL_FILENAME = "overall.pdf"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ag-mips",
        description="ATCS Compilers MIPS-lab autograder. "
                    "Produces a colour-coded PDF report for each student "
                    "submission zip.",
    )
    p.add_argument("input",
                   help="Path to a student submission .zip OR a directory "
                        "containing many .zip files.")
    p.add_argument("-o", "--output", default="reports",
                   help="Directory to write PDF reports into. "
                        "Defaults to ./reports/.")
    p.add_argument("--java", default=shutil.which("java") or "java",
                   help="Path to the java executable (auto-detected by default). "
                        "Used to launch MARS in CLI mode.")
    p.add_argument("--keep-temp", action="store_true",
                   help="Don't delete the per-student temp dir after grading.")
    return p


def _report_path(out_dir: Path, student_slug: str,
                 used_slugs: "set[str]") -> Path:
    """Compose a unique '<student-slug>-mips-report.pdf' path inside out_dir.

    Same disambiguation rule as ag-procedures: append "-2", "-3", ... if
    two submissions collide (e.g. two students sharing a first/last name).
    """
    base = f"{student_slug}-{LAB_SLUG}-report"
    candidate = out_dir / f"{base}.pdf"
    n = 2
    while candidate.name in used_slugs or candidate.exists():
        candidate = out_dir / f"{base}-{n}.pdf"
        n += 1
    used_slugs.add(candidate.name)
    return candidate


def _grade_one(zip_path: Path, out_dir: Path, args,
               used_slugs: "set[str]",
               roster: list | None = None) -> Path | None:
    """Grade a single zip and return the path to the resulting PDF.

    Always produces a PDF (even on extraction or rendering failure) so
    the teacher has something to look at for every submission.
    """
    cfg = config.build_config(java_exe=args.java)
    print(f"[ag-mips] Grading: {zip_path.name}")

    submission = None
    try:
        submission = extractor.extract_mips(zip_path)
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[ag-mips]   EXTRACTION FAILED: {exc}", file=sys.stderr)
        fallback_slug = extractor.name_to_filename_slug(zip_path.stem)
        out_path = _report_path(out_dir, fallback_slug, used_slugs)
        try:
            render_error_stub(zip_path, out_path, tb)
            print(f"[ag-mips]   -> {out_path}  (error stub)")
            if roster is not None:
                roster.append((zip_path.stem, 0.0, out_path.name))
            return out_path
        except Exception:
            traceback.print_exc()
            return None

    student_slug = submission.student_slug
    out_path = _report_path(out_dir, student_slug, used_slugs)
    print(f"[ag-mips]   student: {submission.student_name!r} "
          f"-> {out_path.name}")

    graded = None
    try:
        graded = grade(zip_path, cfg, submission=submission)
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[ag-mips]   GRADING FAILED (emitting stub): {exc}",
              file=sys.stderr)
        try:
            render_error_stub(zip_path, out_path, tb)
            print(f"[ag-mips]   -> {out_path}  (error stub)")
            if roster is not None:
                roster.append((submission.student_name, 0.0, out_path.name))
            return out_path
        except Exception:
            traceback.print_exc()
            return None
        finally:
            if not args.keep_temp:
                try:
                    submission.cleanup()
                except Exception:
                    pass

    try:
        render(graded, out_path)
        print(f"[ag-mips]   -> {out_path}  ({graded.percent:.1f}%)")
        if roster is not None:
            roster.append((graded.submission.student_name,
                           graded.percent, out_path.name))
        return out_path
    except Exception as exc:
        print(f"[ag-mips]   RENDER FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return None
    finally:
        if graded is not None and not args.keep_temp:
            try:
                graded.submission.cleanup()
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        print(f"input not found: {in_path}", file=sys.stderr)
        return 2

    def _is_student_zip(p: Path) -> bool:
        return (p.is_file()
                and p.suffix.lower() == ".zip"
                and not p.name.startswith("._"))

    if in_path.is_file():
        if _is_student_zip(in_path):
            zips = [in_path]
        else:
            print(f"ignoring non-zip input: {in_path.name}", file=sys.stderr)
            zips = []
    else:
        zips = sorted(p for p in in_path.iterdir() if _is_student_zip(p))
    if not zips:
        print(f"no .zip files found under {in_path}", file=sys.stderr)
        return 2

    failed = 0
    used_slugs: set[str] = set()
    roster: list[tuple[str, float, str]] = []
    for z in zips:
        if _grade_one(z, out_dir, args, used_slugs, roster) is None:
            failed += 1

    if len(zips) > 1 and roster:
        overall_path = out_dir / OVERALL_FILENAME
        try:
            render_overall(roster, overall_path, lab_name="MIPS Lab")
            print(f"[ag-mips] Batch summary: {overall_path}")
        except Exception as exc:
            print(f"[ag-mips] Batch summary FAILED: {exc}", file=sys.stderr)

    if failed:
        print(f"[ag-mips] Done. {failed}/{len(zips)} report(s) failed.")
        return 1
    print(f"[ag-mips] Done. {len(zips)} report(s) written to {out_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
