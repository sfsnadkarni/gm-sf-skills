#!/usr/bin/env python3
"""Build an AC-verification PDF report from a results JSON file.

Usage:
    python3 build_report.py <results.json> <output.pdf>

The results JSON schema is documented in SKILL.md. Each acceptance
criterion has: id, text, status (PASS|FAIL|INCONCLUSIVE), nav_hint,
steps (list[str]), evidence (str), and optional screenshot (path to PNG).
"""
import json
import os
import sys

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        Image,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:
    sys.exit(
        "reportlab is required. Install it with: python3 -m pip install reportlab"
    )

STATUS_COLORS = {
    "PASS": colors.HexColor("#1a7f37"),
    "FAIL": colors.HexColor("#cf222e"),
    "INCONCLUSIVE": colors.HexColor("#9a6700"),
}
STATUS_ORDER = ["PASS", "FAIL", "INCONCLUSIVE"]
STATUS_HEADING = {
    "PASS": "Passed",
    "FAIL": "Failed",
    "INCONCLUSIVE": "Inconclusive",
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("ACTitle", parent=ss["Heading3"], spaceAfter=2))
    ss.add(ParagraphStyle("ACBody", parent=ss["BodyText"], leftIndent=8, spaceAfter=2))
    ss.add(
        ParagraphStyle(
            "SectionHead",
            parent=ss["Heading1"],
            fontSize=16,
            spaceBefore=16,
            spaceAfter=6,
        )
    )
    ss.add(ParagraphStyle("Meta", parent=ss["BodyText"], fontSize=9, textColor=colors.HexColor("#57606a")))
    return ss


def _summary_table(counts, ss):
    total = sum(counts.values())
    data = [
        ["Passed", "Failed", "Inconclusive", "Total"],
        [
            str(counts.get("PASS", 0)),
            str(counts.get("FAIL", 0)),
            str(counts.get("INCONCLUSIVE", 0)),
            str(total),
        ],
    ]
    tbl = Table(data, colWidths=[1.5 * inch] * 4)
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 20),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 1), (0, 1), STATUS_COLORS["PASS"]),
                ("TEXTCOLOR", (1, 1), (1, 1), STATUS_COLORS["FAIL"]),
                ("TEXTCOLOR", (2, 1), (2, 1), STATUS_COLORS["INCONCLUSIVE"]),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f8fa")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
            ]
        )
    )
    return tbl


def _ac_flowables(ac, ss):
    out = []
    status = ac.get("status", "INCONCLUSIVE").upper()
    color = STATUS_COLORS.get(status, colors.grey)
    title = f'<b>{ac.get("id", "")}</b> &nbsp;<font color="#{color.hexval()[2:]}">[{status}]</font>'
    out.append(Paragraph(title, ss["ACTitle"]))
    out.append(Paragraph(ac.get("text", ""), ss["ACBody"]))

    steps = ac.get("steps") or []
    if steps:
        items = [ListItem(Paragraph(s, ss["ACBody"])) for s in steps]
        out.append(Paragraph("<i>Steps taken:</i>", ss["ACBody"]))
        out.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=16))

    if ac.get("evidence"):
        out.append(Paragraph(f'<i>Evidence:</i> {ac["evidence"]}', ss["ACBody"]))

    shot = ac.get("screenshot")
    if shot and os.path.isfile(shot):
        try:
            out.append(Spacer(1, 4))
            out.append(Image(shot, width=5.5 * inch, height=3.1 * inch, kind="proportional"))
        except Exception:
            pass

    out.append(Spacer(1, 6))
    out.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d0d7de")))
    out.append(Spacer(1, 6))
    return out


def build(results_path, output_path):
    with open(results_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    acs = data.get("acceptance_criteria", [])
    counts = {s: 0 for s in STATUS_ORDER}
    for ac in acs:
        counts[ac.get("status", "INCONCLUSIVE").upper()] = (
            counts.get(ac.get("status", "INCONCLUSIVE").upper(), 0) + 1
        )

    ss = _styles()
    story = []

    story.append(Paragraph("Acceptance Criteria Verification Report", ss["Title"]))
    meta = [
        f'<b>Story:</b> {data.get("story_key", "")} — {data.get("story_title", "")}',
        f'<b>Environment:</b> {data.get("environment", "")}',
        f'<b>Persona:</b> {data.get("persona", "")}',
        f'<b>Run:</b> {data.get("run_timestamp", "")}',
    ]
    for m in meta:
        story.append(Paragraph(m, ss["Meta"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Summary", ss["SectionHead"]))
    story.append(_summary_table(counts, ss))
    story.append(Spacer(1, 8))

    for status in STATUS_ORDER:
        group = [a for a in acs if a.get("status", "INCONCLUSIVE").upper() == status]
        if not group:
            continue
        heading = f"{STATUS_HEADING[status]} ({len(group)})"
        story.append(Paragraph(heading, ss["SectionHead"]))
        for ac in group:
            story.extend(_ac_flowables(ac, ss))

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        title="AC Verification Report",
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(story)
    print(
        f"Report saved to {output_path} — "
        f"{counts['PASS']} passed, {counts['FAIL']} failed, "
        f"{counts['INCONCLUSIVE']} inconclusive."
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 build_report.py <results.json> <output.pdf>")
    build(sys.argv[1], sys.argv[2])
