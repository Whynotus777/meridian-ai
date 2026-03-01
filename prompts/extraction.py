"""Versioned prompt templates for CIM extraction.

Supports multiple prompt versions so the same CIM can be run through
different versions and extraction accuracy compared field-by-field.

Usage:
    from prompts.extraction import SYSTEM_PROMPT, CIM_EXTRACTION_PROMPT  # v1 (default)
    from prompts.extraction import PromptRegistry, compare_extractions

    registry = PromptRegistry()
    v1_prompts = registry.get("v1")
    v2_prompts = registry.get("v2")

    diff = compare_extractions(document_text, "v1", "v2", client, model)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ===========================================================================
# V1 — Original prompts (production baseline)
# ===========================================================================

SYSTEM_PROMPT_V1 = """You are an expert private equity analyst. You extract structured
financial and business data from Confidential Information Memorandums (CIMs).
You are precise, conservative in estimates, and flag uncertainty.
You never fabricate data — if information is not in the document, say "not_provided".
Return ONLY valid JSON. No markdown, no explanation, no preamble."""

CIM_EXTRACTION_PROMPT_V1 = """Analyze this CIM document and extract structured data.

Return ONLY a valid JSON object with these exact fields:

{{
    "company_overview": {{
        "company_name": "string",
        "description": "2-3 sentence summary of what the company does",
        "industry": "Primary industry",
        "sub_industry": "Specific niche",
        "business_model": "B2B | B2C | B2B2C | Marketplace | Hybrid",
        "founding_year": "YYYY or not_provided",
        "headquarters": "City, State/Country",
        "employees": "number or range, e.g. '150' or '100-200'",
        "website": "URL or not_provided"
    }},
    "financials": {{
        "currency": "USD | EUR | GBP | etc",
        "revenue": {{
            "ltm": "Latest twelve months revenue as number or not_provided",
            "prior_year": "Prior full year revenue or not_provided",
            "two_years_ago": "Revenue from 2 years ago or not_provided",
            "cagr_3yr": "3-year revenue CAGR as decimal (0.15 = 15%) or not_provided"
        }},
        "ebitda": {{
            "ltm": "LTM EBITDA or not_provided",
            "margin_ltm": "EBITDA margin as decimal or not_provided",
            "adjusted_ebitda_ltm": "Adjusted EBITDA if provided or not_provided"
        }},
        "gross_margin": "as decimal or not_provided",
        "net_income": "LTM net income or not_provided",
        "capex": "Annual capex or not_provided",
        "debt": "Total debt or not_provided",
        "cash": "Cash and equivalents or not_provided",
        "recurring_revenue_pct": "% of revenue that is recurring (decimal) or not_provided",
        "revenue_by_segment": [
            {{"segment": "name", "revenue": "amount", "pct_of_total": "decimal"}}
        ]
    }},
    "customers": {{
        "total_customers": "number or range or not_provided",
        "top_customer_concentration": "% of revenue from top customer (decimal) or not_provided",
        "top_10_concentration": "% from top 10 customers (decimal) or not_provided",
        "customer_retention": "annual retention rate as decimal or not_provided",
        "net_revenue_retention": "NRR as decimal or not_provided",
        "avg_contract_value": "ACV or not_provided",
        "notable_customers": ["list of named customers mentioned"]
    }},
    "market": {{
        "tam": "Total addressable market size or not_provided",
        "market_growth_rate": "Annual market growth as decimal or not_provided",
        "competitive_position": "Market leader | Strong player | Niche player | Emerging",
        "key_competitors": ["list of competitors mentioned"],
        "key_trends": ["list of market trends discussed"]
    }},
    "management": {{
        "ceo_name": "name or not_provided",
        "ceo_tenure_years": "number or not_provided",
        "key_executives": [
            {{"name": "string", "title": "string", "years_at_company": "number or not_provided"}}
        ],
        "management_ownership": "% owned by management or not_provided"
    }},
    "growth_thesis": {{
        "organic_levers": ["list of organic growth drivers mentioned"],
        "ma_opportunity": "Description of M&A/add-on opportunity or not_provided",
        "expansion_plans": ["geographic, product, or market expansion plans"],
        "technology_initiatives": ["tech/AI/digital transformation plans"]
    }},
    "risk_factors": {{
        "customer_concentration_risk": "low | medium | high based on data",
        "key_person_dependency": "low | medium | high",
        "regulatory_risk": "low | medium | high with brief explanation",
        "market_cyclicality": "low | medium | high",
        "technology_risk": "low | medium | high",
        "identified_risks": ["explicit risks mentioned in the document"]
    }},
    "deal_context": {{
        "reason_for_sale": "Why the company is being sold or not_provided",
        "asking_multiple": "EV/EBITDA multiple mentioned or not_provided",
        "transaction_type": "Full sale | Majority recap | Minority investment | not_provided",
        "advisor": "Investment bank or advisor named or not_provided"
    }},
    "extraction_confidence": {{
        "financial_data": 0.0 to 1.0,
        "business_description": 0.0 to 1.0,
        "market_data": 0.0 to 1.0,
        "overall": 0.0 to 1.0
    }}
}}

