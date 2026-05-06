# Your Browser

> The web, inverted. *You* tell every page should look like. Youtube should have the UI you think it should have + video. You should have the UI as you want, not just the one they offer to you.

This is an MVP Chrome extension that lets you walk into any website — YouTube,
Google, Facebook, a news site you've never seen — and immediately declare what
*you* want from it. An LLM reads the page structure, decides what doesn't serve
your intent, and hides it. The rest of the page is the page you came for.

It's the opposite of how the web works today. Today the site decides what you
see. Here, you do.

---

## What you'll feel

1. You open YouTube. Floating in the corner: **"what do you want here?"**
2. You click it and type: *"only my subscriptions, no shorts, no recommendations, no ads"*
3. The page fades. The shorts shelf, the trending sidebar, the ads, the
   "watch next" panel — they dissolve. What's left is the thing you actually
   came for.
4. Next time you open YouTube, your intent is remembered. The page loads the
   way *you* defined it.

You can do this on any site. Google. A news homepage. An e-commerce listing.
Whatever.

A baseline ad/promo stripper runs instantly on every page even before you say
anything, so the "this feels different" sensation hits the moment you install.

---

## Install (developer mode, ~60 seconds)

1. Open `chrome://extensions`
2. Toggle **Developer mode** (top right)
3. Click **Load unpacked** and select this folder (`intent-browser/`)
4. Click the puzzle-piece icon in Chrome's toolbar → pin **Intent Browser**
5. Click the extension icon → paste your OpenRouter API key → Save
   - Get a key at <https://openrouter.ai/keys>
   - Pick any model from <https://openrouter.ai/models> and paste its slug
     (e.g. `anthropic/claude-3.5-sonnet`, `google/gemini-2.0-flash-001`,
     `meta-llama/llama-3.3-70b-instruct`). Default is `openai/gpt-4o-mini`.
   - The Base URL field is exposed for power users who want to point at
     another OpenAI-compatible endpoint (OpenAI direct, LM Studio, Ollama).
6. Open any site. The pill is in the bottom-right.

---

## How it works

- **`content.js`** — injected into every page. It:
  - Applies a curated baseline of ad/promo selectors immediately.
  - Tags every "significant" region of the DOM with a `data-ib-id` attribute.
  - Builds a compact JSON summary (tag, role, aria-label, classes, text snippet)
    of up to ~180 regions.
  - Sends `{intent, elements}` to the background worker.
  - Receives `{hide:[ids], keep:[ids]}` and applies it via injected CSS with a
    smooth fade.
  - Persists per-hostname intent so the next visit auto-applies.
  - Watches for SPA URL changes and re-runs.
- **`background.js`** — service worker. Calls the LLM (OpenAI-compatible
  `/chat/completions` with JSON mode) so your API key never lives in page
  context.
- **`popup.html` / `popup.js`** — minimal settings: API key, base URL, model.

---

## Limits of the MVP (what to expect, what's next)

- Per-page-load LLM call when re-applying remembered intent. Costs a few
  fractions of a cent on `gpt-4o-mini`. A v0.2 should cache by URL signature
  and only re-call when the page structure meaningfully changes.
- Element IDs are assigned at tagging time, so they aren't stable across page
  loads. That's why re-applying requires a fresh LLM call. A future version
  could derive structural fingerprints (selector + position + text hash) and
  cache rules on those.
- Modern feed sites (Facebook, Instagram) heavily obfuscate class names. The
  LLM-based approach is more robust to this than hand-written rules, but
  results will vary.
- No screenshot understanding — purely structural. Adding a vision model pass
  for ambiguous pages is the obvious next step.
- No "allow ads sometimes" mode yet. The architecture supports it cleanly:
  a per-host toggle that skips the baseline + LLM filter.

See `DECISIONS.md` for the rationale behind each technical choice.
