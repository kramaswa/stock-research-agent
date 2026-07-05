import os
import json
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import anthropic

from agents.quant_agent import run_quant_agent
from agents.news_agent import run_news_agent
from agents.synthesis_agent import run_synthesis_agent
from agents.comparison_agent import run_comparison_agent, format_comparison_table
from agents.discovery_agent import run_discovery_agent
from agents.hold_check_agent import run_hold_check_agent
from tools.market_tools import get_all_stock_data
from tools.edgar_tools import get_recent_8k_text, get_recent_10q_mda, get_earnings_transcript
from tools.macro_tools import get_treasury_yield_10y

load_dotenv()

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Stock Research Agent API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResearchRequest(BaseModel):
    ticker: str


async def research_stream(ticker: str, risk: str, horizon: str, goal: str):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    ticker = ticker.upper().strip()
    user_context = {"risk": risk, "horizon": horizon, "goal": goal}

    def event(type: str, payload: dict):
        return {"data": json.dumps({"type": type, **payload})}

    try:
        yield event("status", {"message": f"Starting research for {ticker}...", "step": "init"})
        await asyncio.sleep(0)

        # Step 1: Fast raw data fetch to get company_name and validate ticker (cached)
        loop = asyncio.get_event_loop()
        raw_data = await loop.run_in_executor(None, get_all_stock_data, ticker)
        company_name = raw_data.get("company_name", ticker)
        raw_chart = raw_data.get("chart_data", [])

        if company_name == ticker and not raw_chart:
            yield event("error", {"message": f"'{ticker}' doesn't appear to be a valid stock ticker. Please check the symbol and try again (e.g. AAPL, NVDA, TSLA)."})
            return

        # Step 2: Quant + News + Comparison all in parallel — raw data is cached so quant won't re-hit Finnhub
        yield event("status", {"message": "Running quant, news & comparison in parallel...", "step": "quant"})
        await asyncio.sleep(0)

        (quant_result, news_analysis, (peer_data, peer_tickers)) = await asyncio.gather(
            run_quant_agent(ticker, client),
            run_news_agent(ticker, company_name, client),
            run_comparison_agent(ticker),
        )
        quant_analysis, quant_company, chart_data = quant_result
        if quant_company != ticker:
            company_name = quant_company

        yield event("agent_result", {"agent": "quant", "content": quant_analysis})
        if chart_data:
            yield event("chart_data", {"data": chart_data, "ticker": ticker})
        yield event("agent_result", {"agent": "news", "content": news_analysis})
        await asyncio.sleep(0)

        comparison_md = ""
        if peer_data:
            comparison_md = format_comparison_table(raw_data, peer_data)
            yield event("comparison_data", {"markdown": comparison_md, "peers": peer_tickers})
        await asyncio.sleep(0)

        # Step 3: Synthesis
        yield event("status", {"message": "Synthesizing final report...", "step": "synthesis"})
        await asyncio.sleep(0)

        report = await run_synthesis_agent(
            ticker, quant_analysis, news_analysis, client,
            comparison_table=comparison_md,
            user_context=user_context,
        )
        yield event("report", {"content": report, "ticker": ticker, "company": company_name})
        await asyncio.sleep(0)

        yield event("done", {"message": "Research complete."})

    except Exception as e:
        yield event("error", {"message": str(e)})


@app.get("/research/{ticker}")
@limiter.limit("10/hour")
async def research(
    request: Request,
    ticker: str,
    risk: str = "moderate",
    horizon: str = "medium-term",
    goal: str = "growth",
):
    if not ticker or not ticker.replace("-", "").isalpha():
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")
    return EventSourceResponse(research_stream(ticker, risk, horizon, goal))


