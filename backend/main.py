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

load_dotenv()

app = FastAPI(title="Stock Research Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
        yield event("agent_result", {"agent": "quant", "content": quant_analysis})
        if chart_data:
            yield event("chart_data", {"data": chart_data, "ticker": ticker})
        await asyncio.sleep(0)

        # Step 2: News agent + Comparison agent run in parallel (fan-out)
        yield event("status", {"message": "Running news & competitor analysis in parallel...", "step": "news"})
        await asyncio.sleep(0)

        (news_analysis, (peer_data, peer_tickers)) = await asyncio.gather(
            run_news_agent(ticker, company_name, client),
            run_comparison_agent(ticker),
        )

        yield event("agent_result", {"agent": "news", "content": news_analysis})
        await asyncio.sleep(0)

        # Build comparison table and send to frontend
        comparison_md = ""
        if peer_data:
            # We need the target stock's own data for the table header row
            target_data = {"ticker": ticker, "company_name": company_name}
            # Pull key metrics from quant_analysis context — use chart_data's price for now
            if chart_data:
                target_data["current_price"] = chart_data[-1]["price"] if chart_data else None
            comparison_md = format_comparison_table(target_data, peer_data)
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


@app.get("/health")
async def health():
    return {"status": "ok"}
