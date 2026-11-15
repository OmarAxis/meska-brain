"""The agent as a LangGraph state machine.

    load_learner -> read_document -> extract_evidence -> record_evidence
        -> investigate -> compose_findings -> propose_findings
        -> [teacher gate 1] -> draft_summaries -> [teacher gate 2] -> done

Division of labour, on purpose:
- The MODEL reads documents, decides which analysis tools to call, and words text.
- The MCP TOOLS hold all learner data and do all reasoning over the graph.
- EVIDENCE IDS never come from the model. They are copied from tool results, so a claim
  cannot cite something that is not in the records.
- A TEACHER approves findings and summaries. The agent has no tool that can approve.
"""

from __future__ import annotations

import json
import operator
import re
import time
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .. import db, guard
from ..curriculum import load_pack
from . import prompts
from .language import language_name, looks_like
from .llm import Usage, timed_invoke
from .mcp_io import McpHub, ToolError

ANALYSIS_TOOLS = ["find_patterns", "trace_root", "what_worked", "get_learner_timeline"]
MAX_TOOL_CALLS = 6
MIN_ROOT_CONFIDENCE = 0.4
MAX_PATTERN_FINDINGS = 3
TEXT_SUFFIXES = {".txt", ".md", ".csv"}

# Live objects for a run (MCP sessions, model, usage). Kept out of the graph state because
# the state is checkpointed to disk and these cannot be serialised.
RESOURCES: dict[str, dict] = {}


class RunState(TypedDict, total=False):
    run_id: str
    learner_id: str
    inbox_file: str | None
    learner: dict
    document_text: str
    extraction: dict
    recorded: list[dict]
    analyses: dict
    candidates: list[dict]
    open_questions: list[str]
    finding_ids: list[str]
    approved_finding_ids: list[str]
    summary_ids: list[str]
    steps: Annotated[list[dict], operator.add]


class EvidenceRow(BaseModel):
    kind: Literal["quiz_item", "assignment", "project", "observation", "attendance"]
    concept_id: str | None = None
    # The model copies the marks as written; the code does the division. Small models are
    # reliable at copying two numbers and unreliable at arithmetic.
    marks: float | None = Field(default=None, ge=0)
    out_of: float | None = Field(default=None, gt=0)
    absent_days: int | None = Field(default=None, ge=0)
    quote: str
    language: str = "en"

    @property
    def score(self) -> float | None:
        if self.marks is None or self.out_of is None or self.marks > self.out_of:
            return None
        return round(self.marks / self.out_of, 3)


class Extraction(BaseModel):
    learner_alias: str | None = None
    year: int | None = None
    term: int | None = Field(default=None, ge=1, le=3)
    grade: int | None = None
    rows: list[EvidenceRow]


def _step(node: str, note: str, ok: bool = True, **extra) -> dict:
    return {"steps": [{"node": node, "ts": db.now_iso(), "ok": ok, "note": note, **extra}]}


def _res(state: RunState) -> tuple[McpHub, object, Usage]:
    r = RESOURCES[state["run_id"]]
    return r["hub"], r["llm"], r["usage"]


# --------------------------------------------------------------------------- nodes

async def load_learner(state: RunState) -> dict:
    hub, _, _ = _res(state)
    timeline = await hub.call("get_learner_timeline", learner_id=state["learner_id"], limit=1)
    learner = timeline["learner"]
    return {"learner": learner, **_step("load_learner", f"Loaded {learner.get('alias', state['learner_id'])}.")}


async def read_document(state: RunState) -> dict:
    """Convert the incoming file to text with the borrowed markitdown server.
    Recovery: if conversion fails and the file is plain text, read it directly."""
    path = state.get("inbox_file")
    if not path:
        return _step("read_document", "No new document. Reviewing existing records only.")
    hub, _, _ = _res(state)
    file = Path(path)
    try:
        text = await hub.convert_document(file)
        return {"document_text": text, **_step("read_document", f"Converted {file.name} with markitdown ({len(text)} chars).")}
    except Exception as exc:  # noqa: BLE001 - any failure here has the same recovery
        if file.suffix.lower() in TEXT_SUFFIXES:
            text = file.read_text(encoding="utf-8", errors="replace")
            return {"document_text": text,
                    **_step("read_document", f"markitdown failed ({exc}); recovered by reading {file.name} as text.")}
        return {"document_text": "",
                **_step("read_document", f"Could not read {file.name}: {exc}. Nothing recorded from it.", ok=False)}