async def hold_check_stream(ticker: str, purchase_price: float, thesis: str, risk: str, horizon: str, goal: str):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    ticker = ticker.upper().strip()
    user_context = {"risk": risk, "horizon": horizon, "goal": goal}

    def event(type: str, payload: dict):
        return {"data": json.dumps({"type": type, **payload})}

    try:
        yield event("status", {"message": f"Fetching current data for {ticker}...", "step": "quant"})
        await asyncio.sleep(0)

        # Fetch raw Finnhub data first (fast, cached) to get company_name and validate ticker
        loop = asyncio.get_event_loop()
        raw_data = await loop.run_in_executor(None, get_all_stock_data, ticker)
        company_name = raw_data.get("company_name", ticker)
        raw_chart = raw_data.get("chart_data", [])

        if company_name == ticker and not raw_chart:
            yield event("error", {"message": f"'{ticker}' doesn't appear to be a valid stock ticker. Please check the symbol and try again."})
            return

        # Run quant, news, peer comparison, and EDGAR 8-K fetch in parallel
        yield event("status", {"message": "Running quant analysis, news, and peer comparison in parallel...", "step": "news"})
        await asyncio.sleep(0)

        async def fetch_edgar():
            return await loop.run_in_executor(None, get_recent_8k_text, ticker)

        async def fetch_10q():
            return await loop.run_in_executor(None, get_recent_10q_mda, ticker)

        async def fetch_yield():
            return await loop.run_in_executor(None, get_treasury_yield_10y)

        async def fetch_transcript():
            return await loop.run_in_executor(None, get_earnings_transcript, ticker)

        (
            quant_result,
            news_analysis,
            (peer_data, peer_tickers),
            edgar_text,
            mda_text,
            treasury_yield,
            transcript_text,
        ) = await asyncio.gather(
            run_quant_agent(ticker, client),
            run_news_agent(ticker, company_name, client),
            run_comparison_agent(ticker),
            fetch_edgar(),
            fetch_10q(),
            fetch_yield(),
            fetch_transcript(),
        )
        quant_analysis, quant_company, chart_data = quant_result
        if quant_company != ticker:
            company_name = quant_company

        comparison_md = ""
        if peer_data:
            comparison_md = format_comparison_table(raw_data, peer_data)

        # Emit data sources so the UI can show what context was fed to Opus
        sources = ["Finnhub"]
        insider_count = len(raw_data.get("insider_transactions") or [])
        if insider_count:
            sources.append(f"{insider_count} insider transaction{'s' if insider_count != 1 else ''}")
        if treasury_yield is not None:
            sources.append(f"10Y yield ({treasury_yield}%)")
        for sec_text in (edgar_text, mda_text, transcript_text):
            if sec_text:
                bracket_end = sec_text.find("]")
                if bracket_end > 0:
                    label = sec_text[1:bracket_end]
                    parts = label.split(" filed ")
                    sources.append(f"{parts[0]} ({parts[1]})" if len(parts) == 2 else label)
        yield event("data_sources", {"sources": sources})

        yield event("status", {"message": "Analyzing your thesis...", "step": "analyze"})
        await asyncio.sleep(0)

        current_price = chart_data[-1]["price"] if chart_data else (raw_chart[-1]["price"] if raw_chart else 0.0)

        analysis = await run_hold_check_agent(
            ticker, purchase_price, quant_analysis, news_analysis, client,
            user_thesis=thesis,
            current_price=current_price,
            user_context=user_context,
            comparison_table=comparison_md,
            earnings_release=edgar_text or "",
            mda_text=mda_text or "",
            treasury_yield=treasury_yield,
            transcript=transcript_text or "",
        )

        yield event("hold_result", {
            "content": analysis,
            "ticker": ticker,
            "company": company_name,
            "current_price": current_price,
            "purchase_price": purchase_price,
        })
        yield event("done", {"message": "Analysis complete."})

    except Exception as e:
        yield event("error", {"message": str(e)})


@app.get("/holdcheck/{ticker}")
@limiter.limit("10/hour")
async def hold_check(
    request: Request,
    ticker: str,
    purchase_price: float = 0.0,
    thesis: str = "",
    risk: str = "moderate",
    horizon: str = "medium-term",
    goal: str = "growth",
):
    if not ticker or not ticker.replace("-", "").isalpha():
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")
    return EventSourceResponse(hold_check_stream(ticker, purchase_price, thesis, risk, horizon, goal))


@app.get("/discover")
@limiter.limit("10/hour")
async def discover(
    request: Request,
    query: str,
    risk: str = "moderate",
    horizon: str = "medium-term",
    goal: str = "growth",
):
    if not query or len(query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query too short")
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    user_context = {"risk": risk, "horizon": horizon, "goal": goal}
    recommendations = await run_discovery_agent(query.strip(), user_context, client)
    return {"recommendations": recommendations}


@app.get("/health")
async def health():
    return {"status": "ok"}
