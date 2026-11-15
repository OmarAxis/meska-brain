# Build contract

Shared interfaces for everyone building Meska Brain. If you need to change something here, say so in
your final report instead of changing it silently. `schema.sql`, `db.py`, `config.py` and `audit.py`
are fixed; read them first.

## What the product is

A living, cited learning map for one learner across years. Three maps are laid over each other:

- **Curriculum map**: concepts and "needs this first" links, loaded from a pack. We graph the school's
  curriculum, we never change it.
- **Learner map**: every quiz item, assignment, project, observation and attendance record (`evidence`).
- **Teacher map**: what was taught, when, and with which approach (`teaching_units`).

The graph does the reasoning (deterministic, explainable). A small open-weights model only reads
documents and words text. The agent recommends, a named teacher decides.

Rules that code must enforce, not just document:

1. Every finding cites evidence rows that exist and belong to that learner. No evidence, no finding.
2. A finding describes a pattern, never a label on a child, and never compares a learner to classmates.
3. Nothing is approved by the agent. Approval functions live in `review.py` and are not MCP tools.
4. A summary can only be drafted from approved findings, and needs its own approval.
5. Every tool call is written to `audit_log` (use `@audited`), every decision to `approvals`.
6. No real learner data. Synthetic only. Learners have an alias, never a name.

## Time

`year` is a calendar year, `term` is 1..3. `period_ord = year*3 + (term-1)` (`db.period_ord`).
`db.period_label(ord)` gives `"2023-T2"`.

## Curriculum pack: `packs/<pack_id>/pack.yaml`

```yaml
id: generic-maths
name: School mathematics, grades 1 to 8
subject: maths
grades: [1, 8]
languages: [en]
strands:
  - {id: number, label: {en: Number}}
skills:            # cross-subject skills, in the spirit of "approaches to learning"
  - {id: spatial-reasoning, label: {en: Spatial reasoning}}
  - {id: persistence-on-hard-problems, label: {en: Persistence on hard problems}, kind: disposition}
approaches:        # teaching approaches a unit can use
  - {id: concrete_objects, label: {en: Hands-on objects}}
concepts:
  - id: division-basic
    label: {en: Division as sharing and grouping}
    strand: number
    grade: 3
    requires: [multiplication-basic]
    skills: []
```

`requires` must form a DAG. Labels are dicts keyed by language code; `en` is always present.
A skill's `kind` is `thinking` (default) or `disposition` (it describes character, such as persistence).
A disposition can show up as a strength but is never reported as a struggle: that would label a child.

## `curriculum.py`

```python
@dataclass(frozen=True)
class Concept: id: str; label: dict[str, str]; strand: str; grade: int; requires: tuple[str, ...]; skills: tuple[str, ...]

class Pack:
    id: str; name: str; subject: str; grades: tuple[int, int]
    strands: dict[str, dict[str, str]]      # id -> label dict
    skills: dict[str, dict[str, str]]
    approaches: dict[str, dict[str, str]]
    concepts: dict[str, Concept]
    graph: nx.DiGraph                        # edge prerequisite -> concept
    skill_kinds: dict[str, str]              # skill id -> "thinking" | "disposition"
    def label(self, any_id: str, lang: str = "en") -> str      # concept, strand, skill or approach; falls back to en, then the id
    def prerequisites(self, concept_id: str) -> list[str]      # direct
    def ancestors(self, concept_id: str) -> list[str]          # all, nearest first (BFS)
    def dependents(self, concept_id: str) -> list[str]         # direct

def load_pack(pack_id: str | None = None, packs_dir: Path | None = None) -> Pack   # cached; validates DAG and references
```

## `graph.py` (pure, deterministic, no model calls)

All take `db_path=None` as a keyword and return plain JSON-able dicts.

