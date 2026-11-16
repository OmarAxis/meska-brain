# Security and data protection

Meska Brain is a prototype. It is built to run on one machine inside a school, on synthetic data. This page
says what the code enforces today, what it does not, and how to report a problem.

## What the code enforces

| Rule | Where | Checked by |
|---|---|---|
| The agent cannot approve a finding or a note, or answer its own question. Those functions are not MCP tools. | `review.py`, `server.py` | `tests/test_server.py` |
| Every tool call is written to the audit log, including refused ones, with who called it. | `audit.py` | `tests/test_tools.py` |
| A finding must cite evidence that exists and belongs to that learner. | `tools.py` | `tests/test_tools.py` |
| A statement that labels, ranks or tracks a child is refused, for the agent and for a teacher's edit. | `guard.py` | `tests/test_guard.py` |
| A document that names another learner is never recorded on this one. | `agent/workflow.py` | `tests/test_agent_units.py` |
| Instructions inside a document are treated as data. | `agent/prompts.py` | evaluation task A9 |
| A file is opened only by name from the inbox folder. A path from the page is never followed. | `web/app.py` | `tests/test_web.py` |
| All SQL uses bound parameters. Table and column names never come from a request. | `db.py`, `tools.py` | code review |
| The school map and the export never carry a learner's scores, and never rank learners. | `school.py` | `tests/test_report_and_school.py` |
| The teacher app and the MCP HTTP server listen on `127.0.0.1` unless you change it. | `config.py`, `server.py` | |
| The page loads no script, font or style from another site. | `web/static/index.html` | `tests/test_web.py` |
| No key is stored in the repository. Settings come from the environment. | `.gitignore`, `config.py` | |
| A cloud model key typed in the teacher app is kept in memory until the app stops. It is never written to the database, the audit log, a run record or a file, no endpoint returns it, and it is removed from any error text. | `agent/llm.py`, `web/app.py` | `tests/test_cloud_models.py` |
| A learner's name is shown to teachers only. No MCP tool returns it and no model prompt contains it: tools and models see the record code. | `tools.py`, `agent/workflow.py` | `tests/test_school_seed.py` |
| The explanation shown with a finding is computed from the records it cites, never written by a model. | `explain.py` | `tests/test_explain.py` |

## What it does not do yet

These are known gaps. Do not use Meska Brain with real learners until they are closed.

- **No sign-in.** A teacher is chosen from a list. Anyone at the machine can approve as any teacher.
- **No encryption at rest.** The database is one SQLite file. Protect the machine and its disk.
- **No roles.** Every teacher can see every learner.
- **No consent records, and no way to correct or delete one learner's data on request.**
- **No backup.** If the file is lost, the history is lost.
- **A cloud key typed in the app is protected only by the app being on this machine.** There is no sign-in, so
  anyone who can open the page can start a run that uses the key until the app stops.
- **The MCP HTTP server has no authentication.** Keep it on `127.0.0.1`. Do not put it on a network or behind a
  public tunnel with real data.
- **The guard is a word list.** It blocked 2 of 6 labelling phrasings it was not written for (see `EVALS.md`). The
  teacher gate is the real protection.

## Data

All data in this repository is synthetic. Learners are aliases such as "Learner A-17" and teachers are fictional.
Never add real learner data to this repository, an issue, a pull request or a test.

The names shown for learners are invented (a first name and an initial). They are not real children.

The default is a local open-weights model, so nothing leaves the machine. The Agent page can use OpenAI or Claude
for a run instead. Then the document and the records the agent reads are sent to that company, by record code and
without names. Do that with synthetic data only. The page says so each time a cloud model is chosen.

## Reporting a problem

Open a private security advisory on the GitHub repository (Security, then Report a vulnerability). Please do not
open a public issue for something that could expose learner data. Say what you did, what happened and what you
expected.
