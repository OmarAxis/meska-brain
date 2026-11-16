"""A printable report for one learner.

It opens with a picture of the learner's own records: the learner in the middle, lines out to each
subject and strand, and the average on record for each. Then come the findings, and only the ones a
named teacher has approved: nothing proposed, drafted or waiting appears. Every finding is printed
with the name of the teacher who approved it and the records it rests on, so the page can answer a
parent's "why?". The report never ranks, never compares with classmates and never names a subject track."""

from __future__ import annotations

import base64
import math
from html import escape
from pathlib import Path
from typing import Any

from . import db, review
from .curriculum import load_pack

KIND_TITLE = {"strength": "A strength held over time", "root_cause": "Where a difficulty may have started",
              "struggle": "A difficulty held over time", "what_worked": "What seems to have helped"}
KIND_ORDER = ("strength", "root_cause", "struggle", "what_worked")   # a report starts with what goes well
EVIDENCE_KIND = {"quiz_item": "Quiz item", "assignment": "Assignment", "project": "Project",
                 "observation": "Teacher note", "attendance": "Attendance"}
AUDIENCE = {"guardian": "Note for the family", "teacher_handover": "Note for the next teacher"}
MAX_RECORDS_SHOWN = 12
RTL = {"ar", "fa", "ur", "he"}
_LOGO = Path(__file__).parent / "web" / "static" / "brand" / "meska-white.png"


def _cited(pack, rows: list[dict]) -> list[dict]:
    return [{"id": r["id"], "period": db.period_label(r["period_ord"]), "kind": r["kind"],
             "topic": pack.label(r["concept_id"]) if r["concept_id"] else "",
             "score": r["score"], "absent_days": r["absent_days"], "text": r["raw_text"],
             "language": r["language"], "source": r["source_ref"]} for r in rows]


def build(learner_id: str, *, db_path=None) -> dict[str, Any]:
    """Everything the report prints, as data. Approved findings and approved notes only."""
    with db.connect(db_path) as conn:
        learner = db.one(conn, "SELECT * FROM learners WHERE id = ?", (learner_id,))
        if learner is None:
            raise ValueError(f"Unknown learner '{learner_id}'.")
        pack = load_pack(learner["pack_id"])
        span = db.one(conn, "SELECT COUNT(*) AS records, COUNT(DISTINCT period_ord) AS terms, MIN(period_ord) AS first, "
                            "MAX(period_ord) AS last, MAX(grade) AS grade, COALESCE(SUM(absent_days), 0) AS absent "
                            "FROM evidence WHERE learner_id = ? AND status != 'retracted'", (learner_id,))
        approved = db.rows(conn, "SELECT f.*, t.name AS teacher FROM findings f LEFT JOIN teachers t ON t.id = f.decided_by "
                                 "WHERE f.learner_id = ? AND f.status IN ('approved', 'edited') ORDER BY f.decided_at, f.id",
                           (learner_id,))
        findings = []
        for f in sorted(approved, key=lambda f: KIND_ORDER.index(f["kind"])):
            expanded = review.expand_finding(conn, f)
            cited = _cited(pack, expanded["evidence"])
            findings.append({"explain": expanded["explain"], "id": f["id"], "kind": f["kind"], "statement": f["statement"], "teacher": f["teacher"],
                             "decided_at": f["decided_at"], "edited": f["status"] == "edited", "note": f["teacher_note"],
                             "records": cited[:MAX_RECORDS_SHOWN], "records_total": len(cited)})
        notes = db.rows(conn, "SELECT s.audience, s.language, s.text, s.decided_at, t.name AS teacher FROM summaries s "
                              "LEFT JOIN teachers t ON t.id = s.decided_by WHERE s.learner_id = ? AND s.status = 'approved' "
                              "ORDER BY s.audience, s.language", (learner_id,))
        gaps = db.rows(conn, "SELECT r.concept_id, r.status, r.answered_at, t.name AS teacher FROM record_requests r "
                             "LEFT JOIN teachers t ON t.id = r.answered_by WHERE r.learner_id = ? AND r.status != 'provided' "
                             "ORDER BY r.asked_at, r.id", (learner_id,))
        scored = db.rows(conn, "SELECT concept_id, score FROM evidence WHERE learner_id = ? AND status = 'active' "
                               "AND score IS NOT NULL AND concept_id IS NOT NULL", (learner_id,))
        waiting = db.one(conn, "SELECT (SELECT COUNT(*) FROM findings WHERE learner_id = ? AND status = 'proposed') + "
                               "(SELECT COUNT(*) FROM summaries WHERE learner_id = ? AND status = 'draft') AS n",
                         (learner_id, learner_id))["n"]
    by_strand: dict[str, list[float]] = {strand: [] for strand in pack.strands}
    for row in scored:
        concept = pack.concepts.get(row["concept_id"])
        if concept and concept.strand in by_strand:
            by_strand[concept.strand].append(row["score"])
    strands = [{"id": strand, "label": pack.label(strand), "subject": pack.strand_subject.get(strand),
                "subject_label": pack.label(pack.strand_subject[strand]) if pack.strand_subject.get(strand) else None,
                "records": len(values), "mean": round(sum(values) / len(values), 3) if values else None}
               for strand, values in by_strand.items()]
    return {
        "strands": strands,
        "learner": {"learner_id": learner_id, "alias": learner["alias"],
                    "name": learner.get("display_name") or learner["alias"], "home_language": learner["home_language"],
                    "grade_now": span["grade"] or learner["start_grade"], "curriculum": pack.name},
        "span": {"records": span["records"], "terms": span["terms"], "days_absent": span["absent"],
                 "first_period": db.period_label(span["first"]) if span["first"] is not None else None,
                 "last_period": db.period_label(span["last"]) if span["last"] is not None else None},
        "findings": findings,
        "notes": notes,
        "gaps": [{"topic": pack.label(g["concept_id"]), "answered": g["status"] == "no_record",
                  "teacher": g["teacher"], "answered_at": g["answered_at"]} for g in gaps],
        "waiting": waiting,
        "generated_at": db.now_iso(),
    }


