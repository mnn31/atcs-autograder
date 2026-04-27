"""
Render a MipsGradedSubmission into a colour-coded PDF blanksheet.

Visually identical to the Procedures-lab report (same banner colours,
same Quick Review box, same rubric table look) so a teacher who
already knows how to skim a Procedures PDF can skim a MIPS PDF
without re-orienting. The differences are purely structural: there
is no checkstyle section, no per-method documentation listing, and
the appendix shows per-exercise stdout instead of per-PASCAL-test
stdout.

Robustness contract (same as report.py): we ALWAYS leave a PDF at
out_path, even if rich rendering throws -- the fallback writes a
plain-text dump so the teacher at least sees the score.
"""

from __future__ import annotations

import datetime as _dt
import traceback
from pathlib import Path
from typing import List

from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, Spacer,
                                SimpleDocTemplate, Table, TableStyle)

from .mips_grader import MipsGradedSubmission, MipsTestOutcome
# Reuse style + colour helpers so the two labs stay visually consistent.
from .report import (RED_SHADES, SCORE_BANDS, _build_styles, _shade_for,
                     _safe_escape)


MAX_APPENDIX_OUTPUT_LINES = 40
MAX_APPENDIX_STDERR_LINES = 5
MAX_PARAGRAPH_CHARS = 4000


