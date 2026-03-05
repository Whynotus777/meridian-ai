"""JSON export for structured pipeline output."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import Dict, Any, List

from core.risk_analyzer import RiskFlag
from core.comp_builder import Comparable
from scoring.deal_scorer import DealScore


def export_full_analysis(
    extracted_data: Dict[str, Any],
    memo: str,
    risks: List[RiskFlag],
    comps: List[Comparable],
    deal_score: DealScore,
    output_path: str,
) -> str:
    """Export the complete analysis as a single JSON file."""
    output = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "version": "0.1.0-mvp",
            "pipeline": "meridian-ai",
        },
        "extracted_data": extracted_data,
        "investment_memo": memo,
        "risk_analysis": {
            "total_risks": len(risks),
            "critical_risks": len([r for r in risks if r.severity == "Critical"]),
            "high_risks": len([r for r in risks if r.severity == "High"]),
            "risks": [
                {
                    "category": r.category,
                    "severity": r.severity,
                    "title": r.title,
                    "description": r.description,
                    "mitigant": r.mitigant,
                    "diligence_question": r.diligence_question,
                    "source": r.source,
                }
                for r in risks
            ],
        },
        "comparable_companies": [c.to_dict() for c in comps],
        "deal_score": {
            "total_score": deal_score.total_score,
            "grade": deal_score.grade,
            "recommendation": deal_score.recommendation,
            "summary": deal_score.summary,
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "score": d.score,
                    "weight": d.weight,
                    "weighted_score": d.weighted_score,
                    "rationale": d.rationale,
                    "data_quality": d.data_quality,
                }
                for d in deal_score.dimensions
            ],
        },
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    return output_path
