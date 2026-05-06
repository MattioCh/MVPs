"""
event_momentum.py
=================

Boss's hypothesis: macro events generate ~1-2 month of momentum in the
broad market. Test it.

Method:
  1. Load labeled macro events from data/macro_events.csv.
  2. Fetch S&P 500 daily prices (^SPX) from Stooq (free, no API key).
  3. For each event date, compute forward returns at T+5d, T+21d (~1mo),
     T+42d (~2mo), T+63d (~3mo) trading days.
  4. Compare event-conditional means to the **unconditional base rate**
     over the same period (any random day).
  5. Sign-adjust by direction_prior so positive = "moved as expected".
  6. Report per-event, per-category, and aggregate.

Run:
  uv run python scripts/event_momentum.py
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

HORIZONS = {"T+5d": 5, "T+21d (~1mo)": 21, "T+42d (~2mo)": 42, "T+63d (~3mo)": 63}


def fetch_spx() -> pd.DataFrame:
    """Daily S&P 500 from yfinance (^GSPC)."""
    import yfinance as yf
    df = yf.download("^GSPC", start="2015-01-01", progress=False, auto_adjust=False)
    if df.empty:
        raise RuntimeError("yfinance returned no data for ^GSPC")
    # yfinance returns multiindex columns when single ticker — flatten
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.reset_index().rename(columns={"Date": "date", "Close": "close"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["log_ret"] = np.log(df["close"]).diff()
    return df[["date", "close", "log_ret"]]


def forward_log_return(prices: pd.DataFrame, event_date: pd.Timestamp,
                       n_trading_days: int) -> float | None:
    """Log return from the close on/after event_date through n trading days later."""
    after = prices[prices["date"] >= event_date].reset_index(drop=True)
    if len(after) <= n_trading_days:
        return None
    p0 = after["close"].iloc[0]
    pT = after["close"].iloc[n_trading_days]
    return float(np.log(pT / p0))


def main() -> None:
    print("Fetching S&P 500 from yfinance ...")
    spx = fetch_spx()
    print(f"  {len(spx):,} rows, {spx['date'].min().date()} -> {spx['date'].max().date()}")

    events = pd.read_csv(DATA / "macro_events.csv")
    events["date"] = pd.to_datetime(events["date"])

    # Limit to events with enough forward window data
    last = spx["date"].max()
    events_usable = events[events["date"] + pd.Timedelta(days=120) <= last].copy()
    dropped = len(events) - len(events_usable)
    if dropped:
        print(f"  Dropping {dropped} event(s) with insufficient forward data:")
        print(events.loc[~events.index.isin(events_usable.index), ["date", "event"]].to_string(index=False))

    # ---- Event-conditional forward returns ----
    rows = []
    for _, e in events_usable.iterrows():
        row = {"date": e["date"].date(), "event": e["event"], "category": e["category"],
               "direction_prior": e["direction_prior"]}
        for label, h in HORIZONS.items():
            row[label] = forward_log_return(spx, e["date"], h)
        rows.append(row)
    ev_df = pd.DataFrame(rows)

    # Sign-adjust: multiply by +1 if prior=positive, -1 if negative,
    # leave NaN for ambiguous (not used in directional aggregate).
    sign_map = {"positive": 1.0, "negative": -1.0, "ambiguous": np.nan}
    ev_df["sign"] = ev_df["direction_prior"].map(sign_map)
    for label in HORIZONS:
        ev_df[f"{label}_signed"] = ev_df[label] * ev_df["sign"]

    # ---- Unconditional base rate over same date range ----
    spx_in_range = spx[(spx["date"] >= events["date"].min())
                       & (spx["date"] <= last)].copy()
    base = {}
    for label, h in HORIZONS.items():
        # rolling forward log return of h trading days
        spx_in_range[f"fwd_{h}"] = (
            np.log(spx_in_range["close"]).shift(-h) - np.log(spx_in_range["close"])
        )
        base[label] = {
            "mean": spx_in_range[f"fwd_{h}"].mean(),
            "median": spx_in_range[f"fwd_{h}"].median(),
            "std": spx_in_range[f"fwd_{h}"].std(),
            "pct_positive": (spx_in_range[f"fwd_{h}"] > 0).mean(),
        }

    # ---- Per-event print ----
    print("\n=== Per-event forward log returns (raw, in %) ===")
    pretty = ev_df.copy()
    for label in HORIZONS:
        pretty[label] = (pretty[label] * 100).round(2)
    print(pretty[["date", "event", "category", *HORIZONS]].to_string(index=False))

    # ---- Aggregates ----
    print("\n=== Unconditional base rate (any random day, same period) ===")
    base_df = pd.DataFrame(base).T
    base_df_pct = (base_df[["mean", "median", "std"]] * 100).round(2)
    base_df_pct["pct_positive"] = (base_df["pct_positive"] * 100).round(1)
    print(base_df_pct.to_string())

    # Directional (signed) aggregate — does the market move IN the
    # direction the event would imply, on average?
    print("\n=== Directional test: mean SIGNED return after events (in %) ===")
    print("(positive = market moved as the event's prior would imply)")
    signed_cols = [f"{l}_signed" for l in HORIZONS]
    directional = ev_df[ev_df["sign"].notna()]
    agg = pd.DataFrame({
        "n_events": [directional[c].notna().sum() for c in signed_cols],
        "mean_signed_%": [(directional[c].mean() * 100) for c in signed_cols],
        "median_signed_%": [(directional[c].median() * 100) for c in signed_cols],
        "pct_in_predicted_dir": [(directional[c] > 0).mean() * 100 for c in signed_cols],
    }, index=list(HORIZONS.keys()))
    print(agg.round(2).to_string())

    # Raw (unsigned) aggregate per category
    print("\n=== Mean raw return by category (in %) ===")
    cat_agg = ev_df.groupby("category")[list(HORIZONS.keys())].mean() * 100
    print(cat_agg.round(2).to_string())

    # Hit-rate vs base: did 1mo/2mo conditional return beat unconditional in absolute magnitude?
    print("\n=== Excess movement vs baseline (|event return| - |base mean|, in %) ===")
    excess_rows = []
    for label in HORIZONS:
        evs = ev_df[label].dropna()
        excess_rows.append({
            "horizon": label,
            "mean_|event|_%": (evs.abs().mean() * 100),
            "mean_|base|_%": (abs(base[label]["mean"]) * 100),
            "event_std_%": (evs.std() * 100),
            "base_std_%": (base[label]["std"] * 100),
        })
    print(pd.DataFrame(excess_rows).round(2).to_string(index=False))

    # Save
    ev_df.to_csv(OUT / "event_momentum_per_event.csv", index=False)
    agg.to_csv(OUT / "event_momentum_directional.csv")
    cat_agg.to_csv(OUT / "event_momentum_by_category.csv")
    print(f"\nSaved -> {OUT}")


if __name__ == "__main__":
    main()
