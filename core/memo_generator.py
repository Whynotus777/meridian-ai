"""Investment memo generator.

Takes extracted CIM data and produces a structured investment memo
suitable for Investment Committee presentation.
"""

import json
from typing import Dict, Any, Optional

from config.settings import ModelConfig
from core.llm_client import LLMClient, strip_fences
from prompts.extraction import SYSTEM_PROMPT, MEMO_GENERATION_PROMPT


class MemoGenerator:
    """Generates IC-ready investment memos from extracted CIM data."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.client = LLMClient(self.config)

    def generate(self, extracted_data: Dict[str, Any]) -> str:
        """Generate an investment memo from extracted CIM data.

        Args:
            extracted_data: Structured dict from CIMExtractor.

        Returns:
            Formatted investment memo as string.
        """
        prompt = MEMO_GENERATION_PROMPT.format(
            extracted_data=json.dumps(extracted_data, indent=2, default=str)
        )

        return strip_fences(self.client.complete(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=8192,
            temperature=0.1,
        ))

    def generate_executive_summary(self, extracted_data: Dict[str, Any]) -> str:
        """Generate just the executive summary section."""
        company = extracted_data.get("company_overview", {})
        financials = extracted_data.get("financials", {})
        risks = extracted_data.get("risk_factors", {})

        prompt = f"""Write a 4-5 sentence executive summary for an IC memo.

Company: {company.get('company_name', 'Unknown')}
Description: {company.get('description', 'N/A')}
Industry: {company.get('industry', 'N/A')} / {company.get('sub_industry', 'N/A')}
Revenue (LTM): {financials.get('revenue', {}).get('ltm', 'N/A')}
EBITDA (LTM): {financials.get('ebitda', {}).get('ltm', 'N/A')}
Revenue CAGR: {financials.get('revenue', {}).get('cagr_3yr', 'N/A')}
Top risk: {risks.get('identified_risks', ['N/A'])[0] if risks.get('identified_risks') else 'N/A'}

Be specific with numbers. Lead with what makes this interesting, end with the key concern.
Return ONLY the summary paragraph, no headers."""

        return strip_fences(self.client.complete(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=500,
            temperature=0.1,
        ))
