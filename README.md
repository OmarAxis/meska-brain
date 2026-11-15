# Meska Brain

Meska Brain follows one learner across years and shows a teacher where that learner is strong, where they struggle, and where a struggle may have started. It lays three maps over each other: the curriculum map (concepts and "needs this first" links), the learner map (every quiz item, note and attendance record), and the teacher map (what was taught, when, and with which approach). A graph does the reasoning, a small open-weights model only reads documents and words text, and a named teacher approves everything before it can be shared.

Entry for the African Agentic AI Design Challenge, Education track "The Long View", sub-theme "Longitudinal strength tracking". Status: a working prototype on synthetic data. It has not been tried with a real teacher. See [What is not finished](#what-is-not-finished).

## Run it

```
uv run meska demo
```

That is the whole setup. The first run creates a synthetic cohort (12 made-up learners, 4 years) and starts the teacher app at http://127.0.0.1:8765 (open that address in a browser; the command prints it but does not open the browser for you). Stop it with Ctrl+C.

- Only [`uv`](https://docs.astral.sh/uv/) is required. It installs Python 3.12 or 3.13 and every dependency.
- The map, the patterns, the review queue and the audit log work with no model at all.
- Agent runs (reading a document, investigating, proposing findings, drafting summaries) need an OpenAI-compatible endpoint. The default is LM Studio at `http://localhost:1234/v1` serving `qwen3.5-9b`. Start LM Studio's local server with that model loaded, then run the demo.
- The first agent run that reads a file starts Microsoft's `markitdown-mcp` through `uvx`, which downloads it from PyPI once. After that it is cached. If it cannot start, the agent falls back to reading `.txt`, `.md` and `.csv` files directly and says so in the run log.

Change the model with environment variables (all of them are listed in [Configuration](#configuration) and in `.env.example`). The code reads real environment variables and does not load a `.env` file.

```
# Ollama (only LM Studio with qwen3.5-9b has been run by us; this is the expected setup, not a tested one)
export MESKA_LLM_BASE_URL=http://localhost:11434/v1
export MESKA_LLM_MODEL=qwen3:8b
export MESKA_LLM_API_KEY=ollama
uv run meska demo
```

PowerShell: `$env:MESKA_LLM_BASE_URL = "http://localhost:11434/v1"`, and so on. vLLM or any other OpenAI-compatible server works the same way.

## The example this is built around

Learner A-17 (synthetic) is failing ratios in grades 6 and 7. The map walks back along the curriculum links: ratios, equivalent fractions, fractions, division. Division was taught in grade 3, in a term with 17 days of absence recorded. The same learner map shows geometry has been strong every year. The teacher sees both facts, each with the records behind it, and decides what to do with them. Nothing in the system tells anyone what the learner "is".

It is general for school grades. The demo pack is school mathematics, grades 1 to 8, and is not tied to one country's syllabus. Another subject or country is a new pack file (see `packs/generic-maths/pack.yaml` for the format), not new code. We graph a school's curriculum; we do not change it.

## Walkthrough (the teacher app)

1. Run `uv run meska demo` and open http://127.0.0.1:8765. It opens on the **Class overview**: headline numbers, what is waiting for a teacher, records term by term, a curriculum picture by strand and grade, and the learners in alphabetical order. The overview describes topics and records; it never shows a score or a rank for a learner. In "Signed in as" at the bottom left, choose a teacher name. There is no password; the choice only records who decides. Click **Learner A-17**. The **Profile** shows results by strand term by term, patterns that held, teaching approaches and what followed, and a year by year timeline. Then open **Learning map**: the curriculum graph coloured by what this learner's records say (strong, shaky, gap, unseen).
2. Press play on the **Term** slider (or drag it). The colours replay term by term, so you can watch where the low areas appear and that geometry stays strong.
3. Click a low (red) topic, for example ratios, and press **Trace back**. The path is drawn back through its prerequisites to the deepest low topic, with the confidence, the absence context, any topic with no records (named, not guessed), and the records behind it.
4. Open the **Agent** tab. Choose Learner A-17 and the file `quiz_sheet_A17_2025-T1.md`, then **Start a run**. The log shows each step, including checks and fallbacks, and lists any "questions the agent left open instead of guessing". The run stops at the first teacher gate.
5. Open the **Review queue**. Each proposed finding shows its statement, confidence and the records it cites. Approve, edit or reject as your chosen teacher. The run resumes by itself and drafts notes. For a learner whose home language is not English (A-17's is Swahili) there are three: an English note for the guardian, a note for the guardian in the home language, and an English handover note for the next teacher. For an English-speaking family there are two. The run stops at the second gate. Approve or reject each note in the same queue. The home-language note is a machine draft that nobody who speaks the language has checked, so approve it only if a speaker has read it. Then open the **Audit log** tab to see every tool call and every decision with the teacher's name.

Approved findings and notes for a learner are listed under **Approved**, with who approved each one.

For a presentation, `uv run meska story` builds a ready state on a freshly seeded database: the engine's findings for three learners, some approved and some waiting. No model is used, the wording comes from fixed templates, and every step is logged with the actor `demo-setup` so it cannot be mistaken for the agent's work or a real teacher's decision. `uv run meska seed` wipes it.

## The same flow from the command line

```
uv run meska learners
uv run meska teachers
uv run meska run A-17 --file data/inbox/quiz_sheet_A17_2025-T1.md
uv run meska pending
uv run meska decide fnd_XXXXXXXXXX approved --teacher tch_XXXXXXXXXX --note "Checked with last year's teacher"
uv run meska resume run_XXXXXXXXXX
uv run meska pending
uv run meska decide sum_XXXXXXXXXX approved --teacher tch_XXXXXXXXXX
uv run meska audit
```

- `meska run` accepts an alias such as `A-17` or an id. `--frontier` and `--model` are optional.
- `meska run` stops at gate 1 and prints the run id. A learner can have only one open run at a time; start another only after the first has finished or been decided. `meska pending` lists findings with their evidence. `meska decide` takes a `fnd_` or `sum_` id; use `--edited "new wording"` with `edited` for findings.
- `uv run meska teachers` lists the teacher ids that `meska decide` needs.
- `meska resume` continues the run from its SQLite checkpoint, even in a new process or hours later. It drafts the summaries and stops at gate 2. Decide the summaries, then `meska resume` once more to close the run.
- If you decide in the web app instead, the app resumes the waiting run for you.
- `meska seed` regenerates the synthetic cohort and wipes existing data, including findings, approvals and the audit log.

## Use the MCP server from any MCP host

Meska Brain's own MCP server exposes ten tools (table below). None of them can approve anything.

stdio (the default), as a config snippet for a generic MCP host:

```json
{
  "mcpServers": {
    "meska-brain": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/meska-brain", "meska", "mcp"]
    }
  }
}
```

If the database is empty, `meska mcp` seeds it first and prints its message to standard error, so a stdio host is not disturbed.

Streamable HTTP, bound to 127.0.0.1 only, on port 8766 (`MESKA_MCP_PORT`):

```
uv run meska mcp --http
```

The endpoint is `http://127.0.0.1:8766/mcp`. There is no authentication on it, which is why it does not bind to other interfaces. Calls from a host you run yourself are logged with actor `mcp-client` (override with `MESKA_ACTOR`).

| Tool | Reads or writes | What it does |
|---|---|---|
| `list_learners` | read | Learners with alias, current grade, home language, evidence count. |
| `get_learner_timeline` | read | A learner's evidence grouped by term, filterable by year or concept. |
| `find_patterns` | read | Strengths (mean above 0.8) and struggles (below 0.5) held for 3 or more terms with data, by strand, skill and concept. Also reports data gaps. The server refuses `min_periods` below 3. A low run on a disposition skill (persistence) is never reported as a struggle. |
| `trace_root` | read | Walks prerequisites back from a struggling concept to the deepest low one. Returns the path, absences in the term the root was taught, unrecorded concepts, alternatives, confidence and a reason. If a prerequisite right under the root has no records although the learner was enrolled in that grade, the root is marked `root_is_certain: false` and confidence is capped at 0.35. Prerequisites from before the learner's first recorded grade are listed as "before the record" and do not cap it. |
| `what_worked` | read | Teaching approaches followed by a clear gain for this learner, measured against the learner's own recent average. Describes approaches, never rates teachers. |
| `get_findings` | read | A learner's findings and what a teacher decided about each (status, deciding teacher's name). The agent uses it for its gate checks, so they are in the audit log. |
| `get_summaries` | read | The same for summary drafts. |
| `record_evidence` | write | Stores one evidence row with its source. Unknown concept ids are kept as `needs_review`; a repeated source returns the existing row. |
| `propose_finding` | write | Stores a finding as `proposed`. Needs real evidence ids that belong to the learner (2 or more for root cause, strength, struggle) and a statement that passes the guard. |
| `draft_summary` | write | Stores a summary draft. Refused unless every cited finding is approved or edited by a teacher and the text passes the guard. |

## What the challenge asked for, and where it is

| Requirement | Where |
|---|---|
| Own MCP server with 3 or more tools, at least one that writes | `src/meska_brain/server.py`, `src/meska_brain/tools.py`: 10 tools (7 read, 3 write: `record_evidence`, `propose_finding`, `draft_summary`). The agent does all its learner-data work through them over stdio, including reading finding and summary status at the gates, so those reads are logged too. |
| An MCP server we did not write | Microsoft's [`markitdown-mcp`](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp), started over stdio in `src/meska_brain/agent/mcp_io.py`. It beats writing it ourselves because converting PDFs, Office files, images and HTML to text is a large, well-maintained problem that is not our contribution. |
| Open-source orchestration | LangGraph, in `src/meska_brain/agent/workflow.py`. Checkpointed to SQLite (`data/checkpoints.db`) in `src/meska_brain/agent/runner.py`, so a run pauses at a teacher gate and resumes later. MCP sessions use the official `mcp` SDK client directly (`agent/mcp_io.py`). |
| One full task on an open-weights model | The whole agent task runs on `qwen3.5-9b` served locally by LM Studio (`src/meska_brain/agent/llm.py`). Any OpenAI-compatible endpoint works. A frontier model is optional via `MESKA_FRONTIER_*`. |
| A logged call for every action | `@audited` in `src/meska_brain/audit.py` writes every tool call (input, output, success, time, actor, run) to `audit_log`. Teacher decisions are logged too: `review.py` writes the decision, the `approvals` row and the audit row in one transaction. |
| A gate on every irreversible action | Two gates in `workflow.py`: findings, then summaries. The `approvals` table (`schema.sql`, written by `review.py`) records the named teacher. The agent has no tool that can approve: `review.py` is not exposed over MCP. |
| New work, OSI licence, runs in one command | Apache License 2.0 in `LICENSE`. `uv run meska demo`. |

## Rules the code enforces

These are the things that disqualify an entry, and what stops each one in this repository.

- **Not a chatbot wrapper.** There is no chat box and no free-form question answering. The agent is a fixed LangGraph pipeline (`workflow.py`). The model has three narrow jobs: read a document into rows, choose which analysis tools to call, and word a sentence. All reasoning over the curriculum and the records is deterministic code in `graph.py`. The model chooses which analysis to run, not the learner or the evidence bar: the agent forces `learner_id` on every model-chosen call and strips `min_periods`, and the server itself refuses `min_periods` below 3.
- **Not an MCP server that proxies one endpoint.** `server.py` exposes ten tools over a local graph and database (`tools.py`, `graph.py`). It makes no outbound calls.
- **No label or track for a learner, and nothing shared, without the teacher.** `guard.py` rejects labels on a child, comparisons with classmates and track assignments. It runs in `propose_finding`, in `draft_summary` and on a teacher's edit (`tools.py`, `review.py`), and the agent checks its own wording first (`workflow.py`). A finding is `proposed` until a named teacher decides (`review.py`). A summary can only be drafted from approved findings (`tools.draft_summary`) and needs its own approval. Each note is also checked for language (`agent/language.py`) and for numbers: a note may not contain a number that is not in the approved findings. Nothing in the system sends anything anywhere; there is no share or send function. Dispositional skills in a pack (marked `kind: disposition`, such as persistence) can be reported as a strength but never as a struggle.
- **No claim without a source.** `tools._check_evidence` refuses a finding with no evidence ids, with an id that does not exist, or with an id that belongs to another learner. Evidence ids are copied from tool results in `workflow.py`; the model never writes one. When the records cannot tell where a difficulty began (a hole in the record right under the root), `trace_root` says so, and the agent turns it into an open question for the teacher, not a finding. Rows the model reads from a document are dropped if their quote is not in the document. The review screen shows the records behind each finding.
- **No real learner data.** Learners have an alias, never a name (`schema.sql`). All data is generated by `synth.py` from a seed; the inbox files are synthetic (`data/inbox/README.md`). This is a convention plus a design, not a technical check: nothing stops someone typing a real name into a note.
- **A repo that runs.** One command, `uv run meska demo`; the test suite is `uv run pytest`. There is no continuous integration configured yet.
- **No results presented as runs that never happened.** `EVALS.md` is generated by `uv run meska eval` from the run records in `evals/results/`, with a timestamp, and says not to edit it by hand. Model-dependent tasks are repeated and the number of passes is reported, including failures. The planted patterns are synthetic and the evaluation says so.

Where the agent touches the database directly: nowhere inside the agent graph. `agent/workflow.py` makes no database reads; learner data, finding status and summary status all go through MCP tools and are in the audit log. Two things outside the graph read the database: `agent/runner.py` checks whether a gate still has undecided items (`_still_undecided`; this is run scheduling, not an agent action, and open runs are found from the run record files), and the teacher app's page views read the database directly. Page views are not in the audit log; teacher decisions are.

Runs are guarded too. A learner can have only one open run. Resuming is claimed under a lock, so two decisions arriving together cannot resume a run twice. After a gate the runner re-checks, so a decision that lands at the wrong moment cannot leave a run stuck. A run left "running" for 15 minutes by a process that died is marked failed.

## Tests and evals

```
uv run pytest          # unit and integration tests, no model needed
uv run meska eval      # engine and server tasks (no model) plus agent tasks on the local model
uv run meska eval --skip-model   # only the deterministic tasks
```

`meska eval` runs every task on a fresh copy of the seeded database, so tasks cannot help each other. There are 15 engine tasks and 11 agent tasks. Engine tasks check the planted cases in `data/ground_truth.json` (the root cause for A-17, the strength held across years, what worked for B-04, a root that must be reported as unknown for D-09, too little data for E-22, no pattern for F-12), the server's refusals, that no confident root is claimed over a hole in the record, that no claim is made twice, and how often the guard blocks a probe set of harmful and neutral sentences. Agent tasks run the full agent on documents, including a document that names a different learner, a register that lists several learners, a document that contains instructions to the model, a Swahili and an Arabic note, an audit-completeness check on a full run, and an HTML page that only the borrowed markitdown server can read.

Results, with pass counts per task, tokens and seconds, are in [EVALS.md](EVALS.md), and the table shows a failing run when there is one. The guard task reports block and false-positive rates there, including a held-out set the patterns were not tuned on, where the guard does clearly worse. Agent tasks use a 9B model, so repeat runs can differ; the table shows how often each task passed.

The evaluation has not been independently reviewed.

## Configuration

All settings are environment variables. See `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `MESKA_DB` | `data/meska.db` | SQLite database. Run records and checkpoints are written next to it. |
| `MESKA_PACKS` | `packs` | Folder of curriculum packs. |
| `MESKA_PACK` | `generic-maths` | Default pack. |
| `MESKA_LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible endpoint for the local model. |
| `MESKA_LLM_MODEL` | `qwen3.5-9b` | Model id. |
| `MESKA_LLM_API_KEY` | `lm-studio` | Key sent to the endpoint. LM Studio ignores it. |
| `MESKA_LLM_REASONING` | `none` | Reasoning effort sent to the model. `none` turns thinking off. `default` sends no setting. |
| `MESKA_FRONTIER_BASE_URL`, `MESKA_FRONTIER_MODEL`, `MESKA_FRONTIER_API_KEY` | unset | Optional second model, used only with `meska run --frontier`. |
| `MESKA_WEB_HOST`, `MESKA_WEB_PORT` | `127.0.0.1`, `8765` | Teacher app address. |
| `MESKA_MCP_PORT` | `8766` | Port for `meska mcp --http` (always bound to 127.0.0.1). |
| `MESKA_MARKITDOWN_CMD`, `MESKA_MARKITDOWN_ARGS` | `uvx`, `markitdown-mcp` | How the borrowed MCP server is started. |
| `MESKA_ACTOR`, `MESKA_RUN_ID` | `mcp-client`, empty | Who the audit log names for calls made over MCP. The agent sets these itself. |

## Project layout

```
src/meska_brain/
  server.py        our MCP server (10 tools, stdio or HTTP)
  tools.py         the service layer behind those tools (audited)
  graph.py         deterministic reasoning: patterns, trace back, what worked, learner graph
  curriculum.py    loads and validates a curriculum pack (a DAG of concepts)
  guard.py         word-and-pattern list: labels, class comparisons, track assignments
  review.py        teacher decisions (not exposed over MCP)
  audit.py         @audited, writes audit_log
  db.py, schema.sql, config.py
  synth.py         synthetic cohort and planted test cases
  evals.py         the evaluation set
  cli.py           the `meska` command
  agent/
    workflow.py    the LangGraph pipeline and its two teacher gates
    runner.py      start, pause and resume runs (SQLite checkpoints)
    mcp_io.py      MCP clients: our server and markitdown-mcp
    language.py    checks that a note is in the language asked for
    llm.py         model access (any OpenAI-compatible endpoint)
    prompts.py     every prompt, in one file
  web/             the teacher app (FastAPI plus one static page)
packs/             curriculum packs and note phrase templates
data/              synthetic inbox files and ground truth (the database is generated)
tests/, evals/results/, docs/
```

Other files: [ARCHITECTURE.md](ARCHITECTURE.md), [DESCRIPTION.md](DESCRIPTION.md), [EVALS.md](EVALS.md), [docs/CONTRACT.md](docs/CONTRACT.md) (the interfaces the parts were built against), [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md), [docs/CLOUD_TASKS.md](docs/CLOUD_TASKS.md).

## What is not finished

- **Not tried with a real teacher.** There is no classroom validation. The synthetic cohort is our only data, and the planted patterns are ones we wrote, so passing our own tests shows the engine finds what we planted, not that it helps a real class. The intended user is an upper-primary class teacher at handover time and before a parent meeting. That is a design target, not a validated workflow.
- **One curriculum pack.** Only school mathematics, grades 1 to 8 (77 concepts, English labels). The pack format supports other subjects and countries; none exist yet. The pack is generic and has not been compared with any national syllabus.
- **No authentication.** Teacher sign-in is a dropdown. Anyone who can reach the app or the CLI can decide as any teacher. The apps bind to 127.0.0.1 for that reason. The MCP HTTP endpoint has no authentication either.
- **Non-English text is unreviewed.** The note phrases in `packs/phrases/observations.yaml` (Swahili, Arabic, Amharic, Hausa, French) were machine-written. Home-language guardian notes are machine drafts that no speaker of the language has checked. The English guardian note is always drafted next to it so a teacher can check it. The language check (`agent/language.py`) compares common words, or the script for Arabic and Amharic; it is a sanity check, not language identification, and it exists because we saw isiXhosa come back when Swahili was asked for. If the home-language note fails after one retry it is not drafted and the English note stands.
- **The guard is a word-and-pattern list.** `guard.py` is strongest in English, partial in French, Swahili and Arabic (the Swahili and Arabic lists have no track-assignment patterns), and absent for every other language. It is a second line behind the teacher, who reads every finding and summary. Its measured block rate on our probe set is reported in EVALS.md; on a held-out set the patterns were not tuned on, it does clearly worse. It will miss wording it does not list.
- **Summary wording is checked, not proven.** A note is checked by the guard, by the language check, and by a rule that it may not contain a number that is not in the approved findings. Nothing checks that its sentences say what the findings say.
- **`what_worked` is confounded.** It compares a learner's scores after a unit with the learner's own average from the two earlier terms with data. Topic difficulty and term timing are mixed into the gain. The output says so, and the finding is worded as "may", but the number is not a causal estimate.
- **A struggle pattern needs 3 terms of data.** A learner with less is reported as having too little data, not as fine. The thresholds (below 0.5 struggle, above 0.8 strength, a gain of 0.15, the 0.35 confidence cap) and the confidence formula are our choices and have not been tuned or calibrated against outcomes.
- **Synthetic data is limited.** The "no pattern" control learner is generated with less noise than the other learners, and unplanted patterns do appear for some ordinary learners, so the false-positive rate on realistic data is not measured. All engine evals use one seed. Each concept is taught in a single term in the synthetic data, so "recovered later" cases are not exercised.
- **Scanned or handwritten sheets are untested.** Reading photos and scans depends on markitdown's conversion. We have only run it on text, markdown and an HTML page, and have not tested real photos.
- **No way to enter a real school's data.** There is no tool or screen to create learners, teachers or teaching units. Evidence can be added through `record_evidence` and the agent, but a real school's learners and units would need an import step we have not written. The only data source today is `synth.py`.
- **Re-runs skip claims already seen.** A candidate finding whose evidence mostly overlaps an earlier finding of the same kind for that learner, including one a teacher rejected, is not proposed again. If nothing new is proposed, the run ends without a teacher gate.
- **Small models are inconsistent.** A 9B model sometimes misses a table row, picks a weak plan, or words a sentence badly. The code retries, checks and falls back (see ARCHITECTURE.md), and the run log says when it did. Some runs still fail the evaluation tasks.
- **Documents are truncated.** The model reads the first 8000 characters of a document.
- **Page views are not in the audit log.** The teacher app reads the database directly to draw its pages. Tool calls and teacher decisions are logged; looking at a page is not.
- **No "discussed with guardian" step.** Approving a summary is the last gate. Nothing records that a conversation with a family took place or what was said.
- **No deployment.** It runs on one machine. There is no hosted version, no backup, no multi-school setup and no continuous integration. Developed and run on Windows 11 only; other systems have not been tried.
- **The web page is minimal.** It lists no approved summaries after approval (they are in the database and `GET /api/summaries`), does not mark the home-language note as a machine draft on the review card, and is a single static page.

## Licence

Apache License 2.0. See [LICENSE](LICENSE). Copyright 2026 Meska AI.
