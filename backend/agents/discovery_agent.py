import anthropic
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tools.market_tools import get_all_stock_data

_executor = ThreadPoolExecutor(max_workers=8)

SYSTEM = """You are a stock discovery agent. Given a natural language description of what a user is looking for, find 3-5 publicly traded US stocks that best match.

Steps:
1. Interpret the query — identify key criteria (sector, growth rate, valuation, risk level, dividend, etc.)
2. Think of 6-8 candidate tickers based on your knowledge of well-known public companies
3. Call get_stock_data for each candidate to verify with real current data
4. Select and rank the top 3-5 based on actual fit with the query AND the investor profile

For each recommendation, assign a signal based on the data you fetched and the investor's profile:
- "Add to Position" — accelerating fundamentals, valuation still reasonable, strong analyst conviction, good profile fit
- "Strong Hold" — great business, executing well, but fully valued or not a compelling add right now
- "Hold" — solid but with minor concerns or slight profile mismatch
- "Partial Match" — fits some criteria but not ideal

If the user is asking for stocks to buy or add to, only include stocks that genuinely qualify as "Add to Position" — do not include stocks that are merely "Strong Hold" or lower just to fill the list.

Return ONLY a raw JSON object (no markdown, no code blocks, no explanation outside JSON):
{
  "recommendations": [
    {
      "ticker": "TICKER",
      "company": "Full Company Name",
      "match": "Add to Position",
      "rationale": "2-3 sentences explaining why this fits the user's query using real data you fetched",
      "highlight": "The single most compelling data point (e.g. '47% revenue growth YoY' or 'Fwd P/E of 12x vs sector avg 22x')"
    }
  ]
}

match values must be exactly one of: "Add to Position", "Strong Hold", "Hold", "Partial Match"."""


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
