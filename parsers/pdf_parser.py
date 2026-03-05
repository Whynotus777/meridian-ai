"""PDF document parser with layout-aware text and table extraction.

Primary engine: PyMuPDF (fitz) — used for both text and table extraction.
  • Text: page.get_text() — fast native extraction
  • Tables: page.find_tables() — native table detector, no extra file I/O
  • Per-page content is built by interleaving text blocks and table markdown
    ordered by vertical position so document structure is preserved for the LLM.

Fallback: pdfplumber — used only if PyMuPDF is unavailable.
"""

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

try:
    import fitz  # pymupdf
    USE_PYMUPDF = True
except ImportError:
    fitz = None
    USE_PYMUPDF = False

if not USE_PYMUPDF:
    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None


@dataclass
class ExtractedTable:
    """A table extracted from the document."""
    page_number: int
    headers: List[str]
    rows: List[List[str]]
    context: str = ""  # Text immediately before the table (section heading, etc.)

    def to_markdown(self) -> str:
        if not self.headers:
            return ""
        md = "| " + " | ".join(self.headers) + " |\n"
        md += "| " + " | ".join(["---"] * len(self.headers)) + " |\n"
        for row in self.rows:
            # Pad row to match header count
            padded = row + [""] * (len(self.headers) - len(row))
            md += "| " + " | ".join(padded[: len(self.headers)]) + " |\n"
        return md


@dataclass
class ParsedDocument:
    """Fully parsed document with text, tables, and metadata."""
    filename: str
    total_pages: int
    sections: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[ExtractedTable] = field(default_factory=list)
    raw_text: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)

    def get_full_text(self) -> str:
        """Return all text content as a single string."""
        return self.raw_text

    def get_text_with_tables(self) -> str:
        """Return text with tables rendered as markdown inline."""
        parts = []
        for section in self.sections:
            parts.append(section.get("text", ""))
            for table in section.get("tables", []):
                parts.append("\n[TABLE]\n" + table.to_markdown() + "[/TABLE]\n")
        return "\n\n".join(parts) if parts else self.raw_text

    def get_financial_tables(self) -> List[ExtractedTable]:
        """Filter for tables that likely contain financial data."""
        financial_keywords = [
            "revenue", "ebitda", "margin", "income", "profit", "loss",
            "cash flow", "balance sheet", "capex", "debt", "growth",
            "historical", "projected", "forecast", "fiscal", "fy",
            "$", "%", "000", "millions",
        ]
        results = []
        for table in self.tables:
            combined = " ".join(table.headers + [c for row in table.rows for c in row]).lower()
            combined += " " + table.context.lower()
            if any(kw in combined for kw in financial_keywords):
                results.append(table)
        return results


