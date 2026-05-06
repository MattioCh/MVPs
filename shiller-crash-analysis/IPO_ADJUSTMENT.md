# Does the pre-IPO AI complex rescue the high S&P 500 P/E?

**Short answer: no — and including them actually makes the headline ratio
slightly *worse*, not better.** The intuition that "missing private
revenue" is depressing the index's reported earnings is half-right
(revenue *is* missing) but practically wrong (the missing companies are
collectively *losing money*, not generating it). Three independent
arguments converge on this conclusion. They are laid out below with the
arithmetic shown.

---

## TL;DR

| Scenario | S&P 500 mkt cap ($B) | TTM earnings ($B) | P/E (TTM) | CAPE-equiv |
|---|---:|---:|---:|---:|
| **BASE** (May 2026)      | 61,100 | 1,974 | **30.96** | **40.90** |
| FULL_INCLUSION (add all 6 private AI cos at last-round value + losses) | 62,537 | 1,960 | 31.90 | 42.23 |
| LOOKTHROUGH (only add the un-owned %, since 27%/33%/19% etc. is already in MSFT/GOOGL/AMZN) | 62,321 | 1,964 | 31.73 | 41.98 |
| **BULL** (assume mature 20% net margin on current private revenue, full inclusion) | 62,537 | 1,984 | **31.52** | — |

Even the most charitable bull case nudges P/E *up*, because the added
market cap dwarfs the added (real or imagined) earnings. To bring the
S&P 500 P/E from 30.96 to its long-run mean of 16, the index would need
**+94% earnings growth ($1.85T more)** — a number two orders of
magnitude larger than anything the entire private AI complex could
contribute. The Shiller-CAPE crash analysis ([ANALYSIS.md](ANALYSIS.md))
is therefore not materially altered by IPO accounting.

---

## Why the user's hypothesis was reasonable to test

The intuition — "the index's denominator is artificially low because
giant private cos like SpaceX/OpenAI aren't in it yet" — has surface
appeal:

1. SpaceX (~$400B), OpenAI (~$500B), Anthropic (~$183B), xAI (~$200B)
   together are roughly **$1.3T of value sitting outside the index**.
2. If those cos eventually IPO with positive earnings, public-market
   aggregate E rises while M (market cap) only rises by their float weight.
3. Many S&P 500 incumbents (MSFT, GOOGL, AMZN, NVDA) hold material
   equity stakes, so part of the economic value is *already* implicitly
   in the index via stakeholder accounting.

So: a serious diligence answer requires actually pricing this in, not
hand-waving. Which is what the script does.

---

## Method

[scripts/ipo_adjustment.py](scripts/ipo_adjustment.py) builds three
scenarios on top of the May-2026 macro anchors:

