import httpx
import re
from datetime import datetime, timedelta
from cachetools import TTLCache

_edgar_cache: TTLCache = TTLCache(maxsize=50, ttl=3600)

_HEADERS = {
    "User-Agent": "StockResearchAgent research@stockagent.app",
    "Accept-Encoding": "gzip, deflate",
}


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    for entity, char in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")]:
        text = text.replace(entity, char)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _get_cik(ticker: str) -> str | None:
    key = f"cik_{ticker.upper()}"
    if key in _edgar_cache:
        return _edgar_cache[key]
    try:
        r = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        for entry in r.json().values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                _edgar_cache[key] = cik
                return cik
    except Exception:
        pass
    _edgar_cache[key] = None
    return None


def get_recent_8k_text(ticker: str) -> str | None:
    """Fetch text from the most recent 8-K earnings press release via SEC EDGAR."""
    key = f"8k_{ticker.upper()}"
    if key in _edgar_cache:
        return _edgar_cache[key]
    result = _fetch_8k(ticker)
    _edgar_cache[key] = result
    return result


def _fetch_8k(ticker: str) -> str | None:
    try:
        cik = _get_cik(ticker)
        if not cik:
            return None

        cik_int = str(int(cik))
        cutoff = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")

        r = httpx.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        recent = r.json().get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        # Try 8-K first (US domestic filers), then 6-K (foreign private issuers)
        for target_form in ("8-K", "6-K"):
            for i, form in enumerate(forms):
                if form != target_form:
                    continue
                if i >= len(dates) or dates[i] < cutoff:
                    break  # Filings are newest-first; stop after cutoff

                accession = accessions[i]
                accession_nodash = accession.replace("-", "")

                # Try to find EX-99 (earnings press release) in the filing index
                doc_url = None
                try:
                    idx_url = (
                        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                        f"{accession_nodash}/{accession}-index.htm"
                    )
                    idx_r = httpx.get(idx_url, headers=_HEADERS, timeout=8)
                    for line in idx_r.text.split("\n"):
                        if "EX-99" in line.upper():
                            href = re.search(
                                r'href="(/Archives/edgar/data/[^"]+)"', line, re.IGNORECASE
                            )
                            if href:
                                doc_url = "https://www.sec.gov" + href.group(1)
                                break
                except Exception:
                    pass

                # Fall back to the primary document
                if not doc_url and i < len(primary_docs) and primary_docs[i]:
                    doc_url = (
                        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                        f"{accession_nodash}/{primary_docs[i]}"
                    )

                if doc_url:
                    try:
                        doc_r = httpx.get(doc_url, headers=_HEADERS, timeout=15)
                        text = _strip_html(doc_r.text)
                        if len(text) > 150:
                            if len(text) > 3500:
                                text = text[:3500] + "... [truncated]"
                            return f"[SEC {target_form} filed {dates[i]}]\n{text}"
                    except Exception:
                        pass

                break  # Only try the most recent filing of this form type

    except Exception:
        pass

    return None
