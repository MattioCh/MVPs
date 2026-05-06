"""
ipo_adjustment.py
=================

Question (from user):
  Several large private AI cos (SpaceX, OpenAI, Anthropic, xAI ...) may IPO
  soon. Pre-IPO, their revenue isn't in the S&P 500 P/E. Could including
  them — or recognising that S&P 500 cos already own large stakes in them
  — meaningfully bring the elevated S&P 500 P/E down?

Method:
  1. Anchor: current S&P 500 aggregate market cap and TTM earnings
     (from public sources, May 2026).
  2. Build three scenarios:
     a) BASE          — current S&P 500 as-is.
     b) FULL_INCLUSION — pretend the private AI cos are *already* in the
        index at their last-round valuation, with their last-reported
        net income added to aggregate earnings.
     c) LOOKTHROUGH    — only the *unowned* portion of each private co
        is added (since the part already held by an S&P 500 co is, in
        principle, already priced into the holder's market cap and its
        earnings flow through equity-method accounting).
  3. Recompute aggregate P/E under each scenario, plus Shiller-style
     CAPE-equivalent stress (assume long-run earnings 25% below TTM,
     i.e. cyclically adjusted).

Run:
  uv run python scripts/ipo_adjustment.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Macro anchors (sourced May 2026; see IPO_ADJUSTMENT.md for citations)
# ---------------------------------------------------------------------------

SP500_MARKET_CAP_USD_B = 61_100.0   # $61.1T, 31-Dec-2025 (S&P DJI)
SP500_PE_TTM = 30.96                # multpl.com, May 2026
SP500_CAPE = 40.90                  # multpl.com, May 2026
SP500_TTM_EARNINGS_USD_B = SP500_MARKET_CAP_USD_B / SP500_PE_TTM  # ~$1,973B

# Cyclically-adjusted ("normalised") earnings = price / CAPE, using the
# same market cap denominator. This is what CAPE implicitly assumes are
# the "true" earnings power once you smooth over a cycle.
SP500_CAPE_EARNINGS_USD_B = SP500_MARKET_CAP_USD_B / SP500_CAPE  # ~$1,494B


def main() -> None:
    privates = pd.read_csv(DATA / "private_ai_companies.csv")
    stakes = pd.read_csv(DATA / "sp500_holder_stakes.csv")

    # Total stake already held by S&P 500 cos in each private co.
    stake_total = (
        stakes.groupby("investee")["stake_pct"].sum().rename("sp500_held_pct")
    )
    privates = privates.merge(
        stake_total, left_on="name", right_index=True, how="left"
    )
    privates["sp500_held_pct"] = privates["sp500_held_pct"].fillna(0.0)
    privates["unowned_pct"] = 100.0 - privates["sp500_held_pct"]

    # Look-through additions: only the % NOT already held by S&P 500 cos.
    privates["lookthrough_value_b"] = (
        privates["latest_valuation_usd_b"] * privates["unowned_pct"] / 100.0
    )
    privates["lookthrough_earnings_b"] = (
        privates["net_income_usd_b"] * privates["unowned_pct"] / 100.0
    )
    privates["lookthrough_revenue_b"] = (
        privates["latest_revenue_usd_b"] * privates["unowned_pct"] / 100.0
    )

    print("\n=== Private AI co inputs ===")
    cols = [
        "name",
        "latest_valuation_usd_b",
        "latest_revenue_usd_b",
        "net_income_usd_b",
        "sp500_held_pct",
        "lookthrough_value_b",
        "lookthrough_earnings_b",
    ]
    print(privates[cols].to_string(index=False))

    # ---------------------------------------------------------------
    # Scenarios
    # ---------------------------------------------------------------
    base = {
        "scenario": "BASE",
        "market_cap_usd_b": SP500_MARKET_CAP_USD_B,
        "ttm_earnings_usd_b": SP500_TTM_EARNINGS_USD_B,
        "cape_earnings_usd_b": SP500_CAPE_EARNINGS_USD_B,
        "added_revenue_usd_b": 0.0,
    }
    full = {
        "scenario": "FULL_INCLUSION",
        "market_cap_usd_b": SP500_MARKET_CAP_USD_B
        + privates["latest_valuation_usd_b"].sum(),
        "ttm_earnings_usd_b": SP500_TTM_EARNINGS_USD_B
        + privates["net_income_usd_b"].sum(),
        # Cape-equivalent: earnings hit grows 1:1 since these cos have no
        # 10y history; treat their net income as their cyclically-adjusted
        # earnings (charitable assumption).
        "cape_earnings_usd_b": SP500_CAPE_EARNINGS_USD_B
        + privates["net_income_usd_b"].sum(),
        "added_revenue_usd_b": privates["latest_revenue_usd_b"].sum(),
    }
    lookthrough = {
        "scenario": "LOOKTHROUGH",
        "market_cap_usd_b": SP500_MARKET_CAP_USD_B
        + privates["lookthrough_value_b"].sum(),
        "ttm_earnings_usd_b": SP500_TTM_EARNINGS_USD_B
        + privates["lookthrough_earnings_b"].sum(),
        "cape_earnings_usd_b": SP500_CAPE_EARNINGS_USD_B
        + privates["lookthrough_earnings_b"].sum(),
        "added_revenue_usd_b": privates["lookthrough_revenue_b"].sum(),
    }

    rows = []
    for sc in (base, full, lookthrough):
        sc["pe_ttm_adj"] = sc["market_cap_usd_b"] / sc["ttm_earnings_usd_b"]
        sc["cape_adj"] = sc["market_cap_usd_b"] / sc["cape_earnings_usd_b"]
        rows.append(sc)
    out = pd.DataFrame(rows)

    print("\n=== Scenario results ===")
    print(out.to_string(index=False))

    out.to_csv(OUT / "ipo_scenarios.csv", index=False)
    privates.to_csv(OUT / "private_ai_with_stakes.csv", index=False)

    # ---------------------------------------------------------------
    # Bull-case stress: what if these cos were valued at *future*
    # profitability instead of current losses? Assume 20% net margin on
    # current revenue (mature SaaS-like). This is the most generous case.
    # ---------------------------------------------------------------
    bull_added_earnings = (privates["latest_revenue_usd_b"] * 0.20).sum()
    bull_pe = (
        SP500_MARKET_CAP_USD_B + privates["latest_valuation_usd_b"].sum()
    ) / (SP500_TTM_EARNINGS_USD_B + bull_added_earnings)
    print(
        f"\nBull case (20% margin on private-co revenue): "
        f"PE_TTM = {bull_pe:.2f} "
        f"(vs base {SP500_PE_TTM:.2f})"
    )

    # ---------------------------------------------------------------
    # Sensitivity: how much *aggregate* extra earnings would the index
    # need to bring TTM P/E from 30.96 down to its long-run mean of 16?
    # ---------------------------------------------------------------
    target_pe = 16.0
    needed_earnings = SP500_MARKET_CAP_USD_B / target_pe
    earnings_gap = needed_earnings - SP500_TTM_EARNINGS_USD_B
    print(
        f"\nTo reach long-run mean P/E of {target_pe}: "
        f"need ${needed_earnings:,.0f}B of earnings "
        f"(+${earnings_gap:,.0f}B vs current ${SP500_TTM_EARNINGS_USD_B:,.0f}B)"
    )
    print(
        f"That is +{earnings_gap / SP500_TTM_EARNINGS_USD_B * 100:.0f}% growth "
        "in aggregate S&P 500 earnings."
    )

    summary = {
        "anchors": {
            "sp500_market_cap_usd_b": SP500_MARKET_CAP_USD_B,
            "sp500_pe_ttm": SP500_PE_TTM,
            "sp500_cape": SP500_CAPE,
            "sp500_ttm_earnings_usd_b": SP500_TTM_EARNINGS_USD_B,
        },
        "scenarios": rows,
        "bull_case_pe_ttm": bull_pe,
        "earnings_gap_to_mean_pe_usd_b": earnings_gap,
        "earnings_growth_needed_pct": earnings_gap
        / SP500_TTM_EARNINGS_USD_B
        * 100,
    }
    with (OUT / "ipo_summary.json").open("w") as f:
        json.dump(summary, f, indent=2, default=float)


if __name__ == "__main__":
    main()
