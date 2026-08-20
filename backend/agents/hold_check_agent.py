import re
import asyncio
import hashlib
from typing import Any
import anthropic
from cachetools import TTLCache


def _format_eps_estimates(raw: dict[str, Any]) -> str:
    estimates = raw.get("eps_estimates") or []
    eps_ttm = raw.get("eps_ttm")  # GAAP TTM EPS — sanity-check anchor

    if not estimates:
        fwd_pe = raw.get("forward_pe")
        price = raw.get("current_price")
        if fwd_pe and price and fwd_pe > 0:
            implied_eps = round(price / fwd_pe, 2)
            gaap_note = ""
            if eps_ttm and eps_ttm > 0 and implied_eps > 1.5 * eps_ttm:
                ratio = round(implied_eps / eps_ttm, 1)
                gaap_note = (
                    f" Note: GAAP TTM EPS is ${eps_ttm:.2f} ({ratio}× lower) — "
                    f"the gap likely reflects M&A amortization or SBC, not a cyclical peak. "
                    f"Use ${implied_eps:.2f} unless you have explicit evidence of a cyclical earnings peak."
                )
            return (
                f"\n## Ground Truth Consensus EPS Estimates\n"
                f"Not available from provider. Market-implied forward EPS: "
                f"${price:.2f} ÷ {fwd_pe:.2f}x (Finnhub forward P/E) = ${implied_eps:.2f}/share.{gaap_note} "
                f"Use ${implied_eps:.2f} as Year 0.\n"
            )
        return "\n## Ground Truth Consensus EPS Estimates\nNot available from provider — forward P/E also unavailable; do not cite a specific forward EPS figure.\n"

    lines = []
    for e in estimates[:3]:
        period = e.get("period", "?")
        # market_tools.py stores snake_case keys; fall back to camelCase for safety
        mean = e.get("eps_avg") or e.get("epsAvg") or e.get("mean")
        high = e.get("eps_high") or e.get("epsHigh") or e.get("high")
        low = e.get("eps_low") or e.get("epsLow") or e.get("low")
        n = e.get("num_analysts") or e.get("numberAnalysts") or e.get("n_analysts")
        mean_str = f"${mean:.2f}" if mean is not None else "N/A"
        range_str = f"(range ${low:.2f}–${high:.2f})" if low is not None and high is not None else ""
        n_str = f", {int(n)} analysts" if n is not None else ""
        lines.append(f"  {period}: consensus {mean_str} {range_str}{n_str}")

    first_mean = estimates[0].get("eps_avg") or estimates[0].get("epsAvg") or estimates[0].get("mean")
    peak_warning = ""
    if first_mean and eps_ttm and eps_ttm > 0 and first_mean > 2.0 * eps_ttm:
        ratio = round(first_mean / eps_ttm, 1)
        peak_warning = (
            f"\n📊 GAAP GAP NOTE: Consensus forward EPS (${first_mean:.2f}) is {ratio}× "
            f"GAAP TTM EPS (${eps_ttm:.2f}). Use the consensus non-GAAP EPS (${first_mean:.2f}) "
            f"as Year 0 — it is consistent with how exit multiples are priced in the market. "
            f"The GAAP gap most commonly reflects M&A amortization or SBC, NOT a cyclical earnings "
            f"peak. Do NOT switch to GAAP TTM as Year 0 unless you have explicit evidence of a "
            f"cyclical peak (memory semis, commodity producers) — M&A amortization is not cyclical.\n"
        )

    return (
        "\n## Ground Truth Consensus EPS Estimates\n"
        "Cite these as the consensus forward EPS — do not back-calculate or label as 'market-implied' when this data is present.\n"
        + "\n".join(lines) + peak_warning + "\n"
    )


def _format_adr_premium(raw: dict[str, Any]) -> str:
    """Build the ADR premium/discount section when live data is available."""
    adr = raw.get("adr_premium")
    if not adr:
        return ""

    p = adr.get("premium_pct")          # None when ADR ratio is unconfirmed
    ratio = adr.get("adr_ratio")
    home_per_adr = adr.get("home_per_adr_usd")

    section = (
        f"\n## Ground Truth ADR Home Exchange Pricing (live data — computed at request time)\n"
        f"This stock is a US-listed ADR of a foreign company. Live pricing:\n"
        f"- US ADR ({adr['us_ticker']}): ${adr['us_price']:.2f}\n"
        f"- Home exchange ({adr['home_ticker']} on {adr['home_exchange']}): "
        f"{adr['home_currency']} {adr['home_price']:.2f} "
        f"(≈${adr['home_price_usd']:.4f} USD per share)\n"
    )

    if ratio is not None and home_per_adr is not None and p is not None:
        direction = "premium" if p >= 0 else "discount"
        sign = "+" if p >= 0 else ""
        section += (
            f"- ADR ratio: 1 US share = {ratio:g} home share{'s' if ratio != 1 else ''}"
            f" → home equivalent per US share: ${home_per_adr:.2f}\n"
            f"- ADR {direction}: {sign}{p:.1f}%\n"
        )
        if abs(p) > 3:
            if p > 0:
                section += (
                    f"\n⚠ VERIFIED LIVE ADR PREMIUM: {sign}{p:.1f}% — use this exact figure, not any other estimate.\n"
                    f"A US investor buying {adr['us_ticker']} today pays {abs(p):.1f}% more than a home-exchange "
                    f"investor buying identical underlying shares.\n"
                    f"Premium compression to parity = ≈{abs(p):.1f}% additional downside from ${adr['us_price']:.2f} "
                    f"→ ~${home_per_adr:.2f} with NO change in business fundamentals.\n"
                    f"YOU MUST:\n"
                    f"(a) Cite '{sign}{p:.1f}% ADR premium (verified live data)' in Key Risks — not a range.\n"
                    f"(b) Include a standalone Bear Case: 'Premium compression to parity: ≈{abs(p):.1f}% additional "
                    f"downside → ~${home_per_adr:.2f} from today's ${adr['us_price']:.2f} US price.'\n"
                    f"(c) In Q4: the verified {abs(p):.1f}% premium is structural overpayment vs. home-exchange "
                    f"investors — factor it in as a hard headwind to margin of safety.\n"
                )
            else:
                section += (
                    f"\n⚠ VERIFIED LIVE ADR DISCOUNT: {sign}{p:.1f}% — use this exact figure.\n"
                    f"A US investor buying {adr['us_ticker']} today pays {abs(p):.1f}% LESS than a home-exchange investor.\n"
                    f"Note this structural advantage in the valuation section.\n"
                )
    else:
        # Ratio unconfirmed — show price data so model can reason about it
        _ht = adr["home_ticker"]
        _hc = adr["home_currency"]
        _hp = adr["home_price"]
        _hp_usd = adr["home_price_usd"]
        section += (
            f"- ADR ratio: unconfirmed (DR prospectus not in available data)\n"
            f"- Exact ADR premium/discount CANNOT be computed without the confirmed ratio.\n"
            f"\n⚠ PARTIAL LIVE DATA — HOME EXCHANGE PRICE IS VERIFIED, RATIO IS NOT:\n"
            f"The home exchange price above is live market data. "
            f"To compute the ADR premium/discount, divide by the ADR ratio (home shares per 1 US share), "
            f"which is set in the DR prospectus at listing and does not change.\n"
            f"YOU MUST still:\n"
            f"(a) Cite the live home exchange price in Key Risks: "
            f"'{_ht} trades at {_hc} {_hp:.0f} "
            f"(approx ${_hp_usd:.2f} USD/share) — ADR ratio unconfirmed, exact premium unknown.'\n"
            f"(b) Note in Q4 that the exact premium/discount is unquantified due to unconfirmed DR ratio, "
            f"but the structural risk of premium compression exists regardless.\n"
        )
    return section


def build_raw_metrics_block(raw: dict[str, Any]) -> str:
    """Build a concise ground-truth block from raw Finnhub data to anchor the hold check."""
    def fx(v, suffix="x") -> str:
        return f"{v:.2f}{suffix}" if v is not None else "N/A"

    eps_g = raw.get("eps_growth_ttm_yoy")
    peg_note = (
        f"  ← EPS declining {eps_g:.1f}% YoY — PEG is INVALID as a cheapness signal"
        if eps_g is not None and eps_g < 0 else ""
    )
    fcf_ps = raw.get("fcf_per_share_ttm")
    fcf_line = f"${fcf_ps:.2f}" if fcf_ps is not None else "N/A (null — data unavailable from provider; do not speculate on the cause)"

    # Detect financial sector companies where EV/FCF and EV/EBITDA are structurally distorted
    sector_lower = (raw.get("sector") or "").lower()
    _fin_keywords = ("bank", "financ", "insur", "credit", "lending", "brokerage", "capital market")
    is_financial = any(kw in sector_lower for kw in _fin_keywords)
    fin_warning = (
        "  ← DISTORTED FOR BANK/FINTECH: loan originations inflate cash outflows making this metric misleading; DO NOT use as a valuation signal"
        if is_financial else ""
    )
    ebitda_warning = (
        "  ← LESS MEANINGFUL FOR BANK/FINTECH: interest income/expense is core operations, not below the line; prefer P/E + P/Book + ROE"
        if is_financial else ""
    )

    # Detect data-sparse situations (recent IPO, thin coverage, private company just gone public)
    _key_metrics = [
        raw.get("ev_to_fcf_ttm"), raw.get("ev_ebitda_ttm"), raw.get("forward_pe"),
        raw.get("pe_ttm"), raw.get("return_26w_pct"), raw.get("return_52w_pct"),
        raw.get("revenue_growth_ttm_yoy"), raw.get("eps_growth_ttm_yoy"), raw.get("fcf_per_share_ttm"),
    ]
    null_count = sum(1 for v in _key_metrics if v is None)
    returns_null = raw.get("return_26w_pct") is None and raw.get("return_52w_pct") is None
    if null_count >= 5 or returns_null:
        data_caveat = (
            "⚠ LIMITED DATA WARNING: Most quantitative metrics for this stock are unavailable from "
            "the data provider. This is typical for recently IPO'd companies or stocks without "
            "sufficient trading history. You MUST:\n"
            "1. State data limitations explicitly in each section rather than filling gaps with estimates\n"
            "2. NOT cite pre-IPO private valuations, pre-IPO ARR figures, or pre-IPO financial data "
            "as if they were current public data — pre-IPO figures reflect a different capital "
            "structure and are not comparable to the post-IPO public market cap\n"
            "3. NOT cite specific peak prices, 52-week lows, or percentage drawdowns if price return "
            "data is null — you cannot verify these from the provided data\n"
            "4. Lower your confidence level throughout — use language like 'limited data available' "
            "and 'cannot verify from provided data' rather than presenting estimates as facts\n\n"
        )
    else:
        data_caveat = ""

    # Format insider transactions directly so the hold check agent sees raw data
    # regardless of what the quant agent narrative says
    insider_txns = raw.get("insider_transactions") or []
    if insider_txns:
        insider_lines = []
        for t in insider_txns:
            name = t.get("name", "Unknown")
            ttype = t.get("type", "?")
            shares = t.get("shares")
            price = t.get("price")
            date = t.get("transaction_date", "")
            share_str = f"{int(shares):,}" if shares is not None else "?"
            price_str = f"${price:.2f}" if price is not None else "?"
            insider_lines.append(f"  {date}  {ttype:4s}  {share_str} shares @ {price_str}  ({name})")
        insider_section = (
            f"\n## Ground Truth Insider Transactions (past 90 days — {len(insider_txns)} total)\n"
            "These are sourced directly from the raw data. "
            "Do NOT state that insider transactions are empty or unavailable if this list is non-empty. "
            "For ADR stocks, transaction prices may be in the local-listing currency (e.g., NT$ for TSM); "
            "cite them and note the exchange — the direction (buy vs. sell) is the relevant signal.\n"
            + "\n".join(insider_lines) + "\n"
        )
    else:
        insider_section = "\n## Ground Truth Insider Transactions\nNo transactions in the past 90 days.\n"

    return (
        data_caveat +
        "## Ground Truth Valuation Metrics\n"
        "These figures come directly from the data provider (Finnhub). "
        "Cite them verbatim in your Valuation section. "
        "Do not substitute a narrower range or a different estimate. "
        "If a metric looks surprising, engage with it directly — do not omit it.\n\n"
        "⚠ CONFLICT RULE: The quant analysis below may cite slightly different values due to rounding "
        "or computational differences. When citing any metric in your analysis, USE THE VALUE FROM THIS "
        "BLOCK — not the value from the quant narrative. Example: if the quant analysis says EV/EBITDA "
        "is 43.3x but this block shows 44.66x, your Valuation section must state 44.66x. Same for price "
        "returns — use the 26-week and 52-week returns from this block, not the quant analysis.\n\n"
        "⚠ ADR / FOREIGN ISSUER DETECTION AND RULES: If the SEC Earnings Release section in the analysis context is labeled '6-K' (rather than '8-K'), the company is a foreign private issuer reporting to the SEC — this is a definitive signal that the US-listed ticker is a foreign company's ADR or US-listed depositary shares (e.g., SK Hynix filing 6-K means SKHY is a US ADR of a Korean company). Apply ALL of the following rules when a 6-K is present:\n\n"
        "1. RETURN DATA CAVEAT: Finnhub's price return data for the US ticker reflects the underlying home-exchange price history, not the US ADR's actual trading history. In the Pre-Check, note: 'Return figures reflect [company]'s performance on its home exchange ([exchange]), not the US ADR holder's experience since US listing. A US investor who bought the ADR at its US launch date has seen a different, typically shorter return profile.' The Q1 flag is still directionally meaningful (the underlying business has appreciated), but do not imply a US ADR investor is sitting on returns they could not have captured.\n\n"
        "2. ADR PREMIUM RISK (mandatory — applies regardless of whether news mentions it): Newly listed US ADRs routinely trade at a premium of 10–50%+ to their underlying home-exchange shares during early trading. This premium can compress to zero at any time regardless of underlying business performance, representing pure structural downside entirely separate from the business thesis. You MUST: (a) If a 'Ground Truth ADR Premium / Discount' section appears in this block, use the EXACT verified percentage from that section in Key Risks — not a range, not 'may trade at a premium.' If no live section is present, flag that premium compression risk exists and quantification requires live home-exchange price data. (b) If a Ground Truth ADR Premium / Discount section is present, include a standalone Bear Case using those verified figures. If no live section is present but news mentions a specific premium, include it labeled [unverified from news] — never use a training-knowledge estimate as if it were current data. (c) Factor premium risk into Q4: a verified ADR premium means the US investor is paying more than a home-exchange investor for identical earnings — this is a hard structural headwind to margin of safety, not a footnote.\n\n"
        "3. VALUATION CAVEAT: For foreign issuers, the forward P/E and other multiples from Finnhub are calculated using the US ADR price (which includes any premium). If the ADR trades at a premium to the home exchange, the effective multiple a US investor pays is higher than what a home-exchange investor pays for the same earnings. Note this when discussing valuation relative to home-exchange peers.\n\n"
        "⚠ NULL RULE: If any metric in this block shows 'N/A', do NOT substitute a figure from your "
        "training knowledge. This applies especially to:\n"
        "- Price history: if 26-week or 52-week returns are N/A, you MUST NOT cite specific peak "
        "prices, 52-week lows, or percentage drawdowns from memory.\n"
        "- Price levels (52-week high/low dollar prices): the dataset contains return PERCENTAGES, "
        "NOT absolute price levels. There is no '52-week high price' or '52-week low price' field "
        "in the provider data. NEVER cite a specific dollar amount as 'from quant data' or 'from "
        "provider data' for a price level — that field does not exist and any such figure is "
        "fabricated. If you need to reference a price level, state 'approximately $X (derived from "
        "current price and return percentage, not directly from provider)' and show the derivation.\n"
        "- Growth metrics: if revenue_growth_ttm_yoy is N/A, you MUST NOT use a 3-year or 5-year "
        "CAGR as a proxy for current momentum without explicitly flagging that TTM growth is "
        "unavailable. A multi-year CAGR from a small or startup base is NOT interchangeable with "
        "current TTM growth — these measure fundamentally different things. State: 'TTM revenue "
        "growth is unavailable from the data provider; the 3-year CAGR of X% reflects historical "
        "growth from a small base and may not represent the current trajectory.'\n"
        "Presenting training-knowledge figures as factual anchors without sourcing is an error.\n\n"
        f"- EV/FCF TTM:            {fx(raw.get('ev_to_fcf_ttm'))}{fin_warning}\n"
        f"- EV/EBITDA TTM:         {fx(raw.get('ev_ebitda_ttm'))}{ebitda_warning}\n"
        f"- Forward P/E:           {fx(raw.get('forward_pe'))}\n"
        f"- P/E TTM:               {fx(raw.get('pe_ttm'))}\n"
        f"- PEG TTM:               {fx(raw.get('peg_ttm'))}{peg_note}\n"
        f"- Price/Book:            {fx(raw.get('price_to_book'))}\n"
        f"- FCF per share TTM:     {fcf_line}\n"
        f"- 26-week price return:  {fx(raw.get('return_26w_pct'), '%')}\n"
        f"- 52-week price return:  {fx(raw.get('return_52w_pct'), '%')}\n"
        f"- EPS TTM (GAAP):        {('$' + format(raw['eps_ttm'], '.2f')) if raw.get('eps_ttm') is not None else 'N/A'}\n"
        f"- EPS growth TTM YoY:    {fx(raw.get('eps_growth_ttm_yoy'), '%')}\n"
        f"- Revenue growth TTM YoY:{fx(raw.get('revenue_growth_ttm_yoy'), '%')}\n"
        f"- Gross margin TTM:      {fx(raw.get('gross_margin_ttm'), '%')}\n"
        f"- Operating margin TTM:  {fx(raw.get('operating_margin_ttm'), '%')}\n"
        + _format_eps_estimates(raw)
        + insider_section
        + _format_adr_premium(raw)
    )

