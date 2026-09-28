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
    """Fetch SPY trailing/forward P/E from Yahoo Finance using crumb-based auth.

    Yahoo Finance v10 quoteSummary requires a session cookie + crumb obtained from
    fc.yahoo.com / v1/test/getcrumb. The crumb endpoint returns 429 when called
    repeatedly from the same IP in a short window (dev machines), but works fine
    from the production server. Falls back to None on any failure.
    """
    if "SPY_PE" in _market_pe_cache:
        return _market_pe_cache["SPY_PE"]
    try:
        _headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(headers=_headers, timeout=10, follow_redirects=True) as session:
            session.get("https://fc.yahoo.com")
            crumb_r = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb")
            if crumb_r.status_code != 200:
                return None
            crumb = crumb_r.text.strip()
            r = session.get(
                "https://query1.finance.yahoo.com/v10/finance/quoteSummary/SPY",
                params={"modules": "summaryDetail", "crumb": crumb},
            )
            if r.status_code != 200:
                return None
            sd = r.json()["quoteSummary"]["result"][0]["summaryDetail"]
            # Prefer forwardPE (uses consensus estimates); fall back to trailingPE
            pe_raw = sd.get("forwardPE") or sd.get("trailingPE")
            if pe_raw and float(pe_raw) > 5:
                result = round(float(pe_raw), 1)
                _market_pe_cache["SPY_PE"] = result
                return result
    except Exception:
        pass
    return None
