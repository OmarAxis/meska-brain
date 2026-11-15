# Meska Brain: notes for Claude Code

Read this first, then `HANDOVER.md` (what the person in front of you has been asked to do),
then `README.md`, `ARCHITECTURE.md` and `EVALS.md`.

## What this is

An entry for the Education track ("The Long View") of the African Agentic AI Design Challenge.
Meska Brain follows one learner across years and builds a cited profile for a teacher.

Three maps laid over each other:

- **Curriculum map**: concepts and their prerequisites, loaded from a pack (`packs/generic-maths/pack.yaml`).
  We graph the school's curriculum. We never change it.
- **Learner map**: evidence rows (quiz items, observations, attendance) attached to concepts over time.
- **Teacher map**: what was taught, when, and with which approach.

Who does what:

- The **graph engine** (`graph.py`) reaches the conclusions, in plain code: patterns held over terms,
  tracing a struggle back to where it began, which approaches were followed by improvement.
- The **model** only reads documents, chooses which analyses to run, and words text.
- A **named teacher** approves every finding and every note. Approving is not an MCP tool, so the
  agent cannot approve anything.

## Layout

| Path | What |
|---|---|
| `src/meska_brain/server.py`, `tools.py` | Our MCP server: 10 tools, 3 that write |
| `src/meska_brain/graph.py` | The deterministic graph engine |
| `src/meska_brain/guard.py` | Refuses statements that label, rank or track a child |
| `src/meska_brain/review.py` | Teacher decisions (not reachable by the agent) |
| `src/meska_brain/audit.py` | Every tool call is logged |
| `src/meska_brain/agent/workflow.py` | The LangGraph agent, with two teacher gates |
| `src/meska_brain/agent/runner.py` | Starts, pauses and resumes runs |
| `src/meska_brain/agent/llm.py` | Model access (any OpenAI-compatible endpoint) |
| `src/meska_brain/web/` | Teacher web app (FastAPI and one HTML file) |
| `src/meska_brain/synth.py` | Synthetic cohort and sample documents |
| `src/meska_brain/evals.py` | The evaluation set that writes `EVALS.md` |
| `tests/` | 145 tests, no model needed |

## Commands

```
uv sync --extra dev          # install
uv run meska demo            # seed if needed, open the teacher app at http://127.0.0.1:8765
uv run pytest -q             # tests (no model needed)
uv run ruff check src tests  # lint
uv run meska seed --pack generic-school   # all four subjects (default seed is maths only)
uv run meska story           # a ready state for presenting, no model used
uv run meska learners        # list learners
uv run meska run A-17 --file data/inbox/quiz_sheet_A17_2025-T1.md
uv run meska pending         # what is waiting for a teacher
uv run meska eval --skip-model   # engine tasks only
uv run meska eval --repeats 1    # full evaluation, needs a model
```

## Using an API instead of a local model

The model is any OpenAI-compatible endpoint. Settings are read from the process environment.
The project does not load a `.env` file, so set them in the shell that runs the command:

```
MESKA_LLM_BASE_URL   the provider's OpenAI-compatible base URL (ends in /v1)
MESKA_LLM_API_KEY    the key
MESKA_LLM_MODEL      the model id as the provider names it
MESKA_LLM_REASONING  set to "default" for hosted APIs
```

`MESKA_LLM_REASONING=default` matters: by default the code sends `reasoning_effort: "none"`, which
LM Studio accepts and some hosted APIs reject.

Prefer an open-weights model (Qwen, Llama, Gemma, Mistral) from a host such as OpenRouter, Groq or
Together. The challenge requires a full task on open weights, so numbers that go into `EVALS.md`
must come from an open-weights model. A closed model is fine for exploring, but say which model
produced any result you report.

## Rules that must not be broken

These come from the challenge. Breaking one disqualifies the entry.

1. **Never commit a key.** No `.env` file, no key in code, docs, tests or commit messages. The repo is public.
2. **Synthetic data only.** No real learner data, ever. Learners are known by alias (A-17).
3. **The agent never labels a child or assigns a track.** Do not weaken `guard.py` or the two teacher gates.
4. **No unsourced claim.** Every finding cites evidence ids, and those ids come from the tools, never from the model.
5. **Every tool call is logged.** New tools must use `@audited`.
6. **Report results as they are.** Do not edit the generated table in `EVALS.md` by hand. If something fails, write it down.
7. **Keep the one-command run working.** `uv run meska demo` must work on a fresh clone.

## Working here

- Work on a branch and open a pull request. Do not push to `main`.
- Before every commit: `uv run pytest -q` and `uv run ruff check src tests` must both pass.
- Add a test with every fix.
- Docs are written in plain English with no em dashes or en dashes.
- Known weak spots are listed at the end of `EVALS.md`. Start there.
