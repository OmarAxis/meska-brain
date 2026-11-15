"""Tests for the agent's deterministic parts. No model and no MCP server needed."""

from types import SimpleNamespace

from meska_brain.agent import workflow
from meska_brain.agent.language import looks_like

QUIZ = """# Quiz sheet

Learner: Learner A-17

| Item | Question | Marks | Out of |
|------|----------|-------|--------|
| 1 | Simplify 12:18 | 1 | 2 |
| 2 | Share 40 in 3:5 | 0 | 3 |
| 3 | Explain | - | 2 |
"""


def test_table_row_count_ignores_header_and_rule():
    assert workflow._table_row_count(QUIZ) == 3
    assert workflow._table_row_count("No table here.") == 0


def test_other_learners_detected():
    learner = {"alias": "Learner A-17"}
    assert not workflow._other_learners_in(QUIZ, learner)
    assert workflow._other_learners_in(QUIZ + "\nLearner T-20 was absent.", learner)


def test_score_is_computed_from_copied_marks():
    row = workflow.EvidenceRow(kind="quiz_item", marks=1, out_of=2, quote="Simplify 12:18")
    assert row.score == 0.5
    assert workflow.EvidenceRow(kind="quiz_item", marks=None, out_of=2, quote="x").score is None
    # Marks above the maximum are a misreading: no score rather than a wrong one.
    assert workflow.EvidenceRow(kind="quiz_item", marks=5, out_of=2, quote="x").score is None


def test_language_check_catches_a_neighbouring_language():
    swahili = ("Mtoto wako anafanya vizuri sana katika jiometri na kazi za maumbo. Matokeo yake ya uwiano "
               "yamekuwa ya chini, na hii inaweza kuwa inatokana na mada ya kugawanya ya darasa la tatu.")
    xhosa = ("Umsombululo wakho kwi-Geometry kunye nokuzibona kwisithuba ubonisa ukuba uyazi kakuhle. "
             "Oku kubonisa ukuba uhlala unenkcubeko ekwenzeni oku.")
    english = "Your child does well in geometry and the work has been strong for several terms."
    assert looks_like(swahili, "sw")
    assert not looks_like(xhosa, "sw")
    assert not looks_like(english, "sw")
    assert looks_like(english, "en")
    assert looks_like("يُظهر عمل طفلك في الهندسة نتائج قوية.", "ar")
    assert not looks_like(english, "ar")


def _pack():
    return SimpleNamespace(label=lambda concept_id, lang="en": concept_id.replace("-", " ").title())


def _traced(target, root, confidence=0.7, evidence=("e1", "e2", "e3")):
    return {"target": {"concept_id": target, "label": target, "mean": 0.3, "n": 4},
            "root": {"concept_id": root, "label": root, "grade": 3, "mean": 0.3, "n": 5, "period": "2021-T1"},
            "path": [target, root], "context": [{"type": "absence", "absent_days": 17}],
            "unrecorded_prerequisites_of_root": [], "evidence_ids": list(evidence), "confidence": confidence}


def test_two_topics_with_the_same_root_give_one_finding():
    analyses = {"roots": {"ratio-concept": _traced("ratio-concept", "division-basic", 0.7),
                          "percentages": _traced("percentages", "division-basic", 0.6)},
                "patterns": {"patterns": []}, "what_worked": {"approaches": []}}
    candidates, questions = workflow._candidates(analyses, _pack())
    assert [c["kind"] for c in candidates] == ["root_cause"]
    assert candidates[0]["concept_ids"] == ["ratio-concept", "division-basic"]   # the more confident one
    assert candidates[0]["evidence_ids"] == ["e1", "e2", "e3"]                   # copied from the tool
    assert questions == []


def test_weak_or_missing_roots_become_open_questions_not_findings():
    no_root = {"target": {"concept_id": "fraction-concept", "label": "Fractions", "mean": 0.3, "n": 6},
               "root": None, "reason": "Fractions is low, but there are no records for Division.",
               "evidence_ids": ["e1"], "confidence": 0.0}
    analyses = {"roots": {"fraction-concept": no_root, "ratio-concept": _traced("ratio-concept", "division-basic", 0.2)},
                "patterns": {"patterns": []}, "what_worked": {"approaches": []}}
    candidates, questions = workflow._candidates(analyses, _pack())
    assert candidates == []
    assert len(questions) == 2
    assert "no records" in questions[0]


