#!/usr/bin/env python3
"""Stress-test extraction pipeline on real SEC 10-K filings.

This script:
1) Pulls 3 real 10-K filings from SEC EFTS API
2) Normalizes them to PDF (if filing source is HTML/TXT)
3) Runs Meridian extraction with citations enabled
4) Validates required key metrics + citation objects
5) Writes summary report to tests/extraction_test_results.json
"""

from __future__ import annotations

import json
import re
import traceback
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz
import requests
from bs4 import BeautifulSoup

EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_HEADERS = {
    "User-Agent": "MeridianAI/1.0 (real-doc stress test; contact: support@meridian.local)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "efts.sec.gov",
}
SEC_DOC_HEADERS = {
    "User-Agent": "MeridianAI/1.0 (real-doc stress test; contact: support@meridian.local)",
    "Accept-Encoding": "gzip, deflate",
}
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PipelineConfig
from core.pipeline import MeridianPipeline

TEST_DOCS_DIR = PROJECT_ROOT / "test_documents"
RESULTS_PATH = PROJECT_ROOT / "tests" / "extraction_test_results.json"

# Target profiles requested by prompt (messy financial styles)
TARGET_QUERIES = [
    {"label": "thousands_units_candidate", "query": "Fastenal", "sector": "Industrial"},
    {"label": "gaap_non_gaap_candidate", "query": "Microsoft", "sector": "Technology"},
    {"label": "ltm_candidate", "query": "Salesforce", "sector": "Technology"},
]

KEY_METRIC_PATHS = [
    "financials.revenue.ltm",
    "financials.ebitda.ltm",
    "financials.ebitda.adjusted_ebitda_ltm",
    "financials.revenue.cagr_3yr",
    "financials.gross_margin",
    "financials.ebitda.margin_ltm",
    "customers.top_customer_concentration",
    "financials.capex",
]

CITATION_PATHS = [
    "financials.revenue.ltm_citation",
    "financials.ebitda.ltm_citation",
    "financials.ebitda.adjusted_ebitda_ltm_citation",
    "financials.revenue.cagr_3yr_citation",
    "financials.gross_margin_citation",
    "financials.ebitda.margin_ltm_citation",
    "customers.top_customer_concentration_citation",
    "financials.capex_citation",
]


def _safe_name(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", text.strip())
    return cleaned.strip("_") or "document"


def _pick_field(record: Dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return None


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _resolve_cik(query: str) -> str | None:
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


def _build_filing_url(record: Dict[str, Any]) -> str | None:
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
    ciks = _pick_field(record, "ciks")
    if cik is None and isinstance(ciks, list) and ciks:
        cik = ciks[0]
    accession = _pick_field(record, "accessionNo", "accessionNumber", "adsh")
    primary_doc = _pick_field(record, "primaryDoc", "primaryDocument")

    if not (cik and accession):
        return None
    cik_num = str(int(str(cik)))
    accession = str(accession)
    acc_no_dash = accession.replace("-", "")
    if isinstance(primary_doc, str) and primary_doc:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dash}/{primary_doc}"
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_no_dash}/{accession}.txt"


def _normalize_10k_record(record: Dict[str, Any]) -> Dict[str, Any] | None:
    forms = []
    forms.extend(_as_list(_pick_field(record, "root_forms", "rootForms")))
    forms.append(_pick_field(record, "formType", "form", "file_type"))
    form_text = " ".join(str(x) for x in forms if x).upper()
    form = str(_pick_field(record, "formType", "form", "file_type") or "").upper()
    if not form:
        form = form_text
    if "10-K" not in form:
        return None

    company_names = _pick_field(record, "display_names", "entityName", "companyName", "company")
    if isinstance(company_names, list):
        company = str(company_names[0]) if company_names else "Unknown Company"
    else:
        company = str(company_names) if company_names else "Unknown Company"

    filing_date = _pick_field(record, "filedAt", "filingDate", "periodOfReport", "file_date")
    source_url = _build_filing_url(record)
    accession = _pick_field(record, "accessionNo", "accessionNumber", "adsh")
    cik = _pick_field(record, "cik", "cikNumber")
    ciks = _pick_field(record, "ciks")
    if cik is None and isinstance(ciks, list) and ciks:
        cik = ciks[0]

    source_id = _pick_field(record, "_id", "id")
    if isinstance(source_id, str) and ":" in source_id and cik is not None:
        adsh, filename = source_id.split(":", 1)
        accession = accession or adsh
        source_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(str(cik))}/{adsh.replace('-', '')}/{filename}"
        )

    if not source_url:
        return None
    return {
        "company": company,
        "form_type": form,
        "filing_date": str(filing_date) if filing_date else "unknown",
        "accession": str(accession) if accession else "unknown",
        "cik": str(cik) if cik else "unknown",
        "source_url": source_url,
    }


