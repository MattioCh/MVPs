"""
SQLite database for storing option chain data.

Tables
------
**underlyings**        — canonical list of underlying assets (symbol, name, type)
**chain_snapshots**    — metadata for each time we fetched a full option chain
**option_contracts**   — individual options (calls & puts) with prices, liquidity, Greeks

Usage
-----
    from option_chain_db import OptionChainDB

    db = OptionChainDB("options.db")
    db.create_db()

    # Insert a snapshot
    db.insert_chain(
        symbol="AAPL",
        underlying_price=175.30,
        quote_date="2026-05-06 10:30:00",
        options=[
            {"option_type": "call", "strike": 170.0, "expiration": "2026-05-10",
             "bid": 5.20, "ask": 5.40, "volume": 1200, "open_interest": 8500,
             "implied_volatility": 0.25, "delta": 0.65},
        ],
    )

    # Query latest chain for a symbol
    df = db.get_latest_chain("AAPL")

    # Query by expiration
    df = db.get_chain_by_expiration("AAPL", "2026-06-20")
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

CREATE_UNDERLYINGS = """
CREATE TABLE IF NOT EXISTS underlyings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL UNIQUE,
    name        TEXT,
    exchange    TEXT,
    asset_type  TEXT    NOT NULL DEFAULT 'stock'
                        CHECK(asset_type IN ('stock', 'etf', 'index', 'future', 'currency')),
    created_at  TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_CHAIN_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS chain_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    underlying_id     INTEGER NOT NULL REFERENCES underlyings(id) ON DELETE CASCADE,
    symbol            TEXT    NOT NULL,
    quote_date        TIMESTAMP NOT NULL,          -- when the snapshot was taken
    underlying_price  REAL,                         -- price of the underlying at snapshot
    underlying_bid    REAL,
    underlying_ask    REAL,
    iv30              REAL,                         -- 30-day implied volatility of underlying
    fetched_at        TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_OPTION_CONTRACTS = """
CREATE TABLE IF NOT EXISTS option_contracts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id       INTEGER NOT NULL REFERENCES chain_snapshots(id) ON DELETE CASCADE,

    -- Contract identifiers
    option_symbol     TEXT,                          -- OCC symbol (e.g. AAPL260516C00170000)
    option_type       TEXT    NOT NULL
                              CHECK(option_type IN ('call', 'put')),
    strike            REAL    NOT NULL,
    expiration_date   DATE    NOT NULL,
    days_to_expiration INTEGER,                      -- calendar days from quote_date to expiry

    -- Prices & liquidity
    last_price        REAL,
    bid               REAL,
    ask               REAL,
    mark              REAL,                          -- (bid + ask) / 2  or last if no 2-sided mkt
    bid_size          INTEGER,
    ask_size          INTEGER,
    volume            INTEGER,
    open_interest     INTEGER,

    -- Greeks & pricing
    implied_volatility REAL,
    delta             REAL,
    gamma             REAL,
    theta             REAL,
    vega              REAL,
    rho               REAL,

    -- Flags
    in_the_money      INTEGER,                       -- 0/1 boolean

    fetched_at        TIMESTAMP NOT NULL DEFAULT (datetime('now')),

    -- Ensure no duplicate option in the same snapshot
    UNIQUE(snapshot_id, option_type, strike, expiration_date)
);
"""

# Performance indexes
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_snapshots_symbol      ON chain_snapshots(symbol);",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_quote_date  ON chain_snapshots(quote_date);",
    "CREATE INDEX IF NOT EXISTS idx_contracts_snapshot    ON option_contracts(snapshot_id);",
    "CREATE INDEX IF NOT EXISTS idx_contracts_type_strike ON option_contracts(option_type, strike);",
    "CREATE INDEX IF NOT EXISTS idx_contracts_expiry      ON option_contracts(expiration_date);",
    "CREATE INDEX IF NOT EXISTS idx_contracts_symbol_exp  ON option_contracts(snapshot_id, option_type, expiration_date);",
]


