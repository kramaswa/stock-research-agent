import asyncio
import json
import re
import anthropic

EVAL_SYSTEM = """You are a senior equity research director performing quality control on hold check analyses. Your job: find errors, unsupported claims, weak reasoning, and give actionable feedback. Be rigorous. Generic praise is useless.

You receive:
1. Raw quantitative data (JSON) — the definitive source of truth for all numbers
2. Investor profile (risk, horizon, goal)
3. The hold check analysis to evaluate

## STEP 1 — ANSWER THE 4 PRE-CHECK QUESTIONS FROM RAW DATA

Q1: Was the stock up >30% in the trailing 6 months OR >50% in the trailing 12 months?
  Use: return_26w_pct (6-month), return_52w_pct (12-month). If either null, note that.

Q2: Is EV/FCF above 40x OR EV/EBITDA above 25x OR forward P/E above 30x?
  Use: ev_to_fcf_ttm, ev_ebitda_ttm, forward_pe. Any one being above the threshold = YES.

Q3: Does the current valuation require above-consensus growth assumptions to justify?
  Consider: if eps_growth_ttm_yoy < 0 (EPS declining) and forward_pe > 20x, likely YES. If multiples are modest relative to growth, likely NO. Use judgment.

Q4: Would a new investor buying at today's price have a clear margin of safety?
  Consider EV/FCF, EV/EBITDA, forward P/E against growth rate. If EV/FCF < 20x for a quality business, likely YES. If all multiples are stretched, likely NO. BORDERLINE if one metric looks cheap but others are stretched.

## STEP 2 — APPLY PROFILE RULES

Conservative or Moderate (any horizon): if 2+ of Q1–Q3 are YES, or Q4 is NO → signal CANNOT be Strong Hold or better.
Short horizon (any risk): same restriction as conservative/moderate.
Aggressive + Long: relaxed thresholds allowed. Q4 can be BORDERLINE and Strong Hold is still OK. But if Q4 is clearly NO (all multiples stretched, no margin of safety), Strong Hold is still wrong.

Flag any signal that violates these rules as severity "critical".

## STEP 3 — CHECK DATA ACCURACY

Cross-reference specific numbers the analyst cites against the raw JSON. Key checks:
- PEG validity: if eps_growth_ttm_yoy is negative (EPS declining YoY), and the hold check uses PEG as a cheapness signal, flag "major" — PEG computed on revenue growth when EPS is declining is a misleading anchor.
- Quoted valuation multiples: verify ev_to_fcf_ttm, ev_ebitda_ttm, forward_pe match what the analyst stated.
- Any specific number cited that cannot be found in the raw data is a "minor" issue.

## STEP 4 — EVALUATE BEAR CASE QUALITY

Grade on three criteria:
a) Specificity: names actual competitors, products, regulatory bodies, customers (not "competition could intensify" or "macro headwinds")
b) Mechanism: traces [specific cause] → [revenue/margin impact] → [EPS change] → [multiple compression] → [price target]
c) Quantification: gives specific $ numbers ("EPS falls from $X to $Y at Nx multiple = $Z stock price, a N% decline")
Grade: A = all three, B = specificity + mechanism, C = only specificity, D = generic

## STEP 5 — CHECK INTERNAL CONSISTENCY

a) Signal vs. tone: if the analysis reads as skeptical throughout but awards Strong Hold, flag it.
b) Conditional Signal step: if present, it MUST be exactly one step up on the six-signal ladder: Exit Signal → Consider Exiting → Consider Trimming → Hold → Strong Hold → Add to Position. If signal is Hold, conditional must be Strong Hold only — not "Add to Position" or anything else.
c) Price scenario probabilities must sum to 100%.
d) "When to Change Signal" must have exactly 3 conditions: upgrade to adjacent signal, downgrade to adjacent, downgrade two steps.

## STEP 6 — SECTION COMPLETENESS

Required sections: Signal, Business Quality (4 sub-bullets), Accounting Quality (3 sub-bullets), Valuation, Growth & Earnings Quality, Bear Case (3 arguments), Price Scenarios (3 scenarios + probabilities), Profile Fit, What Has Changed, Key Risks, What to Watch, When to Change Your Signal.
Optional: Conditional Signal (only if single dominant assumption drives the signal — verify this is true), Earnings Call Analysis, Thesis Check, Peer Context.

## OUTPUT FORMAT

Respond with ONLY valid JSON — no markdown fences, no explanation text outside the JSON:

{
  "overall_grade": "A" | "B" | "C" | "D" | "F",
  "signal_verdict": "correct" | "likely_correct" | "overcautious" | "overaggressive" | "rule_violation",
  "signal_explanation": "one concise sentence",
  "pre_check": {
    "q1": {"answer": "YES" | "NO", "evidence": "return_26w_pct = X%, return_52w_pct = Y%"},
    "q2": {"answer": "YES" | "NO", "evidence": "EV/FCF = Xx, EV/EBITDA = Xx, fwd P/E = Xx"},
    "q3": {"answer": "YES" | "NO", "evidence": "one sentence"},
    "q4": {"answer": "YES" | "NO" | "BORDERLINE", "evidence": "one sentence"},
    "profile_rule": "which rule applies to this profile and why",
    "signal_allowed": "what signals are permitted under the rule",
    "violation": null
  },
  "issues": [
    {"severity": "critical" | "major" | "minor", "section": "section name", "description": "specific issue"}
  ],
  "bear_case_grade": "A" | "B" | "C" | "D",
  "bear_case_feedback": "specific actionable critique, max 2 sentences",
  "section_scores": {
    "signal": "A" | "B" | "C" | "D" | "F",
    "business_quality": "A" | "B" | "C" | "D",
    "valuation": "A" | "B" | "C" | "D",
    "accounting_quality": "A" | "B" | "C" | "D",
    "growth_earnings": "A" | "B" | "C" | "D",
    "bear_case": "A" | "B" | "C" | "D",
    "price_scenarios": "A" | "B" | "C" | "D"
  },
  "strengths": ["strength 1", "strength 2"],
  "improvements": ["specific improvement 1", "specific improvement 2"],
  "summary": "2–3 sentence overall assessment"
}"""


