import anthropic
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tools.market_tools import get_all_stock_data

_executor = ThreadPoolExecutor(max_workers=8)

SYSTEM = """You are a stock discovery agent. Given a natural language description of what a user is looking for, find 3-5 publicly traded US stocks that best match.

Steps:
1. Interpret the query — identify key criteria (sector, growth rate, valuation, risk level, dividend, etc.)
2. If the query includes investment action intent (e.g. "add to position", "strong hold", "buy more", "stocks I can add to"), note this — it requires stricter filtering in step 5.
3. Think of 10-12 diverse candidate tickers based on your knowledge of well-known public companies — cast a wide net across sub-sectors and market caps to avoid missing qualified names
4. Call get_stock_data for each candidate to verify with real current data
5. Select and rank the top 3-6 based on actual fit with the query AND the investor profile — return as many Strong Matches as genuinely qualify; do not pad with Good/Partial Matches just to reach a count

Assigning match labels:
- "Strong Match" — fits all key criteria AND, if the user specified an investment action (add/buy/strong hold), the data supports it: strong analyst buy ratings (more Buy/Strong Buy than Hold/Sell), positive revenue growth, and valuation that is not extreme relative to growth. Do NOT assign "Strong Match" if the stock fails the investment action test.
- "Good Match" — fits most criteria with minor caveats
- "Partial Match" — fits some criteria but not ideal

If the query asks for stocks suitable to "add to position", "buy more", or "strong hold":
- Analyst consensus alone is NOT sufficient — a stock can have 50 Buy ratings and still be a Hold if valuation or price action is unfavorable
- For moderate or conservative risk profiles: downgrade or exclude stocks where forward P/E > 80x AND EPS growth is flat or negative — these are priced for perfection
- For aggressive risk profiles: forward P/E > 120x AND declining EPS is the threshold
- Also consider recent price momentum: if a stock is up >45% over 52 weeks AND the forward P/E is not clearly cheap (e.g. < 20x), the risk/reward is likely already balanced — downgrade to "Good Match" or "Partial Match" and note this in the rationale
- Only assign "Strong Match" if the stock passes the sector/style fit, valuation/earnings test, AND has not already repriced so aggressively that adding more carries asymmetric downside risk
- Be honest in the rationale — if a stock is a great business but has run too far to add at current prices, say so clearly

Return ONLY a raw JSON object (no markdown, no code blocks, no explanation outside JSON):
{
  "recommendations": [
    {
      "ticker": "TICKER",
      "company": "Full Company Name",
      "match": "Strong Match",
      "rationale": "2-3 sentences explaining why this fits the user's query using real data you fetched",
      "highlight": "The single most compelling data point (e.g. '47% revenue growth YoY' or 'Fwd P/E of 12x vs sector avg 22x')"
    }
  ]
}

match values must be exactly one of: "Strong Match", "Good Match", "Partial Match"."""


async def run_discovery_agent(query: str, user_context: dict, client: anthropic.Anthropic) -> list[dict]:
    loop = asyncio.get_event_loop()

    tools = [
        {
            "name": "get_stock_data",
            "description": "Fetch real-time price, fundamentals, and analyst data for a stock ticker.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"}
                },
                "required": ["ticker"],
            },
        }
    ]

    messages = [
        {
            "role": "user",
            "content": f"""Find stocks matching this request: "{query}"

Investor profile:
- Risk tolerance: {user_context.get("risk", "moderate")}
- Time horizon: {user_context.get("horizon", "medium-term")}
- Investment goal: {user_context.get("goal", "growth")}

Call get_stock_data for each candidate to get real metrics before finalizing your recommendations.""",
        }
    ]

    for _ in range(12):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            fetch_tasks = []
            for block in response.content:
                if block.type == "tool_use" and block.name == "get_stock_data":
                    ticker = block.input.get("ticker", "").upper().strip()
                    fetch_tasks.append((block.id, ticker))

            async def fetch(tool_use_id: str, t: str):
                try:
                    data = await loop.run_in_executor(_executor, get_all_stock_data, t)
                    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(data)}
                except Exception as e:
                    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps({"error": str(e)})}

            tool_results = await asyncio.gather(*[fetch(tid, t) for tid, t in fetch_tasks])

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": list(tool_results)})

        elif response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text.strip()
                    if "```" in text:
                        parts = text.split("```")
                        for part in parts:
                            part = part.strip()
                            if part.startswith("json"):
                                part = part[4:].strip()
                            try:
                                result = json.loads(part)
                                return result.get("recommendations", [])
                            except Exception:
                                continue
                    else:
                        try:
                            result = json.loads(text)
                            return result.get("recommendations", [])
                        except Exception:
                            pass
            return []
        else:
            break

    return []
