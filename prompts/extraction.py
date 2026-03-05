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
financial and business data from CIMs and financial filings.

You reason like a senior PE associate — you don't just copy what's on the page.
You derive, infer, and normalise data to give the analyst a complete picture.
You never fabricate data that cannot be supported by the document.

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
        "employee_count": "integer headcount or not_provided",
        "website": "URL or not_provided"
    }},
    "financials": {{
        "currency": "USD | EUR | GBP | etc",
        "revenue": {{
            "ltm":             "Latest twelve months revenue as raw integer or not_provided",
            "ltm_conf":        1.0,
            "ltm_source":      "verbatim quote or formula, e.g. 'FY2023 revenue: $258.5M' or not_provided",
            "prior_year":      "Prior full year revenue as raw integer or not_provided",
            "two_years_ago":   "Revenue from 2 years ago as raw integer or not_provided",
            "cagr_3yr":        "3-year revenue CAGR as decimal (0.15 = 15%) or not_provided",
            "cagr_3yr_conf":   1.0,
            "cagr_3yr_source": "verbatim quote or calculation or not_provided",
            "history": [
                {{"period": "e.g. FY2021 or LTM Sep-2024", "value": "raw integer", "yoy_growth": "decimal or not_provided"}}
            ],
            "international_pct": "share of revenue from non-domestic markets as decimal or not_provided"
        }},
        "ebitda": {{
            "ltm":                 "LTM EBITDA as raw integer or not_provided",
            "ltm_conf":            1.0,
            "ltm_source":          "verbatim quote or formula or not_provided",
            "margin_ltm":          "EBITDA margin as decimal or not_provided",
            "adjusted_ebitda_ltm": "Adjusted EBITDA as raw integer if provided or not_provided",
            "derived_ebitda":      "EBITDA derived from revenue × margin if not directly stated, else not_provided"
        }},
        "gross_margin":          "as decimal or not_provided",
        "gross_margin_conf":     1.0,
        "gross_margin_source":   "verbatim quote or formula or not_provided",
        "net_income":            "LTM net income as raw integer or not_provided",
        "net_income_conf":       1.0,
        "net_income_source":     "verbatim quote or not_provided",
        "capex":                 "Annual capex as raw integer or not_provided",
        "free_cash_flow":        "LTM FCF (net income + D&A − capex) as raw integer or not_provided",
        "free_cash_flow_conf":   1.0,
        "free_cash_flow_source": "verbatim quote or derivation formula or not_provided",
        "debt":                  "Total debt as raw integer or not_provided",
        "cash":                  "Cash and equivalents as raw integer or not_provided",
        "recurring_revenue_pct": "% of revenue that is recurring as decimal or not_provided",
        "revenue_by_segment": [
            {{"segment": "name", "revenue": "raw integer", "pct_of_total": "decimal"}}
        ]
    }},
    "customers": {{
        "total_customers": "number or range or not_provided",
        "top_customer_concentration": "% of revenue from top customer as decimal or not_provided",
        "top_10_concentration": "% from top 10 customers as decimal or not_provided",
        "customer_retention": "annual retention rate as decimal or not_provided",
        "net_revenue_retention": "NRR as decimal or not_provided",
        "avg_contract_value": "ACV as raw integer or not_provided",
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
        "management_ownership": "% owned by management as decimal or not_provided"
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
        "financial_data": 0.0,
        "business_description": 0.0,
        "market_data": 0.0,
        "overall": 0.0
    }}
}}

ANALYST PRINCIPLES:

1. DERIVATION — Never return not_provided for a field that can be computed from numbers
   explicitly in the document. Priority derivation rules (apply in order):
   a. LTM period: most recent annual period = LTM for 10-K / annual reports.
   b. gross_margin: if the income statement shows both Revenue and "Gross profit" lines,
      compute gross_margin = gross_profit / revenue (set _conf = 0.7, _source = formula).
   c. ebitda.ltm: if EBITDA is not stated, compute as operating_income + D&A where D&A is
      visible in the income statement or cash flow statement (set _conf = 0.7).
   d. ebitda.derived_ebitda: fallback when ebitda.ltm is still absent — use revenue × margin
      or operating_income + any D&A figure available (set _conf = 0.7).
   e. cagr_3yr: if revenue.history has ≥3 periods, compute as (latest/earliest)^(1/(n-1)) − 1.

