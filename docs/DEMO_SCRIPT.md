# Demo video script

Target: one unedited screen recording, under 3:00 (aim for 2:40), with tool calls visible on screen and at least one place where the agent fails or declines. Do not cut, speed up or splice. Say that the data is synthetic.

## Before recording

- LM Studio is running its local server with `qwen3.5-9b` loaded and has answered one request already (the first call after loading is slower).
- Fresh data: `uv run meska seed`, then clear `data/runs/` if you want an empty Agent tab. Do not run `seed` while recording.
- Run the whole script once and time it. Agent runs take tens of seconds each on a laptop. If the run is too slow to fit, use the cover lines in the "While it runs" rows instead of cutting.
- Two windows side by side: the browser at http://127.0.0.1:8765 and a terminal in the repo folder. Large font. Choose a teacher name in "Signed in as" before you start (the video should show the name being used, not hide it).
- Learner A-17's id: `uv run meska learners`. Teacher ids: `uv run meska teachers`.
- Rehearse the two runs in the Agent tab starting back to back. They are for different learners, so both are allowed (a learner can have only one open run). They should run at the same time; the model server queues them. If your setup does not handle that, start the wrong-learner run after the findings are approved.

## Shot list

| Time | On screen | Say | Tool calls visible |
|---|---|---|---|
| 0:00 to 0:15 | Terminal: `uv run meska demo`, then the browser at the app. | "Meska Brain follows one learner across years for a teacher. All data here is synthetic. It has not been tried with a real teacher yet." | Terminal command. |
| 0:15 to 0:50 | Map tab, Learner A-17. Press play on the Term slider. Click "Ratio as a comparison", press **Trace back**. | "Three maps: the curriculum, the learner, the teacher. Geometry is strong every year. Ratios are low. Trace back walks the curriculum links: equivalent fractions, fractions, division, taught in grade 3 in a term with 17 days of absence. The graph does this, not the model. Each line has the records behind it." | The trace is the `trace_root` logic, shown in the panel with its evidence list. |
| 0:50 to 1:00 | Agent tab: Learner A-17, file `quiz_sheet_A17_2025-T1.md`, **Start a run**. Then immediately start a second run: Learner F-12 with the same file. | "Now the agent. I give it A-17's new quiz sheet. I also hand the same sheet to a different learner, F-12, on purpose." | Run cards appear. |
| 1:00 to 1:30 | While both runs work: open the failure case that needs no model. Map tab, Learner D-09, click "Fractions as equal parts of a whole", **Trace back**. | "This is where it declines. For D-09 the topic the difficulty probably began in was taught in a term with no records. The map says it cannot tell where it began. It does not guess. If I ran the agent on D-09 it would not propose a finding here either: it would list this as a question left open for the teacher." | Trace panel shows no root and the unrecorded topic. |
| 1:30 to 1:50 | Agent tab, open the F-12 run. | "The wrong-learner run: the document names Learner A-17, so the agent recorded nothing for F-12." | Step log: `extract_evidence` marked failed with the "must not land on the wrong learner" note. |
| 1:50 to 2:10 | Open the A-17 run. Show the steps: `read_document` (markitdown), `extract_evidence`, `record_evidence`, `investigate` (which tools the model chose, what the coverage check added), `propose_findings`. | "markitdown, which Microsoft wrote, reads the file over MCP. Our own server records the evidence. The model picked these analysis tools; the coverage check added what it missed. The run is now stopped at gate 1. Anything the records could not settle shows up as a question left open, not as a finding." | Step log with tool names; status "waiting for a teacher". |
| 2:10 to 2:30 | Review queue. Open a finding and its evidence. Approve the root cause finding as the chosen teacher. | "The finding cites real records. I am the named teacher. I approve this one. Nothing the agent proposes is visible as approved until I do." | Decision is written to `approvals`. |
| 2:30 to 2:50 | Terminal: `uv run meska audit`. Optionally the Audit log tab with the decisions table. | "Every tool call is here, with who made it. The agent's calls say agent, the decision says teacher. The agent has no tool that can approve. The run now drafts three notes: an English one for the guardian, a Swahili one for the guardian that is a machine draft nobody has checked, and an English handover note. It stops at gate 2 for me to approve the text." | `get_learner_timeline`, `record_evidence`, `find_patterns`, `trace_root`, `what_worked`, `get_findings`, `propose_finding` in the log (the gate check is a logged tool call too); the teacher decision row. |
| 2:50 to 3:00 | Hold on the review queue showing the three drafted notes waiting, the Swahili one tagged with its language. | "That is Meska Brain. It is open source under Apache 2.0, and what is not finished is in the README." | Draft summaries pending. |

## Optional extra decline (if there is time, otherwise skip)

Show the server refusing an unsourced claim, from the terminal:

```
uv run python -c "from meska_brain import tools; print(tools.propose_finding(learner_id='LEARNER_ID', kind='struggle', statement='Results in fractions are low.', evidence_ids=[]))"
```

It ends with "No evidence, no finding." and the refused call appears in `uv run meska audit` with `ok` set to NO.

## Do not

- Do not claim the model chose a tool when the step note says the coverage check added it.
- Do not call the Swahili note checked or approved-quality. It is a machine draft; say so.
- Do not show or imply real children or schools. The aliases are made up.
- Do not re-record only part of it. If a run fails on camera, say so and keep going, or record again from the start.
