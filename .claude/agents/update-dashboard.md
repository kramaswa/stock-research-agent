---
name: update-dashboard
description: Update the stock ranking dashboard artifact with new or revised hold_check data. Use this when the user shares hold_check results (screenshot or table) for a stock, or asks to add a stock with a manual estimate.
---

## Dashboard context

**Artifact URL:** https://claude.ai/artifact/YTRPRTL1gdHr4HuXFWqTAf  
**HTML file:** `ranking.html` in the project root (`C:\Users\kisho\projects\stock-research-agent\ranking.html`)  
**S&P baseline:** 9.25%/yr + ~1.3% div → **~2.55× total return over 10yr**

## Current rank order (79 stocks)

| # | Ticker | Expected | Notes |
|---|--------|----------|-------|
| 1 | SKHY | ~4.67× | ADR — Korean SK Hynix |
| 2 | DLO | ~3.97× | batch; LatAm payments; revised anchor 15%, LatAm risk adj |
| 3 | MU | ~3.85× | cyclical; 35% bear |
| 4 | VEEV | ~3.80× | |
| 5 | AVGO | ~3.74× | exit PE bull 32→28 for projected rev scale |
| 6 | MA | ~3.70× | |
| 7 | NU | ~3.67× | LatAm digital bank |
| 8 | PAYP | ~3.56× | batch; Japan payments |
| 9 | FLYW | ~3.47× | batch; cross-border fintech |
| 10 | NVDA | ~3.47× | exit PEs revised 23/29→20/25; implied mkt cap sanity check |
| 11 | SMCI | ~3.42× | manual; ⚠ DOJ probe |
| 12 | TTMI | ~3.41× | batch; PCB |
| 13 | CRDO | ~3.41× | batch; AI connectivity semi; EPS corrected to $5.30 |
| 14 | INTU | ~3.40× | |
| 15 | MKSI | ~3.37× | batch; semi instruments + Atotech; PEs revised 16/22/28 |
| 16 | LYFT | ~3.30× | |
| 17 | TSM | ~3.29× | ADR — TSMC; PEs 25/32→22/26 for projected rev scale; probs 25/55/20 |
| 18 | ORCL | ~3.25× | batch; enterprise cloud/legacy; PEs revised to 14/22/28 |
| 19 | PLTR | ~3.24× | manual at ~$192 |
| 20 | ISRG | ~3.16× | exit PEs 20/32/46→20/26/35; competition + implied mkt cap check |
| 21 | SIMO | ~3.11× | batch; NAND controller; cyclical |
| 22 | CRWD | ~3.10× | hold_check at ~$262 |
| 23 | FICO | ~3.08× | batch; revised: anchor 9%, PEs fintech; VantageScore competition |
| 24 | AMD | ~3.00× | manual at ~$643 |
| 25 | CRWV | ~3.00× | GAAP-neg equity-value model |
| 26 | KLIC | ~2.99× | batch; semi equipment; EPS corrected to $4.24 |
| 27 | FIS | ~2.96× | batch; anomalous ~5× PE; conservative anchor |
| 28 | ALAB | ~2.92× | batch; AI connectivity semi; 61× PE |
| 29 | DSP | ~2.88× | batch; adtech |
| 30 | PENG | ~2.87× | manual; AI cluster integrator |
| 31 | SNOW | ~2.80× | |
| 32 | CRM | ~2.79× | hold_check at ~$224 |
| 33 | CORZ | ~2.75× | batch; GAAP-neg equity-value; AI data center |
| 34 | AMKR | ~2.73× | batch; OSAT |
| 35 | NOW | ~2.67× | hold_check; PEs 32/46→28/34 for projected rev; probs 26/49/25 |
| 36 | STX | ~2.67× | manual; cyclical HDD |
| 37 | APLD | ~2.67× | GAAP-neg equity-value model |
| 38 | META | ~2.66× | hold_check; bull PE 30→26; probs 16/52/32 |
| 39 | MELI | ~2.60× | |
| 40 | TER | ~2.60× | batch; semi equipment |
| 41 | PAY | ~2.57× | batch; bill payment fintech |
| 42 | AMZN | ~2.55× | hold_check; PEs 33/42→22/26 for projected rev; probs 20/55/25 |
| 43 | MSFT | ~2.53× | hold_check; PEs 24/32→22/26; probs 7/61/32 |
| 44 | HPE | ~2.46× | batch; enterprise hardware |
| 45 | NFLX | ~2.40× | |
| 46 | ADBE | ~2.40× | |
| 47 | IONQ | ~2.34× | batch; GAAP-neg equity-value; quantum |
| 48 | FORM | ~2.32× | batch; semi equipment |
| 49 | UBER | ~2.30× | |
| 50 | NTAP | ~2.27× | batch; cloud storage |
| 51 | KEYS | ~2.19× | batch; test & measurement |
| 52 | DASH | ~2.16× | bull PE 37→32; probs 20/55/25 |
| 53 | LIF | ~2.14× | batch; consumer app |
| 54 | JBL | ~2.10× | batch; EMS |
| 55 | ADI | ~2.07× | batch; analog semi |
| 56 | GOOGL | ~2.07× | manual estimate; bull PE 28→26; probs 15/55/30 |
| 57 | SMTC | ~2.03× | batch; IoT/optical semi |
| 58 | ARW | ~2.01× | batch; distribution |
| 59 | MRVL | ~2.00× | |
| 60 | WDC | ~2.00× | batch; cyclical HDD storage |
| 61 | VICR | ~1.97× | batch; power semi |
| 62 | AVT | ~1.90× | batch; distribution |
| 63 | CIEN | ~1.87× | batch; networking |
| 64 | LRCX | ~1.86× | batch; semi equipment |
| 65 | DELL | ~1.86× | batch; AI servers; $192B rev dp=7 |
| 66 | FN | ~1.83× | batch; optical EMS |
| 67 | DDOG | ~1.81× | batch; observability; 112× PE |
| 68 | TSLA | ~1.80× | warning color — autonomy option |
| 69 | P | ~1.70× | batch; Pure Storage; 55× PE |
| 70 | APH | ~1.68× | batch; connectors; post-split |
| 71 | SNX | ~1.65× | batch; IT distribution |
| 72 | SPCX | ~1.60× | SpaceX IPO vehicle |
| 73 | ASTS | ~1.60× | batch; GAAP-neg equity-value; satellite |
| 74 | CLS | ~1.59× | batch; EMS |
| 75 | IMOS | ~1.46× | batch; Taiwan OSAT; EPS corrected |
| 76 | DOCN | ~1.45× | batch; cloud SMB |
| 77 | ASX | ~1.17× | batch; large OSAT |
| 78 | NET | ~1.08× | batch; cloud/CDN; 241× PE |
| 79 | BLSH | ~0.88× | batch; crypto exchange |

