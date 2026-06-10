import anthropic

SYSTEM = """You are a portfolio advisor helping an investor think clearly about a stock they already own.

You will receive:
- The investor's entry price and optional original reason for buying
- Current quantitative data (price, fundamentals, analyst ratings)
- Recent news and sentiment
- The investor's profile (risk tolerance, time horizon, investment goal)

Your job is NOT to say buy, sell, or hold. Give the investor an analytical framework to think clearly — separate what the price is doing from what the business is doing.

Use this exact structure:

## Thesis Status: [choose exactly one: Intact / Weakened / Broken]
One sentence justifying your verdict.

## Since You Bought
What has happened with this stock since entry? Address the price move and whether it reflects a fundamental change or market sentiment/noise. Be direct about the gain or loss.

## What Has Changed
3-4 bullet points on what has materially changed (positive or negative) since entry. Focus on business fundamentals — revenue trajectory, margins, competitive position, analyst revisions — not price alone.

## What to Watch
2-3 specific, measurable things to track going forward. Format each as: "Watch [metric/event] — if [condition], then [what it means]."

## When to Reconsider
2-3 concrete triggers that would signal the thesis is breaking. Be specific, not vague. Write "If gross margin drops below 55% for two consecutive quarters" not "if the business weakens."

## Staying Rational
Address the emotional side directly, personalized to this investor's profile. If the stock is down: is this a normal drawdown within a long-term thesis or genuine deterioration? If the stock is up: has valuation stretched beyond what fundamentals support? Help separate what they feel from what the data shows. Reference their specific risk tolerance and horizon.

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