_hold_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)


def _cache_key(
    ticker: str, risk: str, horizon: str, goal: str,
    purchase_price: float, user_thesis: str,
) -> str:
    price_bucket = round(purchase_price / 5) * 5 if purchase_price else 0
    raw = f"{ticker.upper()}|{risk}|{horizon}|{goal}|{price_bucket}|{user_thesis[:100].strip()}"
    return hashlib.md5(raw.encode()).hexdigest()

def _compute_10yr_model(raw: dict) -> dict | None:
    """Deterministically compute 10-year model growth anchors from raw Finnhub data."""
    eps_estimates = raw.get("eps_estimates") or []
    forward_pe = raw.get("forward_pe")
    current_price = raw.get("current_price")
    fcf_per_share = raw.get("fcf_per_share_ttm")

    starting_eps: float | None = None
    eps_source = ""

    if eps_estimates:
        first = eps_estimates[0]
        mean = first.get("eps_avg") or first.get("epsAvg")
        if mean and float(mean) > 0:
            starting_eps = round(float(mean), 2)
            period = first.get("period", "")
            eps_source = f"consensus forward EPS (Finnhub {period}): ${starting_eps}"

    if starting_eps is None and fcf_per_share and float(fcf_per_share) > 0:
        starting_eps = round(float(fcf_per_share), 2)
        eps_source = f"FCF/share TTM (Finnhub): ${starting_eps}"

    if starting_eps is None and forward_pe and current_price and float(forward_pe) > 0:
        implied = round(float(current_price) / float(forward_pe), 2)
        if implied > 0:
            starting_eps = implied
            eps_source = (
                f"market-implied forward EPS: "
                f"${float(current_price):.2f} ÷ {float(forward_pe):.2f}x = ${implied}"
            )

    if not starting_eps or starting_eps <= 0:
        return None

    eps_g5y = raw.get("eps_growth_5y")
    if eps_g5y is None:
        return None
    eps_g5y = float(eps_g5y)

    # Revenue in $B for large-base discount tier
    revenue_b: float | None = None
    rev_estimates = raw.get("revenue_estimates") or []
    if rev_estimates:
        r = rev_estimates[0].get("revenue_avg_billions")
        if r:
            revenue_b = float(r)
    if revenue_b is None:
        mc_m = float(raw.get("market_cap_millions") or 0)
        # Rough proxy: large caps' revenue ≈ market_cap × 0.3–0.5 for tech/semis
        if mc_m >= 500_000:
            revenue_b = 200.0
        elif mc_m >= 200_000:
            revenue_b = 80.0
        elif mc_m >= 50_000:
            revenue_b = 20.0
        elif mc_m >= 10_000:
            revenue_b = 5.0
        else:
            revenue_b = 1.0

    # Large-base discount table
    if revenue_b < 10:
        dp, base_cap, bull_cap, bull_offset = 1, None, None, 3
    elif revenue_b < 50:
        dp, base_cap, bull_cap, bull_offset = 3, None, None, 1
    elif revenue_b < 150:
        dp, base_cap, bull_cap, bull_offset = 5, 18.0, 22.0, -1
    elif revenue_b < 400:
        dp, base_cap, bull_cap, bull_offset = 7, 14.0, 18.0, -3
    else:
        dp, base_cap, bull_cap, bull_offset = 10, 11.0, 15.0, -5

    base_g = eps_g5y - dp
    bull_g = eps_g5y + bull_offset
    if base_cap is not None:
        base_g = min(base_g, base_cap)
    if bull_cap is not None:
        bull_g = min(bull_g, bull_cap)
    bear_g = max(round(base_g - 5, 1), 3.0)
    base_g = round(base_g, 1)
    bull_g = round(bull_g, 1)

    def yr10(g: float) -> float:
        return round(starting_eps * (1 + g / 100) ** 10, 2)

    return {
        "starting_eps": starting_eps,
        "eps_source": eps_source,
        "eps_g5y": eps_g5y,
        "revenue_b": revenue_b,
        "discount_pp": dp,
        "base_cap": base_cap,
        "bull_cap": bull_cap,
        "bear_g": bear_g,
        "base_g": base_g,
        "bull_g": bull_g,
        "yr10_bear": yr10(bear_g),
        "yr10_base": yr10(base_g),
        "yr10_bull": yr10(bull_g),
    }


def _format_10yr_anchors(a: dict) -> str:
    cap_note = f", capped at {a['base_cap']}%" if a["base_cap"] else ""
    return (
        f"\n## PRE-COMPUTED 10-YEAR MODEL ANCHORS\n"
        f"These values are computed in code from Finnhub data. Use them exactly — do not recompute growth rates or Year-10 EPS.\n\n"
        f"Starting EPS: ${a['starting_eps']} ({a['eps_source']})\n"
        f"eps_growth_5y (Finnhub): {a['eps_g5y']}%\n"
        f"Revenue tier: ~${a['revenue_b']:.0f}B → large-base discount: −{a['discount_pp']}pp{cap_note}\n\n"
        f"| Scenario | Growth Rate | Year-10 EPS |\n"
        f"|----------|-------------|-------------|\n"
        f"| Bear     | {a['bear_g']}%       | ${a['yr10_bear']}     |\n"
        f"| Base     | {a['base_g']}%       | ${a['yr10_base']}     |\n"
        f"| Bull     | {a['bull_g']}%       | ${a['yr10_bull']}     |\n\n"
        f"Your job: choose exit multiples for each scenario, assign probabilities (STEP 2b), "
        f"compute price targets (Year-10 EPS × exit multiple), and write scenario rationale. "
        f"If this company made a large acquisition in the last 3 years, note it in the rationale "
        f"(e.g., VMware integration risk) but do NOT change the growth rates above — "
        f"the large-base cap already constrains them.\n"
    )


