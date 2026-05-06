"""Vision adapter — Kimi VL via OpenRouter (OpenAI-compatible)."""

from __future__ import annotations

import base64

from openai import OpenAI

from .config import Config

_PROMPT = """You are a screen-observation assistant. Analyze the screenshot and produce an exhaustive, factual report of what is on the user's monitor RIGHT NOW. Describe only what is directly visible — never guess intent or invent content. If something is unreadable, write "unreadable". If a section has nothing to report, write "none".

Use EXACTLY the following sections and headers, in this order:

# OVERVIEW
- One or two sentences summarizing the whole screen at a glance.
- Display layout: single monitor / multi-monitor, OS (macOS/Windows/Linux if inferable from chrome), approximate window arrangement (e.g. "split view: editor left, browser right").

# APPLICATIONS VISIBLE
List every application, window, and browser tab you can identify. Use a bullet per app, with sub-bullets for windows/tabs. Include exact titles when readable.
Format:
- <App name> — <window count> window(s)
  - Window/Tab: "<exact title>" — brief role (e.g. editor, terminal, chat, video)
Mark the focused/frontmost window with `[FOCUSED]`.

# SCREEN REGIONS
Break the screen into spatial regions and describe each. Use this structure for each region:
- Region: <top-left | top-right | center | left-pane | right-pane | bottom | menu-bar | dock | etc.>
  - App/Window: <which app occupies it>
  - Contents: <what is shown — UI elements, panels, text blocks, media>
  - Notable text: <short quotes of any prominent visible text, headings, code identifiers, URLs>

# UI COMPONENTS
Enumerate distinctive UI elements present anywhere on screen:
- Menu bar items, toolbars, sidebars, tab bars
- Editors / terminals / REPLs (note language, file name, line numbers if visible)
- Browser address bars (record full URL if readable)
- Media players (note playback state, title, timestamp)
- Notifications, modals, pop-ups, badges, unread counts
- System indicators (clock, battery, wifi, status icons) — only if clearly visible

# CONTENT DETAIL
For the most prominent content area(s), describe what is actually shown:
- If code: language, file/module, what the code appears to do (based only on visible symbols)
- If document/article: title, headings, topic, current scroll position if inferable
- If web page: site, page title, main heading, key visible elements
- If video/image/media: subject, on-screen text, any captions
- If chat/messaging: app, conversation participants if visible, latest message snippet
- If data/dashboard: what is being measured, key numbers visible

# TEXT EXTRACTED
Bullet list of short, verbatim snippets of any clearly legible text that helps identify activity (titles, headings, URLs, filenames, prominent labels). Keep each snippet under ~120 chars. Skip body paragraphs.

# ACTIVITY SIGNAL
- Primary activity: <one short phrase describing what the user appears to be doing, based strictly on visible evidence>
- Supporting evidence: <bullet list of the specific visual cues that justify the above>
- Confidence: <high | medium | low>

Rules:
- Be precise and concrete. Prefer exact titles, filenames, and URLs over paraphrases.
- Do not infer the user's goals, emotions, or future actions.
- Do not mention anything that is not visible in the image.
- Keep the structure exactly as specified so downstream parsing is reliable."""


def _data_url(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def describe_screen(cfg: Config, png_bytes: bytes) -> str:
    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)

    content: list[dict] = [
        {"type": "text", "text": _PROMPT},
        {"type": "image_url", "image_url": {"url": _data_url(png_bytes)}},
    ]

    resp = client.chat.completions.create(
        model=cfg.vision_model,
        messages=[{"role": "user", "content": content}],
        max_tokens=6144,
        temperature=0.2,
    )
    msg = resp.choices[0].message
    finish = getattr(resp.choices[0], "finish_reason", "unknown")
    text = (getattr(msg, "content", None) or "").strip()
    if not text:
        # Reasoning models (Kimi K2.5/K2.6, etc.) may put output in `reasoning`
        # when truncated or when the model thinks but never finalizes.
        text = (getattr(msg, "reasoning", None) or "").strip()
    if not text:
        raise RuntimeError(f"vision returned empty content (finish_reason={finish})")
    if finish == "length":
        # Don't fail — the partial report is usually still useful — but flag it
        # so the loop can log and downstream parsers know to be lenient.
        text += f"\n\n<!-- vision truncated: finish_reason={finish} -->"
    return text