def _concept_menu(pack, grade_now: int | None) -> str:
    concepts = [c for c in pack.concepts.values() if grade_now is None or c.grade <= grade_now + 1]
    return "\n".join(f"{c.id}: {pack.label(c.id)} (grade {c.grade})" for c in sorted(concepts, key=lambda c: (c.grade, c.id)))


def _table_row_count(text: str) -> int:
    """Data rows in a markdown table: lines starting with '|', minus the header and the rule."""
    lines = [line for line in text.splitlines() if line.strip().startswith("|")]
    rules = [line for line in lines if set(line.strip()) <= set("|-: ")]
    return max(0, len(lines) - len(rules) - (1 if rules else 0))


def _squash(text: str) -> str:
    """Text reduced to letters and digits, so table pipes, commas and spacing do not matter."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _other_learners_in(text: str, learner: dict) -> bool:
    """True when the document names learners other than the target (so fewer rows is correct)."""
    names = set(re.findall(r"Learner [A-Z]-\d+", text))
    return bool(names - {learner.get("alias")})


def _same_learner(named: str | None, alias: str | None) -> bool:
    """True when the alias the model read is the target learner. Models often shorten
    'Learner C-31' to 'C-31', so the code part (letter, dash, number) is compared when both have one."""
    named, alias = (named or "").strip().lower(), (alias or "").strip().lower()
    if not named:
        return True
    code = r"(?<![a-z])[a-z]-\d+"
    named_codes, alias_codes = re.findall(code, named), re.findall(code, alias)
    if named_codes and alias_codes:
        return named_codes == alias_codes
    return named == alias


def _grade_in(learner: dict, year: int | None) -> int | None:
    """The grade the learner is in for a school year, from when they were first enrolled."""
    if year is None or learner.get("start_year") is None or learner.get("start_grade") is None:
        return learner.get("grade_now")
    return int(learner["start_grade"]) + (int(year) - int(learner["start_year"]))


class Period(BaseModel):
    year: int | None = None
    term: int | None = Field(default=None, ge=1, le=3)


async def _ask_period(llm, usage: Usage, text: str) -> tuple[int | None, int | None]:
    question = ("Which school year and term (1, 2 or 3) is this document about? The term may be written in words "
                "in any language, for example 'first term', 'muhula wa kwanza', 'premier trimestre', "
                "'الفصل الأول'. Use null when the document does not say.\n\nDOCUMENT:\n" + text[:3000])
    started = time.perf_counter()
    try:
        out = await llm.with_structured_output(Period, method="json_schema", include_raw=True).ainvoke(question)
    except Exception:  # noqa: BLE001
        return None, None
    usage.add("extract_evidence#period", out.get("raw"), time.perf_counter() - started)
    period = out.get("parsed")
    return (period.year, period.term) if period else (None, None)


async def extract_evidence(state: RunState) -> dict:
    """The model reads the document into rows. Recovery: one retry with the validation error;
    after that the document is left for a teacher instead of being guessed at."""
    text = state.get("document_text") or ""
    if not text.strip():
        return {"extraction": {"rows": []}}
    _, llm, usage = _res(state)
    learner = state["learner"]
    # Checked in code, before the model sees anything: a document that names other learners
    # and not this one must never be recorded here, whatever the model (or the document) says.
    named = set(re.findall(r"Learner [A-Z]-\d+", text))
    if named and learner.get("alias") not in named:
        return {"extraction": {"rows": []},
                **_step("extract_evidence", f"Document names {', '.join(sorted(named))}, not {learner.get('alias')}. "
                        "Nothing recorded: a record must not land on the wrong learner.", ok=False, refused="wrong_learner")}
    pack = load_pack(learner.get("pack_id"))
    messages = [
        SystemMessage(prompts.EXTRACT_SYSTEM),
        HumanMessage(f"TARGET LEARNER: {learner.get('alias')}\n\nCONCEPTS:\n{_concept_menu(pack, learner.get('grade_now'))}"
                     f"\n\nDOCUMENT ({Path(state['inbox_file']).name}):\n{text[:8000]}"),
    ]
    structured = llm.with_structured_output(Extraction, method="json_schema", include_raw=True)
    table_rows = _table_row_count(text)
    extraction, error, notes = None, None, []
    for attempt in (1, 2, 3):
        started = time.perf_counter()
        try:
            out = await structured.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 - the model being down must not end the run
            error = f"{type(exc).__name__}: {exc}"
            break
        usage.add(f"extract_evidence#{attempt}", out.get("raw"), time.perf_counter() - started)
        if out.get("parsed") is None:
            error = str(out.get("parsing_error"))
            messages.append(HumanMessage(f"Your last reply did not match the schema: {error[:400]}. "
                                         "Reply again, following the schema exactly."))
            continue
        extraction = out["parsed"]
        # Self-check: a table with N rows must give N rows. Small models tend to drop the last one.
        if table_rows and len(extraction.rows) < table_rows and attempt < 3 and not _other_learners_in(text, learner):
            notes.append(f"first reading had {len(extraction.rows)} of {table_rows} table rows, asked again")
            messages += [out["raw"], HumanMessage(f"The table has {table_rows} rows but you returned {len(extraction.rows)}. "
                                                  "Return every row, including items that were not attempted (score null).")]
            continue
        break
    if extraction is None:
        return {"extraction": {"rows": []},
                **_step("extract_evidence", f"The model could not produce valid rows after retries ({error}). Left for a teacher.", ok=False)}
    if extraction.year is None or extraction.term is None:
        # Recovery: ask one narrow question about the date instead of giving up on the document.
        year, term = await _ask_period(llm, usage, text)
        if year and term:
            extraction.year, extraction.term = year, term
            notes.append("term found with a follow-up question")

    # Self-checks on what the model returned.
    if not _same_learner(extraction.learner_alias, learner.get("alias")):
        return {"extraction": {"rows": []},
                **_step("extract_evidence", f"Document names '{extraction.learner_alias}', not {learner.get('alias')}. "
                        "Nothing recorded: a record must not land on the wrong learner.", ok=False)}
    document_words = _squash(text)
    kept = []
    for row in extraction.rows:
        if row.concept_id and row.concept_id not in pack.concepts:
            notes.append(f"dropped unknown concept id '{row.concept_id}'")
            row.concept_id = None
        about_others = set(re.findall(r"Learner [A-Z]-\d+", row.quote)) - {learner.get("alias")}
        if about_others:
            notes.append("dropped a row about another learner")
        # A row whose quote is not in the document has no source, so it is not recorded.
        elif _squash(row.quote)[:20] and _squash(row.quote)[:20] in document_words:
            kept.append(row)
        else:
            notes.append("dropped a row whose quote is not in the document")
    extraction.rows = kept
    if extraction.year is None or extraction.term is None:
        match = re.search(r"(20\d{2})-T([1-3])", Path(state["inbox_file"]).name)
        if match:
            extraction.year, extraction.term = int(match.group(1)), int(match.group(2))
            notes.append("term taken from the file name")
    if extraction.year is None or extraction.term is None:
        return {"extraction": {"rows": []},
                **_step("extract_evidence", "The document has no year and term. Nothing recorded; a teacher should add them.", ok=False)}
    note = f"Read {len(extraction.rows)} rows for {extraction.year}-T{extraction.term}."
    if notes:
        note += " Checks: " + "; ".join(sorted(set(notes))) + "."
    data = extraction.model_dump()
    for row, parsed in zip(data["rows"], extraction.rows, strict=True):
        row["score"] = parsed.score if parsed.kind in ("quiz_item", "assignment", "project") else None
    return {"extraction": data, **_step("extract_evidence", note)}


async def record_evidence(state: RunState) -> dict:
    extraction = state.get("extraction") or {}
    rows = extraction.get("rows") or []
    if not rows:
        return {"recorded": []}
    hub, _, _ = _res(state)
    learner = state["learner"]
    file_name = Path(state["inbox_file"]).name
    recorded, problems = [], []
    for index, row in enumerate(rows, start=1):
        try:
            result = await hub.call(
                "record_evidence", learner_id=state["learner_id"], kind=row["kind"],
                year=extraction["year"], term=extraction["term"],
                grade=extraction.get("grade") or _grade_in(learner, extraction["year"]) or 0,
                source_ref=f"{file_name}#row{index}", concept_id=row.get("concept_id"),
                score=row.get("score"), absent_days=row.get("absent_days"),
                raw_text=row.get("quote"), language=row.get("language") or "en")
            recorded.append({**result, "concept_id": row.get("concept_id"), "score": row.get("score")})
        except ToolError as exc:
            problems.append(f"row {index}: {exc}")
    note = f"Recorded {len(recorded)} of {len(rows)} rows."
    if problems:
        note += " Not recorded: " + " | ".join(problems[:3])
    return {"recorded": recorded, **_step("record_evidence", note, ok=not problems)}


def _struggle_concepts(analyses: dict, recorded: list[dict]) -> list[str]:
    """Concepts worth tracing: concept-level struggles, plus anything just recorded with a low score."""
    # For a strand- or skill-level struggle the engine lists the low concepts inside it,
    # most recent first; the most recent one is where the teacher feels the problem today.
    concepts = [p["concept_ids"][0] for p in (analyses.get("patterns") or {}).get("patterns", [])
                if p["kind"] == "struggle" and p.get("concept_ids")]
    low = {}
    for row in recorded:
        if row.get("concept_id") and row.get("score") is not None:
            low.setdefault(row["concept_id"], []).append(row["score"])
    concepts += [c for c, scores in low.items() if sum(scores) / len(scores) < 0.5]
    return list(dict.fromkeys(concepts))


async def investigate(state: RunState) -> dict:
    """The model plans and calls analysis tools. Afterwards the agent checks coverage and fills
    any gap itself, and says so in the step note, so a weak plan cannot silently hide a pattern."""
    hub, llm, usage = _res(state)
    learner_id = state["learner_id"]
    analyses: dict = {"patterns": None, "roots": {}, "what_worked": None}
    specs = await hub.tool_specs(ANALYSIS_TOOLS)
    recorded = state.get("recorded") or []
    new_info = ""
    if recorded:
        new_info = "New evidence was just recorded for concepts: " + ", ".join(
            sorted({r["concept_id"] for r in recorded if r.get("concept_id")})) + "."
    messages = [SystemMessage(prompts.INVESTIGATE_SYSTEM),
                HumanMessage(f"Learner id: {learner_id}. {new_info} Investigate this learner.")]
    model_calls: list[str] = []
    seen: set[str] = set()
    bound = llm.bind_tools(specs)
    try:
        while len(model_calls) < MAX_TOOL_CALLS:
            reply: AIMessage = await timed_invoke(bound, messages, usage, "investigate")
            messages.append(reply)
            if not reply.tool_calls:
                break
            for call in reply.tool_calls:
                key = call["name"] + json.dumps(call["args"], sort_keys=True)
                if key in seen or call["name"] not in ANALYSIS_TOOLS or len(model_calls) >= MAX_TOOL_CALLS:
                    messages.append(ToolMessage("Skipped: repeated, unknown, or over the call limit.", tool_call_id=call["id"]))
                    continue
                seen.add(key)
                # The model chooses WHICH analysis to run. It does not choose the learner or
                # the evidence bar: those are fixed by the run and by the server.
                args = {**call["args"], "learner_id": learner_id}
                args.pop("min_periods", None)
                try:
                    result = await hub.call(call["name"], **args)
                    _store(analyses, call["name"], args, result)
                    model_calls.append(call["name"])
                    content = json.dumps(_brief(result), ensure_ascii=False)[:3000]
                except ToolError as exc:
                    content = f"Tool error: {exc}"  # the model sees the error and can correct its call
                messages.append(ToolMessage(content, tool_call_id=call["id"]))
    except Exception as exc:  # noqa: BLE001 - a model failure must not end the run
        model_calls.append(f"(model failed: {type(exc).__name__})")

    filled: list[str] = []
    if analyses["patterns"] is None:
        analyses["patterns"] = await hub.call("find_patterns", learner_id=learner_id)
        filled.append("find_patterns")
    for concept in _struggle_concepts(analyses, recorded):
        if concept not in analyses["roots"]:
            try:
                analyses["roots"][concept] = await hub.call("trace_root", learner_id=learner_id, concept_id=concept)
                filled.append(f"trace_root({concept})")
            except ToolError:
                pass
    if analyses["what_worked"] is None:
        analyses["what_worked"] = await hub.call("what_worked", learner_id=learner_id)
        filled.append("what_worked")
    note = f"Model chose: {', '.join(model_calls) or 'no tools'}."
    note += f" Coverage check added: {', '.join(filled)}." if filled else " Coverage check added nothing."
    return {"analyses": analyses, **_step("investigate", note, model_calls=model_calls, filled=filled)}


def _store(analyses: dict, tool: str, args: dict, result: dict) -> None:
    if tool == "find_patterns":
        analyses["patterns"] = result
    elif tool == "trace_root":
        analyses["roots"][args.get("concept_id")] = result
    elif tool == "what_worked":
        analyses["what_worked"] = result


def _brief(result: dict) -> dict:
    """Tool results for the model's eyes: drop long id lists to keep the context small."""
    def trim(value):
        if isinstance(value, dict):
            return {k: trim(v) for k, v in value.items() if k not in ("evidence_ids", "instances")}
        if isinstance(value, list):
            return [trim(v) for v in value[:8]]
        return value
    return trim(result)