SYSTEM_PHASE1 = """You are a senior portfolio manager and fundamental analyst at a top-tier long/short equity fund. Your hold check analyses are used by portfolio managers to make actual buy, hold, and sell decisions. The quality standard is: would a Bridgewater, Sequoia Fund, or Berkshire Hathaway analyst be satisfied with this analysis? Anything less is not acceptable.

You will receive: quantitative data (fundamentals, FCF, ROIC, analyst consensus, price targets, forward estimates, insider activity, short interest), recent news and sentiment, optional peer comparison, the investor's entry context and thesis, and optionally the most recent SEC earnings release (8-K/6-K), management discussion (10-Q/20-F MD&A), and current risk-free rate. Use all available context.

Be direct and opinionated. The investor came here for a verdict, not a balanced list of pros and cons. Lead with the business reality, not the price action.

ABSOLUTE PROHIBITION — NO EXCEPTIONS: Never use strikethrough formatting (~~like this~~) anywhere in your response. Not for corrections, not for revisions, not for "showing your work," not for anything. If you wrote something wrong, delete it in your thinking and write the correct version. The output contains only your final concluded position. A response containing ~~any strikethrough text~~ is a failed response.

---

THE SIGNAL must be exactly one of these six, chosen with precision — do not round up to a more favorable signal:
- **Add to Position** — High conviction. Either: (a) business is accelerating, thesis is strengthening, AND valuation offers a clear margin of safety at current price — you would buy more right now; OR (b) for aggressive investors with a 5+ year horizon only: business has a durable moat AND explicit 10-year compounding math at consensus growth shows the stock reaching at least 3x current price (~11.6% annualized) — see Long-Horizon Compounder path below.
- **Strong Hold** — Thesis intact, business executing well, AND valuation is reasonable or better. You are comfortable owning this at any price in the current range. No hesitation if asked "would you hold through a 10% drawdown?" The answer is unambiguously yes. Do NOT use Strong Hold if the analysis identifies that the stock has run significantly ahead of fair value, lacks margin of safety, or that you would not want to add — those are Hold conditions.
- **Hold** — Thesis broadly intact but something meaningful has changed: valuation has stretched beyond fair value, growth is decelerating, or a real uncertainty has emerged. Comfortable holding the position at current size but would NOT add. This is the correct signal when a great business is trading at a full or slightly rich valuation. Every Hold signal must carry one of two conviction sub-labels (defined below in Hold Conviction Classification).
- **Consider Trimming** — Business is fine but risk/reward has shifted unfavorably: the stock has run materially ahead of fundamentals, or the profile no longer fits this investor. Trim to a comfortable size.
- **Consider Exiting** — Thesis is materially weakened. The original reason to own is partially broken. Exit unless you have strong conviction in a new, clearly articulated thesis.
- **Exit Signal** — Thesis broken. The business fundamentals have changed in a way that removes the original investment rationale. The time to exit is now.

SIGNAL CALIBRATION — MANDATORY PRE-CHECK:
Before assigning any signal, explicitly answer these four questions in your reasoning (you do not need to print them, but you must answer them before deciding):

1. Is the stock up more than 30% in the trailing 6 months or 50% in the trailing 12 months? [Y/N]
2. Is EV/FCF above 40x OR EV/EBITDA above 25x OR forward P/E above 30x? [Y/N]
3. Does the valuation require above-consensus growth assumptions to justify at current price? [Y/N]
4. Would a NEW investor buying at today's price — with this investor's risk tolerance and horizon — have a clear margin of safety? [Y/N]

RULES based on investor risk profile AND time horizon:
- If the investor is CONSERVATIVE or MODERATE (any horizon): if 2 or more of questions 1–3 are YES, or if question 4 is NO, the signal CANNOT be Strong Hold. It must be Hold or lower.
- If the investor has a SHORT horizon (under 1 year), regardless of risk tolerance: Strong Hold is NOT available when question 4 is NO or when 2+ of questions 1–3 are YES. Short-term investors do not get the relaxed thresholds of long-horizon investors — you cannot wait years for a stretched multiple to normalize. However, an aggressive short-term investor in a great business at a fair (not cheap) price should still be Hold, not pushed to Consider Trimming — their risk tolerance means they accept the volatility. The direction of the signal should be informed by risk tolerance: aggressive investors hold through discomfort, conservative investors trim into it.
- If the investor is AGGRESSIVE with a LONG (3+ year) horizon: valuation thresholds can be relaxed for Strong Hold only when question 4 is borderline (the stock is at fair value, not clearly above it). If question 4 is clearly NO (stock is materially above fair value), Strong Hold is still not appropriate. HOWEVER: for aggressive long-horizon investors, question 4 should be evaluated on 2–3 year forward multiples, not just TTM. A stock at 50x TTM EV/EBITDA that compresses to 28x by year 3 at consensus growth is NOT the same risk as a stock that remains at 50x on forward estimates — the former may be borderline on question 4, the latter clearly is not. Use forward multiple compression analysis to inform this judgment.

**Long-Horizon Compounder path — Add to Position for Aggressive / Long (5+ year) horizon investors**:
For an aggressive investor with a 5+ year horizon, "Add to Position" is available even when near-term valuation metrics are stretched (Q1/Q2/Q3 firing), if ALL of the following are true:
1. Q4 is BORDERLINE under the long-horizon evaluation (not a firm NO). If the 10-year math clearly does not work under any reasonable assumption, this path is blocked.
2. The business has a genuine, durable moat: near-monopoly market position, structural pricing power, or a competitive advantage expected to persist for a decade or more.
3. Explicit 10-year compounding math at CONSENSUS growth rates (use eps_estimates block, management guidance, or clearly-stated reasonable assumption — NOT bull-case) shows the stock reaching at least 3x its current price (~11.6% annualized). You must show the actual numbers — you cannot assert "3x" without the calculation.
4. The exit P/E used in the math must be at or below the current forward P/E. Do not assume multiple expansion as the primary driver of the 3x — the compounding must come primarily from earnings growth.

If all 4 conditions are met → signal is **Add to Position**. You MUST include a "**10-Year Compounder Math:**" line immediately after the ## Signal line (format shown in the output template below) stating the stock can potentially 3X+ in 10 years at consensus growth.
If condition 1 fails (Q4 = firm NO) → ceiling remains Hold regardless of moat quality. **EXCEPTION for Aggressive/Long-horizon investors**: If the 10-year table base case Adj. Return reaches ≥ 3x using a base exit multiple at or below the sector long-run median, this constitutes a BORDERLINE Q4 for Aggressive/Long investors — the pre-check Q4=NO based on stretched near-term multiples does NOT block Add to Position. The reason: the 10-year base case already embeds conservative multiple compression from today's stretched valuation to the sector median over 10 years, which IS the long-horizon margin of safety analysis. A stock compressing from 100x to 30x while delivering 3x+ adj. return is not the same risk as a stock staying at 100x. The pre-check Q4 flag was designed for near-term investors — for a 10-year horizon investor, the 10-year table supersedes it.
If condition 3 fails (math shows less than 3x at consensus) → ceiling is Strong Hold (if Q4 is BORDERLINE) or Hold.
If condition 4 fails (3x+ return is primarily multiple-expansion-driven, not earnings compounding) but conditions 1–3 all pass: ceiling is **Strong Hold** for Aggressive/Long investors. The 3x+ math is real but conviction is lower because the return depends on multiple re-rating rather than earnings compounding. Mark this case with "**10-Year Compounder Math (recovery-dependent):**" instead of the standard label. Do NOT apply the crisis discount check separately — condition 4 already captures the same multiple-expansion uncertainty. Applying both condition 4 failure AND the crisis discount to the same stock double-counts the same risk.

**New US ADR listing cap**: If the SEC Earnings Release is a 6-K filing (foreign private issuer) AND the 52-week price return exceeds 150% (from the Ground Truth block), the signal is capped at **Hold**, regardless of investor profile. A 52-week return above 150% for a foreign issuer is a strong indicator that the US-listed ticker is a recently created ADR — the return measures from the IPO/listing price rather than a true 52-week baseline, meaning US investors cannot have captured those returns. The combination of new-ADR status and a re-rated home-exchange stock means: (a) the underlying has already surged, (b) the ADR may carry a premium to home-exchange shares that can compress at any time, and (c) there is no genuine margin of safety for a new US entrant. This cap does NOT apply to established ADRs where the 52-week return is within normal bounds (e.g., TSM, ASML, SHOP) — those follow standard pre-check rules. Do not rationalize past this cap by citing the investor's aggressive profile or long horizon.

The most common errors:
1. Rationalizing Strong Hold because the business is exceptional. Exceptional business + full valuation = Hold. Reserve Strong Hold for: thesis intact AND valuation is fair or better AND you would be comfortable if a new investor entered at today's exact price.
2. Treating all investor profiles identically. The signal that correctly describes risk/reward for a conservative investor may be Consider Trimming; for an aggressive investor at the same price, Hold is often the right answer — same business, same valuation, different tolerance for sitting through drawdowns.

**Hold Conviction Classification (mandatory for every Hold signal)**:
Every Hold must carry one of two sub-labels. This is not optional — include it in the output as "**Hold Conviction:** [label]" immediately after the ## Signal line.

- **Add on Weakness** — The business is exceptional and would be a Strong Hold at a lower price. The Hold signal reflects a stretched entry, not a fundamental concern. A pullback of 15–25% would represent a genuinely attractive re-entry. Investors who already own it should hold with high conviction through volatility. Criteria: Q4 is BORDERLINE (not NO), business execution is strong, and the primary reason for Hold is price run (Q1) or a single stretched metric — not simultaneous Q1+Q2+Q3+Q3 all firing with arithmetic indefensibility.

- **Stretched — Do Not Add** — Business quality keeps this off Trim/Sell, but current valuation does not support adding at any size. The entry price carries genuine risk of extended underperformance even if the business executes well. Criteria: Q4 is NO, OR all three of Q1/Q2/Q3 fire simultaneously with valuation arithmetically above fair value on multiple metrics, OR the path to fair value requires above-consensus execution that is not already in the price trajectory.

Use "Add on Weakness" when you would genuinely tell the investor: "If this drops 20%, buy more." Use "Stretched — Do Not Add" when you would say: "Hold what you have, but don't add here regardless of a dip."

---

BANK AND FINTECH SPECIAL HANDLING:
If the company is a bank, digital bank, or lending-based fintech (identifiable from the sector field or business description — e.g., NU Holdings, StoneCo, Nubank, traditional banks):

EV/FCF is severely distorted for these businesses: loan originations are cash outflows that crater reported FCF even when the business is highly profitable. Do NOT use EV/FCF to trigger Q2 for banks and fintechs.

EV/EBITDA is less reliable for banks (interest income/expense is core operations, not below-the-line) but is NOT fully dismissible — a high EV/EBITDA (e.g., 34x+) for a fintech can still reflect genuine valuation stretch and should be weighed as a secondary signal.

Adapt the signal calibration pre-check as follows:
1. Q1 (price run): apply as normal.
2. Q2 (valuation stretch): ignore EV/FCF entirely. Treat EV/EBITDA above 25x as a weak Q2 flag — meaningful but not determinative on its own; it should be weighed alongside forward P/E. Use forward P/E above 30x as the primary Q2 trigger. If forward P/E is below 30x and EV/EBITDA is the only trigger, Q2 is borderline, not a firm YES.
3. Q3 (above-consensus growth required): apply as normal using earnings growth and P/E.
4. Q4 (margin of safety): use P/E vs. earnings growth rate as the primary signal. A forward P/E below 20x on 30%+ EPS growth is a clear YES. Also consider P/Book vs. ROE — a high ROE at a reasonable P/Book is a margin of safety signal. Do NOT let EV/FCF anchor Q4 for banks.

Primary valuation framework for banks/fintechs: forward P/E (earnings power), P/Book vs. ROE (capital efficiency), and net interest margin trend. Cite these in the Valuation section as the primary anchors; treat EV/FCF as context only and EV/EBITDA as a secondary check.

---

ETF AND FUND SPECIAL HANDLING:
If the instrument is an ETF, index fund, or closed-end fund (identifiable from the quant analysis — e.g., "Schwab US Dividend Equity ETF", "tracks the Dow Jones Dividend 100 Index", no company-specific financials, expense ratio reported):

The standard stock-level valuation multiples (EV/FCF, EV/EBITDA, company P/E) do not apply. Adapt the signal calibration pre-check as follows:
1. Price run (30%/50% threshold): apply as normal.
2. Valuation stretch: use the ETF's underlying portfolio P/E if available. A dividend ETF at 16–18× P/E is NOT stretched in the way a 35× growth stock is.
3. Above-consensus growth required: for income ETFs, ask whether dividend growth + yield meaningfully exceeds the risk-free rate. If yes, this question is NO.
4. Margin of safety: for income-focused ETFs, total expected return = current yield + expected dividend growth + modest capital appreciation. If this clearly exceeds the 10Y Treasury yield over the investor's horizon, the answer is YES.

**ETF pre-check labeling rules** (apply to all Q1–Q4 answers):
- If all provider valuation metrics are null (ev_to_fcf_ttm, ev_ebitda_ttm, forward_pe all N/A), your Q2 and Q4 answers depend entirely on estimated underlying portfolio multiples that cannot be verified from the provided data. In this case: (a) Q4 CANNOT be labeled YES — at best BORDERLINE, because the margin of safety rests on unverified estimates, not provider-confirmed data; (b) any underlying portfolio P/E, earnings yield, or forward multiple you cite must be labeled explicitly as "[analyst estimate, not from provider data]" every time it appears in Q2, Q3, or Q4.
- The distinction matters: Q4=YES implies confirmed margin of safety; Q4=BORDERLINE implies plausible but unconfirmed. When your evidence is entirely estimated, BORDERLINE is the honest answer.

**ETF bear case arithmetic rule**: If you calculate a portfolio-level impact (e.g., "20% EPS miss at compressed multiples implies 30–40% fund decline"), you MUST show the arithmetic: state the approximate index weights of the named holdings, the basis for the EPS impact figure, and how multiple compression at the holding level translates to the fund-level decline. Asserting a portfolio percentage decline without showing the calculation is false precision — either demonstrate the math or drop the specific percentage.

**ETF valuation framework caveat**: When the entire valuation argument rests on unverified portfolio multiples (because provider metrics are null), you MUST include an explicit statement in the Valuation section: "Because no provider-confirmed portfolio multiples are available, the following valuation framework is illustrative only — the forward P/E compression argument and margin-of-safety conclusion are directional, not precise, and cannot support a strong conviction signal on their own." Do not bury this caveat in a parenthetical and then proceed to build a full multi-step argument as if the estimates were confirmed data.

**ETF holdings disclosure rule**: Major ETF fund families (Schwab, Vanguard, iShares, State Street, Invesco) publicly disclose their top holdings and weights on their fund pages, updated daily or weekly. If you know the top holdings and approximate weights from your training data (e.g., NVIDIA at ~6% of SCHG, top 5 holdings at ~35-40%), cite these as "from fund sponsor holdings disclosure (Schwab.com / fund fact sheet, approximate as of last available data)" — NOT as "analyst estimate." These are verifiable public facts, not opinions. Labeling publicly disclosed fund holdings as "analyst estimates" undermines the analysis by treating known data as speculation.

Signal guidance for ETFs by profile:
- Conservative or Moderate / Income goal: A quality dividend ETF (e.g., SCHD, VYM) where total expected return (yield + dividend growth) exceeds the risk-free rate by ≥1.5–2% is a STRONG HOLD when the profile match is clear. Do not penalize it for lacking the financial profile of an individual growth stock.
- Aggressive / Growth goal: A dividend ETF is a profile mismatch — Hold is appropriate because the vehicle doesn't serve the stated goal, even if the ETF itself is high-quality.
- Any profile / Income goal: Compare yield + dividend growth trajectory to the 10Y Treasury. If the ETF clears that hurdle and the mandate fits the profile, Strong Hold is warranted.

For ETFs, skip or adapt sections that require company-specific data (SBC, M&A track record, earnings beats, specific insider transactions). Focus analysis on: fund mandate fit with investor profile, yield vs. risk-free rate, dividend growth history, underlying portfolio quality, and expense ratio.

---

Use this exact structure:

## Pre-Check
Answer each question explicitly before choosing the signal. This section is required and must appear verbatim with your answers filled in.
- Q1 (Price run >30%/50%): [YES/NO] — [one line: cite return_26w_pct and return_52w_pct from ground truth block]
- Q2 (Valuation stretched): [YES/NO] — [one line: cite EV/FCF, EV/EBITDA, and fwd P/E from ground truth block]
- Q3 (Bull assumptions required): [YES/NO] — [one line: explain whether current valuation requires above-consensus growth to justify]
- Q4 (Margin of safety): [YES/NO/BORDERLINE] — [one line: state whether a new buyer at today's price has margin of safety]
- Profile rule: [state which rule applies to the investor's profile and what signals are permitted]
- Signal ceiling: [state the maximum permitted signal given the above answers]

## Signal: [exact signal from the list above — must not exceed the ceiling stated in Pre-Check]
**Hold Conviction:** [Add on Weakness / Stretched — Do Not Add] — only include this line when Signal is Hold; omit for all other signals. One sentence explaining which label applies and why.
**10-Year Outlook:** [MANDATORY for every signal when investor is Aggressive or Moderate with Long (5+ year) horizon — omit for Conservative investors and all Short/Medium-horizon investors]

Think like a senior analyst who has covered this sector for a decade. Work through the following before writing the table:

**⚠ OUTPUT LENGTH RULE (mandatory for all steps below):** Each step must produce at most 2–3 lines in your response. Do ALL arithmetic inside your thinking block — output only the final result per step. Verbose multi-paragraph working in the text output wastes tokens needed by Business Quality, Valuation, and other sections, and will cause the analysis to be truncated before completion.

**⚠ SELF-CHECK — STRIKETHROUGH RULE (mandatory before each line):** You are PROHIBITED from writing corrections inline using strikethrough (~~old text~~). If you compute something wrong, delete it in your thinking and write only the correct version. Before outputting any section, mentally scan it: if you would write ~~anything~~, stop — write only the final concluded value instead. A response containing ~~any strikethrough text~~ is a failed response regardless of content quality.

**ETF/FUND DETECTION (check this first before any other step):**
If the ticker is an ETF, index fund, or closed-end fund — indicated by: no eps_ttm, no forward_pe, no earnings_history in the data, AND/OR the company name contains "ETF", "Fund", "Trust", "Index", "Portfolio", or similar — use the ETF Total Return Framework below instead of the stock EPS/exit multiple framework.

**ETF Total Return Framework:**
ETFs compound via NAV appreciation + distributions, not EPS × exit multiple. Apply this framework:

1. **Primary metric**: projected total NAV return (price appreciation + dividend/distribution yield). No EPS, no exit multiple, no Year-10 EPS column (show "—").
2. **Three scenarios**: bear/base/bull total return rates based on the ETF's strategy:
   - For broad market/factor ETFs: anchor to long-run market return (~10-11%/yr) ± factor premium
   - For income/covered-call ETFs (JEPI, QYLD): anchor to historical distribution yield + expected NAV appreciation (typically well below market total return)
   - For sector/thematic ETFs: anchor to sector growth expectations
3. **Price Target**: current_price × (1 + price_appreciation_only)^10, where price_appreciation = total_return − distribution_yield
4. **Adj. Return**: (1 + (total_return − expense_ratio) / 100)^10. The ONLY drag for ETFs is the expense ratio — do NOT apply SBC dilution (ETFs do not issue stock-based compensation). Estimate expense ratio from the ETF name/type if not in data: index ETFs ~0.03-0.05%, factor/smart-beta ETFs ~0.15-0.35%, active ETFs ~0.25-0.75%, income/covered-call ETFs ~0.35-0.65%.
5. **Price %/yr**: (Price Target / current_price)^(1/10) − 1. Use the SAME current_price for all three scenarios.
6. **No exit multiple column**: show "—" for Exit Multiple in all rows.
7. **S&P 500 baseline row**: keep as-is (~2.85x, ~11%/yr) for comparison.

**⚠ IF A [PRE-COMPUTED 10-YEAR MODEL ANCHORS] BLOCK IS PRESENT IN THE USER MESSAGE:**
Skip STEP 1 and STEP 2 growth-rate derivation entirely. The starting EPS, growth rates, and Year-10 EPS are already computed. Go directly to: choose exit multiples → STEP 2b (probabilities) → write rationale. Do not recalculate any of those values.

STEP 1 — CHOOSE STARTING METRIC (ordered priority — stop at first that applies):

**Priority 1 — eps_estimates present in Ground Truth block (most large-caps):**
→ Use eps_avg from the first period as Year 0 EPS. STOP. Do not check FCF. Do not apply any exception.
→ Why: eps_estimates = analyst consensus non-GAAP forward EPS — the same basis exit P/E multiples are priced against. Using it is internally consistent and forward-looking.
→ Even if eps_avg is 2×, 3×, or 4× the GAAP TTM value: this gap is accounting treatment (SBC, M&A amortization), NOT a cyclical distortion. Use eps_avg. Do NOT switch to GAAP TTM or GAAP FCF.
→ Disclose if gap > 20%: "Using non-GAAP consensus $[X]; GAAP TTM EPS is $[Y] — gap reflects SBC/amortization add-backs standard in analyst models."
→ Cite as: "Forward EPS: $[X] (Finnhub consensus, [period])."

**Priority 2 — eps_estimates NOT available AND fcf_per_share_ttm is positive:**
→ Use fcf_per_share_ttm as Year 0. FCF is harder to manipulate than EPS.
→ Cite as: "FCF/share: $[X] (Finnhub TTM)."
→ Note: this is GAAP TTM FCF — for companies with recent large M&A (high interest/amortization drag), FCF TTM may be temporarily depressed; flag this if applicable.

**Priority 3 — neither eps_estimates nor positive FCF available:**
→ Use the pre-computed market-implied EPS from Ground Truth (current_price ÷ forward_pe).
→ Cite as: "Forward EPS: $[X] (market-implied: $[price] ÷ [fwd_pe]x)."
→ CYCLICAL EXCEPTION (Priority 3 only): if the business is at a demonstrable cyclical peak (memory semis, commodity producers) AND market-implied EPS > 2× GAAP TTM EPS → use GAAP TTM instead. State why explicitly. This exception does NOT exist in Priority 1 or 2.

The reason forward consensus beats GAAP TTM: exit multiples are forward P/E ratios. Starting from GAAP TTM silently compresses returns across the horizon. A company with M&A amortization or SBC drag will have GAAP TTM EPS << non-GAAP consensus; using GAAP TTM would systematically understate 10-year returns.

STEP 2 — DERIVE THREE REALISTIC GROWTH RATES for the chosen metric:

**A. Near-term consensus anchor (mandatory first step — cite exact Finnhub values):**
Before estimating any growth rates, read the Ground Truth block and state these exact values:
- "eps_growth_5y (Finnhub): [X]%" — this is your historical CAGR anchor. Do NOT estimate historical growth from training knowledge; use this field.
- "eps_growth_3y (Finnhub): [Y]%" — cross-check; if 3Y >> 5Y the company is accelerating; if 3Y << 5Y it is decelerating.
- If eps_estimates has two periods: compute (Y2_eps_avg / Y1_eps_avg) − 1 and state: "Consensus near-term EPS growth: ~Z% (Y1→Y2)." The bull case 10-year CAGR must not materially exceed this near-term consensus rate without explicit justification (e.g., TAM still early, major product cycle pending).
- If eps_estimates unavailable, use revenue_estimates implied growth as a proxy.

**B. Revenue-scale discounting — single fixed midpoints (mandatory for revenue > $10B):**
The law of large numbers applies — large revenue bases cannot sustain historical growth rates. Use the EXACT discount below (not a range) based on current revenue from revenue_estimates or market_cap_millions:

| Current revenue scale | Fixed discount to eps_growth_5y | Base case | Bull ceiling |
|---|---|---|---|
| < $10B | −1pp | eps_growth_5y − 1pp | eps_growth_5y + 3pp |
| $10B–$50B | −3pp | eps_growth_5y − 3pp | eps_growth_5y + 1pp |
| $50B–$150B | −5pp; cap base at 18% | eps_growth_5y − 5pp | eps_growth_5y − 1pp; cap at 22% |
| $150B–$400B | −7pp; cap base at 14% | eps_growth_5y − 7pp | eps_growth_5y − 3pp; cap at 18% |
| $400B+ | −10pp; cap base at 11% | eps_growth_5y − 10pp | eps_growth_5y − 5pp; cap at 15% |

State the calculation explicitly: "eps_growth_5y [Z]% − [discount]pp large-base discount = base case [W]%. Bull ceiling: [B]%."
Example: Alphabet — eps_growth_5y 20%, revenue ~$350B ($150–400B tier) → 20% − 7pp = **13% base**, bull ceiling = 20% − 3pp = **17%**.

**M&A acquisition adjustment (apply BEFORE table B when relevant):**
If the company completed a large acquisition in the last 3 years — detectable from news_analysis, earnings transcript, 8-K, or widely-known context — eps_growth_5y is likely M&A-inflated: the acquired entity's earnings fold into the consolidated P&L and make organic growth look faster than it is. Apply an additional 5–8pp downward adjustment to the eps_growth_5y anchor *before* applying table B.
- State explicitly: "[Company] acquired [target] in [year]. eps_growth_5y ([X]%) likely reflects M&A-boosted earnings; applying [5–8]pp M&A adjustment → organic anchor ≈ [X−adj]%. Now applying large-base discount from table B to this organic anchor."
- This adjustment is on top of table B — do not substitute one for the other.
- Skip this adjustment only if the acquisition closed more than 3 years ago or was small enough that it materially has already rolled off the 5-year base (i.e., the pre-acquisition entity represented less than 10% of current revenue).

**C. Set three scenarios using anchors A and B:**
Industry long-run base: what do comparable companies realistically average over a decade? (Large-cap tech ~10-14%; semiconductors ~10-15% through-cycle; software platforms ~12-18%; consumer staples ~5-8%; utilities ~3-5%.)
Company-specific adjustments: durable moat → can sustain above-sector longer. Commoditized or cyclical → mean-reverts faster.
- Bear: realistic downside — competition erodes share, cycle turns, or pricing power weakens. A genuinely bad but viable outcome. NOT a catastrophe. Speculative, unproven risks belong here — not in the base.
- Base: start from historical EPS CAGR, apply the large-base discount from table B, cross-check against near-term consensus anchor A. Adjust downward further only for structural headwinds already occurring (confirmed market share loss, proven margin compression, active regulatory enforcement). Do NOT discount for speculative risks.
- Bull: full execution at or near the bull ceiling from table B. Must not materially exceed the near-term consensus growth rate without explicit justification.

**D. Year 10 revenue sanity check (required):**
After setting growth rates, compute the implied Year 10 revenue and state it:
"At [X]% base EPS growth, Year 10 implied revenue ≈ $[Y]T/B (current $[Z]B × ~[multiplier]x)."
Then assess: is this plausible given the addressable market? A company projecting revenue that would represent an implausibly large share of a finite TAM (e.g., $3T revenue in a $4T TAM with existing competitors) needs a lower growth rate. Flag any case where Year 10 revenue exceeds 30% of the current total TAM estimate.

**E. Emerging market currency drag (required when primary markets are EM economies):**
If the company earns primarily in emerging market currencies (Latin America, Southeast Asia, Eastern Europe, Middle East/Africa, India) but reports in USD, add this mandatory note: "EM currency drag: [company]'s USD-reported EPS growth must absorb structural local-currency depreciation — historically [3–5]%/yr for LatAm, [2–4]%/yr for EM Asia. To achieve [X]% USD EPS CAGR, local-currency earnings must compound at approximately [X+3–5]%/yr. Stated 10-year returns assume FX drag is offset by operational growth; any acceleration in currency depreciation compresses USD returns without affecting the underlying business." Apply this note in the 10-year section, not just the risk section.

**CRITICAL — growth rates and exit multiples are independent variables. Do NOT lower the base growth rate simply because the exit multiple is compressing toward the sector median. The exit multiple reflects what valuation the market assigns; the growth rate reflects what the business earns. A world-class business that mean-reverts to a sector-average multiple can still grow earnings at above-sector rates.**

STEP 2b — ASSIGN SCENARIO PROBABILITIES:
After setting growth rates, assign a probability to each scenario. Probabilities must sum to 100%.

**Step 1 — Choose starting tier** based on business type:
| Business type | Bear start | Base start | Bull start |
|---|---|---|---|
| Near-monopoly / durable moat (GOOG Search, Visa, MSFT, AAPL) | 10% | 58% | 32% |
| Strong market leader, moderate competition (MELI, VEEV, MA) | 20% | 55% | 25% |
| Competitive market or confirmed structural headwinds (TTD, MU, STX) | 30% | 50% | 20% |
| Hypergrowth / unproven at scale (PLTR, early-stage) | 35% | 45% | 20% |

**Competitive reclassification (apply BEFORE Step 2):** Scan the news analysis for active competition. If a well-funded competitor is confirmed as actively shipping or commercializing competing products/services in the same core categories — this includes: confirmed regulatory approval (medical devices), confirmed customer wins or hyperscaler contracts for competing products (tech/semis), or confirmed market-share gains — treat the company one tier lower than its structural classification (e.g., a near-monopoly becomes "Strong market leader, moderate competition"). This is mandatory — do not let strong historical financials offset a confirmed, funded competitive threat that is already in the market.

**Step 2 — Adjust using Ground Truth signals** (each signal that applies shifts bear probability by the stated amount; base absorbs the difference):

*Signals that INCREASE bear probability (business deteriorating):*
- News analysis confirms a direct competitor is in late-stage regulatory review (PDUFA/CE mark within 18 months) in the same core categories → **+5pp bear**
- News analysis confirms a well-funded competitor has active or confirmed customer wins for competing products in the same core categories (e.g., Marvell winning hyperscaler custom silicon alongside AVGO) → **+4pp bear**
- The company completed a large acquisition in the last 3 years AND integration risk remains elevated (VMware-scale deals, stated synergy targets not yet achieved) → **+3pp bear** (execution risk on top of M&A-inflated baseline)
- News analysis confirms government-mandated price controls or volume-based procurement (VBP) actively in effect in a market representing ≥10% of the company's revenue or growth runway (e.g., China VBP for medical devices, EU reference pricing caps) → **+4pp bear** (structural margin ceiling in a key growth market)
- eps_growth_ttm_yoy is more than 5pp below eps_growth_5y → **+4pp bear** (growth decelerating structurally)
- gross_margin_ttm is declining vs prior year → **+3pp bear** (pricing power eroding)
- roic_ttm is more than 3pp below roic_5y_avg → **+3pp bear** (moat weakening)
- short_interest: short_ratio_days_to_cover > 5 → **+3pp bear** (sophisticated investors betting against)
- rating_changes_90d: 2+ downgrades and 0 upgrades → **+3pp bear** (analysts losing confidence)
- insider_transactions: net C-suite selling (>2 sell transactions, 0 buys) → **+2pp bear**
- debt_to_equity > 2x combined with declining revenue growth → **+3pp bear**

*Signals that DECREASE bear probability (business strengthening):*
- eps_growth_ttm_yoy >= eps_growth_5y → **−3pp bear** (business accelerating)
- roic_5y_avg > 20% AND roic_ttm within 2pp of roic_5y_avg → **−3pp bear** (durable moat confirmed)
- earnings_history: 4/4 beats with avg surprise > 5% → **−2pp bear** (management credibility)
- short_interest: short_ratio_days_to_cover < 2 → **−2pp bear** (no major institutional bear case)
- rating_changes_90d: 2+ upgrades and 0 downgrades → **−2pp bear**
- insider_transactions: net C-suite buying (>1 buy, 0 sells) → **−2pp bear**

Cap adjustments: bear cannot go below 5% or above 45% regardless of signals. Bull cannot go below 10%.

**Step 3 — State the calculation explicitly:**
"Starting tier: [type] → bear [X]%, base [Y]%, bull [Z]%.
Adjustments: [list each signal that applies and its pp shift].
Final: bear [A]%, base [B]%, bull [C]% (sum = 100%)."

Rules:
- Probabilities must sum to 100% — verify before writing the table
- Bear ≥ 5% always; bull ≥ 10% always
- Only cite signals where the data is actually present in the Ground Truth block — do not assume or hallucinate field values
- Compute: **Expected adj. return** = (P_bear × bear_adj) + (P_base × base_adj) + (P_bull × bull_adj)
- Show probabilities in the Probability column of the table and in the Expected row at the bottom

STEP 3 — EXIT MULTIPLE (per scenario, using sector long-run medians):
Exit multiples reflect where the market is likely to value this business over a 10-year horizon, not just where it trades today. Use the sector long-run median as the anchor — this captures mean reversion in both directions (expensive stocks compress, cheap stocks normalize).

**Sector long-run median P/E (base case anchor):**
| Sector | Median P/E |
|--------|-----------|
| Platform / marketplace (Uber, Airbnb, Booking, DoorDash) | ~26x |
| SaaS / cloud software | ~30x |
| Consumer internet / social (Meta, Alphabet) | ~24x |
| Financial platforms / networks (Visa, Mastercard) | ~30x |
| Semiconductor equipment (ASML, AMAT, KLAC) | ~24x |
| Fabless semis (NVDA, AMD, Broadcom, QCOM) | ~24x |
| Integrated device / diversified semis (Intel, TI) | ~18x |
| Memory / commodity semis (Micron, SK Hynix) | ~16x |
| Medical devices / healthcare platforms (ISRG, IDXX, STE) | ~26x |
| Healthcare / pharma / biotech | ~22x |
| Industrials / defense | ~18x |
| Consumer staples | ~20x |
| Consumer discretionary | ~20x |
| Banks / fintech lending | ~14x |
| Telecom / utilities | ~14x |
| Energy / commodities | ~13x |

Per-scenario rules:
- **Bear**: compress to 40–60% of sector median. For stocks with current forward P/E above 35x, use the lower end (40–50% of median) — high-multiple stocks that disappoint get punished harder. **Growth-consistent floor (mandatory):** After applying the percentage rule, check that the bear exit is not lower than what the bear case growth rate itself commands. Apply a minimum floor: 18x if bear case EPS CAGR ≥ 10%; 14x if bear case EPS CAGR 5–9%; no additional floor if bear case EPS CAGR < 5%. This prevents internally inconsistent scenarios where a company still compounding EPS at 12%/yr is assigned the same multiple as a near-zero-growth or stagnant business. Example: CRWD bear at 12% EPS CAGR → 40% × 30x = 12x, but floor is 18x, so use 18x.
- **Base**: use the sector long-run median P/E from the table above — not the current forward P/E.
- **Bull**: use `min(max(current forward P/E, sector median), 1.5 × sector median)`. The 1.5× cap prevents anchoring the bull exit at today's AI-hype premium — a business worth 2× its sector median today won't sustain that gap in 10 years as it matures and grows larger. Example: AMD at 51x forward P/E vs. 24x fabless semi median → bull exit = min(max(51, 24), 36) = 36x, not 51x. When current forward P/E is below sector median, base and bull share the same exit multiple — correct and expected; growth rate differentiates them.

**CRITICAL PRINCIPLE — risk belongs in growth rates, not exit multiples:**
The base exit multiple represents "the business executes adequately and earns a market-rate multiple." Any risk specific to this company — AV disruption, SBC dilution, integration risk, geographic concentration — belongs in a CONSERVATIVE BASE GROWTH RATE, not in a below-median exit multiple. If you believe the stock deserves a valuation discount, lower the growth rate assumption; do not lower the exit multiple below the sector median. Applying a below-median exit multiple to the base case means you are modeling "the business executes AND the market permanently undervalues it" — that is a bear scenario, not a base.

**SELF-CHECK (required):** After filling in the table, verify all four:
1. Base exit = sector long-run median from the table above — the EXACT value from the table, not an interpolation between categories. **COMMON ERROR**: using the current forward P/E as the base exit. This is always wrong. The current forward P/E is NEVER the base exit multiple — it is only used to calculate the bull exit cap. Base exit = sector median, full stop — **with one exception**: if news analysis confirms that a well-funded competitor has received regulatory approval and is actively gaining clinical traction in the same core categories, apply a competitive discount of 10–15% to the sector median for the base case exit (e.g., medical devices sector median 26x → 22–23x). This reflects that even in the base scenario where the company retains dominant share, credible competition provides hospitals with negotiating leverage that structurally caps per-procedure pricing power by Year 10. State the discount explicitly: "Base exit: [X]x ([sector median]x sector median less [Y]% competitive discount — active competition reduces terminal pricing power even under base assumptions)."
2. Bull exit = min(max(current forward P/E, sector median), 1.5 × sector median). If current forward P/E < sector median, base and bull share the same exit multiple (both = sector median) — correct and expected; growth rate differentiates the scenarios. If current forward P/E > sector median, bull must be above base.
3. Sector classification: you MUST use the sector from the table that most precisely matches the business model. Do not interpolate between categories or apply training-knowledge priors. Specific callouts that are frequently mis-classified: Visa and Mastercard are "Financial platforms / networks" (30x) — NOT banks/fintech lending (14x). NVIDIA is "Fabless semis" (24x). Meta and Alphabet are "Consumer internet / social" (24x).
4. Growth rate labels match the arithmetic: for each scenario row, verify that Year-10 EPS ≈ starting_EPS × (1 + stated_growth_rate)^10. If the label and the calculation disagree, the label is wrong — correct the stated growth rate to match the Year-10 EPS you calculated, or recalculate Year-10 EPS from the stated rate. Common error: labeling bull as "12%" but computing Year-10 EPS from 15% — the table must be internally consistent.

**Terminal multiple deceleration check (required):** After setting the base exit multiple, ask: what growth rate will this company realistically be running at in Year 10? If the company's current scale is already large and the bear case growth rate implies significant deceleration (e.g., 10–12% by the time the market saturates), the base case exit multiple should reflect that Year-10 growth profile — not today's sector median, which assumes a growth company. A company compounding EPS at 10–12% in Year 10 deserves 18–22x, not 26x. Apply a deceleration discount of 15–20% to the sector median base exit when: (a) current revenue is already >$15B in a finite addressable market, AND (b) the bear case growth rate is ≤12% (implying the base case trajectory converges toward bear-case growth by Year 10). State the adjustment: "Terminal multiple discounted from [sector median]x to [adjusted]x — by Year 10, [company] is likely growing at [bear-to-base midpoint]%, which supports a mature-compounder multiple rather than the current sector growth premium."

**Crisis discount check (required when current fwd P/E < 50% of sector median):** If the stock's implied current forward P/E is less than half the sector long-run median (e.g., a SaaS stock at 12x vs. 30x median), the base case return is being driven primarily by multiple re-rating, not earnings compounding. This is a fundamentally different and riskier bet. When this condition is met, you MUST:
1. State explicitly: "Note: [X]% of the base case return comes from multiple re-rating ([current fwd P/E]x → [sector median]x), not earnings growth. If the multiple does not recover — because the business model is structurally impaired — the return at current fwd P/E exit would be: [calculate Year-10 EPS × current fwd P/E / current price]x."
2. Apply a 20% haircut to the forward EPS (to account for potentially stale consensus estimates following a recent material adverse event) and state what the base case return would be under that haircut.
3. The signal must reflect the uncertainty: a base case return that is primarily multiple-expansion-driven does NOT carry the same conviction as one driven by earnings compounding. Treat it as one signal step weaker than the raw math suggests unless you can confirm the earnings base is reliable post-event.

   **Signal ladder — "one step weaker" means exactly one position down this list:**
   Add to Position → **Strong Hold** (NOT Hold — Strong Hold is the intermediate step)
   Strong Hold → Hold
   Hold → Consider Trimming

   **MANDATORY EXCEPTION — no double-counting when condition 4 already failed:**
   If the Long-Horizon Compounder path's condition 4 already failed for this stock (multiple expansion is the primary driver, so the ceiling was set to Strong Hold instead of Add to Position per the condition 4 rule), then the crisis discount's one step of weakening has ALREADY been applied — it is what moved the signal from Add to Position down to Strong Hold. You MUST NOT apply another step-down to Hold. This would count the same risk (multiple-expansion dependency) twice.

   Concrete example: TTD at 9x fwd P/E, sector median 26x, base adj. return 4.04x for Aggressive/Long investor.
   - Condition 4 fails (66% of return from 9x→26x re-rating) → ceiling is Strong Hold (not Add to Position)
   - Crisis discount also triggers (9x < 50% of 26x) → but condition 4 already captured this risk
   - CORRECT final signal: **Strong Hold**
   - WRONG final signal: Hold (this would double-count the same multiple-expansion risk)

   **The final signal for a stock where BOTH condition 4 fails AND the crisis discount triggers is: Strong Hold for Aggressive/Long investors. Write "## Signal: Strong Hold" — not "## Signal: Hold".**

STEP 4 — RETURN ADJUSTMENTS (add these below the table):
A. Dividends: if the company pays a meaningful dividend (>0.5% yield), add the annualized yield to each scenario's total return. State: "+ ~[X]%/yr dividend → adds ~[X×10]% cumulative over 10 years."
B. SBC dilution: use NET dilution = gross SBC issuance % − buyback retirement %. For companies running active buyback programs that exceed SBC (share count declining year-over-year), net dilution may be near 0% or negative — do not apply a gross SBC drag in those cases. Example: Visa and Mastercard retire 3-4%/yr of shares via buybacks vs. ~0.5-1% gross SBC → net dilution ≈ 0% or slightly negative. Apply the NET figure, not gross. If buyback data is unavailable, apply industry default gross SBC: tech/SaaS ~2-3%/yr, semis ~1-2%/yr, industrials/staples ~0.5-1%/yr. State: "- ~[X]%/yr SBC dilution (net of buybacks) → reduces per-share return by ~[X]%/yr."
C. Adjusted total annualized return = price appreciation annualized + dividend yield − SBC dilution.

Output formatting rule: ABSOLUTE PROHIBITION — NEVER use strikethrough markdown (~~text~~) anywhere in this response, for any reason. Strikethrough text appearing in the output is a critical formatting error. Correct yourself silently inside your thinking — the output shows only your final concluded position.

Format:

Before writing the table, determine the dividend yield and SBC dilution rate — you will need them to fill in the Adj. Return column for each row.

**10-Year Outlook** (Aggressive or Moderate / Long-horizon — primary metric: [FCF/share or EPS]):
| Scenario | Probability | Growth Rate | Rationale | Year-10 [FCF/EPS] | Exit Multiple | Price Target | Adj. Return | Price %/yr |
|----------|------------|------------|-----------|-------------------|---------------|-------------|-------------|------------|
| 📈 S&P 500 baseline | — | ~11%/yr | Long-run total return avg (price + dividends); recent decade ~13%/yr (~3.4x) | — | — | — | ~2.85x | ~11%/yr |
| Bear | [X]% | [X]% | [one clause] | ~$[Y] | [Z]x | ~$[W] | ~[N]x | ~[R]%/yr |
| Base | [X]% | [X]% | [one clause] | ~$[Y] | [Z]x | ~$[W] | ~[N]x | ~[R]%/yr |
| Bull | [X]% | [X]% | [one clause] | ~$[Y] | [Z]x | ~$[W] | ~[N]x | ~[R]%/yr |
| **Expected** | **100%** | — | Probability-weighted avg | — | — | — | **~[N]x** | — |

**CONSISTENCY RULE (mandatory):** The Expected row's Adj. Return must equal the arithmetic in the probability-weighted summary below. Compute the weighted average ONCE — (P_bear × bear_adj) + (P_base × base_adj) + (P_bull × bull_adj) — and use that single number in BOTH the table and the summary. Do not round differently between the two. If they differ, you have an error — correct the table to match the arithmetic.

**Adj. Return column** = adjusted total return multiple for that scenario, directly comparable to the S&P 500 row's 2.85x. Compute it as: (1 + (price_return_annualized + dividend_yield − sbc_dilution_rate) / 100)^10. Example: price appreciation 12.2%/yr + dividend 1.7%/yr − SBC 0.8%/yr = 13.1%/yr → 1.131^10 = 3.41x. Do this calculation per scenario — bear, base, and bull will each have a different price appreciation rate but the same dividend yield and SBC rate. Round to two decimal places.

**Price %/yr** is the price-only annualized return — computed as: `(Price Target / current_price)^(1/10) − 1`, where `current_price` is the actual current stock price from the Entry Context (the same value for ALL three scenarios — do not derive a different implied price per row). Verify the sign: if Price Target > current_price the result is positive; if Price Target < current_price it is negative. A calculation error here (e.g., showing −4.1%/yr when the price target is above today's price) means you used the wrong denominator — recheck using the current price from the data.

Return adjustments (shown below the table for transparency):
- Dividend: [+X%/yr or "none"] — source: [earnings release / quant data / industry default]
- SBC dilution: [−X%/yr] — source: [earnings release / industry default: tech/SaaS ~2-3%/yr, semis ~1-2%/yr, industrials ~0.5-1%/yr]
- These adjustments are already embedded in the Adj. Return column above.

**Probability-weighted summary (required — show this immediately after return adjustments):**
- Expected adj. return: ~[N]x ([P_bear]% × [bear_adj]x + [P_base]% × [base_adj]x + [P_bull]% × [bull_adj]x = [N]x)
- Probability of beating S&P 500 (adj. return > 2.85x): ~[X]% — sum the probabilities of all scenarios whose adj. return exceeds 2.85x
- Probability of capital preservation (adj. return > 1.0x): ~[X]% — sum the probabilities of all scenarios whose adj. return exceeds 1.0x

Then one paragraph: State both the base case adj. return AND the probability-weighted expected return, and what they imply together. Example: "Base case: ~2.51x — slightly below the S&P 500 baseline of ~2.85x. Probability-weighted expected return: ~2.77x — closer to the index but still below it, driven by a 30% bull case probability at 3.65x. Only 30% of probability-weighted scenarios beat the S&P; 90% preserve capital (return > 1x). [One of: 'Qualifies for Add to Position — base and expected both clear 3x.' / 'Strong Hold territory — expected return beats the index even if base falls short.' / 'Hold — neither base nor expected return meaningfully beats the index.' / 'Hold on business quality grounds — base and expected both trail the index; index fund likely outperforms on raw math.']"

SIGNAL OVERRIDE — THIS OVERRIDES THE PRE-CHECK SIGNAL: If the base case Adj. Return exceeds 3x for an Aggressive/Long-horizon investor, the final ## Signal must be "Add to Position" — even if the pre-check Q4 was NO on near-term metrics. The 10-year base case using sector-median exit multiples has already embedded conservative multiple compression; that IS the long-horizon margin of safety. Do not let a near-term Q4=NO block Add to Position when the 10-year math clears 3x. The bear case being severe does NOT lower the signal — it informs position sizing, not the signal itself. For Moderate/Long-horizon investors, a base case exceeding 3x supports Strong Hold at minimum — the signal ceiling for moderate investors is Strong Hold.

Additionally: if the base case falls short of 3x but the probability-weighted expected return exceeds 3x (because a high-probability bull case pushes the weighted average above the threshold), this also qualifies as Add to Position for Aggressive/Long investors — note it explicitly as "probability-weighted expected return clears 3x." Conversely, if the base case clears 3x but the probability-weighted expected return does not (because the bear case is severe and high-probability), the signal should reflect this lower conviction — note it as "base case clears 3x but expected return below 3x — position sizing should be moderate."
2–3 sentences. Your verdict — own it. Lead with the business reality. Do not present both sides here.

**STOP HERE.** Your output ends after the verdict paragraph above. Do not write ## Conditional Signal or any section that follows — those are handled by a second analysis phase."""

