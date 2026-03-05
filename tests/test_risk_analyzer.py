"""Tests for RiskAnalyzer heuristic checks.

Tests cover only deterministic (non-LLM) methods:
  - _check_customer_concentration
  - _check_financial_quality
  - _check_management_risk
  - _check_growth_sustainability

LLM methods are not tested here (require live API key).
"""

import pytest
from unittest.mock import patch, MagicMock

from core.risk_analyzer import RiskAnalyzer, RiskFlag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_analyzer():
    """Return a RiskAnalyzer with a mocked LLM client (no API calls)."""
    analyzer = RiskAnalyzer.__new__(RiskAnalyzer)
    analyzer.client = MagicMock()
    return analyzer


def flags_by_title(flags, keyword):
    """Return flags whose title contains keyword (case-insensitive)."""
    return [f for f in flags if keyword.lower() in f.title.lower()]


# ---------------------------------------------------------------------------
# _check_customer_concentration
# ---------------------------------------------------------------------------

class TestCustomerConcentration:

    def test_top_customer_above_40_is_critical(self):
        analyzer = make_analyzer()
        data = {"customers": {"top_customer_concentration": 0.55}}
        flags = analyzer._check_customer_concentration(data)
        concentration_flags = flags_by_title(flags, "concentration")
        assert any(f.severity == "Critical" for f in concentration_flags), \
            "Expected Critical flag for top customer > 40%"

    def test_top_customer_between_25_and_40_is_high(self):
        analyzer = make_analyzer()
        data = {"customers": {"top_customer_concentration": 0.30}}
        flags = analyzer._check_customer_concentration(data)
        concentration_flags = flags_by_title(flags, "concentration")
        assert any(f.severity == "High" for f in concentration_flags), \
            "Expected High flag for top customer between 25–40%"

    def test_top_customer_below_25_no_flag(self):
        analyzer = make_analyzer()
        data = {"customers": {"top_customer_concentration": 0.20}}
        flags = analyzer._check_customer_concentration(data)
        concentration_flags = flags_by_title(flags, "High customer concentration")
        assert len(concentration_flags) == 0, \
            "No flag expected for top customer below 25%"

    def test_top_customer_not_provided_no_flag(self):
        analyzer = make_analyzer()
        data = {"customers": {"top_customer_concentration": "not_provided"}}
        flags = analyzer._check_customer_concentration(data)
        assert len(flags) == 0

    def test_top_10_above_75_is_high(self):
        analyzer = make_analyzer()
        data = {"customers": {"top_10_concentration": 0.80}}
        flags = analyzer._check_customer_concentration(data)
        t10_flags = flags_by_title(flags, "Top 10")
        assert any(f.severity == "High" for f in t10_flags)

    def test_top_10_between_60_and_75_is_medium(self):
        analyzer = make_analyzer()
        data = {"customers": {"top_10_concentration": 0.65}}
        flags = analyzer._check_customer_concentration(data)
        t10_flags = flags_by_title(flags, "Top 10")
        assert any(f.severity == "Medium" for f in t10_flags)

    def test_top_10_below_60_no_flag(self):
        analyzer = make_analyzer()
        data = {"customers": {"top_10_concentration": 0.55}}
        flags = analyzer._check_customer_concentration(data)
        t10_flags = flags_by_title(flags, "Top 10")
        assert len(t10_flags) == 0

    def test_low_retention_below_75_is_high(self):
        analyzer = make_analyzer()
        data = {"customers": {"customer_retention": 0.70}}
        flags = analyzer._check_customer_concentration(data)
        retention_flags = flags_by_title(flags, "retention")
        assert any(f.severity == "High" for f in retention_flags)

    def test_low_retention_between_75_and_85_is_medium(self):
        analyzer = make_analyzer()
        data = {"customers": {"customer_retention": 0.80}}
        flags = analyzer._check_customer_concentration(data)
        retention_flags = flags_by_title(flags, "retention")
        assert any(f.severity == "Medium" for f in retention_flags)

    def test_retention_above_85_no_flag(self):
        analyzer = make_analyzer()
        data = {"customers": {"customer_retention": 0.90}}
        flags = analyzer._check_customer_concentration(data)
        retention_flags = flags_by_title(flags, "retention")
        assert len(retention_flags) == 0

    def test_empty_customers_dict_no_crash(self):
        analyzer = make_analyzer()
        flags = analyzer._check_customer_concentration({})
        assert isinstance(flags, list)

    def test_all_flags_are_riskflag_instances(self, high_risk_data):
        analyzer = make_analyzer()
        flags = analyzer._check_customer_concentration(high_risk_data)
        for f in flags:
            assert isinstance(f, RiskFlag)

    def test_all_flags_have_diligence_question(self, high_risk_data):
        analyzer = make_analyzer()
        flags = analyzer._check_customer_concentration(high_risk_data)
        for f in flags:
            assert f.diligence_question, f"Missing diligence question on: {f.title}"


