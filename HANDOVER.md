# Handover

You are picking this up for a day. This page is everything you need to start.

## Start in five minutes

1. Install [uv](https://docs.astral.sh/uv/) and Git.
2. Clone and install:

   ```
   git clone https://github.com/OmarAxis/meska-brain.git
   cd meska-brain
   uv sync --extra dev
   ```

3. Open the folder in Claude Code. It reads `CLAUDE.md` by itself. For a full guided walkthrough
   (the idea, the features, the code, exercises), paste the prompt in `docs/ONBOARDING_PROMPT.md`
   as your first message. For a quick start instead:

   > Read CLAUDE.md, HANDOVER.md, README.md, ARCHITECTURE.md and EVALS.md, then explain this
   > project to me and run the tests.

4. See the product: `uv run meska demo`, then open http://127.0.0.1:8765. The map, the review queue
   and the audit log work with no model at all.

## Give it a model (an API is fine)

The agent needs a model. You do not need LM Studio. Any OpenAI-compatible API works. Set four
variables in the same terminal you run commands from. The project does not read a `.env` file.

PowerShell:

```
$env:MESKA_LLM_BASE_URL = "<provider base URL ending in /v1>"
$env:MESKA_LLM_API_KEY = "<your key>"
$env:MESKA_LLM_MODEL = "<model id>"
$env:MESKA_LLM_REASONING = "default"
```

macOS or Linux:

```
export MESKA_LLM_BASE_URL="<provider base URL ending in /v1>"
export MESKA_LLM_API_KEY="<your key>"
export MESKA_LLM_MODEL="<model id>"
export MESKA_LLM_REASONING="default"
```

Pick an open-weights model (Qwen, Llama, Gemma, Mistral) from a host such as OpenRouter, Groq or
Together. The challenge requires open weights, so only those results can go in `EVALS.md`.

Use your own key. Never put it in a file in this folder.

Then run the agent once:

```
uv run meska run A-17 --file data/inbox/quiz_sheet_A17_2025-T1.md
uv run meska pending
```

## What to test

In rough order of value:

1. **Run the full evaluation on your model**: `uv run meska eval --repeats 1`. It has only ever been
   run on one model (`qwen3.5-9b`). Note which tasks fail on yours. Do not commit the regenerated
   `EVALS.md` unless the model is open weights.
2. **Feed it your own documents.** Write made-up quiz sheets, teacher notes and registers (any
   language) and run them with `--file`. Look for: rows dropped, scores wrong, quotes that are not
   in the document, evidence recorded on the wrong learner. Made-up data only, never real pupils.
3. **Try to make it label a child.** The guard blocks only 2 of 6 phrasings it was not written for
   (see "A failure we did not fix" in `EVALS.md`). Find more that get through.
4. **Read the non-English notes.** If you speak Arabic, French, Swahili, Amharic or Hausa, read the
   guardian notes the agent drafts. Nobody has checked them.
5. **Use the web app as a teacher would.** Approve, edit and reject findings. Note anything confusing.

## What is still open

- Nobody who teaches has used it. Twenty points of the judging depend on fit to a real classroom.
- No demo video yet (`docs/DEMO_SCRIPT.md` has the shot list; under 3 minutes, unedited).
- The web app has no page that lists approved notes, and no sign-in.
- Only one model has been evaluated.
- Full list: the last section of `EVALS.md` and `docs/CLOUD_TASKS.md`.

## How to hand it back

1. Work on a branch: `git checkout -b <your-name>/<what-you-did>`.
2. Before each commit: `uv run pytest -q` and `uv run ruff check src tests`.
3. Push the branch and open a pull request on GitHub. Do not push to `main`.
4. In the pull request, write: what you tested, with which model, what broke, what you fixed, and
   what you left. A short list is enough.

If you only tested and changed nothing, open a GitHub issue with your notes instead.