def _candidates(analyses: dict, pack) -> tuple[list[dict], list[str]]:
    """Turn tool results into candidate findings. Deterministic: no model involved."""
    candidates, open_questions = [], []
    by_root: dict[str, dict] = {}
    for concept, traced in (analyses.get("roots") or {}).items():
        root = traced.get("root")
        if not root:
            if traced.get("target", {}).get("mean") is not None and traced["target"]["mean"] < 0.5:
                open_questions.append(traced.get("reason", f"No root found for {pack.label(concept)}."))
            continue  # the concept is not low, or has no records: nothing to say
        if not traced.get("root_is_certain", True):
            # There is a hole in the record right under this root. Naming it as the cause
            # would be a guess, so it goes to the teacher as a question, with the reason.
            open_questions.append(traced.get("reason") or f"Where the difficulty with {pack.label(concept)} began cannot be told from the records.")
            continue
        if traced.get("confidence", 0) < MIN_ROOT_CONFIDENCE or len(traced.get("evidence_ids", [])) < 2:
            open_questions.append(f"A possible starting point for the difficulty with {pack.label(concept)} is "
                                  f"{root['label']}, but there is too little evidence to propose it.")
            continue
        starts_here = root["concept_id"] == concept
        candidate = {
            "kind": "root_cause", "concept_ids": list(dict.fromkeys([concept, root["concept_id"]])),
            "path": traced.get("path", []), "evidence_ids": traced["evidence_ids"], "confidence": traced["confidence"],
            "facts": {"struggling_with": traced["target"]["label"],
                      "possible_root": "this topic itself; earlier topics it builds on look fine" if starts_here else root["label"],
                      "root_taught_in_grade": root.get("grade"), "root_period": root.get("period"),
                      "root_average": root.get("mean"), "root_items": root.get("n"),
                      "days_absent_in_that_term": sum(c.get("absent_days", 0) for c in traced.get("context", [])),
                      "earlier_topics_with_no_records": [pack.label(c) for c in traced.get("unrecorded_prerequisites_of_root", [])]},
            "starts_here": starts_here,
        }
        # Several recent topics often lead back to the same root: keep one finding per root.
        best = by_root.get(root["concept_id"])
        if best is None or candidate["confidence"] > best["confidence"]:
            by_root[root["concept_id"]] = candidate
    candidates.extend(by_root.values())
    patterns = sorted((analyses.get("patterns") or {}).get("patterns", []), key=lambda p: -p.get("confidence", 0))
    traced_concepts = set((analyses.get("roots") or {}).keys())
    kept = 0
    for p in patterns:
        if kept >= MAX_PATTERN_FINDINGS or len(p.get("evidence_ids", [])) < 2:
            continue
        if p["kind"] == "struggle" and set(p.get("concept_ids") or []) & traced_concepts and by_root:
            continue  # already covered by a root-cause finding, which says more
        kept += 1
        candidates.append({
            "kind": p["kind"], "concept_ids": [p["scope_id"]] if p["scope"] == "concept" else [], "path": [],
            "evidence_ids": p["evidence_ids"], "confidence": p["confidence"],
            "facts": {"pattern": p["kind"], "in": p["label"], "level": p["scope"], "terms": p["periods"],
                      "average": p["mean"], "items": p["n_items"]},
        })
    for a in (analyses.get("what_worked") or {}).get("approaches", []):
        ids = [e for inst in a.get("instances", []) for e in inst.get("evidence_ids", [])]
        if a.get("improved", 0) >= 2 and a["improved"] > a.get("not_improved", 0) and ids:
            candidates.append({
                "kind": "what_worked", "concept_ids": [i["concept_id"] for i in a["instances"]], "path": [],
                "evidence_ids": list(dict.fromkeys(ids)), "confidence": min(0.9, 0.4 + 0.15 * a["improved"]),
                "facts": {"teaching_approach": a["label"], "times_followed_by_improvement": a["improved"],
                          "times_not": a.get("not_improved", 0), "average_gain": a.get("mean_gain"),
                          "topics": [pack.label(i["concept_id"]) for i in a["instances"]]},
            })
    return _without_repeats(candidates), list(dict.fromkeys(open_questions))


