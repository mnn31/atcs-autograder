"""
Renders a GradedSubmission into a colour-coded PDF blanksheet. Every
submission produces the same template (rubric, test cases, documentation
listing, quick review box) so the teacher can scan it for red cells without
re-orienting per student.

We intentionally include no student code in the PDF -- only method names,
their doc summaries, and free-text notes. This matches the lab requirement.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import List, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, Spacer,
                                SimpleDocTemplate, Table, TableStyle)

from .grader import GradedSubmission, TestOutcome
from .proximity import ProximityFinding
from .rubric import GradedItem


# Red-severity colour palette: none, minor, medium, major. Deliberately light
# so black text stays legible.
RED_SHADES = [
    Color(1.00, 1.00, 1.00),   # 0 = clean (transparent-ish white)
    Color(1.00, 0.92, 0.88),   # 1 = minor pink
    Color(1.00, 0.76, 0.72),   # 2 = medium red
    Color(1.00, 0.55, 0.52),   # 3 = major red
]

# Background for "quick review" summary when overall score dips.
SCORE_BANDS = [
    (90, Color(0.82, 0.95, 0.82)),   # green
    (75, Color(0.98, 0.95, 0.78)),   # amber
    (0,  Color(1.00, 0.80, 0.78)),   # red
]


def _shade_for(severity: int) -> Color:
    """Pick a row-background colour from the RED_SHADES palette."""
    return RED_SHADES[max(0, min(3, severity))]


def render(graded: GradedSubmission, out_path: Path) -> Path:
    """Write the blanksheet PDF for one student.

    Returns the output path so the CLI can print it.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

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
    _add_rubric_table(story, graded, styles)
    story.append(PageBreak())
    _add_test_cases(story, graded, styles)
    story.append(Spacer(1, 12))
    _add_checkstyle_details(story, graded, styles)
    story.append(PageBreak())
    _add_doc_listing(story, graded, styles)
    _add_quick_review(story, graded, styles)

    doc.build(story)
    return out_path


def _build_styles() -> dict:
    """Paragraph styles used across the report."""
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontSize=16, spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=12, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=9, leading=11,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontSize=7.5, leading=9,
            textColor=colors.black,
        ),
        "mono": ParagraphStyle(
            "mono", parent=base["BodyText"], fontName="Courier",
            fontSize=8, leading=10,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["BodyText"], fontSize=9, leading=11,
            textColor=colors.grey,
        ),
        "red": ParagraphStyle(
            "red", parent=base["BodyText"], fontSize=9, leading=11,
            textColor=colors.darkred,
        ),
    }


def _add_header(story: List, graded: GradedSubmission, styles: dict) -> None:
    cfg = graded.config
    header_rows = [
        [Paragraph("<b>ATCS - Compilers and Interpreters: Autograder Report</b>",
                   styles["h1"])],
        [Paragraph(f"<b>Lab:</b> {cfg.lab_name}", styles["body"])],
        [Paragraph(
            f"<b>Student (inferred from filename):</b> "
            f"{graded.submission.student_name}",
            styles["body"],
        )],
        [Paragraph(
            f"<b>Graded on:</b> {_dt.datetime.now():%Y-%m-%d %H:%M}",
            styles["body"],
        )],
    ]
    story.extend([row[0] for row in header_rows])
    story.append(Spacer(1, 6))


