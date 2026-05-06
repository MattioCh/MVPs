// Intent Browser — content script
// Injected into every page. Provides the floating intent pill, baseline
// ad-stripping, and applies LLM-decided element hides.

(() => {
  if (window.__intentBrowserLoaded) return;
  window.__intentBrowserLoaded = true;

  const HOST = location.hostname;
  const STORAGE_KEY = `ib:host:${HOST}`;

  // ---------- Baseline distraction stripper ----------
  // Curated selectors that are ~always ads/trackers/promos. Applied instantly
  // on every page so the user feels something the moment the extension loads.
  const BASELINE_SELECTORS = [
    // Generic ad markers
    '[class*="sponsored" i]', '[id*="sponsored" i]',
    '[class*="advert" i]:not([class*="adventure" i])',
    '[id*="advert" i]',
    '[data-ad]', '[data-ads]', '[data-adunit]',
    '[data-testid*="ad-" i]', '[data-testid*="-ad" i]',
    '[aria-label*="advertisement" i]',
    'iframe[src*="doubleclick"]', 'iframe[src*="googlesyndication"]',
    'iframe[src*="adservice"]', 'iframe[src*="amazon-adsystem"]',
    // YouTube
    'ytd-ad-slot-renderer', 'ytd-promoted-video-renderer',
    'ytd-promoted-sparkles-web-renderer', 'ytd-display-ad-renderer',
    'ytd-in-feed-ad-layout-renderer', 'ytd-banner-promo-renderer',
    'ytd-statement-banner-renderer', '#masthead-ad',
    'ytd-rich-section-renderer', // shorts shelf etc; opinionated
    // Facebook / Instagram (best-effort; class names rotate)
    '[aria-label="Sponsored" i]',
    // Cookie & newsletter walls
    '[id*="cookie" i][class*="banner" i]',
    '[class*="newsletter" i][class*="modal" i]',
    '[class*="paywall" i]'
  ];

  const baselineStyle = document.createElement("style");
  baselineStyle.id = "ib-baseline-style";
  baselineStyle.textContent =
    BASELINE_SELECTORS.join(",") +
    ` { display: none !important; visibility: hidden !important; }`;
  document.documentElement.appendChild(baselineStyle);

  // ---------- Hide rules layer (per-host, persisted) ----------
  const hideStyle = document.createElement("style");
  hideStyle.id = "ib-hide-style";
  document.documentElement.appendChild(hideStyle);

  const keepStyle = document.createElement("style");
  keepStyle.id = "ib-keep-style";
  document.documentElement.appendChild(keepStyle);

  function applyHideIds(ids) {
    if (!ids?.length) {
      hideStyle.textContent = "";
      return;
    }
    const sel = ids.map(i => `[data-ib-id="${i}"]`).join(",");
    hideStyle.textContent = `${sel} { opacity: 0 !important; pointer-events: none !important; transition: opacity .35s ease; }`;
    // After fade, fully remove from layout
    setTimeout(() => {
      hideStyle.textContent = `${sel} { display: none !important; }`;
    }, 380);
  }

  function applyKeepIds(ids) {
    if (!ids?.length) {
      keepStyle.textContent = "";
      return;
    }
    const sel = ids.map(i => `[data-ib-id="${i}"]`).join(",");
    keepStyle.textContent = `${sel} { outline: 2px solid rgba(120, 200, 255, 0.0); transition: outline-color .8s ease; }
      ${sel}.ib-pulse { outline-color: rgba(120, 200, 255, 0.6); }`;
    requestAnimationFrame(() => {
      ids.forEach(i => {
        document.querySelectorAll(`[data-ib-id="${i}"]`).forEach(el => {
          el.classList.add("ib-pulse");
          setTimeout(() => el.classList.remove("ib-pulse"), 1500);
        });
      });
    });
  }

  // ---------- DOM summarization ----------
  // Tag every "significant" element with data-ib-id, then build a compact
  // JSON description for the LLM.
  let nextId = 1;
  function tagAndCollect() {
    nextId = 1;
    const out = [];
    const seen = new WeakSet();

    const candidates = document.querySelectorAll(
      "header,nav,aside,section,article,main,footer,form," +
      "[role='banner'],[role='navigation'],[role='complementary'],[role='main']," +
      "[role='article'],[role='region'],[role='dialog'],[role='feed'],[role='list']," +
      "[role='listitem'],[aria-label],[id]," +
      // Common feed/card containers across major sites
      "ytd-rich-item-renderer,ytd-video-renderer,ytd-compact-video-renderer," +
      "ytd-watch-next-secondary-results-renderer,ytd-comments,#secondary,#related," +
      "div[data-pagelet],div[data-testid]"
    );

    const vw = window.innerWidth, vh = window.innerHeight;

    candidates.forEach(el => {
      if (seen.has(el)) return;
      if (el.closest("#ib-root")) return; // never tag our own UI
      const rect = el.getBoundingClientRect();
      // Skip invisible / tiny
      if (rect.width < 80 || rect.height < 40) return;
      // Skip giant wrappers covering most of the viewport (low signal)
      const area = rect.width * rect.height;
      const vpArea = vw * vh;
      if (area > vpArea * 2.5) return;

      seen.add(el);
      const id = nextId++;
      el.setAttribute("data-ib-id", String(id));

      const text = (el.innerText || "").trim().replace(/\s+/g, " ").slice(0, 120);
      const cls = (el.className && typeof el.className === "string")
        ? el.className.split(/\s+/).slice(0, 4).join(" ")
        : "";

      out.push({
        ib: id,
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || undefined,
        aria: el.getAttribute("aria-label") || undefined,
        id: el.id || undefined,
        cls: cls || undefined,
        text: text || undefined
      });

      if (out.length >= 180) return;
    });

    return out;
  }

  // ---------- Floating UI ----------
  const root = document.createElement("div");
  root.id = "ib-root";
  root.innerHTML = `
    <div id="ib-pill" title="Intent Browser — click to set what you want">
      <span id="ib-pill-dot"></span>
      <span id="ib-pill-label">what do you want here?</span>
    </div>
    <div id="ib-panel" hidden>
      <div id="ib-panel-header">
        <span>Tell me what this page is for <em>you</em>.</span>
        <button id="ib-close" aria-label="Close">×</button>
      </div>
      <textarea id="ib-input" rows="3" placeholder="e.g. only my subscriptions, no shorts, no recommendations, no ads"></textarea>
      <div id="ib-actions">
        <button id="ib-apply">Filter this page</button>
        <button id="ib-reset" class="ib-secondary">Reset</button>
      </div>
      <div id="ib-status"></div>
    </div>
  `;
  document.documentElement.appendChild(root);

  const pill = root.querySelector("#ib-pill");
  const panel = root.querySelector("#ib-panel");
  const input = root.querySelector("#ib-input");
  const status = root.querySelector("#ib-status");
  const applyBtn = root.querySelector("#ib-apply");
  const resetBtn = root.querySelector("#ib-reset");
  const closeBtn = root.querySelector("#ib-close");

  pill.addEventListener("click", () => {
    panel.hidden = false;
    input.focus();
  });
  closeBtn.addEventListener("click", () => { panel.hidden = true; });

  function setStatus(msg, kind = "info") {
    status.textContent = msg;
    status.dataset.kind = kind;
  }

  async function runFilter(intent) {
    setStatus("Reading the page…");
    const elements = tagAndCollect();
    setStatus(`Asking the model about ${elements.length} regions…`);
    try {
      const resp = await chrome.runtime.sendMessage({
        type: "ib:filter",
        intent,
        elements
      });
      if (!resp?.ok) {
        setStatus("Error: " + (resp?.error || "unknown"), "error");
        return;
      }
      const { hide = [], keep = [], reason = "" } = resp.result || {};
      applyHideIds(hide);
      applyKeepIds(keep);
      await chrome.storage.local.set({
        [STORAGE_KEY]: { intent, hide, keep, ts: Date.now() }
      });
      setStatus(`Filtered ${hide.length} regions. ${reason}`, "ok");
    } catch (e) {
      setStatus("Error: " + e.message, "error");
    }
  }

  applyBtn.addEventListener("click", () => {
    const intent = input.value.trim();
    if (!intent) { setStatus("Type what you want first.", "error"); return; }
    runFilter(intent);
  });

  resetBtn.addEventListener("click", async () => {
    applyHideIds([]);
    applyKeepIds([]);
    await chrome.storage.local.remove(STORAGE_KEY);
    input.value = "";
    setStatus("Reset. Page restored.", "ok");
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      applyBtn.click();
    }
  });

  // ---------- Auto-apply remembered intent on load ----------
  (async () => {
    const stored = (await chrome.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
    if (!stored?.intent) return;
    input.value = stored.intent;
    // Re-tag the current DOM so the stored ids align with what's on screen now.
    // Note: ids regenerate per-tagging, so we re-run the LLM on auto-apply.
    // This costs an API call per page load; acceptable for MVP.
    setStatus("Re-applying your intent…");
    runFilter(stored.intent);
  })();

  // ---------- React to SPA navigation ----------
  let lastUrl = location.href;
  const obs = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      // Give the SPA a beat to render new content.
      setTimeout(async () => {
        const stored = (await chrome.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
        if (stored?.intent) runFilter(stored.intent);
      }, 800);
    }
  });
  obs.observe(document.body, { childList: true, subtree: true });
})();
