"""Core analysis: when CAPE is high, does mean reversion come from price
crashes or from earnings growth?

Method (decomposition)
----------------------
By construction, CAPE_t = RealPrice_t / RealEarnings10y_t.
Therefore:
    log(CAPE_{t+h} / CAPE_t) = log(P_real_{t+h}/P_real_t)
                              - log(E10_real_{t+h}/E10_real_t)
So any change in CAPE is *exactly* the difference between real-price growth
and 10-yr real-earnings growth. We can attribute mean reversion (when CAPE
falls) to whichever side moved more.

Episode definition
------------------
- A month is "elevated" if CAPE >= threshold (we run thresholds 25 and 30).
- Consecutive elevated months are merged into one episode, indexed by the
  episode's CAPE peak.
- For each episode peak we look forward 3, 5, and 10 years and compute:
    * forward real price return (cumulative)
    * forward real earnings (E10) growth
    * change in CAPE
    * peak-to-trough real-price drawdown inside the window
    * a contribution share: how much of the CAPE reversion is "price-down"
      vs "earnings-up". A reversion is "crash-driven" if the real price
      fell >15% and price contributed >60% of the absolute change.
      "Earnings-driven" if real price did NOT fall >15% and real earnings
      grew >15%. Otherwise "mixed/none".
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "shiller_clean.csv"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS_YEARS = [3, 5, 10]
THRESHOLDS = [25.0, 30.0]
CRASH_PRICE_DROP = -0.15      # real price drop deeper than -15%
EARNINGS_GROWTH_HURDLE = 0.15  # >15% real E10 growth


def load() -> pd.DataFrame:
    df = pd.read_csv(SRC, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    # We need the 10-yr real-earnings series for the decomposition. Use our
    # recomputation (matches Shiller's CAPE to <1% median).
    df = df.dropna(subset=["cape", "real_price", "real_earnings_10y_avg"]).reset_index(drop=True)
    return df


def find_episodes(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Collapse consecutive elevated months into episodes, anchored at
    the CAPE peak inside each run."""
    elevated = df["cape"] >= threshold
    # Group ID increments each time we cross from below->above.
    grp = (elevated & ~elevated.shift(1, fill_value=False)).cumsum()
    out = []
    for gid, sub in df[elevated].groupby(grp[elevated]):
        peak_idx = sub["cape"].idxmax()
        peak = df.loc[peak_idx]
        out.append({
            "episode_id": int(gid),
            "start_date": sub["date"].min(),
            "end_date": sub["date"].max(),
            "duration_months": len(sub),
            "peak_date": peak["date"],
            "peak_cape": peak["cape"],
            "peak_idx": peak_idx,
        })
    return pd.DataFrame(out)


def forward_metrics(df: pd.DataFrame, peak_idx: int, horizon_years: int) -> dict:
    n = len(df)
    target_date = df.loc[peak_idx, "date"] + pd.DateOffset(years=horizon_years)
    # Find first row at-or-after target date
    fut_mask = df["date"] >= target_date
    if not fut_mask.any():
        return {}
    fut_idx = df[fut_mask].index[0]
    p0, p1 = df.loc[peak_idx, "real_price"], df.loc[fut_idx, "real_price"]
    e0, e1 = df.loc[peak_idx, "real_earnings_10y_avg"], df.loc[fut_idx, "real_earnings_10y_avg"]
    c0, c1 = df.loc[peak_idx, "cape"], df.loc[fut_idx, "cape"]
    # Window from peak to target for drawdown
    win = df.loc[peak_idx:fut_idx, "real_price"]
    trough_idx = win.idxmin()
    trough_dd = win.loc[trough_idx] / p0 - 1.0
    return {
        f"h{horizon_years}_end_date": df.loc[fut_idx, "date"],
        f"h{horizon_years}_real_price_ret": p1 / p0 - 1.0,
        f"h{horizon_years}_real_e10_growth": e1 / e0 - 1.0,
        f"h{horizon_years}_cape_change": c1 / c0 - 1.0,
        f"h{horizon_years}_end_cape": c1,
        f"h{horizon_years}_max_drawdown": trough_dd,
        f"h{horizon_years}_trough_date": df.loc[trough_idx, "date"],
    }