def _same_claim(a: dict, b: dict) -> bool:
    """Two findings of the same kind resting on mostly the same evidence are one claim.
    (A skill strength is often the same rows as its strand's strength.)"""
    if a["kind"] != b["kind"]:
        return False
    first, second = set(a["evidence_ids"]), set(b["evidence_ids"])
    return bool(first and second) and len(first & second) / min(len(first), len(second)) >= 0.8


def _without_repeats(candidates: list[dict]) -> list[dict]:
    """Keep the more confident of any two candidates that make the same claim."""
    kept: list[dict] = []
    for candidate in sorted(candidates, key=lambda c: -c["confidence"]):
        if not any(_same_claim(candidate, other) for other in kept):
            kept.append(candidate)
    return kept


def _template_statement(candidate: dict) -> str:
    """Fallback wording when the model's statement does not pass the guard."""
    f = candidate["facts"]
    if candidate["kind"] == "root_cause" and candidate.get("starts_here"):
        return (f"Results in {f['struggling_with']} have been low (average {round((f.get('root_average') or 0) * 100)}%), "
                "while the earlier topics it builds on look fine, which suggests the difficulty starts with this topic.")
    if candidate["kind"] == "root_cause":
        text = (f"Recent difficulty with {f['struggling_with']} may trace back to {f['possible_root']}, "
                f"where results averaged {round((f.get('root_average') or 0) * 100)}% in {f.get('root_period')}. "
                f"It is worth checking {f['possible_root']} directly before reteaching {f['struggling_with']}.")
        if f.get("earlier_topics_with_no_records"):
            text += (" The difficulty may begin even earlier: there are no records for "
                     + ", ".join(f["earlier_topics_with_no_records"]) + ".")
        return text
    if candidate["kind"] == "what_worked":
        return (f"Results improved {f['times_followed_by_improvement']} times after units taught with "
                f"{f['teaching_approach']}, which suggests this approach suits how this learner picks up new topics.")
    word = "strong" if candidate["kind"] == "strength" else "low"
    return (f"Results in {f['in']} have been consistently {word} across {len(f['terms'])} terms "
            f"(average {round(f['average'] * 100)}% over {f['items']} items).")


