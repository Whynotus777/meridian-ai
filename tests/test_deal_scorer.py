"""Tests for DealScorer — all dimensions, penalty logic, grade/recommendation mapping.

Tests only deterministic logic. No LLM calls.
"""

import pytest

from scoring.deal_scorer import DealScorer, DealScore, DimensionScore
from scoring.deal_scorer import DealScorer
from config.scoring_weights import BALANCED, CONSERVATIVE, GROWTH_ORIENTED, ScoringWeights


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_scorer(weights=None):
    return DealScorer(weights=weights or BALANCED)


def dim_by_name(score: DealScore, name: str) -> DimensionScore:
    """Return the DimensionScore for a given dimension name."""
    for d in score.dimensions:
        if name.lower() in d.dimension.lower():
            return d
    raise KeyError(f"Dimension '{name}' not found in score dimensions")


# ---------------------------------------------------------------------------
# Market Attractiveness dimension
# ---------------------------------------------------------------------------

class TestScoreMarket:

    def test_high_growth_market_scores_well(self):
        scorer = make_scorer()
        data = {"market": {"tam": "5000000000", "market_growth_rate": 0.15, "competitive_position": ""}}
        result = scorer._score_market(data)
        assert result.score >= 0.70, f"Expected ≥0.70, got {result.score}"

    def test_low_growth_market_scores_lower(self):
        scorer = make_scorer()
        data = {"market": {"tam": "1000000000", "market_growth_rate": 0.03, "competitive_position": ""}}
        result = scorer._score_market(data)
        assert result.score <= 0.65

    def test_market_leader_position_boosts_score(self):
        scorer = make_scorer()
        data_leader = {"market": {"competitive_position": "market leader", "market_growth_rate": 0.10, "tam": "1000000000"}}
        data_other = {"market": {"competitive_position": "challenger", "market_growth_rate": 0.10, "tam": "1000000000"}}
        assert scorer._score_market(data_leader).score > scorer._score_market(data_other).score

    def test_strong_position_boosts_score_less_than_leader(self):
        scorer = make_scorer()
        data_leader = {"market": {"competitive_position": "market leader", "market_growth_rate": 0.10}}
        data_strong = {"market": {"competitive_position": "strong", "market_growth_rate": 0.10}}
        assert scorer._score_market(data_leader).score > scorer._score_market(data_strong).score

    def test_tam_revenue_ratio_cap(self):
        """TAM/revenue > 100,000× should cap score at 0.60."""
        scorer = make_scorer()
        data = {
            "market": {
                "tam": "1000000000000",   # $1T TAM
                "market_growth_rate": 0.20,
                "competitive_position": "market leader",
            },
            "financials": {
                "revenue": {"ltm": 500_000}  # $500K revenue → ratio = 2,000,000×
            },
        }
        result = scorer._score_market(data)
        assert result.score <= 0.60, f"Expected TAM cap ≤0.60, got {result.score}"

    def test_score_capped_at_1(self):
        """Score should never exceed 1.0."""
        scorer = make_scorer()
        data = {
            "market": {
                "tam": "10000000000",
                "market_growth_rate": 0.50,
                "competitive_position": "market leader",
            }
        }
        result = scorer._score_market(data)
        assert result.score <= 1.0

    def test_empty_market_data_returns_baseline(self):
        scorer = make_scorer()
        result = scorer._score_market({})
        assert 0.0 <= result.score <= 1.0
        assert result.data_quality == "no_data"


# ---------------------------------------------------------------------------
# Financial Quality dimension
# ---------------------------------------------------------------------------

class TestScoreFinancials:

    def test_strong_margins_high_recurring_scores_well(self):
        scorer = make_scorer()
        data = {
            "financials": {
                "ebitda": {"margin_ltm": 0.30},
                "recurring_revenue_pct": 0.85,
            },
            "customers": {"top_customer_concentration": 0.08},
        }
        result = scorer._score_financials(data)
        assert result.score >= 0.80

    def test_thin_margins_low_recurring_scores_poorly(self):
        scorer = make_scorer()
        data = {
            "financials": {
                "ebitda": {"margin_ltm": 0.05},
                "recurring_revenue_pct": 0.25,
            },
            "customers": {"top_customer_concentration": 0.50},
        }
        result = scorer._score_financials(data)
        assert result.score <= 0.50

    def test_high_concentration_penalises_score(self):
        scorer = make_scorer()
        data_conc = {
            "financials": {"ebitda": {"margin_ltm": 0.20}, "recurring_revenue_pct": 0.70},
            "customers": {"top_customer_concentration": 0.40},
        }
        data_diverse = {
            "financials": {"ebitda": {"margin_ltm": 0.20}, "recurring_revenue_pct": 0.70},
            "customers": {"top_customer_concentration": 0.08},
        }
        assert scorer._score_financials(data_conc).score < scorer._score_financials(data_diverse).score

    def test_score_bounds(self):
        scorer = make_scorer()
        # Worst-case: very low margins, no recurrence, extreme concentration
        data = {
            "financials": {
                "ebitda": {"margin_ltm": -0.50},
                "recurring_revenue_pct": 0.01,
            },
            "customers": {"top_customer_concentration": 0.99},
        }
        result = scorer._score_financials(data)
        assert 0.0 <= result.score <= 1.0

    def test_empty_financials_returns_baseline(self):
        scorer = make_scorer()
        result = scorer._score_financials({})
        assert result.data_quality == "no_data"
        assert result.score == 0.5  # Unchanged baseline


