"""Background research adapter — DeepSeek `:online` via OpenRouter.

OpenRouter's `:online` model suffix routes the request through their `web`
plugin (Exa-backed) and returns citations as `message.annotations`. We use
that as the cheapest path to give the LLM web access without adding a new
provider or API key.

Every cycle the loop calls `research()` with a topic extracted from the
current vision report. The result is written to `notes/research-<ts>.md`
(and overwrites `notes/research-latest.md`) and also passed back into the
mentor LLM, which decides whether anything is worth saying out loud.

Docs: https://openrouter.ai/docs/features/web-search
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from .config import Config


_SYSTEM = """You are a background research assistant for a focused learner.
Each cycle you are given a topic the user is currently working on, plus
their study goals. Your job is to use the web — favouring ACADEMIC and
authoritative sources (peer-reviewed papers, arXiv, university course
notes, standard textbooks, primary documentation, well-known references) —
and return a short, concrete brief.

Constraints:
- Quality over quantity. 3–5 distinct angles is plenty.
- Prefer primary academic sources. Skip blog spam, SEO listicles, marketing.
- Do not invent sources. Only cite what you actually consulted via the web.
- Assume the reader is the user described in USER GOALS, at their level.
- The user may never read this. Be useful at a glance.

Output STRICT Markdown with EXACTLY these sections, in this order:

# Topic
One sentence restating the topic.

# Why this might help
2–3 sentences linking the topic to the user's stated goals. Concrete.

# Angles
A numbered list of 3–5 short angles. Each item: a bold one-line title, then
1–3 sentences of substance, ending with an inline citation like `[1]` that
points to a source in the list below.

# Questions to explore
A numbered list of 2–3 sharp questions the user could ask themselves to go
deeper. Phrased as questions, not advice.

# Sources
A numbered list of the academic/authoritative sources you actually used.
For each: title — author/venue if known — short note on what's in it — URL.
If you have no sources, write "none".

Rules:
- No preamble, no closing remarks, no emojis.
- Keep the whole response under ~600 words."""


@dataclass(frozen=True)
class ResearchResult:
    topic: str
    markdown: str
    annotations: list[dict] | None
    finish_reason: str | None
    usage: dict | None


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "with", "to", "in", "on",
    "at", "by", "is", "are", "be", "this", "that", "it", "its", "as", "from",
    "user", "screen", "appears", "currently", "working", "viewing",
}


def _normalize(text: str, max_words: int = 8) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    keep = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    return " ".join(keep[:max_words])


def extract_topic(vision_report: str) -> str:
    """Derive a short research topic from a vision report.

    Tries, in order:
    1. `Primary activity:` line + first 1–2 `# TEXT EXTRACTED` bullets.
    2. First few `# APPLICATIONS VISIBLE` window/tab titles + `# CONTENT DETAIL`
       (used when the vision report was truncated before ACTIVITY SIGNAL).
    Returns "" if nothing usable was found.
    """
    parts: list[str] = []

    m = re.search(r"Primary activity:\s*(.+)", vision_report)
    if m:
        parts.append(m.group(1).strip())

    parts.extend(_section_bullets(vision_report, "# TEXT EXTRACTED", limit=2))

    if not parts:
        # Fallback for truncated reports.
        parts.extend(_section_bullets(vision_report, "# APPLICATIONS VISIBLE", limit=4))
        content_detail = _section_body(vision_report, "# CONTENT DETAIL")
        if content_detail:
            parts.append(content_detail[:300])

    return _normalize(" ".join(parts))


def _section_bullets(report: str, header: str, limit: int) -> list[str]:
    out: list[str] = []
    in_section = False
    for line in report.splitlines():
        s = line.strip()
        if s.startswith(header):
            in_section = True
            continue
        if in_section:
            if s.startswith("#"):
                break
            if s.startswith("- "):
                out.append(s[2:].strip().strip('"'))
                if len(out) >= limit:
                    break
    return out


def _section_body(report: str, header: str) -> str:
    if header not in report:
        return ""
    block = report.split(header, 1)[1]
    block = re.split(r"\n# ", block, maxsplit=1)[0]
    return block.strip()


# ---------------------------------------------------------------------------
# Research call
# ---------------------------------------------------------------------------


def research(cfg: Config, topic: str, context: str = "") -> ResearchResult:
    """Run one online research call. `topic` is short; `context` is optional
    extra text (usually a trimmed copy of the vision report) to disambiguate.
    """
    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)

    user_msg_parts = [
        f"USER GOALS:\n{cfg.goals.strip()}",
        f"TOPIC:\n{topic.strip()}",
    ]
    if context.strip():
        user_msg_parts.append(f"CURRENT SCREEN CONTEXT (truncated):\n{context.strip()}")
    user_msg = "\n\n".join(user_msg_parts)

    resp = client.chat.completions.create(
        model=cfg.research_model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=1500,
        temperature=0.4,
    )
    choice = resp.choices[0]
    markdown = (choice.message.content or "").strip()
    annotations = getattr(choice.message, "annotations", None)
    if annotations is not None:
        try:
            annotations = [
                a.model_dump() if hasattr(a, "model_dump") else dict(a)
                for a in annotations
            ]
        except Exception:
            annotations = None
    usage = resp.usage.model_dump() if resp.usage is not None else None
    return ResearchResult(
        topic=topic,
        markdown=markdown,
        annotations=annotations,
        finish_reason=choice.finish_reason,
        usage=usage,
    )


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------


def write_markdown(result: ResearchResult, dir: Path) -> Path:
    """Write the research markdown to `dir/research-<ts>.md` and overwrite
    `dir/research-latest.md` with the same content.
    """
    dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = dir / f"research-{stamp}.md"
    body = result.markdown or "# Topic\n\n(empty research result)\n"
    header = f"<!-- topic: {result.topic} -->\n<!-- generated: {stamp} -->\n\n"
    path.write_text(header + body, encoding="utf-8")
    (dir / "research-latest.md").write_text(header + body, encoding="utf-8")
    return path


def digest(result: ResearchResult, max_chars: int = 220) -> str:
    """One-line digest of a research brief for memory logs.

    Pulls the first sentence/line of the `# Why this might help` section if
    present, otherwise the first non-empty content line. Bounded length.
    """
    md = (result.markdown or "").strip()
    if not md:
        return ""
    snippet = ""
    if "# Why this might help" in md:
        block = md.split("# Why this might help", 1)[1]
        block = re.split(r"\n# ", block, maxsplit=1)[0].strip()
        snippet = block
    if not snippet:
        for line in md.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("<!--"):
                continue
            snippet = s
            break
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 1].rstrip() + "…"
    return snippet
