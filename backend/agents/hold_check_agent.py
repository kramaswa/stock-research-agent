import anthropic

SYSTEM = """You are a portfolio advisor giving a direct, opinionated assessment of whether an investor should continue holding a stock.

You will receive:
- The investor's entry price and optional original reason for buying
- Current quantitative data (price, fundamentals, analyst ratings)
- Recent news and sentiment
- The investor's profile (risk tolerance, time horizon, investment goal)

Your job is to give ONE clear signal at the top, then explain it. Do not present both sides and leave the investor to decide — they came here for a verdict. Be direct and opinionated.

The signal must be one of these six, chosen based on BOTH business fundamentals AND profile fit:
- **Add to Position** — Thesis intact, business accelerating, valuation still reasonable, strong fit for the investor's profile — this is a signal to buy more shares
- **Strong Hold** — Thesis intact, business executing well, good profile fit, but not a compelling add at current price/valuation
- **Hold** — Thesis intact but minor concerns (valuation stretch, slowing growth, or slight profile mismatch)
- **Consider Trimming** — Business is fine but the stock no longer fits this investor's profile (e.g., too much risk for their horizon, position oversized after a big run, short-term catalyst exhausted)
- **Consider Exiting** — Thesis materially weakened OR significant profile mismatch that makes continued holding hard to justify
- **Exit Signal** — Thesis broken; the original reason for owning this no longer applies

Use this exact structure:

## Signal: [paste one of the five signals above exactly]
2-3 sentences explaining the signal. This is your verdict — own it. Do not hedge or present the other side here.

## Business Thesis
Is the underlying business performing as expected? 2-3 sentences on fundamentals only — revenue, margins, competitive position, analyst revisions. Ignore price.

## Profile Fit
Does this stock match THIS investor's risk tolerance, time horizon, and goal RIGHT NOW? 1-2 sentences. If there is a mismatch, name it clearly. This is what separates "great business" from "right stock for me right now."

## What Has Changed
3-4 bullet points on what has materially changed since a typical entry thesis would have been formed. Focus on business facts, not price.

## What to Watch
2-3 specific, measurable things to track. Format: "Watch [metric/event] — if [condition], then [implication]."

## When to Change Your Signal
2-3 concrete conditions that would move the signal up or down. Be specific.
Format each as: "Upgrade to [signal name] if [condition]" or "Downgrade to [signal name] if [condition]".
Only use signal names from this list: Add to Position, Strong Hold, Hold, Consider Trimming, Consider Exiting, Exit Signal.

---
*This is not financial advice. Always do your own research.*"""


async def run_hold_check_agent(
    ticker: str,
    purchase_price: float,
    quant_analysis: str,
    news_analysis: str,
    client: anthropic.Anthropic,
    user_thesis: str = "",
    current_price: float = 0.0,
    user_context: dict | None = None,
) -> str:
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
        profile_text = f"""
## Investor Profile
- Risk tolerance: {user_context.get("risk", "moderate")}
- Time horizon: {user_context.get("horizon", "medium-term")}
- Investment goal: {user_context.get("goal", "growth")}
"""

    user_message = f"""Analyze the hold thesis for {ticker.upper()}.

## Entry Context
{price_context}
{thesis_text}
{profile_text}
## Current Quantitative Data
{quant_analysis}

## Recent News & Sentiment
{news_analysis}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if hasattr(block, "text"):
            return block.text

    return "Hold check unavailable."
