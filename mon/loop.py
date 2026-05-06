"""Main loop: capture → vision → (optional research) → mentor decision → optional TTS.

When `cfg.research_enabled` is on, every cycle:
1. Vision describes the screen.
2. We extract a short topic and run an online academic research call.
3. The research markdown is written to disk (always — the user can read it).
4. Mentor LLM receives screen + research and decides whether to speak.

The mentor still defaults to silence. Research is background context; the
user reads the markdown when they want to.
"""

from __future__ import annotations

import time
from datetime import datetime

from . import capture, llm, memory, research as research_mod, tts, vision
from .config import Config


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run_once(cfg: Config) -> None:
    """Run a single capture→vision→(research)→mentor→tts cycle."""
    try:
        png = capture.capture_primary_screen()
    except Exception as e:
        _log(f"capture failed: {e}")
        return

    if cfg.save_dir is not None:
        try:
            cfg.save_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = cfg.save_dir / f"screen-{stamp}.png"
            path.write_bytes(png)
            _log(f"saved {path}")
        except OSError as e:
            _log(f"save failed: {e}")

    try:
        description = vision.describe_screen(cfg, png)
    except Exception as e:
        _log(f"vision failed: {e}")
        return
    if not description.strip():
        _log("vision returned empty description; skipping cycle")
        return
    if "<!-- vision truncated" in description:
        _log("vision: response was truncated (finish_reason=length) — partial report below")
    _log(f"screen: {description}")

    research_markdown: str | None = None
    research_topic: str | None = None
    research_digest: str | None = None
    if cfg.research_enabled:
        topic = research_mod.extract_topic(description)
        if not topic:
            _log("research: no usable topic from vision report; skipping")
        else:
            _log(f"research: topic={topic!r}")
            try:
                result = research_mod.research(cfg, topic=topic, context=description)
                path = research_mod.write_markdown(result, cfg.research_dir)
                research_markdown = result.markdown
                research_topic = topic
                research_digest = research_mod.digest(result)
                _log(f"research: wrote {path}")
            except Exception as e:
                _log(f"research failed: {e}")

    try:
        recent = memory.load_recent(
            cfg.memory_dir, cfg.goals, limit=cfg.memory_recent_turns
        )
        memory_recap = memory.build_recap(recent, char_limit=cfg.memory_char_limit)
    except Exception as e:
        _log(f"memory load failed: {e}")
        memory_recap = ""
    if memory_recap:
        _log(f"memory: injecting {len(recent)} prior entries ({len(memory_recap)} chars)")

    try:
        decision = llm.decide(
            cfg,
            description,
            research_markdown=research_markdown,
            memory_recap=memory_recap or None,
        )
    except Exception as e:
        _log(f"llm failed: {e}")
        return

    if decision.reasoning:
        _log(f"reasoning: {decision.reasoning}")

    was_silent = not decision.message
    memory.append_entry(
        cfg.memory_dir,
        cfg.goals,
        message=decision.message,
        was_silent=was_silent,
        topic=research_topic,
        research_digest=research_digest,
    )

    if was_silent:
        _log(
            f"llm returned empty message; skipping TTS "
            f"(finish_reason={decision.finish_reason}, usage={decision.usage})"
        )
        return
    _log(f"mentor: {decision.message}")
    tts.speak(
        decision.message,
        language=cfg.tts_language,
        voice=cfg.tts_voice,
    )


def run_forever(cfg: Config) -> None:
    _log(
        f"mon started — interval={cfg.interval_seconds}s, "
        f"vision={cfg.vision_model}, llm={cfg.llm_model}, "
        f"research={'on' if cfg.research_enabled else 'off'}"
    )
    try:
        while True:
            run_once(cfg)
            time.sleep(cfg.interval_seconds)
    except KeyboardInterrupt:
        _log("stopped.")
