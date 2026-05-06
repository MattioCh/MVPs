"""Parse Shiller's ie_data.xls into a clean monthly DataFrame.

Columns of interest in the raw 'Data' sheet (0-indexed):
  0  Date (YYYY.MM as a float)
  1  P     - nominal S&P Composite price
  2  D     - nominal dividend (annualized)
  3  E     - nominal earnings (annualized)
  4  CPI
  6  GS10  - long interest rate
  7  Real Price
  10 Real Earnings
  12 CAPE  - cyclically-adjusted P/E (price / 10-yr avg real earnings)
  16 Excess CAPE Yield
  19 Forward 10y annualized real stock return (already provided by Shiller)

Output: data/shiller_clean.csv  (one row per month)
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "ie_data.xls"
OUT = ROOT / "data" / "shiller_clean.csv"


def parse_date(date_float: float) -> pd.Timestamp | pd.NaT:
    """Shiller stores dates as YYYY.MM where 1871.10 means October 1871
    (NOT 1871 + 0.10). So 1871.1 == 1871.10. Multiply by 100 then split."""
    if pd.isna(date_float):
        return pd.NaT
    s = f"{date_float:.4f}"  # e.g. '1871.1000'
    year_str, frac_str = s.split(".")
    # Month is encoded in the first two digits of the fractional part.
    # 1871.10 -> '1000' -> month 10. 1871.01 -> '0100' -> month 01.
    month = int(frac_str[:2])
    return pd.Timestamp(year=int(year_str), month=month, day=1)


def main() -> int:
    raw = pd.read_excel(RAW, sheet_name="Data", header=None)
    # Data rows start at index 8 (after multi-row header).
    data = raw.iloc[8:].reset_index(drop=True)
    df = pd.DataFrame({
        "date_raw": pd.to_numeric(data[0], errors="coerce"),
        "price": pd.to_numeric(data[1], errors="coerce"),
        "dividend": pd.to_numeric(data[2], errors="coerce"),
        "earnings": pd.to_numeric(data[3], errors="coerce"),
        "cpi": pd.to_numeric(data[4], errors="coerce"),
        "gs10": pd.to_numeric(data[6], errors="coerce"),
        "real_price": pd.to_numeric(data[7], errors="coerce"),
        "real_earnings": pd.to_numeric(data[10], errors="coerce"),
        "cape": pd.to_numeric(data[12], errors="coerce"),
    })
    df = df.dropna(subset=["date_raw"]).copy()
    df["date"] = df["date_raw"].apply(parse_date)
    df = df.dropna(subset=["date", "price"]).drop(columns=["date_raw"])
    df = df.sort_values("date").reset_index(drop=True)

    # Trailing twelve-month nominal earnings. Shiller's E column is reported
    # as an annualized TTM figure, so we use it directly. PE_ttm = P / E.
    df["pe_ttm"] = df["price"] / df["earnings"]

    # Real (CPI-adjusted) earnings used in CAPE denominator
    df["real_earnings_10y_avg"] = df["real_earnings"].rolling(120, min_periods=120).mean()
    # Sanity check: our CAPE recomputation should match Shiller's column.
    df["cape_check"] = df["real_price"] / df["real_earnings_10y_avg"]

    df.to_csv(OUT, index=False)
    print(f"Wrote {OUT}: {len(df):,} monthly rows from {df['date'].min().date()} to {df['date'].max().date()}")
    # Quick parity check
    diff = (df["cape"] - df["cape_check"]).abs().dropna()
    print(f"CAPE recompute max abs diff vs Shiller column: {diff.max():.4f}  (median {diff.median():.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