# ---------------------------------------------------------------------------
# Helper dataclass
# ---------------------------------------------------------------------------


@dataclass
class OptionContract:
    """Single option contract record ready for insertion."""
    option_type: str
    strike: float
    expiration_date: str              # ISO date string "YYYY-MM-DD"
    days_to_expiration: Optional[int] = None
    option_symbol: Optional[str] = None
    last_price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    mark: Optional[float] = None
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    in_the_money: Optional[bool] = None


# ---------------------------------------------------------------------------
# Main database handler
# ---------------------------------------------------------------------------


class OptionChainDB:
    """Create, populate, and query the option-chain SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ---- connection management ----

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "OptionChainDB":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- schema ----

    def create_db(self, reset: bool = False) -> None:
        """Create tables & indexes.  If *reset*, drop existing tables first."""
        if reset:
            cur = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row["name"] for row in cur.fetchall()
                      if row["name"] != "sqlite_sequence"]
            for t in tables:
                self.conn.execute(f"DROP TABLE IF EXISTS {t};")
        self.conn.execute(CREATE_UNDERLYINGS)
        self.conn.execute(CREATE_CHAIN_SNAPSHOTS)
        self.conn.execute(CREATE_OPTION_CONTRACTS)
        for idx in CREATE_INDEXES:
            self.conn.execute(idx)
        self.conn.commit()

    # ---- insert helpers ----

    def _ensure_underlying(self, symbol: str, *, name: str | None = None,
                           exchange: str | None = None,
                           asset_type: str = "stock") -> int:
        """Return the *underlyings.id* for *symbol*, inserting if missing."""
        cur = self.conn.execute("SELECT id FROM underlyings WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        if row is not None:
            return int(row["id"])
        self.conn.execute(
            "INSERT INTO underlyings (symbol, name, exchange, asset_type) VALUES (?, ?, ?, ?)",
            (symbol, name, exchange, asset_type),
        )
        return int(self.conn.execute("SELECT last_insert_rowid()").fetchone()[0])

    def insert_chain(self, symbol: str, *, quote_date: str,
                     underlying_price: float | None = None,
                     underlying_bid: float | None = None,
                     underlying_ask: float | None = None,
                     iv30: float | None = None,
                     name: str | None = None,
                     exchange: str | None = None,
                     asset_type: str = "stock",
                     options: List[OptionContract | dict]) -> int:
        """Insert a full option-chain snapshot for *symbol*.

        Args:
            symbol: Ticker symbol (e.g. "AAPL", "SPX").
            quote_date: Timestamp string for the snapshot.
            underlying_price: Spot/underlying price at snapshot time.
            underlying_bid, underlying_ask: NBBO of the underlying.
            iv30: 30-day implied vol of the underlying (e.g. VIX for SPX).
            name: Company / descriptive name (used on first insert).
            exchange: Exchange code.
            asset_type: 'stock', 'etf', 'index', 'future', or 'currency'.
            options: Sequence of option records.

        Returns:
            The chain_snapshots.id of the newly inserted snapshot.
        """
        uid = self._ensure_underlying(symbol, name=name, exchange=exchange,
                                      asset_type=asset_type)

        # Insert the snapshot header
        cur = self.conn.execute(
            """INSERT INTO chain_snapshots
               (underlying_id, symbol, quote_date, underlying_price, underlying_bid,
                underlying_ask, iv30)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, symbol, quote_date, underlying_price, underlying_bid,
             underlying_ask, iv30),
        )
        snapshot_id = cur.lastrowid

        # Insert each option contract
        for opt in options:
            if isinstance(opt, dict):
                opt = OptionContract(**opt)

            # Compute days to expiration if not provided
            dte = opt.days_to_expiration
            if dte is None:
                try:
                    qd = datetime.strptime(quote_date[:10], "%Y-%m-%d")
                    ex = datetime.strptime(opt.expiration_date[:10], "%Y-%m-%d")
                    dte = (ex - qd).days
                except (ValueError, TypeError):
                    dte = None

            # Compute mark if not provided
            mark = opt.mark
            if mark is None and opt.bid is not None and opt.ask is not None:
                mark = round((opt.bid + opt.ask) / 2.0, 2)

            itm = int(opt.in_the_money) if opt.in_the_money is not None else None

            self.conn.execute(
                """INSERT INTO option_contracts
                   (snapshot_id, option_symbol, option_type, strike, expiration_date,
                    days_to_expiration, last_price, bid, ask, mark, bid_size, ask_size,
                    volume, open_interest, implied_volatility, delta, gamma, theta,
                    vega, rho, in_the_money)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_id, opt.option_symbol, opt.option_type, opt.strike,
                 opt.expiration_date, dte, opt.last_price, opt.bid, opt.ask,
                 mark, opt.bid_size, opt.ask_size, opt.volume, opt.open_interest,
                 opt.implied_volatility, opt.delta, opt.gamma, opt.theta,
                 opt.vega, opt.rho, itm),
            )

        self.conn.commit()
        return snapshot_id

    # ---- query helpers ----

    def get_underlyings(self) -> List[Dict[str, Any]]:
        """Return list of all tracked underlyings."""
        cur = self.conn.execute("SELECT * FROM underlyings ORDER BY symbol")
        return [dict(row) for row in cur.fetchall()]

    def get_latest_snapshot_id(self, symbol: str) -> int | None:
        """Return the most recent *chain_snapshots.id* for *symbol*, or None."""
        cur = self.conn.execute(
            "SELECT id FROM chain_snapshots WHERE symbol = ? ORDER BY quote_date DESC LIMIT 1",
            (symbol,),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else None

    def get_latest_chain(self, symbol: str) -> List[Dict[str, Any]]:
        """Return the latest full option chain for *symbol* as a list of dicts."""
        sid = self.get_latest_snapshot_id(symbol)
        if sid is None:
            return []
        return self._get_contracts_for_snapshot(sid)

    def get_chain_by_expiration(self, symbol: str, expiration_date: str) -> List[Dict[str, Any]]:
        """Return options for a specific expiry from the latest snapshot."""
        sid = self.get_latest_snapshot_id(symbol)
        if sid is None:
            return []
        cur = self.conn.execute(
            """SELECT * FROM option_contracts
               WHERE snapshot_id = ? AND expiration_date = ?
               ORDER BY option_type, strike""",
            (sid, expiration_date),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_chain_at_time(self, symbol: str, quote_date: str) -> List[Dict[str, Any]]:
        """Return the chain closest to *quote_date* for *symbol*."""
        # Find the snapshot nearest to the requested time
        cur = self.conn.execute(
            """SELECT id FROM chain_snapshots
               WHERE symbol = ? AND quote_date <= ?
               ORDER BY quote_date DESC LIMIT 1""",
            (symbol, quote_date),
        )
        row = cur.fetchone()
        if row is None:
            # Try forward
            cur = self.conn.execute(
                "SELECT id FROM chain_snapshots WHERE symbol = ? ORDER BY quote_date ASC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
        if row is None:
            return []
        return self._get_contracts_for_snapshot(int(row["id"]))

    def get_available_expirations(self, symbol: str) -> List[str]:
        """Return sorted unique expiration dates for *symbol*'s latest snapshot."""
        sid = self.get_latest_snapshot_id(symbol)
        if sid is None:
            return []
        cur = self.conn.execute(
            """SELECT DISTINCT expiration_date FROM option_contracts
               WHERE snapshot_id = ?
               ORDER BY expiration_date""",
            (sid,),
        )
        return [row["expiration_date"] for row in cur.fetchall()]

    def get_available_strikes(self, symbol: str, expiration_date: str) -> List[float]:
        """Return sorted unique strikes for *symbol* + *expiration_date*."""
        sid = self.get_latest_snapshot_id(symbol)
        if sid is None:
            return []
        cur = self.conn.execute(
            """SELECT DISTINCT strike FROM option_contracts
               WHERE snapshot_id = ? AND expiration_date = ?
               ORDER BY strike""",
            (sid, expiration_date),
        )
        return [row["strike"] for row in cur.fetchall()]

    def get_snapshot_summary(self, symbol: str) -> Dict[str, Any] | None:
        """Return summary info (underlying price, iv30, option count, etc.)."""
        sid = self.get_latest_snapshot_id(symbol)
        if sid is None:
            return None
        cur = self.conn.execute("SELECT * FROM chain_snapshots WHERE id = ?", (sid,))
        snap = cur.fetchone()
        if snap is None:
            return None
        cur = self.conn.execute(
            """SELECT COUNT(*) AS cnt, COUNT(DISTINCT expiration_date) AS expiries
               FROM option_contracts WHERE snapshot_id = ?""",
            (sid,),
        )
        counts = cur.fetchone()
        result = dict(snap)
        result["total_contracts"] = int(counts["cnt"])
        result["total_expirations"] = int(counts["expiries"])
        return result

    # ---- internal ----

    def _get_contracts_for_snapshot(self, snapshot_id: int) -> List[Dict[str, Any]]:
        cur = self.conn.execute(
            """SELECT * FROM option_contracts
               WHERE snapshot_id = ?
               ORDER BY option_type, expiration_date, strike""",
            (snapshot_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ---- convenience ----

    def to_dataframe(self, rows: List[Dict[str, Any]]) -> "pd.DataFrame":
        """Convert a list-of-dicts result to a pandas DataFrame."""
        import pandas as pd  # optional dependency, import only when needed
        return pd.DataFrame(rows)

    def print_chain(self, rows: List[Dict[str, Any]]) -> None:
        """Pretty-print an option chain (calls left, puts right)."""
        if not rows:
            print("No data.")
            return
        # Group by expiration
        from collections import defaultdict
        by_expiry: Dict[str, List[Dict]] = defaultdict(list)
        for r in rows:
            by_expiry[r["expiration_date"]].append(r)

        for exp in sorted(by_expiry):
            dte = by_expiry[exp][0].get("days_to_expiration", "?")
            print(f"\n{'=' * 90}")
            print(f"  Expiration: {exp}  (DTE: {dte})")
            print(f"{'=' * 90}")
            header = (f"{'CALLS':^42} | {'PUTS':^42}\n"
                      f"{'Strike':>8} {'IV':>6} {'Bid':>8} {'Ask':>8} {'Vol':>6} {'OI':>6}  |"
                      f" {'Strike':>8} {'IV':>6} {'Bid':>8} {'Ask':>8} {'Vol':>6} {'OI':>6}")
            print(header)
            print("-" * 42 + "+" + "-" * 42)
            calls = [r for r in by_expiry[exp] if r["option_type"] == "call"]
            puts = [r for r in by_expiry[exp] if r["option_type"] == "put"]
            call_map = {r["strike"]: r for r in calls}
            put_map = {r["strike"]: r for r in puts}
            all_strikes = sorted(set(call_map) | set(put_map))
            for k in all_strikes:
                c = call_map.get(k)
                p = put_map.get(k)
                def fmt_val(v, w=8, d=2):
                    if v is None:
                        return " " * w
                    if isinstance(v, float):
                        return f"{v:>{w}.{d}f}"
                    return f"{v:>{w}}"
                c_str = (f"{k:>8.1f} {fmt_val(c['implied_volatility'])} "
                         f"{fmt_val(c['bid'])} {fmt_val(c['ask'])} "
                         f"{fmt_val(c['volume'], 6, 0)} {fmt_val(c['open_interest'], 6, 0)}"
                         if c else f"{k:>8.1f}")
                p_str = (f"{k:>8.1f} {fmt_val(p['implied_volatility'])} "
                         f"{fmt_val(p['bid'])} {fmt_val(p['ask'])} "
                         f"{fmt_val(p['volume'], 6, 0)} {fmt_val(p['open_interest'], 6, 0)}"
                         if p else f"{k:>8.1f}")
                print(f"{c_str}  | {p_str}")