```python
concept_mastery(learner_id) -> {concept_id: [{"period_ord", "period", "mean", "n", "evidence_ids"}]}
find_patterns(learner_id, min_periods=3) -> {
  "learner_id", "patterns": [{"kind": "strength"|"struggle", "scope": "strand"|"skill"|"concept",
     "scope_id", "label", "periods": ["2022-T1", ...], "mean", "n_items", "evidence_ids", "confidence",
     "concept_ids": [concepts behind the pattern, most recent first]}],
  "data_gaps": [{"period", "reason"}]}
trace_root(learner_id, concept_id) -> {
  "target": {"concept_id", "label", "mean", "n"},
  "path": [concept ids from target back to root],
  "root": {"concept_id", "label", "grade", "mean", "n", "period", "taught_period", "evidence_ids"} | None,
  "root_is_target": bool,
  "root_is_certain": bool,                 # false when a prerequisite of the root is a hole in the record
  "context": [{"type": "absence", "period", "absent_days", "evidence_id"}],
  "unknowns": [every concept the walk visited that has no evidence],
  "unknowns_on_path": [unrecorded concepts strictly between target and root on `path`],
  "unrecorded_prerequisites_of_root": [direct prerequisites of the root with no evidence],
  "prerequisites_before_record": [those of grade below the learner's start_grade],
  "prerequisites_missing_in_record": [those of grade >= start_grade: holes in the record],
  "alternatives": [other candidate roots, same shape as root],
  "evidence_ids": [...], "confidence": float, "reason": str}
what_worked(learner_id) -> {
  "approaches": [{"approach_id", "label", "units", "improved", "not_improved", "mean_gain",
     "instances": [{"concept_id", "period", "before", "after", "unit_id", "baseline_periods", "evidence_ids"}]}],
  "note": "Describes teaching approaches for this learner. It does not rate teachers. Gains are measured
           against the learner's own recent average, so topic difficulty also plays a part."}
learner_graph(learner_id) -> {
  "learner": {...}, "periods": ["2021-T1", ...],
  "nodes": [{"id", "type": "concept"|"skill"|"strand", "label", "grade", "strand", "mastery", "n", "state": "strong"|"shaky"|"gap"|"unseen"}],
  "edges": [{"source", "target", "type": "requires"|"shows"}],
  "timeline": {"2021-T1": {concept_id: mastery_so_far}}}
```

Definitions: a scored item counts toward mastery when `status='active'` and `score` is not null.
Struggle = mean below 0.5, strength = mean above 0.8, held for `min_periods` periods that have data
(not necessarily consecutive calendar terms, but consecutive among periods with data for that scope).
For a strand or skill pattern, `concept_ids` lists the concepts inside it whose mean over the pattern's
periods is itself low (struggle) or strong (strength), ordered by latest period with evidence, then id;
for a concept pattern it is `[scope_id]`. The agent traces from these.

`trace_root` walks back from the target through prerequisites that are low or have no evidence, and
stops at prerequisites that are fine. Root candidates are low concepts on that walk none of whose direct
prerequisites is low; the root is the one with the lowest grade (then longest path, then lowest mean),
the rest are `alternatives`. Concepts with no evidence are reported, never guessed. If the root is the
target itself and all its direct prerequisites are recorded and fine, it is returned with
`root_is_target: true` (the difficulty starts there).

