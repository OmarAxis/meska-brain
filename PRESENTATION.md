# Meska Brain: presenting it in Nairobi

Speaker notes for MCP Dev Summit Nairobi, 19 and 20 November 2026. The longer written pitch is in
`PITCH.md`. This file is what to say out loud, to whom, and in what order.

## Who is in the room

Checked on 15 November 2026 against the summit's own pages and the challenge site.

- **Size.** The organisers expect 700 or more developers, founders and enterprise AI leaders. One outside
  estimate says close to 2,000 people from about 240 companies, with roughly 280 founders or C-level.
  That estimate is not the organisers' list, so treat it as a guess.
- **Mostly builders.** Engineers from Safaricom, Andela, Yellowcard, Kora, Jacaranda Health, IntelliSOFT,
  Data Science Nigeria, JetBrains and GitHub are on the programme. They will judge the code before the
  story.
- **Funders and public-good people.** The opening keynote is by the Gates Foundation's AI programme officer
  and the Africa Digital Health Networks, on what safety means when agents act. Qhala's founder is on a
  panel about agents in low-resource settings.
- **The protocol people.** The Agentic AI Foundation runs the event, and MCP maintainers are there.
- **The judges.** The challenge site still says "panel to be announced". Plan for a mix of the three
  groups above.

## What this room already cares about

These are talks on the schedule. Each one is a door we can walk through with something we have built.

| Talk on the schedule | What we can honestly say |
|---|---|
| Small Models, Big Toolboxes; The Context Window Is the Budget | Our agent runs on a 9B open model on one laptop. A run costs 40 to 100 seconds and no money. |
| MCP When the Network Disappears; Goose In A Pond keynote | It needs no internet. Records never leave the school. |
| Translating MCP (GitHub keynote) | It reads teacher notes in Arabic, French and Swahili and drafts notes for guardians in their language. |
| From Answers to Action: safety for agents (Gates Foundation) | The agent cannot approve anything. Approval is not a tool it has. A named teacher decides, twice. |
| Cross-Agent Decision Memory: a Graph of Why; Memory Is a Tool Contract | Every finding carries the ids of the records it rests on, and those ids come from the tools, never the model. |
| Instruction Injection Through MCP Tool Descriptions | We fed it a document with hidden instructions. It ignored them. It is in `EVALS.md`. |

## The one sentence

Rich countries improve schools with money. We cannot, so we make sure nothing a teacher learns about a
child is lost.

## The three-minute pitch

**0:00 The child (30 seconds).**
"A girl misses three weeks of school in grade 3. That is the term her class learns division. Nobody
notices a gap. Three years later she is failing fractions. Her grade 6 teacher sees a child who is weak at
maths. The real cause is three years old and it is in another teacher's notebook, or nowhere."

**0:30 Why nobody catches it (20 seconds).**
"A private school fixes this with small classes and specialists. A public school teacher has fifty
learners, a pile of quiz sheets and her memory. Every year the child moves on, and what the last teacher
knew is lost."

**0:50 What we built (30 seconds).**
"Meska Brain keeps each learner's story across the years and lays it over the school's own curriculum,
which already says what builds on what. Then it does the searching no teacher has time for: where did
this difficulty start, what has stayed strong, what kind of teaching was followed by progress."

**1:20 Show it (60 seconds).** Screen, not slides.
1. One learner. Drag the term slider back. "The gap was visible in grade 3."
2. Drop in a teacher's note in Swahili or Arabic. The agent reads it, records evidence, proposes a finding.
   Tool calls are on screen.
3. Click the finding. "Every sentence opens the records behind it."
4. Approve as a named teacher. "The agent cannot do this step. It has no tool for it."
5. Ask it to label a child. The server refuses, and the refusal is in the log.

If there is time, show the loop instead of step 5. Run the agent on Learner D-09 with no document. It stops
and asks for a division record, because the trace cannot go further without one. Type three marks as the
teacher. It reads them, looks again, and the root moves from fractions back to division.

**2:20 Why it is safe to trust (20 seconds).**
"The model does not reach the conclusions. Plain code does, over a graph. The model reads documents and
writes sentences. So a parent can ask why, and there is an answer."

