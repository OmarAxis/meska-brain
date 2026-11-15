"""Teacher decisions. Only a named teacher approves, edits or rejects. These functions are never
exposed over MCP; the web app calls them for a signed-in teacher."""

from __future__ import annotations

import time

from . import audit, db, guard

FINDING_DECISIONS = ("approved", "edited", "rejected")
SUMMARY_DECISIONS = ("approved", "rejected")


def _expand_finding(conn, finding: dict) -> dict:
    """A finding with its JSON fields decoded and its cited evidence rows attached."""
    finding = dict(finding, concept_ids=db.jload(finding["concept_ids"], []),
                   evidence_ids=db.jload(finding["evidence_ids"], []), path=db.jload(finding["path"], []))
    marks = ",".join("?" for _ in finding["evidence_ids"])
    finding["evidence"] = db.rows(conn, f"SELECT * FROM evidence WHERE id IN ({marks}) ORDER BY period_ord, id",
                                  tuple(finding["evidence_ids"])) if marks else []
    return finding


def pending(db_path=None) -> dict:
    """Findings and summaries waiting for a teacher, with the evidence behind them."""
    with db.connect(db_path) as conn:
        findings = [_expand_finding(conn, f) for f in db.rows(
            conn, "SELECT * FROM findings WHERE status = 'proposed' ORDER BY proposed_at, id")]
        summaries = []
        for summary in db.rows(conn, "SELECT * FROM summaries WHERE status = 'draft' ORDER BY created_at, id"):
            ids = db.jload(summary["finding_ids"], [])
            summary = dict(summary, finding_ids=ids, findings=[
                _expand_finding(conn, f) for f in db.rows(
                    conn, f"SELECT * FROM findings WHERE id IN ({','.join('?' for _ in ids)})", tuple(ids))])
            summaries.append(summary)
    return {"findings": findings, "summaries": summaries}


def _teacher(conn, teacher_id: str) -> dict:
    teacher = db.one(conn, "SELECT * FROM teachers WHERE id = ?", (teacher_id,))
    if teacher is None:
        raise ValueError(f"Unknown teacher '{teacher_id}'. Only a named teacher can decide.")
    return teacher


def _record_approval(conn, target_type: str, target_id: str, decision: str, teacher: dict,
                     note: str | None) -> None:
    conn.execute("INSERT INTO approvals (ts, target_type, target_id, decision, teacher_id, teacher_name, note) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (db.now_iso(), target_type, target_id, decision, teacher["id"], teacher["name"], note))


def decide_finding(finding_id: str, decision: str, teacher_id: str, note: str | None = None,
                   edited_statement: str | None = None, *, db_path=None) -> dict:
    """Approve, edit or reject a proposed finding. The decision, its `approvals` row and its
    `audit_log` row are written in one transaction: all three or none."""
    started = time.perf_counter()
    if decision not in FINDING_DECISIONS:
        raise ValueError(f"Decision must be one of: {', '.join(FINDING_DECISIONS)}.")
    if decision == "edited":
        if not edited_statement:
            raise ValueError("An 'edited' decision needs the edited_statement.")
        problems = guard.check_statement(edited_statement)
        if problems:
            raise ValueError("The edited statement was rejected: " + " | ".join(problems))
    with db.connect(db_path) as conn:
        teacher = _teacher(conn, teacher_id)
        finding = db.one(conn, "SELECT * FROM findings WHERE id = ?", (finding_id,))
        if finding is None:
            raise ValueError(f"Unknown finding '{finding_id}'.")
        if finding["status"] != "proposed":
            raise ValueError(f"Finding '{finding_id}' was already decided ({finding['status']}).")
        statement = edited_statement if decision == "edited" else finding["statement"]
        conn.execute("UPDATE findings SET status = ?, statement = ?, decided_by = ?, decided_at = ?, "
                     "teacher_note = ? WHERE id = ?",
                     (decision, statement, teacher_id, db.now_iso(), note, finding_id))
        _record_approval(conn, "finding", finding_id, decision, teacher, note)
        result = _expand_finding(conn, db.one(conn, "SELECT * FROM findings WHERE id = ?", (finding_id,)))
        audit.write_row(conn, "decide_finding", {"finding_id": finding_id, "decision": decision,
                                                 "teacher_id": teacher_id, "note": note,
                                                 "edited_statement": edited_statement},
                        result, True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{teacher_id}")
    return result


def decide_summary(summary_id: str, decision: str, teacher_id: str, note: str | None = None,
                   *, db_path=None) -> dict:
    """Approve or reject a summary draft. Decision, approval and audit row share one transaction."""
    started = time.perf_counter()
    if decision not in SUMMARY_DECISIONS:
        raise ValueError(f"Decision must be one of: {', '.join(SUMMARY_DECISIONS)}.")
    with db.connect(db_path) as conn:
        teacher = _teacher(conn, teacher_id)
        summary = db.one(conn, "SELECT * FROM summaries WHERE id = ?", (summary_id,))
        if summary is None:
            raise ValueError(f"Unknown summary '{summary_id}'.")
        if summary["status"] != "draft":
            raise ValueError(f"Summary '{summary_id}' was already decided ({summary['status']}).")
        conn.execute("UPDATE summaries SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                     (decision, teacher_id, db.now_iso(), summary_id))
        _record_approval(conn, "summary", summary_id, decision, teacher, note)
        result = db.one(conn, "SELECT * FROM summaries WHERE id = ?", (summary_id,))
        result["finding_ids"] = db.jload(result["finding_ids"], [])
        audit.write_row(conn, "decide_summary", {"summary_id": summary_id, "decision": decision,
                                                 "teacher_id": teacher_id, "note": note},
                        result, True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{teacher_id}")
    return result
