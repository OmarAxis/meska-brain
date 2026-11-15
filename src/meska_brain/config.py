"""Settings, all from environment variables with local-first defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    db_path: Path
    packs_dir: Path
    default_pack: str
    # Any OpenAI-compatible endpoint. Default is LM Studio on this machine (open-weights models).
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    # Optional second model shown alongside the open-weights one. Never required.
    frontier_base_url: str | None
    frontier_api_key: str | None
    frontier_model: str | None
    web_host: str
    web_port: int
    mcp_port: int


def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        db_path=Path(env("MESKA_DB", str(ROOT / "data" / "meska.db"))),
        packs_dir=Path(env("MESKA_PACKS", str(ROOT / "packs"))),
        default_pack=env("MESKA_PACK", "generic-maths"),
        llm_base_url=env("MESKA_LLM_BASE_URL", "http://localhost:1234/v1"),
        llm_api_key=env("MESKA_LLM_API_KEY", "lm-studio"),
        llm_model=env("MESKA_LLM_MODEL", "qwen3.5-9b"),
        frontier_base_url=env("MESKA_FRONTIER_BASE_URL"),
        frontier_api_key=env("MESKA_FRONTIER_API_KEY"),
        frontier_model=env("MESKA_FRONTIER_MODEL"),
        web_host=env("MESKA_WEB_HOST", "127.0.0.1"),
        web_port=int(env("MESKA_WEB_PORT", "8765")),
        mcp_port=int(env("MESKA_MCP_PORT", "8766")),
    )
