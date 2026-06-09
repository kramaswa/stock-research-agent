import os
import json
from datetime import datetime, timedelta
from newsapi import NewsApiClient


def get_stock_news(ticker: str, company_name: str = "", days_back: int = 7) -> dict:
    """Fetch recent news articles about a stock."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"error": "NEWS_API_KEY not configured"}

    client = NewsApiClient(api_key=api_key)
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    query = f"{ticker} stock"
    if company_name:
        query = f"{company_name} OR {ticker} stock"

    try:
        response = client.get_everything(
            q=query,
            from_param=from_date,
            language="en",
            sort_by="relevancy",
            page_size=10,
        )

        articles = []
        for a in response.get("articles", []):
            articles.append({
                "title": a.get("title"),
                "source": a.get("source", {}).get("name"),
                "published_at": a.get("publishedAt"),
                "description": a.get("description"),
                "url": a.get("url"),
            })

        return {
            "ticker": ticker.upper(),
            "query": query,
            "total_results": response.get("totalResults", 0),
            "articles": articles,
        }
    except Exception as e:
        return {"error": str(e)}


def get_market_sentiment_news(topic: str = "stock market") -> dict:
    """Fetch broad market sentiment / macro news."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"error": "NEWS_API_KEY not configured"}

    client = NewsApiClient(api_key=api_key)
    from_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    try:
        response = client.get_top_headlines(
            q=topic,
            language="en",
            category="business",
            page_size=5,
        )

        articles = []
        for a in response.get("articles", []):
            articles.append({
                "title": a.get("title"),
                "source": a.get("source", {}).get("name"),
                "published_at": a.get("publishedAt"),
                "description": a.get("description"),
            })

        return {
            "topic": topic,
            "articles": articles,
        }
    except Exception as e:
        return {"error": str(e)}


NEWS_TOOLS = [
    {
        "name": "get_stock_news",
        "description": "Fetch recent news articles about a specific stock. Returns titles, sources, descriptions, and dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"},
                "company_name": {"type": "string", "description": "Full company name to improve search, e.g. Apple"},
                "days_back": {"type": "integer", "description": "How many days of news to fetch (default 7)", "default": 7},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_market_sentiment_news",
        "description": "Fetch broad market or macro news headlines (interest rates, Fed, sector trends).",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to search, e.g. 'interest rates', 'tech stocks', 'S&P 500'", "default": "stock market"},
            },
            "required": [],
        },
    },
]


def execute_news_tool(tool_name: str, tool_input: dict) -> str:
    dispatch = {
        "get_stock_news": get_stock_news,
        "get_market_sentiment_news": get_market_sentiment_news,
    }
    fn = dispatch.get(tool_name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = fn(**tool_input)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
