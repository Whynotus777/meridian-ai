"""Risk analysis engine.

Combines rule-based heuristic checks with LLM-powered risk identification.
Design principle: deterministic checks where possible, LLM for nuance.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from config.settings import ModelConfig
from core.llm_client import LLMClient, strip_fences
from prompts.extraction import SYSTEM_PROMPT, RISK_ANALYSIS_PROMPT


@dataclass
class RiskFlag:
    """A single identified risk."""
    category: str  # Financial, Operational, Market, Regulatory, Management, Customer, Tech
    severity: str  # Critical, High, Medium, Low
    title: str
    description: str
    mitigant: str = ""
    diligence_question: str = ""
    source: str = "heuristic"  # "heuristic" or "llm"


class RiskAnalyzer:
    """Identifies investment risks from CIM data."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.client = LLMClient(self.config)

    def analyze(self, extracted_data: Dict[str, Any]) -> List[RiskFlag]:
        """Run full risk analysis: heuristic checks + LLM analysis."""
        risks = []

        # Deterministic checks first
        risks.extend(self._check_customer_concentration(extracted_data))
        risks.extend(self._check_financial_quality(extracted_data))
        risks.extend(self._check_management_risk(extracted_data))
        risks.extend(self._check_growth_sustainability(extracted_data))

        # LLM-powered deeper analysis
        llm_risks = self._llm_risk_analysis(extracted_data)
        risks.extend(llm_risks)

        # Deduplicate by title similarity
        seen_titles = set()
        unique_risks = []
        for risk in risks:
            key = risk.title.lower()[:30]
            if key not in seen_titles:
                seen_titles.add(key)
                unique_risks.append(risk)

        # Sort by severity
        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        unique_risks.sort(key=lambda r: severity_order.get(r.severity, 4))

        return unique_risks

    def _check_customer_concentration(self, data: Dict) -> List[RiskFlag]:
        """Heuristic: check customer concentration thresholds."""
        flags = []
        customers = data.get("customers", {})

        top_customer = customers.get("top_customer_concentration")
        if top_customer and top_customer != "not_provided":
            pct = float(top_customer) if isinstance(top_customer, (int, float)) else 0
            if pct > 0.25:
                flags.append(RiskFlag(
                    category="Customer",
                    severity="Critical" if pct > 0.40 else "High",
                    title="High customer concentration",
                    description=f"Top customer represents {pct:.0%} of revenue. "
                                f"Loss of this customer would materially impact the business.",
                    diligence_question="What is the contract term and renewal status "
                                      "with the top customer? Any recent RFP activity?",
                ))

        top_10 = customers.get("top_10_concentration")
        if top_10 and top_10 != "not_provided":
            pct = float(top_10) if isinstance(top_10, (int, float)) else 0
            if pct > 0.60:
                flags.append(RiskFlag(
                    category="Customer",
                    severity="High" if pct > 0.75 else "Medium",
                    title="Top 10 customer concentration",
                    description=f"Top 10 customers represent {pct:.0%} of revenue.",
                    diligence_question="Request full customer cohort analysis "
                                      "with retention rates by vintage.",
                ))

        retention = customers.get("customer_retention")
        if retention and retention != "not_provided":
            rate = float(retention) if isinstance(retention, (int, float)) else 1.0
            if rate < 0.85:
                flags.append(RiskFlag(
                    category="Customer",
                    severity="High" if rate < 0.75 else "Medium",
                    title="Below-benchmark retention rate",
                    description=f"Customer retention at {rate:.0%} is below "
                                f"typical benchmarks for this business type.",
                    diligence_question="What is driving churn? Analyze by segment, "
                                      "cohort, and reason code.",
                ))

        return flags

    def _check_financial_quality(self, data: Dict) -> List[RiskFlag]:
        """Heuristic: check financial quality indicators."""
        flags = []
        fin = data.get("financials", {})

        # Margin check
        ebitda_margin = fin.get("ebitda", {}).get("margin_ltm")
        if ebitda_margin and ebitda_margin != "not_provided":
            margin = float(ebitda_margin) if isinstance(ebitda_margin, (int, float)) else 0
            if margin < 0.10:
                flags.append(RiskFlag(
                    category="Financial",
                    severity="High",
                    title="Low EBITDA margins",
                    description=f"LTM EBITDA margin of {margin:.0%} suggests limited "
                                f"pricing power or operational inefficiency.",
                    diligence_question="What is the margin improvement roadmap? "
                                      "Benchmark against peers.",
                ))

        # Adjusted vs reported EBITDA gap
        ebitda = fin.get("ebitda", {})
        reported = ebitda.get("ltm")
        adjusted = ebitda.get("adjusted_ebitda_ltm")
        if (reported and adjusted and
                reported != "not_provided" and adjusted != "not_provided"):
            try:
                r, a = float(reported), float(adjusted)
                if r > 0 and (a - r) / r > 0.30:
                    flags.append(RiskFlag(
                        category="Financial",
                        severity="High",
                        title="Large EBITDA adjustments",
                        description=f"Adjusted EBITDA ({a:,.0f}) is {((a-r)/r):.0%} higher "
                                    f"than reported ({r:,.0f}). Scrutinize add-backs.",
                        diligence_question="Request detailed add-back schedule with "
                                          "supporting documentation for each adjustment.",
                    ))
            except (ValueError, TypeError):
                pass

        # Recurring revenue
        recurring = fin.get("recurring_revenue_pct")
        if recurring and recurring != "not_provided":
            pct = float(recurring) if isinstance(recurring, (int, float)) else 1.0
            if pct < 0.50:
                flags.append(RiskFlag(
                    category="Financial",
                    severity="Medium",
                    title="Low recurring revenue",
                    description=f"Only {pct:.0%} of revenue is recurring/contracted. "
                                f"Higher execution risk on revenue forecasts.",
                    diligence_question="Analyze revenue by type (recurring, "
                                      "repeat, project-based) with historical trends.",
                ))

        return flags

    def _check_management_risk(self, data: Dict) -> List[RiskFlag]:
        """Heuristic: check management / key person risk."""
        flags = []
        mgmt = data.get("management", {})

        ceo_tenure = mgmt.get("ceo_tenure_years")
        if ceo_tenure and ceo_tenure != "not_provided":
            try:
                years = float(ceo_tenure)
                if years < 2:
                    flags.append(RiskFlag(
                        category="Management",
                        severity="Medium",
                        title="New CEO",
                        description=f"CEO has been in role for only {years:.0f} years. "
                                    f"Strategy may not be fully proven.",
                        diligence_question="What was the CEO transition story? "
                                          "Interview prior leadership if possible.",
                    ))
            except (ValueError, TypeError):
                pass

        key_execs = mgmt.get("key_executives", [])
        if isinstance(key_execs, list) and len(key_execs) < 3:
            flags.append(RiskFlag(
                category="Management",
                severity="Medium",
                title="Thin management bench",
                description="Limited executive team depth identified in CIM. "
                            "Key person dependency risk.",
                diligence_question="Map org chart 2 levels deep. "
                                  "Assess flight risk and bench strength.",
            ))

        return flags

    def _check_growth_sustainability(self, data: Dict) -> List[RiskFlag]:
        """Heuristic: validate growth claims."""
        flags = []
        fin = data.get("financials", {})
        market = data.get("market", {})

        rev = fin.get("revenue", {})
        cagr = rev.get("cagr_3yr")
        market_growth = market.get("market_growth_rate")

        if (cagr and market_growth and
                cagr != "not_provided" and market_growth != "not_provided"):
            try:
                c, m = float(cagr), float(market_growth)
                if c > m * 3:
                    flags.append(RiskFlag(
                        category="Market",
                        severity="Medium",
                        title="Growth significantly outpacing market",
                        description=f"Company CAGR ({c:.0%}) is {c/m:.1f}x the market "
                                    f"growth rate ({m:.0%}). Validate sustainability.",
                        diligence_question="What is driving outperformance? "
                                          "Is it share gain, new products, or acquisitions?",
                    ))
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        return flags

    def _llm_risk_analysis(self, data: Dict) -> List[RiskFlag]:
        """LLM-powered risk identification for nuanced risks."""
        prompt = RISK_ANALYSIS_PROMPT.format(
            extracted_data=json.dumps(data, indent=2, default=str)
        )

        try:
            raw = self.client.complete(
                system=SYSTEM_PROMPT,
                user=prompt,
                max_tokens=3000,
                temperature=0.0,
            )
            text = strip_fences(raw)

            # Try direct parse, then find outermost [ ... ] block
            risks_data = None
            try:
                risks_data = json.loads(text)
            except json.JSONDecodeError:
                bracket_start = text.find("[")
                bracket_end   = text.rfind("]")
                if bracket_start != -1 and bracket_end != -1:
                    try:
                        risks_data = json.loads(text[bracket_start:bracket_end + 1])
                    except json.JSONDecodeError:
                        pass

            if risks_data:
                return [
                    RiskFlag(
                        category=r.get("category", "Other"),
                        severity=r.get("severity", "Medium"),
                        title=r.get("title", r.get("description", "")[:50]),
                        description=r.get("description", ""),
                        mitigant=r.get("mitigant", ""),
                        diligence_question=r.get("diligence_question", ""),
                        source="llm",
                    )
                    for r in risks_data
                    if isinstance(r, dict)
                ]
        except Exception:
            pass  # Graceful degradation — heuristic risks still work

        return []
