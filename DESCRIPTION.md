# Meska Brain: description

**Track:** Education, "The Long View". **Sub-theme:** Longitudinal strength tracking.

Meska Brain follows one learner across years and shows a teacher where that learner is strong, where they struggle, and where a struggle may have started, early enough to talk to a family.

It lays three maps over each other: the school's own curriculum (topics and "needs this first" links, from a swappable pack), the learner's record (quiz items, notes, attendance), and what was taught, when and how.

A graph does the reasoning, in deterministic code: strengths and struggles held over several terms, a struggle traced back through prerequisites to where it began, and which teaching approaches were followed by improvement. A small open-weights model, qwen3.5-9b running locally, only reads documents, chooses which analysis tools to call, and words short text. Every finding cites its records. When the records cannot tell where a difficulty began, the agent stops, asks a named teacher for the missing record, and investigates again once it has an answer. Nothing is approved by the agent: a named teacher approves each finding, then each summary, at two gates, and every tool call is logged. Notes for families are drafted in English and, as an unchecked machine draft, in the home language.

Example, with synthetic data: Learner A-17 is failing ratios in grades 6 and 7. The map walks back from ratios to equivalent fractions, fractions and division. Division was taught in grade 3, in a term with 17 days of absence. Geometry has been strong every year. The teacher sees both, with evidence, and decides what to say.

It has its own MCP server (twelve tools, four that write), uses Microsoft's markitdown-mcp to read documents, and runs on LangGraph, checkpointed so a run can pause for a teacher and resume later. There are four subject packs (mathematics, science, language, technology), not tied to one country, and a whole-school pack that links them, so a difficulty in one subject can be traced to another.
**Who and which workflow:** an upper-primary class teacher at handover time and before a parent meeting. This is a design target. It has not been validated with a real teacher or school, and all data here is synthetic.

Open source, Apache 2.0. Run it with `uv run meska demo`.
