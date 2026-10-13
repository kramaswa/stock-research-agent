#!/usr/bin/env python3
"""
dashboard_update.py — helpers for updating the stock ranking dashboard.

Called by Claude Code in the stock-research-agent project. Not a CLI tool —
import the functions and use add_stock / update_stock / move_stock.

Artifact URL: https://claude.ai/artifact/YTRPRTL1gdHr4HuXFWqTAf
HTML file:    ranking.html  (project root)
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
import math
from datetime import date as _date

HTML_PATH = Path(__file__).parent / "ranking.html"

# ── dp tier table (large-base discount applied by hold_check model) ────────────
# revenue ($B)  → dp, base_cap, bull_cap
DP_TIERS = [
    (0,   10,  1,  None, None),
    (10,  50,  3,  None, None),
    (50,  150, 5,  18.0, 22.0),
    (150, 400, 7,  14.0, 18.0),
    (400, 1e9, 10, 11.0, 15.0),
]

def dp_for_revenue(revenue_b: float) -> dict:
    for lo, hi, dp, base_cap, bull_cap in DP_TIERS:
        if lo <= revenue_b < hi:
            return {"dp": dp, "base_cap": base_cap, "bull_cap": bull_cap}
    return {"dp": 10, "base_cap": 11.0, "bull_cap": 15.0}


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class Scenario:
    prob: int           # probability %
    growth: float       # EPS CAGR %
    exit_pe: int        # exit P/E multiple
    price_target: int   # approximate $ price target
    ret: float          # adjusted return ×
    rationale: str      # brief description for the table cell

@dataclass
class StockEntry:
    ticker: str
    company: str        # e.g. "Advanced Micro Devices — NASDAQ"
    price: float        # current entry price $
    fwd_pe: float       # forward P/E
    ntm_eps: float      # NTM EPS $
    dilution: float     # dilution factor over 10yr (e.g. 0.95)
    rank: int           # target rank position
    bear: Scenario
    base: Scenario
    bull: Scenario
    expected: float     # probability-weighted expected return ×
    chips: list[str] = field(default_factory=list)  # info chip texts
    warns: list[str] = field(default_factory=list)  # warning chip texts
    note: str = ""      # long-form analysis note
    source_note: str = ""  # e.g. "hold_check at ~$490 entry" or "manual estimate"
    rev_cagr: float | None = None   # revenue CAGR %, if known; else proxied from EPS growth
    allow_ps_expansion: bool = False  # opt out of the implied price/sales guard


# ── Entry validation (eval pass) ──────────────────────────────────────────────

def validate_entry(e: StockEntry, expected_tol: float = 3.0, adj_tol: float = 25.0,
                   skip_prob_check: bool = False) -> None:
    """Validate a StockEntry before writing to the dashboard.

    Raises ValueError with a clear explanation if anything is wrong.
    Called automatically by add_stock / update_stock / move_stock.

    Checks:
      1. Probability constraints: bear 15-40%, base 40-60%, bull 15-40%, sum=100%
         (pass skip_prob_check=True for hold_check results with unusual distributions)
      2. Weighted expected matches sum(prob_i * ret_i) within expected_tol %
      3. Each scenario adj return plausibility:
         formula = (NTM_EPS × (1+g/100)^10 × exit_PE × dilution) / price
         within adj_tol % of stated ret (loose tolerance accommodates growth-decay entries
         where `growth` is the effective CAGR, not the simple 10-yr flat rate)
    """
    b, s, u = e.bear, e.base, e.bull

    # ── 1. Probability constraints ─────────────────────────────────────────────
    total = b.prob + s.prob + u.prob
    if total != 100:
        raise ValueError(f"[{e.ticker}] Probs sum to {total}%, must be 100%")
    if not skip_prob_check:
        if not (15 <= b.prob <= 40):
            raise ValueError(f"[{e.ticker}] Bear prob {b.prob}% outside [15%, 40%]")
        if not (40 <= s.prob <= 60):
            raise ValueError(f"[{e.ticker}] Base prob {s.prob}% outside [40%, 60%]")
        if not (15 <= u.prob <= 40):
            raise ValueError(f"[{e.ticker}] Bull prob {u.prob}% outside [15%, 40%]")

    # ── 2. Weighted expected ────────────────────────────────────────────────────
    weighted = b.prob/100 * b.ret + s.prob/100 * s.ret + u.prob/100 * u.ret
    err_pct = abs(weighted - e.expected) / max(e.expected, 0.01) * 100
    if err_pct > expected_tol:
        raise ValueError(
            f"[{e.ticker}] Expected return mismatch:\n"
            f"  Stated:   {e.expected:.3f}×\n"
            f"  Computed: {b.prob/100:.2f}×{b.ret:.3f} + "
            f"{s.prob/100:.2f}×{s.ret:.3f} + "
            f"{u.prob/100:.2f}×{u.ret:.3f} = {weighted:.3f}×\n"
            f"  Error:    {err_pct:.1f}% (tolerance {expected_tol}%)"
        )

    # ── 3. Adj return plausibility per scenario ────────────────────────────────
    for label, sc in [("Bear", b), ("Base", s), ("Bull", u)]:
        formula = (e.ntm_eps * (1 + sc.growth/100)**10 * sc.exit_pe * e.dilution) / e.price
        err = abs(formula - sc.ret) / max(sc.ret, 0.01) * 100
        if err > adj_tol:
            raise ValueError(
                f"[{e.ticker}] {label} adj return plausibility check failed:\n"
                f"  Stated:  {sc.ret:.3f}×\n"
                f"  Formula: ({e.ntm_eps} × (1+{sc.growth}%)^10 × {sc.exit_pe}× × {e.dilution}) / {e.price} = {formula:.3f}×\n"
                f"  Error:   {err:.1f}% (tolerance {adj_tol}%)\n"
                f"  Hint: if this scenario uses growth decay, pass the effective CAGR as `growth`, not the starting rate."
            )

    # ── 4. Implied price/sales guard (blocking) ────────────────────────────────
    _check_ps_expansion(e)

    # ── 5. Sanity checks (warnings, not errors) ────────────────────────────────
    _sanity_check(e)

    # ── Summary (always print so it appears in Claude Code output) ────────────
    print(
        f"[validate_entry] {e.ticker} OK — "
        f"probs {b.prob}/{s.prob}/{u.prob}%, "
        f"weighted {weighted:.3f}× vs stated {e.expected:.3f}× (err {err_pct:.1f}%), "
        f"adj returns within {adj_tol}% tolerance"
    )


# ── Implied price/sales guard (blocking) ──────────────────────────────────────
# The revenue-tier exit-PE caps below check the multiple against company size,
# but for a sub-$50B-revenue company they permit a 35x base / 52x bull exit.
# For a low-margin manufacturer that implies a sales multiple no such business
# has ever sustained, which is how MKSI (bull implied 10.3x sales, ~ASML's
# multiple, for a subsystems supplier) and TTMI (9.1x sales for PCB fabrication)
# passed validation. This check closes that gap.
#
#   exit_P/S / today_P/S = (adj_return / dilution^2) / (1 + rev_cagr)^10
#
# Derivation: future_cap/today_cap = adj_return / dilution^2, because the raw
# price multiple is adj_return/dilution and the share count grows by 1/dilution.
# Dividing by revenue growth gives the change in the sales multiple. Needs no
# share count or market cap -- only fields the model already carries.
_PS_EXPANSION_CAP_BASE = 1.50
_PS_EXPANSION_CAP_BULL = 2.25

# A base case should not underwrite a re-rating; a bull may assume a moderate one.
_EXIT_PE_RERATE_CAP_BASE = 1.15
_EXIT_PE_RERATE_CAP_BULL = 1.40

# Sustained 10yr EPS CAGR ceilings, applied only above $1B revenue.
_EPS_CAGR_CAP_BASE = 13.0
_EPS_CAGR_CAP_BULL = 17.5


# Clauses describing a forward, partial or non-company figure -- never current
# annual revenue. Forward fiscal years are caught separately, year-aware, because
# 'FY2026E' is this year's estimate while 'FY2027E' is a projection.
_REV_SKIP = re.compile(r'projected|project\b|guide|guidance|target|TAM|first-year|'
                       r'by 20\d\d|exit|\bQ[1-4]\b|quarter', re.I)
_REV_FWD_YEAR = re.compile(r'(?:FY)?(\d{4})E\b')
# "<something> revenue/rev $12.2B", "$44-46B" ranges, "$342M" all accepted.
_REV_PAT = re.compile(r'(?:revenue|rev)\b[^$]{0,26}\$\s*([\d.]+)\s*(?:[-–]\s*([\d.]+))?\s*([BM])', re.I)
_REV_ANNUALIZED = re.compile(r'annuali[sz]ed\s*~?\$\s*([\d.]+)\s*([BM])', re.I)


def _revenue_from_chips(chips) -> float | None:
    """Current annual revenue in $B from the info chips, or None.

    Tolerates the shapes actually used across the table -- 'Revenue: $3.3B',
    'Rev: $0.6B', 'FY2026 revenue $39.1B', '2026 revenue ~$44-46B' (range, taken
    at the midpoint) and 'Q1 rev $342M; annualized ~$1.4B' (the annualized figure
    wins over the quarterly one). Clauses naming a forward figure -- '2027E
    revenue ~$88B', anything marked projected/guide/target/TAM -- are skipped,
    because every caller wants today's revenue, not the exit-year number.
    """
    def scaled(v, unit):
        return v / 1000 if unit.upper() == 'M' else v

    this_year = _date.today().year
    for chip in (chips or []):
        # split on bullets, semicolons, pipes, ' -- ', and commas that do not sit
        # inside a number, so one bad half of a clause cannot veto the good half
        for clause in re.split(r'[·;|]|\s--\s|,(?!\d)', chip):
            if _REV_SKIP.search(clause):
                continue
            fwd = _REV_FWD_YEAR.search(clause)
            if fwd and int(fwd.group(1)) > this_year:
                continue
            m = _REV_ANNUALIZED.search(clause)
            if m:
                return scaled(float(m.group(1)), m.group(2))
            m = _REV_PAT.search(clause)
            if m:
                lo = float(m.group(1))
                hi = float(m.group(2)) if m.group(2) else None
                return scaled((lo + hi) / 2 if hi else lo, m.group(3))
    return None


def implied_ps_expansion(adj_return: float, dilution: float, eps_growth_pct: float,
                         rev_cagr_pct: float | None = None) -> float:
    """Exit price/sales expressed as a multiple of today's price/sales.

    When rev_cagr_pct is unknown, revenue is proxied at 75% of EPS growth. EPS
    compounding faster than revenue is margin expansion, and a scenario claiming
    high EPS growth is implicitly claiming it; proxying revenue too close to EPS
    inflates the denominator and lets the very cases this guard exists to catch
    slip through. Pass rev_cagr explicitly whenever it is known.
    """
    if rev_cagr_pct is None:
        rev_cagr_pct = eps_growth_pct * 0.75
    return (adj_return / dilution ** 2) / ((1 + rev_cagr_pct / 100) ** 10)


def _check_ps_expansion(e: StockEntry) -> None:
    """Raise if an exit multiple implies an implausible re-rating.

    Two independent tests, because they catch different failure modes:
      1. implied price/sales expansion -- catches multiple and growth inflating together
      2. exit P/E vs entry P/E         -- catches underwriting a re-rating outright

    Neither is a perfect oracle. A scenario can still carry an over-aggressive EPS
    CAGR at a defensible multiple and pass both; growth remains a judgment call.
    """
    if e.allow_ps_expansion:
        return
    problems = []

    for name, sc, cap in (("Base", e.base, _PS_EXPANSION_CAP_BASE),
                          ("Bull", e.bull, _PS_EXPANSION_CAP_BULL)):
        x = implied_ps_expansion(sc.ret, e.dilution, sc.growth, e.rev_cagr)
        if x > cap:
            problems.append(
                f"  {name}: exit P/S = {x:.2f}x today's P/S  (cap {cap:.2f}x)\n"
                f"    ret {sc.ret:.2f}x, exit PE {sc.exit_pe}x, "
                f"EPS CAGR {sc.growth:.1f}%, dilution {e.dilution:.2f}x"
            )

    if e.fwd_pe and e.fwd_pe > 0:
        for name, sc, cap in (("Base", e.base, _EXIT_PE_RERATE_CAP_BASE),
                              ("Bull", e.bull, _EXIT_PE_RERATE_CAP_BULL)):
            ratio = sc.exit_pe / e.fwd_pe
            if ratio > cap:
                problems.append(
                    f"  {name}: exit PE {sc.exit_pe}x is {ratio:.2f}x the entry PE "
                    f"{e.fwd_pe:.1f}x  (cap {cap:.2f}x)\n"
                    f"    this underwrites a re-rating -- legitimate only with a stated catalyst"
                )

    # Sustained EPS CAGR. Companies past ~$1B of revenue very rarely compound EPS
    # above these rates for a full decade; below that threshold small-base growth
    # is common enough that the cap would misfire.
    rev_b = _revenue_from_chips(e.chips)
    if rev_b is not None and rev_b >= 1.0:
        for name, sc, cap in (("Base", e.base, _EPS_CAGR_CAP_BASE),
                              ("Bull", e.bull, _EPS_CAGR_CAP_BULL)):
            if sc.growth > cap:
                problems.append(
                    f"  {name}: EPS CAGR {sc.growth:.1f}% over 10yr exceeds {cap:g}% "
                    f"for a ${rev_b:.1f}B-revenue company\n"
                    f"    sustaining this for a decade from an established base is a "
                    f"strong claim -- state the driver or lower it"
                )

    if problems:
        raise ValueError(
            f"{e.ticker}: exit multiple implies an implausible re-rating.\n"
            + "\n".join(problems)
            + "\n\n  Fix by lowering the exit P/E, lowering growth, or -- if a genuine "
              "re-rating thesis justifies it (a de-rated name recovering, or a real "
              "business-model shift) -- set allow_ps_expansion=True and add a `warns` "
              "chip stating the catalyst.\n"
              "  Pass rev_cagr=<pct> when revenue growth differs materially from EPS growth."
        )


# ── Sanity checks (warnings printed but not raising errors) ──────────────────

# Exit PE caps by revenue tier — base exit PE should not exceed these
_EXIT_PE_CAPS = [
    (0,   50,  35),   # < $50B: base exit PE up to 35×
    (50,  150, 26),   # $50–150B: base exit PE up to 26×
    (150, 400, 22),   # $150–400B: base exit PE up to 22×
    (400, 1e9, 18),   # > $400B: base exit PE up to 18×
]

def _sanity_check(e: StockEntry) -> None:
    """Print warnings for entries that pass formula checks but have
    implausible parameters.  Called automatically by validate_entry()."""
    warnings = []
    b, s, u = e.bear, e.base, e.bull

    # 1. Exit PE scale check
    rev_b = _revenue_from_chips(e.chips)
    if rev_b is not None:
        for lo, hi, cap in _EXIT_PE_CAPS:
            if lo <= rev_b < hi:
                if s.exit_pe > cap:
                    warnings.append(
                        f"Base exit PE {s.exit_pe}x exceeds {cap}x cap "
                        f"for ${rev_b:.0f}B revenue company"
                    )
                if u.exit_pe > cap + 8:
                    warnings.append(
                        f"Bull exit PE {u.exit_pe}x very high "
                        f"for ${rev_b:.0f}B revenue company"
                    )
                break

    # 1b. Projected-revenue PE check (checks PE against company size AT EXIT)
    if rev_b is not None:
        proj_rev_base = rev_b * (1 + s.growth / 100) ** 10
        proj_rev_bull = rev_b * (1 + u.growth / 100) ** 10
        for lo, hi, cap in _EXIT_PE_CAPS:
            if lo <= proj_rev_base < hi:
                premium_cap = cap * 1.2
                if s.exit_pe > premium_cap:
                    warnings.append(
                        f"Base exit PE {s.exit_pe}x exceeds {premium_cap:.0f}x "
                        f"(20% premium on {cap}x cap) for projected "
                        f"${proj_rev_base:.0f}B revenue at exit"
                    )
                break
        for lo, hi, cap in _EXIT_PE_CAPS:
            if lo <= proj_rev_bull < hi:
                if u.exit_pe > cap * 1.5:
                    warnings.append(
                        f"Bull exit PE {u.exit_pe}x exceeds {cap * 1.5:.0f}x "
                        f"for projected ${proj_rev_bull:.0f}B bull revenue at exit"
                    )
                break

    # 2. Expected return vs starting PE plausibility
    if e.fwd_pe and e.fwd_pe > 0:
        if e.fwd_pe > 50 and e.expected > 3.0:
            warnings.append(
                f"Expected {e.expected:.2f}x high for {e.fwd_pe:.0f}x fwd PE "
                f"(growth already priced in)"
            )
        if e.fwd_pe > 100 and e.expected > 2.0:
            warnings.append(
                f"Expected {e.expected:.2f}x suspicious at {e.fwd_pe:.0f}x PE"
            )
        if e.fwd_pe < 10 and e.expected < 1.5:
            warnings.append(
                f"Expected {e.expected:.2f}x low for cheap {e.fwd_pe:.1f}x PE "
                f"(verify growth rates)"
            )

    # 3. Bear return floor — 10yr bear > 8× implies no realistic downside
    if b.ret > 8.0:
        warnings.append(
            f"Bear return {b.ret:.2f}x > 8x — bear case implausibly high"
        )

    # 4. Expected > 4× — rare, flag for review
    if e.expected > 4.0:
        warnings.append(
            f"Expected {e.expected:.2f}x > 4x — verify this is not a data error"
        )

    for w in warnings:
        print(f"[sanity_check] {e.ticker} WARNING: {w}")


def sanity_check_card(html: str, ticker: str) -> list[str]:
    """Parse a stock's card from the HTML and run sanity checks.
    Returns a list of warning strings (empty = all clear)."""
    warnings = []

    # Find the card for this ticker
    pat = re.compile(
        rf'<!--\s*{re.escape(ticker)}\s*-->.*?<div class="card">(.*?)</div>\s*\n\s*\n',
        re.DOTALL
    )
    m = pat.search(html)
    if not m:
        pat2 = re.compile(
            rf'class="ticker">{re.escape(ticker)}</span>.*?</div>\s*\n\s*\n',
            re.DOTALL
        )
        m = pat2.search(html)
    if not m:
        return [f"Card not found for {ticker}"]

    card = m.group(0)

    # Extract expected value
    exp_m = re.search(r'val-exp["\']?>~?([\d.]+)', card)
    expected = float(exp_m.group(1)) if exp_m else 0

    # Extract scenario returns (match the ×-suffixed return, not the growth %)
    bear_m = re.search(r'val-bear["\']?>~?([\d.]+)\xd7', card)
    base_m = re.search(r'val-base["\']?>~?([\d.]+)\xd7', card)
    bull_m = re.search(r'val-bull["\']?>~?([\d.]+)\xd7', card)
    bear_ret = float(bear_m.group(1)) if bear_m else 0
    base_ret = float(base_m.group(1)) if base_m else 0
    bull_ret = float(bull_m.group(1)) if bull_m else 0

    # Extract PE from price-sub
    pe_m = re.search(r'fwd P/E[:\s~]*(\d+\.?\d*)', card)
    fwd_pe = float(pe_m.group(1)) if pe_m else 0

    # Extract revenue from chip
    rev_m = re.search(r'Revenue:?\s*~?\$?([\d.]+)([BM])', card)
    rev_b = 0
    if rev_m:
        rev_b = float(rev_m.group(1))
        if rev_m.group(2) == 'M':
            rev_b /= 1000

    # Extract exit PEs from scenario rows
    base_pe_m = re.search(r'row-base.*?/\s*(\d+)', card, re.DOTALL)
    bull_pe_m = re.search(r'row-bull.*?/\s*(\d+)', card, re.DOTALL)
    base_exit_pe = int(base_pe_m.group(1)) if base_pe_m else 0
    bull_exit_pe = int(bull_pe_m.group(1)) if bull_pe_m else 0

    # Check 1: Exit PE scale (current revenue)
    if rev_b > 0 and base_exit_pe > 0:
        for lo, hi, cap in _EXIT_PE_CAPS:
            if lo <= rev_b < hi:
                if base_exit_pe > cap:
                    warnings.append(
                        f"Base exit PE {base_exit_pe}x exceeds {cap}x cap "
                        f"for ${rev_b:.0f}B revenue"
                    )
                break

    # Check 1b: Exit PE scale (projected revenue at exit)
    if rev_b > 0 and base_exit_pe > 0:
        base_section = re.search(r'row-base.*?row-bull', card, re.DOTALL)
        base_g = None
        if base_section:
            g_m = re.search(r'(-?[\d.]+)%\s*(?:EPS|eff|\()', base_section.group(0))
            if g_m:
                base_g = float(g_m.group(1))
        if base_g and base_g > 0:
            proj_rev = rev_b * (1 + base_g / 100) ** 10
            for lo, hi, cap in _EXIT_PE_CAPS:
                if lo <= proj_rev < hi:
                    premium_cap = cap * 1.2
                    if base_exit_pe > premium_cap:
                        warnings.append(
                            f"Base exit PE {base_exit_pe}x exceeds {premium_cap:.0f}x "
                            f"(projected ${proj_rev:.0f}B rev at exit)"
                        )
                    break

    # Check 2: Expected vs PE
    if fwd_pe > 50 and expected > 3.0:
        warnings.append(
            f"Expected {expected:.2f}x high for {fwd_pe:.0f}x PE"
        )
    if fwd_pe > 100 and expected > 2.0:
        warnings.append(
            f"Expected {expected:.2f}x suspicious at {fwd_pe:.0f}x PE"
        )

    # Check 3: Bear too optimistic (10yr bear > 8× implies no realistic downside)
    if bear_ret > 8.0:
        warnings.append(f"Bear {bear_ret:.2f}x > 8x — bear case implausibly high")

    # Check 4: Expected > 4×
    if expected > 4.0:
        warnings.append(f"Expected {expected:.2f}x > 4x — verify data")

    return warnings


def sanity_check_all(html: str) -> dict[str, list[str]]:
    """Run sanity checks on all ranked stocks. Returns {ticker: [warnings]}."""
    results = {}
    for _rank, ticker in get_rank_order(html):
        warns = sanity_check_card(html, ticker)
        if warns:
            results[ticker] = warns
    return results


# ── File I/O ───────────────────────────────────────────────────────────────────

def load_html(path: Path = HTML_PATH) -> str:
    return Path(path).read_text(encoding="utf-8")

def save_html(html: str, path: Path = HTML_PATH) -> None:
    Path(path).write_text(html, encoding="utf-8")


# ── Rank table parsing ─────────────────────────────────────────────────────────

# rticker spans may have inline styles (e.g. TSLA has color:#b45309)
_RANK_ROW_RE = re.compile(
    r'<span class="rank">#(\d+)</span>\s*\n\s*<span class="rticker"[^>]*>(\w+)</span>'
)

def get_rank_order(html: str) -> list[tuple[int, str]]:
    """Return [(rank, ticker), ...] from the rank table, sorted by rank."""
    return sorted(
        [(int(m.group(1)), m.group(2)) for m in _RANK_ROW_RE.finditer(html)],
        key=lambda x: x[0],
    )


# ── Rank renumbering ───────────────────────────────────────────────────────────

def _find_rank_span(html: str, rank: int, ticker: str) -> re.Match:
    """Find the rank span for a specific (rank, ticker) pair."""
    pat = (
        r'(<span class="rank">)#' + str(rank)
        + r'(</span>\s*\n\s*<span class="rticker"[^>]*>)'
        + re.escape(ticker) + r'(</span>)'
    )
    m = re.search(pat, html)
    if not m:
        raise ValueError(f"Rank #{rank} / {ticker} not found in rank table")
    return m

def _set_rank_number(html: str, old_rank: int, ticker: str, new_rank: int) -> str:
    m = _find_rank_span(html, old_rank, ticker)
    return html[:m.start(1)] + m.group(1) + f"#{new_rank}" + m.group(2) + ticker + m.group(3) + html[m.end(3):]

def shift_ranks(html: str, from_rank: int, delta: int, skip: str = "", until: int = None) -> str:
    """Shift ranks >= from_rank (and <= until if given) by delta. Process order avoids collisions."""
    affected = [(r, t) for r, t in get_rank_order(html)
                if r >= from_rank and t != skip and (until is None or r <= until)]
    # Incrementing: process high→low to avoid overwriting; decrementing: low→high
    affected.sort(key=lambda x: x[0], reverse=(delta > 0))
    for rank, ticker in affected:
        html = _set_rank_number(html, rank, ticker, rank + delta)
    return html


# ── Rank row find/remove/insert ────────────────────────────────────────────────

def _find_rank_row_div(html: str, ticker: str) -> tuple[int, int]:
    """Return (start, end) byte offsets of the rank-row div for ticker."""
    pat = r'<span class="rticker"[^>]*>' + re.escape(ticker) + r'</span>'
    m = re.search(pat, html)
    if not m:
        raise ValueError(f"Ticker {ticker} not found in rank table")
    start = html.rfind('<div class="rank-row"', 0, m.start())
    if start == -1:
        raise ValueError(f"rank-row div not found before {ticker}")
    # Find the matching closing </div>
    end = html.index("</div>", m.end()) + len("</div>")
    # Eat the trailing newline if present
    if end < len(html) and html[end] == "\n":
        end += 1
    return start, end

def remove_rank_row(html: str, ticker: str) -> str:
    start, end = _find_rank_row_div(html, ticker)
    return html[:start] + html[end:]

def _voo_ref_row_start(html: str) -> int:
    marker = '  <div class="rank-row" style="border-top:2px dashed var(--border);'
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("VOO reference row not found")
    return idx

def insert_rank_row_before(html: str, before_ticker: str, row_html: str) -> str:
    start, _ = _find_rank_row_div(html, before_ticker)
    return html[:start] + row_html + "\n" + html[start:]

def insert_rank_row_at_end(html: str, row_html: str) -> str:
    idx = _voo_ref_row_start(html)
    return html[:idx] + row_html + "\n" + html[idx:]

def reorder_rank_rows(html: str) -> str:
    """Reorder rank table rows to match rank number order (ascending).
    Leaves VOO/SCHG reference rows (dashed border) untouched."""
    rank_order = get_rank_order(html)  # list of (rank, ticker) sorted by rank
    if not rank_order:
        return html
    # Deduplicate: keep only the last occurrence of each ticker (most recently placed)
    seen = {}
    for rank, ticker in rank_order:
        seen[ticker] = rank
    rank_order = sorted(seen.items(), key=lambda x: x[1])  # [(ticker, rank), ...]
    rank_order = [(r, t) for t, r in rank_order]            # back to [(rank, ticker), ...]

    # Extract each rank row's text (last occurrence for each ticker)
    rows = {}
    for _, ticker in rank_order:
        start, end = _find_rank_row_div(html, ticker)
        rows[ticker] = html[start:end]

    # Use EARLIEST row position as section start (same fix as reorder_cards)
    positions = [_find_rank_row_div(html, t)[0] for _, t in rank_order]
    first_start = min(positions)
    voo_start = _voo_ref_row_start(html)
    ordered = "".join(rows[t] + "\n" for _, t in rank_order)
    return html[:first_start] + ordered + html[voo_start:]


# ── Card find/remove/insert ────────────────────────────────────────────────────

def _find_card_bounds(html: str, ticker: str) -> tuple[int, int]:
    """Return (start, end) of the full card block including its <!-- TICKER --> comment."""
    comment = f"\n<!-- {ticker} -->\n"
    start = html.find(comment)
    if start == -1:
        raise ValueError(f"Card comment <!-- {ticker} --> not found")
    # Find the next card comment to determine the end
    after = html.find("\n<!-- ", start + len(comment))
    if after != -1:
        end = after
    else:
        # Last card before the closing section
        end = html.rfind("\n\n</div>", start)
        if end == -1:
            end = len(html)
    return start, end

def remove_card(html: str, ticker: str) -> str:
    start, end = _find_card_bounds(html, ticker)
    return html[:start] + html[end:]

def insert_card_before(html: str, before_ticker: str, card_html: str) -> str:
    start, _ = _find_card_bounds(html, before_ticker)
    return html[:start] + card_html + html[start:]

def insert_card_at_end(html: str, card_html: str) -> str:
    # Insert before <!-- VOO -->
    return insert_card_before(html, "VOO", card_html)


# ── HTML generation ────────────────────────────────────────────────────────────

def _ret_class(expected: float) -> str:
    if expected >= 3.5:
        return "ret-high"
    elif expected >= 2.45:
        return "ret-mid"
    else:
        return "ret-low"

def generate_rank_row(rank: int, e: StockEntry) -> str:
    rc = _ret_class(e.expected)
    vs_sp = f"expected ~{e.expected:.2f}× vs S&P 2.55×"
    pe_str = f"~{e.fwd_pe:.0f}×" if e.fwd_pe is not None else "N/A"
    rationale = (
        f"~${e.price:.0f} · fwd P/E {pe_str} · "
        f"bear {e.bear.ret:.2f}×, base {e.base.ret:.2f}×, bull {e.bull.ret:.2f}×, "
        f"expected ~{e.expected:.2f}×"
    )
    if e.source_note:
        rationale += f" — {e.source_note}"
    return (
        f'  <div class="rank-row">\n'
        f'    <span class="rank">#{rank}</span>\n'
        f'    <span class="rticker">{e.ticker}</span>\n'
        f'    <span class="rationale">{rationale}</span>\n'
        f'    <span class="{rc}">~{e.expected:.2f}×</span>\n'
        f'    <span class="vs-sp">{vs_sp}</span>\n'
        f'  </div>'
    )

def generate_card(e: StockEntry) -> str:
    b, s, u = e.bear, e.base, e.bull
    formula = (
        f"{b.prob/100:.2f}×{b.ret:.2f} + "
        f"{s.prob/100:.2f}×{s.ret:.2f} + "
        f"{u.prob/100:.2f}×{u.ret:.2f} = {e.expected:.2f}×"
    )
    if e.source_note:
        formula += f" ({e.source_note})"

    chips_html = "\n".join(f'    <span class="chip">{c}</span>' for c in e.chips)
    warns_html = "\n".join(f'    <span class="warn">{w}</span>' for w in e.warns)
    info_section = "\n".join(filter(None, [chips_html, warns_html]))

    return (
        f'\n<!-- {e.ticker} -->\n'
        f'<div class="card">\n'
        f'  <div class="card-header">\n'
        f'    <div><div class="ticker-row">'
        f'<span class="ticker">{e.ticker}</span>'
        f'<span class="company">{e.company}</span>'
        f'</div></div>\n'
        f'    <div class="price-block">'
        f'<div class="price">~${e.price:.0f}</div>'
        f'<div class="price-sub">fwd P/E {"~" + f"{e.fwd_pe:.0f}×" if e.fwd_pe is not None else "N/A (GAAP-neg)"} · NTM EPS ~${e.ntm_eps:.2f} · dilution ~{e.dilution:.2f}×</div>'
        f'</div>\n'
        f'  </div>\n'
        f'  <div class="chips">\n'
        f'{info_section}\n'
        f'  </div>\n'
        f'  <div class="scenario-row">\n'
        f'    <div class="s-header">Scenario</div>'
        f'<div class="s-header">EPS CAGR / Exit P/E</div>'
        f'<div class="s-header">Price Target</div>'
        f'<div class="s-header">Adj Return</div>\n'
        f'  </div>\n'
        f'  <div class="scenario-row row-bear">\n'
        f'    <div class="s-label"><span class="dot" style="background:var(--bear)"></span>Bear</div>\n'
        f'    <div class="s-cell val-bear">{b.growth:.1f}% ({b.rationale}) / {b.exit_pe}×</div>\n'
        f'    <div class="s-cell">~${b.price_target:,}</div>\n'
        f'    <div class="s-cell val-bear">~{b.ret:.2f}×</div>\n'
        f'  </div>\n'
        f'  <div class="scenario-row row-base">\n'
        f'    <div class="s-label"><span class="dot" style="background:var(--base)"></span>Base</div>\n'
        f'    <div class="s-cell val-base">{s.growth:.1f}% ({s.rationale}) / {s.exit_pe}×</div>\n'
        f'    <div class="s-cell">~${s.price_target:,}</div>\n'
        f'    <div class="s-cell val-base">~{s.ret:.2f}×</div>\n'
        f'  </div>\n'
        f'  <div class="scenario-row row-bull">\n'
        f'    <div class="s-label"><span class="dot" style="background:var(--bull)"></span>Bull</div>\n'
        f'    <div class="s-cell val-bull">{u.growth:.1f}% ({u.rationale}) / {u.exit_pe}×</div>\n'
        f'    <div class="s-cell">~${u.price_target:,}</div>\n'
        f'    <div class="s-cell val-bull">~{u.ret:.2f}×</div>\n'
        f'  </div>\n'
        f'  <div class="scenario-row row-exp">\n'
        f'    <div class="s-label" style="font-weight:700;">Expected</div>\n'
        f'    <div class="s-cell muted" style="grid-column:span 2;font-family:\'Inter\',sans-serif;font-size:11.5px;">'
        f'{formula}</div>\n'
        f'    <div class="s-cell val-exp">~{e.expected:.2f}×</div>\n'
        f'  </div>\n'
        f'  <div class="note">{e.note}</div>\n'
        f'</div>\n'
    )


# ── Card reordering ────────────────────────────────────────────────────────────

def _extract_all_cards(html: str) -> dict[str, str]:
    """Return {ticker: raw_card_block} preserving the \n<!-- TICKER -->\n prefix."""
    cards: dict[str, str] = {}
    pat = re.compile(r'(\n<!-- (\w+) -->\n(?:(?!\n<!-- ).)*)', re.DOTALL)
    for m in pat.finditer(html):
        cards[m.group(2)] = m.group(1)
    return cards

def reorder_cards(html: str) -> str:
    """Reorder all card blocks to match the rank table order.
    Replaces the cards section in-place; leaves everything else untouched."""
    rank_order = [t for _, t in get_rank_order(html)]
    all_cards = _extract_all_cards(html)

    if not rank_order or not all_cards:
        return html

    section_end = html.find("\n<!-- VOO -->")
    if section_end == -1:
        return html

    # Use the EARLIEST card comment in the file as the section start — not the
    # rank-#1 card, which may have been appended last by insert_card_at_end.
    positions = [html.find(f"\n<!-- {t} -->") for t in all_cards]
    positions = [p for p in positions if p != -1]
    if not positions:
        return html
    section_start = min(positions)

    ordered = "".join(all_cards[t] for t in rank_order if t in all_cards)
    return html[:section_start] + ordered + "\n" + html[section_end:]


# ── High-level operations ──────────────────────────────────────────────────────

def _next_ticker_at_or_after(html: str, rank: int) -> str | None:
    return next((t for r, t in get_rank_order(html) if r >= rank), None)

def _reorder_all(html: str) -> str:
    """Sort both the rank table rows and the card section by rank number."""
    return reorder_cards(reorder_rank_rows(html))

def add_stock(html: str, e: StockEntry) -> str:
    """Insert a new stock at e.rank, shifting all existing stocks at that rank down."""
    validate_entry(e)
    html = shift_ranks(html, e.rank, +1)
    next_t = _next_ticker_at_or_after(html, e.rank + 1)
    row = generate_rank_row(e.rank, e)
    if next_t:
        html = insert_rank_row_before(html, next_t, row)
    else:
        html = insert_rank_row_at_end(html, row)
    html = insert_card_at_end(html, generate_card(e))
    return _reorder_all(html)

def update_stock(html: str, e: StockEntry, skip_prob_check: bool = False) -> str:
    """Replace an existing stock's rank row and card (same rank position)."""
    validate_entry(e, skip_prob_check=skip_prob_check)
    html = remove_rank_row(html, e.ticker)
    html = remove_card(html, e.ticker)
    next_t = _next_ticker_at_or_after(html, e.rank)
    row = generate_rank_row(e.rank, e)
    if next_t:
        html = insert_rank_row_before(html, next_t, row)
    else:
        html = insert_rank_row_at_end(html, row)
    html = insert_card_at_end(html, generate_card(e))
    return _reorder_all(html)

def move_stock(html: str, ticker: str, new_rank: int, e: StockEntry,
               skip_prob_check: bool = False) -> str:
    """Move an existing stock to a new rank, reindexing everything in between."""
    validate_entry(e, skip_prob_check=skip_prob_check)
    old_rank = next((r for r, t in get_rank_order(html) if t == ticker), None)
    if old_rank is None:
        raise ValueError(f"{ticker} not found in rank table")
    html = remove_rank_row(html, ticker)
    html = remove_card(html, ticker)
    if old_rank < new_rank:
        html = shift_ranks(html, old_rank + 1, -1, until=new_rank)
    elif old_rank > new_rank:
        html = shift_ranks(html, new_rank, +1)
    e.rank = new_rank
    next_t = _next_ticker_at_or_after(html, new_rank + 1)
    row = generate_rank_row(new_rank, e)
    if next_t:
        html = insert_rank_row_before(html, next_t, row)
    else:
        html = insert_rank_row_at_end(html, row)
    html = insert_card_at_end(html, generate_card(e))
    return _reorder_all(html)


if __name__ == "__main__":
    html = load_html()
    print("Current rank order:")
    for rank, ticker in get_rank_order(html):
        print(f"  #{rank}: {ticker}")