def _add_at_a_glance(story: List, graded: GradedSubmission,
                     styles: dict) -> None:
    """Top-of-page-1 four-cell banner so a teacher sees the verdict before
    scrolling. Each cell is coloured by severity of its section.
    """
    rubric_fails = sum(1 for gi in graded.graded_items
                       if gi.earned < gi.item.points)
    test_total = len(graded.test_outcomes)
    test_passed = sum(1 for t in graded.test_outcomes if t.passed)
    cs_total = len(graded.checkstyle.violations)
    member_total = sum(1 + len(c.methods) for c in graded.classes)
    doc_fails = sum(1 for f in graded.proximity if not f.passed)

    compile_ok = graded.compile_result.success
    percent = graded.percent

    # Shared palette -- green / amber / red / white (white == neutral / no data).
    green = Color(0.80, 0.94, 0.80)
    amber = Color(0.99, 0.93, 0.78)
    red_c = Color(1.00, 0.78, 0.76)
    grey = Color(0.93, 0.93, 0.93)

    def cell(title: str, value: str, bg: Color):
        return Table(
            [[Paragraph(f"<b>{title}</b>", styles["small"])],
             [Paragraph(f"<b>{value}</b>", styles["body"])]],
            colWidths=[1.75 * inch],
            style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]),
        )

    # Overall score cell (wins real estate over the four sub-badges).
    score_bg = (green if percent >= 90 else amber if percent >= 75 else red_c)
    score_cell = cell("Overall", f"{percent:.1f}%", score_bg)

    compile_bg = green if compile_ok else red_c
    compile_val = "compiled" if compile_ok else "COMPILE FAIL"
    compile_cell = cell("Build", compile_val, compile_bg)

    rubric_bg = (green if rubric_fails == 0
                 else amber if rubric_fails <= 2 else red_c)
    rubric_val = (f"{len(graded.graded_items) - rubric_fails}/"
                  f"{len(graded.graded_items)} full-credit")
    rubric_cell = cell("Rubric", rubric_val, rubric_bg)

    if test_total == 0:
        test_bg, test_val = grey, "no tests"
    elif test_passed == test_total:
        test_bg, test_val = green, f"{test_passed}/{test_total} pass"
    elif test_passed >= test_total // 2:
        test_bg, test_val = amber, f"{test_passed}/{test_total} pass"
    else:
        test_bg, test_val = red_c, f"{test_passed}/{test_total} pass"
    test_cell = cell("Tests", test_val, test_bg)

    cs_bg = (green if cs_total == 0
             else amber if cs_total <= 5 else red_c)
    cs_val = "clean" if cs_total == 0 else f"{cs_total} issue(s)"
    cs_cell = cell("Checkstyle", cs_val, cs_bg)

    docs_bg = (green if doc_fails == 0
               else amber if doc_fails <= 3 else red_c)
    docs_val = (f"{member_total - doc_fails}/{member_total} ok"
                if member_total else "no docs")
    docs_cell = cell("Docs", docs_val, docs_bg)

    banner = Table(
        [[score_cell, compile_cell, rubric_cell, test_cell, cs_cell,
          docs_cell]],
        colWidths=[1.25 * inch] * 6,
        style=TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    )
    story.append(banner)
    story.append(Spacer(1, 10))


def _add_rubric_table(story: List, graded: GradedSubmission,
                      styles: dict) -> None:
    rubric_fails = sum(1 for gi in graded.graded_items
                       if gi.earned < gi.item.points)
    story.append(Paragraph("Peer Checkoff Rubric", styles["h2"]))
    story.append(Paragraph(
        f"{len(graded.graded_items)} items &middot; "
        f"{rubric_fails} partial / missed. "
        "Rows in red were NOT awarded full credit. Darker red = more "
        "severe. Items with partial credit are flagged <b>REVIEW</b> in "
        "the Notes column -- a human should confirm.",
        styles["small"],
    ))
    story.append(Spacer(1, 4))

    rows: List[List] = [[
        Paragraph("<b>#</b>", styles["small"]),
        Paragraph("<b>Check</b>", styles["small"]),
        Paragraph("<b>Earned / Possible</b>", styles["small"]),
        Paragraph("<b>Notes</b>", styles["small"]),
    ]]
    row_colours: List[Tuple[int, Color]] = []
    for idx, gi in enumerate(graded.graded_items, start=1):
        note = gi.notes or ""
        # Flag partial-credit rows so teachers can distinguish "auto-flunked"
        # from "needs a human to read the student code" at a glance.
        if 0 < gi.earned < gi.item.points:
            note = ("<b>REVIEW:</b> " + note) if note else "<b>REVIEW</b>"
        rows.append([
            Paragraph(str(idx), styles["small"]),
            Paragraph(gi.item.description, styles["small"]),
            Paragraph(f"{gi.earned:.1f} / {gi.item.points:.1f}",
                      styles["small"]),
            Paragraph(note, styles["small"]),
        ])
        if gi.earned < gi.item.points:
            row_colours.append((idx, _shade_for(gi.severity or 2)))
    table = Table(rows, colWidths=[0.3 * inch, 4.2 * inch,
                                   1.0 * inch, 2.0 * inch])
    style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.85, 0.85, 0.85)),
    ]
    for row_idx, colour in row_colours:
        style_cmds.append(
            ("BACKGROUND", (0, row_idx), (-1, row_idx), colour)
        )
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(Spacer(1, 8))

    total = (f"<b>Rubric total:</b> {graded.total_earned:.1f} / "
             f"{graded.total_possible:.1f} "
             f"({graded.percent:.1f}%)")
    story.append(Paragraph(total, styles["body"]))


