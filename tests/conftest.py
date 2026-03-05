"""Shared pytest fixtures for Meridian AI test suite."""

import pytest


# ---------------------------------------------------------------------------
# Complete extracted_data fixture — all fields populated with clean values
# ---------------------------------------------------------------------------

@pytest.fixture
def complete_data():
    """Fully-populated extracted_data dict. All core fields present and valid."""
    return {
        "company": {
            "name": "Acme Corp",
            "sector": "SaaS",
            "description": "B2B SaaS platform for supply chain management",
        },
        "financials": {
            "revenue": {
                "ltm": 10_000_000,
                "cagr_3yr": 0.18,
            },
            "ebitda": {
                "ltm": 2_500_000,
                "adjusted_ebitda_ltm": 2_700_000,
                "margin_ltm": 0.25,
            },
            "gross_margin": 0.72,
            "recurring_revenue_pct": 0.85,
            "net_income": 1_200_000,
        },
        "customers": {
            "top_customer_concentration": 0.15,
            "top_10_concentration": 0.50,
            "customer_retention": 0.92,
            "total_customers": 120,
        },
        "management": {
            "ceo_tenure_years": 7,
            "key_executives": [
                {"name": "Jane Doe", "title": "CEO"},
                {"name": "John Smith", "title": "CFO"},
                {"name": "Alice Lee", "title": "CTO"},
                {"name": "Bob Chen", "title": "COO"},
            ],
            "management_ownership": 0.12,
        },
        "market": {
            "tam": "5000000000",
            "market_growth_rate": 0.12,
            "competitive_position": "strong",
        },
        "growth_thesis": {
            "organic_levers": ["upsell", "geographic expansion", "new verticals", "channel partners"],
            "ma_opportunity": "Fragmented market with multiple bolt-on targets",
        },
        "risk_factors": {
            "customer_concentration_risk": "low",
            "key_person_dependency": "low",
            "regulatory_risk": "low",
            "market_cyclicality": "low",
            "technology_risk": "low",
            "identified_risks": ["competition", "macro"],
        },
    }


# ---------------------------------------------------------------------------
# Sparse data fixture — most financial fields missing
# ---------------------------------------------------------------------------

@pytest.fixture
def sparse_data():
    """Mostly-empty extracted_data. Simulates a thin CIM with minimal financials."""
    return {
        "company": {"name": "Sparse Co", "sector": "Unknown"},
        "financials": {
            "revenue": {"ltm": "not_provided", "cagr_3yr": "not_provided"},
            "ebitda": {
                "ltm": "not_provided",
                "adjusted_ebitda_ltm": "not_provided",
                "margin_ltm": "not_provided",
            },
            "gross_margin": "not_provided",
            "recurring_revenue_pct": "not_provided",
            "net_income": "not_provided",
        },
        "customers": {
            "top_customer_concentration": "not_provided",
            "top_10_concentration": "not_provided",
            "customer_retention": "not_provided",
        },
        "management": {
            "ceo_tenure_years": "not_provided",
            "key_executives": [],
            "management_ownership": "not_provided",
        },
        "market": {
            "tam": "not_provided",
            "market_growth_rate": "not_provided",
            "competitive_position": "",
        },
        "growth_thesis": {
            "organic_levers": [],
            "ma_opportunity": "not_provided",
        },
        "risk_factors": {},
    }


# ---------------------------------------------------------------------------
# High-risk data fixture — all heuristics should fire
# ---------------------------------------------------------------------------

@pytest.fixture
def high_risk_data():
    """Data engineered to trigger every heuristic risk flag."""
    return {
        "company": {"name": "Risky Inc", "sector": "Services"},
        "financials": {
            "revenue": {
                "ltm": 5_000_000,
                "cagr_3yr": 0.60,   # 10× market growth → growth sustainability flag
            },
            "ebitda": {
                "ltm": 400_000,
                "adjusted_ebitda_ltm": 800_000,  # 100% gap → large adjustments flag
                "margin_ltm": 0.08,              # < 10% → low margin flag
            },
            "gross_margin": 0.40,
            "recurring_revenue_pct": 0.30,       # < 50% → low recurring flag
            "net_income": -200_000,
        },
        "customers": {
            "top_customer_concentration": 0.55,  # > 40% → Critical
            "top_10_concentration": 0.80,        # > 75% → High
            "customer_retention": 0.70,          # < 75% → High
        },
        "management": {
            "ceo_tenure_years": 1,               # < 2 → new CEO flag
            "key_executives": [
                {"name": "Jim Ray", "title": "CEO"},
            ],                                   # < 3 → thin bench flag
            "management_ownership": 0.01,
        },
        "market": {
            "tam": "50000000000",
            "market_growth_rate": 0.06,          # 0.60 CAGR is 10× this
            "competitive_position": "challenger",
        },
        "growth_thesis": {
            "organic_levers": ["upsell"],
            "ma_opportunity": "not_provided",
        },
        "risk_factors": {
            "customer_concentration_risk": "high",
            "key_person_dependency": "high",
            "regulatory_risk": "critical",
            "market_cyclicality": "high",
            "technology_risk": "high",
            "identified_risks": list(range(8)),  # > 5 → extra deduction
        },
    }


# ---------------------------------------------------------------------------
# Edge-case helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_data():
    """Completely empty dict — no keys at all."""
    return {}


@pytest.fixture
def none_values_data():
    """Dict with None values instead of 'not_provided' strings."""
    return {
        "financials": {
            "revenue": {"ltm": None, "cagr_3yr": None},
            "ebitda": {"ltm": None, "adjusted_ebitda_ltm": None, "margin_ltm": None},
            "gross_margin": None,
            "recurring_revenue_pct": None,
            "net_income": None,
        },
        "customers": {
            "top_customer_concentration": None,
            "top_10_concentration": None,
            "customer_retention": None,
        },
        "management": {
            "ceo_tenure_years": None,
            "key_executives": [],
            "management_ownership": None,
        },
        "market": {"tam": None, "market_growth_rate": None, "competitive_position": ""},
        "growth_thesis": {"organic_levers": [], "ma_opportunity": None},
        "risk_factors": {},
    }
