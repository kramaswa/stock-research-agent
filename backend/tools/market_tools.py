import os
import json
import httpx
from datetime import datetime, timedelta
from cachetools import TTLCache

_data_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)


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
    if ticker in _data_cache:
        return _data_cache[ticker]

    quote = _get("/quote", {"symbol": ticker})
    profile = _get("/stock/profile2", {"symbol": ticker})
    metrics_resp = _get("/stock/metric", {"symbol": ticker, "metric": "all"})
    rec = _get("/stock/recommendation", {"symbol": ticker})
    price_target_resp = _get("/stock/price-target", {"symbol": ticker})
    eps_estimate_resp = _get("/stock/eps-estimate", {"symbol": ticker, "freq": "annual"})

    m = metrics_resp.get("metric", {}) if isinstance(metrics_resp, dict) else {}

    current = quote.get("c")
    prev_close = quote.get("pc")
    change_pct_1d = round(((current - prev_close) / prev_close) * 100, 2) if current and prev_close else None

    # Last 4 analyst recommendation periods to show trend (not just snapshot)
    recent_recs = []
    if isinstance(rec, list):
        for r in rec[:4]:
            recent_recs.append({
                "period": r.get("period"),
                "strongBuy": r.get("strongBuy"),
                "buy": r.get("buy"),
                "hold": r.get("hold"),
                "sell": r.get("sell"),
                "strongSell": r.get("strongSell"),
            })

    # Forward EPS estimates (next 2 annual periods)
    eps_estimates = []
    if isinstance(eps_estimate_resp, dict) and eps_estimate_resp.get("data"):
        for e in eps_estimate_resp["data"][:2]:
            eps_estimates.append({
                "period": e.get("period"),
                "eps_avg": e.get("epsAvg"),
                "eps_high": e.get("epsHigh"),
                "eps_low": e.get("epsLow"),
                "num_analysts": e.get("numberAnalysts"),
            })

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

    result = {
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
        "long_term_debt_to_equity": m.get("longTermDebt/totalEquityAnnual"),
        "current_ratio": m.get("currentRatioAnnual"),
        "quick_ratio": m.get("quickRatioAnnual"),
        "interest_coverage": m.get("netInterestCoverageAnnual"),
        "dividend_yield": m.get("dividendYieldIndicatedAnnual"),
        # Free cash flow (real earnings power)
        "fcf_per_share_ttm": m.get("freeCashFlowPerShareTTM"),
        "ev_to_fcf_ttm": m.get("currentEv/freeCashFlowTTM"),
        # Capital efficiency
        "roic_ttm": m.get("roicTTM"),
        "roic_5y_avg": m.get("roic5Y"),
        "revenue_growth_5y": m.get("revenueGrowth5Y"),
        "eps_growth_3y": m.get("epsGrowth3Y"),
        # Analyst consensus (last 4 periods — shows trend)
        "recent_recommendations": recent_recs,
        # Analyst price target
        "analyst_target_mean": price_target_resp.get("targetMean") if isinstance(price_target_resp, dict) else None,
        "analyst_target_high": price_target_resp.get("targetHigh") if isinstance(price_target_resp, dict) else None,
        "analyst_target_low": price_target_resp.get("targetLow") if isinstance(price_target_resp, dict) else None,
        # Forward EPS estimates
        "eps_estimates": eps_estimates,
        "chart_data": chart_data,
    }
    _data_cache[ticker] = result
    return result


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