2. NORMALIZATION — Return ALL monetary values as raw integers. Rates, margins, and percentages
   as decimals (15% = 0.15). Detect the document's unit scale (thousands/millions/billions) and
   multiply through to raw USD. Never use abbreviations (k, m, b) in numeric fields.

3. COMPLETENESS — Map document terminology to schema fields correctly:
   "FY revenue" → revenue.ltm | "annual EBITDA" → ebitda.ltm | "net sales" → revenue.ltm
   "Gross profit" line → compute gross_margin | "Cost of revenue" → cost of goods sold
   For 10-K and annual reports, the most recent fiscal year figures ARE the LTM figures.

   EBITDA VARIANT MAPPING — all of the following label types map to ebitda.ltm (or
   ebitda.adjusted_ebitda_ltm when the label says "adjusted/normalized"):
     "Normalized EBITDA", "Adjusted EBITDA", "Pro Forma EBITDA", "EBITDA (Normalized)",
     "EBITDA (Adjusted)", "EBITDA (Pro Forma)", "Recurring EBITDA", "Run-Rate EBITDA",
     "EBITDA — Adjusted", "Adj. EBITDA". When the document presents ONLY a normalized/
     adjusted figure (no clean stated EBITDA), use it for ebitda.adjusted_ebitda_ltm and
     also copy the value to ebitda.ltm (set ltm_conf = 0.9, ltm_source = "Normalized EBITDA
     used as proxy").

   CURRENCY DETECTION — read the document for explicit currency statements (e.g.
   "All figures in Canadian dollars", "amounts in thousands of GBP", "€ millions") and
   set financials.currency accordingly (e.g. "CAD", "GBP", "EUR"). Default to "USD" only
   when no currency is mentioned and the document is clearly US-based.

   REVENUE LTM PROXY — when no historical LTM or most-recent-year revenue is available
   (e.g. forecast-only CIMs, receivership packages with only projected figures), use the
   most recent stated figure (trailing average, last reported actual, or nearest forecast
   year) as a proxy: set revenue.ltm to that value, revenue.ltm_conf = 0.5, and
   revenue.ltm_source = "No LTM stated; [trailing avg / FY20XX actual / FY20XX forecast]
   used as proxy."

   Fill every field you can support with document data — use not_provided only as a last resort.

4. INFERENCE — When a value is not stated but can be computed from other extracted figures
   (e.g. gross_margin = gross_profit / revenue), compute it and set _conf = 0.7.
   When a value is plausible from context but not directly calculable, set _conf = 0.4.
   When directly and explicitly stated in the document, set _conf = 1.0.

5. CONFIDENCE SCORING — For every numeric field that has _conf / _source companions, populate them:
   _conf: 1.0 = explicitly stated | 0.7 = derived from stated figures | 0.4 = inferred from context | 0.0 = absent
   _source: brief verbatim quote (for 1.0), calculation string (for 0.7), or reasoning (for 0.4)
   Example: ltm_conf = 0.7, ltm_source = "prior_year $240M × (1 + cagr 0.077) = $258.5M"

6. SCHEMA ADDITIONS — Populate the new fields when the document supports it:
   revenue.history — year-by-year revenue list (as many periods as the document provides)
   free_cash_flow — PREFERRED METHOD: Net Cash from Operating Activities (OCF) MINUS
      Capital Expenditures, both sourced from the cash flow statement. This is the
      standard PE definition of unlevered FCF. Set conf = 1.0 if both OCF and CapEx
      are explicitly stated. FALLBACK only if no cash flow statement is available:
      net_income + D&A − capex. Never guess FCF — leave not_provided if no cash flow
      statement data is present.
   ebitda.derived_ebitda — compute as operating_income + D&A (preferred) or revenue × margin
   employee_count — extract from "X employees" mentions as an integer
   revenue.international_pct — share of revenue from non-domestic markets

CIM DOCUMENT:
{document_text}
"""


# ===========================================================================
# V2 — Enhanced prompts: better table parsing, explicit unit detection,
#       per-field confidence, and richer qualitative sections
# ===========================================================================

SYSTEM_PROMPT_V2 = """You are a senior private equity analyst and financial data specialist.
You extract structured, machine-readable data from Confidential Information Memorandums (CIMs)
and SEC filings with surgical precision.

Core principles:
1. EXTRACT EVERYTHING — financial numeric fields (revenue, EBITDA, gross margin, net income,
   capex, debt) are REQUIRED. Populate every field you can support with document data.
   Use "not_provided" ONLY as a last resort when data is genuinely absent from the document.
   Never treat different labeling (FY vs LTM, Annual vs Trailing Twelve Months) as missing data —
   map them to the correct schema field.
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
- Use "not_provided" ONLY when data is truly absent from the document. Never use it just
  because the document label differs from the schema field name. Map terminology correctly:
  "FY revenue" → revenue.ltm | "annual EBITDA" → ebitda.ltm | "net sales" → revenue.ltm
  For 10-K and annual reports, the most recent fiscal year figures ARE the LTM figures.

- EBITDA VARIANT MAPPING — all of the following map to ebitda.ltm (or adjusted_ebitda_ltm
  when the label says "adjusted/normalized"):
  "Normalized EBITDA", "Adjusted EBITDA", "Pro Forma EBITDA", "EBITDA (Normalized)",
  "EBITDA (Adjusted)", "EBITDA (Pro Forma)", "Recurring EBITDA", "Run-Rate EBITDA",
  "Adj. EBITDA". When the document presents ONLY a normalized/adjusted figure, copy the
  value to both ebitda.adjusted_ebitda_ltm AND ebitda.ltm (ltm_conf = 0.9,
  ltm_source = "Normalized EBITDA used as proxy").

- CURRENCY DETECTION — read the document for explicit currency statements (e.g. "All
  figures in Canadian dollars", "amounts in thousands of GBP"). Set financials.currency
  to the detected code (e.g. "CAD", "GBP", "EUR"). Default "USD" only when the document
  is clearly US-based and no currency is stated.

- REVENUE LTM PROXY — when no historical LTM or most-recent-year revenue is available
  (forecast-only CIMs, receivership packages with only projected figures), use the most
  recent stated figure (trailing average, last reported actual, or nearest forecast year)
  as proxy: set revenue.ltm to that value, revenue.ltm_conf = 0.5, and revenue.ltm_source
  = "No LTM stated; [trailing avg / FY20XX actual / FY20XX forecast] used as proxy."

- MONETARY VALUES: Return ALL monetary values as raw integers (no $, no commas, no suffixes).
  Normalise from whatever unit the document uses — multiply through to raw USD.
  Examples: "$628 thousand" → 628000 | "$258.5 million" → 258500000 | "$1.2 billion" → 1200000000
  Never use abbreviations like "k", "m", or "b" in numeric fields.
- All rates/margins/percentages as decimals
- Confidence: 1.0 = stated, 0.7 = computed, 0.4 = inferred, 0.0 = absent
- If a range is given, use the midpoint as the value
- Flag revenue/EBITDA unit scale at the top (document_unit field)

CIM DOCUMENT:
{document_text}
"""

CIM_EXTRACTION_PROMPT_V2_CITATIONS = CIM_EXTRACTION_PROMPT_V2 + """

ADDITIONAL REQUIREMENT: SOURCE CITATIONS

PRIORITY ORDER — citations are ADDITIVE and must never degrade core extraction:

STEP 1 — EXTRACT ALL VALUES FIRST.
You MUST fill ALL financial fields before adding any citation objects.
Revenue LTM, EBITDA LTM, gross margin, net income, CAGR, and all other numeric fields
are REQUIRED and take ABSOLUTE PRIORITY over citation completeness.

STEP 2 — ANNUAL FIGURES ARE LTM.
For 10-K filings and annual reports, fiscal year figures ARE the LTM figures.
If the document states "FY2020 revenue: $258.5M", set revenue.ltm = 258500000 and
revenue.ltm_period = "FY2020". Never return not_provided for revenue or EBITDA when
annual figures exist in the document.

STEP 3 — ADD CITATIONS AFTER EXTRACTING.
After all values are filled, add citation objects for the 8 required fields below.
Citations are SECONDARY — they must NEVER cause a field to be left as not_provided.
If you extracted a value but cannot find a clean source quote, keep the extracted value
and set its citation field to "not_provided". A missing citation never justifies a
missing value.

Citation schema (additive — do not remove or modify existing extracted fields):
{{
  "page": int,
  "section": "string",
  "snippet": "verbatim text from source (one sentence maximum)"
}}

Required citation fields (add these alongside existing fields, do not replace them):
- financials.revenue.ltm_citation
- financials.ebitda.ltm_citation
- financials.ebitda.adjusted_ebitda_ltm_citation
- financials.revenue.cagr_3yr_citation
- financials.gross_margin_citation
- financials.ebitda.margin_ltm_citation
- customers.top_customer_concentration_citation
- financials.capex_citation

If a cited metric is genuinely not_provided after exhaustive search, set its citation
field to "not_provided" as well.

Citation rules:
- Use the closest explicit source in document text or financial table content.
- Keep snippet verbatim and concise (one sentence, no paraphrasing).
- Prefer table metadata provided in the prompt (table page + section heading) when available.
- Do not fabricate snippets — if no verbatim source exists, use "not_provided".
"""


# ===========================================================================
# Shared prompts (version-independent)
# ===========================================================================

# Default aliases point to v1 for backwards-compatibility
SYSTEM_PROMPT          = SYSTEM_PROMPT_V1
CIM_EXTRACTION_PROMPT  = CIM_EXTRACTION_PROMPT_V1

MEMO_GENERATION_PROMPT = """Generate a professional investment committee memo from the structured data.

Return output in THIS EXACT JSON SHAPE:
{{
  "title": "string",
  "date": "string",
  "prepared_by": "string",
  "sections": [
    {{
      "heading": "string",
      "content": "string"
    }}
  ]
}}

Schema rules:
- Top-level keys MUST be exactly: title, date, prepared_by, sections.
- sections MUST be an array of objects, each with heading and content as strings.
- content must be plain text only, using \\n for line breaks and * for bullet points.
- Do not put nested JSON objects, arrays, or sub-dicts inside content fields.
- Use concise, analytical PE memo language grounded in the extracted data.

Standard section set (include the ones supported by available data; omit weak/unsupported sections):
- Executive Summary
- Company Overview
- Financial Highlights
- Growth Thesis
- Key Risks & Mitigants
- Valuation Context
- Key Diligence Questions
- Recommendation

CRITICAL OUTPUT INSTRUCTION:
Return ONLY valid JSON.
Do not wrap in a "memo" key.
Do not nest objects inside content fields.

STRUCTURED DATA:
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
    "v2_citations": PromptVersion(
        version="v2_citations",
        description="V2 extraction with additive citation objects on key financial metrics",
        system_prompt=SYSTEM_PROMPT_V2,
        extraction_prompt=CIM_EXTRACTION_PROMPT_V2_CITATIONS,
        created="2026-03",
        changelog=(
            "Adds citation object fields for key financial metrics "
            "(revenue, EBITDA, adjusted EBITDA, revenue growth, gross margin, "
            "EBITDA margin, customer concentration, capex) without replacing "
            "existing V2 fields."
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