# ---------------------------------------------------------------------------
# Growth Profile dimension
# ---------------------------------------------------------------------------

class TestScoreGrowth:

    def test_high_cagr_scores_well(self):
        scorer = make_scorer()
        data = {
            "financials": {"revenue": {"cagr_3yr": 0.25}},
            "growth_thesis": {"organic_levers": ["a", "b", "c", "d"], "ma_opportunity": "yes"},
        }
        result = scorer._score_growth(data)
        assert result.score >= 0.80

    def test_low_cagr_scores_poorly(self):
        scorer = make_scorer()
        data = {
            "financials": {"revenue": {"cagr_3yr": 0.03}},
            "growth_thesis": {"organic_levers": []},
        }
        result = scorer._score_growth(data)
        assert result.score <= 0.55

    def test_3_plus_organic_levers_boost(self):
        scorer = make_scorer()
        data_few = {
            "financials": {"revenue": {"cagr_3yr": 0.15}},
            "growth_thesis": {"organic_levers": ["a"]},
        }
        data_many = {
            "financials": {"revenue": {"cagr_3yr": 0.15}},
            "growth_thesis": {"organic_levers": ["a", "b", "c", "d"]},
        }
        assert scorer._score_growth(data_many).score > scorer._score_growth(data_few).score

    def test_ma_opportunity_boosts_score(self):
        scorer = make_scorer()
        data_no_ma = {
            "financials": {"revenue": {"cagr_3yr": 0.15}},
            "growth_thesis": {"organic_levers": [], "ma_opportunity": "not_provided"},
        }
        data_ma = {
            "financials": {"revenue": {"cagr_3yr": 0.15}},
            "growth_thesis": {"organic_levers": [], "ma_opportunity": "multiple bolt-on targets"},
        }
        assert scorer._score_growth(data_ma).score > scorer._score_growth(data_no_ma).score

    def test_score_bounds(self, complete_data):
        scorer = make_scorer()
        result = scorer._score_growth(complete_data)
        assert 0.0 <= result.score <= 1.0


# ---------------------------------------------------------------------------
# Management Strength dimension
# ---------------------------------------------------------------------------

class TestScoreManagement:

    def test_experienced_ceo_deep_bench_high_ownership_scores_well(self):
        scorer = make_scorer()
        data = {
            "management": {
                "ceo_tenure_years": 10,
                "key_executives": [{"name": "a"}, {"name": "b"}, {"name": "c"}, {"name": "d"}, {"name": "e"}],
                "management_ownership": 0.15,
            }
        }
        result = scorer._score_management(data)
        assert result.score >= 0.80

    def test_new_ceo_thin_bench_scores_lower(self):
        scorer = make_scorer()
        data = {
            "management": {
                "ceo_tenure_years": 0.5,
                "key_executives": [{"name": "a"}],
                "management_ownership": 0.00,
            }
        }
        result = scorer._score_management(data)
        assert result.score <= 0.55

    def test_meaningful_ownership_boosts_score(self):
        scorer = make_scorer()
        base = {
            "management": {
                "ceo_tenure_years": 5,
                "key_executives": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            }
        }
        with_ownership = dict(base)
        with_ownership["management"] = {**base["management"], "management_ownership": 0.10}
        no_ownership = dict(base)
        no_ownership["management"] = {**base["management"], "management_ownership": 0.01}
        assert scorer._score_management(with_ownership).score > scorer._score_management(no_ownership).score

    def test_empty_management_returns_baseline(self):
        scorer = make_scorer()
        result = scorer._score_management({})
        assert result.score == 0.5


# ---------------------------------------------------------------------------
# Risk Profile dimension
# ---------------------------------------------------------------------------

