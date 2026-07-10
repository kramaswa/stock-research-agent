import anthropic
import json
from cachetools import TTLCache
from tools.news_tools import NEWS_TOOLS, execute_news_tool

# Cache news results for 1 hour
_cache: TTLCache = TTLCache(maxsize=50, ttl=3600)

SYSTEM_PROMPT = """You are a financial news and sentiment analyst. Your job is to assess the qualitative picture for a stock.

Use the available tools to fetch:
- Recent news about the specific stock/company
- Relevant macro or market-wide news that could affect this stock

After gathering news, provide a structured analysis covering:
1. Key recent headlines and their significance
2. Overall sentiment (positive / neutral / negative) with reasoning
3. Any major catalysts, risks, or events (earnings, lawsuits, product launches, leadership changes)
4. Macro factors that could impact this stock (rates, sector trends, regulation)

Be concise and specific. Cite article titles where relevant. Do not make a buy/sell recommendation."""


async def run_news_agent(ticker: str, company_name: str, client: anthropic.Anthropic) -> str:
    """Run the news agent for a given ticker. Returns sentiment analysis text."""
    ticker = ticker.upper()
    if ticker in _cache:
        return _cache[ticker]

    messages = [
        {
            "role": "user",
            "content": f"Analyze news and sentiment for {ticker.upper()} ({company_name}). Fetch recent stock-specific news and relevant macro news, then provide your analysis.",
        }
    ]

    while True:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=NEWS_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    _cache[ticker] = block.text
                    return block.text
            return "News analysis unavailable."

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_news_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "News analysis unavailable."
