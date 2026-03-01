"""Scoring weight configurations for deal evaluation.

Each PE firm can have their own weight profile. The defaults represent
a balanced mid-market buyout perspective.
"""

from dataclasses import dataclass


@dataclass
class ScoringWeights:
    """Weights for deal scoring dimensions. Must sum to 1.0."""
    market_attractiveness: float = 0.20
    financial_quality: float = 0.30
    growth_profile: float = 0.20
    management_strength: float = 0.10
    risk_factors: float = 0.20

    def __post_init__(self):
        total = (
            self.market_attractiveness
            + self.financial_quality
            + self.growth_profile
            + self.management_strength
            + self.risk_factors
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total:.2f}")


# Preset weight profiles
BALANCED = ScoringWeights()

CONSERVATIVE = ScoringWeights(
    market_attractiveness=0.15,
    financial_quality=0.35,
    growth_profile=0.15,
    management_strength=0.10,
    risk_factors=0.25,
)

GROWTH_ORIENTED = ScoringWeights(
    market_attractiveness=0.25,
    financial_quality=0.20,
    growth_profile=0.30,
    management_strength=0.10,
    risk_factors=0.15,
)

PROFILES = {
    "balanced": BALANCED,
    "conservative": CONSERVATIVE,
    "growth": GROWTH_ORIENTED,
}