def _add_test_cases(story: List, graded: GradedSubmission,
                    styles: dict) -> None:
    story.append(Paragraph("Internal Functional Test Cases", styles["h2"]))
    story.append(Paragraph(
        "These PASCAL programs are kept secret from students. A failed test "
        "(red) means the student's compiled interpreter produced the wrong "
        "output, crashed, or timed out. The exact error is shown; no student "
        "code is reproduced.",
        styles["small"],
    ))
    story.append(Spacer(1, 4))

    if not graded.compile_result.success:
        story.append(Paragraph(
            "<b>Compile failure</b> -- tests could not run. Compiler error "
            "summary:", styles["red"],
        ))
        err = graded.compile_result.errors or "unknown javac error"
        story.append(Paragraph(
            _first_n_lines(err, 8, placeholder=True),
            styles["mono"],
        ))
        story.append(Spacer(1, 6))

    rows: List[List] = [[
        Paragraph("<b>#</b>", styles["small"]),
        Paragraph("<b>Test</b>", styles["small"]),
        Paragraph("<b>Description</b>", styles["small"]),
        Paragraph("<b>Result</b>", styles["small"]),
        Paragraph("<b>Error / Notes</b>", styles["small"]),
    ]]
    row_colours: List[Tuple[int, Color]] = []
    for idx, outcome in enumerate(graded.test_outcomes, start=1):
        verdict = "PASS" if outcome.passed else "FAIL"
        error_cell = _test_error_cell(outcome, styles)
        rows.append([
            Paragraph(str(idx), styles["small"]),
            Paragraph(outcome.case.name, styles["small"]),
            Paragraph(outcome.case.description, styles["small"]),
            Paragraph(f"<b>{verdict}</b>", styles["small"]),
            error_cell,
        ])
        if not outcome.passed:
            severity = 3 if outcome.timed_out or "runtime error" in (
                outcome.error or "") else 2
            row_colours.append((idx, _shade_for(severity)))
    table = Table(rows, colWidths=[0.3 * inch, 1.1 * inch, 2.3 * inch,
                                   0.6 * inch, 3.2 * inch])
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.85, 0.85, 0.85)),
    ]
    for row_idx, colour in row_colours:
        cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colour))
    table.setStyle(TableStyle(cmds))
    story.append(table)


def _test_error_cell(outcome: TestOutcome, styles: dict):
    """Build the 'Error / Notes' cell for one test case."""
    if outcome.passed:
        return Paragraph("", styles["small"])
    lines: List[str] = []
    if outcome.error:
        lines.append(f"<b>{_escape(outcome.error)}</b>")
    if outcome.stderr:
        lines.append(_escape(_first_n_lines(outcome.stderr, 3)))
    if not lines:
        lines.append("output did not match expected")
    return Paragraph("<br/>".join(lines), styles["small"])


def _add_checkstyle_details(story: List, graded: GradedSubmission,
                            styles: dict) -> None:
    """New section: list concrete checkstyle hits (file:line:rule).

    Capped at 20 rows so a noisy submission doesn't blow the page budget;
    the at-a-glance banner already reports the total count.
    """
    violations = graded.checkstyle.violations
    story.append(Paragraph("Checkstyle Details", styles["h2"]))
    if graded.checkstyle.error:
        story.append(Paragraph(
            f"<b>Checkstyle did not run:</b> "
            f"{_escape(graded.checkstyle.error)}",
            styles["red"],
        ))
        return
    if not violations:
        story.append(Paragraph(
            "No violations against the bundled <i>checkstyle.xml</i>.",
            styles["small"],
        ))
        return
    cap = 20
    shown = violations[:cap]
    story.append(Paragraph(
        f"{len(violations)} violation(s) -- "
        f"showing first {len(shown)}. Grouped rule frequencies are in the "
        "Quick Review box at the end of the report.",
        styles["small"],
    ))
    story.append(Spacer(1, 4))
    rows: List[List] = [[
        Paragraph("<b>#</b>", styles["small"]),
        Paragraph("<b>File</b>", styles["small"]),
        Paragraph("<b>Line</b>", styles["small"]),
        Paragraph("<b>Rule</b>", styles["small"]),
        Paragraph("<b>Message</b>", styles["small"]),
    ]]
    for idx, v in enumerate(shown, start=1):
        rows.append([
            Paragraph(str(idx), styles["small"]),
            Paragraph(_escape(_short_path(v.path)), styles["small"]),
            Paragraph(str(v.line or ""), styles["small"]),
            Paragraph(_escape(v.rule), styles["small"]),
            Paragraph(_escape(_clip(v.message, 180)), styles["small"]),
        ])
    table = Table(rows, colWidths=[0.3 * inch, 1.8 * inch, 0.5 * inch,
                                   1.5 * inch, 3.4 * inch])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.85, 0.85, 0.85)),
    ]))
    story.append(table)


