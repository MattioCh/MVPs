"""Download Robert Shiller's monthly U.S. stock market dataset.

Source: http://www.econ.yale.edu/~shiller/data/ie_data.xls
This is the canonical dataset behind the Shiller CAPE / Irrational Exuberance
work. It contains monthly S&P Composite price, dividends, earnings, CPI, and
the cyclically-adjusted P/E (CAPE) ratio from 1871 onward.
"""
from __future__ import annotations

from pathlib import Path
import sys
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
OUT = DATA_DIR / "ie_data.xls"


def main() -> int:
    print(f"Downloading {URL} ...")
    r = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    OUT.write_bytes(r.content)
    print(f"Wrote {OUT} ({len(r.content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
