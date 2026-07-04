import httpx
from cachetools import TTLCache

_macro_cache: TTLCache = TTLCache(maxsize=10, ttl=86400)


def get_treasury_yield_10y() -> float | None:
    """Fetch current 10-year US Treasury yield from Yahoo Finance (^TNX). No API key needed."""
    if "DGS10" in _macro_cache:
        return _macro_cache["DGS10"]
    try:
        r = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX",
            params={"interval": "1d", "range": "5d"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; StockResearchAgent/1.0)"},
            timeout=8,
        )
        r.raise_for_status()
        price = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        result = round(float(price), 2)
        _macro_cache["DGS10"] = result
        return result
    except Exception:
        pass
    return None
