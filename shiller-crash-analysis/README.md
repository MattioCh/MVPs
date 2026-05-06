# Shiller CAPE crash-vs-earnings analysis

Read [ANALYSIS.md](ANALYSIS.md) for the full writeup. Methodology
rationale in [DECISIONS.md](DECISIONS.md).

## Run end-to-end

```bash
uv sync
uv run python scripts/download_data.py
uv run python scripts/parse_shiller.py
uv run python scripts/analyze.py
uv run python scripts/charts.py
```

Outputs land in `data/` (raw + cleaned panel) and `output/` (episode
tables, summary stats, charts).
