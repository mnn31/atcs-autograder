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

from agcore import extractor  # noqa: E402
from agcore.grader import grade   # noqa: E402  (path tweak above)
from agcore.report import render, render_error_stub, render_overall  # noqa: E402

import config  # noqa: E402  -- local config.py next to this script


# Lab slug used in the report filename: "<student-slug>-<LAB_SLUG>-report.pdf".
LAB_SLUG = "procedures"

# Filename of the batch-level summary written next to the per-student PDFs
# when grading a whole directory.
OVERALL_FILENAME = "overall.pdf"


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


def _report_path(out_dir: Path, student_slug: str,
                 used_slugs: set[str]) -> Path:
    """Compose a unique report path of the form
    "<student-slug>-<LAB_SLUG>-report.pdf" inside out_dir.

    Collisions are possible when two students happen to share a @author
    name (or when the slug falls back to "student" for missing @authors).
    We disambiguate by appending "-2", "-3", ... so no report silently
    overwrites another.
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
               used_slugs: set[str],
               roster: list | None = None) -> Path | None:
    """Grade a single zip and return the path to the resulting PDF.

    This function must ALWAYS produce a PDF (even if grading or rendering
    fails internally) so the teacher has something to look at for every
    submission. Silent drops are worse than ugly reports.

    The output filename is derived from the most common non-teacher @author
    tag found in the student's .java sources (see extractor.py). Every
    student's zip is typically named Compiler.zip, so the zip stem alone
    isn't enough to tell submissions apart.
    """
    cfg = config.build_config(java_exe=args.java, javac_exe=args.javac)
    print(f"[ag-procedures] Grading: {zip_path.name}")

    # Step 1: extract once so we can peek at @author before running the
    # (potentially failure-prone) grading pipeline. If extraction itself
    # fails we fall back to the zip stem for the filename.
    submission = None
    try:
        submission = extractor.extract(zip_path)
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[ag-procedures]   EXTRACTION FAILED: {exc}", file=sys.stderr)
        fallback_slug = extractor.name_to_filename_slug(zip_path.stem)
        out_path = _report_path(out_dir, fallback_slug, used_slugs)
        try:
            render_error_stub(zip_path, out_path, tb)
            print(f"[ag-procedures]   -> {out_path}  (error stub)")
            if roster is not None:
                roster.append((zip_path.stem, 0.0, out_path.name))
            return out_path
        except Exception:
            traceback.print_exc()
            return None

    student_slug = submission.student_slug
    out_path = _report_path(out_dir, student_slug, used_slugs)
    print(f"[ag-procedures]   student: {submission.student_name!r} "
          f"-> {out_path.name}")

    graded = None
    try:
        graded = grade(zip_path, cfg, submission=submission)
    except Exception as exc:
        # Compile orchestration / parsing / test execution blew up. Emit
        # an error-stub PDF so the teacher sees WHY this submission
        # couldn't be graded.
        tb = traceback.format_exc()
        print(f"[ag-procedures]   GRADING FAILED (emitting stub): {exc}",
              file=sys.stderr)
        try:
            render_error_stub(zip_path, out_path, tb)
            print(f"[ag-procedures]   -> {out_path}  (error stub)")
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
        # render() itself has an internal try/except + fallback, so
        # reaching this line means we have SOME PDF at out_path -- may
        # be the rich one or the degraded plain-text dump.
        print(f"[ag-procedures]   -> {out_path}  "
              f"({graded.percent:.1f}%)")
        if roster is not None:
            roster.append((graded.submission.student_name,
                           graded.percent, out_path.name))
        return out_path
    except Exception as exc:
        print(f"[ag-procedures]   RENDER FAILED: {exc}", file=sys.stderr)
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

    # Collect the zips to grade. Non-zip files are silently ignored so a
    # teacher can point us at a Downloads folder (or unpacked share) that
    # mixes zips with stray PDFs, READMEs, .DS_Store, etc. and just have
    # it work. macOS resource-fork siblings (._Compiler.zip) are NOT real
    # zips -- the extractor would choke on them -- so we skip those too.
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
    # One entry per submission: (student_name, percent, report_filename).
    # Populated side-effectfully by _grade_one so the summary reflects
    # exactly what landed on disk -- including 0% rows for any submissions
    # that emitted only an error-stub PDF.
    roster: list[tuple[str, float, str]] = []
    for z in zips:
        if _grade_one(z, out_dir, args, used_slugs, roster) is None:
            failed += 1

    # Batch roll-up: only useful when grading more than one student at a time.
    # For a single-zip run the per-student PDF already tells the whole story.
    if len(zips) > 1 and roster:
        overall_path = out_dir / OVERALL_FILENAME
        try:
            render_overall(roster, overall_path)
            print(f"[ag-procedures] Batch summary: {overall_path}")
        except Exception as exc:
            print(f"[ag-procedures] Batch summary FAILED: {exc}",
                  file=sys.stderr)

    if failed:
        print(f"[ag-procedures] Done. {failed}/{len(zips)} report(s) failed.")
        return 1
    print(f"[ag-procedures] Done. {len(zips)} report(s) written to {out_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
