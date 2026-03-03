"""LLM-powered structured data extraction from CIM documents.

This is the core intelligence layer. Takes parsed document text
and uses Claude to extract structured financial/business data.
"""

import json
import re
from typing import Dict, Any, Optional

from config.settings import ModelConfig
from core.llm_client import LLMClient, strip_fences
from parsers.pdf_parser import ParsedDocument
from prompts.extraction import SYSTEM_PROMPT, CIM_EXTRACTION_PROMPT


class CIMExtractor:
    """Extracts structured data from CIM documents using LLM."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.client = LLMClient(self.config)

    def extract(self, document: ParsedDocument) -> Dict[str, Any]:
        """Extract structured CIM data from a parsed document.

        Args:
            document: A ParsedDocument from any parser.

        Returns:
            Structured dict matching the CIM extraction schema.
        """
        # Build context: text + financial tables get priority
        text_content = self._build_extraction_context(document)

        prompt = CIM_EXTRACTION_PROMPT.format(document_text=text_content)

        response_text = self.client.complete(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        return self._parse_response(response_text)

    def _build_extraction_context(self, document: ParsedDocument) -> str:
        """Build the text context sent to the LLM.

        Strategy: Include full text up to token budget, with financial
        tables rendered as markdown for better extraction.
        """
        parts = []

        # Include document metadata
        if document.metadata:
            meta_str = ", ".join(f"{k}: {v}" for k, v in document.metadata.items())
            parts.append(f"[Document metadata: {meta_str}]")

        # Main text content (cap at ~80k chars ≈ ~20k tokens)
        text = document.raw_text[:80000]
        parts.append(text)

        # Append financial tables as markdown for structured extraction
        financial_tables = document.get_financial_tables()
        if financial_tables:
            parts.append("\n\n=== FINANCIAL TABLES ===\n")
            for i, table in enumerate(financial_tables[:10]):  # Cap at 10 tables
                if table.context:
                    parts.append(f"\nTable context: {table.context}")
                parts.append(table.to_markdown())

        return "\n\n".join(parts)

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM response into structured dict."""
        text = strip_fences(response_text)

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Find outermost { ... } block
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"Failed to parse LLM response as JSON. "
            f"First 500 chars: {response_text[:500]}"
        )