# ---------------------------------------------------------------------------
# _check_financial_quality
# ---------------------------------------------------------------------------

class TestFinancialQuality:

    def test_low_ebitda_margin_flagged(self):
        analyzer = make_analyzer()
        data = {"financials": {"ebitda": {"margin_ltm": 0.07}}}
        flags = analyzer._check_financial_quality(data)
        margin_flags = flags_by_title(flags, "margin")
        assert len(margin_flags) > 0

    def test_ebitda_margin_above_10_no_flag(self):
        analyzer = make_analyzer()
        data = {"financials": {"ebitda": {"margin_ltm": 0.20}}}
        flags = analyzer._check_financial_quality(data)
        margin_flags = flags_by_title(flags, "margin")
        assert len(margin_flags) == 0

    def test_large_ebitda_adjustment_flagged(self):
        """Adjusted EBITDA > 30% above reported should flag."""
        analyzer = make_analyzer()
        data = {
            "financials": {
                "ebitda": {
                    "ltm": 1_000_000,
                    "adjusted_ebitda_ltm": 1_400_000,  # 40% gap
                }
            }
        }
        flags = analyzer._check_financial_quality(data)
        adj_flags = flags_by_title(flags, "adjustment")
        assert len(adj_flags) > 0

    def test_small_ebitda_adjustment_not_flagged(self):
        """Adjusted EBITDA < 30% above reported — no flag."""
        analyzer = make_analyzer()
        data = {
            "financials": {
                "ebitda": {
                    "ltm": 1_000_000,
                    "adjusted_ebitda_ltm": 1_200_000,  # 20% gap
                }
            }
        }
        flags = analyzer._check_financial_quality(data)
        adj_flags = flags_by_title(flags, "adjustment")
        assert len(adj_flags) == 0

    def test_zero_reported_ebitda_no_crash(self):
        """Division-by-zero guard: reported EBITDA of 0."""
        analyzer = make_analyzer()
        data = {
            "financials": {
                "ebitda": {"ltm": 0, "adjusted_ebitda_ltm": 500_000}
            }
        }
        flags = analyzer._check_financial_quality(data)
        assert isinstance(flags, list)

    def test_low_recurring_revenue_flagged(self):
        analyzer = make_analyzer()
        data = {"financials": {"ebitda": {}, "recurring_revenue_pct": 0.35}}
        flags = analyzer._check_financial_quality(data)
        recurring_flags = flags_by_title(flags, "recurring")
        assert len(recurring_flags) > 0

    def test_high_recurring_revenue_no_flag(self):
        analyzer = make_analyzer()
        data = {"financials": {"ebitda": {}, "recurring_revenue_pct": 0.85}}
        flags = analyzer._check_financial_quality(data)
        recurring_flags = flags_by_title(flags, "recurring")
        assert len(recurring_flags) == 0

    def test_not_provided_fields_no_crash(self):
        analyzer = make_analyzer()
        data = {
            "financials": {
                "ebitda": {
                    "margin_ltm": "not_provided",
                    "ltm": "not_provided",
                    "adjusted_ebitda_ltm": "not_provided",
                },
                "recurring_revenue_pct": "not_provided",
            }
        }
        flags = analyzer._check_financial_quality(data)
        assert isinstance(flags, list)
        assert len(flags) == 0

    def test_invalid_string_values_no_crash(self):
        """Non-numeric strings in numeric fields shouldn't raise."""
        analyzer = make_analyzer()
        data = {
            "financials": {
                "ebitda": {"margin_ltm": "N/A", "ltm": "TBD", "adjusted_ebitda_ltm": "TBD"},
                "recurring_revenue_pct": "high",
            }
        }
        flags = analyzer._check_financial_quality(data)
        assert isinstance(flags, list)


