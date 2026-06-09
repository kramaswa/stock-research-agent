import os
import json
import httpx
from datetime import datetime, timedelta


def _get(path: str, params: dict) -> dict | list:
    params["token"] = os.getenv("FINNHUB_API_KEY")
    try:
        r = httpx.get(f"https://finnhub.io/api/v1{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def get_all_stock_data(ticker: str) -> dict:
    """Fetch comprehensive stock data from Finnhub."""
    ticker = ticker.upper()

    quote = _get("/quote", {"symbol": ticker})
    profile = _get("/stock/profile2", {"symbol": ticker})
    metrics_resp = _get("/stock/metric", {"symbol": ticker, "metric": "all"})
    rec = _get("/stock/recommendation", {"symbol": ticker})

    m = metrics_resp.get("metric", {}) if isinstance(metrics_resp, dict) else {}

    current = quote.get("c")
    prev_close = quote.get("pc")
    change_pct_1d = round(((current - prev_close) / prev_close) * 100, 2) if current and prev_close else None

    recent_recs = []
    if isinstance(rec, list) and rec:
        r0 = rec[0]
        recent_recs = [{
            "period": r0.get("period"),
            "strongBuy": r0.get("strongBuy"),
            "buy": r0.get("buy"),
            "hold": r0.get("hold"),
            "sell": r0.get("sell"),
            "strongSell": r0.get("strongSell"),
        }]

    # Build approximate price history from return percentages
    chart_data = []
    if current:
        today = datetime.now()
        intervals = [
            ("52W ago", today - timedelta(weeks=52), m.get("52WeekPriceReturnDaily")),
            ("26W ago", today - timedelta(weeks=26), m.get("26WeekPriceReturnDaily")),
            ("13W ago", today - timedelta(weeks=13), m.get("13WeekPriceReturnDaily")),
            ("5D ago",  today - timedelta(days=5),   m.get("5DayPriceReturnDaily")),
            ("Today",   today,                        0.0),
        ]
        for label, date, ret in intervals:
            if ret is not None:
                approx_price = round(current / (1 + ret / 100), 2)
                chart_data.append({"label": label, "date": date.strftime("%Y-%m-%d"), "price": approx_price})
        # Override last point with exact current price
        if chart_data:
            chart_data[-1]["price"] = round(current, 2)

    return {
        "ticker": ticker,
        "company_name": profile.get("name", ticker),
        "sector": profile.get("finnhubIndustry"),
        "exchange": profile.get("exchange"),
        "market_cap_millions": profile.get("marketCapitalization"),
        "ipo_date": profile.get("ipo"),
        # Price
        "current_price": round(current, 2) if current else None,
        "change_today_pct": change_pct_1d,
        "day_high": quote.get("h"),
        "day_low": quote.get("l"),
        "prev_close": prev_close,
        # Performance
        "return_5d_pct": m.get("5DayPriceReturnDaily"),
        "return_13w_pct": m.get("13WeekPriceReturnDaily"),
        "return_26w_pct": m.get("26WeekPriceReturnDaily"),
        "return_52w_pct": m.get("52WeekPriceReturnDaily"),
        "return_ytd_pct": m.get("yearToDatePriceReturnDaily"),
        "fifty_two_week_high": m.get("52WeekHigh"),
        "fifty_two_week_low": m.get("52WeekLow"),
        "beta": m.get("beta"),
        "avg_volume_10d": m.get("10DayAverageTradingVolume"),
        # Valuation
        "pe_ttm": m.get("peTTM"),
        "pe_annual": m.get("peNormalizedAnnual"),
        "forward_pe": m.get("forwardPE"),
        "peg_ttm": m.get("pegTTM"),
        "price_to_book": m.get("pbAnnual"),
        "price_to_sales_ttm": m.get("psTTM"),
        "ev_ebitda_ttm": m.get("evEbitdaTTM"),
        # Growth
        "revenue_growth_ttm_yoy": m.get("revenueGrowthTTMYoy"),
        "revenue_growth_3y": m.get("revenueGrowth3Y"),
        "eps_ttm": m.get("epsTTM"),
        "eps_growth_ttm_yoy": m.get("epsGrowthTTMYoy"),
        "eps_growth_5y": m.get("epsGrowth5Y"),
        # Profitability
        "gross_margin_ttm": m.get("grossMarginTTM"),
        "operating_margin_ttm": m.get("operatingMarginTTM"),
        "net_margin_ttm": m.get("netProfitMarginTTM"),
        "roe_ttm": m.get("roeTTM"),
        "roa_ttm": m.get("roaTTM"),
        # Financial health
        "debt_to_equity": m.get("totalDebt/totalEquityAnnual"),
        "current_ratio": m.get("currentRatioAnnual"),
        "dividend_yield": m.get("dividendYieldIndicatedAnnual"),
        # Analyst consensus
        "recent_recommendations": recent_recs,
        "chart_data": chart_data,
    }


MARKET_TOOLS = [
    {
        "name": "get_all_stock_data",
        "description": (
            "Fetch comprehensive stock data from Finnhub for a given ticker. Returns: "
            "current price and daily change, 5d/13w/26w/52w/YTD price returns, 52-week range, beta, "
            "valuation (P/E TTM, forward P/E, PEG, P/B, P/S, EV/EBITDA), "
            "growth (revenue growth YoY and 3Y, EPS and EPS growth), "
            "profitability (gross/operating/net margins, ROE, ROA), "
            "financial health (debt/equity, current ratio, dividend yield), "
            "and analyst buy/hold/sell recommendations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, e.g. AAPL, NVDA, MU",
                }
            },
            "required": ["ticker"],
        },
    },
]


def execute_market_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_all_stock_data":
        try:
            result = get_all_stock_data(**tool_input)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})
    return json.dumps({"error": f"Unknown tool: {tool_name}"})
