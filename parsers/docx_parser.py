"""DOCX document parser.

Handles Word documents that some PE firms/banks send CIMs in.
"""

import re
from typing import List, Dict, Any
from dataclasses import field

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

from parsers.pdf_parser import ParsedDocument, ExtractedTable


class DOCXParser:
    """Parses DOCX files into structured text and tables."""

    def __init__(self, max_chars: int = 500000):
        self.max_chars = max_chars
        if DocxDocument is None:
            raise ImportError("python-docx required: pip install python-docx")

    def parse(self, filepath: str) -> ParsedDocument:
        doc = DocxDocument(filepath)

        sections = []
        all_tables = []
        current_section_text = []
        page_estimate = 1

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                text = element.text or ""
                # Simple paragraph extraction
                for child in element.iter():
                    if child.text:
                        text = child.text
                        break
                para_text = self._extract_paragraph_text(element)
                if para_text:
                    current_section_text.append(para_text)

            elif tag == "tbl":
                # Save current text as a section
                if current_section_text:
                    sections.append({
                        "page": page_estimate,
                        "text": "\n".join(current_section_text),
                        "tables": [],
                    })
                    current_section_text = []

                # Extract table
                table = self._extract_table(element, page_estimate)
                if table:
                    all_tables.append(table)
                    sections.append({
                        "page": page_estimate,
                        "text": "",
                        "tables": [table],
                    })

        # Final section
        if current_section_text:
            sections.append({
                "page": page_estimate,
                "text": "\n".join(current_section_text),
                "tables": [],
            })

        raw_text = "\n\n".join(s["text"] for s in sections if s["text"])

        return ParsedDocument(
            filename=filepath,
            total_pages=max(1, len(raw_text) // 3000),  # Rough page estimate
            sections=sections,
            tables=all_tables,
            raw_text=raw_text[:self.max_chars],
            metadata=self._extract_metadata(doc),
        )

    def _extract_paragraph_text(self, element) -> str:
        """Extract all text from a paragraph element."""
        texts = []
        for child in element.iter():
            if child.text:
                texts.append(child.text)
            if child.tail:
                texts.append(child.tail)
        return " ".join(texts).strip()

    def _extract_table(self, tbl_element, page_num: int) -> ExtractedTable | None:
        """Extract a table from a DOCX table element."""
        rows_data = []
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        for tr in tbl_element.findall(".//w:tr", ns):
            row = []
            for tc in tr.findall(".//w:tc", ns):
                cell_text = ""
                for p in tc.findall(".//w:p", ns):
                    for r in p.findall(".//w:r", ns):
                        for t in r.findall(".//w:t", ns):
                            if t.text:
                                cell_text += t.text
                row.append(cell_text.strip())
            if row:
                rows_data.append(row)

        if len(rows_data) < 2:
            return None

        return ExtractedTable(
            page_number=page_num,
            headers=rows_data[0],
            rows=rows_data[1:],
        )

    def _extract_metadata(self, doc) -> Dict[str, str]:
        meta = {}
        try:
            cp = doc.core_properties
            if cp.title:
                meta["title"] = cp.title
            if cp.author:
                meta["author"] = cp.author
            if cp.subject:
                meta["subject"] = cp.subject
        except Exception:
            pass
        return meta
