"""Generate charts for the analysis."""
from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "shiller_clean.csv"
OUT_DIR = ROOT / "output"


def load() -> pd.DataFrame:
    df = pd.read_csv(SRC, parse_dates=["date"])
    return df.dropna(subset=["cape"]).reset_index(drop=True)


def chart_cape_timeline(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df["date"], df["cape"], color="#1f77b4", linewidth=1)
    ax.axhline(25, color="orange", linestyle="--", linewidth=1, label="CAPE = 25")
    ax.axhline(30, color="red", linestyle="--", linewidth=1, label="CAPE = 30")
    long_run_mean = df["cape"].mean()
    ax.axhline(long_run_mean, color="gray", linestyle=":", linewidth=1,
               label=f"Long-run mean ({long_run_mean:.1f})")
    # Annotate famous peaks
    for label, dt in [("1929", "1929-09-01"), ("Tech bubble", "1999-12-01"),
                      ("2007 peak", "2007-05-01"), ("2021 peak", "2021-11-01")]:
        d = pd.Timestamp(dt)
        v = df.loc[df["date"] == d, "cape"]
        if len(v):
            ax.annotate(label, xy=(d, v.iloc[0]), xytext=(0, 8),
                        textcoords="offset points", ha="center", fontsize=8)
    ax.set_title("Shiller CAPE, 1881–2023")
    ax.set_ylabel("CAPE (P / 10-yr avg real earnings)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "01_cape_timeline.png", dpi=140)
    plt.close(fig)


def chart_episodes(df: pd.DataFrame) -> None:
    """For each high-CAPE episode (>=25), show a small-multiple panel of
    real price (rebased to 100 at peak) and real earnings (E10, rebased)
    over the next 10 years. This visualises whether CAPE fell because P
    dropped or because E rose."""
    eps = pd.read_csv(OUT_DIR / "episodes_cape_ge_25.csv", parse_dates=["peak_date"])
    eps = eps[eps["mechanism_10y"] != "incomplete"].reset_index(drop=True)
    n = len(eps)
    cols = 3
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(15, 3.2 * rows), squeeze=False)
    color_map = {
        "crash_driven": "#d62728",
        "earnings_driven": "#2ca02c",
        "no_reversion": "#1f77b4",
        "mixed": "#9467bd",
    }
    for i, ep in eps.iterrows():
        ax = axes[i // cols][i % cols]
        peak = ep["peak_date"]
        end = peak + pd.DateOffset(years=10)
        mask = (df["date"] >= peak) & (df["date"] <= end)
        sub = df.loc[mask].copy()
        if sub.empty:
            continue
        p0 = sub["real_price"].iloc[0]
        e0 = sub["real_earnings_10y_avg"].iloc[0] if not pd.isna(sub["real_earnings_10y_avg"].iloc[0]) else None
        ax.plot(sub["date"], 100 * sub["real_price"] / p0, label="Real price", color="black", linewidth=1.5)
        if e0:
            ax.plot(sub["date"], 100 * sub["real_earnings_10y_avg"] / e0,
                    label="Real E10", color="#2ca02c", linewidth=1.5)
        ax.axhline(100, color="gray", linewidth=0.5, alpha=0.5)
        ax.set_title(f"{peak.strftime('%Y-%m')} (CAPE={ep['peak_cape']:.1f}) — {ep['mechanism_10y']}",
                     color=color_map.get(ep["mechanism_10y"], "black"), fontsize=10)
        ax.tick_params(axis="x", labelsize=8)
        ax.tick_params(axis="y", labelsize=8)
        ax.grid(alpha=0.3)
        if i == 0:
            ax.legend(fontsize=8, loc="upper left")
    # Hide unused axes
    for j in range(n, rows * cols):
        axes[j // cols][j % cols].axis("off")
    fig.suptitle("After CAPE crossed 25: real-price vs real-E10 path over next 10 years (rebased to 100)",
                 y=1.0, fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "02_episodes_decomposition.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def chart_scatter(df: pd.DataFrame) -> None:
    """All-history scatter: CAPE today vs forward 10y real price return,
    coloured by forward 10y real-E10 growth. Tests whether high CAPE
    predicts price weakness AND/OR whether high CAPE periods that DID NOT
    crash were rescued by strong earnings growth."""
    df = df.copy().sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=["cape", "real_price", "real_earnings_10y_avg"])
    df["fwd_idx"] = df["date"].apply(
        lambda d: df["date"].searchsorted(d + pd.DateOffset(years=10))
    )
    n = len(df)
    valid = df["fwd_idx"] < n
    sub = df[valid].copy()
    sub["fp"] = df.loc[sub["fwd_idx"].values, "real_price"].values
    sub["fe"] = df.loc[sub["fwd_idx"].values, "real_earnings_10y_avg"].values
    sub["fwd_price_ret"] = sub["fp"] / sub["real_price"] - 1.0
    sub["fwd_e10_growth"] = sub["fe"] / sub["real_earnings_10y_avg"] - 1.0

    fig, ax = plt.subplots(figsize=(10, 6))
    sc = ax.scatter(sub["cape"], sub["fwd_price_ret"], c=sub["fwd_e10_growth"],
                    cmap="RdYlGn", s=8, alpha=0.6, vmin=-0.3, vmax=1.0)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.axvline(25, color="orange", linestyle="--", linewidth=1, alpha=0.7)
    ax.axvline(30, color="red", linestyle="--", linewidth=1, alpha=0.7)
    ax.set_xlabel("CAPE at month t")
    ax.set_ylabel("Real S&P price return over next 10y")
    ax.set_title("Starting CAPE vs forward 10y real price return\n(colour = forward 10y growth in real 10-yr-avg earnings)")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("Forward 10y real E10 growth")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "03_cape_vs_fwd_return.png", dpi=140)
    plt.close(fig)


def chart_pe_ttm_vs_cape(df: pd.DataFrame) -> None:
    """Show why TTM P/E spikes during recessions (E falls) while CAPE
    smooths through the cycle. This addresses the user's intuition about
    'earnings disappointment' driving high P/E."""
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df["date"], df["cape"], label="CAPE (P/E10)", color="#1f77b4", linewidth=1)
    ax.plot(df["date"], df["pe_ttm"], label="TTM P/E", color="#d62728", linewidth=0.8, alpha=0.7)
    ax.set_ylim(0, 80)
    ax.set_title("CAPE vs TTM P/E: why the smoothed denominator matters")
    ax.set_ylabel("Ratio")
    ax.legend()
    ax.grid(alpha=0.3)
    # Annotate earnings collapses where TTM PE went vertical
    for label, dt in [("WWII E collapse", "1921-06-01"),
                      ("2009 E collapse", "2009-05-01"),
                      ("Covid", "2020-12-01")]:
        d = pd.Timestamp(dt)
        v = df.loc[df["date"] == d, "pe_ttm"]
        if len(v) and not pd.isna(v.iloc[0]):
            ax.annotate(label, xy=(d, min(v.iloc[0], 78)), xytext=(0, -15),
                        textcoords="offset points", ha="center", fontsize=8,
                        arrowprops=dict(arrowstyle="->", color="gray", lw=0.5))
    fig.tight_layout()
    fig.savefig(OUT_DIR / "04_cape_vs_pettm.png", dpi=140)
    plt.close(fig)


def main() -> int:
    df = load()
    df["pe_ttm"] = df["price"] / df["earnings"]
    chart_cape_timeline(df)
    chart_episodes(df)
    chart_scatter(df)
    chart_pe_ttm_vs_cape(df)
    print("Saved 4 charts to output/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