def _quant_subset(raw: dict) -> dict:
    """Extract the fields most relevant to signal correctness and data accuracy."""
    return {
        "ticker": raw.get("ticker"),
        "company_name": raw.get("company_name"),
        "sector": raw.get("sector"),
        "current_price": raw.get("current_price"),
        # Performance — used for Q1
        "return_5d_pct": raw.get("return_5d_pct"),
        "return_13w_pct": raw.get("return_13w_pct"),
        "return_26w_pct": raw.get("return_26w_pct"),
        "return_52w_pct": raw.get("return_52w_pct"),
        "return_ytd_pct": raw.get("return_ytd_pct"),
        # Valuation — used for Q2, Q4, data accuracy
        "pe_ttm": raw.get("pe_ttm"),
        "forward_pe": raw.get("forward_pe"),
        "peg_ttm": raw.get("peg_ttm"),
        "ev_ebitda_ttm": raw.get("ev_ebitda_ttm"),
        "ev_to_fcf_ttm": raw.get("ev_to_fcf_ttm"),
        "price_to_book": raw.get("price_to_book"),
        "price_to_sales_ttm": raw.get("price_to_sales_ttm"),
        # Growth — used for Q3, Q4
        "revenue_growth_ttm_yoy": raw.get("revenue_growth_ttm_yoy"),
        "revenue_growth_3y": raw.get("revenue_growth_3y"),
        "revenue_growth_5y": raw.get("revenue_growth_5y"),
        "eps_ttm": raw.get("eps_ttm"),
        "eps_growth_ttm_yoy": raw.get("eps_growth_ttm_yoy"),
        "eps_growth_3y": raw.get("eps_growth_3y"),
        "eps_growth_5y": raw.get("eps_growth_5y"),
        "fcf_per_share_ttm": raw.get("fcf_per_share_ttm"),
        # Profitability
        "gross_margin_ttm": raw.get("gross_margin_ttm"),
        "operating_margin_ttm": raw.get("operating_margin_ttm"),
        "net_margin_ttm": raw.get("net_margin_ttm"),
        "roe_ttm": raw.get("roe_ttm"),
        "roic_ttm": raw.get("roic_ttm"),
        # Financial health
        "debt_to_equity": raw.get("debt_to_equity"),
        "dividend_yield": raw.get("dividend_yield"),
        # Analyst consensus
        "analyst_target_mean": raw.get("analyst_target_mean"),
        "analyst_target_high": raw.get("analyst_target_high"),
        "analyst_target_low": raw.get("analyst_target_low"),
        # Forward estimates
        "eps_estimates": raw.get("eps_estimates"),
        "revenue_estimates": raw.get("revenue_estimates"),
        "eps_estimates_quarterly": raw.get("eps_estimates_quarterly"),
        "earnings_history": raw.get("earnings_history"),
        "rating_changes_90d": raw.get("rating_changes_90d"),
        "short_interest": raw.get("short_interest"),
        "insider_transactions": raw.get("insider_transactions"),
    }


async def run_eval_agent(
    ticker: str,
    hold_check_output: str,
    raw_quant_data: dict,
    investor_profile: dict,
    client: anthropic.Anthropic,
) -> dict:
    quant_subset = _quant_subset(raw_quant_data)

    user_message = (
        f"## Investor Profile\n"
        f"- Risk tolerance: {investor_profile.get('risk', 'moderate')}\n"
        f"- Time horizon: {investor_profile.get('horizon', 'medium-term')}\n"
        f"- Investment goal: {investor_profile.get('goal', 'growth')}\n\n"
        f"## Raw Quantitative Data (ground truth)\n"
        f"```json\n{json.dumps(quant_subset, indent=2, default=str)}\n```\n\n"
        f"## Hold Check Output to Evaluate\n"
        f"{hold_check_output}"
    )

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=[{"type": "text", "text": EVAL_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_message}],
        ),
    )

    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text = block.text
            break

    # Strip markdown fences if the model wrapped the JSON
    raw_text = re.sub(r"^```json\s*", "", raw_text.strip())
    raw_text = re.sub(r"```\s*$", "", raw_text.strip())

    return json.loads(raw_text)