An unrecorded direct prerequisite of the root is either *before the record* (its grade is below the
learner's `start_grade`: listed, and the reason says records begin in grade N; no cap) or a *hole in the
record* (grade >= `start_grade`: the learner was enrolled and nothing was recorded). With a hole, the
candidate root is still returned so the teacher can see it, but `root_is_certain` is false, confidence
is capped at 0.35, and `reason` ends with the caveat that the difficulty may begin earlier. If the root
would be the target itself and it has a hole below it, `root` is `None` and confidence 0.0: where it
began cannot be told from the records.

`taught_period` is when the root was taught to the learner's year group according to `teaching_units`
(a unit is for this group when `grade - year == start_grade - start_year`), else null. Absences in that
period (falling back to the root's first scored period) are returned in `context`.
Confidence = n/(n+4) × 0.8^len(unknowns_on_path), rounded to 2 dp, where n is the root's own scored
items plus the target's (counted once when the root is the target), then capped at 0.35 when
`root_is_certain` is false.

`find_patterns` never reports a struggle on a skill of kind `disposition`.

`what_worked`: for each teaching unit linked to the learner's evidence, `after` = mean of the learner's
scored items tagged with that unit; `before` = mean of all the learner's scored items (any concept) in
the two most recent earlier periods with data (`baseline_periods`). A unit is skipped with no earlier
period or fewer than 4 baseline items. A gain of at least 0.15 counts as `improved`.

## `guard.py`

```python
check_statement(text: str) -> list[str]   # problems found; empty list means acceptable
```

Rejects labels on a child ("lazy", "slow learner", "weak student", "gifted", "not a maths person",
"has a talent for", "high potential" and similar), comparisons or ranks against classmates ("top of the
class", "below peers", "below the class average", "bottom group", "ranked"), and prescriptive track
assignment ("should become", "must take", "is not suited to", "vocational stream", "lower-tier").

It is a word-and-pattern list, not a classifier: strongest in English, partial in Swahili, French and
Arabic, absent for other languages. It is a second line behind the teacher, who approves everything.
`PROBES` (a list of `Probe(text, should_block, language, held_out)`, 63 entries, 10 held out that the
patterns were not tuned on) and `evaluate()` (block rate and false-positive rate, overall, tuned and
held out, plus the probes it gets wrong) make it measurable.

## `tools.py` (the service layer; these are the MCP tools)

Each is decorated with `@audited("<name>")` and returns a dict. Errors raise `ValueError` with a
message a caller can act on. All arguments are keyword-only (the audit log records kwargs). Each also
accepts `db_path=None`, which `@audited` uses for the audit row too, and the reserved `_actor` /
`_run_id`, which `@audited` sets on `audit.current_actor` / `audit.current_run_id` for the duration of
the call (so `proposed_by` / `created_by` see them).

```python
list_learners() -> {"learners": [{"learner_id", "alias", "grade_now", "home_language", "evidence_count"}]}
get_learner_timeline(learner_id, since_year=None, concept_id=None, limit=200) -> {"learner", "periods": [{"period", "items": [...]}], "counts"}
record_evidence(learner_id, kind, year, term, grade, source_ref, concept_id=None, skill_id=None, score=None,
                absent_days=None, raw_text=None, language="en", teacher_id=None, unit_id=None, logged_late=False)
    -> {"evidence_id", "status": "active"|"needs_review", "warnings": [...]}
find_patterns(learner_id, min_periods=3)
trace_root(learner_id, concept_id)
what_worked(learner_id)
propose_finding(learner_id, kind, statement, evidence_ids, concept_ids=None, path=None, confidence=0.5)
    -> {"finding_id", "status": "proposed"}
draft_summary(learner_id, finding_ids, audience, language, text) -> {"summary_id", "status": "draft"}
get_findings(learner_id, finding_ids=None, status=None) -> {"findings": [{"finding_id", "kind", "statement",
    "concept_ids", "evidence_ids", "confidence", "status", "proposed_by", "proposed_at", "decided_by_name",
    "decided_at", "teacher_note"}]}
get_summaries(learner_id, summary_ids=None, status=None) -> {"summaries": [{"summary_id", "audience",
    "language", "text", "finding_ids", "status", "created_at", "decided_by_name", "decided_at"}]}
```

- `find_patterns`: `min_periods` below 3 raises ("A pattern needs at least 3 terms of data."), so no
  caller can lower the evidence bar.
- `get_findings` / `get_summaries` are read-only and audited, so callers never need SQL to see what a
  teacher decided. An unknown status raises.

- `record_evidence`: unknown learner raises. Unknown concept or skill id stores the row with
  `status='needs_review'` and a warning. Score outside 0..1 raises. A duplicate (`learner_id`,
  `source_ref`) returns the existing id with a warning instead of inserting.
- `propose_finding`: raises if `evidence_ids` is empty, if any id does not exist or belongs to another
  learner, if kind is root_cause/strength/struggle with fewer than 2 evidence rows, or if
  `guard.check_statement` reports problems.
- `draft_summary`: raises unless every finding is `approved` or `edited` and belongs to the learner,
  and unless the text passes `guard.check_statement`.

## `review.py` (teacher only, never exposed over MCP)

```python
pending(db_path=None) -> {"findings": [...], "summaries": [...]}     # with evidence rows expanded
decide_finding(finding_id, decision, teacher_id, note=None, edited_statement=None) -> dict
decide_summary(summary_id, decision, teacher_id, note=None) -> dict
```

Decisions are `approved`, `edited` (findings only, needs `edited_statement`) or `rejected`. Each writes
`approvals` (with the teacher's name) and an `audit_log` row with actor `teacher:<id>`, in the same
transaction as the decision itself: all three are written or none. Unknown teacher raises. Deciding
twice raises.

## `db.py` and `audit.py`

`db.connect(db_path=None)` is a context manager: `with db.connect() as conn:` commits on success, rolls
back on error and always closes the connection. `audit.write_row(conn, ...)` inserts an audit row on an
open connection (used by `review.py` to share the decision's transaction); `audit.log_call(...)` writes
one in its own transaction.

## `server.py`

`FastMCP("meska-brain")` from `mcp.server.fastmcp`, registering the twelve functions in `tools.py` with
clear descriptions and `ToolAnnotations` (read-only for the read tools). `main()` runs stdio by
default; `--http` runs streamable HTTP on `Settings.mcp_port`. Installed mcp version is 1.30.

## `synth.py`

```python
generate(db_path=None, seed=7, n_learners=12, years=4, pack_id=None, out_dir=None) -> dict
```

Fills learners, teachers, teaching_units and evidence, and writes `data/ground_truth.json` (the planted
patterns per learner, used by evals) and a few raw files in `data/inbox/` for the agent to ingest.

## Agent runner (built separately): `meska_brain.agent.runner`

```python
start(task: dict) -> dict      # {"run_id", "status"}; task = {"learner_id", "inbox_file"?: str, "goal"?: str}
status(run_id: str) -> dict    # {"run_id", "status": "running"|"waiting_for_teacher"|"done"|"failed", "steps": [...], "pending": {...}}
resume(run_id: str) -> dict    # call after the teacher has decided; continues the run
```

The web app must import this lazily and still work when it is missing.