# ---------------------------------------------------------------- the picture

RAMP = ("#EAF1FE", "#C5D9FC", "#94B8F9", "#5C93F6", "#1B5BD6")   # one hue, light to dark: lower to higher average
CX, CY, R_SUBJECT, R_STRAND = 430, 300, 118, 232


def _shade(mean: float) -> tuple[str, str]:
    """Fill and text colour for an average. Text stays ink or white so it can always be read."""
    step = min(len(RAMP) - 1, int(mean * len(RAMP)))
    return RAMP[step], "#FFFFFF" if step >= 3 else "#0A0A0A"


def _wrap(text: str, width: int = 17) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if len((current + " " + word).strip()) <= width:
            current = (current + " " + word).strip()
        else:
            if current:
                lines.append(current)
            current = word
    return (lines + [current])[:2]


def graph_svg(data: dict[str, Any]) -> str:
    """The learner's records as a knowledge graph: the learner in the middle, a line to each subject,
    a line on to each strand, and the average on record in each strand's circle. Circle size shows
    how many records there are. It shows this learner's own records and nobody else's."""
    strands = data["strands"]
    if not strands:
        return ""
    subjects = list(dict.fromkeys(st["subject"] for st in strands if st["subject"]))
    two_rings = len(subjects) > 1
    step = 2 * math.pi / len(strands)
    angle = {st["id"]: -math.pi / 2 + i * step for i, st in enumerate(strands)}
    most = max(st["records"] for st in strands) or 1
    lines, nodes = [], []

    def point(radius: float, a: float) -> tuple[float, float]:
        return CX + radius * math.cos(a), CY + radius * math.sin(a)

    hubs: dict[str, tuple[float, float]] = {}
    if two_rings:
        for subject in subjects:
            mine = [angle[st["id"]] for st in strands if st["subject"] == subject]
            hubs[subject] = point(R_SUBJECT, sum(mine) / len(mine))
            x, y = hubs[subject]
            lines.append(f'<line x1="{CX}" y1="{CY}" x2="{x:.1f}" y2="{y:.1f}" stroke="#2871F4" stroke-width="2.5"/>')
    for st in strands:
        a = angle[st["id"]]
        x, y = point(R_STRAND if two_rings else R_STRAND - 50, a)
        x0, y0 = hubs.get(st["subject"], (CX, CY))
        radius = 15 + 13 * math.sqrt(st["records"] / most)
        dashed = ' stroke-dasharray="4 4"' if st["mean"] is None else ""
        lines.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="#9AA4B8" stroke-width="1.5"{dashed}/>')
        if st["mean"] is None:
            nodes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="#FFFFFF" stroke="#9AA4B8" stroke-width="1.5" stroke-dasharray="4 4"/>')
            score, ink = "none", "#5B6478"
        else:
            fill, ink = _shade(st["mean"])
            nodes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{fill}" stroke="#FFFFFF" stroke-width="2"/>')
            score = f"{round(st['mean'] * 100)}%"
        nodes.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11.5" font-weight="700" fill="{ink}">{score}</text>')
        side = math.cos(a)
        anchor = "start" if side > 0.25 else "end" if side < -0.25 else "middle"
        lx, ly = point((R_STRAND if two_rings else R_STRAND - 50) + radius + 9, a)
        words = _wrap(st["label"])
        if anchor == "middle":
            ly += -6 - 13 * (len(words) - 1) if math.sin(a) < 0 else 14
        else:
            ly += 4 - 6.5 * (len(words) - 1)
        spans = "".join(f'<tspan x="{lx:.1f}" dy="{13 if i else 0}">{escape(w)}</tspan>' for i, w in enumerate(words))
        nodes.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="11.5" fill="#0A0A0A">{spans}</text>')
    for subject, (x, y) in hubs.items():
        label = next(st["subject_label"] for st in strands if st["subject"] == subject)
        width = 16 + 7.2 * len(label)
        nodes.append(f'<rect x="{x - width / 2:.1f}" y="{y - 13:.1f}" width="{width:.1f}" height="26" rx="13" fill="#FFFFFF" stroke="#2871F4" stroke-width="2"/>'
                     f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="12" font-weight="700" fill="#0A0A0A">{escape(label)}</text>')
    learner = data["learner"]
    named = learner.get("name") and learner["name"] != learner["alias"]
    alias = escape(learner["name"].split()[0] if named else learner["alias"].split()[-1])
    centre = (f'<circle cx="{CX}" cy="{CY}" r="44" fill="#000038"/><circle cx="{CX}" cy="{CY}" r="50" fill="none" stroke="#2871F4" stroke-width="2"/>'
              f'<text x="{CX}" y="{CY - 3}" text-anchor="middle" font-size="11" fill="#FFFFFF" opacity=".85">Learner</text>'
              f'<text x="{CX}" y="{CY + 15}" text-anchor="middle" font-size="18" font-weight="700" fill="#FFFFFF">{alias}</text>')
    key = "".join(f'<rect x="{24 + i * 26}" y="608" width="26" height="12" fill="{c}"/>' for i, c in enumerate(RAMP))
    legend = (f'{key}<text x="24" y="602" font-size="11" fill="#5B6478">Average on record</text>'
              f'<text x="24" y="634" font-size="10.5" fill="#5B6478">lower</text>'
              f'<text x="154" y="634" text-anchor="end" font-size="10.5" fill="#5B6478">higher</text>'
              f'<circle cx="196" cy="614" r="6" fill="#C5D9FC"/><circle cx="218" cy="614" r="11" fill="#C5D9FC"/>'
              f'<text x="236" y="618" font-size="11" fill="#5B6478">A bigger circle means more records</text>'
              f'<circle cx="462" cy="614" r="8" fill="#FFFFFF" stroke="#9AA4B8" stroke-width="1.5" stroke-dasharray="4 4"/>'
              f'<text x="478" y="618" font-size="11" fill="#5B6478">No scored records yet (not the same as struggling)</text>')
    summary = "; ".join(f"{st['label']}: " + (f"{round(st['mean'] * 100)}% over {st['records']} records" if st["mean"] is not None
                                              else "no scored records") for st in strands)
    return (f'<svg class="graph" viewBox="0 0 860 645" role="img" aria-label="Knowledge graph of the records. {escape(summary)}" '
            f'font-family="inherit" style="-webkit-print-color-adjust:exact;print-color-adjust:exact">'
            f'{"".join(lines)}{centre}{"".join(nodes)}{legend}</svg>')


def term_chart_svg(series: list[dict]) -> str:
    """Results term by term for the records behind one finding: one column per term, the average on top."""
    if not series:
        return ""
    step, base, top = 54, 96, 16
    width = 34 + step * len(series)
    parts = [f'<line x1="20" y1="{base}" x2="{width - 6}" y2="{base}" stroke="#9AA4B8" stroke-width="1"/>']
    for i, point in enumerate(series):
        x = 30 + i * step
        height = max(2.0, (base - top) * point["mean"])
        fill, _ = _shade(point["mean"])
        parts.append(f'<rect x="{x}" y="{base - height:.1f}" width="32" height="{height:.1f}" rx="4" fill="{fill}" stroke="#5C93F6" stroke-width="1"/>'
                     f'<text x="{x + 16}" y="{base - height - 4:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="#0A0A0A">{round(point["mean"] * 100)}%</text>'
                     f'<text x="{x + 16}" y="{base + 14}" text-anchor="middle" font-size="10" fill="#5B6478">{escape(point["period"][2:])}</text>')
    label = "Results term by term: " + ", ".join(f"{p['period']} {round(p['mean'] * 100)}%" for p in series)
    return (f'<svg class="terms" viewBox="0 0 {width} 116" width="{width}" height="116" role="img" aria-label="{escape(label)}" '
            f'font-family="inherit" style="-webkit-print-color-adjust:exact;print-color-adjust:exact">{"".join(parts)}</svg>')


def _chain(chain: list[dict]) -> str:
    """Where it began, on the left, to where it shows now, on the right."""
    if not chain:
        return ""
    chips = []
    for i, topic in enumerate(chain):
        tag = "Began here" if i == 0 else "Shows up here now" if i == len(chain) - 1 else "On the way"
        result = f"{round(topic['mean'] * 100)}% on record" if topic["mean"] is not None else "no records cited"
        edge = " start" if i == 0 else ""
        chips.append(f'<div class="chip{edge}"><span class="tag">{tag}</span><strong>{escape(topic["label"])}</strong>'
                     f'<span>Grade {topic["grade"]}, {result}</span></div>')
    return '<div class="chain" role="img" aria-label="' + escape(" then ".join(t["label"] for t in chain)) + '">' + \
        '<span class="arrow" aria-hidden="true">is needed for</span>'.join(chips) + "</div>"


def _why(explained: dict | None) -> str:
    if not explained:
        return ""
    facts = "".join(f"<li>{escape(fact)}</li>" for fact in explained["facts"])
    chart = term_chart_svg(explained["series"])
    chart = f'<div class="chartbox"><div class="small">Results on the cited records, term by term</div>{chart}</div>' if chart else ""
    return f'{_chain(explained["chain"])}<div class="why"><div><div class="small"><strong>Why this is suggested</strong></div><ul>{facts}</ul></div>{chart}</div>'


# ---------------------------------------------------------------- HTML

_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:'Articulat CF',Inter,system-ui,-apple-system,'Segoe UI',sans-serif;color:#0A0A0A;background:#F5F7FB;line-height:1.5}
.page{max-width:820px;margin:0 auto;background:#fff}
header{background:linear-gradient(135deg,#000038 0%,#000058 45%,#0000CE 100%);color:#fff;padding:26px 36px;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
header img{height:24px;width:auto;display:block;margin-bottom:18px}
header h1{margin:0;font-size:28px;line-height:1.2}
header p{margin:6px 0 0;opacity:.9;font-size:14px}
main{padding:24px 36px 36px}
h2{font-size:17px;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid #2871F4}
.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:0}
.facts div{background:#F5F7FB;border-radius:12px;padding:10px 12px}
.facts dt{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#5B6478}
.facts dd{margin:2px 0 0;font-size:18px;font-weight:700}
.graph{display:block;width:100%;height:auto;break-inside:avoid}
.chain{display:flex;flex-wrap:wrap;align-items:stretch;gap:6px;margin:10px 0}
.chip{border:1px solid #C5D9FC;border-radius:12px;padding:6px 10px;display:flex;flex-direction:column;font-size:12px;background:#fff}
.chip.start{border:2px solid #A63F00}
.chip .tag{font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:#5B6478;font-weight:700}
.chip.start .tag{color:#A63F00}
.arrow{align-self:center;font-size:11px;color:#5B6478}
.arrow::after{content:" \\2192"}
.why{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:flex-start;margin:6px 0 4px}
.why ul{margin:4px 0;padding-left:18px;font-size:13px;max-width:430px}
.terms{display:block;max-width:100%;height:auto}
.finding{border:1px solid #E3E8F2;border-radius:14px;padding:14px 16px;margin:0 0 12px;break-inside:avoid}
.kind{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#1B5BD6;font-weight:700}
.statement{font-size:16px;margin:4px 0 6px}
.by{font-size:12.5px;color:#5B6478;margin:0}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
th{text-align:left;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:#5B6478;border-bottom:1px solid #E3E8F2;padding:4px 6px}
td{border-bottom:1px solid #EEF1F7;padding:4px 6px;vertical-align:top}
td:nth-child(1),td:nth-child(2),td:nth-child(4){white-space:nowrap}
td.id{color:#5B6478;font-family:ui-monospace,Consolas,monospace;font-size:11px;white-space:nowrap}
.note{background:#EAF1FE;border-radius:14px;padding:14px 16px;margin:0 0 12px;break-inside:avoid;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
.note p{margin:6px 0 0;font-size:15px}
.small{font-size:12.5px;color:#5B6478}
.empty{color:#5B6478;font-style:italic}
footer{border-top:1px solid #E3E8F2;margin-top:28px;padding-top:12px;font-size:12px;color:#5B6478}
.print{position:fixed;right:18px;top:18px;background:#2871F4;color:#fff;border:0;border-radius:12px;padding:10px 18px;
  font:inherit;font-weight:600;cursor:pointer}
@media (max-width:640px){.facts{grid-template-columns:repeat(2,1fr)}header,main{padding-left:18px;padding-right:18px}}
@media print{body{background:#fff}.print{display:none}.page{max-width:none}@page{margin:14mm}}
"""


def _logo() -> str:
    if not _LOGO.is_file():
        return ""
    data = base64.b64encode(_LOGO.read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{data}" alt="meska.Ai">'


def _when(iso: str | None) -> str:
    return (iso or "")[:10]


def _score(row: dict) -> str:
    if row["kind"] == "attendance":
        return f"{row['absent_days']} days absent" if row["absent_days"] is not None else ""
    return f"{round(row['score'] * 100)}%" if row["score"] is not None else ""


def _finding(f: dict) -> str:
    rows = "".join(
        f"<tr><td>{escape(r['period'])}</td><td>{escape(EVIDENCE_KIND.get(r['kind'], r['kind']))}</td>"
        f"<td>{escape(r['topic'])}</td><td>{escape(_score(r))}</td>"
        f"<td dir=\"auto\">{escape((r['text'] or '')[:140])}</td><td class=\"id\">{escape(r['id'])}</td></tr>"
        for r in f["records"])
    more = f["records_total"] - len(f["records"])
    extra = f'<p class="small">and {more} more records in the teacher app.</p>' if more > 0 else ""
    how = "Edited and approved" if f["edited"] else "Approved"
    note = f' Teacher\'s note: {escape(f["note"])}' if f["note"] else ""
    return (f'<section class="finding"><div class="kind">{escape(KIND_TITLE.get(f["kind"], f["kind"]))}</div>'
            f'<p class="statement">{escape(f["statement"])}</p>{_why(f.get("explain"))}'
            f'<p class="by">{how} by {escape(f["teacher"] or "a teacher")} on {escape(_when(f["decided_at"]))}. '
            f'Rests on {f["records_total"]} records.{note}</p>'
            f'<table><thead><tr><th>Term</th><th>Record</th><th>Topic</th><th>Result</th><th>Words on the record</th>'
            f'<th>Record id</th></tr></thead><tbody>{rows}</tbody></table>{extra}</section>')


def _note(n: dict) -> str:
    direction = "rtl" if n["language"] in RTL else "auto"
    return (f'<section class="note"><div class="kind">{escape(AUDIENCE.get(n["audience"], n["audience"]))} '
            f'({escape(n["language"])})</div><p lang="{escape(n["language"])}" dir="{direction}">{escape(n["text"])}</p>'
            f'<p class="by">Approved by {escape(n["teacher"] or "a teacher")} on {escape(_when(n["decided_at"]))}.</p></section>')


def _gap(g: dict) -> str:
    if g["answered"]:
        return (f'<li>There are no records for <strong>{escape(g["topic"])}</strong>. '
                f'{escape(g["teacher"] or "A teacher")} confirmed on {escape(_when(g["answered_at"]))} that none exist.</li>')
    return f'<li>There are no records for <strong>{escape(g["topic"])}</strong>. A teacher has been asked and has not answered yet.</li>'


def render_html(data: dict[str, Any]) -> str:
    """One self-contained page: no script except the print button, no outside files."""
    learner, span = data["learner"], data["span"]
    shown = learner.get("name") or learner["alias"]
    code = f'Record code {learner["alias"].split()[-1]}. ' if shown != learner["alias"] else ""
    followed = (f'{span["first_period"]} to {span["last_period"]}' if span["first_period"] else "no dated records yet")
    findings = "".join(_finding(f) for f in data["findings"]) or \
        '<p class="empty">No finding has been approved by a teacher yet, so there is nothing to report.</p>'
    notes = "".join(_note(n) for n in data["notes"]) or '<p class="empty">No note has been approved yet.</p>'
    gaps = f'<h2>What the records cannot tell</h2><ul>{"".join(_gap(g) for g in data["gaps"])}</ul>' if data["gaps"] else ""
    count = data["waiting"]
    waiting = (f' {count} {"item is" if count == 1 else "items are"} still waiting for a teacher and not in this report.'
               if count else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Learning report: {escape(shown)}</title><style>{_CSS}</style></head>
<body><button class="print" type="button" onclick="window.print()">Print or save as PDF</button>
<div class="page"><header>{_logo()}<h1>Learning report: {escape(shown)}</h1>
<p>{escape(code)}Grade {escape(str(learner["grade_now"]))}. {escape(learner["curriculum"])}. Followed {escape(followed)}.</p></header>
<main>
<dl class="facts"><div><dt>Records</dt><dd>{span["records"]}</dd></div><div><dt>Terms followed</dt><dd>{span["terms"]}</dd></div>
<div><dt>Days absent</dt><dd>{span["days_absent"]}</dd></div><div><dt>Approved findings</dt><dd>{len(data["findings"])}</dd></div></dl>
<h2>What the records show</h2>
<p class="small">The learner's own results on record, by subject and strand, across every term followed. This is not
compared with any other learner, and an average is not a judgement of the child.</p>
{graph_svg(data)}
<h2>What a teacher has approved</h2>{findings}
<h2>Notes</h2>{notes}
{gaps}
<footer>The picture shows averages of the records themselves. The findings and notes are only those a named teacher has read and approved.{escape(waiting)} The report describes patterns in the
work, not the child. It is not a grade, a rank or a recommendation of a subject or career. Every finding lists the records
it rests on. Generated {escape(data["generated_at"][:16].replace("T", " "))} UTC by Meska Brain.</footer>
</main></div></body></html>"""
