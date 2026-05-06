# MVPs

A monorepo of small, self-contained projects — each a functional MVP built to explore an idea end-to-end.

---

## Projects

### 1. shiller-crash-analysis

**Shiller CAPE crash-vs-earnings analysis** using Robert Shiller's dataset since 1881. Built with Python (≥3.12), pandas, and matplotlib.

Quantitative exploration of how S&P 500 CAPE ratios relate to forward drawdowns and earnings recoveries across 140+ years of market history. See the project's own [ANALYSIS.md](shiller-crash-analysis/ANALYSIS.md) for the full research writeup and [DECISIONS.md](shiller-crash-analysis/DECISIONS.md) for methodology rationale.

**Setup**

```bash
# Prerequisites: Python ≥3.12 and uv (pip install uv, or see https://docs.astral.sh/uv)
cd shiller-crash-analysis
uv sync
```

**Run end-to-end**

```bash
uv run python scripts/download_data.py   # fetch raw Shiller xls + yfinance supplements
uv run python scripts/parse_shiller.py    # parse into cleaned panel
uv run python scripts/analyze.py          # run crash/episode analysis
uv run python scripts/charts.py           # generate charts and summary stats
```

Outputs land in `data/` (raw + cleaned panel) and `output/` (episode tables, summary stats, charts).

---

### 2. intent-browser

**A Chrome browser extension.** The web, inverted — *you* tell every page what it's for, and everything else dissolves.

Declares an intent for any website (e.g. *"only my subscriptions, no shorts, no recommendations"* on YouTube), and an LLM reads the page structure, decides what doesn't serve your intent, and hides it. Intents persist per hostname. A curated ad/promo baseline runs instantly on every page from the moment you install.

Built as a Manifest V3 extension with vanilla JS, a service-worker-backed LLM proxy (OpenAI-compatible `/chat/completions`), and injected CSS transitions.

**Setup (developer mode, ~60 seconds)**

1. Open `chrome://extensions`
2. Toggle **Developer mode** (top right)
3. Click **Load unpacked** and select the `intent-browser/` folder
4. Pin the extension via Chrome's puzzle-piece toolbar icon
5. Click the extension icon → paste your OpenRouter API key → Save
   - Get a key at [openrouter.ai/keys](https://openrouter.ai/keys)
   - Pick any model slug from [openrouter.ai/models](https://openrouter.ai/models)
   - Default model: `openai/gpt-4o-mini`
6. Open any site — the intent pill appears in the bottom-right corner

See the project's own [README.md](intent-browser/README.md) for a full walkthrough, and [DECISIONS.md](intent-browser/DECISIONS.md) for the rationale behind each technical choice.

---

## Monorepo structure

```
MVPs/
├── README.md                     ← this file
├── .gitignore
├── shiller-crash-analysis/       # Python data-analysis project
│   ├── pyproject.toml            # dependencies managed by uv
│   ├── scripts/                  # pipeline scripts
│   ├── data/                     # raw + cleaned data
│   └── output/                   # tables, stats, charts
└── intent-browser/               # Chrome extension (Manifest V3)
    ├── manifest.json
    ├── background.js              # service worker (LLM proxy)
    ├── content.js                 # page injection + DOM tagging
    ├── content.css                # fade transitions + baseline stripping
    ├── popup.html / popup.js      # settings UI
    └── icons/
```

## License

Each project carries its own license. See individual project directories for details.