Followed by reference rows: VOO, SCHG (not ranked stocks).

**Note:** Stocks marked "batch" were added from the Yahoo Finance growth technology screener using systematic dp-tier estimates. Oct 10 2026: exit PEs revised for projected-revenue scale check on 8 stocks (AMZN, TSM, NOW, MSFT, AVGO, META, GOOGL, DASH); original hold_check probabilities restored (batch fix had incorrectly used 20/55/25 for all). Earlier: CRDO EPS corrected ($7.29→$5.30), KLIC EPS corrected ($5.85→$4.24), IMOS EPS/price corrected, DLO anchor lowered (18%→15%), ORCL/NVDA exit PEs lowered, MKSI PEs lowered, FICO anchor/PEs revised for VantageScore competition, ISRG exit PEs revised for competition+scale.

## dp tier table (hold_check large-base discount)

| Revenue | dp | base_cap | bull_cap |
|---------|-----|----------|---------|
| < $10B  | 1pp | none     | none    |
| $10–50B | 3pp | none     | none    |
| $50–150B| 5pp | 18%      | 22%     |
| $150–400B| 7pp| 14%      | 18%     |
| > $400B | 10pp| 11%      | 15%     |

## Scenario probability constraints (hold_check enforces these)

- Bear: 15–40%
- Base: 40–60%  
- Bull: 15–40%

## ⚠ Accuracy rules (always apply)

1. **Check latest news before finalizing any estimate.** Training knowledge cutoff is Aug 2025. For any stock, search for recent earnings, product launches, competitive developments, and analyst targets before locking in growth rates. A missed product launch or major customer win can shift the base case by 2-5pp.
2. **Run `validate_entry(e)` before calling add_stock/update_stock/move_stock.** This is called automatically inside those functions and will raise a `ValueError` if anything is wrong. Read the error message — it shows exactly what number is wrong and what the correct value should be. Fix the StockEntry data, not the validator.
3. **Cross-check rank position.** After computing expected×, compare to neighbors above and below in the rank table to confirm the slot makes sense.
4. **Flag manual estimates clearly.** Always set `source_note="manual estimate"` on StockEntry when no hold_check data was provided. Note in the card what a hold_check would resolve.

## Sanity check rules (always apply)

`validate_entry()` automatically calls `_sanity_check(e)` which prints warnings for entries that pass formula checks but have implausible parameters. Additionally, `sanity_check_all(html)` can audit all 79 cards from the HTML.

