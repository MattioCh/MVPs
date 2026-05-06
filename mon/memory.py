"""Per-goal mentor memory — JSONL log + compact recap for the LLM.

A "goal" is identified by the trimmed text of the user's goals file. Each
cycle appends one entry; before the next LLM call the loop reads back the
most recent entries for the same goal and turns them into a short recap so
the mentor avoids repeating itself (advice OR research) across runs.

Stdlib only. Failures here are non-fatal — the loop should keep working
even if the memory file is missing or corrupt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def goal_hash(goals: str) -> str:
    """Stable short hash of the trimmed goal text. Exact-match identity."""
    norm = (goals or "").strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def goal_log_path(memory_dir: Path, goals: str) -> Path:
    return memory_dir / f"goal-{goal_hash(goals)}.jsonl"


@dataclass(frozen=True)
class MemoryEntry:
    timestamp: str
    was_silent: bool
    message: str
    topic: str | None
    research_digest: str | None


def append_entry(
    memory_dir: Path,
    goals: str,
    *,
    message: str,
    was_silent: bool,
    topic: str | None = None,
    research_digest: str | None = None,
) -> Path | None:
    """Append one cycle's outcome to the per-goal log. Returns the path
    written, or None on failure (silent — caller should not crash)."""
    try:
        memory_dir.mkdir(parents=True, exist_ok=True)
        path = goal_log_path(memory_dir, goals)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "goal_hash": goal_hash(goals),
            "goals": (goals or "").strip(),
            "was_silent": bool(was_silent),
            "message": (message or "").strip(),
            "topic": (topic or None),
            "research_digest": (research_digest or None),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path
    except OSError:
        return None


def load_recent(memory_dir: Path, goals: str, limit: int) -> list[MemoryEntry]:
    """Read the last `limit` entries for this goal. Skips malformed lines."""
    if limit <= 0:
        return []
    path = goal_log_path(memory_dir, goals)
    if not path.exists():
        return []
    out: list[MemoryEntry] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-limit * 4 :]:  # over-read to tolerate skipped lines
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append(
            MemoryEntry(
                timestamp=str(obj.get("timestamp", "")),
                was_silent=bool(obj.get("was_silent", False)),
                message=str(obj.get("message", "")),
                topic=obj.get("topic") or None,
                research_digest=obj.get("research_digest") or None,
            )
        )
    return out[-limit:]


def build_recap(
    entries: list[MemoryEntry],
    *,
    char_limit: int,
) -> str:
    """Turn recent entries into a short text block to inject into the LLM
    prompt. Returns "" if there is nothing useful to say."""
    if not entries:
        return ""

    spoken = [e for e in entries if not e.was_silent and e.message]
    research_seen = [e for e in entries if e.research_digest]

    lines: list[str] = []

    if spoken:
        lines.append("Recent things you ALREADY said to this user (do not repeat):")
        for e in spoken[-8:]:
            lines.append(f"- [{e.timestamp}] {e.message}")

    if research_seen:
        if lines:
            lines.append("")
        lines.append("Research topics you ALREADY surfaced for this goal (do not re-narrate unless new evidence appears):")
        seen_topics: set[str] = set()
        for e in research_seen[-12:]:
            key = (e.topic or "").lower().strip()
            if key and key in seen_topics:
                continue
            if key:
                seen_topics.add(key)
            topic_label = e.topic or "(untitled)"
            digest = e.research_digest or ""
            lines.append(f"- {topic_label}: {digest}")

    silent_count = sum(1 for e in entries if e.was_silent)
    if silent_count:
        if lines:
            lines.append("")
        lines.append(f"You also stayed silent on {silent_count} recent cycle(s) — silence is working; keep that bar high.")

    text = "\n".join(lines).strip()
    if char_limit > 0 and len(text) > char_limit:
        text = text[: char_limit - 1].rstrip() + "…"
    return text