async def compose_findings(state: RunState) -> dict:
    hub, llm, usage = _res(state)
    pack = load_pack(state["learner"].get("pack_id"))
    candidates, open_questions = _candidates(state.get("analyses") or {}, pack)
    # Skip what a teacher has already been shown (approved or rejected), so a rerun does
    # not flood the review list with the same claim.
    existing = (await hub.call("get_findings", learner_id=state["learner_id"]))["findings"]
    fresh = [c for c in candidates if not any(_same_claim(c, old) for old in existing)]
    fallbacks = 0
    for candidate in fresh:
        statement, problems = "", ["not written"]
        facts = {k: (f"{round(v * 100)}%" if "average" in k and isinstance(v, float) else v)
                 for k, v in candidate["facts"].items() if k != "items" and v not in (None, [], 0)}
        messages = [SystemMessage(prompts.WORD_SYSTEM),
                    HumanMessage("FACTS:\n" + json.dumps(facts, ensure_ascii=False))]
        for _ in (1, 2):
            try:
                reply = await timed_invoke(llm, messages, usage, "compose_findings")
            except Exception:  # noqa: BLE001
                break
            statement = (reply.content or "").strip().strip('"')
            problems = guard.check_statement(statement) if statement else ["empty"]
            if not problems:
                break
            messages += [reply, HumanMessage("Rewrite it. Problems: " + "; ".join(problems))]
        if problems:
            statement, fallbacks = _template_statement(candidate), fallbacks + 1
        candidate["statement"] = statement
    note = (f"{len(candidates)} candidate finding(s), {len(fresh)} not seen by a teacher before. "
            f"{fallbacks} statement(s) used the template after the guard rejected the model's wording. "
            f"{len(open_questions)} open question(s) left unanswered rather than guessed.")
    return {"candidates": fresh, "open_questions": open_questions, **_step("compose_findings", note)}


