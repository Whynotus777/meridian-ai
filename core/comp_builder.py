"""Comparable company and transaction set builder.

Uses LLM to suggest relevant public comps and precedent transactions
based on the target company's profile.
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from config.settings import ModelConfig
from core.llm_client import LLMClient, strip_fences
from prompts.extraction import SYSTEM_PROMPT, COMP_BUILDER_PROMPT


@dataclass
class Comparable:
    """A single comparable company or transaction."""
    name: str
    type: str  # "trading_comp" or "precedent_transaction"
    rationale: str
    ev_revenue: Optional[float] = None
    ev_ebitda: Optional[float] = None
    key_differences: str = ""
    confidence: float = 0.5

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.type,
            "rationale": self.rationale,
            "ev_revenue": self.ev_revenue,
            "ev_ebitda": self.ev_ebitda,
            "key_differences": self.key_differences,
            "confidence": self.confidence,
        }


class CompBuilder:
    """Builds comparable company and transaction sets."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.client = LLMClient(self.config)

    def build(self, extracted_data: Dict[str, Any]) -> List[Comparable]:
        """Generate comparable companies and transactions.

        Args:
            extracted_data: Structured CIM data from extractor.

        Returns:
            List of Comparable objects, sorted by relevance.
        """
        company_data = self._build_company_summary(extracted_data)

        prompt = COMP_BUILDER_PROMPT.format(company_data=company_data)

        text = self.client.complete(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=3000,
            temperature=0.1,
        )
        return self._parse_comps(text)

    def _build_company_summary(self, data: Dict) -> str:
        """Build a concise company summary for comp matching."""
        co = data.get("company_overview", {})
        fin = data.get("financials", {})
        market = data.get("market", {})

        parts = [
            f"Company: {co.get('company_name', 'Unknown')}",
            f"Industry: {co.get('industry', 'N/A')} / {co.get('sub_industry', 'N/A')}",
            f"Business model: {co.get('business_model', 'N/A')}",
            f"Revenue (LTM): {fin.get('revenue', {}).get('ltm', 'N/A')}",
            f"EBITDA (LTM): {fin.get('ebitda', {}).get('ltm', 'N/A')}",
            f"EBITDA margin: {fin.get('ebitda', {}).get('margin_ltm', 'N/A')}",
            f"Revenue CAGR: {fin.get('revenue', {}).get('cagr_3yr', 'N/A')}",
            f"Recurring revenue: {fin.get('recurring_revenue_pct', 'N/A')}",
            f"Employees: {co.get('employees', 'N/A')}",
            f"Geography: {co.get('headquarters', 'N/A')}",
            f"Market position: {market.get('competitive_position', 'N/A')}",
            f"Key competitors: {', '.join(market.get('key_competitors', []))}",
        ]
        return "\n".join(parts)

    def _parse_comps(self, response_text: str) -> List[Comparable]:
        """Parse LLM response into Comparable objects."""
        comps = []

        text = strip_fences(response_text)

        # Try direct parse first, then find outermost [ ... ] block
        data = None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            bracket_start = text.find("[")
            bracket_end   = text.rfind("]")
            if bracket_start != -1 and bracket_end != -1:
                try:
                    data = json.loads(text[bracket_start:bracket_end + 1])
                except json.JSONDecodeError:
                    pass

        if not data:
            return comps

        try:
            for item in data:
                if not isinstance(item, dict):
                    continue
                comps.append(Comparable(
                    name=item.get("name", item.get("company", "Unknown")),
                    type=item.get("type", "trading_comp"),
                    rationale=item.get("rationale", item.get("why_comparable", "")),
                    ev_revenue=self._safe_float(item.get("ev_revenue")),
                    ev_ebitda=self._safe_float(item.get("ev_ebitda")),
                    key_differences=item.get("key_differences", ""),
                    confidence=self._safe_float(item.get("confidence"), 0.5),
                ))
        except json.JSONDecodeError:
            pass

        return sorted(comps, key=lambda c: c.confidence, reverse=True)

    def _safe_float(self, val, default=None):
        if val is None or val == "not_provided":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
