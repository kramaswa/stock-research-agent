import anthropic
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tools.market_tools import get_all_stock_data
from agents.quant_agent import run_quant_agent
from agents.news_agent import run_news_agent

_executor = ThreadPoolExecutor(max_workers=8)

# Phase 1: screen candidates with raw Finnhub data — return candidate tickers only
SYSTEM_SCREEN = """You are a stock screening agent. Given a user query, identify the most promising candidate stocks for deeper analysis.

Steps:
1. Interpret the query — sector/style criteria AND any investment action intent (e.g. "add to position", "buy more", "strong hold")
2. Think of 15-18 diverse candidate tickers across sub-sectors and market caps
3. Call get_stock_data for each candidate to check real current metrics
4. Narrow to the top 5-6 candidates with the best combination of:
   - Sector/style fit for the query
   - Revenue growth (> 5% YoY minimum)
   - Not obviously overvalued (forward P/E reasonable for the sector)
   - Not in freefall (not within 20% of 52-week low)
   - Analyst consensus leaning positive

Return ONLY a raw JSON (no markdown, no code blocks, no explanation outside JSON):
{
  "candidates": [
    {"ticker": "TICKER", "notes": "brief reason this passed initial screening"}
  ]
}

Do NOT assign Strong/Good/Partial Match labels yet. A quant agent and news agent will run on these candidates before final scoring."""


# Phase 3: score finalists with full quant + news context
SYSTEM_SCORE = """You are a stock recommendation agent. You have been given deep quant analysis and news sentiment for each candidate stock.

Use this comprehensive analysis — NOT raw metrics — to assign final match labels and write precise recommendations.

MATCH LABEL DEFINITIONS:

"Strong Match" — only use this if ALL of the following hold based on the deep analysis:
  • Revenue growth > 10% YoY AND EPS growing YoY (not flat, not declining)
  • Valuation is reasonable: PEG < 2.5x, or forward P/E clearly justified by growth rate (e.g. 30x P/E with 30%+ growth is fine; 80x P/E with 10% growth is not)
  • No major negative news catalysts (missed earnings, leadership departure, serious competitive threat, regulatory risk)
  • Not in active downtrend: NOT within 20% of its 52-week LOW
  • 52-week return < 50%, OR if higher, still meaningfully below 52-week high (>15% discount to high)
  • Analyst consensus is majority Buy or Strong Buy
  • For queries with "add to position", "buy more", or "strong hold" intent: the quant data would support an Add or Strong Hold signal — a great business that has ALREADY fully repriced is a Hold, not a Strong Match for adding more

"Good Match" — good business but one meaningful caveat (rich valuation, recent large price run, mixed news, or EPS not yet positive)

"Partial Match" — fits sector/style but fails on fundamentals, valuation, or price action

Be strict. If quant analysis reveals concerns (slowing growth, margin compression, questionable metrics) or news reveals risks (AI competitive threat, regulatory action, key customer loss), downgrade accordingly. Do NOT assign Strong Match because analyst consensus is bullish alone — valuation and price action matter equally.

Return ONLY a raw JSON (no markdown, no code blocks):
{
  "recommendations": [
    {
      "ticker": "TICKER",
      "company": "Full Company Name",
      "match": "Strong Match",
      "rationale": "2-3 sentences based on the deep quant + news analysis — cite specific numbers",
      "highlight": "single most compelling data point (e.g. '47% revenue growth with expanding margins')"
    }
  ]
}

match values must be exactly one of: "Strong Match", "Good Match", "Partial Match"
Return up to 10 results. Only include stocks that genuinely qualify."""


def _parse_json_from_text(text: str) -> dict | None:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    try:
        return json.loads(text)
    except Exception:
        return None


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

    # --- PHASE 1: Screen candidates with raw Finnhub metrics ---
    messages = [
        {
            "role": "user",
            "content": f"""Screen stocks for: "{query}"

Investor profile:
- Risk tolerance: {user_context.get("risk", "moderate")}
- Time horizon: {user_context.get("horizon", "medium-term")}
- Investment goal: {user_context.get("goal", "growth")}

Call get_stock_data for 15-18 candidates, then return the top 5-6 as a JSON candidates list.""",
        }
    ]

    # Track company names as Phase 1 fetches Finnhub data
    company_names: dict[str, str] = {}
    candidates: list[str] = []

    for _ in range(15):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_SCREEN,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            fetch_tasks = []
            for block in response.content:
                if block.type == "tool_use" and block.name == "get_stock_data":
                    ticker = block.input.get("ticker", "").upper().strip()
                    fetch_tasks.append((block.id, ticker))

            async def fetch(tool_use_id: str, t: str) -> dict:
                try:
                    data = await loop.run_in_executor(_executor, get_all_stock_data, t)
                    if data.get("company_name") and data["company_name"] != t:
                        company_names[t] = data["company_name"]
                    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(data)}
                except Exception as e:
                    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps({"error": str(e)})}

            tool_results = await asyncio.gather(*[fetch(tid, t) for tid, t in fetch_tasks])
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": list(tool_results)})

        elif response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    parsed = _parse_json_from_text(block.text)
                    if parsed:
                        candidates = [c["ticker"].upper() for c in parsed.get("candidates", [])]
            break
        else:
            break

    if not candidates:
        return []

    # --- PHASE 2: Run quant + news in parallel for each candidate ---
    async def analyze_one(ticker: str) -> tuple[str, str, str, str]:
        company_name = company_names.get(ticker, ticker)
        try:
            (quant_analysis, resolved_name, _), news_analysis = await asyncio.gather(
                run_quant_agent(ticker, client),
                run_news_agent(ticker, company_name, client),
            )
            # Use the name quant resolved (more reliable than Finnhub summary)
            final_name = resolved_name if resolved_name != ticker else company_name
            return ticker, final_name, quant_analysis, news_analysis
        except Exception as e:
            return ticker, company_name, f"Analysis unavailable: {e}", "News unavailable"

    analyses = await asyncio.gather(*[analyze_one(t) for t in candidates])

    # --- PHASE 3: Final scoring with full quant + news context ---
    analysis_sections = []
    for ticker, company, quant, news in analyses:
        analysis_sections.append(
            f"=== {ticker} — {company} ===\n\nQUANT ANALYSIS:\n{quant}\n\nNEWS SENTIMENT:\n{news}"
        )

    sections_text = "\n\n".join(analysis_sections)
    final_response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_SCORE,
        messages=[
            {
                "role": "user",
                "content": (
                    f'User query: "{query}"\n\n'
                    f"Investor profile:\n"
                    f"- Risk: {user_context.get('risk', 'moderate')}\n"
                    f"- Horizon: {user_context.get('horizon', 'medium-term')}\n"
                    f"- Goal: {user_context.get('goal', 'growth')}\n\n"
                    f"Deep analysis for each candidate:\n\n"
                    f"{sections_text}\n\n"
                    f"Assign final match labels and return recommendations."
                ),
            }
        ],
    )

    for block in final_response.content:
        if hasattr(block, "text"):
            parsed = _parse_json_from_text(block.text)
            if parsed:
                return parsed.get("recommendations", [])

    return []