def _short_path(path: str) -> str:
    """Trim an absolute path to the Compiler/... suffix for readability."""
    parts = path.replace("\\", "/").split("/")
    try:
        idx = parts.index("Compiler")
        return "/".join(parts[idx:])
    except ValueError:
        return "/".join(parts[-3:])


def _add_doc_listing(story: List, graded: GradedSubmission,
                     styles: dict) -> None:
    member_total = sum(1 + len(c.methods) for c in graded.classes)
    doc_fails = sum(1 for f in graded.proximity if not f.passed)
    story.append(Paragraph("Documentation Review", styles["h2"]))
    story.append(Paragraph(
        f"{member_total} members checked &middot; "
        f"{doc_fails} flagged. "
        "Every class and method the autograder found, with the result of "
        "javadoc keyword-proximity and @-tag checks. Rows in red are "
        "candidates for manual review. The Location column is file:line.",
        styles["small"],
    ))
    story.append(Spacer(1, 4))
    findings_by_target = {f.target: f for f in graded.proximity}

    rows: List[List] = [[
        Paragraph("<b>Class</b>", styles["small"]),
        Paragraph("<b>Member</b>", styles["small"]),
        Paragraph("<b>Doc / Keywords</b>", styles["small"]),
        Paragraph("<b>Location</b>", styles["small"]),
        Paragraph("<b>Status</b>", styles["small"]),
    ]]
    row_colours: List[Tuple[int, Color]] = []
    row_idx = 0
    for cls in graded.classes:
        row_idx += 1
        cls_target = f"{cls.name} (class)"
        cls_finding = findings_by_target.get(cls_target)
        rows.append(_class_row(cls, cls_finding, styles))
        if cls_finding and not cls_finding.passed:
            row_colours.append((row_idx, _shade_for(cls_finding.severity)))
        for m in cls.methods:
            row_idx += 1
            m_target = f"{cls.name}.{m.method_name}"
            m_finding = findings_by_target.get(m_target)
            rows.append(_method_row(m, m_finding, styles))
            if m_finding and not m_finding.passed:
                row_colours.append((row_idx, _shade_for(m_finding.severity)))
    if not graded.classes:
        rows.append([
            Paragraph("(none parsed)", styles["small"]),
            Paragraph("", styles["small"]),
            Paragraph("No classes could be parsed -- check for syntax errors.",
                      styles["red"]),
            Paragraph("", styles["small"]),
            Paragraph("FAIL", styles["small"]),
        ])
        row_colours.append((1, _shade_for(3)))

    table = Table(rows, colWidths=[1.05 * inch, 1.55 * inch, 2.95 * inch,
                                   0.95 * inch, 1.0 * inch], repeatRows=1)
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.85, 0.85, 0.85)),
    ]
    for row_n, colour in row_colours:
        cmds.append(("BACKGROUND", (0, row_n), (-1, row_n), colour))
    table.setStyle(TableStyle(cmds))
    story.append(table)
    story.append(Spacer(1, 8))


def _class_row(cls, finding, styles) -> List:
    doc_snippet = (cls.javadoc.description.strip()
                   if cls.javadoc else "(no class javadoc)")
    doc_snippet = _clip(doc_snippet, 180)
    status = _status_text(finding, default="CLASS")
    location = f"{_short_path(cls.file)}:{cls.line}"
    return [
        Paragraph(f"<b>{_escape(cls.name)}</b>", styles["small"]),
        Paragraph("<i>class header</i>", styles["small"]),
        Paragraph(_escape(doc_snippet), styles["small"]),
        Paragraph(_escape(location), styles["small"]),
        Paragraph(status, styles["small"]),
    ]


def _method_row(method, finding, styles) -> List:
    doc = method.javadoc
    if doc is None:
        doc_snippet = "(no javadoc)"
    else:
        desc = doc.description.strip()
        tag_summary = ", ".join(
            f"{t.tag}{' ' + t.arg if t.arg else ''}" for t in doc.tags
        )
        doc_snippet = desc
        if tag_summary:
            doc_snippet = f"{desc} [{tag_summary}]"
    doc_snippet = _clip(doc_snippet, 220)
    sig = (f"{method.method_name}("
           f"{', '.join(method.params) if method.params else ''}) "
           f"&rarr; {_escape(method.return_type)}")
    status = _status_text(finding, default="OK")
    location = f"{_short_path(method.file)}:{method.line}"
    return [
        Paragraph(_escape(method.class_name), styles["small"]),
        Paragraph(sig, styles["small"]),
        Paragraph(_escape(doc_snippet), styles["small"]),
        Paragraph(_escape(location), styles["small"]),
        Paragraph(status, styles["small"]),
    ]


