"""A ready state for presenting, built without a model.

`meska story` runs the same audited tools the agent uses (find_patterns, trace_root, what_worked,
propose_finding) for three synthetic learners, words each finding with the fixed templates, and
records a few decisions by a synthetic teacher. Every step lands in the audit log with the actor
`demo-setup`, so nobody can mistake it for the agent's work or for a real teacher's decision.
It leaves some findings waiting, so the review queue has something to decide live."""

from __future__ import annotations

from typing import Any

from . import audit, db, review, tools
from .curriculum import load_pack

ACTOR = "demo-setup"
# alias suffix -> finding kinds to approve during setup; everything else stays waiting.
PLAN: dict[str, tuple[str, ...]] = {"A-17": ("strength",), "B-04": (), "C-31": ("strength",)}
MAX_TRACES = 4


def _analyses(learner_id: str, db_path) -> dict[str, Any]:
    patterns = tools.find_patterns(learner_id=learner_id, db_path=db_path)
    targets: list[str] = []
    for p in patterns.get("patterns", []):
        if p["kind"] == "struggle":
            targets.extend(c for c in (p.get("concept_ids") or []) if c not in targets)
    roots = {c: tools.trace_root(learner_id=learner_id, concept_id=c, db_path=db_path) for c in targets[-MAX_TRACES:]}
    return {"patterns": patterns, "roots": roots, "what_worked": tools.what_worked(learner_id=learner_id, db_path=db_path)}


def build(db_path=None) -> dict[str, Any]:
    """Create the presenting state. Safe to run once on a freshly seeded database."""
    from .agent.workflow import _candidates, _template_statement  # deterministic helpers, no model

    with db.connect(db_path) as conn:
        learners = db.rows(conn, "SELECT id, alias, pack_id FROM learners ORDER BY alias")
        teacher = db.one(conn, "SELECT id, name FROM teachers ORDER BY name")
        already = db.one(conn, "SELECT COUNT(*) AS n FROM findings")["n"]
    if already:
        return {"skipped": "There are findings already. Run `meska seed` first for a clean start.", "findings": already}

    token = audit.current_actor.set(ACTOR)
    out: dict[str, Any] = {"proposed": 0, "approved": 0, "waiting": 0, "open_questions": 0, "learners": []}
    try:
        for suffix, approve_kinds in PLAN.items():
            learner = next((row for row in learners if row["alias"].endswith(suffix)), None)
            if learner is None:
                continue
            candidates, questions = _candidates(_analyses(learner["id"], db_path), load_pack(learner["pack_id"]))
            out["open_questions"] += len(questions)
            for candidate in candidates:
                made = tools.propose_finding(
                    learner_id=learner["id"], kind=candidate["kind"], statement=_template_statement(candidate),
                    evidence_ids=candidate["evidence_ids"], concept_ids=candidate["concept_ids"],
                    path=candidate["path"], confidence=candidate["confidence"], db_path=db_path)
                out["proposed"] += 1
                if candidate["kind"] in approve_kinds:
                    review.decide_finding(made["finding_id"], "approved", teacher["id"],
                                          note="Recorded by the demo setup, not by a real teacher.", db_path=db_path)
                    out["approved"] += 1
                else:
                    out["waiting"] += 1
            out["learners"].append(learner["alias"])
    finally:
        audit.current_actor.reset(token)
    out["decisions_recorded_as"] = teacher["name"]
    return out
