import os
import json
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import anthropic

from agents.quant_agent import run_quant_agent
from agents.news_agent import run_news_agent
from agents.synthesis_agent import run_synthesis_agent
from agents.comparison_agent import run_comparison_agent, format_comparison_table
from agents.discovery_agent import run_discovery_agent
from agents.hold_check_agent import run_hold_check_agent
from tools.market_tools import get_all_stock_data

load_dotenv()

app = FastAPI(title="Stock Research Agent API")

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

        # Step 1: Quant agent
        yield event("status", {"message": "Running quantitative analysis...", "step": "quant"})
        await asyncio.sleep(0)

        quant_analysis, company_name, chart_data = await run_quant_agent(ticker, client)

        if company_name == ticker and not chart_data:
            yield event("error", {"message": f"'{ticker}' doesn't appear to be a valid stock ticker. Please check the symbol and try again (e.g. AAPL, NVDA, TSLA)."})
            return

        yield event("agent_result", {"agent": "quant", "content": quant_analysis})
        if chart_data:
            yield event("chart_data", {"data": chart_data, "ticker": ticker})
        await asyncio.sleep(0)

        # Step 2: News agent + Comparison agent run in parallel (fan-out)
        yield event("status", {"message": "Running news & competitor analysis in parallel...", "step": "news"})
        await asyncio.sleep(0)

        loop = asyncio.get_event_loop()
        (news_analysis, (peer_data, peer_tickers), target_stock_data) = await asyncio.gather(
            run_news_agent(ticker, company_name, client),
            run_comparison_agent(ticker),
            loop.run_in_executor(None, get_all_stock_data, ticker),
        )

        yield event("agent_result", {"agent": "news", "content": news_analysis})
        await asyncio.sleep(0)

        # Build comparison table using full target metrics (not just price)
        comparison_md = ""
        if peer_data:
            comparison_md = format_comparison_table(target_stock_data, peer_data)
            yield event("comparison_data", {
                "markdown": comparison_md,
                "peers": peer_tickers,
            })
        await asyncio.sleep(0)

        # Step 3: Synthesis agent — gets quant + news + comparison
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
async def research(
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

        quant_analysis, company_name, chart_data = await run_quant_agent(ticker, client)

        if company_name == ticker and not chart_data:
            yield event("error", {"message": f"'{ticker}' doesn't appear to be a valid stock ticker. Please check the symbol and try again."})
            return

        await asyncio.sleep(0)

        yield event("status", {"message": "Checking recent news...", "step": "news"})
        await asyncio.sleep(0)

        news_analysis = await run_news_agent(ticker, company_name, client)
        await asyncio.sleep(0)

        yield event("status", {"message": "Analyzing your thesis...", "step": "analyze"})
        await asyncio.sleep(0)

        current_price = chart_data[-1]["price"] if chart_data else 0.0

        analysis = await run_hold_check_agent(
            ticker, purchase_price, quant_analysis, news_analysis, client,
            user_thesis=thesis,
            current_price=current_price,
            user_context=user_context,
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
async def hold_check(
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
async def discover(
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