**2:40 What is not true yet, and the ask (20 seconds).**
"No real school has used it. All of this is synthetic data. We want one school, one class, one term, and
teachers who will tell us where it is wrong."

## How to land it with each group

### The idea

- Lead with the child, never with the technology. The grade 3 to grade 6 story is the whole product.
- The fresh part is not "AI for education". It is **cause across years**: the curriculum is already a map
  of what depends on what, and we walk it backwards.
- Say the restraint out loud: it never labels a child, never ranks a class, never scores a teacher. In a
  room that opens with a safety keynote, the things we refuse to do are a feature.

### The business

- **Cost.** One ordinary laptop, a free open model, no fee per use, no internet. The price is a cost a
  school can carry without a donor.
- **Who pays.** The teacher uses it, the school or the ministry adopts it, a funder pays for the first
  pilots. Do not pretend parents pay.
- **Why it spreads.** A new subject, grade range or country is a new curriculum file, not new software.
- **Why it is bigger than schools.** The engine is three maps: what there is to learn, what a person has
  shown, what support helped. Swap the curriculum for a job's skills map and it follows an apprentice or a
  nurse in training. Mention this once, near the end. Do not lead with it.
- **Why open.** It is Apache 2.0 licensed and built on MCP, so a school's existing systems can connect and nobody
  is locked in. To this audience that is a selling point, not a weakness.
- Give no market-size numbers. We have none we can defend, and this room will ask.

### The engineering

- Our own MCP server: twelve tools, four that write, every call logged with inputs, outputs and time.
- One borrowed server, Microsoft's `markitdown-mcp`, for reading documents, so we did not write our own
  converter.
- LangGraph for the agent, with two points where it stops and waits for a named teacher.
- 203 tests that need no model, run by CI on Linux and Windows on every push. An evaluation of 28 tasks on an open model, plus 14 scenarios run by hand.
- Show a failure on purpose. The guard catches only 2 of 6 labelling phrasings it was not written for. One
  drafted note added advice that was not in the approved findings. Both are written down in `EVALS.md`.

## Questions you will get

| Question | Answer |
|---|---|
| Has a teacher used it? | No. That is the first thing we want from this room. |
| Why not just ask a big model? | Then nobody can say why. Here the conclusions come from code over records, and each one cites them. |
| What if the model invents something? | It cannot invent evidence ids. They come from the tools. A teacher still reads everything before it counts. |
| What about children's data? | Synthetic only today. In a school it stays on the school's laptop. Learners are aliases. |
| What does a run cost? | Nothing per run. About a minute on a laptop with a 9B model. |
| Does it work in my language? | It reads notes in several. Nobody who speaks them natively has checked the notes it drafts. |
| What breaks? | Say the two failures above before they find them. |
| How is the agent more than a pipeline? | It loops. When a record is missing it stops, asks a teacher, reads the answer and investigates again before it proposes anything. It also chooses which analyses to run and recovers from bad documents. Be honest that outside that loop the order of steps is fixed. |

## For you, before you walk on

- Rehearse the three minutes aloud five times with a timer. Cut words, not the demo.
- Run `uv run meska story` before you present, so the screen is in a ready state. Have the model loaded.
- Record the demo once as a backup in case the laptop or projector fails.
- Zoom the browser to 125 percent. The back of a ballroom cannot read small text.
- Know three numbers by heart: twelve tools, two approval gates, zero cost per run.
- Go to the talks in the table above and speak to those speakers afterwards. They are the people most
  likely to care, and one of them may know a school.
- Never claim a pilot, a partner or a result we do not have. The rules disqualify fake results, and this
  audience checks repositories.

## Sources

- Summit home, schedule and keynote speakers: https://events.linuxfoundation.org/mcp-dev-summit-nairobi/
- Sponsor page (expected attendance): https://events.linuxfoundation.org/mcp-dev-summit-nairobi/sponsor/
- Outside attendance estimate: https://www.promptprospect.ai/conferences/mcp-dev-summit-nairobi-2026
- Challenge and Education track brief: https://agentic-africa-challenge.lovable.app/tracks/education
