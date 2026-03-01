"""PE Fund matching engine — adapted from pe_fund_matcher_final.ipynb (D.E. Shaw Case Study).

Integrates the PEFund dataclass, PE_FUND_DATABASE (25 funds), and MatchingEngine
from the reference notebook. Adapted to accept a CIM extraction dict directly
instead of a CompanyProfile from website scraping. Weighted scoring logic preserved
verbatim: Industry 30% | Size 25% | Geography 15% | Strategic 30%.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data models (from notebook — unchanged)
# ---------------------------------------------------------------------------

@dataclass
class PEFund:
    """PE Fund with investment criteria — all data publicly verifiable."""
    name: str
    headquarters: str
    fund_size_category: str          # "Lower-Middle", "Middle", "Upper-Middle", "Large"
    check_size_min_mm: float         # Minimum equity check in $M
    check_size_max_mm: float
    industry_focus: List[str]
    geography_focus: List[str]
    investment_style: str            # "Growth", "Buyout", "Platform + Add-on"
    sector_keywords: List[str]       # For semantic matching
    portfolio_examples: List[str]    # Verifiable reference points
    thesis_summary: str              # One-line investment thesis


@dataclass
class FundMatch:
    """A scored PE fund match with transparent reasoning."""
    fund: PEFund
    total_score: float
    industry_score: float
    size_score: float
    geography_score: float
    strategic_score: float
    reasons: List[str]
    concerns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["fund"] = asdict(self.fund)
        return d


# ---------------------------------------------------------------------------
# PE Fund Database — 25 funds, publicly verifiable (from notebook)
# ---------------------------------------------------------------------------

PE_FUND_DATABASE: List[PEFund] = [
    # === LOWER MIDDLE MARKET ($5M-$75M checks) ===
    PEFund(
        name="Serent Capital",
        headquarters="San Francisco, CA",
        fund_size_category="Lower-Middle",
        check_size_min_mm=10, check_size_max_mm=75,
        industry_focus=["Software", "Tech-Enabled Services"],
        geography_focus=["North America"],
        investment_style="Growth",
        sector_keywords=["vertical SaaS", "B2B software", "tech services", "subscription"],
        portfolio_examples=["CentralSquare", "Mitratech", "Trintech"],
        thesis_summary="Growth-stage software and tech-enabled services businesses",
    ),
    PEFund(
        name="Riverside Company",
        headquarters="Cleveland, OH",
        fund_size_category="Lower-Middle",
        check_size_min_mm=10, check_size_max_mm=100,
        industry_focus=["Business Services", "Healthcare", "Consumer", "Manufacturing"],
        geography_focus=["North America", "Europe", "Asia-Pacific"],
        investment_style="Platform + Add-on",
        sector_keywords=["services", "healthcare services", "franchise", "specialty manufacturing"],
        portfolio_examples=["Franchise Group", "NexTech AR"],
        thesis_summary="Global PE focused on smaller businesses with growth potential via buy-and-build",
    ),
    PEFund(
        name="Mainsail Partners",
        headquarters="San Francisco, CA",
        fund_size_category="Lower-Middle",
        check_size_min_mm=5, check_size_max_mm=50,
        industry_focus=["Software"],
        geography_focus=["North America"],
        investment_style="Growth",
        sector_keywords=["B2B SaaS", "bootstrapped", "profitable software", "vertical software"],
        portfolio_examples=["Buildout", "Axon", "Formstack"],
        thesis_summary="Growth capital for bootstrapped B2B software companies",
    ),
    PEFund(
        name="Frontier Growth",
        headquarters="Charlotte, NC",
        fund_size_category="Lower-Middle",
        check_size_min_mm=10, check_size_max_mm=50,
        industry_focus=["Software", "Tech-Enabled Services"],
        geography_focus=["North America"],
        investment_style="Growth",
        sector_keywords=["SaaS", "recurring revenue", "tech-enabled", "B2B"],
        portfolio_examples=["LogRhythm", "Pax8"],
        thesis_summary="Growth equity for B2B software and tech-enabled businesses",
    ),
    PEFund(
        name="Norwest Equity Partners",
        headquarters="Minneapolis, MN",
        fund_size_category="Lower-Middle",
        check_size_min_mm=25, check_size_max_mm=150,
        industry_focus=["Manufacturing", "Business Services", "Healthcare"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["manufacturing", "industrial", "distribution", "healthcare services"],
        portfolio_examples=["Arctic Wolf", "Silver Peak"],
        thesis_summary="Middle-market buyouts in manufacturing and services",
    ),

    # === MIDDLE MARKET ($25M-$500M checks) ===
    PEFund(
        name="Vista Equity Partners",
        headquarters="Austin, TX",
        fund_size_category="Large",
        check_size_min_mm=100, check_size_max_mm=3000,
        industry_focus=["Software", "Data", "Technology"],
        geography_focus=["North America", "Europe", "Global"],
        investment_style="Buyout",
        sector_keywords=["enterprise software", "SaaS", "data", "B2B software", "vertical software"],
        portfolio_examples=["Tibco", "Ping Identity", "Jamf"],
        thesis_summary="Exclusive focus on enterprise software with operational improvement playbook",
    ),
    PEFund(
        name="Thoma Bravo",
        headquarters="San Francisco, CA",
        fund_size_category="Large",
        check_size_min_mm=50, check_size_max_mm=5000,
        industry_focus=["Software", "Financial Technology", "Security"],
        geography_focus=["North America", "Europe", "Global"],
        investment_style="Buyout",
        sector_keywords=["software", "fintech", "cybersecurity", "SaaS", "infrastructure software"],
        portfolio_examples=["SailPoint", "Sophos", "Ellie Mae"],
        thesis_summary="Software-focused PE with multiple fund strategies across size ranges",
    ),
    PEFund(
        name="Accel-KKR",
        headquarters="Menlo Park, CA",
        fund_size_category="Middle",
        check_size_min_mm=25, check_size_max_mm=300,
        industry_focus=["Software", "Tech-Enabled Services"],
        geography_focus=["North America", "Europe"],
        investment_style="Growth",
        sector_keywords=["software", "tech-enabled services", "SaaS", "recurring revenue"],
        portfolio_examples=["GoodHire", "Allocadia", "Smarsh"],
        thesis_summary="Growth and buyout investments in software and tech-enabled businesses",
    ),
    PEFund(
        name="HGGC",
        headquarters="Palo Alto, CA",
        fund_size_category="Middle",
        check_size_min_mm=50, check_size_max_mm=400,
        industry_focus=["Software", "Business Services", "Consumer"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["software", "services", "consumer", "middle market"],
        portfolio_examples=["AutoAlert", "myCase", "Dealer-FX"],
        thesis_summary="Middle-market buyouts partnering with management teams",
    ),
    PEFund(
        name="Summit Partners",
        headquarters="Boston, MA",
        fund_size_category="Middle",
        check_size_min_mm=25, check_size_max_mm=350,
        industry_focus=["Technology", "Healthcare", "Growth Services"],
        geography_focus=["North America", "Europe"],
        investment_style="Growth",
        sector_keywords=["software", "healthcare technology", "e-commerce", "tech-enabled"],
        portfolio_examples=["Ultimate Software", "FleetCor"],
        thesis_summary="Growth equity in technology and healthcare",
    ),
    PEFund(
        name="Insight Partners",
        headquarters="New York, NY",
        fund_size_category="Large",
        check_size_min_mm=10, check_size_max_mm=1000,
        industry_focus=["Software", "Technology"],
        geography_focus=["North America", "Europe", "Global"],
        investment_style="Growth",
        sector_keywords=["SaaS", "data", "AI", "cybersecurity", "fintech", "DevOps"],
        portfolio_examples=["Twitter", "Shopify", "DocuSign"],
        thesis_summary="Software-focused growth investor with ScaleUp operational platform",
    ),
    PEFund(
        name="Welsh, Carson, Anderson & Stowe",
        headquarters="New York, NY",
        fund_size_category="Middle",
        check_size_min_mm=100, check_size_max_mm=1000,
        industry_focus=["Healthcare", "Technology", "Business Services"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["healthcare IT", "healthcare services", "tech-enabled services"],
        portfolio_examples=["Ability Network", "Cambia Health"],
        thesis_summary="Healthcare and technology with deep sector expertise",
    ),
    PEFund(
        name="H.I.G. Capital",
        headquarters="Miami, FL",
        fund_size_category="Middle",
        check_size_min_mm=10, check_size_max_mm=300,
        industry_focus=["Manufacturing", "Healthcare", "Business Services", "Consumer"],
        geography_focus=["North America", "Europe", "Latin America"],
        investment_style="Buyout",
        sector_keywords=["specialty manufacturing", "healthcare services", "distribution", "industrials"],
        portfolio_examples=["Dynacast", "Techniplas"],
        thesis_summary="Flexible middle-market investor across multiple strategies",
    ),
    PEFund(
        name="Audax Private Equity",
        headquarters="Boston, MA",
        fund_size_category="Middle",
        check_size_min_mm=25, check_size_max_mm=250,
        industry_focus=["Business Services", "Consumer", "Healthcare", "Industrial"],
        geography_focus=["North America"],
        investment_style="Platform + Add-on",
        sector_keywords=["business services", "consumer services", "specialty distribution"],
        portfolio_examples=["Beam Dental", "K2 Insurance"],
        thesis_summary="Middle-market PE focused on buy-and-build strategies",
    ),
    PEFund(
        name="Battery Ventures",
        headquarters="Boston, MA",
        fund_size_category="Middle",
        check_size_min_mm=5, check_size_max_mm=150,
        industry_focus=["Software", "Technology"],
        geography_focus=["North America", "Europe", "Global"],
        investment_style="Growth",
        sector_keywords=["application software", "infrastructure", "industrial tech", "SaaS"],
        portfolio_examples=["Groupon", "Glassdoor", "Marketo"],
        thesis_summary="Technology-focused investor from seed to buyout",
    ),

    # === INDUSTRY-SPECIFIC ===
    PEFund(
        name="Great Hill Partners",
        headquarters="Boston, MA",
        fund_size_category="Middle",
        check_size_min_mm=25, check_size_max_mm=300,
        industry_focus=["Technology", "Healthcare", "Digital Media"],
        geography_focus=["North America"],
        investment_style="Growth",
        sector_keywords=["software", "digital media", "information services", "healthcare IT"],
        portfolio_examples=["Wayfair", "ZocDoc", "Bombas"],
        thesis_summary="Growth equity in technology and healthcare information businesses",
    ),
    PEFund(
        name="Clearlake Capital",
        headquarters="Santa Monica, CA",
        fund_size_category="Large",
        check_size_min_mm=50, check_size_max_mm=1500,
        industry_focus=["Software", "Industrials", "Consumer"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["software", "industrials", "consumer", "tech-enabled services"],
        portfolio_examples=["Symantec", "Wheel Pros", "STATS"],
        thesis_summary="Operationally-focused PE across software and industrials",
    ),
    PEFund(
        name="Genstar Capital",
        headquarters="San Francisco, CA",
        fund_size_category="Middle",
        check_size_min_mm=50, check_size_max_mm=500,
        industry_focus=["Financial Services", "Healthcare", "Industrial", "Software"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["financial services", "insurance", "healthcare", "industrial technology"],
        portfolio_examples=["Mercer Advisors", "Vensure"],
        thesis_summary="Middle-market buyouts in defensive growth sectors",
    ),
    PEFund(
        name="K1 Investment Management",
        headquarters="Manhattan Beach, CA",
        fund_size_category="Lower-Middle",
        check_size_min_mm=10, check_size_max_mm=100,
        industry_focus=["Software"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["enterprise software", "B2B SaaS", "vertical software"],
        portfolio_examples=["Apttus", "Buildium"],
        thesis_summary="Focused exclusively on enterprise software buyouts",
    ),
    PEFund(
        name="JMI Equity",
        headquarters="Baltimore, MD",
        fund_size_category="Middle",
        check_size_min_mm=25, check_size_max_mm=200,
        industry_focus=["Software"],
        geography_focus=["North America"],
        investment_style="Growth",
        sector_keywords=["software", "SaaS", "healthcare IT", "fintech"],
        portfolio_examples=["Phreesia", "Cision", "HighJump"],
        thesis_summary="Growth equity exclusively in software companies",
    ),

    # === HEALTHCARE FOCUSED ===
    PEFund(
        name="Lee Equity Partners",
        headquarters="New York, NY",
        fund_size_category="Middle",
        check_size_min_mm=50, check_size_max_mm=300,
        industry_focus=["Healthcare", "Business Services"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["healthcare services", "healthcare IT", "outsourced services"],
        portfolio_examples=["ExamWorks", "AdvancedMD"],
        thesis_summary="Middle-market healthcare and business services",
    ),
    PEFund(
        name="Water Street Healthcare Partners",
        headquarters="Chicago, IL",
        fund_size_category="Middle",
        check_size_min_mm=50, check_size_max_mm=400,
        industry_focus=["Healthcare"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["healthcare services", "healthcare products", "medical devices"],
        portfolio_examples=["Avalon Healthcare", "NuVasive"],
        thesis_summary="Exclusively focused on healthcare",
    ),

    # === INDUSTRIAL / MANUFACTURING ===
    PEFund(
        name="American Industrial Partners",
        headquarters="New York, NY",
        fund_size_category="Middle",
        check_size_min_mm=75, check_size_max_mm=500,
        industry_focus=["Industrial", "Manufacturing"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["industrial", "manufacturing", "aerospace", "defense", "chemicals"],
        portfolio_examples=["Drew Marine", "PSC Group"],
        thesis_summary="Industrial-focused PE with operational turnaround capability",
    ),
    PEFund(
        name="Stellex Capital",
        headquarters="New York, NY",
        fund_size_category="Lower-Middle",
        check_size_min_mm=25, check_size_max_mm=150,
        industry_focus=["Industrial", "Manufacturing", "Business Services"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["industrial", "manufacturing", "aerospace", "defense", "specialty chemicals"],
        portfolio_examples=["Wesco Aircraft", "MRS Packaging"],
        thesis_summary="Industrial middle-market with operational improvement focus",
    ),
    PEFund(
        name="One Rock Capital Partners",
        headquarters="New York, NY",
        fund_size_category="Middle",
        check_size_min_mm=50, check_size_max_mm=400,
        industry_focus=["Industrial", "Manufacturing", "Business Services"],
        geography_focus=["North America"],
        investment_style="Buyout",
        sector_keywords=["industrials", "manufacturing", "chemicals", "distribution"],
        portfolio_examples=["Ventura Foods", "Niacet"],
        thesis_summary="Operationally-focused PE in industrials and manufacturing",
    ),
]


# ---------------------------------------------------------------------------
# Revenue → estimated EV lookup (from notebook verbatim)
# ---------------------------------------------------------------------------

_REVENUE_TO_EV: Dict[str, Tuple[float, float]] = {
    "<$1M":       (1,   5),
    "$1M-$5M":    (3,   20),
    "$5M-$10M":   (15,  50),
    "$10M-$25M":  (30,  125),
    "$25M-$50M":  (75,  250),
    "$50M-$100M": (150, 500),
    "$100M+":     (300, 2000),
}

_HQ_TO_REGION_KEYWORDS: Dict[str, str] = {
    # North America
    "united states": "North America", "us": "North America", "usa": "North America",
    "canada": "North America", "north america": "North America",
    "new york": "North America", "san francisco": "North America",
    "chicago": "North America", "boston": "North America",
    "austin": "North America", "seattle": "North America",
    "los angeles": "North America", "dallas": "North America",
    "atlanta": "North America", "miami": "North America",
    "toronto": "North America", "montreal": "North America",
    # Europe
    "uk": "Europe", "united kingdom": "Europe", "london": "Europe",
    "germany": "Europe", "berlin": "Europe", "france": "Europe",
    "paris": "Europe", "netherlands": "Europe", "amsterdam": "Europe",
    "ireland": "Europe", "dublin": "Europe", "europe": "Europe",
    # Asia-Pacific
    "china": "Asia-Pacific", "japan": "Asia-Pacific", "india": "Asia-Pacific",
    "singapore": "Asia-Pacific", "australia": "Asia-Pacific",
    "asia": "Asia-Pacific", "asia-pacific": "Asia-Pacific",
    # Latin America
    "brazil": "Latin America", "mexico": "Latin America", "latin america": "Latin America",
}


def _hq_to_region(hq: str) -> str:
    """Map a headquarters string to a region name."""
    if not hq:
        return "North America"  # Default assumption
    hq_lower = hq.lower()
    for keyword, region in _HQ_TO_REGION_KEYWORDS.items():
        if keyword in hq_lower:
            return region
    return "Global"


def _revenue_ltm_to_range(ltm_raw: Any) -> str:
    """Convert a raw LTM revenue number to the revenue-range string used in REVENUE_TO_EV."""
    if ltm_raw is None or ltm_raw == "not_provided":
        return "$10M-$25M"  # Fallback midpoint assumption
    try:
        v = float(ltm_raw)
        # Heuristic: values ≥1M assume the document uses full dollars
        if v >= 1_000_000:
            v /= 1_000_000  # Convert to $M
        # Now v is in $M
        if v < 1:
            return "<$1M"
        if v < 5:
            return "$1M-$5M"
        if v < 10:
            return "$5M-$10M"
        if v < 25:
            return "$10M-$25M"
        if v < 50:
            return "$25M-$50M"
        if v < 100:
            return "$50M-$100M"
        return "$100M+"
    except (ValueError, TypeError):
        return "$10M-$25M"


# ---------------------------------------------------------------------------
# Matching Engine — same scoring logic as the notebook, input adapted to dict
# ---------------------------------------------------------------------------

class MatchingEngine:
    """Scores PE funds against a CIM extraction dict.

    Scoring weights (from notebook):
        Industry fit:   30%
        Size fit:       25%
        Geography:      15%
        Strategic fit:  30%

    Usage:
        engine = MatchingEngine()
        matches = engine.match(extracted_data, top_n=5)
    """

    def __init__(self, funds: Optional[List[PEFund]] = None):
        self.funds = funds or PE_FUND_DATABASE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match(
        self,
        extracted_data: Dict[str, Any],
        top_n: int = 5,
    ) -> List[FundMatch]:
        """Score all funds against CIM data and return top-N matches.

        Args:
            extracted_data: Structured dict from CIMExtractor.
            top_n: Number of top matches to return.

        Returns:
            List of FundMatch objects sorted by total_score descending.
        """
        # Build internal proxy fields (mirrors CompanyProfile from notebook)
        co          = extracted_data.get("company_overview", {})
        fin         = extracted_data.get("financials", {})
        market      = extracted_data.get("market", {})

        industry    = co.get("industry", "")
        sub_industry= co.get("sub_industry", "")
        biz_model   = co.get("business_model", "B2B")
        hq          = co.get("headquarters", "")
        description = co.get("description", "")
        region      = _hq_to_region(hq)
        rev_range   = _revenue_ltm_to_range(fin.get("revenue", {}).get("ltm"))

        # Derive keywords from available structured data
        keywords = _build_keywords(co, market)
        value_prop = description or f"{industry} {biz_model} company"

        matches: List[FundMatch] = []

        for fund in self.funds:
            all_reasons: List[str] = []
            all_concerns: List[str] = []

            # 1. Industry fit (30%)
            ind_score, ind_reasons = self._industry_score(
                industry, sub_industry, keywords, fund
            )
            all_reasons.extend(ind_reasons)

            # 2. Size fit (25%)
            size_score, size_reasons, size_concerns = self._size_score(
                rev_range, fund
            )
            all_reasons.extend(size_reasons)
            all_concerns.extend(size_concerns)

            # 3. Geography (15%)
            geo_score, geo_reasons = self._geography_score(region, fund)
            all_reasons.extend(geo_reasons)

            # 4. Strategic fit (30%)
            strat_score, strat_reasons = self._strategic_score(
                biz_model, value_prop, fin, fund
            )
            all_reasons.extend(strat_reasons)

            # Weighted composite (from notebook)
            total = (
                ind_score   * 0.30 +
                size_score  * 0.25 +
                geo_score   * 0.15 +
                strat_score * 0.30
            )

            matches.append(FundMatch(
                fund=fund,
                total_score=round(total, 3),
                industry_score=round(ind_score, 2),
                size_score=round(size_score, 2),
                geography_score=round(geo_score, 2),
                strategic_score=round(strat_score, 2),
                reasons=all_reasons,
                concerns=all_concerns,
            ))

        matches.sort(key=lambda m: m.total_score, reverse=True)
        return matches[:top_n]

    # ------------------------------------------------------------------
    # Dimension scorers — logic from notebook, parameters adapted
    # ------------------------------------------------------------------

    @staticmethod
    def _industry_score(
        industry: str,
        sub_industry: str,
        keywords: List[str],
        fund: PEFund,
    ) -> Tuple[float, List[str]]:
        """Score industry alignment using keyword matching (notebook verbatim)."""
        score = 0.0
        reasons: List[str] = []

        ind_lower = industry.lower()
        sub_lower = sub_industry.lower()
        kw_lower  = [k.lower() for k in keywords]

        # Primary industry match
        for fund_ind in fund.industry_focus:
            if (fund_ind.lower() in ind_lower or ind_lower in fund_ind.lower()):
                score = 0.7
                reasons.append(f"Industry match: {fund_ind}")
                break

        # Sector keyword bonus
        keyword_matches = sum(
            1 for kw in fund.sector_keywords
            if any(kw.lower() in ckw or ckw in kw.lower()
                   for ckw in kw_lower + [sub_lower])
        )
        if keyword_matches > 0:
            bonus = min(0.3, keyword_matches * 0.10)
            score = min(1.0, score + bonus)
            reasons.append(f"Sector keyword alignment ({keyword_matches} matches)")

        return score, reasons

    @staticmethod
    def _size_score(
        rev_range: str,
        fund: PEFund,
    ) -> Tuple[float, List[str], List[str]]:
        """Score size fit: company EV vs fund check-size range (notebook verbatim)."""
        reasons: List[str] = []
        concerns: List[str] = []

        if rev_range not in _REVENUE_TO_EV:
            return 0.5, ["Unable to estimate company valuation"], concerns

        ev_min, ev_max = _REVENUE_TO_EV[rev_range]
        check_min = fund.check_size_min_mm
        check_max = fund.check_size_max_mm

        # Implied check = 30-60% of EV (typical PE equity ownership)
        implied_check_min = ev_min * 0.3
        implied_check_max = ev_max * 0.6

        if implied_check_max < check_min:
            concerns.append(
                f"Company likely too small (est. ${ev_min}–${ev_max}M EV "
                f"vs ${check_min}M+ checks)"
            )
            return 0.2, reasons, concerns

        if implied_check_min > check_max:
            concerns.append("Company may be too large for this fund")
            return 0.3, reasons, concerns

        overlap_start = max(implied_check_min, check_min)
        overlap_end   = min(implied_check_max, check_max)

        if overlap_end > overlap_start:
            score = 0.7 + 0.3 * (
                (overlap_end - overlap_start) /
                max(implied_check_max - implied_check_min, 1)
            )
            reasons.append(
                f"Size fit: {rev_range} revenue aligns with "
                f"${check_min}–${check_max}M check range"
            )
            return min(1.0, score), reasons, concerns

        return 0.5, reasons, concerns

    @staticmethod
    def _geography_score(
        region: str,
        fund: PEFund,
    ) -> Tuple[float, List[str]]:
        """Score geographic alignment (notebook verbatim)."""
        reasons: List[str] = []
        region_lower = region.lower()

        for geo in fund.geography_focus:
            if (geo.lower() == "global" or
                    geo.lower() in region_lower or
                    region_lower in geo.lower()):
                reasons.append(f"Geographic fit: {geo}")
                return 1.0, reasons

        return 0.3, reasons

    @staticmethod
    def _strategic_score(
        biz_model: str,
        value_prop: str,
        fin: Dict,
        fund: PEFund,
    ) -> Tuple[float, List[str]]:
        """Score strategic fit against fund thesis (notebook verbatim + CIM-adapted)."""
        reasons: List[str] = []
        score = 0.5  # Baseline

        keywords_joined = " ".join(fund.sector_keywords).lower()

        # B2B + SaaS alignment
        if biz_model.upper() in ("B2B", "SAAS") and "saas" in keywords_joined:
            score += 0.2
            reasons.append("B2B model aligns with fund's SaaS focus")

        # Recurring revenue alignment
        recurring = fin.get("recurring_revenue_pct")
        if recurring and recurring != "not_provided":
            try:
                r = float(recurring)
                if r > 0.60 and "recurring revenue" in keywords_joined:
                    score += 0.2
                    reasons.append(
                        f"High recurring revenue ({r:.0%}) matches fund preference"
                    )
                elif r > 0.40:
                    score += 0.1
                    reasons.append(f"Meaningful recurring revenue ({r:.0%})")
            except (ValueError, TypeError):
                pass

        # Value proposition signal
        vp_lower = value_prop.lower()
        if ("recurring" in vp_lower or "subscription" in vp_lower) and \
                "recurring revenue" in keywords_joined:
            score += 0.1
            reasons.append("Recurring revenue model matches fund preference")

        # Platform + Add-on potential
        if fund.investment_style == "Platform + Add-on":
            reasons.append("Fund uses buy-and-build strategy — potential platform or add-on")
            score += 0.1

        return min(1.0, score), reasons


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_keywords(
    co: Dict[str, Any],
    market: Dict[str, Any],
) -> List[str]:
    """Derive keyword list from CIM extraction fields."""
    kws: List[str] = []
    for field_val in [
        co.get("industry"), co.get("sub_industry"),
        co.get("business_model"),
    ]:
        if field_val and field_val != "not_provided":
            kws.extend(field_val.lower().split())

    for trend in market.get("key_trends", []):
        if isinstance(trend, str):
            kws.extend(trend.lower().split()[:3])

    for comp in market.get("key_competitors", []):
        if isinstance(comp, str):
            kws.append(comp.lower())

    return list(dict.fromkeys(kws))  # Deduplicate, preserve order


def display_matches(
    extracted_data: Dict[str, Any],
    matches: List[FundMatch],
):
    """Pretty-print fund match results (mirrors notebook output)."""
    co = extracted_data.get("company_overview", {})
    print(f"\n{'=' * 65}")
    print(f"  PE FUND MATCHES — {co.get('company_name', 'Unknown Company')}")
    print(f"{'=' * 65}")

    for i, m in enumerate(matches, 1):
        fund = m.fund
        print(f"\n#{i}. {fund.name} — Score: {m.total_score:.0%}")
        print(f"   📍 {fund.headquarters} | {fund.fund_size_category} Market")
        print(f"   💰 Check: ${fund.check_size_min_mm}M–${fund.check_size_max_mm}M")
        print(f"   🎯 Focus: {', '.join(fund.industry_focus[:3])}")
        print(f"   📝 Thesis: {fund.thesis_summary}")
        print(
            f"   📊 Industry {m.industry_score:.0%} | "
            f"Size {m.size_score:.0%} | "
            f"Geo {m.geography_score:.0%} | "
            f"Strategic {m.strategic_score:.0%}"
        )
        for reason in m.reasons[:3]:
            print(f"   ✅ {reason}")
        for concern in m.concerns:
            print(f"   ⚠️  {concern}")