CRITICAL RULES:
- Use "not_provided" for ANY field where data is not explicitly in the document
- All financial numbers should be raw numbers (no $ signs, no commas)
- All percentages as decimals (15% = 0.15)
- Be conservative — do not extrapolate or assume
- If a range is given, use the midpoint
- Flag low confidence for any inferred (vs. stated) values

CIM DOCUMENT:
{document_text}
"""


# ===========================================================================
# V2 — Enhanced prompts: better table parsing, explicit unit detection,
#       per-field confidence, and richer qualitative sections
# ===========================================================================

SYSTEM_PROMPT_V2 = """You are a senior private equity analyst and financial data specialist.
You extract structured, machine-readable data from Confidential Information Memorandums (CIMs)
with surgical precision.

Core principles:
1. ACCURACY OVER COMPLETENESS — if uncertain, use "not_provided"; never fabricate or extrapolate
2. UNIT AWARENESS — always detect the document's stated unit (thousands, millions, billions)
   and normalize all numbers to raw values (1,000,000 = one million)
3. TIMESTAMP ANCHORING — note the period (LTM, FY2023, H1-2024) wherever relevant
4. FIELD-LEVEL CONFIDENCE — rate each numeric field you extract (1=stated, 0.7=derived, 0.4=inferred)
5. Return ONLY valid JSON. No markdown, no prose, no preamble."""

CIM_EXTRACTION_PROMPT_V2 = """Analyze this CIM document and extract structured data with enhanced precision.

Return ONLY a valid JSON object. The schema below uses [_conf] fields to capture
per-field confidence (1.0 = explicitly stated in document, 0.7 = calculated from stated data,
0.4 = inferred/estimated, 0.0 = not available).

