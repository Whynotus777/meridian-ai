#!/usr/bin/env python3
"""Download a recent SEC 10-K filing and log it to Apex state.

Usage:
  python tests/download_test_docs.py MSFT
  python tests/download_test_docs.py "Microsoft Corporation" --sector Technology
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz
import requests
from bs4 import BeautifulSoup


EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_HEADERS = {
    "User-Agent": "MeridianAI/1.0 (research testing; contact: support@meridian.local)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "efts.sec.gov",
}
SEC_DOC_HEADERS = {
    "User-Agent": "MeridianAI/1.0 (research testing; contact: support@meridian.local)",
    "Accept-Encoding": "gzip, deflate",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DOCS_DIR = PROJECT_ROOT / "test_documents"
APEX_PATH = Path("~/Projects/apex").expanduser()
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _safe_name(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", text.strip())
    return cleaned.strip("_") or "document"


def _sec_get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.get(url, params=params, headers=SEC_HEADERS, timeout=45)
    response.raise_for_status()
    return response.json()


def _resolve_cik(query: str) -> Optional[str]:
    q = query.strip()
    if not q:
        return None
    try:
        payload = requests.get(COMPANY_TICKERS_URL, headers=SEC_DOC_HEADERS, timeout=45).json()
    except Exception:
        return None
    entries = payload.values() if isinstance(payload, dict) else []

    ticker_mode = bool(re.fullmatch(r"[A-Za-z]{1,5}", q))
    q_lower = q.lower()
    for item in entries:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).upper()
        title = str(item.get("title", ""))
        cik_num = item.get("cik_str")
        if cik_num is None:
            continue
        if ticker_mode and ticker == q.upper():
            return f"{int(cik_num):010d}"
        if (not ticker_mode) and q_lower in title.lower():
            return f"{int(cik_num):010d}"
    return None


def _extract_hits(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits_block = payload.get("hits", {})
    if isinstance(hits_block, dict):
        hits = hits_block.get("hits", [])
    elif isinstance(hits_block, list):
        hits = hits_block
    else:
        hits = []
    normalized = []
    for item in hits:
        if isinstance(item, dict):
            source = item.get("_source", {})
            if isinstance(source, dict):
                merged = dict(source)
                if "_id" in item:
                    merged["_id"] = item["_id"]
                normalized.append(merged)
            else:
                normalized.append(item)
    return normalized


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _pick_field(record: Dict[str, Any], *names: str) -> Optional[Any]:
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return None


def _build_filing_url(record: Dict[str, Any]) -> Optional[str]:
    direct = _pick_field(
        record,
        "linkToFilingDetails",
        "linkToHtml",
        "linkToTxt",
        "linkToFiling",
        "filing_url",
        "url",
    )
    if isinstance(direct, str) and direct:
        if direct.startswith("http"):
            return direct
        if direct.startswith("/"):
            return f"https://www.sec.gov{direct}"
        return f"https://www.sec.gov/{direct}"

    cik = _pick_field(record, "cik", "cikNumber")
    ciks = _as_list(_pick_field(record, "ciks"))
    if cik is None and ciks:
        cik = ciks[0]
    accession = _pick_field(record, "accessionNo", "accessionNumber", "adsh")
    primary_doc = _pick_field(record, "primaryDoc", "primaryDocument", "documentFormatFiles")
    if isinstance(primary_doc, list) and primary_doc:
        primary_doc = _pick_field(primary_doc[0], "documentUrl", "document", "sequence")
    if not (cik and accession):
        return None
    cik_num = str(int(str(cik)))
    accession = str(accession)
    acc_no_dash = accession.replace("-", "")
    if isinstance(primary_doc, str) and primary_doc:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dash}/{primary_doc}"
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dash}/{accession}.txt"


def _normalize_10k_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    forms = []
    forms.extend(_as_list(_pick_field(record, "root_forms", "rootForms")))
    forms.append(_pick_field(record, "formType", "form", "file_type"))
    form_text = " ".join(str(x) for x in forms if x).upper()
    form = str(_pick_field(record, "formType", "form", "file_type") or "").upper()
    if not form:
        form = form_text
    if "10-K" not in form:
        return None

    names = _as_list(_pick_field(record, "display_names", "companyName", "entityName", "company"))
    company = names[0] if names else "Unknown Company"
    cik = _pick_field(record, "cik", "cikNumber")
    ciks = _as_list(_pick_field(record, "ciks"))
    if cik is None and ciks:
        cik = ciks[0]
    filing_date = _pick_field(record, "filedAt", "filingDate", "periodOfReport", "file_date")
    accession = _pick_field(record, "accessionNo", "accessionNumber", "adsh")
    doc_from_id = None
    source_id = _pick_field(record, "_id", "id")
    if isinstance(source_id, str) and ":" in source_id:
        adsh, filename = source_id.split(":", 1)
        accession = accession or adsh
        if cik is not None:
            cik_num = str(int(str(cik)))
            doc_from_id = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_num}/{adsh.replace('-', '')}/{filename}"
            )
    source_url = doc_from_id or _build_filing_url(record)
    if not source_url:
        return None

    return {
        "company": str(company),
        "cik": str(cik) if cik is not None else "unknown",
        "form_type": form,
        "filing_date": str(filing_date) if filing_date else "unknown",
        "accession": str(accession) if accession else "unknown",
        "source_url": source_url,
        "record": record,
    }


def search_latest_10k(query: str) -> Dict[str, Any]:
    cik = _resolve_cik(query)
    params = {
        "q": f"{cik} 10-K" if cik else query,
        "from": "0",
        "size": "200",
    }
    payload = _sec_get_json(EFTS_SEARCH_URL, params=params)
    candidates = []
    for hit in _extract_hits(payload):
        normalized = _normalize_10k_record(hit)
        if normalized:
            candidates.append(normalized)
    q = query.strip()
    if cik:
        cik_int = str(int(cik))
        cik_filtered = [
            c for c in candidates
            if c.get("cik") and str(int(str(c.get("cik")))) == cik_int
        ]
        if cik_filtered:
            candidates = cik_filtered
    elif q and re.fullmatch(r"[A-Za-z]{1,5}", q):
        ticker = q.upper()
        ticker_filtered = [
            c for c in candidates
            if f"({ticker})" in c.get("company", "").upper()
        ]
        if ticker_filtered:
            candidates = ticker_filtered
    elif q:
        q_lower = q.lower()
        name_filtered = [
            c for c in candidates
            if q_lower in c.get("company", "").lower()
        ]
        if name_filtered:
            candidates = name_filtered
    if not candidates:
        raise RuntimeError(f"No 10-K filings found via EFTS for query: {query}")
    candidates.sort(key=lambda x: x["filing_date"], reverse=True)
    return candidates[0]


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    compact = "\n".join(line for line in lines if line)
    return compact


def _build_filing_index_url(cik: str, accession: str) -> Optional[str]:
    try:
        cik_num = str(int(str(cik)))
    except Exception:
        return None
    accession = str(accession)
    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_num}/{accession.replace('-', '')}/{accession}-index.html"
    )


def _to_absolute_sec_url(href: str) -> str:
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://www.sec.gov{href}"
    return f"https://www.sec.gov/{href.lstrip('./')}"


def _normalize_sec_doc_url(url: str) -> str:
    """Resolve SEC inline viewer URLs (ix?doc=...) to direct Archives paths."""
    if "sec.gov/ix?doc=" not in url:
        return url
    doc_part = url.split("ix?doc=", 1)[1]
    if doc_part.startswith("/"):
        return f"https://www.sec.gov{doc_part}"
    return f"https://www.sec.gov/{doc_part.lstrip('./')}"


def _resolve_primary_doc_from_documents_table(cik: str, accession: str) -> Optional[str]:
    """Parse EDGAR filing index page and select the primary 10-K document URL."""
    filing_index_url = _build_filing_index_url(cik, accession)
    if not filing_index_url:
        return None
    try:
        response = requests.get(filing_index_url, headers=SEC_DOC_HEADERS, timeout=45)
        response.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    best_candidates: List[str] = []
    fallback_candidates: List[str] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            row_text = " ".join(c.get_text(" ", strip=True) for c in cells).upper()
            link = row.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            lhref = href.lower()
            if "index" in lhref or "exhibit" in row_text or "ex-" in row_text:
                continue
            if not any(lhref.endswith(ext) for ext in (".htm", ".html", ".pdf", ".txt")):
                continue

            abs_url = _normalize_sec_doc_url(_to_absolute_sec_url(href))
            if "10-K" in row_text and "10-K/A" not in row_text:
                best_candidates.append(abs_url)
            else:
                fallback_candidates.append(abs_url)

    if best_candidates:
        return best_candidates[0]
    if fallback_candidates:
        return fallback_candidates[0]
    return None


def _resolve_primary_doc_url(cik: str, accession: str, fallback_url: str) -> str:
    """Resolve best primary filing document URL.

    Priority:
    1) Filing index Documents table (authoritative)
    2) accession index.json fallback heuristic
    3) input fallback_url
    """
    resolved_from_table = _resolve_primary_doc_from_documents_table(cik, accession)
    if resolved_from_table:
        return resolved_from_table

    try:
        cik_num = str(int(str(cik)))
    except Exception:
        return fallback_url
    acc_no_dash = str(accession).replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dash}/index.json"
    try:
        response = requests.get(index_url, headers=SEC_DOC_HEADERS, timeout=45)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return fallback_url

    items = payload.get("directory", {}).get("item", [])
    if not isinstance(items, list) or not items:
        return fallback_url

    preferred = []
    fallback = []
    for item in items:
        name = str(item.get("name", ""))
        lname = name.lower()
        if not name or lname == "index.json":
            continue
        if "index" in lname or "headers" in lname:
            continue
        if not any(lname.endswith(ext) for ext in (".htm", ".html", ".txt", ".pdf")):
            continue
        if any(x in lname for x in ("ex", "exhibit", "cal", "def", "lab", "pre", "_xbrl")):
            fallback.append(name)
            continue
        if any(x in lname for x in ("10k", "annual", "form10", "10-k")):
            preferred.append(name)
        else:
            fallback.append(name)

    for name in preferred + fallback:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dash}/{name}"
    return _normalize_sec_doc_url(fallback_url)


def _text_to_pdf(text: str, output_pdf_path: Path):
    """Render text into a multi-page PDF to avoid blank single-page overflows."""
    doc = fitz.open()
    page_width = 612
    page_height = 792
    margin = 48
    font_size = 9
    line_height = 12
    wrap_width = 105
    max_lines = int((page_height - 2 * margin) / line_height)

    wrapped_lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            wrapped_lines.append("")
            continue
        wrapped = textwrap.wrap(
            line,
            width=wrap_width,
            replace_whitespace=False,
            drop_whitespace=False,
        )
        wrapped_lines.extend(wrapped or [""])

    if not wrapped_lines:
        wrapped_lines = ["No text extracted from source document."]

    idx = 0
    while idx < len(wrapped_lines):
        page = doc.new_page(width=page_width, height=page_height)
        y = margin
        for _ in range(max_lines):
            if idx >= len(wrapped_lines):
                break
            page.insert_text((margin, y), wrapped_lines[idx], fontsize=font_size, fontname="helv")
            y += line_height
            idx += 1

    doc.save(str(output_pdf_path))
    doc.close()


def download_filing_as_pdf(filing: Dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_name(f"{filing['company']}_{filing['filing_date']}_10k")
    source_url = _resolve_primary_doc_url(
        cik=filing.get("cik", ""),
        accession=filing.get("accession", ""),
        fallback_url=filing["source_url"],
    )
    filing["source_url"] = source_url
    response = requests.get(source_url, headers=SEC_DOC_HEADERS, timeout=60)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()

    if ".pdf" in source_url.lower() or "application/pdf" in content_type:
        pdf_path = out_dir / f"{stem}.pdf"
        pdf_path.write_bytes(response.content)
        return pdf_path

    text = response.text
    if "<html" in text.lower() or "text/html" in content_type:
        text = _html_to_text(text)
    pdf_path = out_dir / f"{stem}.pdf"
    _text_to_pdf(text, pdf_path)
    return pdf_path


def log_to_apex_state(company: str, sector: str, source_url: str):
    if not APEX_PATH.exists():
        print("Apex path not found; skipping SQLite logging.")
        return
    if str(APEX_PATH) not in sys.path:
        sys.path.insert(0, str(APEX_PATH))
    try:
        from apex_state import ApexState  # type: ignore
    except Exception as exc:
        print(f"Failed to import apex_state; skipping log. Error: {exc}")
        return

    db = ApexState()
    doc_id = db.add_test_document(
        company=company,
        sector=sector or "Unknown",
        doc_type="10k",
        source_url=source_url,
    )
    print(f"Logged to Apex test_documents (id={doc_id})")


def main():
    parser = argparse.ArgumentParser(description="Download most recent 10-K from SEC EFTS")
    parser.add_argument("query", help="Ticker symbol or company name (e.g., MSFT)")
    parser.add_argument("--sector", default="Unknown", help="Sector tag for Apex logging")
    args = parser.parse_args()

    filing = search_latest_10k(args.query)
    pdf_path = download_filing_as_pdf(filing, TEST_DOCS_DIR)

    print(json.dumps({
        "company": filing["company"],
        "filing_date": filing["filing_date"],
        "form_type": filing["form_type"],
        "source_url": filing["source_url"],
        "saved_pdf": str(pdf_path),
    }, indent=2))

    log_to_apex_state(
        company=filing["company"],
        sector=args.sector,
        source_url=filing["source_url"],
    )


if __name__ == "__main__":
    main()