### Exit PE caps by revenue tier

| Revenue | Base exit PE cap |
|---------|-----------------|
| < $50B  | 35× |
| $50–150B | 26× |
| $150–400B | 22× |
| > $400B | 18× |

Bull exit PE is flagged if it exceeds cap + 8×. These caps apply to batch-added stocks. Known exceptions from original analysis: AMZN (33× base, AWS segment), TSM (25× base, monopoly fab), MSFT (24× base, Azure AI), GOOGL (22× base, Cloud growth).

### Other sanity checks

- **Expected vs PE**: Flag if expected > 3.0× at > 50× PE, or expected > 2.0× at > 100× PE
- **Bear floor**: Flag if bear return > 8× (implies no realistic downside modeled)
- **Expected ceiling**: Flag if expected > 4× (verify data, not necessarily wrong — FICO and SKHY are legitimate)
- **Implied market cap**: Before presenting any estimate, mentally verify: does `NTM_EPS × (1+g)^10 × exit_PE × shares` produce a plausible market cap? A $50B company reaching $5T in the base case is wrong.

### Running the audit

```python
from dashboard_update import load_html, sanity_check_all
html = load_html()
results = sanity_check_all(html)  # {ticker: [warnings]}
```

## What validate_entry checks

```
validate_entry(e: StockEntry) → None   # raises ValueError on failure, prints OK on success
```

Three checks, in order:

**1. Probability constraints**
- Bear: 15–40%, Base: 40–60%, Bull: 15–40%, sum = 100%

**2. Weighted expected (tolerance 3%)**
- `abs(stated_expected - (b.prob/100*b.ret + s.prob/100*s.ret + u.prob/100*u.ret)) / stated_expected ≤ 0.03`
- This is the most important check. If you copy `expected=` from a hold_check screenshot, this verifies the screenshot's math was correct.

**3. Adj return plausibility per scenario (tolerance 25%)**
- `formula = (ntm_eps × (1 + growth/100)^10 × exit_pe × dilution) / price`
- Checks each scenario's stated `ret` against the formula within 25%.
- The tolerance is intentionally loose to accommodate growth-decay entries (where `growth` is an effective CAGR, not a flat rate). If a scenario uses growth decay, pass the **effective CAGR** as `growth`, not the starting rate.
- A >25% error means the scenario numbers are internally inconsistent — the growth%, exit P/E, dilution, and NTM EPS don't produce the stated return at the given price.

## Workflow for updating a stock

### If the user shares a hold_check screenshot:
1. **Search recent news first** — WebSearch for "[TICKER] earnings 2026" and "[TICKER] latest news" to catch any developments since Aug 2025 that the hold_check may not have fully priced in
2. Read all numbers from the screenshot: bear/base/bull (prob%, growth%, exit P/E, price target, adj return×), expected×, starting EPS, entry price, S&P baseline
3. Build a `StockEntry` using `dashboard_update.py` data classes
4. **Call `validate_entry(e)` in a Bash script** — verify it prints OK before proceeding. If it fails, fix the mismatched field.
5. Determine correct rank by comparing expected× to neighbors
6. Call `add_stock()` (new stock) or `update_stock()` (existing) or `move_stock()` (rank changed)
7. Save HTML, then publish artifact

### If doing a manual estimate (no hold_check):
1. **Search current price and NTM EPS** — WebSearch for "[TICKER] stock price today" and "[TICKER] forward EPS 2026 2027 consensus"
2. **Search recent news** — WebSearch for "[TICKER] earnings revenue growth 2026" to catch product launches, competitive wins, or guidance changes since Aug 2025
3. Estimate growth rates using dp tier table above: bear = anchor - 2×dp, base = min(anchor - dp, base_cap), bull = min(anchor, bull_cap)
4. Use exit P/E: bear ~12-16×, base ~20-24×, bull ~26-32× (adjust for company quality)
5. Compute adj return = (NTM_EPS × (1+g)^10 × exit_PE × dilution) / current_price for each scenario
6. Compute weighted expected = sum(prob_i/100 × ret_i)
7. Build StockEntry, **call `validate_entry(e)` to confirm the math**, then call `add_stock()`
8. Note any news developments that materially affected the estimate in the card's `note` field

## Using dashboard_update.py