{{
    "schema_version": "v2",
    "document_unit": "millions | thousands | raw — detected currency scale in the document",
    "reporting_period_end": "YYYY-MM or not_provided",

    "company_overview": {{
        "company_name": "string",
        "description": "3-4 sentence summary including product, market, and differentiation",
        "industry": "Primary industry (use standard PE sector taxonomy)",
        "sub_industry": "Specific vertical niche",
        "business_model": "B2B | B2C | B2B2C | Marketplace | SaaS | Hybrid",
        "founding_year": "YYYY or not_provided",
        "headquarters": "City, State/Country",
        "additional_offices": ["City, Country"],
        "employees": "number or range",
        "employees_conf": 0.0,
        "website": "URL or not_provided",
        "key_products_services": ["list of main products or services"],
        "moat_description": "1-2 sentences on competitive advantages / barriers to entry"
    }},

    "financials": {{
        "currency": "USD | EUR | GBP | etc",
        "revenue": {{
            "ltm":           "raw number or not_provided",
            "ltm_period":    "e.g. LTM Sep-2024 or not_provided",
            "ltm_conf":      0.0,
            "fy_current":    "Current fiscal year revenue or not_provided",
            "fy_minus_1":    "Prior fiscal year revenue or not_provided",
            "fy_minus_2":    "Revenue 2 fiscal years ago or not_provided",
            "fy_minus_3":    "Revenue 3 fiscal years ago or not_provided",
            "cagr_3yr":      "3-year CAGR as decimal or not_provided",
            "cagr_3yr_conf": 0.0
        }},
        "ebitda": {{
            "ltm":                  "LTM EBITDA raw number or not_provided",
            "ltm_conf":             0.0,
            "margin_ltm":           "EBITDA margin decimal or not_provided",
            "adjusted_ebitda_ltm":  "Adjusted EBITDA raw number or not_provided",
            "addback_items":        ["list of stated add-back items"],
            "addback_total":        "Total add-backs raw number or not_provided",
            "fy_current":           "FY EBITDA or not_provided",
            "fy_minus_1":           "Prior FY EBITDA or not_provided"
        }},
        "gross_profit":              "LTM gross profit raw or not_provided",
        "gross_margin":              "as decimal or not_provided",
        "net_income":                "LTM net income raw or not_provided",
        "capex":                     "Annual capex raw or not_provided",
        "capex_as_pct_revenue":      "decimal or not_provided",
        "free_cash_flow":            "LTM FCF raw or not_provided",
        "debt":                      "Total debt raw or not_provided",
        "net_debt":                  "Net debt (debt minus cash) raw or not_provided",
        "cash":                      "Cash raw or not_provided",
        "recurring_revenue_pct":     "decimal or not_provided",
        "revenue_by_segment": [
            {{
                "segment":       "name",
                "revenue":       "raw number",
                "pct_of_total":  "decimal",
                "growth_rate":   "YoY growth decimal or not_provided"
            }}
        ],
        "revenue_by_geography": [
            {{"region": "name", "pct_of_total": "decimal"}}
        ],
        "financial_notes": "Any material footnotes or accounting policy comments"
    }},

    "customers": {{
        "total_customers": "number or not_provided",
        "top_customer_concentration": "decimal or not_provided",
        "top_5_concentration":  "decimal or not_provided",
        "top_10_concentration": "decimal or not_provided",
        "customer_retention":   "annual gross retention decimal or not_provided",
        "net_revenue_retention":"NRR decimal or not_provided",
        "avg_contract_value":   "raw or not_provided",
        "avg_contract_length_years": "number or not_provided",
        "sales_cycle_days":     "number or not_provided",
        "notable_customers":    ["named customers"],
        "customer_segments":    ["e.g. Enterprise, Mid-Market, SMB"],
        "churn_rate":           "annual churn decimal or not_provided"
    }},

    "market": {{
        "tam":                "Total addressable market description or number",
        "sam":                "Serviceable addressable market or not_provided",
        "market_growth_rate": "decimal or not_provided",
        "competitive_position": "Market leader | Strong player | Niche player | Emerging",
        "market_share_estimate": "decimal or not_provided",
        "key_competitors":    ["list"],
        "barriers_to_entry":  ["list of moat/barrier items mentioned"],
        "key_trends":         ["macro and sector trends discussed"],
        "regulatory_environment": "brief description or not_provided"
    }},

    "management": {{
        "ceo_name":          "name or not_provided",
        "ceo_tenure_years":  "number or not_provided",
        "ceo_background":    "1-2 sentence bio or not_provided",
        "key_executives": [
            {{
                "name":              "string",
                "title":             "string",
                "years_at_company":  "number or not_provided",
                "prior_employer":    "string or not_provided"
            }}
        ],
        "management_ownership": "decimal or not_provided",
        "equity_incentive_plan": "description or not_provided",
        "board_composition":     "description or not_provided"
    }},

    "growth_thesis": {{
        "organic_levers":         ["list of organic growth drivers"],
        "pricing_power":          "description or not_provided",
        "product_roadmap":        ["key product expansion items"],
        "geographic_expansion":   ["target regions or not_provided"],
        "ma_opportunity":         "description or not_provided",
        "ma_pipeline_size":       "number of targets or not_provided",
        "technology_initiatives": ["AI/tech transformation plans"]
    }},

    "risk_factors": {{
        "customer_concentration_risk": "low | medium | high",
        "key_person_dependency":       "low | medium | high",
        "regulatory_risk":             "low | medium | high",
        "market_cyclicality":          "low | medium | high",
        "technology_risk":             "low | medium | high",
        "leverage_risk":               "low | medium | high",
        "integration_risk":            "low | medium | high",
        "identified_risks":            ["explicit risks mentioned in document"],
        "data_inconsistencies":        ["any figures that appear contradictory"]
    }},

    "deal_context": {{
        "reason_for_sale":     "string or not_provided",
        "asking_multiple":     "EV/EBITDA number or not_provided",
        "asking_ev":           "EV in raw or not_provided",
        "transaction_type":    "Full sale | Majority recap | Minority investment | not_provided",
        "process_type":        "Auction | Bilateral | not_provided",
        "advisor":             "bank name or not_provided",
        "loi_deadline":        "date or not_provided",
        "data_room_status":    "Open | Not yet open | not_provided"
    }},

    "extraction_confidence": {{
        "financial_data":       0.0,
        "business_description": 0.0,
        "market_data":          0.0,
        "management_data":      0.0,
        "overall":              0.0,
        "notes":                "Any extraction limitations or data quality observations"
    }}
}}

