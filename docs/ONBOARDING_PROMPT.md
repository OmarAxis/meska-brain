# Onboarding prompt

New to the project? Clone the repo, open the folder in Claude Code, and paste the text below as your
first message. It asks Claude to read the project and walk you through it step by step.

This needs Claude Code, or another assistant that can read the files in the folder. A plain chat window
cannot open the repo.

```text
I'm joining a project called Meska Brain and I need you to get me up to speed. I'm a teammate, not the original author, and I haven't seen the code. Explain things in simple, plain language, as if to a smart person who is new to this project. Avoid jargon, and when you must use a technical word, say what it means.

Context: Meska Brain is our entry for the Education track ("The Long View") of the African Agentic AI Design Challenge. It follows one learner across years and builds a record, with evidence, for a teacher. The teacher always decides. The repo is https://github.com/OmarAxis/meska-brain and I have it cloned in this folder.

First, read these files in this order before answering anything: CLAUDE.md, HANDOVER.md, PITCH.md, README.md, ARCHITECTURE.md, EVALS.md, DESCRIPTION.md. Then look through src/meska_brain, packs, and tests so your answers come from the real code, not from guesses. If the docs and the code disagree, trust the code and tell me.

Then walk me through the project in these steps. Stop after each step and ask if I have questions before moving on.

1. The idea. What problem does this solve, who is it for, and why does it matter for schools with few resources? Use the example of the child who missed school in grade 3 and struggles in grade 6.

2. How it works, without code. Explain the three maps (curriculum, learner, teacher), what the graph engine does, what the AI model does and does not do, and why a teacher approves everything.

3. The features. Go screen by screen through the teacher app: class overview, school map, learner profile, knowledge graph, learning map, patterns, review queue, approved, the printable report, my teaching, agent, audit log. For each one, say what it shows and why it's there.

4. The challenge rules. List the rules we must meet and the things that would disqualify us, and show me where in the code each rule is met. Be clear about which rules matter most.

5. The code. Give me a map of the folders and the 8 to 10 most important files, one or two sentences each. Then pick one full path and trace it for me end to end: a quiz sheet comes in, and a finding ends up waiting for a teacher. Name the files and functions as you go.

6. Get it running. Help me run it on my machine, one command at a time, and check each one worked before the next: install, tests, start the app, load all four subjects with "uv run meska seed --pack generic-school", then "uv run meska story". I'll use a hosted API with an open-weights model instead of a local model, so help me set the four environment variables from HANDOVER.md. I'll paste my own key into my terminal myself; never ask me to put a key in a file or in this chat.

7. Exercises. Give me five small hands-on exercises, easiest first, so I learn by doing. For example: read one learner's story in the app, approve a finding as a teacher and find it in the audit log, write my own made-up quiz sheet and run the agent on it, try to make the system label a child and see it refuse, add one topic to a curriculum pack. Tell me what I should see if each one worked.

8. What's weak. Tell me honestly what is not finished, not tested, or risky, using EVALS.md and what you see in the code. Then suggest the three most useful things I could work on, with the reason for each.

Rules for working with me on this repo:
- Only made-up data. Never real pupils.
- Never commit a key or a .env file. The repo is public.
- Don't weaken the teacher approval steps or the check that stops the system labelling a child.
- Before any commit, run "uv run pytest -q" and "uv run ruff check src tests".
- Work on a branch and open a pull request. Don't push to main.
- If I report results, say which model produced them. Only open-weights model results go in EVALS.md.

Start by reading the files, then give me a five-sentence summary of the whole project before step 1.
```
