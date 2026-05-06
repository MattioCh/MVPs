// Intent Browser — background service worker
// Handles LLM calls so API keys never live in page context.

const SYSTEM_PROMPT = `You are an interface curator. The user is browsing a webpage and has stated what they want to see. You will receive:
- The user's intent (free text).
- A compressed list of significant DOM elements on the page. Each has an id (the "ib" number), tag, role, aria-label, classes, and a short text snippet.

Your job: decide which elements DO NOT serve the user's intent and should be hidden. Be aggressive about ads, recommendations, promos, sidebars, banners, modals, "people you may know", trending, suggested, sponsored, and anything irrelevant to what the user asked for. Be conservative about elements that look like the actual content the user wants.

Respond ONLY with valid minified JSON of the form:
{"hide":[1,2,3],"keep":[4,5],"reason":"one short sentence"}

- "hide": array of ib numbers to hide.
- "keep": array of ib numbers that are clearly the content the user wants (used for emphasis; can be empty).
- "reason": one short sentence explaining your filter, written to the user in second person.

No prose outside the JSON. No code fences.`;

async function callLLM({ intent, elements, settings }) {
  let { apiKey, baseUrl, model } = settings;
  // Strip whitespace, surrounding quotes, and any literal "Bearer " prefix the
  // user may have pasted by accident. Also strip zero-width chars some browsers
  // sneak in via autofill.
  apiKey = (apiKey || "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .trim()
    .replace(/^['"]|['"]$/g, "")
    .replace(/^Bearer\s+/i, "")
    .trim();

  if (!apiKey) {
    throw new Error("No API key set. Click the Intent Browser toolbar icon, paste your OpenRouter key (starts with sk-or-v1-), and press Save.");
  }

  const userMsg = `User intent: ${intent}\n\nElements (JSON):\n${JSON.stringify(elements)}`;

  const res = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
      // OpenRouter uses these for attribution / leaderboards. Harmless on other providers.
      "HTTP-Referer": "https://github.com/intent-browser",
      "X-Title": "Intent Browser"
    },
    body: JSON.stringify({
      model,
      temperature: 0.1,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: userMsg }
      ],
      response_format: { type: "json_object" }
    })
  });

  if (!res.ok) {
    const text = await res.text();
    if (res.status === 401) {
      throw new Error(
        `401 from ${baseUrl}. The saved key (length ${apiKey.length}) was rejected. ` +
        `Open the extension popup, re-paste your OpenRouter key (starts with "sk-or-v1-"), and press Save. ` +
        `Provider said: ${text.slice(0, 200)}`
      );
    }
    throw new Error(`LLM error ${res.status}: ${text.slice(0, 300)}`);
  }
  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content ?? "{}";
  let parsed;
  try {
    parsed = JSON.parse(content);
  } catch (e) {
    // Try to recover JSON from a code-fenced response
    const m = content.match(/\{[\s\S]*\}/);
    if (!m) throw new Error("LLM returned non-JSON response.");
    parsed = JSON.parse(m[0]);
  }
  return parsed;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "ib:filter") return false;
  (async () => {
    try {
      const settings = await chrome.storage.local.get({
        apiKey: "",
        baseUrl: "https://openrouter.ai/api/v1",
        model: "openai/gpt-4o-mini"
      });
      const result = await callLLM({
        intent: msg.intent,
        elements: msg.elements,
        settings
      });
      sendResponse({ ok: true, result });
    } catch (err) {
      sendResponse({ ok: false, error: String(err.message || err) });
    }
  })();
  return true; // async
});