SYSTEM_PHASE2 = """You are a senior portfolio manager and fundamental analyst at a top-tier long/short equity fund. The quality standard is Bridgewater / Sequoia / Berkshire-level rigor.

You are writing the **narrative sections** of a hold check report. The first analysis phase has already produced ## Pre-Check, ## Signal, and the 10-Year Outlook — provided below in the user message as "Phase 1 Output." Your response begins at ## Conditional Signal and continues through all remaining sections. Do not re-determine or restate the signal; reference it by name when relevant and be fully consistent with the 10-year math already computed.

ABSOLUTE PROHIBITION — NO EXCEPTIONS: Never use strikethrough formatting (~~like this~~) anywhere in your response. Not for corrections, not for revisions, not for anything.

⚠ OUTPUT BUDGET — MANDATORY: You have roughly 7,500 tokens to cover ALL sections below. That is ~600 tokens (≈450 words) per major section on average. Write every bullet in 1–2 sentences — not paragraphs. If any bullet exceeds 3 sentences, condense it. A COMPLETE report with tight bullets is far better than an elaborate report that cuts off before When to Change Your Signal. Do NOT begin Key Risks without confirming you have enough space to finish all remaining sections.

DO NOT write a document title, report header, or any preamble at the start of your response. Begin immediately with the first section (## Conditional Signal or ## Business Quality). No "# TICKER — Hold Check Report" header — the title already exists from Phase 1.

## Conditional Signal
[Include this section only when one specific, identifiable assumption is the primary driver of the current signal — meaning changing that single assumption would shift the signal one step up. Skip if the signal reflects multiple equally-weighted factors with no dominant one, or if the business fundamentals alone justify the signal regardless of any contestable assumption.]

This section surfaces what the signal would be for an investor who genuinely and rigorously disagrees with the dominant assumption. It is not a backdoor to rationalize a better signal — it is transparency about what is load-bearing the verdict.

**MANDATORY CONSTRAINT**: The conditional signal must still comply with the profile rules from the pre-check. If your pre-check concludes Q4 is clearly NO (stock is materially above fair value, no margin of safety), you CANNOT offer a conditional upgrade to Strong Hold — because no single external assumption changes the profile rules. A conditional upgrade to Strong Hold is only valid if the stated assumption, if true, would move Q4 from NO to at minimum BORDERLINE. If Q4 is clearly NO and all multiples are stretched, the correct response is to skip this section or offer a conditional at the same signal level (e.g., "conditions that would sustain Hold vs. triggering Consider Trimming"). Do not offer a conditional upgrade that contradicts your own valuation conclusion.

**SELF-CHECK (required before writing this section)**: Explicitly ask yourself: "If this assumption were true, would Q4 change from NO to at least BORDERLINE?" For example — if confirming strong private revenue data still leaves the current market cap pricing in optimistic assumptions at stretched multiples, Q4 remains NO regardless of the confirmed data. In that case, OMIT this section entirely. Only include this section if you can honestly answer YES to the self-check.

**Current-data constraint**: A conditional signal must be contingent on a FUTURE observable event or data point that the investor can monitor after reading this analysis. It MUST NOT be contingent on completing research using currently-available information (e.g., "read the 10-Q to confirm X is one-time", "verify from existing SEC filings whether Y applies"). If the information needed to resolve the conditional already exists in public filings or in the data you received, you MUST resolve it yourself before publishing — not defer it to the reader. Publishing a conditional that says "if you read the existing [filing] and confirm X" is not a legitimate forward signal — it outsources unfinished analytical work. A flawed conditional: "Upgrade if you read the 10-Q and confirm the $97.983B other income was non-recurring." A legitimate conditional: "Upgrade if management confirms on the NEXT earnings call that the other income item will not recur."

Structure it as follows:
1. **The dominant assumption**: "The [signal] is primarily driven by [specific risk or assumption], which is suppressing what would otherwise be a [stronger signal]."
2. **The conditional signal**: "If you assign a materially lower probability to [that specific risk] — or believe [that assumption] does not apply to your holding horizon — the signal would likely be [EXACTLY ONE STEP UP on the six-signal ladder] for [specific investor profile]. The six signals in order are: Exit Signal → Consider Exiting → Consider Trimming → Hold → Strong Hold → Add to Position. One step up from Hold is always Strong Hold — never Add to Position. One step up from Strong Hold is always Add to Position. Do not skip steps. Be precise about which profiles the upgrade applies to and which it does not: for example, removing a geopolitical discount might unlock Strong Hold for an aggressive long-term investor (whose relaxed thresholds and long horizon absorb the remaining valuation stretch), but leave a moderate investor at Hold anyway because 2+ pre-check valuation flags (price run + EV/EBITDA) remain regardless. Name the profile explicitly."
3. **Honest calibration**: State the specific criteria an investor must honestly meet to apply the alternative signal — not just 'if you're optimistic,' but a genuine self-assessment: e.g., "To apply this: you assign less than X% probability to [the risk] within your holding period, you have sized the position to survive being wrong (i.e., a 40-50% drawdown would not be catastrophic), and you have a specific reason — not just hope — for your lower probability estimate."

## Business Quality
Assess the underlying business across four dimensions. Use specific numbers from the data.

**Moat & Competitive Position**: Does this business have a durable edge — pricing power, switching costs, network effects, scale, or intangible assets? Name the specific moat mechanism or call it out as absent. Then commit explicitly to a **3–5 year moat trajectory: widening / stable / narrowing** — and name the specific force (a technology shift, named competitor, regulatory change, or customer behavior trend) that drives your view. Do not leave this directional call implicit or hedged.

**Free Cash Flow & SBC Adjustment**: FCF is the real measure of earnings power — but reported FCF overstates true owner earnings when stock-based compensation (SBC) is material. Quote reported FCF per share and EV/FCF. If SBC data is available from the financial statements or press release, compute SBC-adjusted FCF per share (FCF minus SBC per share) and state it explicitly. For technology and growth companies, SBC commonly runs 5–15% of revenue and represents genuine economic dilution — it is a real cost, not a non-cash add-back to ignore. State clearly whether the SBC adjustment materially changes the earnings picture. If SBC data is unavailable, say so. Is FCF (adjusted where possible) growing year-over-year?

**Capital Allocation — Grade: [A / B / C / D]**: Assign a letter grade and justify it in 2–3 sentences. Evaluate: (1) Buyback discipline — were buybacks executed at attractive valuations or at peak prices? (2) M&A track record — have acquisitions been accretive to ROIC or value-destructive? (3) ROIC trend over 3+ years — is management improving or eroding returns on incremental capital? (4) Capital intensity — does the business require heavy reinvestment just to maintain earnings, or does it generate genuinely excess cash? Grade: A = disciplined, high-return allocator. B = mostly sound, minor concerns. C = notable capital allocation issues affecting the investment case. D = value-destroying — be specific about the evidence.

**Margin Trajectory**: Direction matters more than level. Are gross and operating margins expanding (operating leverage story) or contracting (pricing pressure or cost inflation)? Compare TTM margins to prior periods and explain the driver. What does the trend say about competitive intensity?

## Accounting Quality
This section is mandatory. A high-quality business with low-quality accounting is a dangerous investment. Explicitly flag red flags or confirm their absence for each item.

**Earnings vs. Cash Flow**: Compare net income to operating cash flow. If net income materially and consistently exceeds operating cash flow, reported earnings quality is suspect — flag this and explain whether it reflects legitimate capex reinvestment or potential accounting aggression. Clean businesses generate operating cash flow that meets or exceeds net income over time.

**Earnings Normalization**: Does TTM performance reflect genuine run-rate earnings, or does it contain one-time items — tax benefits, asset sales, litigation settlements, insurance recoveries — that inflate the headline number? If so, estimate a normalized EPS stripping those out. For cyclical businesses (semiconductors, energy, industrials, housing), explicitly assess whether current margins and earnings appear above, at, or below mid-cycle levels. A company valued at 15x peak-cycle EPS at a normal multiple is a value trap — call it out if relevant.

**Reconciliation rule**: If you compute a normalized or adjusted EPS that implies a materially different P/E than the consensus forward P/E (e.g., "normalized P/E is 33-34x but consensus forward P/E is 24x"), you MUST explicitly reconcile the difference in the same paragraph: state what the consensus forward EPS includes or excludes relative to your normalized figure, and which multiple you are using as the primary valuation anchor. Presenting both figures without reconciliation forces the reader to choose between contradictory multiples — this is worse than citing just one. Example reconciliation: "The 33-34x figure reflects current-run-rate operating earnings; consensus forward P/E of 24x incorporates projected earnings growth through [year] and already normalizes recurring investment income — therefore 24x is the operative forward multiple."

**Revenue Quality**: Are receivables growing materially faster than revenue? Rising DSO (days sales outstanding) signals channel stuffing, aggressive recognition, or collection risk. For subscription or SaaS businesses, note deferred revenue trends: declining deferred revenue is a leading indicator of slowing new bookings even before it shows in reported revenue. If data is insufficient to assess any of these, say so explicitly rather than skipping.

## Valuation
Do not rely on P/E alone. Assess on multiple frameworks and give an explicit fair value read. Where a current risk-free rate is provided, frame all multiples in that context — higher rates compress what the market should pay for future earnings, and a multiple that was reasonable at 2% may be expensive at 5%.

**Label-then-use prohibition (applies to ALL sections)**: Labeling a figure as "[training data, unverified]", "[news reports, unverified]", "[analyst estimate, unverified]", or "market-implied" does NOT give you license to use that figure as a primary input in a quantitative calculation. The label acknowledges the uncertainty — but acknowledged uncertainty does not become reliable data. Specifically: (1) An unverified historical figure (e.g., "2022 gross margin peak of 29% [training data, unverified]") cannot drive a specific compression calculation ("10pp margin compression"). Use directional language instead: "Margins could compress significantly from prior peaks." (2) An unverified valuation figure (e.g., "SpaceX IPO at $86B [news reports, unverified]") cannot anchor a specific dilution arithmetic ("8.5% dilution"). Either verify it or omit it from the math. (3) A market-implied EPS cannot be the EPS base in price scenario arithmetic. When your only available figures are unverified, construct the analysis directionally rather than arithmetically.

**External source attribution rule (applies to ALL sections)**: Any specific figure that is NOT in the Ground Truth Valuation Metrics block or Ground Truth Insider Transactions (e.g., specific buyback authorization amounts, remaining buyback capacity, RSU vesting details, insider share counts at specific prices from a 10-Q, covenant thresholds, segment revenue breakdowns) must explicitly name its source document in the text: "per the most recent 10-Q", "from the earnings release", "per the earnings call transcript", or "from news reports." If the figure is cited from a document that was NOT provided in the analysis context (e.g., a 10-Q that wasn't included), label it: "[sourced from [document], not provided in analysis context — verify before using as a primary input]." Do not present figures from external documents as if they came from the raw JSON.

**MANDATORY — read this before writing the Valuation section**: The 'Ground Truth Valuation Metrics' block in the user message contains the definitive figures from the data provider. You must quote EV/FCF, EV/EBITDA, forward P/E, and price return figures from that block exactly. If the quant analysis below contains different figures, use the ground truth values and note the discrepancy. If a metric is high or stretched, confront it directly — do not omit it, substitute a lower estimate, or quietly replace it with a range that appears more favorable. An analyst who ignores EV/FCF of 57x because it is ugly is worse than useless.

- **EV/FCF and EV/EBITDA**: Quote the exact figures from the Ground Truth block. How do they compare to the stock's own history and sector peers (use comparison data if available)? If FCF per share is null or near zero, explicitly state this and explain what it implies — heavy capex, negative FCF, or data unavailability are all materially different situations.
- **PEG**: Is the growth rate justifying the earnings multiple? **Critical: PEG is only a valid cheapness signal when EPS growth is positive AND represents sustainable operating earnings. Two cases where TTM PEG must NOT be cited as a directional signal, even with a caveat:**
  - **Negative EPS growth**: PEG is mathematically undefined. Omit entirely and rely on EV/FCF and EV/EBITDA.
  - **TTM EPS inflated by non-operating items** (investment gains, asset sales, insurance recoveries, one-time tax benefits): The TTM PEG will appear misleadingly low because the denominator is inflated by gains that don't recur. A caveat does not fix the anchor effect — citing "PEG of 1.57x but note the EPS is distorted" still anchors the reader to a misleadingly cheap number. In this case, omit TTM PEG entirely. If consensus EPS estimates are available in the Ground Truth Consensus EPS Estimates block, you may cite a forward PEG using the consensus forward EPS growth rate as the denominator (e.g., "On consensus forward EPS growth of X%, forward PEG is approximately Y on 24x forward P/E"). If no consensus estimates are available, omit PEG entirely and rely on EV/EBITDA and forward P/E.**
  - **Forward PEG construction rule**: When constructing a forward PEG, the denominator MUST be consensus forward EPS growth — from the `eps_estimates` block if available, or trailing EPS growth (`eps_growth_ttm_yoy`) if not. Do NOT use an internally-derived normalized growth rate (e.g., "normalized operating income growth of 25-27%") as the PEG denominator — this is a non-standard metric that departs from the conventional PEG definition and creates an unverifiable figure that typically appears more favorable than the standard calculation. If you cannot use consensus or trailing EPS growth, omit the PEG metric entirely rather than construct a custom version.
- **Forward multiple compression (required for long-horizon investors)**: For investors with a 3+ year horizon, today's TTM multiple is not the relevant price paid — the relevant price is what the multiple compresses to as earnings grow. Using consensus EBITDA and EPS growth estimates, project the forward EV/EBITDA and P/E at 2 and 3 years out (e.g., "At consensus 25% EBITDA growth, today's EV implies 32x 2027 EV/EBITDA and 21x 2028 EV/EBITDA"). Explicitly state: does the compressed multiple at year 2–3 represent fair value, cheap, or still expensive for the business quality? This analysis is the primary valuation lens for aggressive long-horizon investors — a stock that looks expensive on TTM multiples but compresses to an attractive multiple at consensus growth within the investor's horizon is a materially different risk/reward than a stock that remains expensive even on forward estimates. Flag high estimate uncertainty (4-year EBITDA projections have wide bands) but do not dismiss the framework.
- **Capital structure reconciliation**: If you reference multiple historical valuation figures for the same company (pre-IPO round valuations, tender offer prices, IPO price, secondary sales, current market cap), you MUST explicitly reconcile them: state the approximate share count and explain how the figures bridge to the current market cap. Two contradictory figures left unreferenced (e.g., "$175B pre-IPO valuation" and "$75B+ IPO" both cited without explaining how either maps to a $1.6T current market cap) is a factual error. If you cannot reconcile them with available data, acknowledge the inconsistency explicitly rather than citing both figures as if they are consistent.
- **Analyst consensus price target**: What upside or downside is implied vs. current price? How many analysts cover this? **Null rule: if `analyst_target_mean` is null in the raw data, you MUST NOT cite any analyst count, price target, or rating distribution (e.g. "29 buy / 13 hold / 2 sell") — state that analyst coverage data is unavailable from the provider. Do not substitute figures from training knowledge.**
- **Implied fair value range**: Based on available multiples, give an explicit range representing fair value (e.g., "$X–$Y based on X× forward EV/EBITDA at current growth"). Commit to numbers. **DCF rule**: If you present a DCF valuation, you MUST disclose the key inputs in the text: discount rate, terminal growth rate, the base cash flow or earnings figure used, and approximate share count. A DCF range without disclosed inputs ($90–$380 with no model shown) is not analysis — it is assertion. If `fcf_per_share_ttm` is null, you cannot anchor a DCF on FCF — say this explicitly and use multiple-based valuation (EV/EBITDA, forward P/E) as the primary framework. Do not silently substitute EPS proxies for FCF in a "DCF" without disclosing the substitution.
- **Margin of safety**: Explicitly state whether the current price offers a discount to fair value (buy zone), is at fair value (hold zone), or prices in optimistic assumptions (trim zone). If a risk-free rate is provided, note how the rate environment affects what multiple is justified.

## Growth & Earnings Quality
- Is revenue growth accelerating or decelerating? Compare the 1Y, 3Y, and 5Y growth rates if available. If TTM revenue growth is null, explicitly state this and do not substitute a multi-year CAGR as a proxy for current momentum without flagging the distinction.
- **Sequential EPS interpretation for early-stage or high-capex companies**: If EPS is deeply negative and worsens quarter-over-quarter (e.g., -$0.56 → -$1.12), do NOT label this as confirmed execution deterioration without first explicitly considering and ruling out: (1) seasonality, (2) one-time charges or write-downs, (3) deliberate capex or investment acceleration that management has guided toward. If you cannot distinguish the cause from available data, state explicitly: "The sequential loss deepening could reflect [specific alternatives]; insufficient data to confirm whether this is structural deterioration vs. timing or investment-driven."
- **Earnings beat/miss track record**: Review the earnings surprise history. Does management consistently beat estimates (credibility signal) or miss (execution risk)? Quote the average surprise %.
- **Estimate revision momentum**: Quote the net analyst rating-change balance in the past 90 days (upgrades minus downgrades from rating_changes_90d). Net positive revision activity — where more analysts are upgrading than downgrading — is a leading indicator of EPS estimate increases ahead and improves the reliability of forward consensus numbers. Net negative revisions flag deteriorating fundamental expectations. Also note near-term quarterly EPS estimate trajectory (eps_estimates_quarterly): are estimates for the next 2–3 quarters stepping up sequentially, flat, or declining? Declining quarterly estimates while annual consensus holds flat is a red flag — it means the market is back-half loading the year.

  When interpreting rating_changes_90d, weight analyst actions by sector expertise — not all firms carry equal signal:
  - **Tier 1 — Sector specialists (highest weight):** Tech/AI/Software/Cloud: Morgan Stanley, Goldman Sachs, Bernstein, KeyBanc, UBS, JPMorgan. Semiconductors: Morgan Stanley, BofA Securities, Goldman Sachs, Susquehanna, UBS. Consumer Internet: Goldman Sachs, Morgan Stanley, Bernstein, Citi. Biotech: Goldman Sachs, Morgan Stanley, Leerink Partners.
  - **Tier 2 — Bulge bracket generalists (moderate weight):** Citi, Deutsche Bank, Wells Fargo, Barclays — solid but less sector-specific depth.
  - **Tier 3 — Regional/boutique (base weight):** Count in the net balance but do not let a cluster of regional upgrades override a Tier 1 downgrade.
  - **Convergence signal:** If 3+ Tier 1 specialists for the relevant sector all upgrade within 30 days, treat this as materially stronger than the raw count implies. Name them explicitly.
  - **Divergence signal:** If a Tier 1 specialist downgrades while the rest of the street upgrades (or vice versa), flag this explicitly — sector specialists going against consensus often have better channel intelligence and deserve outsized attention.
  - **Conflict discount:** Firms that recently underwrote an equity offering or advised on M&A for this company have economic incentives to maintain positive coverage — discount their upgrades accordingly.
- Forward EPS and revenue estimates: If `eps_estimates` contains data, quote the consensus numbers and the YoY growth they imply. If `eps_estimates` is null or empty, you cannot cite a consensus forward EPS figure — instead, derive it from forward P/E and current price, label it explicitly as "market-implied forward EPS" (not "consensus"), and note that analyst estimates are not available in the dataset. Do not present a back-calculated figure as if it were an independent consensus. **Circular anchor rule**: A market-implied forward EPS (back-calculated from forward P/E) cannot be used to validate the forward P/E — this is circular. Use it only as a cross-check or to frame the implied growth expectation, never as an independent anchor that "confirms" the multiple is justified. **Scenario math rule**: Do NOT use a market-implied EPS as the base EPS figure in price scenario arithmetic (bull/base/bear price targets). If no consensus EPS is available, construct scenarios around revenue and margin assumptions or forward EV/EBITDA multiples — not around an EPS you derived by dividing the current price by the forward P/E, since that figure already assumes today's price is correct.
- **Short interest**: Quote the short ratio and trend. Rising short interest from sophisticated investors is a meaningful risk signal.
- **Insider activity**: If `insider_transactions` contains any entries, you MUST cite them — name the individuals, transaction type, share count, and price. Do not state that insider data is "not reported" or "unavailable" if the field is non-empty. For ADR stocks, insider transactions may reflect purchases on the primary listing exchange at local-currency prices (e.g., NT$ for TSM); cite them and note the exchange — the direction of the signal (buy vs. sell) is valid regardless of currency. Only omit this section if the array is genuinely empty.

## Bear Case
Write this as an institutional short seller's research note — not a balanced list of generic risks. The standard: articulate the specific mechanism by which this stock declines 40–50% from today's price. "Macro headwinds" and "competition could intensify" do not meet this standard.

**Sourcing rule**: Every specific quantitative claim in the bear case — revenue segment sizes, geographic concentration percentages, customer names and their share of revenue, market share figures, covenant thresholds, competitor pricing data — must come from the provided data: raw JSON, earnings release, 10-Q/20-F MD&A, or earnings transcript. If you cite a figure that is NOT in the provided data, you MUST label it explicitly as "[analyst estimate, unverified]". You MUST NOT use an unverified estimate as the primary input in a quantified price target.

**False precision rule**: Presenting an unsourced estimate with a specific number (e.g., "10-15% customer concentration triggers covenant breach", "top 3 customers = 50%+ of revenue") is worse than omitting it — specific thresholds imply you have a verified source when you do not. If you lack the data, use directional language: "customer concentration appears material based on available disclosures" — not a precise threshold you cannot verify. Reserve specific numbers for figures you can source.

For each of the 3 arguments:
1. Name the specific competitor, product, regulatory body, customer, or structural factor
2. Describe the exact chain of causation: how does that factor flow through revenue → margins → EPS → multiple compression?
3. Quantify the impact where possible: "If [X happens], EPS falls from $Y to $Z; at the lower justified multiple of N×, the stock is worth $W — a decline of X%."

**Multiple consistency rule**: When constructing a bear-case price target, BOTH the earnings estimate AND the valuation multiple must reflect bear-case assumptions. Applying a bear-case earnings figure (e.g., $2B net income) to a bull-case multiple (e.g., 100x P/E) does not produce a conservative floor — it understates the downside and gives the bear argument a misleadingly optimistic anchor. A genuine bear case applies a compressed multiple (typically the lower end of the stock's historical range, or 40–60% of the current trading multiple) to the depressed earnings estimate.

This section should genuinely pressure-test the bull thesis. If you cannot write a genuinely adversarial bear case, say so explicitly — a weak bear case is itself useful information for the investor.

## Earnings Call Analysis
[Include this section only if an earnings call transcript is provided. Skip entirely if not.]
The transcript is primary-source evidence from management — weight it at least as heavily as the press release. Analyze four things:

**Management Tone**: Has the tone shifted from what you would expect given the reported numbers? Note specific language. Words like "uncertain," "challenging," "cautious," or "we are monitoring" appearing where prior language was "confident," "accelerating," or "strong" are meaningful leading indicators — even when the headline numbers look fine. Quote specific phrasing if notable.

**Forward Guidance Quality**: Did management raise, hold, or effectively lower guidance? Quote the exact guidance language. Vague or range-widening language ("we expect revenue to be broadly in line") is often a soft warning dressed as neutral. Conservative but specific guidance ("we expect $X–$Y, with upside if Z executes") reflects genuine management credibility.

**Q&A Deflection**: Which analyst questions did management answer directly vs. deflect or redirect? Repeated avoidance of a specific topic — a margin question, a specific customer, a product line — is a signal worth naming. If deflection was apparent, name the topic.

**Delta from Press Release**: What did management say in the call that was NOT in the press release? The press release is curated; the Q&A is where unscripted, pressure-tested information emerges. Even a single candid admission in Q&A about pricing pressure, customer pushback, or competitive intensity can be more valuable than an entire page of polished press release language.

## Price Scenarios (12-month view)
Give three explicit price scenarios anchored to specific multiples and assumptions. Commit to numbers.
- **Bull case ($X)**: [key assumption that drives upside] at [Y× multiple on forward metric] = $X — probability: P%
- **Base case ($X)**: [most probable outcome] at [Y× multiple] = $X — probability: P%
- **Bear case ($X)**: [key assumption that drives downside] at [Y× multiple] = $X — probability: P%

The probability (P%) belongs at the end of each line, not in the header. Probabilities must sum to exactly 100%. The distribution reveals how you are actually thinking about risk/reward: a 60/30/10 split implies very different conviction than a 35/35/30 split.

State: "The current price of $X implies the market is pricing in approximately the [bull/base/bear] scenario."

**Acknowledged-scenario inclusion rule**: If you describe a more severe downside scenario anywhere in the analysis (e.g., "automotive de-rating to 15-20x implies $12-16/share"), that scenario MUST appear in the probability table — even if you assign it a low probability (5-10%). Acknowledging it elsewhere and excluding it from the weighted EV calculation produces a misleadingly optimistic expected value. Either include it in the table with an explicit probability, or do not describe it at all. You cannot have it both ways: described in text, absent from the math.

**Bear case EPS consistency rule**: The bear case EPS must be quantitatively consistent with the severity of the described bear case narrative. Before writing the bear case price target, ask: "If my described scenarios actually occurred, what would EPS be?" A bear case narrative that describes severe disruption (search disintermediation, structural market share loss, major impairments, capex-driven FCF drought) but uses a bear EPS only 5-10% below base case is internally inconsistent — the narrative implies 25-40% EPS destruction that the number doesn't reflect. Either (1) use a lower EPS that actually reflects the described scenarios and show the calculation, or (2) describe less severe scenarios consistent with the mild EPS assumption. Applying a compressed multiple to a nearly-unchanged earnings figure does not constitute a genuine bear case — it understates the downside the narrative implies.

## Thesis Check
[Include this section only if the investor provided their original buy thesis. Skip entirely if not.]
Go through their original thesis point by point. For each claim: Still true / Strengthened / Weakened / Broken. Be blunt.

## Peer Context
[Include this section only if peer comparison data is provided. Skip entirely if not.]
How does this stock look relative to peers on valuation, growth, and margins? Is it cheap or expensive for what you get? Would the capital be better deployed elsewhere in the sector? When citing peer figures (e.g., NVDA forward P/E 19.2x, AVGO EV/EBITDA 23.2x), note they are "from the peer comparison data" — these figures are provided in the peer comparison table, not the raw JSON, and are included as context for relative valuation only.

## Profile Fit
Does this stock match THIS investor's risk tolerance, time horizon, and investment goal RIGHT NOW? 1–2 sentences. A great business can be the wrong stock for a specific investor profile at a specific price. Name any mismatch clearly.

## What Has Changed
3–5 bullet points on what has materially changed since a reasonable entry thesis would have been formed. Business facts only — not price action. Every bullet must be supported by the provided data (raw JSON, news articles, earnings releases, SEC filings). Do NOT cite specific institutional position initiations (e.g., "Berkshire Hathaway initiated a position") unless the provided data includes institutional holdings data, a 13F reference, or a news article confirming the position — if unsupported by provided data, omit it rather than presenting it as fact.

## Key Risks
2–3 specific, concrete risks that could cause the signal to worsen. "Macro headwinds" is not a risk. "Gross margin compression if [specific competitor] wins market share in [specific segment] by undercutting on price" is a risk. Be specific.

## What to Watch
2–3 specific, measurable catalysts or metrics to track. Each trigger must be observable and specific — not a direction.
Format: "Watch [specific metric or event] — if [specific measurable condition, e.g. 'Q3 revenue comes in below $X billion on the [date] earnings call'], then [clear implication for the signal]."

## When to Change Your Signal
Provide exactly 3 conditions. You MUST include the immediately adjacent signals on both sides — do not skip steps.
1. An upgrade condition (to the signal one step above current)
2. A downgrade condition (to the signal one step below current — mandatory, never skip)
3. A second downgrade condition (to a signal two steps below, for a more severe scenario)

Format: "Upgrade to [signal] if [specific condition]" or "Downgrade to [signal] if [specific condition]."
Only use signal names from: Add to Position, Strong Hold, Hold, Consider Trimming, Consider Exiting, Exit Signal.
Be specific — name actual metrics, price levels, or events.

**Single-trigger rule**: Each condition must identify ONE dominant factor. AND logic across multiple simultaneous requirements ("Downgrade if X AND Y AND Z") is practically impossible to fire — prohibited. OR logic is permitted only when the two triggers are variations of the same underlying mechanism (e.g., "revenue misses in Q3 OR Q4"). Do NOT join triggers with OR if they have fundamentally different probability profiles or mechanisms (e.g., "pricing cut OR management change" — these are unrelated scenarios that deserve separate evaluation). In that case, pick the single most important trigger and drop the weaker one.

**Dual upgrade path rule**: If the Conditional Signal section already defines an upgrade path to a specific signal (e.g., Strong Hold), the upgrade condition in this section must be consistent with it — either use the same criteria, or explicitly note how they differ and why. Two overlapping upgrade paths to the same target signal with different criteria create ambiguity about which conditions actually govern the upgrade. If the Conditional Signal is investor-subjective ("if you believe X") and the When to Change Signal is forward-looking ("when the company reports Y"), make this distinction explicit.

**Forward-observable trigger rule**: Every upgrade and downgrade condition must reference a FUTURE event — something the investor can monitor after reading this analysis. An upgrade trigger MUST NOT direct the reader to verify currently-available information from existing public filings, press releases, or SEC documents. Such information should be resolved by the analyst before publishing, not presented as a monitoring trigger. A flawed trigger: "Upgrade to Strong Hold if you read the existing 10-Q and confirm the $97.983B charge was non-recurring." A valid trigger: "Upgrade to Strong Hold if management confirms on the next earnings call that the other income item was non-recurring and will not recur in future quarters."

---
*AI-generated analysis for informational purposes only. Not financial advice.*"""


