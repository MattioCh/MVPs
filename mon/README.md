# mon

A mentor. Every N minutes `mon` captures your screen, asks a vision model what you're doing, compares it to your stated goals with an LLM, and **either stays silent (focused) or speaks one short nudge** via macOS `say`.

Designed for creating an environments that will help achieve their goals.

## Stack

| Role   | Provider                                   |
| ------ | ------------------------------------------ |
| LLM    | DeepSeek (`deepseek/deepseek-chat`) via OpenRouter |
| Vision | Kimi VL (`moonshotai/kimi-vl-a3b-thinking`) via OpenRouter |
| TTS    | Local macOS `say` (subprocess)             |

Package manager: **`uv` only**.

## Setup

```bash
uv sync
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
```

macOS will prompt for **Screen Recording** permission for your terminal/IDE the first time you run it. Grant it, then restart the terminal.

## Run

```bash
# every 10 minutes against goals.example.txt
uv run mon --goals goals.example.txt --interval 10

# single cycle (useful while testing)
uv run mon --goals goals.example.txt --once
```

Write your own goals file — plain text, the more concrete the better. Example:

```
I am studying linear algebra: eigenvalues, SVD.
On-task: textbook PDFs, lecture videos on the topic, notes, problem sets.
Off-task: social media, entertainment YouTube, shopping, games.
```

## TTS voices

- Voice names for `--tts-voice` come from your macOS `say` installation.
- See [docs/tts-voices.md](docs/tts-voices.md) for a full snapshot and examples.
- To list your current machine voices at any time: `say -v '?'`.

## Background research (optional)

Add `--research` and every cycle `mon` will:

1. Pick a short topic from what's currently on screen.
2. Run an online academic research call (web-search-backed) on that topic.
3. Write the brief to `notes/research-<timestamp>.md` (and overwrite
   `notes/research-latest.md`) — always, so you can read it on your own.
4. Hand the brief to the mentor as background. The mentor still defaults to
   silence and only speaks if one specific idea or question would clearly
   help right now.

```bash
uv run mon --goals goals.example.txt --interval 10 --research
```

Manual one-off (no loop, just produces a markdown file):

```bash
uv run mon --goals goals.example.txt research --topic "eigenvalues geometric intuition"
```

Tunables (flag or env):

| Flag             | Env                  | Default                          |
| ---------------- | -------------------- | -------------------------------- |
| `--research-dir` | `MON_RESEARCH_DIR`   | `notes`                          |
| —                | `MON_RESEARCH_MODEL` | `deepseek/deepseek-chat:online`  |

The `:online` suffix routes through OpenRouter's web plugin (Exa-backed). No new key.

## Mentor memory (per goal)

`mon` remembers what it has already said to you for the same goals across runs, so it doesn't repeat the same nudge or re-narrate research it has already surfaced.

- A "goal" is identified by the **exact trimmed text** of your goals file. Edit the wording → new memory stream.
- Each cycle appends one JSONL entry (spoken *and* silent outcomes) to `notes/mentor-memory/goal-<hash>.jsonl`.
- Before each LLM call, the most recent same-goal entries are summarized into a short `MENTOR MEMORY` block injected into the prompt with an explicit "do not repeat" instruction.

Tunables (flag or env):

| Flag                    | Env                         | Default                |
| ----------------------- | --------------------------- | ---------------------- |
| `--memory-dir`          | `MON_MEMORY_DIR`            | `notes/mentor-memory`  |
| `--memory-recent-turns` | `MON_MEMORY_RECENT_TURNS`   | `12`                   |
| `--memory-char-limit`   | `MON_MEMORY_CHAR_LIMIT`     | `2000`                 |

Privacy: memory entries contain mentor messages and short research digests derived from your screen. They live locally; do not commit them.

## Notes

- Screenshots are held in memory only and never written to disk.
- The "stay silent" branch is the expected outcome most of the time.
- Model ids are configurable via env (`MON_LLM_MODEL`, `MON_VISION_MODEL`).
- TTS is intentionally local for the MVP; swap `mon/tts.py` to switch providers.