def test_root_over_a_hole_in_the_record_becomes_a_question():
    uncertain = {**_traced("percentages", "fraction-concept", 0.35), "root_is_certain": False,
                 "reason": "Percentages is low. The difficulty may begin earlier: there are no records for Division."}
    analyses = {"roots": {"percentages": uncertain}, "patterns": {"patterns": []}, "what_worked": {"approaches": []}}
    candidates, questions = workflow._candidates(analyses, _pack())
    assert candidates == []
    assert questions == [uncertain["reason"]]


def test_same_evidence_is_one_claim():
    def strength(label, ids, confidence):
        return {"kind": "strength", "scope": "strand", "scope_id": label, "label": label, "periods": ["a", "b", "c"],
                "mean": 0.9, "n_items": len(ids), "evidence_ids": ids, "confidence": confidence, "concept_ids": []}
    geometry = strength("geometry", [f"e{i}" for i in range(22)], 0.85)
    spatial = strength("spatial-reasoning", [f"e{i}" for i in range(19)], 0.83)      # a subset of geometry's rows
    number = strength("number", [f"n{i}" for i in range(10)], 0.7)
    analyses = {"roots": {}, "patterns": {"patterns": [geometry, spatial, number]}, "what_worked": {"approaches": []}}
    candidates, _ = workflow._candidates(analyses, _pack())
    assert [c["facts"]["in"] for c in candidates] == ["geometry", "number"]


def test_a_note_may_not_add_numbers():
    source = "Results in geometry averaged 91% across five terms. Division averaged 33% in 2021."
    assert workflow._numbers_not_in("Your child's geometry results averaged 91%.", source) == []
    assert workflow._numbers_not_in("Practise for 5 minutes each day; geometry is at 91%.", source) == ["5"]
    assert workflow._numbers_not_in("متوسط النتائج ٩١٪", source) == []          # Arabic-Indic digits are read too


def test_what_worked_needs_more_wins_than_losses():
    def approach(improved, not_improved):
        return {"approach_id": "x", "label": "Hands-on objects", "improved": improved, "not_improved": not_improved,
                "mean_gain": 0.2, "instances": [{"concept_id": "volume", "evidence_ids": ["e1", "e2"]}]}
    base = {"roots": {}, "patterns": {"patterns": []}}
    assert workflow._candidates({**base, "what_worked": {"approaches": [approach(3, 0)]}}, _pack())[0][0]["kind"] == "what_worked"
    assert workflow._candidates({**base, "what_worked": {"approaches": [approach(1, 0)]}}, _pack())[0] == []
    assert workflow._candidates({**base, "what_worked": {"approaches": [approach(2, 4)]}}, _pack())[0] == []


def test_a_handover_note_must_not_be_written_to_a_parent():
    to_parent = "Your child demonstrates strong potential but struggles with ratio comparisons."
    assert workflow._speaks_to_wrong_reader(to_parent, "teacher_handover")
    assert not workflow._speaks_to_wrong_reader(to_parent, "guardian")
    assert not workflow._speaks_to_wrong_reader("This learner's ratio results have been low.", "teacher_handover")


def test_a_shortened_alias_is_still_the_same_learner():
    # Found by running a teacher note by hand: the model read "Learner C-31" as "C-31"
    # and the whole note was refused as belonging to someone else.
    assert workflow._same_learner("C-31", "Learner C-31")
    assert workflow._same_learner("learner c-31", "Learner C-31")
    assert workflow._same_learner(None, "Learner C-31")
    assert not workflow._same_learner("C-13", "Learner C-31")
    assert not workflow._same_learner("Learner A-17", "Learner C-31")
    assert not workflow._same_learner("Amina", "Learner C-31")


def test_grade_comes_from_enrolment_when_the_document_gives_none():
    learner = {"start_year": 2021, "start_grade": 3}
    assert workflow._grade_in(learner, 2025) == 7
    assert workflow._grade_in(learner, 2021) == 3
    assert workflow._grade_in({"grade_now": 6}, 2025) == 6
    assert workflow._grade_in({}, 2025) is None
