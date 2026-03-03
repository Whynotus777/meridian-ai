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

        sections = []
        all_text_parts = []
        all_tables = []

        for page_num in range(total_pages):
            page = doc[page_num]

            # Extract tables (native, no extra file I/O)
            page_tables = []
            if self.extract_tables:
                page_tables = self._extract_tables_fitz(page, page_num)

            # Build page content: text blocks and table markdown ordered by y-position
            page_text_clean, combined_text = self._build_page_content(
                page, page_tables
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
            metadata=self._extract_metadata_fitz(filepath),
        )

    def _extract_tables_fitz(self, page, page_num: int) -> List[ExtractedTable]:
        """Extract tables using PyMuPDF's native table finder.

        Uses the already-open page object — zero additional file I/O.
        Returns ExtractedTable objects in the same schema as the pdfplumber path.
        """
        tables: List[ExtractedTable] = []
        try:
            tab_finder = page.find_tables()
            for tab in tab_finder:
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
                    tables.append(ExtractedTable(
                        page_number=page_num + 1,
                        headers=headers,
                        rows=rows,
                    ))
        except Exception:
            pass  # Graceful degradation — tables are supplementary
        return tables

    def _build_page_content(
        self, page, page_tables: List[ExtractedTable]
    ) -> Tuple[str, str]:
        """Build per-page content by interleaving text and table markdown.

        Returns (plain_text, combined_text) where combined_text has table
        markdown inserted at the correct vertical position in the text stream.
        This preserves document structure so the LLM sees tables in context.
        """
        # Plain text (used for context lookup and raw_text fallback)
        plain_text = self._clean_text(page.get_text("text"))

        if not page_tables:
            return plain_text, plain_text

        # Collect text blocks with y-position (top of block)
        # block format: (x0, y0, x1, y1, text, block_no, block_type)
        # block_type 0 = text, 1 = image
        text_blocks: List[Tuple[float, str]] = []
        for block in page.get_text("blocks"):
            if block[6] == 0 and block[4].strip():  # text blocks only
                text_blocks.append((block[1], self._clean_text(block[4])))

        # Map each ExtractedTable back to its fitz table bbox y0
        # We do a second find_tables() call to get bboxes — cheap since it's in-memory
        table_bboxes: List[Tuple[float, str]] = []
        try:
            for tab in page.find_tables():
                table_data = tab.extract()
                if not table_data or len(table_data) < 2:
                    continue
                headers = [str(c or "").strip() for c in table_data[0]]
                # Match to our ExtractedTable by header equality
                for et in page_tables:
                    if et.headers == headers:
                        md = et.to_markdown()
                        table_bboxes.append((tab.bbox[1], md))
                        break
        except Exception:
            pass

        if not table_bboxes:
            # Can't match positions — append tables at end of page text
            combined = plain_text
            for et in page_tables:
                combined += "\n\n" + et.to_markdown()
            return plain_text, self._clean_text(combined)

        # Merge text blocks and table markdown, ordered by vertical position
        items: List[Tuple[float, str]] = text_blocks + table_bboxes
        items.sort(key=lambda x: x[0])

        combined_parts = [text for _, text in items if text.strip()]
        combined = "\n\n".join(combined_parts)
        return plain_text, combined

    def _extract_metadata_fitz(self, filepath: str) -> Dict[str, str]:
        """Extract PDF metadata using PyMuPDF."""
        meta: Dict[str, str] = {}
        try:
            doc = fitz.open(filepath)
            pdf_meta = doc.metadata
            if pdf_meta:
                for key in ["title", "author", "subject", "creator"]:
                    if pdf_meta.get(key):
                        meta[key] = pdf_meta[key]
            meta["page_count"] = str(len(doc))
            doc.close()
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