CRITICAL RULES:
- "not_provided" for ANY field not explicitly in the document
- All financials as raw numbers (not formatted strings)
- All rates/margins/percentages as decimals
- Confidence: 1.0 = stated, 0.7 = computed, 0.4 = inferred, 0.0 = absent
- If a range is given, use the midpoint as the value
- Flag revenue/EBITDA unit scale at the top (document_unit field)

CIM DOCUMENT:
{document_text}
"""


# ===========================================================================
# Shared prompts (version-independent)
# ===========================================================================

# Default aliases point to v1 for backwards-compatibility
SYSTEM_PROMPT          = SYSTEM_PROMPT_V1
CIM_EXTRACTION_PROMPT  = CIM_EXTRACTION_PROMPT_V1

MEMO_GENERATION_PROMPT = """Based on the following structured CIM data, generate a professional
investment committee memo.

FORMAT:
1. EXECUTIVE SUMMARY (3-4 sentences: what the company does, why it's interesting, key concern)
2. COMPANY OVERVIEW (business description, market position, competitive advantages)
3. FINANCIAL HIGHLIGHTS (key metrics, trends, quality of earnings observations)
4. GROWTH THESIS (organic + inorganic, with specific evidence from the data)
5. KEY RISKS & MITIGANTS (top 3-5 risks with honest assessment)
6. VALUATION CONTEXT (comparable multiples context if available, or market benchmarks)
7. KEY DILIGENCE QUESTIONS (5-8 critical questions for next phase)
8. RECOMMENDATION (Pursue / Pass / Need More Info — with clear reasoning)

TONE: Direct, analytical, no fluff. Write like a senior associate at a top PE firm.
Be specific with numbers. Flag what's missing.

STRUCTURED CIM DATA:
{extracted_data}
"""

RISK_ANALYSIS_PROMPT = """Analyze the following CIM data for investment risks.

For each risk identified, provide:
- Category (Financial, Operational, Market, Regulatory, Management, Customer, Technology)
- Severity (Critical, High, Medium, Low)
- Description (1-2 sentences)
- Mitigant (if any data suggests a mitigant)
- Diligence question (what to verify)

Also flag any INCONSISTENCIES in the data (e.g., revenue growth claimed vs. actual numbers,
margin trends that don't match the narrative, customer concentration not matching the
diversification claims).

Return as JSON array of risk objects.

CIM DATA:
{extracted_data}
"""

QA_PROMPT = """You are answering questions about a CIM document for a PE analyst.

RULES:
- Answer ONLY based on information in the document
- If the answer is not in the document, say "This information is not provided in the CIM"
- Cite specific data points when possible
- Be concise and direct

DOCUMENT CONTENT:
{document_text}

EXTRACTED DATA:
{extracted_data}

QUESTION: {question}
"""

COMP_BUILDER_PROMPT = """Based on the following company profile extracted from a CIM,
suggest comparable companies and transactions.

For each comparable, provide:
- Company/deal name
- Why it's comparable (business model, size, sector, growth profile)
- Relevant metrics if known (EV/Revenue, EV/EBITDA multiples from public data)
- Key differences from the target

Return 5-8 comparables as a JSON array. Include both:
- Public company comparables (trading comps)
- Precedent transactions (deal comps) if relevant sector M&A is known

Use only REAL companies and real transactions you are confident about.
Flag confidence level for each comparable.

COMPANY PROFILE:
{company_data}
"""


# ===========================================================================
# Prompt Registry
# ===========================================================================

@dataclass
class PromptVersion:
    """A versioned prompt set."""
    version: str
    description: str
    system_prompt: str
    extraction_prompt: str
    created: str                # e.g. "2025-01"
    changelog: str = ""         # What changed vs. prior version


PROMPT_REGISTRY: Dict[str, PromptVersion] = {
    "v1": PromptVersion(
        version="v1",
        description="Original extraction prompt — broad coverage, minimal schema",
        system_prompt=SYSTEM_PROMPT_V1,
        extraction_prompt=CIM_EXTRACTION_PROMPT_V1,
        created="2025-01",
        changelog="Initial production version.",
    ),
    "v2": PromptVersion(
        version="v2",
        description="Enhanced extraction — per-field confidence, unit detection, "
                    "richer financial schema (FCF, addbacks, geo mix, NRR), "
                    "market moat/barrier fields, management bio details",
        system_prompt=SYSTEM_PROMPT_V2,
        extraction_prompt=CIM_EXTRACTION_PROMPT_V2,
        created="2025-06",
        changelog=(
            "Added: schema_version, document_unit, per-field confidence scores, "
            "reporting_period_end, net_debt, FCF, capex_as_pct_revenue, "
            "addback_items, gross_profit, customer churn_rate, sales_cycle_days, "
            "SAM, market_share_estimate, barriers_to_entry, CEO background, "
            "prior employer, equity plan, board composition, pricing_power, "
            "product_roadmap, MA pipeline size, leverage/integration risk, "
            "data_inconsistencies, asking_ev, process_type, LOI deadline."
        ),
    ),
}


class PromptRegistry:
    """Manages versioned prompt sets.

    Usage:
        registry = PromptRegistry()
        v2 = registry.get("v2")
        all_versions = registry.list_versions()
    """

    def get(self, version: str) -> PromptVersion:
        if version not in PROMPT_REGISTRY:
            raise KeyError(
                f"Prompt version '{version}' not found. "
                f"Available: {list(PROMPT_REGISTRY.keys())}"
            )
        return PROMPT_REGISTRY[version]

    def list_versions(self) -> List[str]:
        return list(PROMPT_REGISTRY.keys())

    def describe(self, version: str) -> str:
        pv = self.get(version)
        return (
            f"Version: {pv.version}\n"
            f"Created: {pv.created}\n"
            f"Description: {pv.description}\n"
            f"Changelog: {pv.changelog}"
        )


# ===========================================================================
# Extraction comparison utility
# ===========================================================================

def compare_extractions(
    document_text: str,
    version_a: str,
    version_b: str,
    client,                     # LLMClient instance (or legacy anthropic.Anthropic)
    model: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """Run the same document through two prompt versions and compare outputs.

    Args:
        document_text: Raw CIM text (already parsed from PDF/DOCX).
        version_a:     First prompt version key (e.g. "v1").
        version_b:     Second prompt version key (e.g. "v2").
        client:        Initialized anthropic.Anthropic client.
        model:         Claude model ID.

    Returns:
        Dict with keys:
          - version_a_result:  Extracted dict from version A
          - version_b_result:  Extracted dict from version B
          - field_diff:        Per-field comparison table
          - coverage_a:        % of fields populated in A
          - coverage_b:        % of fields populated in B
          - winner:            Which version extracted more / higher confidence
          - summary:           Human-readable comparison narrative
    """
    registry = PromptRegistry()
    pv_a = registry.get(version_a)
    pv_b = registry.get(version_b)

    def _extract(pv: PromptVersion) -> Dict[str, Any]:
        prompt = pv.extraction_prompt.format(document_text=document_text[:80000])
        # Support both LLMClient and legacy anthropic.Anthropic
        if hasattr(client, "complete"):
            text = client.complete(
                system=pv.system_prompt,
                user=prompt,
                max_tokens=8192,
                temperature=0.0,
            )
        else:
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                temperature=0.0,
                system=pv.system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
        return _parse_json(text)

    result_a = _extract(pv_a)
    result_b = _extract(pv_b)

    field_diff = _diff_extractions(result_a, result_b)
    cov_a      = _coverage(result_a)
    cov_b      = _coverage(result_b)

    winner = version_b if cov_b > cov_a else (version_a if cov_a > cov_b else "tie")

    summary = (
        f"Comparison: {version_a} vs {version_b}\n"
        f"  Coverage — {version_a}: {cov_a:.0%} | {version_b}: {cov_b:.0%}\n"
        f"  Fields only in {version_a}: {field_diff['only_in_a']}\n"
        f"  Fields only in {version_b}: {field_diff['only_in_b']}\n"
        f"  Fields with different values: {field_diff['different_count']}\n"
        f"  Verdict: {winner} extracted more complete data.\n"
    )

    return {
        "version_a":        version_a,
        "version_b":        version_b,
        "version_a_result": result_a,
        "version_b_result": result_b,
        "field_diff":       field_diff,
        "coverage_a":       cov_a,
        "coverage_b":       cov_b,
        "winner":           winner,
        "summary":          summary,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> Dict[str, Any]:
    """Parse JSON from LLM response (handles markdown fences)."""
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    json_str = fence.group(1) if fence else text
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        brace = re.search(r"\{[\s\S]*\}", json_str)
        if brace:
            try:
                return json.loads(brace.group())
            except json.JSONDecodeError:
                pass
    return {}


def _flatten(d: Any, prefix: str = "") -> Dict[str, Any]:
    """Recursively flatten a nested dict into dot-separated keys."""
    items: Dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{prefix}.{k}" if prefix else k
            items.update(_flatten(v, new_key))
    elif isinstance(d, list):
        items[prefix] = json.dumps(d, default=str)
    else:
        items[prefix] = d
    return items


def _coverage(data: Dict[str, Any]) -> float:
    """Fraction of non-null, non-'not_provided' leaf values."""
    flat = _flatten(data)
    if not flat:
        return 0.0
    filled = sum(
        1 for v in flat.values()
        if v is not None and str(v) not in ("not_provided", "", "[]", "{}")
    )
    return filled / len(flat)


def _diff_extractions(
    a: Dict[str, Any],
    b: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare two flattened extractions field by field."""
    flat_a = _flatten(a)
    flat_b = _flatten(b)

    keys_a = set(flat_a.keys())
    keys_b = set(flat_b.keys())

    only_in_a = sorted(keys_a - keys_b)
    only_in_b = sorted(keys_b - keys_a)
    common    = keys_a & keys_b

    different: List[Dict] = []
    same: List[str] = []

    for key in sorted(common):
        va = flat_a[key]
        vb = flat_b[key]
        if str(va) != str(vb):
            different.append({
                "field":     key,
                "value_a":   va,
                "value_b":   vb,
                "a_provided": va not in (None, "not_provided", "", "[]"),
                "b_provided": vb not in (None, "not_provided", "", "[]"),
            })
        else:
            same.append(key)

    return {
        "only_in_a":       only_in_a,
        "only_in_b":       only_in_b,
        "common_fields":   len(common),
        "same_count":      len(same),
        "different_count": len(different),
        "differences":     different,
        "same_fields":     same,
    }
