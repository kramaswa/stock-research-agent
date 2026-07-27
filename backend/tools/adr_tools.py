import re
import json
import yfinance as yf
import anthropic
from cachetools import TTLCache

_adr_info_cache: TTLCache = TTLCache(maxsize=100, ttl=86400)   # 24h — home ticker/ratio rarely changes
_adr_price_cache: TTLCache = TTLCache(maxsize=100, ttl=900)    # 15min — live prices


def get_adr_home_info(us_ticker: str, company_name: str, client: anthropic.Anthropic) -> dict | None:
    """
    Ask Haiku for the home exchange ticker and ADR ratio.
    Returns dict with home_ticker, adr_ratio, home_exchange — or None if unknown.
    """
    key = us_ticker.upper()
    if key in _adr_info_cache:
        return _adr_info_cache[key]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": (
                    f"The US-listed stock {us_ticker} ({company_name}) is a foreign company with a US ADR or depositary share listing.\n"
                    f"Provide:\n"
                    f"1. home_ticker: primary home exchange ticker in yfinance format "
                    f"(e.g. '000660.KS' for SK Hynix on KRX, '2330.TW' for TSMC on TWSE, 'ASML.AS' for ASML on Euronext)\n"
                    f"2. adr_ratio: how many home exchange shares does 1 US ADR represent? "
                    f"(e.g. 1 TSM ADR = 5 shares of 2330.TW → adr_ratio=5; 1 NVO ADR = 1 NVO.CO share → adr_ratio=1)\n"
                    f"3. home_exchange: short exchange name (e.g. 'KRX', 'TWSE', 'Euronext Amsterdam', 'TSX')\n"
                    f"Reply ONLY in JSON: {{\"home_ticker\": \"...\", \"adr_ratio\": 1.0, \"home_exchange\": \"...\"}}\n"
                    f"If you are not confident, reply: {{\"unknown\": true}}"
                ),
            }],
        )
        text = response.content[0].text.strip()
        data = _parse_json(text)
        if not data or data.get("unknown"):
            return None
        if not data.get("home_ticker") or not data.get("adr_ratio"):
            return None
        _adr_info_cache[key] = data
        return data
    except Exception:
        return None


def calculate_adr_premium(us_ticker: str, home_info: dict) -> dict | None:
    """
    Fetch live prices for the US ADR and the home-exchange stock via yfinance,
    convert to a common currency, and compute the premium/discount.
    """
    key = us_ticker.upper()
    if key in _adr_price_cache:
        return _adr_price_cache[key]

    home_ticker = home_info["home_ticker"]
    adr_ratio = float(home_info["adr_ratio"])

    try:
        us_info = yf.Ticker(us_ticker).info
        home_info_data = yf.Ticker(home_ticker).info

        us_price = us_info.get("regularMarketPrice") or us_info.get("currentPrice")
        home_price = home_info_data.get("regularMarketPrice") or home_info_data.get("currentPrice")
        home_currency = home_info_data.get("currency", "USD")

        if not us_price or not home_price:
            return None

        # Convert home price to USD
        if home_currency == "USD":
            home_price_usd = home_price
        else:
            # "{CURRENCY}=X" gives units of that currency per 1 USD
            fx_rate = yf.Ticker(f"{home_currency}=X").info.get("regularMarketPrice")
            if not fx_rate:
                return None
            home_price_usd = home_price / fx_rate

        # How much should 1 US ADR cost if it traded at parity with the home exchange?
        # adr_ratio = home shares per 1 ADR, so: fair_adr_price = home_price_usd * adr_ratio
        home_per_adr_usd = home_price_usd * adr_ratio
        premium_pct = ((us_price - home_per_adr_usd) / home_per_adr_usd) * 100

        result = {
            "us_ticker": us_ticker.upper(),
            "home_ticker": home_ticker,
            "home_exchange": home_info.get("home_exchange", ""),
            "adr_ratio": adr_ratio,
            "us_price": round(us_price, 2),
            "home_price": round(home_price, 2),
            "home_currency": home_currency,
            "home_price_usd": round(home_price_usd, 4),
            "home_per_adr_usd": round(home_per_adr_usd, 2),
            "premium_pct": round(premium_pct, 1),
        }
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