def render(graded: MipsGradedSubmission, out_path: Path) -> Path:
    """Write a MIPS blanksheet PDF for one student.

    Returns the output path so the CLI can print it. Falls back to a
    plain-text dump if rich rendering throws.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _render_full(graded, out_path)
    except Exception:
        tb = traceback.format_exc()
        return _render_fallback(graded, out_path, tb)


# --------------------------------------------------------------------------- #
# Full-richness renderer
# --------------------------------------------------------------------------- #

def _render_full(graded: MipsGradedSubmission, out_path: Path) -> Path:
    doc = SimpleDocTemplate(
        str(out_path), pagesize=LETTER,
        leftMargin=0.55 * inch, rightMargin=0.55 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title=f"Autograder Report - {graded.submission.student_name}",
    )
    styles = _build_styles()
    story: List = []
    _add_header(story, graded, styles)
    _add_at_a_glance(story, graded, styles)
    _add_quick_review(story, graded, styles)
    _add_environment_warnings(story, graded, styles)
    _add_rubric_table(story, graded, styles)
    story.append(PageBreak())
    _add_file_inventory(story, graded, styles)
    story.append(Spacer(1, 10))
    _add_test_appendix(story, graded, styles)
    doc.build(story)
    return out_path


def _add_header(story, graded, styles):
    cfg = graded.config
    story.append(Paragraph(
        "<b>ATCS - Compilers and Interpreters: Autograder Report</b>",
        styles["h1"]))
    story.append(Paragraph(f"<b>Lab:</b> {cfg.lab_name}", styles["body"]))
    story.append(Paragraph(
        f"<b>Student (from # @author tag):</b> "
        f"{_safe_escape(graded.submission.student_name)}",
        styles["body"]))
    story.append(Paragraph(
        f"<b>Graded on:</b> {_dt.datetime.now():%Y-%m-%d %H:%M}",
        styles["body"]))
    story.append(Spacer(1, 6))


def _at_a_glance_cell(label, value, color, styles):
    """One coloured cell for the top-of-page banner."""
    return Table(
        [[Paragraph(f"<b>{label}</b>", styles["small"])],
         [Paragraph(value, styles["small"])]],
        colWidths=[1.45 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), color),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]),
    )


def _add_at_a_glance(story, graded, styles):
    """Five-cell banner: Overall, Files, Exercises Run, Tests Pass, Header Docs.

    Mirrors the Procedures-lab six-cell banner (Build / Rubric / Tests /
    Checkstyle / Docs) but with MIPS-relevant cells. Build doesn't apply
    -- MARS assembles per-file as part of running -- so we replace it
    with "Files Found".
    """
    pct = graded.percent
    rubric_fails = sum(1 for gi in graded.graded_items
                       if gi.earned < gi.item.points)
    n_files = len(graded.asm_files)
    n_roles = len(graded.config.file_roles)
    matched = sum(1 for m in graded.role_matches.values()
                  if m.file is not None)
    test_total = sum(len(v) for v in graded.test_outcomes.values())
    test_passed = sum(1 for v in graded.test_outcomes.values()
                      for t in v if t.passed)
    header_total = sum(1 for f in graded.asm_files if f.header.has_block)

    green = Color(0.80, 0.94, 0.80)
    amber = Color(0.99, 0.93, 0.78)
    red = Color(1.00, 0.78, 0.76)
    white = Color(1.00, 1.00, 1.00)

    def band(good, ok):
        return green if good else (amber if ok else red)

    overall_color = (green if pct >= 90 else
                     amber if pct >= 75 else red)
    files_color = band(matched == n_roles, matched >= max(1, n_roles - 1))
    rubric_color = band(rubric_fails == 0, rubric_fails <= 2)
    tests_color = (white if test_total == 0
                   else band(test_passed == test_total,
                             test_passed >= max(1, test_total - 1)))
    docs_color = (band(header_total == n_files, header_total >= max(1, n_files - 1))
                  if n_files else white)

    cells = [
        _at_a_glance_cell("Overall",
                          f"{pct:.1f}%", overall_color, styles),
        _at_a_glance_cell("Exercises matched",
                          f"{matched} / {n_roles}", files_color, styles),
        _at_a_glance_cell("Rubric flags",
                          f"{rubric_fails} of {len(graded.graded_items)} "
                          f"not full credit", rubric_color, styles),
        _at_a_glance_cell("Tests passed",
                          (f"{test_passed} / {test_total}" if test_total
                           else "n/a"), tests_color, styles),
        _at_a_glance_cell("Header docs",
                          (f"{header_total} / {n_files}"
                           if n_files else "no .asm files"),
                          docs_color, styles),
    ]
    banner = Table([cells], colWidths=[1.45 * inch] * 5,
                   style=TableStyle([
                       ("LEFTPADDING", (0, 0), (-1, -1), 0),
                       ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                       ("TOPPADDING", (0, 0), (-1, -1), 0),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                   ]))
    story.append(banner)
    story.append(Spacer(1, 8))


def _quick_review_lines(graded):
    """3-5 short bullets summarising what's worth a teacher's attention."""
    lines: List[str] = []
    lines.append(f"Files found: {len(graded.asm_files)} .asm.")
    matched = sum(1 for m in graded.role_matches.values()
                  if m.file is not None)
    lines.append(
        f"Rubric exercises matched to a file: "
        f"{matched} of {len(graded.config.file_roles)}.")
    test_total = sum(len(v) for v in graded.test_outcomes.values())
    test_passed = sum(1 for v in graded.test_outcomes.values()
                      for t in v if t.passed)
    if test_total:
        lines.append(f"Hidden output tests passed: "
                     f"{test_passed} / {test_total}.")
    fails = [gi for gi in graded.graded_items
             if gi.earned < gi.item.points]
    if fails:
        worst = sorted(fails, key=lambda g: g.item.points - g.earned,
                       reverse=True)[:3]
        previews = ", ".join(g.item.code for g in worst)
        lines.append(f"Biggest rubric losses: {previews}.")
    return lines


def _add_quick_review(story, graded, styles):
    pct = graded.percent
    band_color = next((c for thresh, c in SCORE_BANDS if pct >= thresh),
                      RED_SHADES[3])
    body = "<br/>".join(f"&bull; {line}" for line in _quick_review_lines(graded))
    body += (f"<br/><br/><b>Overall:</b> "
             f"{graded.total_earned:.1f} / {graded.total_possible:.1f} "
             f"({pct:.1f}%)")
    box = Table(
        [[Paragraph(body, styles["body"])]],
        colWidths=[7.4 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), band_color),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]),
    )
    story.append(box)
    story.append(Spacer(1, 8))


def _add_environment_warnings(story, graded, styles):
    """Surface fatal-environment notes (e.g. java missing) BEFORE the rubric
    so the teacher knows why every behavioural row may be zero.
    """
    if not graded.environment_notes:
        return
    body = "<br/>".join(f"&bull; {_safe_escape(n)}"
                       for n in graded.environment_notes)
    box = Table(
        [[Paragraph(f"<b>Environment notes</b><br/>{body}", styles["body"])]],
        colWidths=[7.4 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), Color(1.00, 0.85, 0.78)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]),
    )
    story.append(box)
    story.append(Spacer(1, 8))


def _add_rubric_table(story, graded, styles):
    """One row per RubricItem, severity-shaded like Procedures."""
    header = [
        Paragraph("<b>#</b>", styles["small"]),
        Paragraph("<b>Rubric Item</b>", styles["small"]),
        Paragraph("<b>Earned / Possible</b>", styles["small"]),
        Paragraph("<b>Notes</b>", styles["small"]),
    ]
    data = [header]
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.85, 0.85, 0.85)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, gi in enumerate(graded.graded_items, start=1):
        review_tag = ""
        if 0 < gi.earned < gi.item.points:
            review_tag = " <b>[REVIEW]</b>"
        data.append([
            Paragraph(str(i), styles["small"]),
            Paragraph(_safe_escape(gi.item.description) + review_tag,
                      styles["small"]),
            Paragraph(f"{gi.earned:.1f} / {gi.item.points:.1f}",
                      styles["small"]),
            Paragraph(_safe_escape(gi.notes or ""), styles["small"]),
        ])
        if gi.severity > 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i),
                               _shade_for(gi.severity)))
    table = Table(
        data,
        colWidths=[0.3 * inch, 3.4 * inch, 1.0 * inch, 2.7 * inch],
        repeatRows=1,
    )
    table.setStyle(TableStyle(style_cmds))
    story.append(table)


def _add_file_inventory(story, graded, styles):
    """Per-file table: name, header doc presence, density, rubric binding."""
    story.append(Paragraph("<b>.asm File Inventory</b>", styles["h2"]))
    story.append(Paragraph(
        "Every .asm file the autograder discovered in the submission. "
        "The 'Bound to' column shows which rubric exercise this file "
        "fulfils, if any. Files with no binding still count toward the "
        "header-docs and comment-density rows.",
        styles["meta"]))
    # Reverse-index role matches by file path so we can show bindings.
    bindings: dict = {}
    for role, match in graded.role_matches.items():
        if match.file is not None:
            bindings.setdefault(match.file.relative, []).append(role)
    header = [
        Paragraph("<b>File</b>", styles["small"]),
        Paragraph("<b>Header doc</b>", styles["small"]),
        Paragraph("<b>@author</b>", styles["small"]),
        Paragraph("<b>@version</b>", styles["small"]),
        Paragraph("<b>Inst.</b>", styles["small"]),
        Paragraph("<b>Cmt %</b>", styles["small"]),
        Paragraph("<b>Bound to</b>", styles["small"]),
    ]
    data = [header]
    for f in graded.asm_files:
        bound = ", ".join(bindings.get(f.relative, [])) or "(unused)"
        data.append([
            Paragraph(_safe_escape(f.relative), styles["small"]),
            Paragraph("yes" if f.header.has_block else "no",
                      styles["small"]),
            Paragraph(_safe_escape(f.header.author or "—"),
                      styles["small"]),
            Paragraph(_safe_escape(f.header.version or "—"),
                      styles["small"]),
            Paragraph(str(f.instruction_lines), styles["small"]),
            Paragraph(f"{int(f.comment_density * 100)}%",
                      styles["small"]),
            Paragraph(_safe_escape(bound), styles["small"]),
        ])
    table = Table(data, colWidths=[
        1.7 * inch, 0.7 * inch, 1.1 * inch, 0.9 * inch,
        0.5 * inch, 0.5 * inch, 1.7 * inch,
    ], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.85, 0.85, 0.85)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)


def _add_test_appendix(story, graded, styles):
    """Per-exercise: description, stdin, expected substrings, actual stdout."""
    story.append(Paragraph(
        "<b>Appendix: Hidden Test Suite</b>", styles["h2"]))
    story.append(Paragraph(
        "For every rubric exercise that has hidden tests, this appendix "
        "shows the input the autograder fed in, the expected substrings, "
        "and the student's actual stdout. Pass cells are green; fail cells "
        "are red. This is a teacher-only reference.",
        styles["meta"]))
    story.append(Spacer(1, 4))
    green = Color(0.82, 0.95, 0.82)
    red = Color(1.00, 0.80, 0.78)
    for role, outcomes in graded.test_outcomes.items():
        if not outcomes:
            continue
        match = graded.role_matches.get(role)
        file_label = match.file.relative if match and match.file else "(missing)"
        story.append(Paragraph(
            f"<b>{_safe_escape(role)}</b> &nbsp; "
            f"<i>file:</i> {_safe_escape(file_label)}",
            styles["body"]))
        for t in outcomes:
            verdict = "PASS" if t.passed else "FAIL"
            cell_color = green if t.passed else red
            stdin_show = _clip(t.spec.stdin_text or "(no stdin)", 200)
            expected_show = (" -> ".join(repr(s)
                                         for s in t.spec.expected_substrings)
                             or "(any output)")
            actual_show = _clip(_truncate_lines(
                t.stdout.strip() or "(empty)", MAX_APPENDIX_OUTPUT_LINES), 800)
            err_show = _clip(_truncate_lines(
                t.stderr.strip() or "", MAX_APPENDIX_STDERR_LINES), 400)
            note_show = t.error or ""
            data = [
                [Paragraph(f"<b>{verdict}</b> &nbsp; {_safe_escape(t.spec.name)}"
                           f" &mdash; {_safe_escape(t.spec.description)}",
                           styles["small"])],
                [Paragraph("<b>stdin:</b> " + _safe_escape(stdin_show),
                           styles["mono"])],
                [Paragraph("<b>expected substrings (in order):</b> "
                           + _safe_escape(expected_show), styles["small"])],
                [Paragraph("<b>actual stdout:</b><br/>"
                           + _safe_escape(actual_show).replace("\n", "<br/>"),
                           styles["mono"])],
            ]
            if err_show:
                data.append([Paragraph(
                    "<b>stderr:</b><br/>"
                    + _safe_escape(err_show).replace("\n", "<br/>"),
                    styles["mono"])])
            if note_show:
                data.append([Paragraph(
                    "<b>note:</b> " + _safe_escape(_clip(note_show, 240)),
                    styles["small"])])
            tbl = Table(data, colWidths=[7.3 * inch])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cell_color),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(KeepTogether([tbl, Spacer(1, 4)]))


# --------------------------------------------------------------------------- #
# Fallback renderer
# --------------------------------------------------------------------------- #

def _render_fallback(graded: MipsGradedSubmission, out_path: Path,
                     traceback_text: str) -> Path:
    """Plain-text dump PDF used when the rich renderer throws.

    Same contract as report._render_fallback: ALWAYS leave a PDF (or a
    .FAILED.txt sidecar in the very-very-worst case).
    """
    try:
        doc = SimpleDocTemplate(
            str(out_path), pagesize=LETTER,
            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
            title=f"Autograder Report (FALLBACK) - "
                  f"{graded.submission.student_name}",
        )
        styles = _build_styles()
        story = [
            Paragraph("<b>ATCS Compilers Autograder &mdash; "
                      "MIPS Degraded Report</b>", styles["h1"]),
            Paragraph("Rich renderer failed; emitting plain-text dump.",
                      styles["body"]),
            Paragraph(
                f"Student: {_safe_escape(graded.submission.student_name)}",
                styles["body"]),
            Paragraph(
                f"Lab: {_safe_escape(graded.config.lab_name)}",
                styles["body"]),
            Paragraph(f"Score: {graded.total_earned:.1f} / "
                      f"{graded.total_possible:.1f} ({graded.percent:.1f}%)",
                      styles["body"]),
            Spacer(1, 6),
            Paragraph("<b>Rubric</b>", styles["h2"]),
        ]
        for gi in graded.graded_items:
            story.append(Paragraph(
                f"[{gi.earned:.1f}/{gi.item.points:.1f}] "
                f"{_safe_escape(gi.item.description)} "
                + (f"&mdash; {_safe_escape(gi.notes)}" if gi.notes else ""),
                styles["small"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>Traceback</b>", styles["h2"]))
        story.append(Paragraph(
            _safe_escape(_clip(traceback_text, 2000)).replace("\n", "<br/>"),
            styles["mono"]))
        doc.build(story)
        return out_path
    except Exception:
        try:
            out_path.with_suffix(".FAILED.txt").write_text(
                f"MIPS autograder rendering failed for "
                f"{graded.submission.student_name}.\n\n{traceback_text}\n",
                encoding="utf-8")
        except Exception:
            pass
        return out_path


# --------------------------------------------------------------------------- #
# Tiny helpers
# --------------------------------------------------------------------------- #

def _clip(text: str, limit: int) -> str:
    """Truncate text to limit chars, marking truncation."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 12)] + " ...[clip]..."


def _truncate_lines(text: str, limit: int) -> str:
    """Keep the first `limit` lines of text, marking truncation."""
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    head = "\n".join(lines[:limit])
    return head + f"\n...[{len(lines) - limit} more lines clipped]..."