# ---------------------------------------------------------------------------
# _check_management_risk
# ---------------------------------------------------------------------------

class TestManagementRisk:

    def test_new_ceo_flagged(self):
        analyzer = make_analyzer()
        data = {"management": {"ceo_tenure_years": 1, "key_executives": []}}
        flags = analyzer._check_management_risk(data)
        ceo_flags = flags_by_title(flags, "CEO")
        assert len(ceo_flags) > 0

    def test_ceo_tenure_exactly_2_not_flagged(self):
        """Boundary: 2 years is NOT new CEO (< 2 triggers)."""
        analyzer = make_analyzer()
        data = {"management": {"ceo_tenure_years": 2, "key_executives": []}}
        flags = analyzer._check_management_risk(data)
        ceo_flags = flags_by_title(flags, "New CEO")
        assert len(ceo_flags) == 0

    def test_experienced_ceo_not_flagged(self):
        analyzer = make_analyzer()
        data = {"management": {"ceo_tenure_years": 8, "key_executives": []}}
        flags = analyzer._check_management_risk(data)
        ceo_flags = flags_by_title(flags, "New CEO")
        assert len(ceo_flags) == 0

    def test_thin_bench_flagged_when_fewer_than_3(self):
        analyzer = make_analyzer()
        data = {
            "management": {
                "ceo_tenure_years": "not_provided",
                "key_executives": [{"name": "A", "title": "CEO"}, {"name": "B", "title": "CFO"}],
            }
        }
        flags = analyzer._check_management_risk(data)
        bench_flags = flags_by_title(flags, "bench")
        assert len(bench_flags) > 0

    def test_adequate_bench_not_flagged(self):
        """3+ execs → no thin bench flag."""
        analyzer = make_analyzer()
        data = {
            "management": {
                "ceo_tenure_years": "not_provided",
                "key_executives": [
                    {"name": "A"}, {"name": "B"}, {"name": "C"},
                ],
            }
        }
        flags = analyzer._check_management_risk(data)
        bench_flags = flags_by_title(flags, "bench")
        assert len(bench_flags) == 0

    def test_empty_management_dict_no_crash(self):
        analyzer = make_analyzer()
        flags = analyzer._check_management_risk({})
        assert isinstance(flags, list)

    def test_invalid_tenure_type_no_crash(self):
        """Non-numeric tenure value should be silently ignored."""
        analyzer = make_analyzer()
        data = {"management": {"ceo_tenure_years": "five years", "key_executives": []}}
        flags = analyzer._check_management_risk(data)
        assert isinstance(flags, list)


# ---------------------------------------------------------------------------
# _check_growth_sustainability
# ---------------------------------------------------------------------------

