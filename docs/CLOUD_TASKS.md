# Things that need the team

These cannot be done from the project folder.

## Required for submission

1. **Create the public GitHub repository and push with fresh history.**
   - Start from a clean `git init` so no earlier history, local paths or scratch files come along.
   - Never commit a `.env` file or any key. `.gitignore` already excludes `.env` and `.env.*` but keeps `.env.example`. Check with `git status` before the first commit.
   - The generated database (`data/*.db`, `data/runs/`, `data/checkpoints*`) is ignored on purpose; a stranger regenerates it with `uv run meska demo`.
   - Decide whether to commit `evals/results/`. If you do, it must be from a real `uv run meska eval` run, and `EVALS.md` must be the file that run wrote.
   - Re-run `uv run pytest` and `uv run meska eval` on the final code, so `EVALS.md` matches what is pushed.
   - Test from a fresh clone on a machine that has only `uv`: `uv run meska demo`.
2. **Record and upload the demo video** (under 3 minutes, unedited) to YouTube or Vimeo, following `docs/DEMO_SCRIPT.md`. Put the link in the submission form and in the README.
3. **Fill in the submission form.** Use `DESCRIPTION.md` for the text description and link the repository and the video.
4. **Talk to at least one real teacher, and add what they said to the README.** Show them the map and the review queue. Record their name only if they agree, and say what they found useful, confusing or wrong. Until this is done the README must keep saying it has not been tried with a teacher. Do not paraphrase their words into praise.

## Optional

5. **Host the MCP server over HTTP for remote hosts.** `uv run meska mcp --http` binds to 127.0.0.1 with no authentication. A remote deployment needs authentication and TLS first, and must hold only synthetic data.
6. **Native-speaker review of the non-English phrases.** The Swahili, Arabic, Amharic, Hausa and French text in `packs/phrases/observations.yaml`, the home-language guardian notes the agent drafts (machine drafts), and the French, Swahili and Arabic word lists in `src/meska_brain/guard.py` have not been reviewed by speakers. Record who reviewed them and what changed.
7. **Continuous integration.** There is none. A workflow that runs `uv run pytest` and `uv run meska eval --skip-model` would show a stranger that the repo runs.
