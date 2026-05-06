const $ = (id) => document.getElementById(id);

(async function init() {
  const cfg = await chrome.storage.local.get({
    apiKey: "",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "openai/gpt-4o-mini"
  });
  $("apiKey").value = cfg.apiKey;
  $("baseUrl").value = cfg.baseUrl;
  $("model").value = cfg.model;
})();

$("save").addEventListener("click", async () => {
  const apiKey = $("apiKey").value
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .trim()
    .replace(/^['"]|['"]$/g, "")
    .replace(/^Bearer\s+/i, "")
    .trim();
  await chrome.storage.local.set({
    apiKey,
    baseUrl: $("baseUrl").value.trim() || "https://openrouter.ai/api/v1",
    model: $("model").value.trim() || "openai/gpt-4o-mini"
  });
  if (!apiKey) {
    $("status").textContent = "Saved — but no API key entered.";
    $("status").style.color = "#f88";
  } else {
    $("status").textContent = `Saved. Key length: ${apiKey.length}.`;
    $("status").style.color = "#8fd";
  }
  setTimeout(() => { $("status").textContent = ""; $("status").style.color = ""; }, 2500);
});