- S&P 500 aggregate market cap: **$61.1T** (S&P DJI year-end 2025).
- Trailing P/E: **30.96** ([multpl.com](https://www.multpl.com/s-p-500-pe-ratio)).
- Implied TTM earnings: 61,100 / 30.96 = **$1,974B**.
- Shiller CAPE: **40.90** ([multpl.com](https://www.multpl.com/shiller-pe)).
- Implied "cyclically-adjusted" earnings: 61,100 / 40.90 = **$1,494B**.

Inputs in [data/private_ai_companies.csv](data/private_ai_companies.csv)
and [data/sp500_holder_stakes.csv](data/sp500_holder_stakes.csv).

### Scenarios

1. **BASE** — current S&P 500 as-is.
2. **FULL_INCLUSION** — pretend all 6 cos are already in the index at
   their most recent private-round valuation, and their last-reported
   net income is added to the aggregate denominator.
3. **LOOKTHROUGH** — recognise that the % already economically owned by
   S&P 500 cos is double-counted under (2), and add only the *un-owned*
   slice to both numerator and denominator.

The 4th column ("BULL") is a separate sensitivity: replace the actual
losses with a mature-software-style 20% net margin on current revenue.

### Stakes used in LOOKTHROUGH

| Holder (S&P 500) | Investee | Estimated economic stake |
|---|---|---|
| MSFT | OpenAI | 27% |
| NVDA | OpenAI | 2% |
| AMZN | Anthropic | 19% |
| GOOGL | Anthropic | 14% |
| NVDA | xAI | 5% |

Stakes are rough public-source estimates (Reuters, FT, The Information).
SpaceX, Stripe, and Databricks have no material S&P 500 holder stakes.

---

## Results

```
=== Scenario results ===
      scenario  market_cap_usd_b  ttm_earnings_usd_b  pe_ttm_adj  cape_adj
          BASE          61100.00             1973.51       30.96     40.90
FULL_INCLUSION          62536.50             1960.41       31.90     42.23
   LOOKTHROUGH          62321.11             1964.11       31.73     41.98
```

Three things to notice:

1. **The numerator (market cap) increases by 2.4% under full inclusion**
   — because we add ~$1.4T of private-co value.
2. **The denominator (earnings) *falls* by 0.7%** — because the private
   cos collectively report a net loss of ~$13B (OpenAI alone is ~−$9B).
3. **Net effect on P/E: +3%, in the wrong direction.**

LOOKTHROUGH is almost identical because the un-owned percentages are
still 65–95% of each co (no single S&P 500 co holds a controlling stake).

The bull case (20% mature-software net margin applied to today's
private-co revenue) only adds ~$10.5B of earnings — still far smaller
than the $1.4T of market cap added — so P/E barely improves.

---

## Why this result is robust

### 1. The numbers don't depend on which estimates you use

Even doubling every private-co valuation *and* assuming each one
suddenly earns a 30% net margin on **3x** their current revenue (a
pure fantasy bull case) only adds ~$50B of earnings against ~$2.6T of
added market cap. P/E stays north of 30. The arithmetic is dominated by
the size of the public market: $61T is ~50x the entire private AI
complex.

### 2. The "earnings already in the index" argument cuts the *other* way

Equity-method / fair-value accounting means MSFT, GOOGL, AMZN, NVDA
**already report a share of OpenAI/Anthropic/xAI's losses** in their
own income statements. So the BASE $1,974B of S&P 500 earnings is
already *depressed* by ~$5–8B of look-through AI losses. Stripping
those out (i.e. measuring incumbents on their own operations) would
*lower* P/E by about 0.1 — tiny, but the sign is the opposite of the
user's hypothesis.

### 3. The Shiller-crash result holds

The empirical finding from [ANALYSIS.md](ANALYSIS.md) is that **all
four** historical CAPE>=30 episodes (1929, 1999, 2001, 2002) produced
≥40% real drawdowns within 10 years and negative 10-year real returns —
**even when forward earnings growth was strong** (1999 had +31% real E10
growth and price still fell 39%). Today's CAPE of 40.90 is the
**second-highest in 154 years**, behind only Dec 1999. IPO-driven
denominator relief at the scale of $50–100B of incremental earnings does
not move the needle against a price level of $61T.

---

## What the user got right (and where the intuition does have value)

- **Concentration of AI economic exposure inside a few S&P 500 cos is
  real.** MSFT/GOOGL/AMZN/NVDA collectively now have hundreds of
  billions of dollars of economic interest in the private AI complex.
  This is *already in their stock prices*, which is part of why the top
  10 names = ~38% of the index ([ANALYSIS.md](ANALYSIS.md)). It is a
  concentration risk, not a valuation cushion.

- **A SpaceX IPO specifically would be different.** SpaceX is the only
  one of the four giants that is roughly cash-flow break-even. If it
  IPOs at, say, $400B with $13B revenue and $1B earnings, it adds 0.7%
  to the index's market cap and ~0.05% to earnings — moves P/E by 0.02.
  Negligible for the headline. Anthropic and OpenAI losses would *worsen*
  the ratio on entry.

- **Forward-looking the picture *could* improve** — but only if the AI
  cos hit aggressive profitability targets (OpenAI's own plan is
  cash-flow positive 2029 with $200B revenue by 2030). At a 25% net
  margin, that's $50B of earnings from one company. Multiply by the
  whole complex and you might get $100–150B/year of incremental
  earnings by ~2030. Against a target $1,845B earnings gap (to reach
  long-run-mean P/E), that closes **<10% of the gap**. The rest must
  come from the existing S&P 500.

---

## Bottom line

The pre-IPO/private-AI revenue story does not rescue the elevated S&P
500 P/E. The arithmetic is clear and the conclusion is robust to
generous assumptions. The real risk is the *opposite* of the
hypothesis: the S&P 500's valuation is **already** stretched in part
because incumbents are valued partly for their AI exposure (direct
opex/capex, plus equity stakes in the private complex). A repricing of
AI expectations would hit both public mega-caps and private valuations
simultaneously. That is single-factor exposure, not diversification.

The Shiller-crash empirical record (CAPE>=30 → 100% deep drawdowns,
n=4) therefore stands without modification.

---

## Sources

- S&P 500 market cap, weights, history: <https://en.wikipedia.org/wiki/S%26P_500>
- Trailing P/E and Shiller CAPE (May 2026): <https://www.multpl.com/s-p-500-pe-ratio>, <https://www.multpl.com/shiller-pe>
- OpenAI: <https://en.wikipedia.org/wiki/OpenAI> (revenue, losses, valuations, MSFT stake)
- Anthropic: <https://en.wikipedia.org/wiki/Anthropic> (Series F/G valuations, AMZN/GOOGL stakes)
- SpaceX, xAI, Stripe, Databricks valuations: most recent reported funding rounds (Bloomberg, Reuters, The Information).

Estimates marked as such in [data/private_ai_companies.csv](data/private_ai_companies.csv) — net income figures
for unprofitable private cos are educated approximations from press
reports, not audited financials.
