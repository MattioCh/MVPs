"""
spx_options.py
==============
Retrieve S&P 500 (SPX) daily option chain data from Yahoo Finance via yfinance.

Yahoo Finance provides full SPX option chains (calls and puts) for each available
expiration date. This script fetches those chains with rate-limit handling and
saves timestamped CSV snapshots.

Usage
-----
    uv run python scripts/spx_options.py                          # fetch ALL expirations
    uv run python scripts/spx_options.py --expiration 2026-05-15  # single expiration
    uv run python scripts/spx_options.py --expiration 2026-05-15,2026-05-22
    uv run python scripts/spx_options.py --list                   # list available expirations
    uv run python scripts/spx_options.py --delay 2.0              # custom delay between calls

Output
------
Timestamped snapshot directories under output/spx_options_YYYYMMDD_HHMMSS/:
    calls_YYYY-MM-DD.csv   — calls for that expiry
    puts_YYYY-MM-DD.csv    — puts for that expiry
    manifest.csv           — summary of all fetched expirations

Columns per CSV
---------------
strike, lastPrice, bid, ask, volume, openInterest, impliedVolatility
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Paths (follow project convention)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
DELAY_BETWEEN_CALLS = 1.0          # seconds between option-chain fetches
MAX_RETRIES = 3                    # attempts on rate-limit / transient errors
RETRY_BACKOFF_BASE = 5.0           # seconds base backoff (scales exponentially)

# The seven columns we keep from yfinance's chain DataFrames
CHAIN_COLUMNS = [
    "strike",
    "lastPrice",
    "bid",
    "ask",
    "volume",
    "openInterest",
    "impliedVolatility",
]


# ---------------------------------------------------------------------------
# Core API helpers
# ---------------------------------------------------------------------------


def _get_ticker() -> yf.Ticker:
    """Return a yfinance Ticker for the S&P 500 index (^SPX)."""
    return yf.Ticker("^SPX")


def get_all_expirations() -> list[str]:
    """Return all available SPX option expiration dates (YYYY-MM-DD strings)."""
    spx = _get_ticker()
    expirations: list[str] = spx.options
    if not expirations:
        raise RuntimeError(
            "No option expiration dates returned for ^SPX. "
            "Yahoo Finance may be throttling or SPX options data is unavailable."
        )
    return expirations


def fetch_option_chain(expiration_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch the full option chain for a single expiration date.

    Parameters
    ----------
    expiration_date : str
        Expiration in YYYY-MM-DD format (must be among ``get_all_expirations()``).

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        (calls_df, puts_df) — each with columns:
        strike, lastPrice, bid, ask, volume, openInterest, impliedVolatility

    Raises
    ------
    RuntimeError
        If the call to yfinance fails after all retries.
    """
    spx = _get_ticker()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chain = spx.option_chain(expiration_date)
            calls = chain.calls[CHAIN_COLUMNS].copy()
            puts = chain.puts[CHAIN_COLUMNS].copy()
            return calls, puts
        except Exception as exc:
            msg = str(exc).lower()
            is_throttle = any(kw in msg for kw in (
                "too many", "rate limit", "429", "throttl",
                "retrieval", "connection", "timeout",
            ))
            if attempt < MAX_RETRIES and is_throttle:
                wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                print(
                    f"  [WARN] Throttled on {expiration_date} "
                    f"(attempt {attempt}/{MAX_RETRIES}), waiting {wait:.0f}s ...",
                    file=sys.stderr,
                )
                time.sleep(wait)
            elif attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE
                print(
                    f"  [WARN] Error fetching {expiration_date}: {exc} "
                    f"(attempt {attempt}/{MAX_RETRIES}), waiting {wait:.0f}s ...",
                    file=sys.stderr,
                )
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Failed to fetch option chain for expiration {expiration_date} "
                    f"after {MAX_RETRIES} attempts: {exc}"
                ) from exc

    raise RuntimeError(f"Unexpected: exhausted retries for {expiration_date}")