class TestGrowthSustainability:

    def test_growth_outpacing_market_3x_flagged(self):
        """Company CAGR > 3× market rate → flag."""
        analyzer = make_analyzer()
        data = {
            "financials": {"revenue": {"cagr_3yr": 0.45}},
            "market": {"market_growth_rate": 0.10},
        }
        flags = analyzer._check_growth_sustainability(data)
        assert len(flags) > 0

    def test_growth_exactly_3x_not_flagged(self):
        """Boundary: exactly 3× should NOT flag (> 3× required)."""
        analyzer = make_analyzer()
        data = {
            "financials": {"revenue": {"cagr_3yr": 0.30}},
            "market": {"market_growth_rate": 0.10},
        }
        flags = analyzer._check_growth_sustainability(data)
        assert len(flags) == 0

    def test_growth_below_3x_no_flag(self):
        analyzer = make_analyzer()
        data = {
            "financials": {"revenue": {"cagr_3yr": 0.20}},
            "market": {"market_growth_rate": 0.10},
        }
        flags = analyzer._check_growth_sustainability(data)
        assert len(flags) == 0

    def test_zero_market_growth_no_crash(self):
        """Division-by-zero guard: market growth rate of 0."""
        analyzer = make_analyzer()
        data = {
            "financials": {"revenue": {"cagr_3yr": 0.30}},
            "market": {"market_growth_rate": 0},
        }
        flags = analyzer._check_growth_sustainability(data)
        assert isinstance(flags, list)

    def test_missing_market_data_no_flag(self):
        """If either CAGR or market growth is missing, no flag raised."""
        analyzer = make_analyzer()
        data = {
            "financials": {"revenue": {"cagr_3yr": 0.50}},
            "market": {"market_growth_rate": "not_provided"},
        }
        flags = analyzer._check_growth_sustainability(data)
        assert len(flags) == 0

    def test_both_missing_no_crash(self):
        analyzer = make_analyzer()
        flags = analyzer._check_growth_sustainability({})
        assert isinstance(flags, list)
        assert len(flags) == 0


# ---------------------------------------------------------------------------
# Full heuristic stack on high_risk_data
# ---------------------------------------------------------------------------

class TestFullHeuristicStack:

    def test_high_risk_data_produces_multiple_flags(self, high_risk_data):
        analyzer = make_analyzer()
        # Run all 4 heuristics
        flags = []
        flags += analyzer._check_customer_concentration(high_risk_data)
        flags += analyzer._check_financial_quality(high_risk_data)
        flags += analyzer._check_management_risk(high_risk_data)
        flags += analyzer._check_growth_sustainability(high_risk_data)
        assert len(flags) >= 6, f"Expected ≥6 flags, got {len(flags)}: {[f.title for f in flags]}"

    def test_all_severities_are_valid(self, high_risk_data):
        analyzer = make_analyzer()
        flags = []
        flags += analyzer._check_customer_concentration(high_risk_data)
        flags += analyzer._check_financial_quality(high_risk_data)
        flags += analyzer._check_management_risk(high_risk_data)
        flags += analyzer._check_growth_sustainability(high_risk_data)
        valid_severities = {"Critical", "High", "Medium", "Low"}
        for f in flags:
            assert f.severity in valid_severities, f"Invalid severity: {f.severity}"

    def test_clean_data_produces_no_heuristic_flags(self, complete_data):
        """Complete, healthy data should produce zero heuristic flags."""
        analyzer = make_analyzer()
        flags = []
        flags += analyzer._check_customer_concentration(complete_data)
        flags += analyzer._check_financial_quality(complete_data)
        flags += analyzer._check_management_risk(complete_data)
        flags += analyzer._check_growth_sustainability(complete_data)
        assert len(flags) == 0, \
            f"Expected 0 heuristic flags on clean data, got: {[f.title for f in flags]}"

    def test_sparse_data_produces_minimal_flags(self, sparse_data):
        """Sparse ('not_provided') data → at most 1 flag.

        The only heuristic that fires on empty-but-structured data is the
        thin management bench check (empty key_executives list is a real
        data point — the field IS present, just empty). All numeric checks
        require actual values and are silent when data is 'not_provided'.
        """
        analyzer = make_analyzer()
        flags = []
        flags += analyzer._check_customer_concentration(sparse_data)
        flags += analyzer._check_financial_quality(sparse_data)
        flags += analyzer._check_management_risk(sparse_data)
        flags += analyzer._check_growth_sustainability(sparse_data)
        # Only "Thin management bench" may fire (empty list counts as observable data)
        non_bench = [f for f in flags if "bench" not in f.title.lower()]
        assert len(non_bench) == 0, \
            f"Unexpected flags on sparse data: {[f.title for f in non_bench]}"
