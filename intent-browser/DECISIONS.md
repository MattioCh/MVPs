# Decisions

## 1. Chrome extension (MV3) over mini-browser or proxy

**Considered:**
- **Electron mini-browser** with embedded webviews. Total control over the rendering surface; could rewrite HTML, intercept network, etc.
- **Local proxy** (mitmproxy / Node) that rewrites HTML on the way through.
- **Chrome extension (MV3)** with content scripts.

**Chose:** Chrome extension.

**Why:** The user said they want to *feel* this when they "go into YouTube, Google, a new browser." The fastest way to that feeling is to keep the browser they already use and have the transformation happen *in place*. Electron loses the muscle memory of "I just opened YouTube." A proxy is brittle on modern SPAs (most content arrives via XHR/streaming, not initial HTML), and HTTPS interception requires a CA cert install that destroys the install-in-60-seconds property. MV3 content scripts run on every page after load, can mutate the DOM, can persist per-host state, and ship in one folder.

**Tradeoffs accepted:**
- MV3 service workers are restartable; we keep no in-memory state in `background.js`.
- Some sites use strict CSP that blocks injected styles in unusual ways. Acceptable for an MVP.
- Can't intercept network requests for true ad-blocking without `declarativeNetRequest` rules. The visual hide is sufficient for the *feeling*; a future version can add network-level blocking.

## 2. LLM-decides-which-elements-to-hide over hand-written rules

**Considered:**
- Curated CSS selector lists per site (uBlock-style).
- LLM generates CSS selectors from intent + URL.
- LLM picks element IDs from a structural summary we provide.

**Chose:** LLM picks IDs from a structural summary.

**Why:** Hand-written rules cannot interpret arbitrary user intent ("only my subscriptions"). LLM-generated CSS selectors hallucinate against obfuscated class names common on modern sites. Tagging the live DOM with `data-ib-id` and asking the model to reference those IDs grounds the model in reality — it can only return IDs that actually exist on the page, and we can apply them with certainty.

**Tradeoffs accepted:**
- Latency: 1–3 seconds per filter. Acceptable for the "I'm shaping this page" moment.
- Cost: a few hundred input tokens per page on `gpt-4o-mini`. Cheap.
- IDs aren't stable across loads, so remembered intent triggers a new LLM call on each page load. v0.2 problem.

## 3. Baseline ad-stripper layered under the LLM filter

**Why:** The user should feel the inversion *the moment they install*, before they've typed any intent or even configured an API key. A curated selector list strips obvious ads/promos on every page instantly. The LLM layer then refines based on stated intent.

## 4. Bring-your-own-key via OpenRouter (default)

**Considered:** Hosted backend that proxies to an LLM with our key; direct OpenAI; per-provider SDKs.

**Chose:** User pastes their own OpenRouter key. Base URL still exposed so power users can swap to OpenAI direct, LM Studio, or Ollama (all OpenAI-compatible).

**Why OpenRouter as default:** One key, one endpoint, every frontier model — Claude, Gemini, GPT, Llama, Qwen, etc. The user can A/B different models against the same intent without changing anything except the model slug. That matters here because filtering quality is model-dependent and the user explicitly asked to be able to pick the model. No backend on our side means no infra, no abuse risk, no developer cost.

**Tradeoffs accepted:** OpenRouter adds a thin margin over provider list prices and is a single point of failure. Both acceptable for an MVP; the Base URL escape hatch covers anyone who wants to bypass it.

## 5. Per-hostname intent persistence

**Why:** The whole point is that *next time* you open YouTube, it's already shaped. Storing `{intent, hide, keep}` keyed by hostname in `chrome.storage.local` is the minimum that delivers this. Per-URL granularity (e.g. different intent for `youtube.com/feed/subscriptions` vs `youtube.com/watch`) is a natural v0.2.

## 6. JSON mode for LLM response

**Why:** Robustness. Free-form responses break parsers. `response_format: {type: "json_object"}` plus a prompt that specifies the schema gives us reliable `{hide, keep, reason}` objects. We still defensively regex-extract a JSON object as a fallback.
