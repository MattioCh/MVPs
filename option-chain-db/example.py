"""
Example: create, populate, and query the option chain SQLite database
with realistic mock data.
"""

from pathlib import Path
from option_chain_db import OptionChainDB, OptionContract

DB_PATH = Path(__file__).resolve().parent / "example_options.db"


def build_mock_options() -> list:
    """Generate a realistic AAPL option chain with multiple expirations."""
    underlying_price = 175.30

    weekly = "2026-05-10"
    monthly = "2026-06-20"
    quarterly = "2026-09-18"

    options = []

    # ---- Weekly expiry: strikes around the money ----
    for strike in [165.0, 170.0, 175.0, 180.0, 185.0]:
        is_call_itm = strike < underlying_price
        is_put_itm = strike > underlying_price

        options.append(OptionContract(
            option_type="call", strike=strike, expiration_date=weekly,
            bid=max(0.05, (underlying_price - strike) * 0.6),
            ask=max(0.10, (underlying_price - strike) * 0.65),
            volume=int(5000 * (1 + abs(underlying_price - strike) / 10)),
            open_interest=int(20000 * (1 + abs(underlying_price - strike) / 10)),
            implied_volatility=0.22 + 0.03 * abs(strike - underlying_price) / 10,
            delta=0.9 - 0.4 * abs(strike - underlying_price) / 10 if is_call_itm
                  else 0.1 + 0.4 * abs(strike - underlying_price) / 10,
            gamma=0.05 - 0.005 * abs(strike - underlying_price),
            theta=-0.15 - 0.05 * abs(strike - underlying_price),
            vega=0.35, rho=0.02, in_the_money=is_call_itm,
        ))

        options.append(OptionContract(
            option_type="put", strike=strike, expiration_date=weekly,
            bid=max(0.05, (strike - underlying_price) * 0.55),
            ask=max(0.10, (strike - underlying_price) * 0.60),
            volume=int(4000 * (1 + abs(underlying_price - strike) / 10)),
            open_interest=int(15000 * (1 + abs(underlying_price - strike) / 10)),
            implied_volatility=0.23 + 0.03 * abs(strike - underlying_price) / 10,
            delta=-0.1 - 0.4 * abs(strike - underlying_price) / 10 if is_put_itm
                  else -0.9 + 0.4 * abs(strike - underlying_price) / 10,
            gamma=0.05 - 0.005 * abs(strike - underlying_price),
            theta=-0.12 - 0.04 * abs(strike - underlying_price),
            vega=0.35, rho=-0.02, in_the_money=is_put_itm,
        ))

    # ---- Monthly expiry: wider strikes ----
    for strike in [155.0, 165.0, 175.0, 185.0, 195.0]:
        for typ, itm_cond in [("call", strike < underlying_price),
                               ("put", strike > underlying_price)]:
            prem = 0.55 if typ == "put" else 0.60
            options.append(OptionContract(
                option_type=typ, strike=strike, expiration_date=monthly,
                bid=max(0.10, abs(strike - underlying_price) * prem),
                ask=max(0.15, abs(strike - underlying_price) * prem + 0.10),
                volume=int(8000 * (1 + abs(underlying_price - strike) / 20)),
                open_interest=int(30000 * (1 + abs(underlying_price - strike) / 20)),
                implied_volatility=0.25 + 0.02 * abs(strike - underlying_price) / 10,
                delta=0.55 if typ == "call" else -0.45,
                gamma=0.035, theta=-0.08, vega=0.45,
                rho=0.03 if typ == "call" else -0.03,
                in_the_money=itm_cond,
            ))

    # ---- Quarterly expiry: even wider ----
    for strike in [145.0, 160.0, 175.0, 190.0, 205.0]:
        for typ in ("call", "put"):
            options.append(OptionContract(
                option_type=typ, strike=strike, expiration_date=quarterly,
                bid=max(0.20, abs(strike - underlying_price) * 0.50),
                ask=max(0.25, abs(strike - underlying_price) * 0.55),
                volume=int(12000 * (1 + abs(underlying_price - strike) / 30)),
                open_interest=int(50000 * (1 + abs(underlying_price - strike) / 30)),
                implied_volatility=0.28 + 0.02 * abs(strike - underlying_price) / 15,
                delta=0.50 if typ == "call" else -0.50,
                gamma=0.025, theta=-0.05, vega=0.60,
                rho=0.05 if typ == "call" else -0.05,
                in_the_money=(strike < underlying_price) if typ == "call"
                             else (strike > underlying_price),
            ))

    return options


