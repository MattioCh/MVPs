"""CLI entry point: `uv run python -m mon` or `uv run mon`."""

from __future__ import annotations

from pathlib import Path

import click

from . import research as research_mod
from .config import Config
from .loop import run_forever, run_once


@click.group(invoke_without_command=True)
@click.option(
    "--goals",
    "goals_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Path to a text file describing your current study goals.",
)
@click.option(
    "--interval",
    "interval_minutes",
    type=click.FloatRange(min=0.1),
    default=10.0,
    show_default=True,
    help="Minutes between checks (5–30 is the typical range).",
)
@click.option(
    "--once",
    is_flag=True,
    default=False,
    help="Run a single cycle and exit (useful for testing).",
)
@click.option(
    "--save-dir",
    "save_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="If set, save each captured screenshot as PNG into this directory.",
)
@click.option(
    "--tts-language",
    type=click.Choice(["auto", "en", "zh"], case_sensitive=False),
    default="auto",
    show_default=True,
    help="Language mode for mentor messages and TTS voice selection.",
)
@click.option(
    "--tts-voice",
    type=str,
    default="Samantha",
    help="Optional explicit macOS `say` voice name (overrides --tts-language voice choice).",
)
@click.option(
    "--research/--no-research",
    "research_enabled",
    default=False,
    show_default=True,
    help="Every cycle, run an online academic research call on the current on-screen topic. "
         "The result is saved as Markdown and passed to the mentor as background context.",
)
@click.option(
    "--research-dir",
    "research_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory for research markdown files (default: ./notes or $MON_RESEARCH_DIR).",
)
@click.option(
    "--memory-dir",
    "memory_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory for per-goal mentor memory logs (default: ./notes/mentor-memory or $MON_MEMORY_DIR).",
)
@click.option(
    "--memory-recent-turns",
    "memory_recent_turns",
    type=click.IntRange(min=0),
    default=None,
    help="How many recent same-goal entries to load into context (default: 12 or $MON_MEMORY_RECENT_TURNS).",
)
@click.option(
    "--memory-char-limit",
    "memory_char_limit",
    type=click.IntRange(min=0),
    default=None,
    help="Max chars of memory recap injected into the prompt (default: 2000 or $MON_MEMORY_CHAR_LIMIT).",
)
@click.pass_context
def main(
    ctx: click.Context,
    goals_path: Path | None,
    interval_minutes: float,
    once: bool,
    save_dir: Path | None,
    tts_language: str,
    tts_voice: str | None,
    research_enabled: bool,
    research_dir: Path | None,
    memory_dir: Path | None,
    memory_recent_turns: int | None,
    memory_char_limit: int | None,
) -> None:
    """Periodic screen-aware study mentor."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        goals_path=goals_path,
        tts_language=tts_language.lower(),
        tts_voice=tts_voice,
        research_dir=research_dir,
    )

    if ctx.invoked_subcommand is not None:
        return

    if goals_path is None:
        raise click.UsageError("--goals is required when running the loop.")

    goals = goals_path.read_text(encoding="utf-8")
    cfg = Config.load(
        interval_seconds=int(interval_minutes * 60),
        goals=goals,
        save_dir=save_dir,
        tts_language=tts_language.lower(),
        tts_voice=tts_voice,
        research_enabled=research_enabled,
        research_dir=research_dir,
        memory_dir=memory_dir,
        memory_recent_turns=memory_recent_turns,
        memory_char_limit=memory_char_limit,
    )
    if once:
        run_once(cfg)
    else:
        run_forever(cfg)


@main.command("research")
@click.option(
    "--topic",
    required=True,
    help="Short topic to research (e.g. 'eigenvalues geometric intuition').",
)
@click.option(
    "--context-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Optional file with extra context (a vision report, notes, etc.).",
)
@click.pass_context
def research_cmd(
    ctx: click.Context,
    topic: str,
    context_file: Path | None,
) -> None:
    """Run a single online research call and write the markdown."""
    goals_path: Path | None = ctx.obj.get("goals_path") if ctx.obj else None
    goals = goals_path.read_text(encoding="utf-8") if goals_path is not None else ""
    research_dir: Path | None = ctx.obj.get("research_dir") if ctx.obj else None
    cfg = Config.load(
        interval_seconds=600,
        goals=goals,
        research_enabled=True,
        research_dir=research_dir,
    )
    context = context_file.read_text(encoding="utf-8") if context_file else ""
    result = research_mod.research(cfg, topic=topic, context=context)
    path = research_mod.write_markdown(result, cfg.research_dir)
    click.echo(f"wrote {path}")
    click.echo(f"latest: {cfg.research_dir / 'research-latest.md'}")


if __name__ == "__main__":
    main()
