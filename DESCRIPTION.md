# Meska Brain: description

**Track:** Education, "The Long View". **Sub-theme:** Longitudinal strength tracking.

Meska Brain follows one learner across years and shows a teacher where that learner is strong, where they struggle, and where a struggle may have started, early enough to talk to a family.

It lays three maps over each other: the curriculum map (concepts and "needs this first" links, loaded from a swappable pack; we graph the school's curriculum, we do not change it), the learner map (every quiz item, note and attendance record), and the teacher map (what was taught, when, and with which approach).

A graph does the reasoning, in deterministic code: strengths and struggles held over several terms, a struggle traced back through prerequisites to where it began, and which teaching approaches were followed by improvement. A small open-weights model, qwen3.5-9b running locally, only reads documents, chooses which analysis tools to call, and words short text. Every finding cites its records. When the records cannot tell where a difficulty began, the system says so and asks the teacher. Nothing is approved by the agent: a named teacher approves each finding, then each summary, at two gates, and every tool call is logged. For a family whose home language is not English it drafts an English note and a machine-drafted home-language note, which no speaker has checked.

Example, with synthetic data: Learner A-17 is failing ratios in grades 6 and 7. The map walks back from ratios to equivalent fractions, fractions and division. Division was taught in grade 3, in a term with 17 days of absence. Geometry has been strong every year. The teacher sees both, with evidence, and decides what to say.

It has its own MCP server (ten tools, three that write), uses Microsoft's markitdown-mcp to read documents, and runs on LangGraph, checkpointed so a run can pause for a teacher and resume later. The demo pack is school mathematics, grades 1 to 8, not tied to one country; other subjects or countries are new pack files.

**Who and which workflow:** an upper-primary class teacher at handover time and before a parent meeting. This is a design target. It has not been validated with a real teacher or school, and all data here is synthetic.

Open source, Apache 2.0. Run it with `uv run meska demo`.