def fetch_all_chains(
    expirations: list[str] | None = None,
    delay: float = DELAY_BETWEEN_CALLS,
) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    """Fetch option chains for all (or a subset of) expirations.

    Parameters
    ----------
    expirations : list[str] | None
        Expiration dates to fetch. If None, fetches all available.
    delay : float
        Seconds to sleep between consecutive fetches (rate-limiting courtesy).

    Returns
    -------
    dict[str, tuple[pd.DataFrame, pd.DataFrame]]
        Map of expiration_date → (calls_df, puts_df).
        Failed expirations are **skipped** (logged to stderr).
    """
    if expirations is None:
        expirations = get_all_expirations()

    print(
        f"Fetching option chains for {len(expirations)} expiration(s) "
        f"with {delay}s delay between calls ..."
    )

    results: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    succeeded = 0
    failed = 0

    for i, exp in enumerate(expirations, start=1):
        print(f"  [{i:>3}/{len(expirations)}] {exp} ...", end=" ", flush=True)
        try:
            calls, puts = fetch_option_chain(exp)
            results[exp] = (calls, puts)
            print(f"OK  (calls: {len(calls)}, puts: {len(puts)})")
            succeeded += 1
        except RuntimeError as exc:
            print(f"FAILED — {exc}", file=sys.stderr)
            failed += 1

        # Don't sleep after the last one
        if i < len(expirations):
            time.sleep(delay)

    print(f"\nDone: {succeeded} succeeded, {failed} failed")
    return results


# ---------------------------------------------------------------------------
# Snapshot save
# ---------------------------------------------------------------------------


def save_snapshot(
    chains: dict[str, tuple[pd.DataFrame, pd.DataFrame]],
    output_dir: Path | None = None,
) -> Path:
    """Save a full option-chain snapshot as timestamped CSV files.

    Creates a directory ``output/spx_options_YYYYMMDD_HHMMSS/`` containing:

    * ``calls_YYYY-MM-DD.csv`` / ``puts_YYYY-MM-DD.csv`` for each expiration
    * ``manifest.csv`` — summary of all fetched expirations with row counts

    Parameters
    ----------
    chains : dict
        Map from expiration_date → (calls_df, puts_df) as returned by
        ``fetch_all_chains()``.
    output_dir : Path | None
        Parent directory for the timestamped snapshot folder.
        Defaults to ``output/``.

    Returns
    -------
    Path
        The created snapshot directory.
    """
    if output_dir is None:
        output_dir = OUT

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap_dir = output_dir / f"spx_options_{timestamp}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict] = []

    for exp, (calls, puts) in sorted(chains.items()):
        exp_slug = exp.replace("/", "-")
        calls_path = snap_dir / f"calls_{exp_slug}.csv"
        puts_path = snap_dir / f"puts_{exp_slug}.csv"
        calls.to_csv(calls_path, index=False)
        puts.to_csv(puts_path, index=False)
        manifest_rows.append({
            "expiration": exp,
            "calls_count": len(calls),
            "puts_count": len(puts),
            "calls_file": calls_path.name,
            "puts_file": puts_path.name,
        })

    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(snap_dir / "manifest.csv", index=False)

    print(f"\nSnapshot saved to {snap_dir}/")
    print(f"  {len(manifest)} expiration(s)")
    print(f"  {manifest['calls_count'].sum():,} total call contracts")
    print(f"  {manifest['puts_count'].sum():,} total put contracts")
    return snap_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="Fetch S&P 500 (SPX) daily option chain data from Yahoo Finance.",
    )
    parser.add_argument(
        "--expiration", "-e",
        type=str, default=None,
        help="Comma-separated expiration date(s) in YYYY-MM-DD. "
             "If omitted, fetches ALL available expirations.",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available expiration dates and exit (no data fetched).",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float, default=DELAY_BETWEEN_CALLS,
        help=f"Seconds to wait between chain fetches (default: {DELAY_BETWEEN_CALLS}).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path, default=None,
        help="Directory for snapshot output (default: output/ relative to project root).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        try:
            expirations = get_all_expirations()
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Available SPX option expirations ({len(expirations)}):")
        for exp in expirations:
            print(f"  {exp}")
        return 0

    if args.expiration:
        expirations = [e.strip() for e in args.expiration.split(",") if e.strip()]
        if not expirations:
            print("ERROR: --expiration provided but no valid dates parsed.", file=sys.stderr)
            return 1
    else:
        try:
            expirations = get_all_expirations()
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    chains = fetch_all_chains(expirations=expirations, delay=args.delay)
    if not chains:
        print("ERROR: No option chains were successfully fetched.", file=sys.stderr)
        return 1

    save_snapshot(chains, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
