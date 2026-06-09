import anthropic
import json
from tools.market_tools import MARKET_TOOLS, execute_market_tool

SYSTEM_PROMPT = """You are a quantitative stock analyst. Your job is to gather and analyze numerical data for a given stock.

Call get_all_stock_data once to retrieve all available data, then provide a structured analysis covering:
1. Price & momentum summary (current price, 6mo return, vs 52-week range)
2. Fundamental health (P/E vs sector norms, revenue growth, margins, debt load)
3. Analyst consensus (rating, price target range, upside/downside from current)
4. Key quantitative risks or red flags in the numbers

If certain data fields are null or missing, note it briefly and move on — do not halt or repeat the tool call.
Be factual and data-driven. Do not make a buy/sell recommendation — that is the synthesis agent's job.
Format numbers clearly (e.g., "$X billion", "X%")."""


async def run_quant_agent(ticker: str, client: anthropic.Anthropic) -> tuple[str, str, list]:
    """Run the quant agent. Returns (analysis_text, company_name, chart_data)."""
    messages = [
        {
            "role": "user",
            "content": f"Analyze the stock {ticker.upper()}. Call get_all_stock_data once to gather data, then provide your analysis.",
        }
    ]

    company_name = ticker  # fallback if tool never returns a name
    chart_data = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=MARKET_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text, company_name, chart_data
            return "Quant analysis unavailable.", company_name, chart_data, chart_data

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_market_tool(block.name, block.input)
                    # Extract company name while we have the raw result
                    try:
                        data = json.loads(result)
                        if data.get("company_name") and data["company_name"] != ticker:
                            company_name = data["company_name"]
                        if data.get("chart_data"):
                            chart_data = data["chart_data"]
                    except Exception:
                        pass
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "Quant analysis unavailable.", company_name, chart_data
