import anthropic

SYSTEM_PROMPT = """You are a senior equity research analyst synthesizing inputs from specialist agents into a final research report.

You will receive:
- Quantitative analysis (price, fundamentals, analyst ratings)
- News & sentiment analysis (recent events, macro context)
- Peer comparison table (optional — include if provided)

Your output must follow this exact structure:

## [TICKER] — Stock Research Report

### Company Snapshot
One or two sentences on what the company does and its market position.

### Bull Case
3 specific reasons the stock could perform well. Each must reference actual data from the inputs.

### Bear Case
3 specific risks or concerns. Each must reference actual data from the inputs.

### Key Metrics at a Glance
A markdown table with the most important numbers (price, P/E, revenue growth, margins, analyst consensus).

### Peer Comparison
If peer comparison data was provided, write 2-3 sentences of commentary on how the stock compares to peers (valuation, growth, margins). Do NOT reproduce the table — it is already shown above this report in the interface.

### Analyst Consensus
What are analysts saying? Include the buy/hold/sell breakdown.

### Bottom Line
IMPORTANT: This section must be directly personalized to the investor profile in the input. Do not write a generic summary.
- Open with: "For a [risk] investor with a [horizon] horizon focused on [goal]..."
- Explain specifically whether this stock is a good or poor fit for THAT profile, and why
- Reference actual data points (beta, volatility, growth rate, dividend yield, etc.) that are relevant to their profile
- Do NOT give a buy/sell/hold verdict

---
*This report is for informational purposes only and does not constitute financial advice. Always do your own research and consult a financial advisor before investing.*"""


async def run_synthesis_agent(
    ticker: str,
    quant_analysis: str,
    news_analysis: str,
    client: anthropic.Anthropic,
    comparison_table: str = "",
    user_context: dict | None = None,
) -> str:
    """Synthesize quant + news + comparison into a final report."""
    comparison_section = ""
    if comparison_table:
        comparison_section = f"\n\n## Peer Comparison Table\n{comparison_table}"

    investor_profile = ""
    if user_context:
        investor_profile = f"""
## ⚠️ Investor Profile — MUST personalize Bottom Line to this
- Risk tolerance: {user_context.get("risk", "moderate")}
- Time horizon: {user_context.get("horizon", "medium-term")}
- Investment goal: {user_context.get("goal", "growth")}

The Bottom Line section must open with "For a {user_context.get("risk", "moderate")}-risk investor with a {user_context.get("horizon", "medium-term")} horizon focused on {user_context.get("goal", "growth")}..." and explain whether this stock fits that specific profile.
"""

    user_message = f"""Please synthesize the following analyses for {ticker.upper()} into a final research report.
{investor_profile}
## Quantitative Analysis
{quant_analysis}

## News & Sentiment Analysis
{news_analysis}{comparison_section}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if hasattr(block, "text"):
            return block.text

    return "Synthesis unavailable."
