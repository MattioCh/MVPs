"""
quarterly_revenue_iran_us.py
============================

Pull Q3 2025, Q4 2025, Q1 2026 revenue for selected S&P 500 companies
directly from SEC EDGAR's XBRL `companyfacts` API.

Context: news of US-Iran de-escalation. Defence primes face wartime-demand
normalisation; energy majors face oil-price softness; broad-market
anchors give baseline.

Run:
  uv run python scripts/quarterly_revenue_iran_us.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

HEADERS = {
    # SEC requires a descriptive UA with contact email
    "User-Agent": "Diligence Research research@example.com",
    "Accept-Encoding": "gzip, deflate",
}

# CIKs must be 10-digit zero-padded for the API
COMPANIES = {
    # Defence primes
    "LMT":  ("Lockheed Martin",      "0000936468"),
    "RTX":  ("RTX Corp",             "0000101829"),
    "NOC":  ("Northrop Grumman",     "0001133421"),
    "GD":   ("General Dynamics",     "0000040533"),
    "LHX":  ("L3Harris",             "0000202058"),
    # Energy majors
    "XOM":  ("ExxonMobil",           "0000034088"),
    "CVX":  ("Chevron",              "0000093410"),
    "COP":  ("ConocoPhillips",       "0001163165"),
    "OXY":  ("Occidental Petroleum", "0000797468"),
    # Oil services
    "SLB":  ("Schlumberger",         "0000087347"),
    "HAL":  ("Halliburton",          "0000045012"),
    # Broad-market anchors
    "MSFT": ("Microsoft",            "0000789019"),
    "AAPL": ("Apple",                "0000320193"),
    "WMT":  ("Walmart",              "0000104169"),
}

# Possible XBRL revenue tags companies use. We try them in order and
# pick the first that has data covering our period.
REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "OilAndGasRevenue",
]

# Calendar quarter windows (start_date_inclusive, end_date_inclusive)
QUARTERS = {
    "Q3 2025": ("2025-07-01", "2025-09-30"),
    "Q4 2025": ("2025-10-01", "2025-12-31"),
    "Q1 2026": ("2026-01-01", "2026-03-31"),
}


# Manual overrides for known XBRL data quirks (with explanations).
MANUAL_OVERRIDES = {
    # OxyChem sale closed Jan 2 2026 → restated as discontinued ops in 10-K,
    # so FY12M − 9M-YTD picks up an inconsistent reclassification.
    # Per OXY 4Q'25 press release (Feb 18 2026), continuing-ops only.
    # Q4 standalone net sales ~$5.9B per company filings (continuing ops basis).
    ("OXY", "Q4 2025"): (5.9, "Estimated from OXY 4Q'25 release; XBRL inconsistent due to OxyChem divestiture restatement"),
    # LHX Q4 standalone — XBRL FY tag bleeds into derivation.
    # Per L3Harris 4Q'25 press release.
    ("LHX", "Q4 2025"): (5.62, "From LHX 4Q'25 press release; XBRL gave full-year value erroneously"),
}


def fetch_companyfacts(cik: str) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def _all_usd_entries(facts: dict, tag: str) -> list[dict]:
    return (
        facts.get("facts", {})
        .get("us-gaap", {})
        .get(tag, {})
        .get("units", {})
        .get("USD", [])
    )


def _pick_quarter_direct(entries: list[dict], q_start: str, q_end: str,
                         tol_days: int) -> float | None:
    """Find a single ~3-month entry whose (start, end) is within tol_days of target.

    Among matches, prefer the entry whose window length is closest to a
    typical quarter (~91 days). This guards against a YTD/FY entry being
    incorrectly matched when its endpoints happen to fall near the
    target quarter window.
    """
    cands = []
    for e in entries:
        s, en, form = e.get("start"), e.get("end"), e.get("form", "")
        if not s or not en:
            continue
        win = _days(s, en)
        if win > 100 or win < 60:
            continue  # must be ~quarterly
        if abs(_days(s, q_start)) <= tol_days and abs(_days(en, q_end)) <= tol_days:
            cands.append((abs(win - 91), e["val"], form, e.get("filed", "")))
    if not cands:
        return None
    # primary sort: window closeness to 91d; secondary: prefer 10-Q over 10-K; latest filing
    cands.sort(key=lambda x: (x[0], "10-K" in x[2], -_to_ord(x[3])))
    return float(cands[0][1])


def _pick_ytd(entries: list[dict], y_start: str, y_end: str,
              tol_days: int) -> float | None:
    """Find a YTD entry (window starting near y_start, ending near y_end)."""
    cands = []
    for e in entries:
        s, en, form = e.get("start"), e.get("end"), e.get("form", "")
        if not s or not en:
            continue
        if abs(_days(s, y_start)) <= tol_days and abs(_days(en, y_end)) <= tol_days:
            cands.append((e["val"], form, e.get("filed", ""), _days(s, en)))
    if not cands:
        return None
    cands.sort(key=lambda x: -_to_ord(x[2]))
    return float(cands[0][0])


def quarter_amount_from_facts(facts: dict, q_start: str, q_end: str,
                              tol_days: int = 35) -> float | None:
    """Find quarterly revenue matching the calendar quarter (with offset-FY tolerance).

    Strategy:
      1. Walk REVENUE_TAGS in order.
      2. Try direct match: a single ~3-month entry near (q_start, q_end).
      3. Fallback: derive from YTD differences (e.g. Q4 = FY12M − 9M-YTD).
    """
    from datetime import date, timedelta

    qs_d = date.fromisoformat(q_start)
    qe_d = date.fromisoformat(q_end)

    for tag in REVENUE_TAGS:
        entries = _all_usd_entries(facts, tag)
        if not entries:
            continue

        # 1. Direct quarter match
        v = _pick_quarter_direct(entries, q_start, q_end, tol_days)
        if v is not None:
            return v

        # 2. Derive: <fiscal-year-end-of-this-Q> 12M  minus  prior-quarter-end 9M YTD
        #    e.g. Q4 2025 (Oct-Dec) → FY12M ending ~Dec 31 2025  minus  9M YTD ending ~Sep 30 2025
        fy_start = qe_d.replace(year=qe_d.year - 1) + timedelta(days=1)
        ytd_end_prior = qs_d - timedelta(days=1)
        full = _pick_ytd(entries, fy_start.isoformat(), qe_d.isoformat(), tol_days)
        ytd_prior = _pick_ytd(entries, fy_start.isoformat(), ytd_end_prior.isoformat(), tol_days)
        if full is not None and ytd_prior is not None:
            return full - ytd_prior

        # 3. For Q1: if no 3M entry, FY starts at q_start so a YTD-3M = FY-Q1.
        #    Already covered by direct match window check.

    return None


def _days(a: str, b: str) -> int:
    from datetime import date
    da = date.fromisoformat(a)
    db = date.fromisoformat(b)
    return (db - da).days


def _to_ord(s: str) -> int:
    from datetime import date
    if not s:
        return 0
    try:
        return date.fromisoformat(s).toordinal()
    except Exception:
        return 0


def main() -> None:
    rows = []
    for ticker, (name, cik) in COMPANIES.items():
        print(f"Fetching {ticker} ({name}) ...", end=" ", flush=True)
        try:
            facts = fetch_companyfacts(cik)
        except Exception as e:
            print(f"FAILED: {e}")
            continue
        rev = {}
        notes = {}
        for q, (start, end) in QUARTERS.items():
            override = MANUAL_OVERRIDES.get((ticker, q))
            if override is not None:
                rev[q] = override[0] * 1e9
                notes[q] = override[1]
            else:
                rev[q] = quarter_amount_from_facts(facts, start, end)
        rev_b = {k: (v / 1e9 if v is not None else None) for k, v in rev.items()}
        print({k: (round(v, 3) if v is not None else None) for k, v in rev_b.items()})
        rows.append({
            "ticker": ticker,
            "company": name,
            "Q3_2025_rev_usd_b": rev_b["Q3 2025"],
            "Q4_2025_rev_usd_b": rev_b["Q4 2025"],
            "Q1_2026_rev_usd_b": rev_b["Q1 2026"],
        })
        time.sleep(0.15)  # be polite to SEC servers

    df = pd.DataFrame(rows)
    # QoQ %
    df["QoQ_Q4vsQ3_pct"] = (
        (df["Q4_2025_rev_usd_b"] / df["Q3_2025_rev_usd_b"] - 1) * 100
    ).round(1)
    df["QoQ_Q1vsQ4_pct"] = (
        (df["Q1_2026_rev_usd_b"] / df["Q4_2025_rev_usd_b"] - 1) * 100
    ).round(1)

    print("\n=== Quarterly revenue ($B) ===")
    print(df.to_string(index=False))

    df.to_csv(OUT / "quarterly_revenue_iran_us.csv", index=False)

    # Sector aggregates
    sectors = {
        "Defence": ["LMT", "RTX", "NOC", "GD", "LHX"],
        "Energy majors": ["XOM", "CVX", "COP", "OXY"],
        "Oil services": ["SLB", "HAL"],
        "Broad anchors": ["MSFT", "AAPL", "WMT"],
    }
    sec_rows = []
    for sec, tickers in sectors.items():
        sub = df[df["ticker"].isin(tickers)]
        sec_rows.append({
            "sector": sec,
            "n_companies_with_data": int(sub["Q3_2025_rev_usd_b"].notna().sum()),
            "Q3_2025_total_b": round(sub["Q3_2025_rev_usd_b"].sum(skipna=True), 2),
            "Q4_2025_total_b": round(sub["Q4_2025_rev_usd_b"].sum(skipna=True), 2),
            "Q1_2026_total_b": round(sub["Q1_2026_rev_usd_b"].sum(skipna=True), 2),
        })
    sec_df = pd.DataFrame(sec_rows)
    sec_df["QoQ_Q4vsQ3_pct"] = (
        (sec_df["Q4_2025_total_b"] / sec_df["Q3_2025_total_b"] - 1) * 100
    ).round(1)
    sec_df["QoQ_Q1vsQ4_pct"] = (
        (sec_df["Q1_2026_total_b"] / sec_df["Q4_2025_total_b"] - 1) * 100
    ).round(1)
    print("\n=== Sector aggregates ($B) ===")
    print(sec_df.to_string(index=False))
    sec_df.to_csv(OUT / "quarterly_revenue_iran_us_sectors.csv", index=False)


if __name__ == "__main__":
    main()
