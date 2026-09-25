import httpx
from cachetools import TTLCache

_macro_cache: TTLCache = TTLCache(maxsize=10, ttl=86400)
_market_pe_cache: TTLCache = TTLCache(maxsize=5, ttl=3600)


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


def get_sp500_fwd_pe() -> float | None:
    """Fetch SPY forward P/E from Yahoo Finance — captures current S&P valuation for baseline return calc."""
    if "SPY_PE" in _market_pe_cache:
        return _market_pe_cache["SPY_PE"]
    try:
        r = httpx.get(
            "https://query1.finance.yahoo.com/v10/finance/quoteSummary/SPY",
            params={"modules": "defaultKeyStatistics"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; StockResearchAgent/1.0)"},
            timeout=8,
        )
        r.raise_for_status()
        stats = r.json()["quoteSummary"]["result"][0]["defaultKeyStatistics"]
        pe_field = stats.get("forwardPE", {})
        raw = pe_field.get("raw") if isinstance(pe_field, dict) else pe_field
        if raw and float(raw) > 5:
            result = round(float(raw), 1)
            _market_pe_cache["SPY_PE"] = result
            return result
    except Exception:
        pass
    return None
