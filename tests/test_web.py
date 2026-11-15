"""Web app: JSON API over a small seeded database, and the single static page."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from meska_brain import db, synth, tools


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    base = tmp_path_factory.mktemp("web")
    db_path = base / "meska.db"
    mp = pytest.MonkeyPatch()
    mp.setenv("MESKA_DB", str(db_path))
    synth.generate(db_path=db_path, n_learners=6, out_dir=base / "out")
    from meska_brain.web.app import app

    yield TestClient(app)
    mp.undo()


@pytest.fixture()
def proposed(client):
    """A freshly proposed finding citing two scored items of one learner."""
    with db.connect() as conn:
        row = db.one(conn, "SELECT learner_id, concept_id FROM evidence WHERE score IS NOT NULL "
                           "AND concept_id IS NOT NULL AND status = 'active' "
                           "GROUP BY learner_id, concept_id HAVING COUNT(*) >= 2 LIMIT 1")
        ids = [r["id"] for r in db.rows(conn, "SELECT id FROM evidence WHERE learner_id = ? AND concept_id = ? "
                                              "AND score IS NOT NULL LIMIT 2", (row["learner_id"], row["concept_id"]))]
    out = tools.propose_finding(learner_id=row["learner_id"], kind="struggle",
                                statement="Scores on this concept stayed low over several terms.",
                                evidence_ids=ids, concept_ids=[row["concept_id"]], confidence=0.6)
    return {"finding_id": out["finding_id"], "learner_id": row["learner_id"], "evidence_ids": ids}


def _teacher(client) -> dict:
    return client.get("/api/teachers").json()["teachers"][0]


def test_learners_alphabetical_by_alias(client):
    learners = client.get("/api/learners").json()["learners"]
    assert len(learners) == 6
    aliases = [lr["alias"] for lr in learners]
    assert aliases == sorted(aliases, key=str.lower)
    assert set(learners[0]) >= {"learner_id", "alias", "grade_now", "home_language", "evidence_count"}


def test_graph_endpoint_has_nodes_edges_timeline(client):
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    body = client.get(f"/api/learners/{lid}/graph").json()
    assert body["nodes"] and body["edges"] and body["timeline"]
    assert {"strong_above", "gap_below"} <= set(body["thresholds"])
    assert {n["state"] for n in body["nodes"]} <= {"strong", "shaky", "gap", "unseen"}


def test_timeline_trace_patterns_what_worked(client):
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    tl = client.get(f"/api/learners/{lid}/timeline").json()
    assert tl["periods"] and tl["periods"][0]["items"]
    g = client.get(f"/api/learners/{lid}/graph").json()
    concept = next(n["id"] for n in g["nodes"] if n["type"] == "concept")
    assert "reason" in client.get(f"/api/learners/{lid}/trace/{concept}").json()
    assert "patterns" in client.get(f"/api/learners/{lid}/patterns").json()
    assert "approaches" in client.get(f"/api/learners/{lid}/what-worked").json()


def test_unknown_learner_is_400(client):
    r = client.get("/api/learners/lrn_nope/graph")
    assert r.status_code == 400 and "error" in r.json()


def test_pending_review_expands_evidence(client, proposed):
    pending = client.get("/api/review/pending").json()
    mine = next(f for f in pending["findings"] if f["id"] == proposed["finding_id"])
    assert {e["id"] for e in mine["evidence"]} == set(proposed["evidence_ids"])
    rows = client.get("/api/evidence", params={"ids": ",".join(proposed["evidence_ids"])}).json()["evidence"]
    assert len(rows) == 2


def test_decision_without_valid_teacher_is_400(client, proposed):
    r = client.post(f"/api/findings/{proposed['finding_id']}/decision",
                    json={"decision": "approved", "teacher_id": "tch_nobody"})
    assert r.status_code == 400
    assert "teacher" in r.json()["error"].lower()
    still = client.get("/api/findings", params={"status": "proposed"}).json()["findings"]
    assert any(f["id"] == proposed["finding_id"] for f in still)


def test_approve_writes_approval_and_audit(client, proposed):
    teacher = _teacher(client)
    r = client.post(f"/api/findings/{proposed['finding_id']}/decision",
                    json={"decision": "approved", "teacher_id": teacher["id"], "note": "Checked with class notes."})
    assert r.status_code == 200, r.text
    approvals = client.get("/api/approvals").json()["approvals"]
    row = next(a for a in approvals if a["target_id"] == proposed["finding_id"])
    assert row["teacher_name"] == teacher["name"] and row["decision"] == "approved"
    entries = client.get("/api/audit", params={"tool": "decide_finding", "limit": 20}).json()["entries"]
    assert any(e["actor"] == f"teacher:{teacher['id']}" for e in entries)
    again = client.post(f"/api/findings/{proposed['finding_id']}/decision",
                        json={"decision": "approved", "teacher_id": teacher["id"]})
    assert again.status_code == 400


def test_inbox_and_runs_do_not_crash(client):
    files = client.get("/api/inbox").json()["files"]
    assert all(f["name"].lower() != "readme.md" for f in files)
    assert client.get("/api/runs").status_code in (200, 503)


def test_index_served_without_external_hosts(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Meska Brain" in r.text
    urls = re.findall(r"https?://[^\s\"'<>)]+", r.text)
    assert [u for u in urls if u != "http://www.w3.org/2000/svg"] == []


def test_page_and_logo_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "/static/brand/meska-white.png" in page.text
    logo = client.get("/static/brand/meska-white.png")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