class PDFParser:
    """Parses PDF documents into structured text and tables."""

    def __init__(self, max_pages: int = 150, extract_tables: bool = True):
        self.max_pages = max_pages
        self.extract_tables = extract_tables

        if not USE_PYMUPDF and pdfplumber is None:
            raise ImportError(
                "No PDF library available. Install PyMuPDF: pip install pymupdf"
            )

    def parse(self, filepath: str) -> ParsedDocument:
        """Parse a PDF file into a ParsedDocument."""
        _t0 = time.time()

        if USE_PYMUPDF:
            result = self._parse_pymupdf(filepath)
        else:
            result = self._parse_pdfplumber(filepath)

        elapsed = time.time() - _t0
        print(f"[TIMING] Parse ({result.total_pages} pages): {elapsed:.1f}s")
        return result

    # ── Primary path: PyMuPDF ─────────────────────────────────────────────

    def _parse_pymupdf(self, filepath: str) -> ParsedDocument:
        """Parse using PyMuPDF — text + native table detection, single file open."""
        doc = fitz.open(filepath)
        total_pages = min(len(doc), self.max_pages)

        # Extract metadata while the doc is already open (avoids a second fitz.open)
        meta = self._extract_metadata_from_doc(doc)

        sections = []
        all_text_parts = []
        all_tables = []
        tables_found_so_far = 0
        pages_scanned_for_tables = 0
        _MAX_TABLE_SCAN_PAGES = 15  # cap: find_tables() on at most 15 pages per doc

        for page_num in range(total_pages):
            page = doc[page_num]
            page_text_clean = self._clean_text(page.get_text("text"))

            # Returns (ExtractedTable, y0) pairs — single find_tables() call per page
            page_table_pairs: List[Tuple[ExtractedTable, float]] = []
            if (
                self.extract_tables
                and pages_scanned_for_tables < _MAX_TABLE_SCAN_PAGES
                and self._should_scan_for_tables(
                    page_text_clean, page_num, tables_found_so_far
                )
            ):
                page_table_pairs = self._extract_tables_fitz(page, page_num)
                pages_scanned_for_tables += 1

            page_tables = [et for et, _ in page_table_pairs]
            tables_found_so_far += len(page_tables)

            # Build page content: text blocks and table markdown ordered by y-position
            # Pass pairs so _build_page_content reuses bboxes (no second find_tables)
            page_text_clean, combined_text = self._build_page_content(
                page, page_table_pairs, page_text_clean
            )

            # Attach context (nearby heading text) to each table
            for tbl in page_tables:
                tbl.context = self._get_table_context(page_text_clean, tbl)
                all_tables.append(tbl)

            all_text_parts.append(combined_text)
            sections.append({
                "page":   page_num + 1,
                "text":   combined_text,
                "tables": page_tables,
            })

        doc.close()

        return ParsedDocument(
            filename=filepath,
            total_pages=total_pages,
            sections=sections,
            tables=all_tables,
            raw_text="\n\n".join(all_text_parts),
            metadata=meta,
        )

    def _extract_tables_fitz(
        self, page, page_num: int
    ) -> List[Tuple["ExtractedTable", float]]:
        """Extract tables using PyMuPDF's native table finder.

        Returns (ExtractedTable, y0) pairs so callers can order tables by
        vertical position without a second find_tables() call.
        """
        results: List[Tuple[ExtractedTable, float]] = []
        try:
            for tab in page.find_tables():
                table_data = tab.extract()
                if not table_data or len(table_data) < 2:
                    continue
                headers = [str(c or "").strip() for c in table_data[0]]
                rows: List[List[str]] = []
                for row in table_data[1:]:
                    cleaned = [str(c or "").strip() for c in row]
                    if any(c for c in cleaned):
                        rows.append(cleaned)
                if headers and rows:
                    et = ExtractedTable(
                        page_number=page_num + 1,
                        headers=headers,
                        rows=rows,
                    )
                    results.append((et, tab.bbox[1]))
        except Exception:
            pass  # Graceful degradation — tables are supplementary
        return results

    def _build_page_content(
        self,
        page,
        page_table_pairs: List[Tuple["ExtractedTable", float]],
        plain_text: str,
    ) -> Tuple[str, str]:
        """Build per-page content by interleaving text and table markdown.

        Accepts (ExtractedTable, y0) pairs produced by _extract_tables_fitz so
        that no second find_tables() call is needed.  Returns (plain_text,
        combined_text) where combined_text has table markdown inserted at the
        correct vertical position.
        """
        if not page_table_pairs:
            return plain_text, plain_text

        # Collect text blocks with y-position (block_type 0 = text, 1 = image)
        text_blocks: List[Tuple[float, str]] = []
        for block in page.get_text("blocks"):
            if block[6] == 0 and block[4].strip():
                text_blocks.append((block[1], self._clean_text(block[4])))

        # Reuse pre-computed bboxes — no second find_tables() call
        table_bboxes: List[Tuple[float, str]] = [
            (y0, et.to_markdown()) for et, y0 in page_table_pairs
        ]

        # Merge and sort by vertical position
        items: List[Tuple[float, str]] = text_blocks + table_bboxes
        items.sort(key=lambda x: x[0])

        combined_parts = [text for _, text in items if text.strip()]
        combined = "\n\n".join(combined_parts)
        return plain_text, combined

    def _should_scan_for_tables(
        self,
        page_text: str,
        page_num: int,
        tables_found_so_far: int,
    ) -> bool:
        """Fast heuristic to skip expensive find_tables on narrative-heavy pages."""
        if not page_text:
            return False

        text = page_text.lower()
        # Strong signals: likely true financial statement pages.
        strong_table_signals = (
            "consolidated statements",
            "balance sheet",
            "cash flow",
            "statement of operations",
            "statement of income",
            "in millions",
            "in thousands",
            "amounts in",
            "selected financial data",
        )
        if any(sig in text for sig in strong_table_signals):
            return True

        # If we reached deeper pages without finding any table, throttle hard.
        if page_num >= 35 and tables_found_so_far == 0:
            return False

        # Numeric density + year density catches compact table pages.
        digit_count = sum(ch.isdigit() for ch in page_text)
        if digit_count < 180:
            return False

        # Year density alone is not enough — 10-K narrative sections mention years
        # constantly (MD&A, risk factors).  Require high year density (≥10) AND
        # meaningful dollar/percent density to avoid scanning narrative pages.
        year_hits = len(re.findall(r"\b20\d{2}\b", page_text))
        money_hits = len(re.findall(r"\$\s?\d", page_text))
        percent_hits = page_text.count("%")
        if year_hits >= 10 and (money_hits + percent_hits) >= 8:
            return True

        return (money_hits + percent_hits) >= 15

    def _extract_metadata_from_doc(self, doc) -> Dict[str, str]:
        """Extract PDF metadata from an already-open fitz document."""
        meta: Dict[str, str] = {}
        try:
            pdf_meta = doc.metadata
            if pdf_meta:
                for key in ["title", "author", "subject", "creator"]:
                    if pdf_meta.get(key):
                        meta[key] = pdf_meta[key]
            meta["page_count"] = str(len(doc))
        except Exception:
            pass
        return meta

    # ── Fallback path: pdfplumber ─────────────────────────────────────────

    def _parse_pdfplumber(self, filepath: str) -> ParsedDocument:
        """Parse using pdfplumber (fallback when PyMuPDF is unavailable)."""
        import pdfplumber as _pdfplumber

        sections = []
        all_text_parts = []
        all_tables: List[ExtractedTable] = []

        with _pdfplumber.open(filepath) as pdf:
            total_pages = min(len(pdf.pages), self.max_pages)
            for page_num in range(total_pages):
                page = pdf.pages[page_num]
                page_text = page.extract_text() or ""
                page_text_clean = self._clean_text(page_text)
                all_text_parts.append(page_text_clean)

                page_tables: List[ExtractedTable] = []
                if self.extract_tables:
                    raw_tables = page.extract_tables() or []
                    for raw in raw_tables:
                        if not raw or len(raw) < 2:
                            continue
                        headers = [str(c or "").strip() for c in raw[0]]
                        rows = []
                        for row in raw[1:]:
                            cleaned = [str(c or "").strip() for c in row]
                            if any(c for c in cleaned):
                                rows.append(cleaned)
                        if headers and rows:
                            tbl = ExtractedTable(
                                page_number=page_num + 1,
                                headers=headers,
                                rows=rows,
                            )
                            tbl.context = self._get_table_context(page_text_clean, tbl)
                            page_tables.append(tbl)
                            all_tables.append(tbl)

                sections.append({
                    "page":   page_num + 1,
                    "text":   page_text_clean,
                    "tables": page_tables,
                })

        meta: Dict[str, str] = {}
        try:
            with _pdfplumber.open(filepath) as pdf:
                if pdf.metadata:
                    for key in ["Title", "Author", "Subject", "Creator"]:
                        if pdf.metadata.get(key):
                            meta[key.lower()] = pdf.metadata[key]
            meta["page_count"] = str(total_pages)
        except Exception:
            pass

        return ParsedDocument(
            filename=filepath,
            total_pages=total_pages,
            sections=sections,
            tables=all_tables,
            raw_text="\n\n".join(all_text_parts),
            metadata=meta,
        )

    # ── Shared helpers ────────────────────────────────────────────────────

    def _clean_text(self, text: str) -> str:
        """Normalize whitespace and strip common PDF artifacts."""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?i)(confidential|draft|privileged)\s*[-–—]\s*", "", text)
        return text.strip()

    def _get_table_context(self, page_text: str, table: ExtractedTable) -> str:
        """Find the heading or label immediately above a table."""
        if not table.headers:
            return ""
        first_header = table.headers[0]
        if first_header and first_header in page_text:
            idx = page_text.index(first_header)
            context_start = max(0, idx - 200)
            context = page_text[context_start:idx].strip()
            lines = [l.strip() for l in context.split("\n") if l.strip()]
            return lines[-1] if lines else ""
        return ""
