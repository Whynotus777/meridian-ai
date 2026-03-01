"""Deal scoring engine.

Scores deals on multiple dimensions with configurable weights.
Combines heuristic scoring with LLM-assessed qualitative dimensions.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from config.scoring_weights import ScoringWeights, BALANCED


@dataclass
class DimensionScore:
    """Score for a single dimension."""
    dimension: str
    score: float  # 0.0 to 1.0
    weight: float
    weighted_score: float
    rationale: str
    data_quality: str  # "strong", "moderate", "weak", "no_data"


@dataclass
class DealScore:
    """Complete deal score with breakdown."""
    total_score: float  # 0.0 to 1.0
    grade: str  # A, B, C, D, F
    dimensions: List[DimensionScore]
    summary: str
    recommendation: str  # "Strong Pursue", "Pursue", "Conditional", "Pass"


class DealScorer:
    """Multi-dimensional deal scoring."""

    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights or BALANCED

    def score(self, extracted_data: Dict[str, Any]) -> DealScore:
        """Score a deal on all dimensions."""
        dimensions = [
            self._score_market(extracted_data),
            self._score_financials(extracted_data),
            self._score_growth(extracted_data),
            self._score_management(extracted_data),
            self._score_risk(extracted_data),
        ]

        total = sum(d.weighted_score for d in dimensions)
        grade = self._total_to_grade(total)
        recommendation = self._grade_to_recommendation(grade)

        return DealScore(
            total_score=round(total, 3),
            grade=grade,
            dimensions=dimensions,
            summary=self._build_summary(dimensions, grade),
            recommendation=recommendation,
        )

    def _score_market(self, data: Dict) -> DimensionScore:
        """Score market attractiveness."""
        market = data.get("market", {})
        score = 0.5  # Baseline
        reasons = []
        quality = "no_data"

        tam = market.get("tam")
        if tam and tam != "not_provided":
            quality = "moderate"
            reasons.append(f"TAM: {tam}")
            score += 0.1

        growth = market.get("market_growth_rate")
        if growth and growth != "not_provided":
            quality = "strong" if quality != "no_data" else "moderate"
            try:
                g = float(growth)
                if g > 0.10:
                    score += 0.3
                    reasons.append(f"High market growth: {g:.0%}")
                elif g > 0.05:
                    score += 0.15
                    reasons.append(f"Moderate market growth: {g:.0%}")
                else:
                    reasons.append(f"Low market growth: {g:.0%}")
            except (ValueError, TypeError):
                pass

        position = market.get("competitive_position", "")
        if "leader" in position.lower():
            score += 0.2
            reasons.append("Market leader position")
        elif "strong" in position.lower():
            score += 0.1
            reasons.append("Strong competitive position")

        score = min(1.0, score)
        weighted = score * self.weights.market_attractiveness

        return DimensionScore(
            dimension="Market Attractiveness",
            score=round(score, 2),
            weight=self.weights.market_attractiveness,
            weighted_score=round(weighted, 3),
            rationale="; ".join(reasons) if reasons else "Insufficient market data",
            data_quality=quality,
        )

    def _score_financials(self, data: Dict) -> DimensionScore:
        """Score financial quality."""
        fin = data.get("financials", {})
        score = 0.5
        reasons = []
        quality = "no_data"

        # EBITDA margin
        margin = fin.get("ebitda", {}).get("margin_ltm")
        if margin and margin != "not_provided":
            quality = "moderate"
            try:
                m = float(margin)
                if m > 0.25:
                    score += 0.25
                    reasons.append(f"Strong margins: {m:.0%}")
                elif m > 0.15:
                    score += 0.15
                    reasons.append(f"Healthy margins: {m:.0%}")
                elif m > 0.10:
                    score += 0.05
                    reasons.append(f"Moderate margins: {m:.0%}")
                else:
                    score -= 0.1
                    reasons.append(f"Thin margins: {m:.0%}")
            except (ValueError, TypeError):
                pass

        # Recurring revenue
        recurring = fin.get("recurring_revenue_pct")
        if recurring and recurring != "not_provided":
            quality = "strong" if quality != "no_data" else "moderate"
            try:
                r = float(recurring)
                if r > 0.80:
                    score += 0.2
                    reasons.append(f"Highly recurring: {r:.0%}")
                elif r > 0.50:
                    score += 0.1
                    reasons.append(f"Moderately recurring: {r:.0%}")
            except (ValueError, TypeError):
                pass

        # Revenue diversity
        customers = data.get("customers", {})
        top_cust = customers.get("top_customer_concentration")
        if top_cust and top_cust != "not_provided":
            try:
                tc = float(top_cust)
                if tc < 0.10:
                    score += 0.1
                    reasons.append("Well-diversified customer base")
                elif tc > 0.25:
                    score -= 0.15
                    reasons.append(f"Customer concentration concern: {tc:.0%}")
            except (ValueError, TypeError):
                pass

        score = max(0.0, min(1.0, score))
        weighted = score * self.weights.financial_quality

        return DimensionScore(
            dimension="Financial Quality",
            score=round(score, 2),
            weight=self.weights.financial_quality,
            weighted_score=round(weighted, 3),
            rationale="; ".join(reasons) if reasons else "Insufficient financial data",
            data_quality=quality,
        )

    def _score_growth(self, data: Dict) -> DimensionScore:
        """Score growth profile."""
        fin = data.get("financials", {})
        growth = data.get("growth_thesis", {})
        score = 0.5
        reasons = []
        quality = "no_data"

        cagr = fin.get("revenue", {}).get("cagr_3yr")
        if cagr and cagr != "not_provided":
            quality = "strong"
            try:
                c = float(cagr)
                if c > 0.20:
                    score += 0.3
                    reasons.append(f"Strong growth: {c:.0%} CAGR")
                elif c > 0.10:
                    score += 0.15
                    reasons.append(f"Solid growth: {c:.0%} CAGR")
                elif c > 0.05:
                    score += 0.05
                    reasons.append(f"Moderate growth: {c:.0%} CAGR")
                else:
                    score -= 0.1
                    reasons.append(f"Low growth: {c:.0%} CAGR")
            except (ValueError, TypeError):
                pass

        organic = growth.get("organic_levers", [])
        if isinstance(organic, list) and len(organic) >= 3:
            score += 0.1
            reasons.append(f"{len(organic)} organic growth levers identified")

        ma = growth.get("ma_opportunity")
        if ma and ma != "not_provided":
            score += 0.05
            reasons.append("M&A / add-on opportunity identified")

        score = max(0.0, min(1.0, score))
        weighted = score * self.weights.growth_profile

        return DimensionScore(
            dimension="Growth Profile",
            score=round(score, 2),
            weight=self.weights.growth_profile,
            weighted_score=round(weighted, 3),
            rationale="; ".join(reasons) if reasons else "Insufficient growth data",
            data_quality=quality,
        )

    def _score_management(self, data: Dict) -> DimensionScore:
        """Score management quality."""
        mgmt = data.get("management", {})
        score = 0.5
        reasons = []
        quality = "no_data"

        ceo_tenure = mgmt.get("ceo_tenure_years")
        if ceo_tenure and ceo_tenure != "not_provided":
            quality = "moderate"
            try:
                t = float(ceo_tenure)
                if t > 5:
                    score += 0.2
                    reasons.append(f"Experienced CEO ({t:.0f} years)")
                elif t > 2:
                    score += 0.1
                    reasons.append(f"CEO tenure: {t:.0f} years")
                else:
                    reasons.append(f"New CEO ({t:.0f} years)")
            except (ValueError, TypeError):
                pass

        execs = mgmt.get("key_executives", [])
        if isinstance(execs, list) and len(execs) >= 4:
            quality = "strong" if quality != "no_data" else "moderate"
            score += 0.15
            reasons.append(f"Deep bench: {len(execs)} key executives")
        elif isinstance(execs, list) and len(execs) >= 2:
            score += 0.05

        ownership = mgmt.get("management_ownership")
        if ownership and ownership != "not_provided":
            try:
                o = float(ownership)
                if o > 0.05:
                    score += 0.1
                    reasons.append("Management has meaningful equity stake")
            except (ValueError, TypeError):
                pass

        score = max(0.0, min(1.0, score))
        weighted = score * self.weights.management_strength

        return DimensionScore(
            dimension="Management Strength",
            score=round(score, 2),
            weight=self.weights.management_strength,
            weighted_score=round(weighted, 3),
            rationale="; ".join(reasons) if reasons else "Limited management data in CIM",
            data_quality=quality,
        )

    def _score_risk(self, data: Dict) -> DimensionScore:
        """Score risk profile (inverted: high risk = low score)."""
        risks = data.get("risk_factors", {})
        score = 0.7  # Start optimistic, deduct for risks
        reasons = []
        quality = "no_data"

        risk_fields = [
            ("customer_concentration_risk", 0.15),
            ("key_person_dependency", 0.10),
            ("regulatory_risk", 0.10),
            ("market_cyclicality", 0.10),
            ("technology_risk", 0.05),
        ]

        for field_name, penalty in risk_fields:
            val = risks.get(field_name, "")
            if val and val != "not_provided":
                quality = "moderate"
                if val.lower() == "high":
                    score -= penalty
                    reasons.append(f"High {field_name.replace('_', ' ')}")
                elif val.lower() == "critical":
                    score -= penalty * 1.5
                    reasons.append(f"Critical {field_name.replace('_', ' ')}")
                elif val.lower() == "low":
                    reasons.append(f"Low {field_name.replace('_', ' ')}")

        identified = risks.get("identified_risks", [])
        if isinstance(identified, list) and len(identified) > 5:
            score -= 0.05
            reasons.append(f"{len(identified)} explicit risks identified")

        score = max(0.0, min(1.0, score))
        weighted = score * self.weights.risk_factors

        return DimensionScore(
            dimension="Risk Profile",
            score=round(score, 2),
            weight=self.weights.risk_factors,
            weighted_score=round(weighted, 3),
            rationale="; ".join(reasons) if reasons else "Risk assessment limited by available data",
            data_quality=quality,
        )

    def _total_to_grade(self, total: float) -> str:
        if total >= 0.80:
            return "A"
        elif total >= 0.65:
            return "B"
        elif total >= 0.50:
            return "C"
        elif total >= 0.35:
            return "D"
        return "F"

    def _grade_to_recommendation(self, grade: str) -> str:
        return {
            "A": "Strong Pursue",
            "B": "Pursue",
            "C": "Conditional — needs diligence on weak areas",
            "D": "Likely Pass — significant concerns",
            "F": "Pass",
        }.get(grade, "Needs Review")

    def _build_summary(self, dims: List[DimensionScore], grade: str) -> str:
        strong = [d.dimension for d in dims if d.score >= 0.7]
        weak = [d.dimension for d in dims if d.score < 0.5]
        summary = f"Overall grade: {grade}. "
        if strong:
            summary += f"Strengths: {', '.join(strong)}. "
        if weak:
            summary += f"Concerns: {', '.join(weak)}. "
        no_data = [d.dimension for d in dims if d.data_quality == "no_data"]
        if no_data:
            summary += f"Insufficient data for: {', '.join(no_data)}."
        return summary
