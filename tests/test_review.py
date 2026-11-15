import pytest

from meska_brain import db, review, tools


def _propose(db_path) -> str:
    return tools.propose_finding(
        learner_id="lrn_b", kind="strength", evidence_ids=["evd_b01", "evd_b07"],
        statement="Geometry items above 0.8 for four terms in a row.", db_path=db_path)["finding_id"]


def _approvals(db_path) -> list[dict]:
    with db.connect(db_path) as conn:
        return db.rows(conn, "SELECT * FROM approvals ORDER BY id")


def _last_audit(db_path) -> dict:
    with db.connect(db_path) as conn:
        return db.one(conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 1")


def test_pending_expands_evidence(db_path):
    finding_id = _propose(db_path)
    result = review.pending(db_path=db_path)
    assert [f["id"] for f in result["findings"]] == [finding_id]
    assert [e["id"] for e in result["findings"][0]["evidence"]] == ["evd_b01", "evd_b07"]
    assert result["summaries"] == []


def test_approve_writes_approval_with_teacher_name(db_path):
    finding_id = _propose(db_path)
    result = review.decide_finding(finding_id, "approved", "tch_amina", note="Matches my notes", db_path=db_path)
    assert result["status"] == "approved" and result["decided_by"] == "tch_amina"
    approval = _approvals(db_path)[-1]
    assert (approval["target_type"], approval["target_id"], approval["decision"]) == ("finding", finding_id,
                                                                                      "approved")
    assert approval["teacher_name"] == "Amina Okafor" and approval["note"] == "Matches my notes"
    audit_row = _last_audit(db_path)
    assert audit_row["tool"] == "decide_finding" and audit_row["actor"] == "teacher:tch_amina"
    assert review.pending(db_path=db_path)["findings"] == []


def test_edit_replaces_statement(db_path):
    finding_id = _propose(db_path)
    result = review.decide_finding(finding_id, "edited", "tch_jean", db_path=db_path,
                                   edited_statement="Geometry quiz and project work above 0.8 since 2021-T1.")
    assert result["status"] == "edited"
    assert result["statement"] == "Geometry quiz and project work above 0.8 since 2021-T1."
    assert _approvals(db_path)[-1]["teacher_name"] == "Jean Dupont"


def test_edit_needs_a_clean_statement(db_path):
    finding_id = _propose(db_path)
    with pytest.raises(ValueError, match="edited_statement"):
        review.decide_finding(finding_id, "edited", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="label on a child"):
        review.decide_finding(finding_id, "edited", "tch_jean", edited_statement="A gifted child.", db_path=db_path)


def test_reject_and_deciding_twice_raises(db_path):
    finding_id = _propose(db_path)
    review.decide_finding(finding_id, "rejected", "tch_jean", note="Too early", db_path=db_path)
    assert _approvals(db_path)[-1]["decision"] == "rejected"
    with pytest.raises(ValueError, match="already decided"):
        review.decide_finding(finding_id, "approved", "tch_amina", db_path=db_path)
    assert len(_approvals(db_path)) == 1


def test_unknown_teacher_and_bad_decision_raise(db_path):
    finding_id = _propose(db_path)
    with pytest.raises(ValueError, match="Unknown teacher"):
        review.decide_finding(finding_id, "approved", "tch_ghost", db_path=db_path)
    with pytest.raises(ValueError, match="Decision must be"):
        review.decide_finding(finding_id, "maybe", "tch_amina", db_path=db_path)
    assert _approvals(db_path) == []


def test_summary_flow(db_path):
    finding_id = _propose(db_path)
    review.decide_finding(finding_id, "approved", "tch_amina", db_path=db_path)
    summary_id = tools.draft_summary(learner_id="lrn_b", finding_ids=[finding_id], audience="guardian",
                                     language="fr", text="Les activités de géométrie réussissent bien.",
                                     db_path=db_path)["summary_id"]
    pending = review.pending(db_path=db_path)["summaries"]
    assert [s["id"] for s in pending] == [summary_id]
    assert pending[0]["findings"][0]["id"] == finding_id

    result = review.decide_summary(summary_id, "approved", "tch_jean", db_path=db_path)
    assert result["status"] == "approved"
    approval = _approvals(db_path)[-1]
    assert (approval["target_type"], approval["teacher_name"]) == ("summary", "Jean Dupont")
    assert _last_audit(db_path)["actor"] == "teacher:tch_jean"
    with pytest.raises(ValueError, match="already decided"):
        review.decide_summary(summary_id, "rejected", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="Decision must be"):
        review.decide_summary(summary_id, "edited", "tch_jean", db_path=db_path)
    with pytest.raises(ValueError, match="Unknown teacher"):
        review.decide_summary(summary_id, "approved", "tch_ghost", db_path=db_path)


def test_decision_is_undone_if_its_audit_row_cannot_be_written(db_path, monkeypatch):
    finding_id = _propose(db_path)

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(review.audit, "write_row", broken)
    with pytest.raises(RuntimeError):
        review.decide_finding(finding_id, "approved", "tch_amina", db_path=db_path)
    with db.connect(db_path) as conn:
        assert db.one(conn, "SELECT status FROM findings WHERE id = ?", (finding_id,))["status"] == "proposed"
    assert _approvals(db_path) == []
