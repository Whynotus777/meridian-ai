"""LLM-powered structured data extraction from CIM documents.

This is the core intelligence layer. Takes parsed document text
and uses Claude to extract structured financial/business data.
"""

import json
import re
from typing import Any, Dict, List, Optional

from config.settings import ModelConfig
from core.llm_client import LLMClient
from parsers.pdf_parser import ParsedDocument
from prompts.extraction import (
    SYSTEM_PROMPT,
    CIM_EXTRACTION_PROMPT,
    PromptRegistry,
)


# ---------------------------------------------------------------------------
# Citation helpers — pure string matching, no LLM
# ---------------------------------------------------------------------------

def _get_nested(d: Any, path: str) -> Any:
    """Traverse a dot-separated key path into a nested dict."""
    for key in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(key)
        if d is None:
            return None
    return d


def _set_nested(d: Dict, path: str, value: Any) -> None:
    """Set a value at a dot-separated path, creating intermediate dicts as needed."""
    keys = path.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _citation_candidates(value: Any, kind: str) -> List[str]:
    """Return ordered search strings for a metric value.

    kind:
        "money"  — raw USD integer → try billions/millions/thousands/raw formats
        "pct"    — decimal 0–1    → try percentage with 2dp and 1dp
        "count"  — integer        → try comma-formatted and bare integer

    Ordered most-specific first to minimise false positives.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return []

    candidates: List[str] = []

    if kind == "money":
        if v == 0:
            return []
        av = abs(v)
        if av >= 1e9:
            b = v / 1e9
            for dp in (3, 2, 1):
                s = f"{b:.{dp}f}"
                if s not in candidates:
                    candidates.append(s)
        if av >= 1e6:
            m = v / 1e6
            for dp in (3, 2, 1):
                s = f"{m:.{dp}f}"
                if s not in candidates:
                    candidates.append(s)
        if av >= 1e3:
            # comma-formatted thousands is highly distinctive
            s = f"{v / 1e3:,.0f}"
            if s not in candidates:
                candidates.append(s)
        raw = f"{int(v):,}"
        if raw not in candidates:
            candidates.append(raw)

    elif kind == "pct":
        pct = v * 100
        for dp in (2, 1):
            s = f"{pct:.{dp}f}"
            if s not in candidates:
                candidates.append(s)
        # Only add bare integer for percentages ≥ 10 that are exact whole numbers.
        # Single-digit percentages (like 6%) produce candidates "6.00"/"6.0" which
        # are distinctive enough; bare "6" would false-match almost any page.
        if pct >= 10 and abs(pct - round(pct)) < 0.005:
            s = str(int(round(pct)))
            if s not in candidates:
                candidates.append(s)

    elif kind == "count":
        iv = int(round(v))
        candidates = [f"{iv:,}", str(iv)]

    return candidates


def _find_page(pages: List[str], candidates: List[str]) -> Optional[int]:
    """Return the first 1-indexed page number where any candidate appears."""
    for page_idx, text in enumerate(pages):
        for candidate in candidates:
            if candidate in text:
                return page_idx + 1
    return None


class CIMExtractor:
    """Extracts structured data from CIM documents using LLM."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.client = LLMClient(self.config)
        self.prompt_registry = PromptRegistry()

    def extract(
        self,
        document: ParsedDocument,
        with_citations: bool = False,
    ) -> Dict[str, Any]:
        """Extract structured CIM data from a parsed document.

        Args:
            document: A ParsedDocument from any parser.
            with_citations: Use citation-augmented v2 prompt and output schema.

        Returns:
            Structured dict matching the CIM extraction schema.
        """
        # Build context: text + financial tables get priority
        text_content = self._build_extraction_context(document)

        if with_citations:
            prompt_version = self.prompt_registry.get("v2_citations")
            system_prompt = prompt_version.system_prompt
            extraction_prompt = prompt_version.extraction_prompt
        else:
            system_prompt = SYSTEM_PROMPT
            extraction_prompt = CIM_EXTRACTION_PROMPT

        prompt = extraction_prompt.format(document_text=text_content)

        response_text = self.client.complete(
            system=system_prompt,
            user=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        result = self._parse_response(response_text)
        return self._add_citations(result, document)

    # Financial statement section markers — ordered by specificity
    _FIN_STMT_MARKERS = [
        "CONSOLIDATED STATEMENTS OF OPERATIONS",
        "CONSOLIDATED STATEMENT OF OPERATIONS",
        "CONSOLIDATED STATEMENTS OF INCOME",
        "CONSOLIDATED STATEMENT OF INCOME",
        "STATEMENTS OF OPERATIONS",
        "STATEMENT OF OPERATIONS",
        "RESULTS OF OPERATIONS",
        "FINANCIAL HIGHLIGHTS",
        "Total revenue",
        "Total Revenue",
        "Net revenues",
        "Net revenue",
    ]

    def _build_extraction_context(self, document: ParsedDocument) -> str:
        """Build the text context sent to the LLM.

        Strategy:
          Short docs (≤120 K chars):  full text.
          Long docs (>120 K chars):
            1. First 40 K    — intro: business overview, strategy, risk factors
            2. 80 K from earliest financial-section marker (>40% into doc)
               — MD&A tables, selected financials, results of operations
            3. For very long docs (>200 K chars): an additional 60 K tail window
               starting from the LAST financial-section marker hit (>70% into doc),
               to capture the actual audited Item 8 financial statements which
               appear after the MD&A summary in annual reports / 10-Ks.
          Financial tables always appended last as markdown.
        """
        parts = []

        # Document metadata
        if document.metadata:
            meta_str = ", ".join(f"{k}: {v}" for k, v in document.metadata.items())
            parts.append(f"[Document metadata: {meta_str}]")

        text = document.raw_text
        INTRO_BUDGET  = 40_000   # chars from start (business description)
        FIN_BUDGET    = 80_000   # chars from financial section start
        TAIL_BUDGET   = 60_000   # extra chars for audited statements (long docs only)
        SHORT_BUDGET  = 120_000  # for short docs: just use raw text up to this
        LONG_THRESHOLD = 200_000 # threshold to trigger tail window

        if len(text) <= SHORT_BUDGET:
            parts.append(text)
        else:
            # Include intro section
            parts.append(text[:INTRO_BUDGET])

            # Find the financial statement section.
            # Collect ALL marker hits in the second half (>40%) and track both
            # the EARLIEST (for the primary window) and LATEST (for the tail).
            text_upper = text.upper()
            threshold = int(len(text) * 0.4)
            fallback = None
            all_hits: list = []  # all (idx) hits from markers in the second half

            for marker in self._FIN_STMT_MARKERS:
                # Collect ALL occurrences of this marker
                start = threshold
                while True:
                    idx = text_upper.find(marker.upper(), start)
                    if idx == -1:
                        break
                    all_hits.append(idx)
                    start = idx + 1
                # Also track a pre-threshold fallback
                if fallback is None:
                    pre_idx = text_upper.find(marker.upper())
                    if pre_idx != -1 and pre_idx < threshold:
                        fallback = pre_idx

            fin_start = min(all_hits) if all_hits else fallback

            if fin_start is not None and fin_start > INTRO_BUDGET:
                fin_section = text[fin_start: fin_start + FIN_BUDGET]
                parts.append(f"\n\n=== FINANCIAL STATEMENTS SECTION (starting at char {fin_start:,}) ===\n")
                parts.append(fin_section)

                # For very long documents add a tail window covering the audited
                # Item 8 financial statements which come after the MD&A section.
                # Use the LAST marker hit as tail_start so we capture the most
                # recent (audited) statements rather than MD&A summary tables.
                if len(text) > LONG_THRESHOLD and all_hits:
                    # Pick the latest hit that is also beyond the primary window
                    primary_end = fin_start + FIN_BUDGET
                    tail_candidates = [h for h in all_hits if h >= primary_end]
                    if tail_candidates:
                        tail_start = min(tail_candidates)  # earliest beyond primary window
                        if tail_start < len(text) - 1000:
                            parts.append(f"\n\n=== AUDITED FINANCIAL STATEMENTS (starting at char {tail_start:,}) ===\n")
                            parts.append(text[tail_start: tail_start + TAIL_BUDGET])
            else:
                # No clear financial section found — include next chunk after intro
                parts.append(text[INTRO_BUDGET: INTRO_BUDGET + FIN_BUDGET])

        # Append financial tables as markdown
        financial_tables = document.get_financial_tables()
        if financial_tables:
            parts.append("\n\n=== FINANCIAL TABLES ===\n")
            for i, table in enumerate(financial_tables[:10]):
                parts.append(f"\n[Table {i + 1}]")
                parts.append(f"Table page: {table.page_number}")
                parts.append(f"Table section heading: {table.context or 'not_provided'}")
                parts.append("Table markdown:")
                parts.append(table.to_markdown())

        return "\n\n".join(parts)

    def _add_citations(
        self, extraction: Dict[str, Any], document: ParsedDocument
    ) -> Dict[str, Any]:
        """Add page-level citations to an extraction dict via string matching.

        No LLM call.  For each key metric, generates candidate numeric
        representations (billions/millions/thousands/raw for money values,
        percentage strings for ratios) and searches every page of the parsed
        document.  On a match the first page number is recorded as:

            {"page": <int>, "confidence": 1.0}

        Works with both v1 and v2 extraction schemas — _set_nested creates
        citation keys even when they don't exist in the original dict.
        """
        pages = [s.get("text", "") for s in document.sections]

        # (value_dot_path, citation_dot_path, kind)
        METRICS = [
            ("financials.revenue.ltm",
             "financials.revenue.ltm_citation",                "money"),
            ("financials.ebitda.ltm",
             "financials.ebitda.ltm_citation",                 "money"),
            ("financials.ebitda.adjusted_ebitda_ltm",
             "financials.ebitda.adjusted_ebitda_ltm_citation", "money"),
            ("financials.gross_margin",
             "financials.gross_margin_citation",               "pct"),
            ("financials.net_income",
             "financials.net_income_citation",                 "money"),
            ("financials.capex",
             "financials.capex_citation",                      "money"),
            ("financials.cash",
             "financials.cash_citation",                       "money"),
            ("customers.total_customers",
             "customers.total_customers_citation",             "count"),
            ("customers.top_customer_concentration",
             "customers.top_customer_concentration_citation",  "pct"),
        ]

        for value_path, citation_path, kind in METRICS:
            value = _get_nested(extraction, value_path)
            if not value or value == "not_provided":
                continue
            candidates = _citation_candidates(value, kind)
            page_num = _find_page(pages, candidates)
            if page_num is not None:
                _set_nested(extraction, citation_path, {"page": page_num, "confidence": 1.0})

        return extraction

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM response into structured dict."""
        text = response_text.strip()

        # Strip markdown code fences — handles ```json, ```JSON, ```, etc.
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Repair literal control characters in JSON string values.
        # Gemini's v2_citations path embeds verbatim document snippets that
        # often contain real newlines/tabs — making the JSON structurally
        # invalid even after fence stripping.
        repaired = self._repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Find outermost { ... } block (handles preamble/postamble prose)
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            chunk = text[brace_start : brace_end + 1]
            try:
                return json.loads(chunk)
            except json.JSONDecodeError:
                try:
                    return json.loads(self._repair_json(chunk))
                except json.JSONDecodeError:
                    pass

        raise ValueError(
            f"Failed to parse LLM response as JSON. "
            f"First 500 chars: {response_text[:500]}"
        )

    @staticmethod
    def _repair_json(text: str) -> str:
        """Escape literal control characters inside JSON string values.

        Gemini returns citation snippets with real newline/tab/CR characters
        inside JSON strings instead of the required \\n/\\t/\\r escapes.
        This state machine walks the text and fixes them without touching the
        JSON structure itself.
        """
        out: list = []
        in_string = False
        escape_next = False
        for ch in text:
            if escape_next:
                out.append(ch)
                escape_next = False
            elif ch == "\\":
                out.append(ch)
                escape_next = True
            elif ch == '"':
                in_string = not in_string
                out.append(ch)
            elif in_string:
                if ch == "\n":
                    out.append("\\n")
                elif ch == "\r":
                    out.append("\\r")
                elif ch == "\t":
                    out.append("\\t")
                else:
                    out.append(ch)
            else:
                out.append(ch)
        return "".join(out)
