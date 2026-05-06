# Decisions

## Data source: Shiller `ie_data.xls`
- **Considered:** Shiller's dataset, S&P Dow Jones official series,
  Bloomberg, Damodaran's archive.
- **Chose:** Shiller, because it is (a) free and citable, (b) extends to
  1871, giving meaningful sample size for rare-event analysis, and (c) is
  the canonical source for the CAPE definition we are testing.
- **Tradeoffs accepted:** monthly granularity (vs daily); U.S.
  large-cap-only; updated only ~quarterly so it lags the present by
  several months.

## Valuation metric: CAPE (Shiller P/E10) over TTM P/E
- **Considered:** TTM P/E, forward P/E, CAPE, Excess CAPE Yield (ECY).
- **Chose:** CAPE as primary, with TTM P/E shown for contrast.
- **Why:** TTM P/E becomes uninformative or even inverted near recessions
  because the denominator collapses faster than the price. CAPE smooths
  through the earnings cycle and is the metric whose long-run reversion
  the user's question implicitly references. ECY would be a refinement
  that adjusts for real interest rates; out of scope here.

## Decomposition method: log identity, no model
- **Considered:** regression of forward returns on starting CAPE; VAR
  decomposition à la Campbell-Shiller; simple log identity.
- **Chose:** log identity (`d log CAPE = d log P - d log E10`) because
  it is exact and assumption-free. The question "did P fall or did E
  rise?" is fundamentally about contributions, not about a model fit.

## Mechanism thresholds (15% / 60% / 40%)
- The 15% real-price-drop bar to call something a "crash" is judgement.
  Bear-market convention is 20% nominal; in real terms over 10 years,
  20% nominal can occur in flat-real markets. 15% real makes the label
  meaningful.
- The 60/40 contribution split avoids edge cases where both sides moved
  but one barely dominated.
- These thresholds change the *labels* on episodes but **do not change
  the underlying decomposition values**, which are reported in full in
  the episode CSVs for reanalysis under different rules.

## Episode definition (peak of consecutive elevated months)
- **Alternative:** treat each elevated month as an observation. This
  inflates the sample but makes observations highly autocorrelated and
  overstates statistical power.
- **Chose:** one episode per consecutive elevated run, anchored at the
  CAPE peak. This is conservative and matches how a practitioner would
  reason ("we are in a high-CAPE regime; what happened last time?").

## Frontend / visualisation
- **Considered:** static matplotlib PNGs; an interactive Plotly/Streamlit
  app; a small SvelteKit dashboard.
- **Chose:** static PNGs.
- **Why:** the analysis is a one-shot research note answering a specific
  question, not an exploratory product. The value-add of interactivity is
  low and would consume disproportionate effort relative to the marginal
  insight. If the user later wants to explore other thresholds or
  horizons interactively, the underlying CSVs are sufficient to bolt on
  Streamlit in an afternoon.

## Stack
- Python 3.12, `uv` for env and deps. pandas + numpy + matplotlib +
  openpyxl/xlrd + requests. No heavier framework needed.

## IPO adjustment scope (added in IPO_ADJUSTMENT.md)
- **Considered:** (a) ignore the question — the index is the index; (b) build
  a full forward-looking pro-forma index with projected IPO timelines and
  index-inclusion mechanics; (c) compute simple BASE / FULL_INCLUSION /
  LOOKTHROUGH scenarios at one point in time (May 2026).
- **Chose:** (c).
- **Why:** the user's question is whether the headline ratio is *materially*
  understated by missing private-AI revenue. A static three-scenario
  comparison is sufficient to answer the order-of-magnitude question;
  the result (P/E moves by <1 in any direction) makes the more elaborate
  pro-forma exercise low-value.
- **Tradeoffs accepted:** uses point-in-time private valuations and rough
  net-income estimates; does not model float ratios or index-inclusion
  rules; treats stake percentages as economic (not voting/control) interests.
  All inputs are exposed in `data/*.csv` for the user to adjust.
