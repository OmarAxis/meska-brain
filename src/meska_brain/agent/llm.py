"""Model access. Any OpenAI-compatible endpoint; the default is an open-weights model served
locally by LM Studio, so learner records never leave the machine."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI

from ..config import get_settings


@dataclass
class Usage:
    """Running totals for one agent run, so the cost of a run is known and reported."""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    by_step: list[dict] = field(default_factory=list)

    def add(self, step: str, message, seconds: float) -> None:
        meta = getattr(message, "usage_metadata", None) or {}
        self.calls += 1
        self.input_tokens += int(meta.get("input_tokens", 0))
        self.output_tokens += int(meta.get("output_tokens", 0))
        self.seconds += seconds
        self.by_step.append({"step": step, "seconds": round(seconds, 2),
                             "input_tokens": int(meta.get("input_tokens", 0)),
                             "output_tokens": int(meta.get("output_tokens", 0))})

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "seconds": round(self.seconds, 1)}


def chat_model(which: str = "local", model: str | None = None) -> ChatOpenAI:
    """`local` is the open-weights model. `frontier` is optional and only used when configured."""
    s = get_settings()
    if which == "frontier":
        if not (s.frontier_base_url and s.frontier_model):
            raise RuntimeError("No frontier model configured (MESKA_FRONTIER_BASE_URL, MESKA_FRONTIER_MODEL).")
        return ChatOpenAI(model=model or s.frontier_model, base_url=s.frontier_base_url,
                          api_key=s.frontier_api_key or "none", temperature=0, timeout=300, max_retries=1)
    # Small local models spend most of their time in "thinking" mode. The agent's tasks are
    # narrow (read a document, pick a tool, word a sentence), so thinking is off by default.
    # Measured on qwen3.5-9b: about 70 s per call with thinking, under 1 s without.
    reasoning = os.environ.get("MESKA_LLM_REASONING", "none")
    extra = {"reasoning_effort": reasoning} if reasoning != "default" else None
    return ChatOpenAI(model=model or s.llm_model, base_url=s.llm_base_url, api_key=s.llm_api_key,
                      temperature=0, timeout=600, max_retries=1, extra_body=extra)


async def timed_invoke(llm, messages, usage: Usage, step: str):
    """Invoke a model and add the call to the run's usage totals."""
    started = time.perf_counter()
    message = await llm.ainvoke(messages)
    usage.add(step, message, time.perf_counter() - started)
    return message