def _search_latest_10k(query: str) -> Dict[str, Any]:
    cik = _resolve_cik(query)
    params = {
        "q": f"{cik} 10-K" if cik else query,
        "from": "0",
        "size": "200",
    }
    response = requests.get(EFTS_SEARCH_URL, params=params, headers=SEC_HEADERS, timeout=45)
    response.raise_for_status()
    payload = response.json()

    candidates: List[Dict[str, Any]] = []
    for hit in _extract_hits(payload):
        norm = _normalize_10k_record(hit)
        if norm:
            candidates.append(norm)
    if cik:
        cik_int = str(int(cik))
        candidates = [
            c for c in candidates
            if c.get("cik") and str(int(str(c.get("cik")))) == cik_int
        ]
    if not candidates:
        raise RuntimeError(f"No 10-K candidates found from EFTS query: {query}")
    candidates.sort(key=lambda x: x["filing_date"], reverse=True)
    return candidates[0]


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _build_filing_index_url(cik: str, accession: str) -> str | None:
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
    if "sec.gov/ix?doc=" not in url:
        return url
    doc_part = url.split("ix?doc=", 1)[1]
    if doc_part.startswith("/"):
        return f"https://www.sec.gov{doc_part}"
    return f"https://www.sec.gov/{doc_part.lstrip('./')}"


def _resolve_primary_doc_from_documents_table(cik: str, accession: str) -> str | None:
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
    """Resolve primary filing document URL from Documents table first."""
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
    if not isinstance(items, list):
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


def _text_to_pdf(text: str, out_pdf: Path):
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
        wrapped_lines.extend(
            textwrap.wrap(
                line,
                width=wrap_width,
                replace_whitespace=False,
                drop_whitespace=False,
            ) or [""]
        )
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

    doc.save(str(out_pdf))
    doc.close()


def _download_filing_to_pdf(filing: Dict[str, Any], out_dir: Path) -> Path:
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

    out_pdf = out_dir / f"{stem}.pdf"
    if ".pdf" in source_url.lower() or "application/pdf" in content_type:
        out_pdf.write_bytes(response.content)
        return out_pdf

    text = response.text
    if "<html" in text.lower() or "text/html" in content_type:
        text = _html_to_text(text)
    _text_to_pdf(text, out_pdf)
    return out_pdf


def _get_nested(data: Dict[str, Any], dotted_path: str) -> Tuple[bool, Any]:
    node: Any = data
    for key in dotted_path.split("."):
        if not isinstance(node, dict) or key not in node:
            return False, None
        node = node[key]
    return True, node


def _is_non_null_metric(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none", "not_provided", "n/a"}:
        return False
    return True


def _is_valid_citation(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    page = value.get("page")
    section = value.get("section")
    snippet = value.get("snippet")
    return (
        isinstance(page, int)
        and page > 0
        and isinstance(section, str)
        and section.strip() != ""
        and isinstance(snippet, str)
        and snippet.strip() != ""
    )


def _run_extraction(pdf_path: Path) -> Dict[str, Any]:
    config = PipelineConfig(verbose=False)
    pipeline = MeridianPipeline(config)
    result = pipeline.analyze(str(pdf_path), with_citations=True)
    return result.extracted_data


def _validate_extraction(extracted: Dict[str, Any]) -> Dict[str, Any]:
    required_fields = {}
    required_ok = True
    for path in KEY_METRIC_PATHS:
        exists, value = _get_nested(extracted, path)
        valid = exists and _is_non_null_metric(value)
        required_fields[path] = {
            "exists": exists,
            "value": value,
            "non_null": valid,
        }
        if not valid:
            required_ok = False

    citations = {}
    citation_ok = True
    for path in CITATION_PATHS:
        exists, value = _get_nested(extracted, path)
        valid = exists and _is_valid_citation(value)
        citations[path] = {
            "exists": exists,
            "value": value,
            "valid_citation": valid,
        }
        if not valid:
            citation_ok = False

    return {
        "required_fields": required_fields,
        "citations": citations,
        "all_required_fields_non_null": required_ok,
        "all_citations_valid": citation_ok,
    }


def main():
    report: Dict[str, Any] = {
        "status": "ok",
        "documents_tested": [],
        "totals": {
            "tested": 0,
            "passed_required_fields": 0,
            "passed_citations": 0,
            "fully_passed": 0,
            "failed": 0,
        },
    }

    for target in TARGET_QUERIES:
        item: Dict[str, Any] = {
            "label": target["label"],
            "query": target["query"],
            "sector": target["sector"],
        }
        try:
            filing = _search_latest_10k(target["query"])
            pdf_path = _download_filing_to_pdf(filing, TEST_DOCS_DIR)
            item.update({
                "company": filing["company"],
                "filing_date": filing["filing_date"],
                "source_url": filing["source_url"],
                "pdf_path": str(pdf_path),
            })
            extracted = _run_extraction(pdf_path)
            validation = _validate_extraction(extracted)

            item.update({
                "validation": validation,
                "result": "pass" if (
                    validation["all_required_fields_non_null"]
                    and validation["all_citations_valid"]
                ) else "fail",
            })
        except Exception as exc:
            item.update({
                "result": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(limit=3),
            })

        report["documents_tested"].append(item)

    report["totals"]["tested"] = len(report["documents_tested"])
    for item in report["documents_tested"]:
        validation = item.get("validation", {})
        required_ok = bool(validation.get("all_required_fields_non_null"))
        cites_ok = bool(validation.get("all_citations_valid"))
        if required_ok:
            report["totals"]["passed_required_fields"] += 1
        if cites_ok:
            report["totals"]["passed_citations"] += 1
        if required_ok and cites_ok and item.get("result") == "pass":
            report["totals"]["fully_passed"] += 1
        if item.get("result") != "pass":
            report["totals"]["failed"] += 1

    if report["totals"]["failed"] > 0:
        report["status"] = "partial_fail"

    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote extraction report to: {RESULTS_PATH}")
    print(json.dumps(report["totals"], indent=2))


if __name__ == "__main__":
    main()
