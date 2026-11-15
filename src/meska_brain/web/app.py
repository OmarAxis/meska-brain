"""Teacher web app: a thin JSON API over graph, review and db, plus one static page.

There is no real sign-in. A teacher is chosen from a list so every decision carries a name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import db, graph, review
from ..config import get_settings
from ..curriculum import load_pack
from . import dashboard, people

STATIC = Path(__file__).with_name("static")

app = FastAPI(title="Meska Brain", docs_url=None, redoc_url=None)
# Brand assets (the logo). The page itself is served at "/".
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class _RunnerUnavailable(Exception):
    pass


@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(_RunnerUnavailable)
async def _runner_unavailable(_: Request, exc: _RunnerUnavailable) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=503)


class FindingDecision(BaseModel):
    decision: str
    teacher_id: str
    note: str | None = None
    edited_statement: str | None = None


class SummaryDecision(BaseModel):
    decision: str
    teacher_id: str
    note: str | None = None


class RunRequest(BaseModel):
    learner_id: str
    inbox_file: str | None = None


def _runner():
    """Import the agent runner lazily; the rest of the app works without it."""
    try:
        from ..agent import runner
    except Exception as exc:  # module missing, or one of its optional dependencies is
        raise _RunnerUnavailable(f"The agent is not available on this machine: {exc}") from exc
    return runner


def _learner_exists(conn, learner_id: str) -> None:
    if db.one(conn, "SELECT id FROM learners WHERE id = ?", (learner_id,)) is None:
        raise ValueError(f"Unknown learner '{learner_id}'.")


# ------------------------------------------------------------------ learners

@app.get("/api/learners")
def learners() -> dict:
    with db.connect() as conn:
        found = db.rows(conn, """
            SELECT l.id AS learner_id, l.alias, l.home_language, l.start_grade,
                   MAX(e.grade) AS latest_grade, COUNT(e.id) AS evidence_count
            FROM learners l LEFT JOIN evidence e ON e.learner_id = l.id AND e.status != 'retracted'
            GROUP BY l.id ORDER BY l.alias COLLATE NOCASE, l.id""")
    return {"learners": [{"learner_id": r["learner_id"], "alias": r["alias"],
                          "grade_now": r["latest_grade"] or r["start_grade"],
                          "home_language": r["home_language"], "evidence_count": r["evidence_count"]}
                         for r in found]}


@app.get("/api/overview")
def overview() -> dict:
    return dashboard.overview()


@app.get("/api/learners/{learner_id}/dashboard")
def learner_dashboard(learner_id: str) -> dict:
    return dashboard.learner_dashboard(learner_id)


@app.get("/api/learners/{learner_id}/mind")
def learner_mind(learner_id: str) -> dict:
    return people.learner_mind(learner_id)


@app.get("/api/learners/{learner_id}/fit")
def learner_fit(learner_id: str, teacher_id: str) -> dict:
    return people.fit(learner_id, teacher_id)


@app.get("/api/teachers/{teacher_id}/profile")
def teacher_profile(teacher_id: str) -> dict:
    return people.teacher_profile(teacher_id)


@app.post("/api/teachers/{teacher_id}/profile")
def save_teacher_profile(teacher_id: str, body: dict[str, Any]) -> dict:
    return people.save_teacher_profile(teacher_id, body)


@app.get("/api/learners/{learner_id}/graph")
def learner_graph(learner_id: str) -> dict:
    data = graph.learner_graph(learner_id)
    # The page recolours nodes while replaying, so it needs the same cut-offs the engine uses.
    data["thresholds"] = {"strong_above": graph.STRENGTH_ABOVE, "gap_below": graph.STRUGGLE_BELOW}
    with db.connect() as conn:
        row = db.one(conn, "SELECT pack_id FROM learners WHERE id = ?", (learner_id,))
    pack = load_pack(row["pack_id"])
    data["subjects"] = [{"id": s, "label": pack.label(s)} for s in pack.subjects]
    data["strand_subject"] = dict(pack.strand_subject)
    return data


@app.get("/api/learners/{learner_id}/timeline")
def learner_timeline(learner_id: str, concept_id: str | None = None) -> dict:
    sql = "SELECT * FROM evidence WHERE learner_id = ? AND status != 'retracted'"
    params: list[Any] = [learner_id]
    if concept_id:
        sql += " AND concept_id = ?"
        params.append(concept_id)
    sql += " ORDER BY period_ord, id"
    with db.connect() as conn:
        _learner_exists(conn, learner_id)
        items = db.rows(conn, sql, tuple(params))
    periods: dict[str, list[dict]] = {}
    for item in items:
        periods.setdefault(db.period_label(item["period_ord"]), []).append(item)
    return {"learner_id": learner_id, "periods": [{"period": p, "items": v} for p, v in periods.items()],
            "counts": {"items": len(items)}}


@app.get("/api/learners/{learner_id}/trace/{concept_id}")
def learner_trace(learner_id: str, concept_id: str) -> dict:
    return graph.trace_root(learner_id, concept_id)


@app.get("/api/learners/{learner_id}/patterns")
def learner_patterns(learner_id: str, min_periods: int = 3) -> dict:
    return graph.find_patterns(learner_id, min_periods)


@app.get("/api/learners/{learner_id}/what-worked")
def learner_what_worked(learner_id: str) -> dict:
    return graph.what_worked(learner_id)


@app.get("/api/evidence")
def evidence(ids: str = "") -> dict:
    wanted = [i.strip() for i in ids.split(",") if i.strip()][:200]
    if not wanted:
        return {"evidence": []}
    marks = ",".join("?" for _ in wanted)
    with db.connect() as conn:
        found = db.rows(conn, f"SELECT * FROM evidence WHERE id IN ({marks}) ORDER BY period_ord, id",
                        tuple(wanted))
    return {"evidence": found}


@app.get("/api/teachers")
def teachers() -> dict:
    with db.connect() as conn:
        found = db.rows(conn, "SELECT id, name, subjects FROM teachers ORDER BY name COLLATE NOCASE")
    for t in found:
        t["subjects"] = db.jload(t["subjects"], [])
    return {"teachers": found}


# ------------------------------------------------------------------ review

def _expand_finding(conn, finding: dict) -> dict:
    out = dict(finding, concept_ids=db.jload(finding["concept_ids"], []),
               evidence_ids=db.jload(finding["evidence_ids"], []), path=db.jload(finding["path"], []))
    marks = ",".join("?" for _ in out["evidence_ids"])
    out["evidence"] = db.rows(conn, f"SELECT * FROM evidence WHERE id IN ({marks}) ORDER BY period_ord, id",
                              tuple(out["evidence_ids"])) if marks else []
    learner = db.one(conn, "SELECT pack_id FROM learners WHERE id = ?", (finding["learner_id"],))
    out["next_step"] = people.next_step(out, load_pack(learner["pack_id"])) if learner else None
    return out


@app.get("/api/review/pending")
def review_pending() -> dict:
    data = review.pending()
    with db.connect() as conn:
        packs = {r["id"]: r["pack_id"] for r in db.rows(conn, "SELECT id, pack_id FROM learners")}
    for finding in data["findings"]:
        finding["next_step"] = people.next_step(finding, load_pack(packs[finding["learner_id"]]))
    return data


@app.get("/api/findings")
def findings(learner_id: str | None = None, status: str | None = None) -> dict:
    sql, params, where = "SELECT * FROM findings", [], []
    if learner_id:
        where.append("learner_id = ?")
        params.append(learner_id)
    if status:
        where.append("status = ?")
        params.append(status)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY proposed_at DESC, id"
    with db.connect() as conn:
        return {"findings": [_expand_finding(conn, f) for f in db.rows(conn, sql, tuple(params))]}


@app.get("/api/summaries")
def summaries(learner_id: str | None = None) -> dict:
    sql, params = "SELECT * FROM summaries", []
    if learner_id:
        sql += " WHERE learner_id = ?"
        params.append(learner_id)
    sql += " ORDER BY created_at DESC, id"
    with db.connect() as conn:
        found = db.rows(conn, sql, tuple(params))
    for s in found:
        s["finding_ids"] = db.jload(s["finding_ids"], [])
    return {"summaries": found}


def _resume_waiting(target_id: str) -> list[str]:
    """Best effort: continue any run that was waiting on this item."""
    resumed: list[str] = []
    try:
        runner = _runner()
        for run in runner.list_runs():
            if run.get("status") != "waiting_for_teacher":
                continue
            if target_id in json.dumps(run.get("pending") or {}):
                runner.resume(run["run_id"])
                resumed.append(run["run_id"])
    except Exception:  # noqa: BLE001, S110 - resuming is best effort; the decision is already saved
        pass
    return resumed


@app.post("/api/findings/{finding_id}/decision")
def decide_finding(finding_id: str, body: FindingDecision) -> dict:
    result = review.decide_finding(finding_id, body.decision, body.teacher_id, body.note,
                                   body.edited_statement)
    return {"finding": result, "resumed_runs": _resume_waiting(finding_id)}


@app.post("/api/summaries/{summary_id}/decision")
def decide_summary(summary_id: str, body: SummaryDecision) -> dict:
    result = review.decide_summary(summary_id, body.decision, body.teacher_id, body.note)
    return {"summary": result, "resumed_runs": _resume_waiting(summary_id)}


# ------------------------------------------------------------------ audit

@app.get("/api/audit")
def audit_log(limit: int = 100, run_id: str | None = None, tool: str | None = None) -> dict:
    sql, params, where = "SELECT * FROM audit_log", [], []
    if run_id:
        where.append("run_id = ?")
        params.append(run_id)
    if tool:
        where.append("tool = ?")
        params.append(tool)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limit, 1000)))
    with db.connect() as conn:
        return {"entries": db.rows(conn, sql, tuple(params))}


@app.get("/api/approvals")
def approvals() -> dict:
    with db.connect() as conn:
        return {"approvals": db.rows(conn, "SELECT * FROM approvals ORDER BY id DESC")}


# ------------------------------------------------------------------ agent runs

def _inbox_dir() -> Path:
    return get_settings().db_path.parent / "inbox"


@app.get("/api/inbox")
def inbox() -> dict:
    folder = _inbox_dir()
    files = sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    return {"files": [{"name": p.name, "path": str(p), "bytes": p.stat().st_size} for p in files
                      if p.name.lower() != "readme.md"]}


@app.post("/api/runs")
def start_run(body: RunRequest) -> dict:
    task: dict[str, Any] = {"learner_id": body.learner_id}
    with db.connect() as conn:
        _learner_exists(conn, body.learner_id)
    if body.inbox_file:
        path = _inbox_dir() / Path(body.inbox_file).name
        if not path.is_file():
            raise ValueError(f"No file called '{Path(body.inbox_file).name}' in the inbox.")
        task["inbox_file"] = str(path)
    return _runner().start(task)


@app.get("/api/runs")
def runs() -> dict:
    return {"runs": _runner().list_runs()}


@app.get("/api/runs/{run_id}")
def run_status(run_id: str) -> dict:
    return _runner().status(run_id)


# ------------------------------------------------------------------ page

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", media_type="text/html")


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.web_host, port=settings.web_port, log_level="info")


if __name__ == "__main__":
    main()