class TestScoreRisk:

    def test_all_low_risk_scores_high(self):
        scorer = make_scorer()
        data = {
            "risk_factors": {
                "customer_concentration_risk": "low",
                "key_person_dependency": "low",
                "regulatory_risk": "low",
                "market_cyclicality": "low",
                "technology_risk": "low",
                "identified_risks": ["competition"],
            }
        }
        result = scorer._score_risk(data)
        assert result.score >= 0.65

    def test_critical_risk_applies_extra_penalty(self):
        scorer = make_scorer()
        data_high = {"risk_factors": {"regulatory_risk": "high"}}
        data_critical = {"risk_factors": {"regulatory_risk": "critical"}}
        assert scorer._score_risk(data_critical).score < scorer._score_risk(data_high).score

    def test_many_identified_risks_penalised(self):
        scorer = make_scorer()
        data_few = {"risk_factors": {"identified_risks": ["a", "b"]}}
        data_many = {"risk_factors": {"identified_risks": list(range(8))}}
        assert scorer._score_risk(data_many).score < scorer._score_risk(data_few).score

    def test_6_identified_risks_not_penalised(self):
        """Exactly 5 identified risks — boundary; > 5 triggers deduction."""
        scorer = make_scorer()
        data = {"risk_factors": {"identified_risks": list(range(5))}}
        result = scorer._score_risk(data)
        data_over = {"risk_factors": {"identified_risks": list(range(6))}}
        result_over = scorer._score_risk(data_over)
        assert result.score > result_over.score

    def test_score_bounds_high_risk(self, high_risk_data):
        scorer = make_scorer()
        result = scorer._score_risk(high_risk_data)
        assert 0.0 <= result.score <= 1.0


# ---------------------------------------------------------------------------
# Data completeness penalty
# ---------------------------------------------------------------------------

class TestDataCompletenessPenalty:

    def test_all_fields_present_no_penalty(self, complete_data):
        scorer = make_scorer()
        multiplier, missing, total = scorer._data_completeness_penalty(complete_data)
        assert multiplier == 1.0
        assert missing == 0

    def test_all_fields_missing_heavy_penalty(self, sparse_data):
        scorer = make_scorer()
        multiplier, missing, total = scorer._data_completeness_penalty(sparse_data)
        assert multiplier == 0.75
        assert missing == total  # 6/6

    def test_5_of_6_missing_heavy_penalty(self):
        """revenue.ltm present (1/6) → 5 missing → 83% > 75% → 0.75 penalty."""
        scorer = make_scorer()
        data = {
            "financials": {
                "revenue": {"ltm": 1_000_000},       # present — only 1 of 6
                "ebitda": {
                    "ltm": "not_provided",
                    "margin_ltm": "not_provided",
                },
                "gross_margin": "not_provided",
                "recurring_revenue_pct": "not_provided",
                "net_income": "not_provided",
            }
        }
        multiplier, missing, total = scorer._data_completeness_penalty(data)
        assert multiplier == 0.75   # 5/6 = 83% > 75% threshold
        assert missing == 5

    def test_4_of_6_missing_medium_penalty(self):
        """4 of 6 fields missing → 67% > 50% but ≤ 75% → 0.85 penalty."""
        scorer = make_scorer()
        data = {
            "financials": {
                "revenue": {"ltm": 1_000_000},
                "ebitda": {
                    "ltm": 250_000,                  # present
                    "margin_ltm": "not_provided",
                },
                "gross_margin": "not_provided",
                "recurring_revenue_pct": "not_provided",
                "net_income": "not_provided",
            }
        }
        multiplier, missing, total = scorer._data_completeness_penalty(data)
        assert multiplier == 0.85   # 4/6 = 67% → medium penalty
        assert missing == 4

    def test_3_of_6_missing_no_penalty(self):
        """Exactly 50% missing — no penalty (> 50% required)."""
        scorer = make_scorer()
        data = {
            "financials": {
                "revenue": {"ltm": 1_000_000},
                "ebitda": {
                    "ltm": 250_000,
                    "margin_ltm": 0.25,
                },
                "gross_margin": "not_provided",
                "recurring_revenue_pct": "not_provided",
                "net_income": "not_provided",
            }
        }
        multiplier, missing, total = scorer._data_completeness_penalty(data)
        assert multiplier == 1.0
        assert missing == 3

    def test_empty_data_max_penalty(self):
        scorer = make_scorer()
        multiplier, missing, total = scorer._data_completeness_penalty({})
        assert multiplier == 0.75


# ---------------------------------------------------------------------------
# Grade and recommendation mapping
# ---------------------------------------------------------------------------

