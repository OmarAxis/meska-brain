"""Command line. `uv run meska demo` is the one command a stranger needs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import db
from .config import get_settings

app = typer.Typer(add_completion=False, help="Meska Brain: a cited learning map for every learner.")
console = Console()


def _ensure_seeded() -> None:
    """Create the synthetic demo data the first time, so one command is enough.
    Messages go to stderr: on stdio, stdout belongs to the MCP protocol."""
    settings = get_settings()
    db.init_db()
    with db.connect() as conn:
        count = db.one(conn, "SELECT COUNT(*) AS n FROM learners")["n"]
    if count == 0:
        from . import synth
        notices = Console(stderr=True)
        notices.print("No data yet. Generating the synthetic cohort...")
        summary = synth.generate()
        notices.print(f"Seeded {settings.db_path} ({summary})")


def _resolve_learner(text: str) -> str:
    """Accept a learner id or an alias such as 'A-17'."""
    with db.connect() as conn:
        row = db.one(conn, "SELECT id FROM learners WHERE id=? OR alias=? OR alias LIKE ?", (text, text, f"%{text}"))
    if not row:
        raise typer.BadParameter(f"No learner matches '{text}'. Try `meska learners`.")
    return row["id"]


@app.command()
def seed(seed: int = 7, learners: int = 12, years: int = 4) -> None:
    """Regenerate the synthetic cohort. Wipes existing data."""
    from . import synth
    console.print_json(json.dumps(synth.generate(seed=seed, n_learners=learners, years=years), default=str))


@app.command()
def demo() -> None:
    """Seed if needed, then open the teacher app."""
    _ensure_seeded()
    s = get_settings()
    console.print(f"Teacher app: http://{s.web_host}:{s.web_port}   (Ctrl+C to stop)")
    from .web.app import main as web_main
    web_main()


@app.command()
def serve() -> None:
    """Run the teacher app."""
    demo()


@app.command()
def mcp(http: bool = typer.Option(False, help="Serve streamable HTTP instead of stdio.")) -> None:
    """Run the Meska Brain MCP server (stdio by default) for any MCP host."""
    _ensure_seeded()
    from . import server
    if http:
        sys.argv = [sys.argv[0], "--http"]
    else:
        sys.argv = [sys.argv[0]]
    server.main()


@app.command()
def learners() -> None:
    """List learners (alphabetical, by alias)."""
    _ensure_seeded()
    with db.connect() as conn:
        found = db.rows(conn, "SELECT id, alias, home_language FROM learners ORDER BY alias")
    table = Table("id", "alias", "home language")
    for r in found:
        table.add_row(r["id"], r["alias"], r["home_language"])
    console.print(table)


@app.command()
def teachers() -> None:
    """List teachers and their ids (needed for `meska decide`)."""
    _ensure_seeded()
    with db.connect() as conn:
        found = db.rows(conn, "SELECT id, name FROM teachers ORDER BY name")
    table = Table("id", "name")
    for r in found:
        table.add_row(r["id"], r["name"])
    console.print(table)


def _print_run(record: dict) -> None:
    console.rule(f"run {record['run_id']} · {record['status']} · model {record.get('model')}")
    for step in record.get("steps", []):
        mark = "ok " if step.get("ok", True) else "!! "
        console.print(f"[dim]{step['ts'][11:19]}[/dim] {mark}[bold]{step['node']}[/bold]: {step['note']}", highlight=False)
    for q in record.get("open_questions", []):
        console.print(f"   open question: {q}", highlight=False)
    if record.get("pending"):
        console.print(f"Waiting for a teacher: {record['pending']}", highlight=False)
    if record.get("error"):
        console.print(f"[red]{record['error']}[/red]", highlight=False)
    console.print(f"usage: {record.get('usage')}", highlight=False)


@app.command()
def run(learner: str, file: Path | None = typer.Option(None, help="A new document to ingest first."),
        frontier: bool = typer.Option(False, help="Use the optional frontier model instead of the local one."),
        model: str | None = typer.Option(None, help="Model id to use.")) -> None:
    """Run the agent for one learner until it finishes or stops for a teacher."""
    _ensure_seeded()
    from .agent import runner
    task = {"learner_id": _resolve_learner(learner), "which_model": "frontier" if frontier else "local"}
    if file:
        task["inbox_file"] = str(file.resolve())
    if model:
        task["model"] = model
    _print_run(runner.run_blocking(task))


@app.command()
def resume(run_id: str) -> None:
    """Continue a run after the teacher has decided."""
    from .agent import runner
    _print_run(runner.resume_blocking(run_id))


@app.command()
def pending() -> None:
    """Show what is waiting for a teacher."""
    from . import review
    console.print_json(json.dumps(review.pending(), ensure_ascii=False, default=str))


@app.command()
def decide(target_id: str, decision: str, teacher: str = typer.Option(..., help="Teacher id (tch_...)."),
           note: str | None = None, edited: str | None = typer.Option(None, help="New statement, for decision=edited.")) -> None:
    """Record a teacher's decision on a finding (fnd_...) or a summary (sum_...)."""
    from . import review
    if target_id.startswith("sum_"):
        result = review.decide_summary(target_id, decision, teacher, note=note)
    else:
        result = review.decide_finding(target_id, decision, teacher, note=note, edited_statement=edited)
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@app.command()
def audit(limit: int = 20) -> None:
    """Show the most recent tool calls."""
    with db.connect() as conn:
        found = db.rows(conn, "SELECT ts, actor, tool, ok, duration_ms, run_id FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    table = Table("time", "actor", "tool", "ok", "ms", "run")
    for r in found:
        table.add_row(r["ts"], r["actor"], r["tool"], "yes" if r["ok"] else "NO", str(r["duration_ms"]), r["run_id"] or "")
    console.print(table)


@app.command("eval")
def eval_(repeats: int = typer.Option(3, help="Runs per model-dependent task, to measure variation."),
          skip_model: bool = typer.Option(False, help="Only run the tasks that need no model."),
          models: str | None = typer.Option(None, help="Comma-separated model ids to compare.")) -> None:
    """Run the evaluation set and write evals/results and EVALS.md."""
    from .evals import run_all
    run_all(repeats=repeats, skip_model=skip_model, models=models.split(",") if models else None)


if __name__ == "__main__":
    app()
