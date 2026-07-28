import re
import json
import yfinance as yf
import anthropic
from cachetools import TTLCache

_adr_info_cache: TTLCache = TTLCache(maxsize=100, ttl=86400)   # 24h — home ticker/ratio rarely changes
_adr_price_cache: TTLCache = TTLCache(maxsize=100, ttl=900)    # 15min — live prices

# Confirmed home tickers and ADR ratios for well-known names
# adr_ratio = home exchange shares per 1 US ADR/share
_KNOWN_ADR_INFO: dict[str, dict] = {
    "TSM":  {"home_ticker": "2330.TW",  "adr_ratio": 5.0, "home_exchange": "TWSE"},
    "ASML": {"home_ticker": "ASML.AS",  "adr_ratio": 1.0, "home_exchange": "Euronext Amsterdam"},
}

# Confirmed home tickers WITHOUT a confirmed ratio (too new / ratio unverified)
# We'll show price comparison but can't compute exact premium/discount
_KNOWN_HOME_TICKER: dict[str, dict] = {
    "SKHY": {"home_ticker": "000660.KS", "home_exchange": "KRX"},
}


def get_adr_home_info(us_ticker: str, company_name: str, client: anthropic.Anthropic) -> dict | None:
    """
    Return home exchange info for a foreign-issuer US ticker.
    Keys: home_ticker, home_exchange, adr_ratio (may be None if unconfirmed).
    Returns None only if the home ticker itself is unknown.
    """
    key = us_ticker.upper()
    if key in _adr_info_cache:
        return _adr_info_cache[key]

    # Confirmed full info (ticker + ratio)
    if key in _KNOWN_ADR_INFO:
        result = dict(_KNOWN_ADR_INFO[key])
        _adr_info_cache[key] = result
        return result

    # Confirmed home ticker, ratio unverified — return partial
    if key in _KNOWN_HOME_TICKER:
        result = dict(_KNOWN_HOME_TICKER[key])
        result["adr_ratio"] = None
        _adr_info_cache[key] = result
        return result

    # Ask Haiku — separate home ticker (high confidence) from ratio (lower confidence)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": (
                    f"The US-listed stock {us_ticker} ({company_name}) is a foreign company's US ADR or depositary share.\n"
                    f"Provide:\n"
                    f"1. home_ticker: primary home exchange ticker in yfinance format "
                    f"(e.g. '000660.KS' for SK Hynix on KRX, '2330.TW' for TSMC, 'ASML.AS' for ASML)\n"
                    f"2. home_exchange: short exchange name (e.g. 'KRX', 'TWSE', 'Euronext Amsterdam')\n"
                    f"3. adr_ratio: home shares per 1 US ADR (e.g. TSM=5, ASML=1) — "
                    f"set to null if you are not certain from the official DR prospectus\n"
                    f"Reply ONLY in JSON: "
                    f'{{\"home_ticker\": \"...\", \"home_exchange\": \"...\", \"adr_ratio\": 1.0}}\n'
                    f"If you don't know the home ticker at all, reply: {{\"unknown\": true}}"
                ),
            }],
        )
        text = response.content[0].text.strip()
        data = _parse_json(text)
        if not data or data.get("unknown") or not data.get("home_ticker"):
            _adr_info_cache[key] = None
            return None
        result = {
            "home_ticker": data["home_ticker"],
            "home_exchange": data.get("home_exchange", ""),
            "adr_ratio": data.get("adr_ratio"),  # may be None
        }
        _adr_info_cache[key] = result
        return result
    except Exception:
        return None


def calculate_adr_premium(
    us_ticker: str,
    home_info: dict,
    us_price_hint: float | None = None,
) -> dict | None:
    """
    Compute ADR premium/discount vs the home exchange.

    us_price_hint: pass the Finnhub current price so we don't need yfinance
                   for the US side (handles new tickers not yet in yfinance).
    When home_info['adr_ratio'] is None the premium_pct field is omitted;
    the caller still gets home exchange price data for context.
    """
    key = us_ticker.upper()
    if key in _adr_price_cache:
        return _adr_price_cache[key]

    home_ticker = home_info["home_ticker"]
    adr_ratio = home_info.get("adr_ratio")  # may be None

    try:
        # US price — prefer Finnhub hint to avoid yfinance failures on new tickers
        us_price = us_price_hint
        if not us_price:
            us_info = yf.Ticker(us_ticker).info
            us_price = us_info.get("regularMarketPrice") or us_info.get("currentPrice")
        if not us_price:
            return None

        # Home exchange price via yfinance
        home_yf = yf.Ticker(home_ticker).info
        home_price = home_yf.get("regularMarketPrice") or home_yf.get("currentPrice")
        home_currency = home_yf.get("currency", "USD")
        if not home_price:
            return None

        # Convert home price to USD
        if home_currency == "USD":
            home_price_usd = home_price
        else:
            fx_rate = yf.Ticker(f"{home_currency}=X").info.get("regularMarketPrice")
            if not fx_rate:
                return None
            home_price_usd = home_price / fx_rate

        result: dict = {
            "us_ticker": us_ticker.upper(),
            "home_ticker": home_ticker,
            "home_exchange": home_info.get("home_exchange", ""),
            "us_price": round(us_price, 2),
            "home_price": round(home_price, 2),
            "home_currency": home_currency,
            "home_price_usd": round(home_price_usd, 4),
        }

        if adr_ratio is not None:
            adr_ratio = float(adr_ratio)
            home_per_adr_usd = home_price_usd * adr_ratio
            premium_pct = ((us_price - home_per_adr_usd) / home_per_adr_usd) * 100
            result["adr_ratio"] = adr_ratio
            result["home_per_adr_usd"] = round(home_per_adr_usd, 2)
            result["premium_pct"] = round(premium_pct, 1)
        else:
            result["adr_ratio"] = None
            result["home_per_adr_usd"] = None
            result["premium_pct"] = None

        _adr_price_cache[key] = result
        return result
    except Exception:
        return None


def _parse_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None
