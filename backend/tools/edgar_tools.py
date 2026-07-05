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


def get_recent_10q_mda(ticker: str) -> str | None:
    """Fetch the MD&A section from the most recent 10-Q (US) or 20-F (foreign) via SEC EDGAR."""
    key = f"10q_{ticker.upper()}"
    if key in _edgar_cache:
        return _edgar_cache[key]
    result = _fetch_mda(ticker)
    _edgar_cache[key] = result
    return result


def _extract_mda(text: str, form_type: str) -> str:
    lower = text.lower()

    if form_type == "10-Q":
        search_markers = ["management’s discussion", "management's discussion"]
        fallback_marker = "item 2."
        end_markers = ["item 3", "quantitative and qualitative", "part ii"]
    else:  # 20-F: MD&A equivalent is Item 5
        search_markers = ["operating and financial review", "management’s discussion"]
        fallback_marker = "item 5."
        end_markers = ["item 6", "directors, senior management", "part ii"]

    # Find the occurrence followed by the most content — this skips TOC entries,
    # which have very little text before the next section marker
    best_idx = -1
    best_content_len = 0

    for marker in search_markers:
        search_from = 0
        while True:
            idx = lower.find(marker, search_from)
            if idx == -1:
                break
            content_end = len(text)
            for em in end_markers:
                ei = lower.find(em, idx + 300)
                if ei != -1 and ei < content_end:
                    content_end = ei
            content_len = content_end - idx
            if content_len > best_content_len:
                best_content_len = content_len
                best_idx = idx
            search_from = idx + 1

    if best_idx == -1:
        best_idx = lower.rfind(fallback_marker)
        if best_idx == -1:
            return ""
        content_end = len(text)
        for em in end_markers:
            ei = lower.find(em, best_idx + 300)
            if ei != -1 and ei < content_end:
                content_end = ei
        best_content_len = content_end - best_idx

    if best_content_len < 300:
        return ""

    section = text[best_idx: best_idx + min(best_content_len, 4500)].strip()
    if best_content_len > 4500:
        section += "... [truncated]"
    return section


def _fetch_mda(ticker: str) -> str | None:
    try:
        cik = _get_cik(ticker)
        if not cik:
            return None

        cik_int = str(int(cik))

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

        # Try 10-Q first (US quarterly), then 20-F (foreign annual — longer lookback)
        for target_form, days_back in (("10-Q", 120), ("20-F", 400)):
            cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            for i, form in enumerate(forms):
                if form != target_form:
                    continue
                if i >= len(dates) or dates[i] < cutoff:
                    break

                accession = accessions[i]
                accession_nodash = accession.replace("-", "")
                doc_name = primary_docs[i] if i < len(primary_docs) else None
                if not doc_name:
                    break

                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                    f"{accession_nodash}/{doc_name}"
                )
                try:
                    doc_r = httpx.get(doc_url, headers=_HEADERS, timeout=20)
                    full_text = _strip_html(doc_r.text)
                    mda = _extract_mda(full_text, target_form)
                    if mda and len(mda) > 300:
                        return f"[SEC {target_form} MD&A filed {dates[i]}]\n{mda}"
                except Exception:
                    pass
                break  # Only try the most recent of each form type

    except Exception:
        pass
    return None


def get_earnings_transcript(ticker: str) -> str | None:
    """Fetch earnings call transcript from SEC EDGAR 8-K/6-K EX-99 exhibits."""
    key = f"transcript_{ticker.upper()}"
    if key in _edgar_cache:
        return _edgar_cache[key]
    result = _fetch_transcript(ticker)
    _edgar_cache[key] = result
    return result


def _is_earnings_transcript(text: str) -> bool:
    lower = text.lower()
    markers = [
        "operator", "question-and-answer", "ladies and gentlemen",
        "your lines are now open", "earnings call", "conference call",
    ]
    return sum(1 for m in markers if m in lower) >= 2


def _extract_transcript_key_sections(text: str, max_chars: int = 4500) -> str:
    """Return the prepared remarks intro + Q&A, prioritising the unscripted section."""
    lower = text.lower()
    qa_markers = [
        "question-and-answer session", "questions and answers",
        "we will now begin the question", "we will now open",
        "open the floor to questions", "operator: our first question",
    ]
    qa_idx = -1
    for marker in qa_markers:
        idx = lower.find(marker)
        if idx != -1 and (qa_idx == -1 or idx < qa_idx):
            qa_idx = idx

    if qa_idx == -1:
        result = text[:max_chars]
        if len(text) > max_chars:
            result += "\n... [truncated]"
        return result

    intro_chars = min(2000, qa_idx)
    intro = text[:intro_chars]
    qa_chars = max_chars - intro_chars
    qa = text[qa_idx : qa_idx + qa_chars]
    sep = "\n\n[...prepared remarks continued — jumping to Q&A...]\n\n" if qa_idx > intro_chars else ""
    result = intro + sep + qa
    if (qa_idx + qa_chars) < len(text):
        result += "\n... [truncated]"
    return result


def _fetch_transcript(ticker: str) -> str | None:
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

        for target_form in ("8-K", "6-K"):
            checked = 0
            for i, form in enumerate(forms):
                if form != target_form:
                    continue
                if i >= len(dates) or dates[i] < cutoff:
                    break
                if checked >= 3:  # check up to 3 recent filings (transcript may be a standalone 8-K)
                    break
                checked += 1

                accession = accessions[i]
                accession_nodash = accession.replace("-", "")

                try:
                    idx_url = (
                        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                        f"{accession_nodash}/{accession}-index.htm"
                    )
                    idx_r = httpx.get(idx_url, headers=_HEADERS, timeout=8)
                except Exception:
                    continue

                # Collect all EX-99 exhibits; flag any explicitly labeled as transcript
                ex99_urls = []
                transcript_url = None
                for line in idx_r.text.split("\n"):
                    if "EX-99" not in line.upper():
                        continue
                    href = re.search(
                        r'href="(/Archives/edgar/data/[^"]+)"', line, re.IGNORECASE
                    )
                    if not href:
                        continue
                    url = "https://www.sec.gov" + href.group(1)
                    if "transcript" in line.lower():
                        transcript_url = url
                        break
                    ex99_urls.append(url)

                # No explicit label — sniff content of EX-99.2+ (skip [0] = press release)
                if not transcript_url:
                    for ex_url in ex99_urls[1:3]:
                        try:
                            doc_r = httpx.get(ex_url, headers=_HEADERS, timeout=12)
                            sniff = _strip_html(doc_r.text)
                            if _is_earnings_transcript(sniff):
                                transcript_url = ex_url
                                break
                        except Exception:
                            pass

                if transcript_url:
                    try:
                        doc_r = httpx.get(transcript_url, headers=_HEADERS, timeout=15)
                        text = _strip_html(doc_r.text)
                        if len(text) > 300 and _is_earnings_transcript(text):
                            extracted = _extract_transcript_key_sections(text)
                            return f"[SEC {target_form} Earnings Call Transcript filed {dates[i]}]\n{extracted}"
                    except Exception:
                        pass

    except Exception:
        pass
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