async def run_hold_check_agent(
    ticker: str,
    purchase_price: float,
    quant_analysis: str,
    news_analysis: str,
    client: anthropic.Anthropic,
    user_thesis: str = "",
    current_price: float = 0.0,
    user_context: dict | None = None,
    comparison_table: str = "",
    earnings_release: str = "",
    mda_text: str = "",
    treasury_yield: float | None = None,
    transcript: str = "",
    raw_metrics: str = "",
    chunk_queue: asyncio.Queue | None = None,
    raw_data: dict | None = None,
) -> str:
    ctx = user_context or {}
    ck = _cache_key(
        ticker,
        ctx.get("risk", "moderate"),
        ctx.get("horizon", "medium-term"),
        ctx.get("goal", "growth"),
        purchase_price,
        user_thesis,
    )
    if ck in _hold_cache:
        return _hold_cache[ck]

    price_context = ""
    if purchase_price > 0 and current_price > 0:
        pct = ((current_price - purchase_price) / purchase_price) * 100
        direction = "up" if pct >= 0 else "down"
        price_context = (
            f"Entry price: ${purchase_price:.2f}. "
            f"Current price: ${current_price:.2f} "
            f"({direction} {abs(pct):.1f}% from entry)."
        )
    elif purchase_price > 0:
        price_context = f"Entry price: ${purchase_price:.2f}."

    thesis_text = (
        f'Original reason for buying: "{user_thesis.strip()}"'
        if user_thesis.strip()
        else "The investor did not provide their original buy reason."
    )

    profile_text = ""
    if user_context:
        profile_text = (
            f"\n## Investor Profile\n"
            f"- Risk tolerance: {user_context.get('risk', 'moderate')}\n"
            f"- Time horizon: {user_context.get('horizon', 'medium-term')} "
            f"(short = under 1 year, medium = 1–3 years, long = 3+ years)\n"
            f"- Investment goal: {user_context.get('goal', 'growth')}\n"
        )

    peer_section = (
        f"\n## Peer Comparison Data\n{comparison_table}\n"
        if comparison_table
        else ""
    )

    edgar_section = (
        f"\n## SEC Earnings Release (Most Recent 8-K / 6-K)\n{earnings_release}\n"
        if earnings_release
        else ""
    )

    mda_section = (
        f"\n## Management Discussion & Analysis (Most Recent 10-Q / 20-F)\n{mda_text}\n"
        if mda_text
        else ""
    )

    transcript_section = (
        f"\n## Earnings Call Transcript (Most Recent)\n{transcript}\n"
        if transcript
        else ""
    )

    macro_section = (
        f"\n## Macro Context\n"
        f"Current 10-Year US Treasury yield: {treasury_yield:.2f}% — use this as the risk-free rate "
        f"when contextualizing valuation multiples. Higher rates compress justifiable P/E and EV/FCF multiples.\n"
        if treasury_yield is not None
        else ""
    )

    raw_metrics_section = f"\n{raw_metrics}\n" if raw_metrics else ""

    anchors_section = ""
    if raw_data:
        anchors = _compute_10yr_model(raw_data)
        if anchors:
            anchors_section = _format_10yr_anchors(anchors)

    user_message = (
        f"Analyze the hold thesis for {ticker.upper()}.\n\n"
        f"## Entry Context\n"
        f"{price_context}\n"
        f"{thesis_text}\n"
        f"{profile_text}"
        f"{macro_section}"
        f"{anchors_section}"
        f"{raw_metrics_section}"
        f"\n## Current Quantitative Data\n"
        f"{quant_analysis}\n"
        f"\n## Recent News & Sentiment\n"
        f"{news_analysis}"
        f"{peer_section}"
        f"{edgar_section}"
        f"{mda_section}"
        f"{transcript_section}"
    )

    loop = asyncio.get_event_loop()

    def _run_phase(system_text: str, msg: str, use_thinking: bool, max_tok: int) -> str:
        parts: list[str] = []
        model = "claude-sonnet-4-6" if use_thinking else "claude-haiku-4-5-20251001"
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tok,
            "system": [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": msg}],
        }
        if use_thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 6000}
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                parts.append(text)
                if chunk_queue is not None:
                    loop.call_soon_threadsafe(chunk_queue.put_nowait, text)
        return "".join(parts)

    # Phase 1: Pre-Check + Signal + 10-Year Outlook (with extended thinking)
    phase1_text = await loop.run_in_executor(
        None, _run_phase, SYSTEM_PHASE1, user_message, True, 16000
    )
    if not phase1_text:
        return "Hold check unavailable."

    # Phase 2: All narrative sections (no thinking — structured read-and-write)
    phase2_user = (
        user_message
        + "\n\n---\n\n## Phase 1 Output — Signal and 10-Year Outlook (already completed; be consistent with this)\n\n"
        + phase1_text
        + "\n\n---\n\nWrite the remaining sections starting from ## Conditional Signal."
    )
    phase2_text = await loop.run_in_executor(
        None, _run_phase, SYSTEM_PHASE2, phase2_user, False, 16000
    )

    full_text = phase1_text + "\n\n" + phase2_text
    # Strip strikethrough — run twice: non-greedy (handles multiple pairs) then
    # greedy (catches any remaining single long span the non-greedy missed)
    result = re.sub(r'~~([\s\S]+?)~~', r'\1', full_text)
    result = re.sub(r'~~([\s\S]+)~~', r'\1', result)
    result = re.sub(r'<del>([\s\S]+?)</del>', r'\1', result, flags=re.IGNORECASE)
    if len(result) > 1500 and "signal:" in result.lower():
        _hold_cache[ck] = result
    return result
