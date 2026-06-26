import anthropic
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tools.market_tools import get_all_stock_data

_executor = ThreadPoolExecutor(max_workers=8)

SYSTEM = """You are a stock discovery agent. Given a natural language description of what a user is looking for, find 3-6 publicly traded US stocks that best match.

Steps:
1. Interpret the query — identify sector/style criteria AND any investment action intent (e.g. "add to position", "strong hold", "buy more")
2. Think of 15-18 diverse candidate tickers across sub-sectors and market caps
3. Call get_stock_data for each candidate to verify with real current data
4. Score each candidate and assign a match label — return up to 10 results

MATCH LABEL DEFINITIONS:

"Strong Match" — only use this if the stock passes ALL of:
  • Fits the sector/style criteria in the query
  • Revenue growth > 10% YoY
  • EPS is growing YoY (not declining)
  • Valuation is reasonable: PEG < 2.5x, or forward P/E clearly justified by growth (e.g. 30x P/E with 30%+ growth is fine; 80x P/E with 10% growth is not)
  • Not in an active downtrend: the stock must NOT be within 20% of its 52-week LOW — a stock near its 52-week low is a falling knife, not a discount opportunity, even if it's far below its 52-week high
  • 52-week return < 50%, OR if higher, the stock is still meaningfully below its 52-week high (>15% discount), meaning room to add
  • Analyst consensus is majority Buy/Strong Buy (not just a slight majority)
  If the user asked for "strong hold" or "add to position" stocks specifically, "Strong Match" means the data would support an Add to Position or Strong Hold signal — a good business that has ALREADY repriced fully is a Hold, not a Strong Match for adding

"Good Match" — fits most criteria but has one meaningful caveat (e.g. great business but stock has run hard, or strong growth but EPS not yet positive)

"Partial Match" — fits the sector/style but fails on valuation, earnings trend, or price action

Return as many Strong Matches as genuinely qualify. Do not pad with lower-quality matches. Do not assign Strong Match just because analyst consensus is bullish — price action and valuation relative to growth matter equally.

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