def main() -> int:
    # 1. Create / reset the database
    print(f"Creating database at: {DB_PATH}")
    db = OptionChainDB(DB_PATH)
    db.create_db(reset=True)

    # 2. Insert a full option chain for AAPL
    print("\nInserting AAPL option chain snapshot...")
    options = build_mock_options()
    sid = db.insert_chain(
        symbol="AAPL", quote_date="2026-05-06 10:30:00",
        underlying_price=175.30, underlying_bid=175.29, underlying_ask=175.31,
        iv30=0.22, name="Apple Inc.", exchange="NASDAQ", asset_type="stock",
        options=options,
    )
    print(f"  Inserted snapshot id={sid} with {len(options)} contracts")

    # 3. Insert a second earlier snapshot for time-series queries
    print("\nInserting AAPL snapshot from the previous day...")
    options_prev = build_mock_options()
    db.insert_chain(
        symbol="AAPL", quote_date="2026-05-05 10:30:00",
        underlying_price=174.80, underlying_bid=174.78, underlying_ask=174.82,
        iv30=0.23, name="Apple Inc.", exchange="NASDAQ", asset_type="stock",
        options=[OptionContract(**{k: v for k, v in o.__dict__.items()
                 if k != "days_to_expiration" or v is not None})
                 for o in options_prev],
    )

    # 4. Insert a SPX (index) chain for variety
    print("\nInserting SPX option chain snapshot...")
    spx_options = [
        OptionContract(
            option_type="call", strike=5400.0, expiration_date="2026-05-10",
            bid=15.20, ask=15.40, volume=850, open_interest=12000,
            implied_volatility=0.14, delta=0.55,
        ),
        OptionContract(
            option_type="call", strike=5450.0, expiration_date="2026-05-10",
            bid=8.50, ask=8.70, volume=620, open_interest=9500,
            implied_volatility=0.15, delta=0.35,
        ),
        OptionContract(
            option_type="put", strike=5300.0, expiration_date="2026-05-10",
            bid=10.10, ask=10.30, volume=710, open_interest=11000,
            implied_volatility=0.16, delta=-0.30,
        ),
        OptionContract(
            option_type="put", strike=5350.0, expiration_date="2026-05-10",
            bid=5.80, ask=5.95, volume=540, open_interest=8700,
            implied_volatility=0.15, delta=-0.15,
        ),
    ]
    sid_spx = db.insert_chain(
        symbol="SPX", quote_date="2026-05-06 09:45:00",
        underlying_price=5420.50, underlying_bid=5420.30, underlying_ask=5420.70,
        iv30=0.14, name="S&P 500 Index", exchange="CBOE", asset_type="index",
        options=spx_options,
    )
    print(f"  Inserted snapshot id={sid_spx} with {len(spx_options)} contracts")

    # ---- Query demos ----

    # 5. List all underlyings
    print("\n=== Underlyings ===")
    for u in db.get_underlyings():
        print(f"  {u['symbol']:6s} | {u['name'] or '':20s} | "
              f"{u['asset_type']:8s} | {u['exchange'] or '':8s}")

    # 6. Snapshot summary
    print("\n=== AAPL Snapshot Summary ===")
    summary = db.get_snapshot_summary("AAPL")
    if summary:
        print(f"  Quote date:      {summary['quote_date']}")
        print(f"  Underlying:      ${summary['underlying_price']:.2f}")
        print(f"  IV30:            {summary['iv30']:.2%}")
        print(f"  Total contracts: {summary['total_contracts']}")
        print(f"  Total expiries:  {summary['total_expirations']}")

    # 7. Available expirations
    print("\n=== AAPL Available Expirations ===")
    for exp in db.get_available_expirations("AAPL"):
        print(f"  {exp}")

    # 8. Chain for a specific expiration
    print("\n=== AAPL Weekly Chain (2026-05-10) ===")
    weekly_chain = db.get_chain_by_expiration("AAPL", "2026-05-10")
    db.print_chain(weekly_chain)

    # 9. Full chain as DataFrame
    full_chain = db.get_latest_chain("AAPL")
    df = db.to_dataframe(full_chain)
    print(f"\n=== Full AAPL Chain as DataFrame ===")
    print(f"  Shape: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Sample:\n{df.head(10).to_string(index=False)}")

    # 10. Query by time
    print("\n=== AAPL Chain on previous day ===")
    prev_chain = db.get_chain_at_time("AAPL", "2026-05-05 12:00:00")
    print(f"  Found {len(prev_chain)} contracts")

    # 11. Available strikes
    strikes = db.get_available_strikes("AAPL", "2026-06-20")
    print(f"\n=== AAPL Strikes (2026-06-20) ===")
    print(f"  {strikes}")

    # 12. Print SPX chain
    print("\n=== SPX Chain ===")
    spx_chain = db.get_latest_chain("SPX")
    db.print_chain(spx_chain)

    db.close()
    print(f"\nAll done!  Database at: {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())