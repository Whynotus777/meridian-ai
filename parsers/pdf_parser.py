"""PDF document parser with layout-aware text and table extraction.

Uses pdfplumber for table detection and pymupdf (fitz) for text.
Designed to handle typical CIM formats: text-heavy with embedded financial tables.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

try:
    import fitz  # pymupdf
except ImportError:
    fitz = None

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

        if fitz is None:
            raise ImportError("pymupdf is required: pip install pymupdf")

    def parse(self, filepath: str) -> ParsedDocument:
        """Parse a PDF file into a ParsedDocument."""
        doc = fitz.open(filepath)
        total_pages = min(len(doc), self.max_pages)

        sections = []
        all_text_parts = []
        all_tables = []

        for page_num in range(total_pages):
            page = doc[page_num]
            page_text = page.get_text("text")
            page_text_clean = self._clean_text(page_text)
            all_text_parts.append(page_text_clean)

            section = {
                "page": page_num + 1,
                "text": page_text_clean,
                "tables": [],
            }

            # Extract tables with pdfplumber if available
            if self.extract_tables and pdfplumber is not None:
                page_tables = self._extract_tables_from_page(filepath, page_num)
                for tbl in page_tables:
                    tbl.context = self._get_table_context(page_text_clean, tbl)
                    all_tables.append(tbl)
                    section["tables"].append(tbl)

            sections.append(section)

        doc.close()

        return ParsedDocument(
            filename=filepath,
            total_pages=total_pages,
            sections=sections,
            tables=all_tables,
            raw_text="\n\n".join(all_text_parts),
            metadata=self._extract_metadata(filepath),
        )

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Normalize whitespace but preserve paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove common PDF artifacts
        text = re.sub(r"(?i)(confidential|draft|privileged)\s*[-–—]\s*", "", text)
        return text.strip()

    def _extract_tables_from_page(
        self, filepath: str, page_num: int
    ) -> List[ExtractedTable]:
        """Extract tables from a specific page using pdfplumber."""
        tables = []
        try:
            with pdfplumber.open(filepath) as pdf:
                if page_num >= len(pdf.pages):
                    return tables
                page = pdf.pages[page_num]
                raw_tables = page.extract_tables()

                for raw in raw_tables:
                    if not raw or len(raw) < 2:
                        continue
                    # First row as headers, rest as data
                    headers = [str(c).strip() if c else "" for c in raw[0]]
                    rows = []
                    for row in raw[1:]:
                        cleaned = [str(c).strip() if c else "" for c in row]
                        if any(c for c in cleaned):  # Skip empty rows
                            rows.append(cleaned)

                    if headers and rows:
                        tables.append(
                            ExtractedTable(
                                page_number=page_num + 1,
                                headers=headers,
                                rows=rows,
                            )
                        )
        except Exception:
            pass  # Graceful degradation — tables are supplementary

        return tables

    def _get_table_context(self, page_text: str, table: ExtractedTable) -> str:
        """Try to find the heading/label above a table."""
        if not table.headers:
            return ""
        # Look for the first header value in the page text
        first_header = table.headers[0]
        if first_header and first_header in page_text:
            idx = page_text.index(first_header)
            # Grab up to 200 chars before the table
            context_start = max(0, idx - 200)
            context = page_text[context_start:idx].strip()
            # Get the last line (likely the heading)
            lines = [l.strip() for l in context.split("\n") if l.strip()]
            return lines[-1] if lines else ""
        return ""

    def _extract_metadata(self, filepath: str) -> Dict[str, str]:
        """Extract PDF metadata."""
        meta = {}
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
