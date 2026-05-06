"""Configuration: env vars + simple dataclass. Single source of truth for the loop."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    openrouter_api_key: str
    openrouter_base_url: str
    llm_model: str
    vision_model: str
    interval_seconds: int
    goals: str
    save_dir: Path | None
    tts_language: str
    tts_voice: str | None
    research_enabled: bool
    research_model: str
    research_dir: Path
    memory_dir: Path
    memory_recent_turns: int
    memory_char_limit: int

    @staticmethod
    def load(
        interval_seconds: int,
        goals: str,
        save_dir: Path | None = None,
        tts_language: str = "auto",
        tts_voice: str | None = None,
        research_enabled: bool = False,
        research_dir: Path | None = None,
        memory_dir: Path | None = None,
        memory_recent_turns: int | None = None,
        memory_char_limit: int | None = None,
    ) -> "Config":
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        return Config(
            openrouter_api_key=api_key,
            openrouter_base_url=os.environ.get(
                "MON_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            llm_model=os.environ.get("MON_LLM_MODEL", "deepseek/deepseek-chat"),
            vision_model=os.environ.get(
                "MON_VISION_MODEL", "moonshotai/kimi-vl-a3b-thinking"
            ),
            interval_seconds=interval_seconds,
            goals=goals,
            save_dir=save_dir,
            tts_language=tts_language,
            tts_voice=tts_voice,
            research_enabled=research_enabled,
            research_model=os.environ.get(
                "MON_RESEARCH_MODEL", "deepseek/deepseek-chat:online"
            ),
            research_dir=(
                research_dir
                if research_dir is not None
                else Path(os.environ.get("MON_RESEARCH_DIR", "notes"))
            ),
            memory_dir=(
                memory_dir
                if memory_dir is not None
                else Path(os.environ.get("MON_MEMORY_DIR", "notes/mentor-memory"))
            ),
            memory_recent_turns=(
                memory_recent_turns
                if memory_recent_turns is not None
                else int(os.environ.get("MON_MEMORY_RECENT_TURNS", "12"))
            ),
            memory_char_limit=(
                memory_char_limit
                if memory_char_limit is not None
                else int(os.environ.get("MON_MEMORY_CHAR_LIMIT", "2000"))
            ),
        )