def _status_text(finding: ProximityFinding | None, default: str) -> str:
    """Human verdict shown in the Status column."""
    if finding is None:
        return default
    if finding.passed:
        return "OK"
    if finding.note:
        return f"<b>REVIEW</b><br/>{_escape(finding.note)}"
    return "<b>REVIEW</b>"


def _add_quick_review(story: List, graded: GradedSubmission,
                      styles: dict) -> None:
    story.append(Spacer(1, 10))
    story.append(Paragraph("Quick Review", styles["h2"]))

    lines = _quick_review_lines(graded)
    body = "<br/>".join(_escape(l) for l in lines)
    percent = graded.percent
    final_bg = _score_band(percent)
    score_line = (f"<b>Overall score:</b> {graded.total_earned:.1f} / "
                  f"{graded.total_possible:.1f} "
                  f"({percent:.1f}%)")
    table = Table([
        [Paragraph(score_line, styles["body"])],
        [Paragraph(body, styles["small"])],
    ], colWidths=[7.4 * inch])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), final_bg),
        ("BACKGROUND", (0, 1), (-1, 1), Color(0.98, 0.98, 0.96)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(KeepTogether(table))


def _quick_review_lines(graded: GradedSubmission) -> List[str]:
    """High-level bullets summarising where things went wrong."""
    lines: List[str] = []
    rubric_fails = [gi for gi in graded.graded_items
                    if gi.earned < gi.item.points]
    test_fails = [t for t in graded.test_outcomes if not t.passed]
    doc_fails = [f for f in graded.proximity if not f.passed]

    if graded.checkstyle.error:
        lines.append(f"Checkstyle did not run cleanly: "
                     f"{graded.checkstyle.error}.")
    elif graded.checkstyle.violations:
        lines.append(f"Checkstyle flagged "
                     f"{len(graded.checkstyle.violations)} violation(s); "
                     f"most common rule(s): "
                     f"{_top_rules(graded.checkstyle.violations)}.")
    else:
        lines.append("Checkstyle: clean (no violations).")

    if not graded.compile_result.success:
        lines.append("Compile error -- the project did not build; every test "
                     "was marked FAIL automatically.")
    elif test_fails:
        lines.append(
            f"Functional tests: {len(graded.test_outcomes) - len(test_fails)}/"
            f"{len(graded.test_outcomes)} passed. Failing cases: "
            f"{', '.join(t.case.name for t in test_fails)}."
        )
    else:
        lines.append(f"Functional tests: all "
                     f"{len(graded.test_outcomes)} passed.")

    if doc_fails:
        egregious = sum(1 for f in doc_fails if f.severity >= 3)
        lines.append(
            f"Documentation: {len(doc_fails)} item(s) need manual review"
            + (f" ({egregious} completely undocumented)" if egregious
               else "")
            + "."
        )
    else:
        lines.append("Documentation: all checked methods/classes cleared the "
                     "proximity + @-tag requirements.")

    if rubric_fails:
        missed = sum(gi.item.points - gi.earned for gi in rubric_fails)
        lines.append(f"Rubric: {len(rubric_fails)} item(s) lost credit "
                     f"(total -{missed:.1f} pts).")
    return lines


def _top_rules(violations) -> str:
    """Top 3 most-common checkstyle rules, comma-separated."""
    counts: dict[str, int] = {}
    for v in violations:
        counts[v.rule] = counts.get(v.rule, 0) + 1
    top = sorted(counts.items(), key=lambda x: -x[1])[:3]
    return ", ".join(f"{r} (x{n})" for r, n in top) if top else "-"


def _score_band(percent: float) -> Color:
    """Pick the quick-review background based on the overall percent."""
    for threshold, colour in SCORE_BANDS:
        if percent >= threshold:
            return colour
    return SCORE_BANDS[-1][1]


def _first_n_lines(text: str, n: int, placeholder: bool = False) -> str:
    """First N lines of a string; optionally append a [...] marker if trimmed."""
    lines = text.splitlines()
    if len(lines) <= n:
        return _escape("\n".join(lines))
    head = "\n".join(lines[:n])
    suffix = "\n[... truncated ...]" if placeholder else ""
    return _escape(head + suffix).replace("\n", "<br/>")


def _clip(text: str, max_chars: int) -> str:
    """Clip a long string to max_chars with an ellipsis."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _escape(text: str) -> str:
    """XML-escape for reportlab's mini HTML Paragraph parser."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
