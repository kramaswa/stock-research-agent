import asyncio
from concurrent.futures import ThreadPoolExecutor
from tools.market_tools import _get, get_all_stock_data

_executor = ThreadPoolExecutor(max_workers=4)


def _fetch_peer_tickers(ticker: str, max_peers: int = 3) -> list[str]:
    """Return top N peers excluding the target ticker itself."""
    result = _get("/stock/peers", {"symbol": ticker})
    if not isinstance(result, list):
        return []
    peers = [t for t in result if t != ticker]
    return peers[:max_peers]


async def _fetch_stock_data_async(ticker: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, get_all_stock_data, ticker)


async def run_comparison_agent(ticker: str) -> tuple[list[dict], list[str]]:
    """
    Fetch peer tickers and pull stock data for all of them in parallel.
    Returns (peer_data_list, peer_tickers).
    """
    peer_tickers = _fetch_peer_tickers(ticker)
    if not peer_tickers:
        return [], []

    results = await asyncio.gather(
        *[_fetch_stock_data_async(t) for t in peer_tickers],
        return_exceptions=True,
    )

    peer_data = []
    for ticker_sym, result in zip(peer_tickers, results):
        if isinstance(result, Exception):
            peer_data.append({"ticker": ticker_sym, "error": str(result)})
        else:
            peer_data.append(result)

    return peer_data, peer_tickers


def format_comparison_table(target: dict, peers: list[dict]) -> str:
    """Format a markdown comparison table from target + peer data dicts."""
    all_stocks = [target] + peers

    def fmt_pct(v):
        if v is None:
            return "—"
        return f"{v:+.1f}%"

    def fmt_x(v):
        if v is None:
            return "—"
        return f"{v:.1f}x"

    def fmt_price(v):
        if v is None:
            return "—"
        return f"${v:,.2f}"

    rows = []
    for s in all_stocks:
        name = (s.get("company_name") or s.get("ticker", ""))
        short_name = name[:22] + "…" if len(name) > 22 else name
        rows.append({
            "ticker": s.get("ticker", ""),
            "name": short_name,
            "price": fmt_price(s.get("current_price")),
            "52w": fmt_pct(s.get("return_52w_pct")),
            "pe_fwd": fmt_x(s.get("forward_pe")),
            "rev_growth": fmt_pct(s.get("revenue_growth_ttm_yoy")),
            "gross_margin": fmt_pct(s.get("gross_margin_ttm")),
            "roe": fmt_pct(s.get("roe_ttm")),
            "rec": (s.get("recent_recommendations") or [{}])[0].get("buy", "—"),
        })

    header = "| Ticker | Company | Price | 52W Return | Fwd P/E | Rev Growth | Gross Margin | ROE |"
    sep    = "|--------|---------|-------|-----------|---------|-----------|-------------|-----|"
    lines  = [header, sep]
    for r in rows:
        marker = " ⭐" if r["ticker"] == target.get("ticker") else ""
        lines.append(
            f"| **{r['ticker']}{marker}** | {r['name']} | {r['price']} | {r['52w']} | {r['pe_fwd']} | {r['rev_growth']} | {r['gross_margin']} | {r['roe']} |"
        )

    return "\n".join(lines)