```python
from dashboard_update import (
    load_html, save_html, get_rank_order,
    Scenario, StockEntry,
    validate_entry,
    add_stock, update_stock, move_stock,
    dp_for_revenue,
    reorder_rank_rows, reorder_cards,
)

html = load_html()

# Check current state
for rank, ticker in get_rank_order(html):
    print(f"#{rank}: {ticker}")

# Example: add a new stock
e = StockEntry(
    ticker="AMD", company="Advanced Micro Devices — NASDAQ",
    price=643, fwd_pe=41, ntm_eps=15.65, dilution=0.95,
    rank=17,
    bear=Scenario(prob=20, growth=8,  exit_pe=14, price_target=449,  ret=0.70, rationale="NVIDIA CUDA moat wins; AMD niche"),
    base=Scenario(prob=55, growth=18, exit_pe=22, price_target=1698, ret=2.64, rationale="MI-series sustains; EPYC #2 server CPU"),
    bull=Scenario(prob=25, growth=24, exit_pe=28, price_target=3575, ret=5.56, rationale="AMD captures 20-25% AI GPU; custom silicon"),
    expected=3.00,
    chips=["NTM EPS: ~$15.65 (FY2027 consensus) · 2026 revenue ~$51B · dp=5pp · dilution ~0.95×"],
    warns=["Starting at 41× fwd P/E — base case below S&P; bull (5.56×) at 25% weight carries expected above index"],
    note="Manual estimate — no hold_check available.",
    source_note="manual estimate",
)
# validate_entry is called automatically inside add_stock — will raise ValueError if wrong
html = add_stock(html, e)
save_html(html)
```

Then publish:
```python
# Artifact tool call with:
# url = "https://claude.ai/artifact/YTRPRTL1gdHr4HuXFWqTAf"
# file_path = "C:\\Users\\kisho\\projects\\stock-research-agent\\ranking.html"
```

## Important notes

- **TSLA (#32)** has a special inline style on its rticker span (`style="color:#b45309"`). The script handles this correctly — don't manually edit the TSLA rank row.
- **SMCI (#1)** also has the amber warning style (`style="color:#b45309"`) applied to its rticker span, reflecting the accounting/DOJ tail risk. Apply it manually with a `html.replace()` after `add_stock` if re-adding.
- **CRWV (#21)** uses a non-standard equity-value model: `ntm_eps=1.0` is a proxy unit (not EPS), and growth%/exit_pe represent revenue-trajectory scenarios. The standard adj return formula is structured to match the equity-value rets by construction. Do NOT update CRWV using the normal EPS model — it will fail. Re-run hold_check when CRWV is GAAP-profitable.
- **GOOGL manual estimate**: the hold_check at ~$414 returned ~1.35× (likely miscalibrated — 2.5% base EPS implies declining real earnings despite 29%+ Cloud growth). Using ~2.1× manual estimate instead.
- When a stock moves rank, always use `move_stock()` — never manually renumber, as the collision logic matters.
- `add_stock`, `update_stock`, and `move_stock` all call `reorder_cards()` internally — card DOM order is always kept in sync with rank numbers automatically.
- If card order or rank table row order ever looks wrong (a card or row appears visually out of rank sequence), run **both** `reorder_rank_rows(html)` and `reorder_cards(html)` to fix without changing any content. `reorder_rank_rows` sorts the summary table rows at the top; `reorder_cards` sorts the detail cards below. Always call both together — they are independent and each can drift independently. `add_stock`, `update_stock`, and `move_stock` already call `reorder_cards` internally, but they do NOT call `reorder_rank_rows`. If you ever manually splice a rank row or add/move a stock in multiple steps, run `reorder_rank_rows(html)` after saving to keep the table in sync.
- **`reorder_rank_rows` uses `min(positions)` as section_start** — it finds the earliest rank row position across all tickers, not the rank-#1 row. This is the same fix applied to `reorder_cards`. Without this, swapping the current #1 ticker (whose row appears later in the file) would use the wrong section start, causing the displaced row to survive in `html[:first_start]` and appear duplicated after re-ordering. If you see a ticker's rank row appearing twice after a swap, call `reorder_rank_rows(html)` — it deduplicates by keeping each ticker's last occurrence.
- For growth-decay scenarios: pass the **effective CAGR** (the average over 10yr) as `growth` in the Scenario, not the starting rate. The adj return formula uses `(1+growth/100)^10` directly.
- After any update: publish to the artifact URL above with `label` describing what changed.
- Hold_check stocks have custom probabilities (e.g., NOW 26/49/25, MSFT 7/61/32, META 16/52/32, TSM 25/55/20). These are preserved in the card's expected formula. Do NOT assume 20/55/25 for hold_check stocks — always read the formula from the card.
- Exit PEs were checked against projected revenue at exit ((1+g)^10 × current_rev). Caps: <$50B→35×, $50-150B→26×, $150-400B→22×, >$400B→18×. Exceptional companies allowed up to 20% above cap.