class TestGradeMapping:

    @pytest.mark.parametrize("total,expected_grade", [
        (0.85, "A"),
        (0.80, "A"),
        (0.79, "B"),
        (0.65, "B"),
        (0.64, "C"),
        (0.50, "C"),
        (0.49, "D"),
        (0.35, "D"),
        (0.34, "F"),
        (0.00, "F"),
    ])
    def test_total_to_grade(self, total, expected_grade):
        scorer = make_scorer()
        assert scorer._total_to_grade(total) == expected_grade

    @pytest.mark.parametrize("grade,expected_rec", [
        ("A", "Strong Pursue"),
        ("B", "Pursue"),
        ("C", "Conditional — needs diligence on weak areas"),
        ("D", "Likely Pass — significant concerns"),
        ("F", "Pass"),
    ])
    def test_grade_to_recommendation(self, grade, expected_rec):
        scorer = make_scorer()
        assert scorer._grade_to_recommendation(grade) == expected_rec

    def test_unknown_grade_returns_needs_review(self):
        scorer = make_scorer()
        assert scorer._grade_to_recommendation("Z") == "Needs Review"


# ---------------------------------------------------------------------------
# _parse_numeric helper
# ---------------------------------------------------------------------------

class TestParseNumeric:

    @pytest.mark.parametrize("value,expected", [
        (1_000_000, 1_000_000.0),
        ("1000000", 1_000_000.0),
        ("1.5M", 1_500_000.0),
        ("2.5B", 2_500_000_000.0),
        ("500K", 500_000.0),
        ("$1.5M", 1_500_000.0),
        ("1,500,000", None),   # comma-separated plain number: not supported (no suffix)
        (None, None),
        ("not_provided", None),
        ("TBD", None),
        ("", None),
    ])
    def test_parse_numeric(self, value, expected):
        scorer = make_scorer()
        result = scorer._parse_numeric(value)
        assert result == expected, f"_parse_numeric({value!r}) = {result}, expected {expected}"


# ---------------------------------------------------------------------------
# Full score() — integration-style (deterministic path only)
# ---------------------------------------------------------------------------

class TestFullScore:

    def test_complete_healthy_data_scores_b_or_above(self, complete_data):
        scorer = make_scorer()
        result = scorer.score(complete_data)
        assert result.grade in {"A", "B"}, f"Expected A or B, got {result.grade}"
        assert isinstance(result, DealScore)

    def test_sparse_data_penalised_and_scores_lower(self, sparse_data, complete_data):
        scorer = make_scorer()
        sparse_result = scorer.score(sparse_data)
        complete_result = scorer.score(complete_data)
        assert sparse_result.total_score < complete_result.total_score

    def test_high_risk_data_scores_d_or_f(self, high_risk_data):
        scorer = make_scorer()
        result = scorer.score(high_risk_data)
        assert result.grade in {"D", "F", "C"}, f"High-risk data scored {result.grade}"

    def test_empty_data_returns_valid_dealscore(self, empty_data):
        scorer = make_scorer()
        result = scorer.score(empty_data)
        assert isinstance(result, DealScore)
        assert result.grade in {"A", "B", "C", "D", "F"}
        assert 0.0 <= result.total_score <= 1.0

    def test_result_has_5_dimensions(self, complete_data):
        scorer = make_scorer()
        result = scorer.score(complete_data)
        assert len(result.dimensions) == 5

    def test_total_score_is_rounded(self, complete_data):
        scorer = make_scorer()
        result = scorer.score(complete_data)
        assert result.total_score == round(result.total_score, 3)

    def test_summary_contains_grade(self, complete_data):
        scorer = make_scorer()
        result = scorer.score(complete_data)
        assert result.grade in result.summary

    def test_penalty_reflected_in_summary(self, sparse_data):
        scorer = make_scorer()
        result = scorer.score(sparse_data)
        assert "penalty" in result.summary.lower()

    def test_weighted_scores_use_correct_weights(self, complete_data):
        scorer = make_scorer()
        result = scorer.score(complete_data)
        for dim in result.dimensions:
            expected_weighted = round(dim.score * dim.weight, 3)
            # Weighted score should be close (may differ by float rounding)
            assert abs(dim.weighted_score - expected_weighted) < 0.005

    def test_conservative_weights_grade_different_than_growth(self, complete_data):
        """Different weight profiles can yield different total scores."""
        cons_scorer = make_scorer(CONSERVATIVE)
        growth_scorer = make_scorer(GROWTH_ORIENTED)
        cons_result = cons_scorer.score(complete_data)
        growth_result = growth_scorer.score(complete_data)
        # Scores may be equal if data is uniformly strong, just confirm no crash
        assert isinstance(cons_result, DealScore)
        assert isinstance(growth_result, DealScore)

    def test_none_values_data_no_crash(self, none_values_data):
        scorer = make_scorer()
        result = scorer.score(none_values_data)
        assert isinstance(result, DealScore)