def classify(price_ret: float, e10_growth: float) -> str:
    """Classify the mechanism of CAPE reversion over the horizon."""
    if pd.isna(price_ret) or pd.isna(e10_growth):
        return "incomplete"
    log_p = np.log1p(price_ret)
    log_e = np.log1p(e10_growth)
    cape_log_change = log_p - log_e
    if cape_log_change >= 0:
        return "no_reversion"
    # CAPE fell. Attribute.
    crashed = price_ret <= CRASH_PRICE_DROP
    earnings_grew = e10_growth >= EARNINGS_GROWTH_HURDLE
    # Share of absolute log change attributable to price decline vs earnings growth
    price_contrib = max(-log_p, 0.0)   # positive when price fell
    earn_contrib = max(log_e, 0.0)     # positive when earnings grew
    total = price_contrib + earn_contrib
    price_share = price_contrib / total if total > 0 else 0.0
    if crashed and price_share >= 0.6:
        return "crash_driven"
    if earnings_grew and not crashed and price_share < 0.4:
        return "earnings_driven"
    return "mixed"


def build_episode_table(df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    eps = find_episodes(df, threshold)
    rows = []
    for _, ep in eps.iterrows():
        row = ep.to_dict()
        for h in HORIZONS_YEARS:
            row.update(forward_metrics(df, int(ep["peak_idx"]), h))
        # Classify based on the 10-year window (the natural CAPE horizon)
        row["mechanism_10y"] = classify(
            row.get("h10_real_price_ret", np.nan),
            row.get("h10_real_e10_growth", np.nan),
        )
        row["mechanism_5y"] = classify(
            row.get("h5_real_price_ret", np.nan),
            row.get("h5_real_e10_growth", np.nan),
        )
        rows.append(row)
    return pd.DataFrame(rows)


def summarise(eps: pd.DataFrame, threshold: float) -> dict:
    """Aggregate stats for the analysis writeup."""
    s = {"threshold": threshold, "n_episodes": len(eps)}
    for h in HORIZONS_YEARS:
        c = f"h{h}_real_price_ret"
        e = f"h{h}_real_e10_growth"
        d = f"h{h}_max_drawdown"
        valid = eps.dropna(subset=[c, e, d])
        s[f"h{h}_n"] = len(valid)
        if len(valid):
            s[f"h{h}_median_real_price_ret"] = valid[c].median()
            s[f"h{h}_median_e10_growth"] = valid[e].median()
            s[f"h{h}_median_max_dd"] = valid[d].median()
            s[f"h{h}_pct_with_20dd"] = (valid[d] <= -0.20).mean()
            s[f"h{h}_pct_negative_real"] = (valid[c] < 0).mean()
    mech = eps["mechanism_10y"].value_counts().to_dict()
    s["mechanism_10y_counts"] = mech
    return s


def main() -> int:
    df = load()
    print(f"Loaded {len(df):,} months from {df['date'].min().date()} to {df['date'].max().date()}")

    summaries = []
    for thr in THRESHOLDS:
        eps = build_episode_table(df, thr)
        out_csv = OUT_DIR / f"episodes_cape_ge_{int(thr)}.csv"
        eps.to_csv(out_csv, index=False)
        print(f"\nThreshold CAPE >= {thr}: {len(eps)} episodes -> {out_csv.name}")
        s = summarise(eps, thr)
        summaries.append(s)
        # Print concise per-episode view
        cols_show = ["peak_date", "peak_cape",
                     "h5_real_price_ret", "h5_real_e10_growth", "h5_max_drawdown", "mechanism_5y",
                     "h10_real_price_ret", "h10_real_e10_growth", "h10_max_drawdown", "mechanism_10y"]
        existing = [c for c in cols_show if c in eps.columns]
        print(eps[existing].to_string(index=False))

    summary_df = pd.DataFrame([{k: v for k, v in s.items() if not isinstance(v, dict)} for s in summaries])
    summary_df.to_csv(OUT_DIR / "summary_stats.csv", index=False)
    # Save mechanism counts separately as JSON-friendly
    import json
    mech_path = OUT_DIR / "mechanism_counts.json"
    mech_path.write_text(json.dumps(
        {f"cape_ge_{int(s['threshold'])}": s["mechanism_10y_counts"] for s in summaries},
        indent=2, default=str,
    ))
    print("\nSaved summary_stats.csv and mechanism_counts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