async def propose_findings(state: RunState) -> dict:
    hub, _, _ = _res(state)
    finding_ids, problems = [], []
    for c in state.get("candidates") or []:
        # Recovery: if the server refuses the model's wording, try once more with the plain template.
        for statement in (c["statement"], _template_statement(c)):
            try:
                result = await hub.call("propose_finding", learner_id=state["learner_id"], kind=c["kind"],
                                        statement=statement, evidence_ids=c["evidence_ids"],
                                        concept_ids=c["concept_ids"], path=c["path"], confidence=c["confidence"])
                finding_ids.append(result["finding_id"])
                break
            except ToolError as exc:
                problems.append(str(exc)[:160])
    note = f"Proposed {len(finding_ids)} finding(s) for teacher review."
    if problems:
        note += " Refused by the server: " + " | ".join(problems)
    return {"finding_ids": finding_ids, **_step("propose_findings", note, ok=len(finding_ids) == len(state.get("candidates") or []))}


async def _finding_statuses(hub: McpHub, learner_id: str, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    found = (await hub.call("get_findings", learner_id=learner_id, finding_ids=ids))["findings"]
    return {f["finding_id"]: f["status"] for f in found}


async def _summary_statuses(hub: McpHub, learner_id: str, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    found = (await hub.call("get_summaries", learner_id=learner_id, summary_ids=ids))["summaries"]
    return {s["summary_id"]: s["status"] for s in found}


async def teacher_gate_findings(state: RunState) -> dict:
    """GATE 1. The run stops here until a named teacher has decided every proposed finding.
    The agent can only look (get_findings). Deciding is not a tool it has."""
    hub, _, _ = _res(state)
    ids = state.get("finding_ids") or []
    # On resume LangGraph runs this node again from the top, and the first interrupt() returns
    # instead of pausing. So the check is a loop: if a teacher resumed early, with items still
    # undecided, the second pass pauses again.
    while True:
        statuses = await _finding_statuses(hub, state["learner_id"], ids)
        waiting = [i for i, s in statuses.items() if s == "proposed"]
        if not waiting:
            break
        interrupt({"gate": "findings", "waiting_for": waiting})
    approved = [i for i, s in statuses.items() if s in ("approved", "edited")]
    return {"approved_finding_ids": approved,
            **_step("teacher_gate_findings", f"Teacher decided {len(ids)} finding(s): {len(approved)} approved.")}


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _numbers_not_in(text: str, source: str) -> list[str]:
    """Numbers in a note that do not appear in the approved findings it is built from.
    A cheap faithfulness check: a note may leave numbers out, it may not add new ones."""
    allowed = set(re.findall(r"\d+", source.translate(_DIGITS)))
    return sorted(set(re.findall(r"\d+", text.translate(_DIGITS))) - allowed)


def _speaks_to_wrong_reader(text: str, audience: str) -> bool:
    """A handover note is read by the next teacher. Small models often write it to a parent instead."""
    return audience == "teacher_handover" and bool(re.search(r"\byour (child|son|daughter)\b", text, re.IGNORECASE))


async def draft_summaries(state: RunState) -> dict:
    """Only approved findings reach here. The model words the notes; the server refuses any
    summary that cites an unapproved finding or fails the guard."""
    hub, llm, usage = _res(state)
    approved = state.get("approved_finding_ids") or []
    found = (await hub.call("get_findings", learner_id=state["learner_id"], finding_ids=approved))["findings"]
    # Re-read at the moment of writing: only what is approved now, in the teacher's final wording.
    findings = [{"kind": f["kind"], "statement": f["statement"]} for f in found if f["status"] in ("approved", "edited")]
    approved = [f["finding_id"] for f in found if f["status"] in ("approved", "edited")]
    if not findings:
        return {"summary_ids": [], **_step("draft_summaries", "No approved findings, so no notes were drafted.")}
    facts = json.dumps(findings, ensure_ascii=False)
    source_text = " ".join(f["statement"] for f in findings)
    summary_ids, notes = [], []
    # The English guardian note is always drafted: it is the one the teacher can certainly check.
    # A note in the family's home language is drafted as well, as a machine draft for a speaker
    # of that language to check before it is used.
    home = state["learner"].get("home_language") or "en"
    wanted = [("guardian", "en")] + ([("guardian", home)] if home != "en" else []) + [("teacher_handover", "en")]
    for audience, language in wanted:
        reader = "the learner's parent or guardian" if audience == "guardian" else "the learner's next teacher"
        messages = [SystemMessage(prompts.SUMMARY_SYSTEM),
                    HumanMessage(f"LANGUAGE: {language_name(language)}\nREADER: {reader}\nAPPROVED FINDINGS:\n{facts}")]
        text, problems = "", ["not written"]
        for _ in (1, 2):
            try:
                reply = await timed_invoke(llm, messages, usage, "draft_summaries")
            except Exception:  # noqa: BLE001
                break
            text = (reply.content or "").strip()
            problems = guard.check_statement(text) if text else ["empty"]
            if not problems and not looks_like(text, language):
                problems = [f"the note is not written in {language_name(language)}"]
            if not problems and _speaks_to_wrong_reader(text, audience):
                problems = ["the note speaks to a parent ('your child'); it must speak to the next teacher about the learner"]
            if not problems and (extra := _numbers_not_in(text, source_text)):
                problems = [f"the note contains numbers that are not in the approved findings: {', '.join(extra)}"]
            if not problems:
                break
            messages += [reply, HumanMessage("Rewrite it. Problems: " + "; ".join(problems))]
        if problems:
            if language != "en":
                notes.append(f"no usable {language_name(language)} note ({problems[0]}); the English note stands")
                continue
            text = source_text   # fall back to the teacher-approved statements, word for word
            notes.append(f"{audience}: the model's wording was not usable ({problems[0]}); "
                         "used the approved statements as written")
        try:
            result = await hub.call("draft_summary", learner_id=state["learner_id"], finding_ids=approved,
                                    audience=audience, language=language, text=text)
            summary_ids.append(result["summary_id"])
        except ToolError as exc:
            notes.append(f"{audience}: refused by the server ({str(exc)[:120]})")
    note = f"Drafted {len(summary_ids)} summary note(s) for teacher review." + (" " + "; ".join(notes) if notes else "")
    return {"summary_ids": summary_ids, **_step("draft_summaries", note)}


async def teacher_gate_summaries(state: RunState) -> dict:
    """GATE 2. Nothing is treated as ready for a guardian until a teacher approves the text."""
    hub, _, _ = _res(state)
    ids = state.get("summary_ids") or []
    while True:   # same loop as gate 1: an early resume pauses again
        statuses = await _summary_statuses(hub, state["learner_id"], ids)
        waiting = [i for i, s in statuses.items() if s == "draft"]
        if not waiting:
            break
        interrupt({"gate": "summaries", "waiting_for": waiting})
    approved = [i for i, s in statuses.items() if s == "approved"]
    return _step("teacher_gate_summaries", f"Teacher decided {len(ids)} summary note(s): {len(approved)} approved.")


# --------------------------------------------------------------------------- graph

def _after_propose(state: RunState) -> str:
    return "teacher_gate_findings" if state.get("finding_ids") else END


def _after_gate(state: RunState) -> str:
    return "draft_summaries" if state.get("approved_finding_ids") else END


def _after_summaries(state: RunState) -> str:
    return "teacher_gate_summaries" if state.get("summary_ids") else END


def build_graph() -> StateGraph:
    g = StateGraph(RunState)
    for node in (load_learner, read_document, extract_evidence, record_evidence, investigate,
                 compose_findings, propose_findings, teacher_gate_findings, draft_summaries, teacher_gate_summaries):
        g.add_node(node.__name__, node)
    g.add_edge(START, "load_learner")
    g.add_edge("load_learner", "read_document")
    g.add_edge("read_document", "extract_evidence")
    g.add_edge("extract_evidence", "record_evidence")
    g.add_edge("record_evidence", "investigate")
    g.add_edge("investigate", "compose_findings")
    g.add_edge("compose_findings", "propose_findings")
    g.add_conditional_edges("propose_findings", _after_propose, ["teacher_gate_findings", END])
    g.add_conditional_edges("teacher_gate_findings", _after_gate, ["draft_summaries", END])
    g.add_conditional_edges("draft_summaries", _after_summaries, ["teacher_gate_summaries", END])
    g.add_edge("teacher_gate_summaries", END)
    return g
