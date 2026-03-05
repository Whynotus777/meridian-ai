"""Meridian AI — Streamlit web application.

Upload a document → progress tracking → tabbed analysis display:
  Memo | Financials | Risks | Comps | Score | Q&A

Run with:
    streamlit run app.py
"""

import io
import html
import os
import re
import sys
import tempfile
import time
import zipfile
from typing import Optional

import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Meridian AI",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)
try:
    st.set_option("server.runOnSave", False)
except Exception:
    pass

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
    .main .block-container {
        padding-top: 1.25rem;
        padding-left: 2rem;
        padding-right: 2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* ── Brand tokens ──────────────────────────────────────────────────── */
    :root {
        --accent:     #E07A5F;
        --accent-dim: #b05f47;
        --green:      #4caf50;
        --amber:      #ffc107;
        --red:        #ef5350;
        --blue-muted: #a8c4e0;
        --bg-card:    #1c1c2e;
        --bg-card2:   #16162a;
        --border:     #2a2a4a;
        --text-muted: #8888aa;
        --text-dim:   #555577;
    }

    /* ── Top bar ───────────────────────────────────────────────────────── */
    header[data-testid="stHeader"] { background-color: #0a0a12; }

    /* ── Sidebar ───────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] { background-color: #0d0d1f; }
    section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }

    /* ── Metric cards ──────────────────────────────────────────────────── */
    div[data-testid="metric-container"] {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 0.75rem 1rem;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.22);
    }

    /* ── Severity badges ───────────────────────────────────────────────── */
    .badge-critical { background:#ef5350; color:#fff; padding:2px 9px; border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-high     { background:#ff7043; color:#fff; padding:2px 9px; border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-medium   { background:#ffc107; color:#111; padding:2px 9px; border-radius:4px; font-size:0.78rem; font-weight:600; }
    .badge-low      { background:#4caf50; color:#fff; padding:2px 9px; border-radius:4px; font-size:0.78rem; font-weight:600; }

    /* ── Score progress bars ───────────────────────────────────────────── */
    .score-bar-bg { background:var(--border); border-radius:4px; height:10px; margin-top:3px; }
    .score-bar-fg { height:10px; border-radius:4px; }

    /* ── Chat bubbles ──────────────────────────────────────────────────── */
    .chat-user      { background:#1e2a40; border-radius:12px; padding:0.6rem 1rem; margin:4px 0; }
    .chat-assistant { background:#1a2e20; border-radius:12px; padding:0.6rem 1rem; margin:4px 0; }

    /* ── Sidebar logo ──────────────────────────────────────────────────── */
    .meridian-logo {
        font-size: 1.65rem;
        font-weight: 800;
        color: #e8e8e8;
        letter-spacing: -0.5px;
        padding: 0.3rem 0 0.15rem 0;
        line-height: 1;
    }
    .meridian-logo span { color: var(--accent); }
    .meridian-home-link {
        display: block;
        text-decoration: none !important;
        background: transparent !important;
        border: 0 !important;
        cursor: pointer;
        padding: 0;
        margin: 0;
    }
    .meridian-home-link:hover,
    .meridian-home-link:focus,
    .meridian-home-link:active {
        text-decoration: none !important;
        outline: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }
    .meridian-home-logo {
        font-size: 1.65rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        padding: 0.3rem 0 0.15rem 0;
        line-height: 1;
    }
    .meridian-home-meridian { color: var(--accent); }
    .meridian-home-ai { color: #e8e8e8; }

    /* ── Tagline under logo ────────────────────────────────────────────── */
    .meridian-tagline {
        font-size: 0.72rem;
        color: var(--text-muted);
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0;
        margin-top: 0.15rem;
    }

    /* ── Footer ────────────────────────────────────────────────────────── */
    .meridian-footer {
        text-align: center;
        color: var(--text-dim);
        font-size: 0.75rem;
        margin-top: 4rem;
        padding: 1rem;
        border-top: 1px solid var(--border);
    }

    /* ── Memo section headers ──────────────────────────────────────────── */
    .memo-section-header {
        color: var(--blue-muted);
        font-size: 1rem;
        font-weight: 700;
        margin-top: 2rem;
        margin-bottom: 0.3rem;
        padding-bottom: 0.25rem;
        border-bottom: 1px solid var(--border);
        letter-spacing: 0.03em;
        text-transform: uppercase;
    }

    /* ── Section subheader (used inside tabs) ──────────────────────────── */
    .section-label {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--text-muted);
        margin-bottom: 0.4rem;
    }

    /* ── Info cards ─────────────────────────────────────────────────────── */
    .info-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1rem;
    }
    .info-card h4 {
        color: var(--blue-muted);
        margin-bottom: 0.3rem;
        font-size: 1rem;
    }
    .info-card p { color: #9090a8; margin: 0; font-size: 0.9rem; }

    /* ── Risk section headers ──────────────────────────────────────────── */
    .risk-section-title {
        color: var(--blue-muted);
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 0.15rem;
    }
    .risk-section-desc {
        color: var(--text-muted);
        font-size: 0.82rem;
        margin-top: 0;
        margin-bottom: 0.8rem;
    }

    .wire-card {
        border: 1px solid #2d2d50;
        border-radius: 10px;
        background: rgba(16, 17, 31, 0.78);
        padding: 0.75rem 0.85rem;
        transition: border-color 0.15s ease, transform 0.15s ease;
    }
    .wire-card:hover {
        border-color: #4b5f9c;
        transform: translateY(-1px);
    }
    .wire-title {
        color: #d8defa;
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.5rem;
        font-weight: 700;
    }
    .wire-row {
        display: flex;
        justify-content: space-between;
        gap: 0.7rem;
        color: #98a0cd;
        border-top: 1px solid #272847;
        padding: 0.45rem 0;
        font-size: 0.86rem;
    }
    .wire-row:first-child { border-top: 0; padding-top: 0.1rem; }
    .health-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .btn-ghost {
        border: 1px solid #3a3a63;
        color: #d3d7f8;
        background: #1a1b30;
        border-radius: 8px;
        padding: 0.38rem 0.72rem;
        font-size: 0.8rem;
        font-weight: 700;
        display: inline-block;
        margin-right: 0.45rem;
    }

    .hero-metric-card {
        background: linear-gradient(180deg, #1b1b31, #18182b);
        border: 1px solid #2c3357;
        border-radius: 10px;
        padding: 0.7rem 0.85rem;
    }
    .hero-metric-label {
        color: #8d94c5;
        font-size: 0.72rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    .hero-metric-value {
        color: #edf0ff;
        font-size: 1.2rem;
        font-weight: 700;
        line-height: 1.15;
    }

    .memo-content ul {
        margin-left: 1.25rem;
        padding-left: 0.9rem;
    }
    .memo-content li {
        margin-bottom: 0.3rem;
    }
    .verification-summary {
        border: 1px solid #2f3558;
        background: #171a2b;
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        margin-top: 0.8rem;
        margin-bottom: 0.55rem;
    }
    .verification-title {
        color: #dbe3ff;
        font-weight: 700;
        font-size: 0.9rem;
        margin-bottom: 0.2rem;
    }
    .verification-line {
        color: #bcc5ec;
        font-size: 0.85rem;
    }
    .verification-chip-green { color: #65d38b; font-weight: 700; }
    .verification-chip-amber { color: #f2c86b; font-weight: 700; }
    .verification-chip-red { color: #ef7a7a; font-weight: 700; }
    .verification-badge {
        display: inline-block;
        padding: 0.12rem 0.5rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 700;
        margin-left: 0.4rem;
    }
    .verification-badge-high { background: #1f5d35; color: #baf0cc; }
    .verification-badge-medium { background: #6a531f; color: #f7df9e; }
    .verification-badge-low { background: #6a2222; color: #ffb5b5; }
    .insight-card {
        background: #171a2b;
        border: 1px solid #2f3558;
        border-left-width: 4px;
        border-radius: 10px;
        padding: 0.65rem 0.8rem;
        margin-bottom: 0.55rem;
    }
    .insight-positive { border-left-color: #4caf50; }
    .insight-info { border-left-color: #4f8bd8; }
    .insight-warning { border-left-color: #f0b34f; }
    .insight-title {
        color: #e8edff;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .insight-detail {
        color: #c3cae8;
        font-size: 0.9rem;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

_PRESET_WEIGHTS = {
    "balanced":     {"market_attractiveness": 20, "financial_quality": 30, "growth_profile": 20, "management_strength": 10, "risk_factors": 20},
    "conservative": {"market_attractiveness": 15, "financial_quality": 35, "growth_profile": 15, "management_strength": 10, "risk_factors": 25},
    "growth":       {"market_attractiveness": 25, "financial_quality": 20, "growth_profile": 30, "management_strength": 10, "risk_factors": 15},
}

_MEMO_SECTION_LABELS = [
    ("executive_summary",       "Executive Summary"),
    ("company_overview",        "Company Overview"),
    ("financial_highlights",    "Financial Highlights"),
    ("growth_thesis",           "Growth Thesis"),
    ("key_risks_and_mitigants", "Key Risks & Mitigants"),
    ("valuation_context",       "Valuation Context"),
    ("key_diligence_questions", "Key Diligence Questions"),
    ("recommendation",          "Recommendation"),
]

_SLIDER_DIMS = [
    ("market_attractiveness", "Market Attractiveness", 0, 50),
    ("financial_quality",     "Financial Quality",     0, 50),
    ("growth_profile",        "Growth Profile",        0, 50),
    ("management_strength",   "Management Strength",   0, 30),
    ("risk_factors",          "Risk Profile",          0, 50),
]

_SECTOR_FLAGS = {
    "Education & EdTech": [
        ("📚", "Title IV / Federal Funding Dependency",
         "Assess exposure to changes in federal education funding, student loan policies, "
         "or Title IV compliance requirements. For higher-ed adjacent businesses, determine "
         "what percentage of end-customer revenue flows through federal programs."),
        ("📅", "Enrollment & Budget Cycle Risk",
         "K-12 revenue is tied to district budget approval cycles (typically March–June). "
         "Higher ed enrollment is subject to demographic trends and yield uncertainty. "
         "Model downside scenarios for enrollment declines and delayed budget approvals."),
        ("🔒", "FERPA / COPPA / Student Data Privacy",
         "Verify compliance with FERPA (K-12 and higher ed student records), COPPA (under-13 "
         "data collection), and applicable state privacy laws (e.g., SOPIPA in California). "
         "Non-compliance is a deal-breaker for district and institutional procurement."),
        ("📊", "State Adoption & Procurement",
         "For K-12: determine whether the product is on state adoption lists or approved vendor "
         "registries. District procurement cycles can run 12–18 months and are subject to board "
         "approval. RFP requirements and sole-source justifications vary significantly by state."),
        ("🔄", "Implementation Seasonality",
         "K-12 implementations are typically limited to summer months (June–August). "
         "This compresses the deployment window, concentrates professional services revenue, "
         "and increases churn risk if go-lives slip. Factor into revenue recognition timing "
         "and working capital requirements."),
    ],
    "Healthcare": [
        ("🏥", "Reimbursement & Payer Mix Risk",
         "Analyze revenue concentration across Medicare, Medicaid, and commercial payers. "
         "Assess exposure to CMS rate changes, prior authorization expansion, and state "
         "Medicaid redetermination cycles that can compress reimbursement rates."),
        ("🔒", "HIPAA / HITECH Compliance",
         "Confirm BAA coverage across all vendor and partner relationships. Review breach "
         "history, security incident response protocols, and cyber insurance adequacy. "
         "OCR enforcement actions can generate material liability."),
        ("🧬", "FDA Regulatory Pathway",
         "For health tech or device-adjacent businesses, clarify FDA classification (510(k), "
         "De Novo, PMA). Confirm predicate device strategy and any open 483 observations "
         "or warning letters that could delay clearance timelines."),
        ("👨‍⚕️", "Clinical & Physician Dependency",
         "Assess key-person risk tied to physician founders, medical directors, or clinical "
         "advisory relationships. Model attrition scenarios and evaluate non-compete "
         "enforceability in applicable jurisdictions."),
    ],
    "Financial Services": [
        ("🏦", "Regulatory Capital & Licensing",
         "Confirm all applicable licenses (state money transmitter, broker-dealer, RIA, "
         "bank charter) are current and transferable post-close. Assess net capital "
         "requirements and the impact of leverage targets on return profile."),
        ("📉", "Interest Rate & Credit Sensitivity",
         "Model revenue and NIM sensitivity across +/- 200bps rate scenarios. For "
         "lending businesses, stress-test the loan portfolio against historical default "
         "rates and assess reserve adequacy relative to CECL requirements."),
        ("🔍", "AML / KYC / BSA Compliance",
         "Review BSA/AML program adequacy, SAR filing history, and any prior FinCEN or "
         "OCC consent orders. Assess transaction monitoring system coverage and "
         "false-positive rates that indicate manual review bottlenecks."),
        ("⚖️", "CFPB & Consumer Protection Exposure",
         "For consumer-facing products, evaluate UDAAP risk, fair lending compliance "
         "(ECOA, Fair Housing Act), and any open CFPB supervisory matters. "
         "Class action exposure in consumer finance can be difficult to quantify."),
    ],
    "Technology / SaaS": [
        ("📉", "Customer Concentration & Churn Risk",
         "Identify revenue concentration in top 5 and top 10 customers. Benchmark gross "
         "and net revenue retention against SaaS peers. Understand logo churn drivers "
         "and whether expansion revenue offsets contraction."),
        ("🔄", "R&D Velocity & Technical Debt",
         "Assess engineering headcount relative to ARR, deployment cadence, and release "
         "quality metrics (bug rate, P0 incidents). Material technical debt can "
         "compress R&D capacity post-close and delay product roadmap delivery."),
        ("☁️", "Cloud Infrastructure Dependency",
         "Quantify AWS/Azure/GCP concentration and contract terms. Assess gross margin "
         "sensitivity to cloud cost increases and evaluate the feasibility of "
         "infrastructure optimization as a post-close value creation lever."),
        ("🔒", "Data Privacy (GDPR / CCPA / State Laws)",
         "Confirm GDPR and CCPA compliance programs, including DPA execution, "
         "data subject request workflows, and consent management infrastructure. "
         "State privacy law proliferation (Virginia, Colorado, Texas, etc.) "
         "increases compliance overhead for multi-state SaaS businesses."),
    ],
    "General": [],
}

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "document" not in st.session_state:
    st.session_state.document = None
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "fund_matches" not in st.session_state:
    st.session_state.fund_matches = None
if "_exports_for" not in st.session_state:
    st.session_state["_exports_for"] = None
if "_preview_panel" not in st.session_state:
    st.session_state["_preview_panel"] = None
if "analyzed_deals" not in st.session_state:
    st.session_state["analyzed_deals"] = []
if "_pipeline_inline_upload" not in st.session_state:
    st.session_state["_pipeline_inline_upload"] = False
if "firm_mandate" not in st.session_state:
    st.session_state["firm_mandate"] = {
        "firm_name": "",
        "target_revenue_min_m": 0.0,
        "target_revenue_max_m": 10000.0,
        "min_ebitda_margin_pct": 0.0,
        "target_sectors": [],
        "min_recurring_revenue_pct": 0.0,
    }

# Configure panel state
if "_scoring_profile" not in st.session_state:
    st.session_state["_scoring_profile"] = "balanced"
if "industry_profile" not in st.session_state:
    st.session_state["industry_profile"] = "General"
for _dim, _, _, _ in _SLIDER_DIMS:
    if f"_w_{_dim}" not in st.session_state:
        st.session_state[f"_w_{_dim}"] = _PRESET_WEIGHTS["balanced"][_dim]
for _sec_key, _ in _MEMO_SECTION_LABELS:
    if f"_msec_{_sec_key}" not in st.session_state:
        st.session_state[f"_msec_{_sec_key}"] = True

# Home navigation via clickable sidebar logo
_home_qp = str(st.query_params.get("home", "")).lower()
if _home_qp in ("1", "true", "yes"):
    st.session_state.result = None
    st.session_state.document = None
    st.session_state.messages = []
    st.session_state.fund_matches = None
    st.session_state["_preview_panel"] = None
    st.session_state["_pipeline_inline_upload"] = False
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.rerun()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_num(val) -> str:
    """Format a raw-USD financial value returned by the LLM.

    The extraction prompt instructs the LLM to normalise all monetary values
    to raw USD integers (628000 for $628K, 258500000 for $258.5M).

    Defensively handles legacy/unexpected suffixed strings:
        "628k"  → 628 * 1,000       = 628,000
        "258m"  → 258 * 1,000,000   = 258,000,000
        "1.2b"  → 1.2 * 1,000,000,000
    """
    if val is None or val == "not_provided":
        return "N/A"

    if isinstance(val, str):
        s = val.strip().replace(",", "").replace("$", "")
        if not s or s.lower() in ("n/a", "not_provided", "none"):
            return "N/A"
        sl = s.lower()
        try:
            if sl.endswith("b"):
                v = float(sl[:-1]) * 1_000_000_000
            elif sl.endswith("m"):
                v = float(sl[:-1]) * 1_000_000
            elif sl.endswith("k"):
                v = float(sl[:-1]) * 1_000
            else:
                v = float(s)
        except ValueError:
            return str(val)
    else:
        try:
            v = float(val)
        except (ValueError, TypeError):
            return str(val)

    # v is raw USD — scale to human-readable
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1_000_000_000:
        return f"{sign}${av / 1_000_000_000:.1f}B"
    if av >= 1_000_000:
        return f"{sign}${av / 1_000_000:.1f}M"
    if av >= 1_000:
        return f"{sign}${av / 1_000:.1f}K"
    return f"{sign}${av:,.0f}"


def _fmt_pct(val) -> str:
    if val is None or val == "not_provided":
        return "N/A"
    try:
        return f"{float(val):.1%}"
    except (ValueError, TypeError):
        return str(val)


def _to_float_or_none(val):
    if val is None or val == "not_provided":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _downgrade_recommendation(rec: str) -> str:
    ladder = [
        "Strong Pursue",
        "Pursue",
        "Conditional",
        "Likely Pass — significant concerns",
        "Pass",
    ]
    if rec not in ladder:
        return rec
    idx = ladder.index(rec)
    return ladder[min(idx + 1, len(ladder) - 1)]


def _evaluate_mandate_fit(extracted_data: dict, mandate: dict) -> dict:
    co = extracted_data.get("company_overview", {})
    fin = extracted_data.get("financials", {})
    ebitda = fin.get("ebitda", {})
    rev_ltm = _to_float_or_none(fin.get("revenue", {}).get("ltm"))
    ebitda_margin = _to_float_or_none(ebitda.get("margin_ltm"))
    recurring = _to_float_or_none(fin.get("recurring_revenue_pct"))
    sector = (co.get("industry") or "").strip()
    sub_sector = (co.get("sub_industry") or "").strip()
    selected_profile = (st.session_state.get("industry_profile") or "").strip()

    if ebitda_margin is None and rev_ltm and rev_ltm != 0:
        ebitda_candidate = (
            _to_float_or_none(ebitda.get("ltm"))
            or _to_float_or_none(ebitda.get("adjusted_ebitda_ltm"))
            or _to_float_or_none(ebitda.get("derived_ebitda"))
        )
        if ebitda_candidate is not None:
            ebitda_margin = ebitda_candidate / rev_ltm

    crit = []
    rev_min_m = float(mandate.get("target_revenue_min_m", 0) or 0)
    rev_max_m = float(mandate.get("target_revenue_max_m", 10000) or 10000)
    min_margin_pct = float(mandate.get("min_ebitda_margin_pct", 0) or 0)
    min_rec_pct = float(mandate.get("min_recurring_revenue_pct", 0) or 0)
    sectors = mandate.get("target_sectors") or []

    if rev_min_m > 0 or rev_max_m < 10000:
        if rev_ltm is None:
            crit.append((False, f"❌ Revenue not provided; target range is ${rev_min_m:.0f}M-${rev_max_m:.0f}M"))
        else:
            rev_m = rev_ltm / 1_000_000
            passed = rev_min_m <= rev_m <= rev_max_m
            if passed:
                crit.append((True, f"✅ Revenue ${rev_m:.0f}M within ${rev_min_m:.0f}M-${rev_max_m:.0f}M range"))
            else:
                crit.append((False, f"❌ Revenue ${rev_m:.0f}M outside ${rev_min_m:.0f}M-${rev_max_m:.0f}M range"))

    if min_margin_pct > 0:
        if ebitda_margin is None:
            crit.append((False, f"❌ EBITDA margin not provided; minimum is {min_margin_pct:.1f}%"))
        else:
            margin_pct = ebitda_margin * 100
            passed = margin_pct >= min_margin_pct
            if passed:
                crit.append((True, f"✅ EBITDA margin {margin_pct:.1f}% meets {min_margin_pct:.1f}% minimum"))
            else:
                crit.append((False, f"❌ EBITDA margin {margin_pct:.1f}% below {min_margin_pct:.1f}% minimum"))

    if sectors:
        # Fuzzy matching over extracted industry + sub-industry + user-selected profile
        candidates = [x for x in [sector, sub_sector, selected_profile] if x]
        candidates_lc = [c.lower() for c in candidates]

        # Common extracted-label variations -> mandate sectors
        variation_map = {
            "software": ["Enterprise Software"],
            "enterprise software": ["Enterprise Software"],
            "saas": ["Enterprise Software"],
            "education technology": ["Education & EdTech"],
            "edtech": ["Education & EdTech"],
            "education": ["Education & EdTech"],
            "learning": ["Education & EdTech"],
            "healthcare": ["Healthcare"],
            "healthcare it": ["Healthcare"],
            "fintech": ["Fintech"],
            "financial services": ["Fintech"],
            "industrial": ["Industrials"],
            "consumer": ["Consumer"],
            "cyber": ["Cybersecurity"],
            "cybersecurity": ["Cybersecurity"],
            "infrastructure": ["Infrastructure"],
            "gaming": ["Gaming & Entertainment"],
            "entertainment": ["Gaming & Entertainment"],
        }

        sector_keywords = {
            "Healthcare": ["healthcare", "health tech", "healthtech", "medical", "provider"],
            "Education & EdTech": ["education", "edtech", "learning", "school", "student", "k-12", "k12", "curriculum", "lms"],
            "Enterprise Software": ["enterprise software", "software", "saas", "b2b software", "platform"],
            "Fintech": ["fintech", "financial services", "payments", "banking", "lending"],
            "Industrials": ["industrial", "manufacturing", "factory", "logistics"],
            "Consumer": ["consumer", "retail", "ecommerce", "e-commerce", "d2c"],
            "Cybersecurity": ["cybersecurity", "cyber", "security software", "infosec"],
            "Infrastructure": ["infrastructure", "data center", "utilities", "network infrastructure"],
            "Gaming & Entertainment": ["gaming", "entertainment", "media", "esports"],
            "Other": ["other"],
        }

        matched_targets = set()

        # Direct contains/equality checks against selected mandate sectors
        for target in sectors:
            tl = target.lower()
            if any(tl in c for c in candidates_lc):
                matched_targets.add(target)

        # Keyword-based matching to canonical mandate sectors
        for target in sectors:
            kws = sector_keywords.get(target, [])
            if any(any(kw in c for kw in kws) for c in candidates_lc):
                matched_targets.add(target)

        # Variation map matching
        for c in candidates_lc:
            for variant, mapped_targets in variation_map.items():
                if variant in c:
                    for mt in mapped_targets:
                        if mt in sectors:
                            matched_targets.add(mt)

        passed = len(matched_targets) > 0
        if passed:
            match_list = ", ".join(sorted(matched_targets))
            crit.append((True, f"✅ Sector match via: {match_list}"))
        else:
            crit.append((
                False,
                f"❌ Sector mismatch. Extracted: '{sector or 'Unknown'}'"
                f"{f' / {sub_sector}' if sub_sector else ''}; Profile: '{selected_profile or 'General'}'"
            ))

    if min_rec_pct > 0:
        if recurring is None:
            crit.append((False, f"❌ Recurring revenue not provided; minimum is {min_rec_pct:.1f}%"))
        else:
            rec_pct = recurring * 100
            passed = rec_pct >= min_rec_pct
            if passed:
                crit.append((True, f"✅ Recurring revenue {rec_pct:.1f}% meets {min_rec_pct:.1f}% minimum"))
            else:
                crit.append((False, f"❌ Recurring revenue {rec_pct:.1f}% below {min_rec_pct:.1f}% minimum"))

    total = len(crit)
    passed_n = sum(1 for p, _ in crit if p)
    fit_pct = int(round((passed_n / total) * 100)) if total else None
    failed_n = total - passed_n
    return {
        "criteria": crit,
        "fit_pct": fit_pct,
        "failed_n": failed_n,
        "active_criteria": total,
    }


def _fmt_str(val) -> str:
    """Return a display-safe string, converting sentinel 'not_provided' to 'N/A'."""
    if val is None or str(val).lower() in ("not_provided", "none", ""):
        return "N/A"
    return str(val)


def _score_colour(score: float) -> str:
    if score >= 0.75:
        return "#4caf50"
    if score >= 0.50:
        return "#ffc107"
    return "#ef5350"


def _severity_colour(severity: str) -> str:
    return {
        "Critical": "#ef5350",
        "High":     "#ff7043",
        "Medium":   "#ffc107",
        "Low":      "#4caf50",
    }.get(severity, "#666688")


def _escape_dollars(text: str) -> str:
    """Escape $ signs so st.markdown doesn't interpret them as LaTeX delimiters."""
    return text.replace("$", "\\$") if isinstance(text, str) else text


def _extract_page_from_citation(citation_obj):
    """Extract a page number from citation/page-reference payloads."""
    if not isinstance(citation_obj, dict):
        return None
    page = citation_obj.get("page")
    if isinstance(page, int) and page > 0:
        return page
    if isinstance(page, str) and page.strip().isdigit():
        return int(page.strip())
    page_ref = citation_obj.get("page_reference")
    if isinstance(page_ref, int) and page_ref > 0:
        return page_ref
    if isinstance(page_ref, str):
        m = re.search(r"\d+", page_ref)
        if m:
            return int(m.group(0))
    return None


def _metric_with_page(value, citation_obj) -> str:
    """Render metric value with optional citation page suffix."""
    # Sanitise sentinel values so raw "not_provided" never reaches the UI
    if value is None or str(value).lower() in ("not_provided", "none", ""):
        value = "N/A"
    page = _extract_page_from_citation(citation_obj)
    if page:
        return f"**{value}** <span style='color:#8888aa;font-size:0.82rem'>(p. {page})</span>"
    return f"**{value}**"


def _health_dot(status: str) -> str:
    return {
        "green": "🟢",
        "yellow": "🟡",
        "red": "🔴",
    }.get(status, "⚪")


def _collect_verification_rows(extracted_data):
    rows = []

    def _is_missing(v):
        return v is None or (isinstance(v, str) and v.strip().lower() in {"", "none", "n/a", "not_provided"})

    def _walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else k
                if k.endswith("_conf"):
                    base_key = k[:-5]
                    base_value = node.get(base_key)
                    source_value = node.get(f"{base_key}_source")
                    conf = _to_float_or_none(v)
                    missing = conf == 0 or _is_missing(base_value)
                    if missing:
                        category = "missing"
                    elif conf is None:
                        category = "missing"
                    elif conf >= 0.9:
                        category = "stated"
                    elif conf >= 0.5:
                        category = "derived"
                    elif conf >= 0.1:
                        category = "inferred"
                    else:
                        category = "missing"
                    rows.append(
                        {
                            "field": p[:-5],
                            "value": base_value,
                            "confidence": conf,
                            "category": category,
                            "cited": not _is_missing(source_value),
                            "source": source_value,
                        }
                    )
                _walk(v, p)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                _walk(item, f"{path}[{idx}]")

    _walk(extracted_data or {}, "")
    return rows


def _render_verification_summary(extracted_data, narrative_gaps=None):
    import pandas as pd

    rows = _collect_verification_rows(extracted_data)
    if not rows:
        return

    total = len(rows)
    stated = sum(1 for r in rows if r["category"] == "stated")
    derived = sum(1 for r in rows if r["category"] == "derived")
    inferred = sum(1 for r in rows if r["category"] == "inferred")
    missing = sum(1 for r in rows if r["category"] == "missing")
    flagged = inferred + missing
    cited = sum(1 for r in rows if r["cited"])
    stated_ratio = stated / max(1, total)

    coverage_ratio = cited / max(1, total)
    if coverage_ratio >= 0.80:
        level = "Strong"
        badge_cls = "verification-badge-high"
    elif coverage_ratio >= 0.50:
        level = "Moderate"
        badge_cls = "verification-badge-medium"
    else:
        level = "Limited"
        badge_cls = "verification-badge-low"

    # Trust check summary line (uses narrative_gaps if available)
    _ngaps = narrative_gaps or []
    _confirmed_n = sum(1 for g in _ngaps if g.get("status") == "confirmed")
    _disc_n      = sum(1 for g in _ngaps if g.get("status") == "discrepancy")
    if _disc_n > 0:
        _trust_icon = "⚠️"
        _trust_line = (
            f"Trust Check: Verified {_confirmed_n} claim(s) &nbsp;•&nbsp; "
            f"<b style='color:#ef7a7a'>{_disc_n} discrepanc{'y' if _disc_n==1 else 'ies'} found</b> "
            f"&nbsp;•&nbsp; {cited}/{total} fields cited"
        )
    else:
        _trust_icon = "✅"
        _trust_line = (
            f"Trust Check: Verified {_confirmed_n} claim(s) &nbsp;•&nbsp; "
            f"0 discrepancies &nbsp;•&nbsp; {cited}/{total} fields cited"
        )

    st.markdown(
        f"<div style='font-size:0.82rem;margin-bottom:6px;color:#ccc'>"
        f"{_trust_icon} {_trust_line}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='verification-summary'>"
        "<div class='verification-title'>Verification Summary</div>"
        f"<div class='verification-line'>{total} fields · "
        f"<span class='verification-chip-green'>{stated} verified</span> · "
        f"<span class='verification-chip-amber'>{derived} derived</span> · "
        f"<span class='verification-chip-red'>{flagged} flagged</span></div>"
        f"<div class='verification-line'>Document coverage: {cited}/{total} fields cited"
        f"&nbsp;&nbsp;<span class='verification-badge {badge_cls}'>{level}</span></div>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("View field-by-field confidence breakdown", expanded=False):
        table = pd.DataFrame(
            [
                {
                    "Field": r["field"],
                    "Value": _fmt_str(r["value"]) if not isinstance(r["value"], (dict, list)) else str(r["value"]),
                    "Confidence": "N/A" if r["confidence"] is None else f"{r['confidence']:.2f}",
                    "Category": r["category"].title(),
                    "Cited": "Yes" if r["cited"] else "No",
                    "Source": _fmt_str(r["source"]),
                }
                for r in rows
            ]
        )
        st.dataframe(table, width="stretch", hide_index=True)


def _pipeline_deals():
    deals = [
        {"company": "NovaTech Solutions", "industry": "Enterprise Software", "revenue": 142_000_000, "grade": "B+", "days": 12, "stage": "Screening"},
        {"company": "Apex Learning Co", "industry": "EdTech", "revenue": 89_000_000, "grade": "A-", "days": 3, "stage": "Initial Review"},
        {"company": "CloudBridge SaaS", "industry": "Cloud Infrastructure", "revenue": 221_000_000, "grade": "B", "days": 8, "stage": "Deep Diligence"},
        {"company": "Summit Cyber", "industry": "Cybersecurity", "revenue": 178_000_000, "grade": "A", "days": 5, "stage": "IC Ready"},
        {"company": "MedTech Solutions", "industry": "Healthcare IT", "revenue": 97_000_000, "grade": "B-", "days": 16, "stage": "Deep Diligence"},
        {"company": "DataFlow Analytics", "industry": "Data/AI", "revenue": 64_000_000, "grade": "C+", "days": 19, "stage": "Passed"},
        {"company": "Harbor Logistics Tech", "industry": "Supply Chain SaaS", "revenue": 133_000_000, "grade": "B", "days": 6, "stage": "Initial Review"},
        {"company": "Veridian Payments", "industry": "FinTech", "revenue": 204_000_000, "grade": "B+", "days": 11, "stage": "Screening"},
    ]
    for item in st.session_state.get("analyzed_deals", []):
        if not any(d["company"] == item["company"] for d in deals):
            deals.append(item)
    return deals


def _render_pipeline_dashboard(show_title: bool = True):
    deals = _pipeline_deals()
    active = [d for d in deals if d["stage"] != "Passed"]
    avg_days = round(sum(d["days"] for d in deals) / max(1, len(deals)), 1)

    left, btn_upload_col, btn_compare_col = st.columns([6, 1.4, 1.4])
    with left:
        if show_title:
            st.markdown(
                "<h2 style='color:#e8e8e8;margin-bottom:0.2rem'>Deal Pipeline Dashboard</h2>",
                unsafe_allow_html=True,
            )
        st.caption("Track live opportunities from screening through IC decisions.")
    with btn_upload_col:
        if st.button("Upload", width="stretch"):
            st.session_state["_pipeline_inline_upload"] = True
    with btn_compare_col:
        if st.button("Compare", width="stretch"):
            st.session_state["_preview_panel"] = "compare"
            st.rerun()

    if st.session_state.get("_pipeline_inline_upload"):
        with st.container(border=True):
            inline_file = st.file_uploader(
                "Upload a PDF or DOCX",
                type=["pdf", "docx", "doc"],
                key="_pipeline_inline_uploader",
                help="Max 200MB",
                width="stretch",
            )
            a_col, c_col = st.columns([1, 1])
            with a_col:
                inline_analyze = st.button(
                    "Analyze Upload",
                    type="primary",
                    width="stretch",
                    disabled=(inline_file is None),
                    key="_pipeline_inline_analyze_btn",
                )
            with c_col:
                if st.button("Cancel", width="stretch", key="_pipeline_inline_cancel_btn"):
                    st.session_state["_pipeline_inline_upload"] = False
                    st.rerun()
        if inline_analyze and inline_file is not None:
            if getattr(inline_file, "size", 0) and inline_file.size > 200 * 1024 * 1024:
                st.error("File exceeds 200MB limit.")
            else:
                _execute_analysis_workflow(inline_file, st.session_state.get("_scoring_profile", "balanced"))
                return

    m1, m2, m3 = st.columns(3, gap="small")
    metric_cards = [
        ("Total Active Deals", f"{len(active)}"),
        ("Average Days to IC", f"{avg_days}d"),
        ("Deals Reviewed This Month", "14"),
    ]
    for col, (label, value) in zip((m1, m2, m3), metric_cards):
        col.markdown(
            "<div class='hero-metric-card'>"
            f"<div class='hero-metric-label'>{label}</div>"
            f"<div class='hero-metric-value'>{value}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    st.divider()

    stages = ["Screening", "Initial Review", "Deep Diligence", "IC Ready", "Passed"]
    cols = st.columns(len(stages))
    for col, stage in zip(cols, stages):
        stage_deals = [d for d in deals if d["stage"] == stage]
        with col:
            st.markdown(
                f"<div class='wire-title' style='margin-bottom:0.4rem'>{stage} ({len(stage_deals)})</div>",
                unsafe_allow_html=True,
            )
            for d in stage_deals:
                st.markdown(
                    "<div class='wire-card' style='margin-bottom:0.55rem'>"
                    f"<div style='color:#e8e8f8;font-weight:700;font-size:0.9rem'>{d['company']}</div>"
                    f"<div style='color:#8e97c8;font-size:0.76rem;margin-top:0.2rem'>{d['industry']}</div>"
                    "<div style='display:flex;justify-content:space-between;margin-top:0.45rem;"
                    "font-size:0.82rem;color:#cfd4f5'>"
                    f"<span>{_fmt_num(d['revenue'])}</span><span style='color:#7fd19a'>{d['grade']}</span>"
                    "</div>"
                    f"<div style='color:#7b83b6;font-size:0.74rem;margin-top:0.28rem'>{d['days']} {'day' if d['days'] == 1 else 'days'} in stage</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )


def _render_data_room_view(show_title: bool = True):
    import pandas as pd

    if show_title:
        st.markdown("<h2 style='color:#e8e8e8;margin-bottom:0.2rem'>Data Room</h2>", unsafe_allow_html=True)
    st.caption("Centralized document management for active deals.")

    deals = _pipeline_deals()
    deal_names = [d.get("company", "Unknown Deal") for d in deals]
    selected_deal = st.selectbox("Select Deal", options=deal_names, key="_data_room_deal_select")

    analyzed_lookup = {
        d.get("company"): d
        for d in st.session_state.get("analyzed_deals", [])
        if isinstance(d, dict)
    }
    selected_analyzed = analyzed_lookup.get(selected_deal)

    first_doc_name = "Confidential Information Memorandum"
    first_doc_pages = 42
    first_doc_status = "Analyzed ✅"
    first_doc_uploaded = "Mar 1, 2026"
    if selected_analyzed:
        first_doc_name = selected_analyzed.get("document_name") or first_doc_name
        first_doc_pages = selected_analyzed.get("document_pages") or first_doc_pages
        first_doc_uploaded = selected_analyzed.get("uploaded_date") or first_doc_uploaded

    docs = [
        {"Document": first_doc_name, "Type": "CIM", "Pages": first_doc_pages, "Status": first_doc_status, "Uploaded": first_doc_uploaded},
        {"Document": "Quality of Earnings Report", "Type": "QoE", "Pages": "—", "Status": "Pending Upload ⏳", "Uploaded": "—"},
        {"Document": "Management Presentation", "Type": "Presentation", "Pages": "—", "Status": "Pending Upload ⏳", "Uploaded": "—"},
        {"Document": "Customer Contracts (Sample)", "Type": "Legal", "Pages": "—", "Status": "Not Started ⏹", "Uploaded": "—"},
        {"Document": "Financial Model", "Type": "Model", "Pages": "—", "Status": "Not Started ⏹", "Uploaded": "—"},
        {"Document": "Environmental Assessment", "Type": "Diligence", "Pages": "—", "Status": "Not Started ⏹", "Uploaded": "—"},
    ]

    analyzed_count = sum(1 for d in docs if str(d.get("Status", "")).startswith("Analyzed"))
    total_count = len(docs)
    pct = analyzed_count / total_count if total_count else 0
    with st.container(border=True):
        st.markdown(f"**{analyzed_count} of {total_count} documents analyzed**")
        st.progress(pct)

    st.dataframe(pd.DataFrame(docs), width="stretch", hide_index=True)

    st.divider()
    st.markdown("<div class='section-label'>Add documents to this deal's data room</div>", unsafe_allow_html=True)
    st.file_uploader(
        "Add documents to this deal's data room",
        type=["pdf", "docx", "xlsx", "pptx"],
        accept_multiple_files=True,
        key="_deal_data_room_upload",
        label_visibility="collapsed",
    )

    st.markdown(
        "<div class='info-card' style='margin-top:0.8rem'>"
        "<h4>Coming Soon</h4>"
        "<p>VDR Integration — Connect to Intralinks, Datasite, or Box for automatic document sync</p>"
        "<p>Cross-Document Analysis — Extract and reconcile data across CIM, QoE, and financial model</p>"
        "<p>Document Versioning — Track changes across document versions</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_portfolio_view(show_title: bool = True):
    import altair as alt
    import pandas as pd

    if show_title:
        st.markdown("<h2 style='color:#e8e8e8;margin-bottom:0.2rem'>Portfolio Intelligence</h2>", unsafe_allow_html=True)
    st.caption("Operating view across active portfolio companies.")
    top_l, top_r = st.columns([5, 1])
    with top_r:
        st.button("Export All", width="stretch")

    records = [
        {"Company": "Apex Learning Co", "Sector": "EdTech", "Revenue": "$142M", "EBITDA Margin": "18%", "YoY Growth": "+14.2%", "Health": _health_dot("green"), "Last Updated": "Feb 2026"},
        {"Company": "CloudBridge SaaS", "Sector": "Cloud Infrastructure", "Revenue": "$221M", "EBITDA Margin": "22%", "YoY Growth": "+28.6%", "Health": _health_dot("green"), "Last Updated": "Jan 2026"},
        {"Company": "MedTech Solutions", "Sector": "Healthcare IT", "Revenue": "$97M", "EBITDA Margin": "12%", "YoY Growth": "+6.9%", "Health": _health_dot("yellow"), "Last Updated": "Mar 2026"},
        {"Company": "DataFlow Analytics", "Sector": "Data/AI", "Revenue": "$64M", "EBITDA Margin": "-3%", "YoY Growth": "-3.1%", "Health": _health_dot("red"), "Last Updated": "Feb 2026"},
        {"Company": "SecureNet Cyber", "Sector": "Cybersecurity", "Revenue": "$178M", "EBITDA Margin": "25%", "YoY Growth": "+19.4%", "Health": _health_dot("green"), "Last Updated": "Mar 2026"},
    ]
    df = pd.DataFrame(records)

    selected_company = None
    try:
        event = st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="portfolio_table",
        )
        rows = (event.selection.rows if event and getattr(event, "selection", None) else [])
        if rows:
            selected_company = df.iloc[rows[0]]["Company"]
    except TypeError:
        st.dataframe(df, width="stretch", hide_index=True)

    fallback = st.selectbox(
        "Select Company",
        options=[r["Company"] for r in records],
        index=0,
        key="_portfolio_company_select",
    )
    selected_company = selected_company or fallback

    if selected_company:
        st.divider()
        st.markdown(f"### {selected_company}")
        trend = {
            "Apex Learning Co": [102, 111, 118, 126, 134, 142],
            "CloudBridge SaaS": [131, 147, 166, 183, 205, 221],
            "MedTech Solutions": [81, 85, 88, 90, 94, 97],
            "DataFlow Analytics": [72, 70, 69, 67, 65, 64],
            "SecureNet Cyber": [121, 132, 144, 156, 168, 178],
        }[selected_company]
        years = ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
        trend_df = pd.DataFrame({"Fiscal Year": years, "Revenue ($M)": trend})
        y_min = min(trend) * 0.92
        y_max = max(trend) * 1.08
        with st.container(border=True):
            chart = (
                alt.Chart(trend_df)
                .mark_line(point=True, strokeWidth=3, color="#7fb8ff")
                .encode(
                    x=alt.X("Fiscal Year:N", sort=years, title="Fiscal Year"),
                    y=alt.Y("Revenue ($M):Q", scale=alt.Scale(domain=[y_min, y_max]), title="Revenue ($M)"),
                    tooltip=["Fiscal Year", "Revenue ($M)"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, width="stretch")
            c1, c2, c3 = st.columns(3)
            c1.metric("LTM Revenue", f"${trend[-1]}M")
            c2.metric("6-Month Delta", f"{trend[-1] - trend[-2]:+,.0f}M")
            c3.metric("Trend", "Improving" if trend[-1] >= trend[-2] else "Under Review")
            st.button("Generate LP Report", type="primary")


def _render_compare_view():
    try:
        from core.deal_store import list_deals
        real_deals = list_deals()
    except Exception:
        real_deals = []

    try:
        from core.deal_store import get_peer_deals
    except Exception:
        get_peer_deals = None

    def _obj_get(obj, key, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _first_present(obj, keys, default=None):
        for key in keys:
            val = _obj_get(obj, key, None)
            if val not in (None, "", "not_provided"):
                return val
        return default

    def _to_number(val):
        if val in (None, "", "not_provided"):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _build_deal_item(deal_obj, source):
        company = _first_present(deal_obj, ["company", "company_name", "name"], "Unknown Deal")
        industry = _first_present(deal_obj, ["industry", "sector"], "Unknown")
        business_model = _first_present(deal_obj, ["business_model"], "Unknown")
        if source == "real":
            # Persisted deal_store payload: use exact field names first.
            revenue = _to_number(_obj_get(deal_obj, "revenue_ltm"))
            ebitda = _to_number(_obj_get(deal_obj, "ebitda_ltm"))
            ebitda_margin = _to_number(_obj_get(deal_obj, "ebitda_margin"))
            revenue_cagr = _to_number(_obj_get(deal_obj, "revenue_cagr"))
            recurring = _to_number(_obj_get(deal_obj, "recurring_revenue_pct"))
            concentration = _to_number(_obj_get(deal_obj, "customer_concentration"))
            deal_score = _to_number(_obj_get(deal_obj, "deal_score"))
            grade = _first_present(deal_obj, ["deal_grade"], "N/A")
        else:
            revenue = _to_number(_first_present(deal_obj, ["revenue_ltm", "revenue"]))
            ebitda = _to_number(_first_present(deal_obj, ["ebitda_ltm", "ebitda"]))
            ebitda_margin = _to_number(_first_present(deal_obj, ["ebitda_margin", "ebitda_margin_ltm"]))
            revenue_cagr = _to_number(_first_present(deal_obj, ["revenue_cagr", "revenue_cagr_3yr", "growth_3yr_cagr"]))
            recurring = _to_number(_first_present(deal_obj, ["recurring_revenue_pct", "recurring_revenue"]))
            concentration = _to_number(_first_present(deal_obj, ["customer_concentration", "top_customer_concentration"]))
            deal_score = _to_number(_first_present(deal_obj, ["deal_score", "total_score"]))
            grade = _first_present(deal_obj, ["deal_grade", "grade"], "N/A")

        if source == "mock":
            revenue = revenue if revenue is not None else _to_number(_obj_get(deal_obj, "revenue"))
            ebitda = ebitda if ebitda is not None and revenue is not None else (revenue * 0.20 if revenue else None)
            ebitda_margin = ebitda_margin if ebitda_margin is not None else (ebitda / revenue if ebitda and revenue else None)
            revenue_cagr = revenue_cagr if revenue_cagr is not None else 0.15
            recurring = recurring if recurring is not None else 0.72
            concentration = concentration if concentration is not None else 0.28
            deal_score = deal_score if deal_score is not None else (0.80 if "A" in str(grade) else 0.68)
            if business_model == "Unknown":
                business_model = "B2B SaaS"

        return {
            "company": str(company),
            "industry": str(industry),
            "business_model": str(business_model),
            "revenue_ltm": revenue,
            "ebitda_ltm": ebitda,
            "ebitda_margin": ebitda_margin,
            "revenue_cagr": revenue_cagr,
            "recurring_revenue_pct": recurring,
            "customer_concentration": concentration,
            "deal_score": deal_score,
            "deal_grade": str(grade),
            "source": source,
            "_raw": deal_obj,
        }

    real_items = [_build_deal_item(d, "real") for d in (real_deals or [])]
    mock_items = [_build_deal_item(d, "mock") for d in _pipeline_deals()]
    all_items = real_items + [m for m in mock_items if m["company"] not in {r["company"] for r in real_items}]

    if not all_items:
        st.info("No deals available for comparison.")
        return

    labels = [
        (f"{d['company']} (Analyzed)" if d["source"] == "real" else d["company"])
        for d in all_items
    ]
    label_to_deal = dict(zip(labels, all_items))

    left_sel, right_sel = st.columns(2)
    company_a_label = left_sel.selectbox("Company A", options=labels, index=0, key="_cmp_a")
    company_b_label = right_sel.selectbox("Company B", options=labels, index=min(1, len(labels) - 1), key="_cmp_b")

    a = label_to_deal[company_a_label]
    b = label_to_deal[company_b_label]
    if a.get("source") == "real":
        print(f"[compare debug] selected deal A = {a.get('_raw')}")
    if b.get("source") == "real":
        print(f"[compare debug] selected deal B = {b.get('_raw')}")
    metrics = [
        ("Revenue", a["revenue_ltm"], b["revenue_ltm"], "num"),
        ("EBITDA", a["ebitda_ltm"], b["ebitda_ltm"], "num"),
        ("EBITDA Margin", a["ebitda_margin"], b["ebitda_margin"], "pct"),
        ("Growth (3yr CAGR)", a["revenue_cagr"], b["revenue_cagr"], "pct"),
        ("Deal Score", a["deal_score"], b["deal_score"], "score"),
        ("Recurring Revenue %", a["recurring_revenue_pct"], b["recurring_revenue_pct"], "pct"),
        ("Customer Concentration", a["customer_concentration"], b["customer_concentration"], "pct_low_wins"),
    ]

    st.divider()
    h1, h2 = st.columns(2)
    h1.markdown(f"### {a['company']}")
    h2.markdown(f"### {b['company']}")

    a_industry = (a.get("industry") or "").strip().lower()
    b_industry = (b.get("industry") or "").strip().lower()
    a_model = (a.get("business_model") or "").strip().lower()
    b_model = (b.get("business_model") or "").strip().lower()
    if a_industry and b_industry and a_industry == b_industry:
        relevance = "🟢 High relevance — same sector"
    elif a_model and b_model and a_model == b_model:
        relevance = "🟡 Medium relevance — same business model"
    else:
        relevance = "🔴 Cross-sector comparison — use caution benchmarking"
    h1.caption(relevance)
    h2.caption(relevance)

    for label, av, bv, kind in metrics:
        c1, c2, c3 = st.columns([2, 2, 2])
        avn = _to_number(av)
        bvn = _to_number(bv)
        if kind == "num":
            a_txt, b_txt = _fmt_num(av), _fmt_num(bv)
            awin = avn is not None and bvn is not None and avn >= bvn
            bwin = avn is not None and bvn is not None and bvn > avn
        elif kind == "pct_low_wins":
            a_txt, b_txt = _fmt_pct(av), _fmt_pct(bv)
            awin = avn is not None and bvn is not None and avn <= bvn
            bwin = avn is not None and bvn is not None and bvn < avn
        elif kind == "score":
            a_txt = "N/A" if avn is None else (f"{avn:.0%}" if avn <= 1.0 else f"{avn:.1f}")
            b_txt = "N/A" if bvn is None else (f"{bvn:.0%}" if bvn <= 1.0 else f"{bvn:.1f}")
            awin = avn is not None and bvn is not None and avn >= bvn
            bwin = avn is not None and bvn is not None and bvn > avn
        else:
            a_txt, b_txt = _fmt_pct(av), _fmt_pct(bv)
            awin = avn is not None and bvn is not None and avn >= bvn
            bwin = avn is not None and bvn is not None and bvn > avn
        c1.write(label)
        c2.markdown(f"<span style='color:{'#65d38b' if awin else '#d3d7f8'};font-weight:700'>{a_txt}</span>", unsafe_allow_html=True)
        c3.markdown(f"<span style='color:{'#65d38b' if bwin else '#d3d7f8'};font-weight:700'>{b_txt}</span>", unsafe_allow_html=True)

    # Peer context for same-sector comparisons
    if a_industry and b_industry and a_industry == b_industry and callable(get_peer_deals):
        peers = []
        try:
            peers = get_peer_deals(a.get("industry"))
        except TypeError:
            try:
                peers = get_peer_deals(sector=a.get("industry"))
            except Exception:
                peers = []
        except Exception:
            peers = []
        revs = [_to_number(_first_present(p, ["revenue_ltm", "revenue"])) for p in (peers or [])]
        margins = [_to_number(_first_present(p, ["ebitda_margin", "ebitda_margin_ltm"])) for p in (peers or [])]
        revs = sorted([x for x in revs if x is not None])
        margins = sorted([x for x in margins if x is not None])
        if revs and margins:
            def _median(values):
                n = len(values)
                mid = n // 2
                if n % 2 == 1:
                    return values[mid]
                return (values[mid - 1] + values[mid]) / 2
            med_rev = _median(revs)
            med_margin = _median(margins)
            st.caption(
                f"Based on {len(peers)} {a.get('industry')} deals analyzed: "
                f"median revenue {_fmt_num(med_rev)}, median EBITDA margin {_fmt_pct(med_margin)}"
            )

    st.divider()
    a_rev = _to_number(a.get("revenue_ltm")) or 0
    b_rev = _to_number(b.get("revenue_ltm")) or 0
    winner = a["company"] if a_rev >= b_rev else b["company"]
    st.markdown(
        "<div style='background:#1a1f2e;border:1px solid #2b3657;border-radius:8px;"
        "padding:0.75rem 0.9rem;color:#c8d0ef'>"
        f"AI summary: {winner} presents the stronger blend of growth quality and scale, "
        "while the other opportunity offers a narrower upside profile with higher diligence sensitivity."
        "</div>",
        unsafe_allow_html=True,
    )


def _render_memo(memo_text):
    """Render memo with canonical sections schema plus resilient fallbacks."""
    import json as _json

    section_order = [
        "executive_summary",
        "company_overview",
        "financial_highlights",
        "growth_thesis",
        "key_risks_and_mitigants",
        "valuation_context",
        "key_diligence_questions",
        "recommendation",
    ]
    label_overrides = {
        "key_risks_and_mitigants": "Key Risks & Mitigants",
        "key_diligence_questions": "Key Diligence Questions",
    }

    def _to_title(key: str) -> str:
        k = str(key).strip().lower()
        if k in label_overrides:
            return label_overrides[k]
        return str(key).replace("_", " ").title()

    def _render_content(val):
        if val is None:
            return
        if isinstance(val, str):
            if val.strip():
                st.markdown(_escape_dollars(val))
            return
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    bits = []
                    for k, v in item.items():
                        if v in (None, "", "not_provided"):
                            continue
                        bits.append(f"{_to_title(k)}: {v}")
                    if bits:
                        st.markdown(f"* {_escape_dollars(' | '.join(bits))}")
                else:
                    st.markdown(f"* {_escape_dollars(str(item))}")
            return
        if isinstance(val, dict):
            for k, v in val.items():
                if v in (None, "", "not_provided"):
                    continue
                if isinstance(v, (dict, list)):
                    st.markdown(f"**{_escape_dollars(_to_title(k))}:**")
                    _render_content(v)
                else:
                    st.markdown(f"* **{_escape_dollars(_to_title(k))}:** {_escape_dollars(str(v))}")
            return
        st.markdown(_escape_dollars(str(val)))

    data = memo_text if isinstance(memo_text, dict) else None
    if data is None:
        try:
            data = _json.loads(memo_text)
        except (_json.JSONDecodeError, TypeError):
            data = None

    # Fallback path 2: plain string
    if data is None:
        st.markdown(_escape_dollars(str(memo_text)))
        return

    # Primary path: canonical schema with top-level sections array
    sections = data.get("sections") if isinstance(data, dict) else None
    if isinstance(sections, list):
        title = str(data.get("title", "")).strip()
        date_str = str(data.get("date", "")).strip()
        prepared_by = str(data.get("prepared_by", "")).strip()
        if title:
            st.markdown(f"### {_escape_dollars(title)}")
        meta = [x for x in [date_str, f"Prepared by: {prepared_by}" if prepared_by else ""] if x]
        if meta:
            st.caption("  ·  ".join(meta))

        rendered = False
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            heading = str(sec.get("heading", "")).strip()
            content = sec.get("content", "")
            if not heading and content in (None, "", "not_provided"):
                continue
            rendered = True
            st.markdown(f"### {_escape_dollars(heading or 'Section')}")
            _render_content(content)
        if rendered:
            return

    # Fallback path 1: keyed sections at top-level (or common legacy wrapper)
    keyed = {}
    if isinstance(data, dict):
        for k, v in data.items():
            lk = str(k).lower()
            if lk in section_order:
                keyed[lk] = v
        if not keyed and isinstance(data.get("investment_committee_memo"), dict):
            for k, v in data["investment_committee_memo"].items():
                keyed[str(k).lower()] = v

    if keyed:
        ordered_keys = [k for k in section_order if k in keyed] + [k for k in keyed.keys() if k not in section_order]
        for k in ordered_keys:
            v = keyed.get(k)
            if v in (None, "", "not_provided"):
                continue
            st.markdown(f"### {_escape_dollars(_to_title(k))}")
            _render_content(v)
        return

    # Last resort: render JSON as markdown-ish text
    _render_content(data)


def _extract_memo_risks(memo_text: str) -> list:
    """Parse risk items out of a memo string — JSON or plain markdown.

    Attempt 1 — Structured keyed memo (JSON):
        data["investment_committee_memo"]["key_risks_and_mitigants"]
        → list of {"risk": ..., "mitigant": ...} dicts

    Attempt 2 — Sections array memo (JSON):
        data["memo"]["sections"] → find section whose heading contains "RISK"
        Content may be a list of dicts OR a plain string block.

    Attempt 3 — Plain text / markdown memo (non-JSON):
        Regex-locate the risks section by heading, split numbered items,
        then split each item on markdown-aware "Mitigant:" variants.

    Returns a list of {"risk": str, "mitigant": str} dicts (mitigant may be "").
    Never raises — returns [] on any parsing failure.
    """
    import json as _json
    import re

    if not memo_text:
        return []

    _stop_markers = (
        "VALUATION CONTEXT",
        "KEY DILIGENCE QUESTIONS",
        "DILIGENCE QUESTIONS",
        "RECOMMENDATION",
    )

    def _truncate_at_stop_markers(text: str) -> str:
        if not isinstance(text, str):
            return text
        upper = text.upper()
        cut = None
        for marker in _stop_markers:
            idx = upper.find(marker)
            if idx != -1 and (cut is None or idx < cut):
                cut = idx
        return text[:cut].strip() if cut is not None else text.strip()

    # Generic intro-sentence phrases that parsers sometimes mis-identify as
    # risk titles.  Any parsed risk whose title matches these patterns or is
    # implausibly long (> 80 chars) is discarded.
    _intro_pat = re.compile(
        r'\b(key risks?|include|following|associated with|related to|'
        r'factors? that|may impact|could impact|potential risks?|risks? include)\b',
        re.IGNORECASE,
    )

    def _is_intro_sentence(title: str) -> bool:
        """Return True if this 'risk title' looks like a preamble sentence."""
        t = title.strip()
        return len(t) > 80 or bool(_intro_pat.search(t))

    def _sanitize_risk_entry(entry: dict) -> dict:
        risk_txt = _truncate_at_stop_markers(
            str(entry.get("risk") or entry.get("title") or "").strip()
        )
        risk_txt = risk_txt.replace("**", "").replace("*", "").replace("\n", " ").strip()
        mitigant_txt = _truncate_at_stop_markers(
            str(entry.get("mitigant") or entry.get("mitigation") or "").strip()
        )
        out = {}
        if risk_txt and not _is_intro_sentence(risk_txt):
            out["risk"] = risk_txt
        if mitigant_txt:
            out["mitigant"] = mitigant_txt
        if entry.get("description"):
            out["description"] = _truncate_at_stop_markers(str(entry.get("description")).strip())
        return out

    def _parse_risk_content_block(text: str) -> list:
        """Parse canonical section content into risk dicts."""
        if not isinstance(text, str) or not text.strip():
            return []
        content = _truncate_at_stop_markers(text.strip())
        split_pat = r'(?m)(?=^\s*(?:\d+[\.\)]\s+|[A-Z][A-Za-z0-9&/,\-\s]{2,}:\s))'
        blocks = [b.strip() for b in re.split(split_pat, content) if b and b.strip()]
        if len(blocks) == 1 and "\n" in content:
            # Fallback split by line when regex doesn't segment well
            blocks = [b.strip() for b in content.splitlines() if b.strip()]

        parsed = []
        for block in blocks:
            line = re.sub(r'^\s*\d+[\.\)]\s*', '', block).strip()
            if not line:
                continue
            if ":" in line:
                title, desc = line.split(":", 1)
            else:
                title, desc = line, ""
            title = title.strip()
            desc = desc.strip()

            mitigant = ""
            mit_match = re.search(r'(?i)\b(?:mitigated by|mitigant)\s*:?\s*', desc)
            if mit_match:
                mitigant = desc[mit_match.end():].strip(" .;:-")
                desc = desc[:mit_match.start()].strip(" .;:-")

            safe = _sanitize_risk_entry({
                "risk": title,
                "description": desc,
                "mitigant": mitigant,
            })
            if safe.get("risk"):
                parsed.append(safe)
        return parsed

    # ── Attempts 1 & 2 require valid JSON ────────────────────────────────
    data = None
    try:
        data = _json.loads(memo_text)
    except (_json.JSONDecodeError, TypeError):
        pass

    if data is not None:
        # ── Canonical format: top-level sections[{heading, content}] ──────
        sections = data.get("sections")
        if isinstance(sections, list):
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                heading = str(sec.get("heading") or sec.get("title") or "").strip()
                if "risk" not in heading.lower():
                    continue
                content = sec.get("content") or ""
                if isinstance(content, str):
                    parsed = _parse_risk_content_block(content)
                    print(f"[risks debug] found {len(parsed)} risks from memo")
                    if parsed:
                        return parsed

        # ── Attempt 1: investment_committee_memo.key_risks_and_mitigants ──
        icm = data.get("investment_committee_memo")
        if isinstance(icm, dict):
            risks = icm.get("key_risks_and_mitigants")
            if isinstance(risks, list) and risks:
                cleaned = []
                for item in risks:
                    if isinstance(item, dict):
                        safe = _sanitize_risk_entry(item)
                        if safe.get("risk"):
                            cleaned.append(safe)
                if cleaned:
                    return cleaned

        # ── Attempt 1b: {"memo": {"key_risks_and_mitigants": [...]}} shape ──
        memo_inner = data.get("memo")
        if isinstance(memo_inner, dict):
            risks = memo_inner.get("key_risks_and_mitigants")
            if isinstance(risks, list) and risks:
                cleaned = []
                for item in risks:
                    if isinstance(item, dict):
                        safe = _sanitize_risk_entry(item)
                        if safe.get("risk"):
                            cleaned.append(safe)
                if cleaned:
                    return cleaned

        # ── Attempt 2: sections array — top-level or nested ──────────────
        # New format: {"memo": {meta}, "sections": [...]}  ← sections at top level
        # Legacy:     {"memo": {"sections": [...]}}        ← sections nested inside memo
        _top_sections = data.get("sections")
        _memo_obj     = data.get("memo", data)
        _nested_secs  = _memo_obj.get("sections") if isinstance(_memo_obj, dict) else None
        sections_list = _top_sections if isinstance(_top_sections, list) else _nested_secs

        if isinstance(sections_list, list):
            for sec in sections_list:
                if not isinstance(sec, dict):
                    continue
                heading = (sec.get("heading") or sec.get("title") or "")
                if "risk" not in heading.lower():
                    continue
                content = sec.get("content") or sec.get("body") or ""

                # Content is a list of structured dicts
                if isinstance(content, list):
                    cleaned = []
                    for item in content:
                        if isinstance(item, dict):
                            safe = _sanitize_risk_entry(item)
                            if safe.get("risk"):
                                cleaned.append(safe)
                    if cleaned:
                        return cleaned

                # Content is a numbered text block:
                # "1. Risk Title: description\n * Mitigant: text\n2. Next Risk: ..."
                if isinstance(content, str) and content.strip():
                    content_clean = _truncate_at_stop_markers(content.strip())
                    blocks = re.split(r"\n(?=\d+[\.\)])", content_clean)
                    result = []
                    for block in blocks:
                        block = block.strip()
                        if not block or not re.match(r'^\d+', block):
                            continue
                        # Strip leading "1. " or "1) "
                        block_body = re.sub(r'^\d+[\.\)]\s*', '', block, count=1)
                        # Extract mitigant (handles "* Mitigant:", "- Mitigant:", "Mitigant:")
                        mitigant_text = ""
                        mit_split = re.split(
                            r'\n\s*[\*\-]?\s*\*{0,2}Mitigant\*{0,2}\s*:',
                            block_body, maxsplit=1, flags=re.IGNORECASE,
                        )
                        if len(mit_split) > 1:
                            block_body    = mit_split[0].strip()
                            mitigant_text = mit_split[1].strip()
                        elif re.search(r'Mitigant\s*:', block_body, re.IGNORECASE):
                            p = re.split(r'Mitigant\s*:', block_body, maxsplit=1, flags=re.IGNORECASE)
                            block_body    = p[0].strip()
                            mitigant_text = p[1].strip()
                        # Split "Risk Title: description body"
                        if ": " in block_body:
                            title_part, desc_part = block_body.split(": ", 1)
                        else:
                            title_part, desc_part = block_body, ""
                        title_part = title_part.strip()
                        desc_part  = desc_part.strip()
                        if title_part:
                            safe = _sanitize_risk_entry({
                                "risk":        title_part,
                                "description": desc_part,
                                "mitigant":    mitigant_text,
                            })
                            if safe.get("risk"):
                                result.append(safe)
                    if result:
                        return result

                    # Content is a markdown bullet block:
                    # "*   **Risk Name (Severity):**\n    *   desc\n    *   Mitigant: ..."
                    # Split on top-level bold bullets: "*   **Title...**:" or "*   **Title...:**"
                    # Split on "\n*   **" (bold top-level bullet). The "**" is
                    # consumed by the split so subsequent blocks start directly
                    # with the title text (no leading "**").
                    bold_blocks = re.split(r'\n\*\s+\*\*', content_clean)
                    result = []
                    for blk_idx, block in enumerate(bold_blocks):
                        block = block.strip()
                        if not block:
                            continue
                        # First block is preamble text (before first bold bullet) — skip
                        if blk_idx == 0 and not re.match(r'[A-Z]', block):
                            continue
                        # Extract bold title: **Title text:**
                        title_match = re.match(r'\*?\*?([^*\n]+?)\*?\*?\s*:', block)
                        if not title_match:
                            continue
                        title_part = title_match.group(1).strip().strip('*').strip()
                        rest = block[title_match.end():].strip()
                        # Extract Mitigant line from sub-bullets
                        mitigant_text = ""
                        mit_m = re.search(r'Mitigant\s*:\s*(.+?)(?:\n\*|\Z)', rest, re.IGNORECASE | re.DOTALL)
                        if mit_m:
                            mitigant_text = mit_m.group(1).strip()
                            rest = rest[:mit_m.start()].strip()
                        # Collect description bullets (strip leading "* " from each)
                        desc_lines = [
                            re.sub(r'^\s*\*\s*', '', ln).strip()
                            for ln in rest.split('\n')
                            if ln.strip() and not ln.strip().startswith('**')
                        ]
                        desc_part = ' '.join(desc_lines).strip()
                        if title_part:
                            safe = _sanitize_risk_entry({
                                "risk":        title_part,
                                "description": desc_part,
                                "mitigant":    mitigant_text,
                            })
                            if safe.get("risk"):
                                result.append(safe)
                    if result:
                        return result

    # ── Attempt 3: Plain text / markdown memo — regex extraction ─────────
    risk_section_match = re.search(
        r'(?:KEY RISKS|RISKS?\s*&\s*MITIGANTS?|5\.\s*KEY RISKS)(.*?)(?:\n\*{0,2}\s*\d+\.\s*[A-Z]|\n#{1,3}\s|\Z)',
        memo_text,
        re.DOTALL | re.IGNORECASE,
    )
    if risk_section_match:
        risk_text = _truncate_at_stop_markers(risk_section_match.group(1).strip())
        items = re.split(r'\n(?=\d+\.)', risk_text)
        risks = []
        for item in items:
            item = item.strip()
            # Skip preamble/heading fragments — only process numbered items
            if not item or not re.match(r'^\d+\.', item):
                continue
            parts = re.split(
                r'\n\s*(?:[\*\-]\s*)?(?:\*\*?)?Mitigant(?:\*\*?)?\s*:',
                item,
                flags=re.IGNORECASE,
                maxsplit=1,
            )
            header_block = parts[0].strip()
            mitigant     = parts[1].strip() if len(parts) > 1 else ""
            # First line = risk title; remaining lines = description body
            header_lines = header_block.splitlines()
            title_line   = header_lines[0].strip() if header_lines else header_block
            description  = "\n".join(l.strip() for l in header_lines[1:]).strip()
            # Strip leading "1. ", surrounding ** bold markers, residual * and trailing ":"
            title_line = re.sub(r'^\d+\.\s*', '', title_line).strip()
            title_line = re.sub(r'^\*+|\*+$', '', title_line).strip()
            title_line = title_line.replace("**", "").replace("*", "").strip()
            title_line = title_line.rstrip(":").strip()
            if title_line:
                entry = {"risk": title_line, "mitigant": _truncate_at_stop_markers(mitigant)}
                if description:
                    entry["description"] = _truncate_at_stop_markers(description)
                safe = _sanitize_risk_entry(entry)
                if safe.get("risk"):
                    risks.append(safe)
        if risks:
            return risks

    return []


def _make_xlsx_bytes(result) -> bytes:
    """Generate Excel workbook bytes from an AnalysisResult."""
    from output.excel_export import export_excel
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp_path = tmp.name
    try:
        export_excel(result, tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def _make_docx_bytes(result) -> bytes:
    """Generate Word document bytes from an AnalysisResult."""
    from output.memo_formatter import export_memo_docx
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp_path = tmp.name
    try:
        export_memo_docx(
            result.memo,
            result.extracted_data,
            result.risks,
            result.comps,
            tmp_path,
        )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def _make_pptx_bytes(result) -> bytes:
    """Generate IC Deck PowerPoint bytes from an AnalysisResult."""
    from output.pptx_export import generate_ic_deck
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as tmp:
        tmp_path = tmp.name
    try:
        generate_ic_deck(result, tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def _make_json_bytes(result) -> bytes:
    """Serialise the full analysis result to UTF-8 JSON bytes."""
    import json
    from datetime import UTC, datetime
    ds = result.deal_score
    payload = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "version": "0.1.0-mvp",
            "pipeline": "meridian-ai",
        },
        "extracted_data": result.extracted_data,
        "investment_memo": result.memo,
        "risk_analysis": {
            "total_risks": len(result.risks),
            "critical": sum(1 for r in result.risks if r.severity == "Critical"),
            "high":     sum(1 for r in result.risks if r.severity == "High"),
            "risks": [
                {
                    "category":           r.category,
                    "severity":           r.severity,
                    "title":              r.title,
                    "description":        r.description,
                    "mitigant":           r.mitigant,
                    "diligence_question": r.diligence_question,
                    "source":             r.source,
                }
                for r in result.risks
            ],
        },
        "comparable_companies": [c.to_dict() for c in result.comps],
        "deal_score": {
            "total_score":    ds.total_score    if ds else None,
            "grade":          ds.grade          if ds else None,
            "recommendation": ds.recommendation if ds else None,
            "summary":        ds.summary        if ds else None,
            "dimensions": [
                {
                    "dimension":      d.dimension,
                    "score":          d.score,
                    "weight":         d.weight,
                    "weighted_score": d.weighted_score,
                    "rationale":      d.rationale,
                    "data_quality":   d.data_quality,
                }
                for d in ds.dimensions
            ] if ds else [],
        },
    }
    return json.dumps(payload, indent=2, default=str).encode("utf-8")


def _persist_analysis(result, source_pdf_path: str, uploaded_name: str) -> None:
    """Persist PDF, extraction JSON, and memo; log to SQLite.

    Called immediately after a successful analysis while the temp file is still
    on disk.  Errors are logged but never raised — storage failure must not
    block the UI.
    """
    import json as _json
    import shutil
    from datetime import date

    co          = result.extracted_data.get("company_overview", {})
    company_raw = co.get("company_name") or ""
    if not company_raw or company_raw == "not_provided":
        company_raw = os.path.splitext(uploaded_name)[0]

    # Build a filesystem-safe slug: keep alphanumerics + spaces → underscores
    slug = "".join(c if c.isalnum() or c == " " else "" for c in company_raw)
    slug = "_".join(slug.split())[:50] or "unknown"
    file_key = f"{slug}_{date.today().strftime('%Y%m%d')}"

    project_root = os.path.expanduser("~/Downloads/meridian-ai")
    doc_dir      = os.path.join(project_root, "test_documents")
    out_dir      = os.path.join(project_root, "output")
    os.makedirs(doc_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    errors   = []
    pdf_dest = source_pdf_path  # fallback

    # 1. Copy PDF to test_documents/
    try:
        ext      = os.path.splitext(uploaded_name)[1] or ".pdf"
        pdf_dest = os.path.join(doc_dir, f"{file_key}{ext}")
        shutil.copy2(source_pdf_path, pdf_dest)
    except Exception as _e:
        errors.append(f"PDF copy: {_e}")

    # 2a. Save raw extraction dict — Critic-compatible (no wrapper)
    try:
        ext_path = os.path.join(out_dir, f"{file_key}_extraction.json")
        with open(ext_path, "w", encoding="utf-8") as _f:
            _json.dump(result.extracted_data, _f, indent=2, default=str)
    except Exception as _e:
        errors.append(f"Extraction JSON save: {_e}")

    # 2b. Save full pipeline payload (metadata + extraction + memo + scores)
    try:
        json_path = os.path.join(out_dir, f"{file_key}_analysis.json")
        with open(json_path, "wb") as _f:
            _f.write(_make_json_bytes(result))
    except Exception as _e:
        errors.append(f"Analysis JSON save: {_e}")

    # 3. Save memo markdown
    try:
        memo_path = os.path.join(out_dir, f"{file_key}_memo.md")
        with open(memo_path, "w", encoding="utf-8") as _f:
            _f.write(result.memo or "")
    except Exception as _e:
        errors.append(f"Memo save: {_e}")

    # 4. Log to SQLite via ApexState
    try:
        sys.path.insert(0, os.path.expanduser("~/Projects/apex"))
        from apex_state import ApexState  # type: ignore
        _fn = uploaded_name.lower()
        if "10-k" in _fn or "10k" in _fn:
            doc_type = "10k"
        elif "10-q" in _fn or "10q" in _fn:
            doc_type = "10q"
        elif "cim" in _fn:
            doc_type = "cim"
        else:
            doc_type = "10k"
        note = f"Streamlit upload: {uploaded_name}"
        if errors:
            note += f" | Errors: {'; '.join(errors)}"
        ApexState().add_test_document(
            company=company_raw,
            sector=co.get("industry") or "Unknown",
            doc_type=doc_type,
            source_url=pdf_dest,
            quality_rating=None,
            notes=note,
        )
    except Exception as _e:
        errors.append(f"SQLite log failed: {_e}")


def _get_pipeline():
    """Initialise and cache the MeridianPipeline."""
    try:
        from config.settings import PipelineConfig
        from core.pipeline import MeridianPipeline
        config = PipelineConfig(verbose=False)
        return MeridianPipeline(config)
    except Exception as e:
        return None, str(e)


def _run_analysis(uploaded_file, profile: str, progress_cb=None):
    """Run each pipeline step and emit progress callbacks."""
    from config.scoring_weights import PROFILES
    from core.pipeline import AnalysisResult
    from scoring.deal_scorer import DealScorer
    from scoring.fund_matcher import MatchingEngine

    pipeline = st.session_state.pipeline

    ext = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        _t0 = time.time()
        if progress_cb:
            progress_cb(0, "Parsing document...", 0.0)

        _t = time.time()
        document = pipeline._parse_document(tmp_path)
        if progress_cb:
            progress_cb(15, "Extracting financials...", time.time() - _t0)

        if progress_cb:
            progress_cb(15, "Extracting financials...", time.time() - _t0)
        _t = time.time()
        extracted_data = pipeline.extractor.extract(document)
        if progress_cb:
            progress_cb(50, "Generating investment memo...", time.time() - _t0)

        # Memo, Risks, and Comps are independent — run them in parallel.
        if progress_cb:
            progress_cb(50, "Generating investment memo...", time.time() - _t0)
        _t = time.time()

        from concurrent.futures import ThreadPoolExecutor

        def _run_memo():
            return (
                pipeline.memo_gen.generate(extracted_data)
                if pipeline.config.enable_memo_generation else ""
            )

        def _run_risks():
            return (
                pipeline.risk_analyzer.analyze(extracted_data)
                if pipeline.config.enable_risk_analysis else []
            )

        def _run_comps():
            return (
                pipeline.comp_builder.build(extracted_data)
                if pipeline.config.enable_comp_builder else []
            )

        with ThreadPoolExecutor(max_workers=3) as _pool:
            _fut_memo  = _pool.submit(_run_memo)
            _fut_risks = _pool.submit(_run_risks)
            _fut_comps = _pool.submit(_run_comps)
            memo  = _fut_memo.result()
            risks = _fut_risks.result()
            comps = _fut_comps.result()

        if progress_cb:
            progress_cb(90, "Finalizing analysis...", time.time() - _t0)

        if progress_cb:
            progress_cb(90, "Finalizing analysis...", time.time() - _t0)
        _t = time.time()
        if pipeline.config.enable_deal_scoring:
            _active = st.session_state.get("_scoring_profile", profile)
            if _active == "custom":
                from config.scoring_weights import ScoringWeights
                _wmap = {
                    dim: st.session_state.get(f"_w_{dim}", _PRESET_WEIGHTS["balanced"][dim])
                    for dim, _, _, _ in _SLIDER_DIMS
                }
                try:
                    _sw = ScoringWeights(
                        market_attractiveness=_wmap["market_attractiveness"] / 100,
                        financial_quality=_wmap["financial_quality"] / 100,
                        growth_profile=_wmap["growth_profile"] / 100,
                        management_strength=_wmap["management_strength"] / 100,
                        risk_factors=_wmap["risk_factors"] / 100,
                    )
                except ValueError:
                    _sw = PROFILES.get("balanced")
            else:
                _sw = PROFILES.get(_active, PROFILES["balanced"])
            deal_score = DealScorer(_sw).score(extracted_data)
        else:
            deal_score = None

        _t = time.time()
        fund_matches = MatchingEngine().match(extracted_data, top_n=5)
        st.session_state.fund_matches = fund_matches
        if progress_cb:
            progress_cb(100, "Finalizing analysis...", time.time() - _t0)

        # Narrative gap detection (pure regex — no LLM)
        from core.pipeline import detect_narrative_gaps
        try:
            narrative_gaps = detect_narrative_gaps(extracted_data, memo, document.raw_text) if memo else []
            print(f"[narrative debug] gaps={len(narrative_gaps)}: {narrative_gaps[:2]}")
        except Exception as _ng_exc:
            import traceback
            print(f"[narrative debug] ERROR: {_ng_exc}")
            traceback.print_exc()
            narrative_gaps = []

        # Deterministic insights + deal persistence (best-effort)
        insights: list = []
        try:
            from core.insights import generate_insights
            from core.deal_store import save_deal, get_peer_deals
            _partial = AnalysisResult(
                document=document,
                extracted_data=extracted_data,
                memo=memo,
                risks=risks,
                comps=comps,
                deal_score=deal_score,
                timing={},
                narrative_gaps=narrative_gaps,
            )
            _deal_id = save_deal(
                _partial,
                document_name=uploaded_file.name,
                pages=getattr(document, "total_pages", 0),
                duration=time.time() - _t0,
            )
            _industry = extracted_data.get("company_overview", {}).get("industry", "")
            _peers = get_peer_deals(_industry, exclude_id=_deal_id)
            insights = generate_insights(extracted_data, peer_deals=_peers or None)
            print(f"[insights debug] generated {len(insights)} insights")
        except Exception as _exc:
            print(f"[insights debug] error: {_exc}")
            pass

        result = AnalysisResult(
            document=document,
            extracted_data=extracted_data,
            memo=memo,
            risks=risks,
            comps=comps,
            deal_score=deal_score,
            timing={},
            narrative_gaps=narrative_gaps,
            insights=insights,
        )

        st.session_state.result   = result
        st.session_state.document = document
        co = extracted_data.get("company_overview", {})
        fin = extracted_data.get("financials", {})
        rev = fin.get("revenue", {})
        deal_stage = "IC Ready" if deal_score else "Deep Diligence"
        analyzed_card = {
            "company": co.get("company_name", "Analyzed Deal"),
            "industry": co.get("industry", "Unknown"),
            "revenue": rev.get("ltm") if isinstance(rev.get("ltm"), (int, float)) else 0,
            "grade": getattr(deal_score, "grade", "B"),
            "days": 1,
            "stage": deal_stage,
            "document_name": uploaded_file.name,
            "document_pages": getattr(document, "total_pages", 42),
            "uploaded_date": time.strftime("%b %d, %Y"),
        }
        existing = st.session_state.get("analyzed_deals", [])
        st.session_state["analyzed_deals"] = [
            d for d in existing if d.get("company") != analyzed_card["company"]
        ] + [analyzed_card]

        _persist_analysis(result, tmp_path, uploaded_file.name)

        return result, None

    except Exception as exc:
        return None, str(exc)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Sidebar callbacks
# ---------------------------------------------------------------------------

def _on_profile_select():
    """Sync sliders to the chosen preset when the dropdown changes."""
    if "_scoring_profile" not in st.session_state:
        return
    sel = st.session_state["_scoring_profile"]
    if sel in _PRESET_WEIGHTS:
        for dim, _, _, _ in _SLIDER_DIMS:
            st.session_state[f"_w_{dim}"] = _PRESET_WEIGHTS[sel][dim]


def _on_weight_slider():
    """Switch profile label to a matching preset or 'Custom' when sliders move."""
    if any(f"_w_{dim}" not in st.session_state for dim, _, _, _ in _SLIDER_DIMS):
        return
    current = {dim: st.session_state[f"_w_{dim}"] for dim, _, _, _ in _SLIDER_DIMS}
    for pname, pvals in _PRESET_WEIGHTS.items():
        if current == pvals:
            st.session_state["_scoring_profile"] = pname
            return
    st.session_state["_scoring_profile"] = "custom"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    # Logo
    st.markdown(
        """
        <a class="meridian-home-link" href="?home=1">
            <div class="meridian-home-logo">
                <span class="meridian-home-meridian">Meridian</span>
                <span class="meridian-home-ai"> AI</span>
            </div>
            <div class="meridian-tagline">PE Deal Intelligence</div>
        </a>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Upload
    st.markdown("<div class='section-label'>Upload Document</div>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Select a PDF or DOCX",
        type=["pdf", "docx", "doc"],
        help="CIM / 10-K / S-1 document",
        label_visibility="collapsed",
    )

    st.selectbox(
        "Scoring profile",
        options=["balanced", "conservative", "growth", "custom"],
        format_func=lambda x: x.title(),
        help="Adjusts dimension weights for the deal score.",
        key="_scoring_profile",
        on_change=_on_profile_select,
    )
    scoring_profile = st.session_state["_scoring_profile"]

    st.selectbox(
        "Industry profile",
        options=["General", "Education & EdTech", "Healthcare", "Financial Services", "Technology / SaaS"],
        help="Surfaces sector-specific risk flags in the Risk tab.",
        key="industry_profile",
    )

    with st.expander("⚙️ Configure", expanded=False):
        # ── Scoring Weights ───────────────────────────────────────────────
        st.markdown(
            "<div class='section-label'>Scoring Weights</div>",
            unsafe_allow_html=True,
        )
        for _dim, _lbl, _min_v, _max_v in _SLIDER_DIMS:
            st.slider(
                _lbl,
                min_value=_min_v,
                max_value=_max_v,
                step=1,
                format="%d%%",
                key=f"_w_{_dim}",
                on_change=_on_weight_slider,
            )
        _total_w = sum(st.session_state[f"_w_{d}"] for d, _, _, _ in _SLIDER_DIMS)
        if abs(_total_w - 100) > 1:
            st.warning(f"Weights sum to {_total_w}% — must equal 100%")

        st.markdown("---")

        # ── Memo Template ─────────────────────────────────────────────────
        st.markdown(
            "<div class='section-label'>Memo Template</div>",
            unsafe_allow_html=True,
        )
        for _sec_key, _sec_label in _MEMO_SECTION_LABELS:
            st.checkbox(_sec_label, key=f"_msec_{_sec_key}")

        st.markdown("---")
        st.markdown(
            "<div class='section-label'>Investment Mandate</div>",
            unsafe_allow_html=True,
        )
        _fm_name = st.text_input(
            "Firm Name",
            value=st.session_state["firm_mandate"].get("firm_name", ""),
            placeholder="e.g., ETS Capital",
            key="_fm_firm_name",
        )
        _fm_rev_min = st.number_input(
            "Target Revenue Min ($M)",
            min_value=0.0,
            value=float(st.session_state["firm_mandate"].get("target_revenue_min_m", 0.0)),
            step=10.0,
            key="_fm_rev_min",
        )
        _fm_rev_max = st.number_input(
            "Target Revenue Max ($M)",
            min_value=0.0,
            value=float(st.session_state["firm_mandate"].get("target_revenue_max_m", 10000.0)),
            step=10.0,
            key="_fm_rev_max",
        )
        _fm_min_margin = st.number_input(
            "Min EBITDA Margin (%)",
            min_value=0.0,
            value=float(st.session_state["firm_mandate"].get("min_ebitda_margin_pct", 0.0)),
            step=1.0,
            key="_fm_min_margin",
        )
        _fm_sectors = st.multiselect(
            "Target Sectors",
            options=[
                "Healthcare",
                "Education & EdTech",
                "Enterprise Software",
                "Fintech",
                "Industrials",
                "Consumer",
                "Cybersecurity",
                "Infrastructure",
                "Gaming & Entertainment",
                "Other",
            ],
            default=st.session_state["firm_mandate"].get("target_sectors", []),
            key="_fm_sectors",
        )
        _fm_min_rec = st.number_input(
            "Min Recurring Revenue (%)",
            min_value=0.0,
            value=float(st.session_state["firm_mandate"].get("min_recurring_revenue_pct", 0.0)),
            step=1.0,
            key="_fm_min_rec",
        )
        st.session_state["firm_mandate"] = {
            "firm_name": _fm_name.strip(),
            "target_revenue_min_m": float(_fm_rev_min),
            "target_revenue_max_m": float(_fm_rev_max),
            "min_ebitda_margin_pct": float(_fm_min_margin),
            "target_sectors": list(_fm_sectors),
            "min_recurring_revenue_pct": float(_fm_min_rec),
        }

    analyze_btn = st.button(
        "Analyze",
        type="primary",
        width="stretch",
        disabled=(uploaded_file is None),
    )
    if st.button("View Pipeline", width="stretch"):
        st.session_state["_preview_panel"] = "pipeline"
    st.markdown("---")
    st.markdown("<div class='section-label'>Portfolio</div>", unsafe_allow_html=True)
    if st.button("Portfolio Intelligence", width="stretch"):
        st.session_state["_preview_panel"] = "portfolio"
    st.caption("Cross-portfolio reporting and health monitoring.")
    if st.button("Data Room", width="stretch"):
        st.session_state["_preview_panel"] = "data_room"
    st.caption("Document management and VDR integration.")

    # ── Post-analysis sidebar content ────────────────────────────────────
    if st.session_state.result:
        result = st.session_state.result
        co     = result.extracted_data.get("company_overview", {})
        ds     = result.deal_score

        st.markdown("---")

        # Company name + sector
        company_name = co.get("company_name", "Unknown")
        industry     = co.get("industry", "")
        sub_industry = co.get("sub_industry", "")
        sector_line  = " / ".join(filter(None, [industry, sub_industry]))

        st.markdown(
            f"<p style='font-size:1.05rem;font-weight:700;color:#e8e8e8;"
            f"margin-bottom:0.05rem;margin-top:0'>{company_name}</p>"
            f"<p style='font-size:0.8rem;color:#8888aa;margin-top:0'>{sector_line}</p>",
            unsafe_allow_html=True,
        )

        # Deal score badge
        if ds:
            _sidebar_rec = ds.recommendation
            _sidebar_m_eval = _evaluate_mandate_fit(
                result.extracted_data,
                st.session_state.get("firm_mandate", {}),
            )
            if (
                _sidebar_m_eval.get("active_criteria", 0) > 0
                and _sidebar_m_eval.get("fit_pct") is not None
                and _sidebar_m_eval.get("fit_pct") < 50
            ):
                _sidebar_rec = _downgrade_recommendation(_sidebar_rec)
            grade_colour = _score_colour(ds.total_score)
            st.markdown(
                f"<p style='margin-bottom:0.1rem'><span style='font-size:0.75rem;"
                f"color:#8888aa;text-transform:uppercase;letter-spacing:0.08em'>"
                f"Deal Score</span></p>"
                f"<p style='margin-top:0;font-size:1.5rem;font-weight:800;"
                f"color:{grade_colour};line-height:1'>"
                f"{ds.total_score:.0%} &nbsp;<span style='font-size:1rem'>"
                f"Grade {ds.grade}</span></p>"
                f"<p style='font-size:0.78rem;color:#8888aa;margin-top:0.1rem'>"
                f"{_sidebar_rec}</p>",
                unsafe_allow_html=True,
            )

        # Risk alerts
        if result.risks:
            critical = sum(1 for r in result.risks if r.severity == "Critical")
            high     = sum(1 for r in result.risks if r.severity == "High")
            if critical:
                st.error(f"{critical} critical risk(s) flagged", icon="🚨")
            if high:
                st.warning(f"{high} high risk(s) flagged", icon="⚠️")

        # ── Exports ───────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("<div class='section-label'>Export</div>", unsafe_allow_html=True)

        # Cache export bytes keyed by result identity
        if st.session_state.get("_exports_for") is not result:
            st.session_state["_exports_for"] = result
            st.session_state["_xlsx_bytes"]  = None
            st.session_state["_xlsx_err"]    = None
            st.session_state["_docx_bytes"]  = None
            st.session_state["_docx_err"]    = None
            st.session_state["_pptx_bytes"]  = None
            st.session_state["_pptx_err"]    = None
            st.session_state["_json_bytes"]  = None
            st.session_state["_json_err"]    = None
            st.session_state["_zip_bytes"]   = None
            st.session_state["_zip_err"]     = None
            try:
                st.session_state["_xlsx_bytes"] = _make_xlsx_bytes(result)
            except Exception as _e:
                st.session_state["_xlsx_err"] = str(_e)
            try:
                st.session_state["_docx_bytes"] = _make_docx_bytes(result)
            except Exception as _e:
                st.session_state["_docx_err"] = str(_e)
            try:
                st.session_state["_pptx_bytes"] = _make_pptx_bytes(result)
            except Exception as _e:
                st.session_state["_pptx_err"] = str(_e)
            try:
                st.session_state["_json_bytes"] = _make_json_bytes(result)
            except Exception as _e:
                st.session_state["_json_err"] = str(_e)

        company_slug = co.get("company_name", "analysis").replace(" ", "_")
        if st.session_state.get("_zip_bytes") is None and st.session_state.get("_zip_err") is None:
            try:
                zip_buf = io.BytesIO()
                wrote_any = False
                with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    if st.session_state.get("_xlsx_bytes") is not None:
                        zf.writestr(f"{company_slug}_analysis.xlsx", st.session_state["_xlsx_bytes"])
                        wrote_any = True
                    if st.session_state.get("_docx_bytes") is not None:
                        zf.writestr(f"{company_slug}_memo.docx", st.session_state["_docx_bytes"])
                        wrote_any = True
                    if st.session_state.get("_pptx_bytes") is not None:
                        zf.writestr(f"{company_slug}_ic_deck.pptx", st.session_state["_pptx_bytes"])
                        wrote_any = True
                if wrote_any:
                    st.session_state["_zip_bytes"] = zip_buf.getvalue()
                else:
                    st.session_state["_zip_err"] = "No export files available to package."
            except Exception as _e:
                st.session_state["_zip_err"] = str(_e)

        if st.session_state.get("_zip_bytes") is not None:
            st.download_button(
                label="📦 IC Package (.zip)",
                data=st.session_state["_zip_bytes"],
                file_name=f"{company_slug}_IC_Package.zip",
                mime="application/zip",
                width="stretch",
                type="primary",
            )
            st.caption("Excel model + IC memo + IC deck")
        else:
            st.caption(f"IC Package unavailable: {st.session_state.get('_zip_err')}")

        if st.session_state["_xlsx_bytes"] is not None:
            st.download_button(
                label="Excel Report",
                data=st.session_state["_xlsx_bytes"],
                file_name=f"{company_slug}_analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        else:
            st.caption(f"Excel unavailable: {st.session_state['_xlsx_err']}")

        if st.session_state["_docx_bytes"] is not None:
            st.download_button(
                label="IC Memo (Word)",
                data=st.session_state["_docx_bytes"],
                file_name=f"{company_slug}_memo.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
            )
        else:
            st.caption(f"Word unavailable: {st.session_state['_docx_err']}")

        if st.session_state["_pptx_bytes"] is not None:
            st.download_button(
                label="IC Deck (PowerPoint)",
                data=st.session_state["_pptx_bytes"],
                file_name=f"{company_slug}_ic_deck.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                width="stretch",
            )
        else:
            st.caption(f"IC Deck unavailable: {st.session_state['_pptx_err']}")

        if st.session_state["_json_bytes"] is not None:
            st.download_button(
                label="Raw JSON",
                data=st.session_state["_json_bytes"],
                file_name=f"{company_slug}_raw.json",
                mime="application/json",
                width="stretch",
            )
        else:
            st.caption(f"JSON unavailable: {st.session_state['_json_err']}")

# ---------------------------------------------------------------------------
# Pipeline initialisation
# ---------------------------------------------------------------------------

if st.session_state.pipeline is None:
    with st.spinner("Loading pipeline…"):
        pipeline_or_tuple = _get_pipeline()
        if isinstance(pipeline_or_tuple, tuple):
            st.error(f"Pipeline init failed: {pipeline_or_tuple[1]}")
        else:
            st.session_state.pipeline = pipeline_or_tuple

# ---------------------------------------------------------------------------
# Analysis trigger
# ---------------------------------------------------------------------------

def _execute_analysis_workflow(uploaded_file, scoring_profile: str):
    st.session_state["_preview_panel"] = None
    st.session_state.result       = None
    st.session_state.document     = None
    st.session_state.messages     = []
    st.session_state.fund_matches = None

    start_time = time.time()

    _progress_text = st.empty()
    _progress_bar = st.progress(0)

    def _progress_cb(pct: int, label: str, _elapsed: float):
        _progress_bar.progress(int(max(0, min(100, pct))))
        _progress_text.caption(label)

    result, err = _run_analysis(uploaded_file, scoring_profile, _progress_cb)
    if err:
        _progress_bar.progress(100)
        _progress_text.caption("Analysis failed")
    else:
        elapsed = time.time() - start_time
        _progress_bar.progress(100)
        _progress_text.caption(f"Completed in {int(round(elapsed))}s")

    if err:
        st.error(f"Analysis failed: {err}")
    else:
        st.session_state["_pipeline_inline_upload"] = False
        st.rerun()


if analyze_btn and uploaded_file:
    if getattr(uploaded_file, "size", 0) and uploaded_file.size > 200 * 1024 * 1024:
        st.error("File exceeds 200MB limit.")
    else:
        _execute_analysis_workflow(uploaded_file, scoring_profile)

# ---------------------------------------------------------------------------
# Results tabs
# ---------------------------------------------------------------------------

_preview_panel = st.session_state.get("_preview_panel")
if _preview_panel in ("portfolio", "compare", "pipeline", "data_room"):
    _panel_title = {
        "portfolio": "Portfolio Intelligence",
        "compare": "Deal Comparison",
        "pipeline": "Deal Pipeline Dashboard",
        "data_room": "Data Room",
    }.get(_preview_panel, "Meridian")
    c_prev, c_close = st.columns([6, 1])
    with c_prev:
        st.markdown(
            f"<h3 style='color:#e8e8e8;margin-bottom:0.2rem'>{_panel_title}</h3>",
            unsafe_allow_html=True,
        )
    with c_close:
        if st.button("Back", width="stretch", key="_preview_back"):
            st.session_state["_preview_panel"] = None
            st.rerun()

    if _preview_panel == "portfolio":
        _render_portfolio_view(show_title=False)
    elif _preview_panel == "compare":
        _render_compare_view()
    elif _preview_panel == "data_room":
        _render_data_room_view(show_title=False)
    else:
        _render_pipeline_dashboard(show_title=False)
    st.stop()

if st.session_state.result:
    result = st.session_state.result
    co     = result.extracted_data.get("company_overview", {})
    fin    = result.extracted_data.get("financials", {})
    rev    = fin.get("revenue", {})
    ebitda = fin.get("ebitda", {})

    # ── Page header ───────────────────────────────────────────────────────
    company_name = co.get("company_name", "Unknown Company")
    st.markdown(
        f"<h2 style='color:#e8e8e8;margin-bottom:0.1rem;font-size:1.8rem'>"
        f"{company_name}</h2>",
        unsafe_allow_html=True,
    )
    detail_parts = [
        co.get("industry", ""),
        co.get("sub_industry", ""),
        co.get("headquarters", ""),
        co.get("business_model", ""),
    ]
    st.caption("  ·  ".join(p for p in detail_parts if p))

    # ── Key metrics strip ─────────────────────────────────────────────────
    def _is_missing(v):
        return v is None or v == "not_provided"
    def _to_num(v):
        if _is_missing(v):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    ebitda_ltm_val = ebitda.get("ltm")
    adj_ebitda_val = ebitda.get("adjusted_ebitda_ltm")
    derived_ebitda_val = ebitda.get("derived_ebitda")
    selected_ebitda_val = ebitda_ltm_val
    if not _is_missing(ebitda_ltm_val):
        ebitda_label = "EBITDA (LTM)"
        selected_ebitda_val = ebitda_ltm_val
    elif not _is_missing(adj_ebitda_val):
        ebitda_label = "Adj. EBITDA (LTM)"
        selected_ebitda_val = adj_ebitda_val
    elif not _is_missing(derived_ebitda_val):
        ebitda_label = "Est. EBITDA (LTM)"
        selected_ebitda_val = derived_ebitda_val
    else:
        ebitda_label = "EBITDA (LTM)"
        selected_ebitda_val = ebitda_ltm_val
    ebitda_value = _fmt_num(selected_ebitda_val)

    margin_val = ebitda.get("margin_ltm")
    margin_label = "EBITDA Margin"
    if _is_missing(margin_val):
        rev_num = _to_num(rev.get("ltm"))
        ebitda_num = _to_num(selected_ebitda_val)
        if rev_num and rev_num != 0 and ebitda_num is not None:
            margin_val = ebitda_num / rev_num
            margin_label = "Est. EBITDA Margin"

    cols = st.columns(5, gap="small")
    metrics = [
        ("Revenue (LTM)",   _fmt_num(rev.get("ltm"))),
        (ebitda_label,      ebitda_value),
        (margin_label,      _fmt_pct(margin_val)),
        ("Revenue CAGR",    _fmt_pct(rev.get("cagr_3yr"))),
        ("Recurring Rev %", _fmt_pct(fin.get("recurring_revenue_pct"))),
    ]
    for col, (label, val) in zip(cols, metrics):
        col.markdown(
            "<div class='hero-metric-card'>"
            f"<div class='hero-metric-label'>{label}</div>"
            f"<div class='hero-metric-value'>{val}</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    _render_verification_summary(result.extracted_data, getattr(result, "narrative_gaps", []))
    st.markdown("---")

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_memo, tab_fin, tab_risks, tab_comps, tab_score, tab_qa = st.tabs(
        ["Memo", "Financials", "Risks", "Comps", "Score", "Q&A"]
    )

    # ── Tab: Memo ─────────────────────────────────────────────────────────
    with tab_memo:
        if result.memo:
            st.markdown("<div class='memo-content'>", unsafe_allow_html=True)
            _render_memo(result.memo)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Memo generation was disabled or not yet run.")

    # ── Tab: Financials ───────────────────────────────────────────────────
    with tab_fin:
        import altair as alt
        import pandas as pd
        customers = result.extracted_data.get("customers", {})

        # Currency badge — show when non-USD or when explicitly stated
        _currency = _fmt_str(fin.get("currency"))
        if _currency not in ("N/A", "", "USD"):
            st.warning(
                f"**Currency: {_currency}** — All figures reported in {_currency}, not USD.",
                icon="⚠️",
            )
        elif _currency == "USD":
            st.caption("All figures in USD.")

        rev_cite_ltm = rev.get("ltm_citation")
        rev_cite_cagr = rev.get("cagr_3yr_citation")
        ebitda_cite_ltm = ebitda.get("ltm_citation")
        ebitda_cite_adj = ebitda.get("adjusted_ebitda_ltm_citation")
        ebitda_cite_margin = ebitda.get("margin_ltm_citation")
        gross_margin_cite = fin.get("gross_margin_citation")
        capex_cite = fin.get("capex_citation")
        top_customer_cite = customers.get("top_customer_concentration_citation")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                "<div class='section-label'>Income Statement</div>",
                unsafe_allow_html=True,
            )
            fin_rows = {
                "Revenue LTM":          (_fmt_num(rev.get("ltm")), rev_cite_ltm),
                "Revenue (Prior Year)": (_fmt_num(rev.get("prior_year")), None),
                "Revenue (2yr Ago)":    (_fmt_num(rev.get("two_years_ago")), None),
                "CAGR (3yr)":           (_fmt_pct(rev.get("cagr_3yr")), rev_cite_cagr),
                "EBITDA LTM":           (_fmt_num(ebitda.get("ltm")), ebitda_cite_ltm),
                "Adjusted EBITDA":      (_fmt_num(ebitda.get("adjusted_ebitda_ltm")), ebitda_cite_adj),
                "EBITDA Margin":        (_fmt_pct(ebitda.get("margin_ltm")), ebitda_cite_margin),
                "Gross Margin":         (_fmt_pct(fin.get("gross_margin")), gross_margin_cite),
                "Net Income":           (_fmt_num(fin.get("net_income")), None),
            }
            for label, (val, cite) in fin_rows.items():
                cc1, cc2 = st.columns([2, 1])
                cc1.write(label)
                cc2.markdown(_metric_with_page(val, cite), unsafe_allow_html=True)

        with c2:
            st.markdown(
                "<div class='section-label'>Balance Sheet & Revenue Mix</div>",
                unsafe_allow_html=True,
            )
            bs_rows = {
                "Total Debt":             (_fmt_num(fin.get("debt")), None),
                "Cash & Equivalents":     (_fmt_num(fin.get("cash")), None),
                "CapEx (Annual)":         (_fmt_num(fin.get("capex")), capex_cite),
                "Recurring Revenue %":    (_fmt_pct(fin.get("recurring_revenue_pct")), None),
                "Total Customers":        (_fmt_str(customers.get("total_customers")), None),
                "Top Customer Conc.":     (_fmt_pct(customers.get("top_customer_concentration")), top_customer_cite),
                "Top 10 Conc.":           (_fmt_pct(customers.get("top_10_concentration")), None),
                "Customer Retention":     (_fmt_pct(customers.get("customer_retention")), None),
                "Net Revenue Retention":  (_fmt_pct(customers.get("net_revenue_retention")), None),
            }
            for label, (val, cite) in bs_rows.items():
                cc1, cc2 = st.columns([2, 1])
                cc1.write(label)
                cc2.markdown(_metric_with_page(val, cite), unsafe_allow_html=True)

        rev_points = [
            ("2yr Ago", rev.get("two_years_ago")),
            ("Prior Year", rev.get("prior_year")),
            ("LTM", rev.get("ltm")),
        ]
        rev_chart_rows = [
            {"Period": p, "RevenueM": float(v) / 1_000_000}
            for p, v in rev_points
            if isinstance(v, (int, float))
        ]
        if rev_chart_rows:
            st.caption("Revenue Trend")
            rev_df = pd.DataFrame(rev_chart_rows)
            rev_chart = (
                alt.Chart(rev_df)
                .mark_bar(color="#6f91ff", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("Period:N", sort=["2yr Ago", "Prior Year", "LTM"], title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("RevenueM:Q", title=f"Revenue ({_currency}M)", axis=alt.Axis(format=",.0f")),
                    tooltip=["Period", alt.Tooltip("RevenueM:Q", format=",.1f", title=f"Revenue ({_currency}M)")],
                )
                .properties(height=220)
            )
            st.altair_chart(rev_chart, width="stretch")

        # Revenue by segment
        segments = fin.get("revenue_by_segment", [])
        if segments:
            st.caption("Revenue by Segment")
            seg_rows = []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                yoy = seg.get("growth_rate")
                yoy_fmt = _fmt_pct(yoy) if yoy not in (None, "not_provided") else "N/A"
                if yoy_fmt != "N/A":
                    yoy_fmt = f"{yoy_fmt} YoY"
                seg_rows.append({
                    "Segment name": seg.get("segment", "N/A"),
                    "Dollar amount": _fmt_num(seg.get("revenue")),
                    "% of total": _fmt_pct(seg.get("pct_of_total")),
                    "YoY growth": yoy_fmt,
                })
            seg_df = pd.DataFrame(seg_rows)
            st.dataframe(
                seg_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Segment name": st.column_config.TextColumn(width="large"),
                    "Dollar amount": st.column_config.TextColumn(width="medium"),
                    "% of total": st.column_config.TextColumn(width="small"),
                    "YoY growth": st.column_config.TextColumn(width="small"),
                },
            )

    # ── Tab: Risks ────────────────────────────────────────────────────────
    with tab_risks:
        memo_risks      = _extract_memo_risks(result.memo)
        heuristic_risks = [r for r in (result.risks or []) if r.source == "heuristic"]
        llm_risks       = [r for r in (result.risks or []) if r.source == "llm"]
        _ngaps          = getattr(result, "narrative_gaps", None) or []

        has_any = memo_risks or heuristic_risks or llm_risks or _ngaps

        if not has_any:
            st.info("No risks identified (or risk analysis was disabled).")

        # ── Section 1: Automated Flags ────────────────────────────────────
        st.markdown("### Automated Flags")
        st.caption("Rule-based checks triggered by extracted financial and operational metrics.")
        if heuristic_risks:
            for risk in heuristic_risks:
                sev_colour = _severity_colour(risk.severity)
                with st.expander(
                    f"[{risk.severity}] {risk.category} — {risk.title}",
                    expanded=(risk.severity in ("Critical", "High")),
                ):
                    st.markdown(
                        f"<span style='background:{sev_colour};color:white;"
                        f"padding:2px 10px;border-radius:4px;font-weight:600;font-size:0.8rem'>"
                        f"{risk.severity}</span> &nbsp; **{risk.category}**",
                        unsafe_allow_html=True,
                    )
                    st.markdown(_escape_dollars(risk.description))
                    if risk.diligence_question:
                        st.info(f"**Diligence:** {_escape_dollars(risk.diligence_question)}")
        else:
            st.caption("No automated flags triggered.")

        # ── Section 2: Narrative Validation ──────────────────────────────
        st.divider()
        st.markdown("### Narrative Validation")
        st.caption(
            "Structured AI risk extraction and cross-check of memo claims against "
            "extracted financials."
        )

        if llm_risks:
            for risk in llm_risks:
                sev_colour = _severity_colour(risk.severity)
                with st.expander(
                    f"[{risk.severity}] {risk.category} — {risk.title}",
                    expanded=(risk.severity in ("Critical", "High")),
                ):
                    st.markdown(
                        f"<span style='background:{sev_colour};color:white;"
                        f"padding:2px 10px;border-radius:4px;font-weight:600;font-size:0.8rem'>"
                        f"{risk.severity}</span> &nbsp; **{risk.category}**",
                        unsafe_allow_html=True,
                    )
                    st.markdown(_escape_dollars(risk.description))
                    if risk.mitigant:
                        st.success(f"**Mitigant:** {_escape_dollars(risk.mitigant)}")
                    if risk.diligence_question:
                        st.info(f"**Diligence:** {_escape_dollars(risk.diligence_question)}")

        if _ngaps:
            st.caption("Programmatic claim validation:")
            _ng_confirmed    = [g for g in _ngaps if g["status"] == "confirmed"]
            _ng_discrepancy  = [g for g in _ngaps if g["status"] == "discrepancy"]
            _ng_unverifiable = [g for g in _ngaps if g["status"] == "unverifiable"]

            _nv_c1, _nv_c2, _nv_c3 = st.columns(3)
            _nv_c1.metric("✅ Confirmed",     len(_ng_confirmed))
            _nv_c2.metric("⚠️ Discrepancies", len(_ng_discrepancy))
            _nv_c3.metric("❓ Unverifiable",   len(_ng_unverifiable))

            if _ng_discrepancy:
                for _g in sorted(_ng_discrepancy,
                                  key=lambda x: {"critical": 0, "warning": 1}.get(x["severity"], 2)):
                    _icon = "🔴" if _g["severity"] == "critical" else "🟡"
                    with st.expander(
                        f"{_icon} {_g['claim']}",
                        expanded=(_g["severity"] == "critical"),
                    ):
                        st.markdown(f"**Source:** {_g['claim_source']}")
                        st.markdown(f"**Extracted:** `{_g['extracted_value']}`")
                        if _g.get("gap"):
                            st.warning(_g["gap"])

            if _ng_confirmed:
                with st.expander(f"✅ {len(_ng_confirmed)} confirmed claim(s)", expanded=False):
                    for _g in _ng_confirmed:
                        _claim_h    = html.escape(str(_g.get("claim", ""))).replace("$", "&#36;")
                        _exval_h    = html.escape(str(_g.get("extracted_value", ""))).replace("$", "&#36;")
                        _src_h      = html.escape(str(_g.get("claim_source", "")))
                        st.markdown(
                            f"<div style='margin:3px 0 3px 8px'>"
                            f"• <b>{_claim_h}</b> — <code>{_exval_h}</code> "
                            f"<em style='color:#888'>({_src_h})</em></div>",
                            unsafe_allow_html=True,
                        )

            if _ng_unverifiable:
                with st.expander(f"❓ {len(_ng_unverifiable)} unverifiable claim(s)", expanded=False):
                    for _g in _ng_unverifiable:
                        _claim_h    = html.escape(str(_g.get("claim", ""))).replace("$", "&#36;")
                        _exval_h    = html.escape(str(_g.get("extracted_value", ""))).replace("$", "&#36;")
                        _src_h      = html.escape(str(_g.get("claim_source", "")))
                        st.markdown(
                            f"<div style='margin:3px 0 3px 8px'>"
                            f"• <b>{_claim_h}</b> — <code>{_exval_h}</code> "
                            f"<em style='color:#888'>({_src_h})</em></div>",
                            unsafe_allow_html=True,
                        )
        elif not llm_risks:
            st.caption("No narrative validation issues detected.")

        # ── Section 3: Diligence Risks from Memo ─────────────────────────
        st.divider()
        st.markdown("### Diligence Risks from Memo")
        st.caption("Qualitative risks parsed from the investment memo.")
        if memo_risks:
            for item in memo_risks:
                if isinstance(item, dict):
                    title = (item.get("risk") or item.get("title") or "").strip()
                    title = title.replace("**", "").replace("*", "").replace("\n", "").strip()
                    description = (item.get("description") or "").strip()
                    mitigant = (item.get("mitigant") or item.get("mitigation") or "").strip()
                    label = (item.get("risk") or "").replace("**", "").replace("*", "").replace("\n", "").strip()
                    if ": " in label and len(label) > 80:
                        label = label.split(": ")[0]
                    label = label[:80] or description[:80]
                    if not label:
                        continue
                    with st.expander(label, expanded=False):
                        if description:
                            st.markdown(_escape_dollars(description))
                        else:
                            st.markdown(f"**{_escape_dollars(title)}**")
                        if mitigant:
                            st.success(f"**Mitigant:** {_escape_dollars(mitigant)}")
                elif isinstance(item, str) and item.strip():
                    with st.expander(item.strip()[:80], expanded=False):
                        st.markdown(f"**{_escape_dollars(item.strip())}**")
        else:
            st.caption("No memo-derived diligence risks available.")

        if has_any:
            st.caption("Meridian AI · Risk Assessment")

        # ── Section 4: Sector-Specific Flags ──────────────────────────────
        _industry = st.session_state.get("industry_profile", "General")
        _sector_flags = _SECTOR_FLAGS.get(_industry, [])
        if _industry != "General":
            st.divider()
            st.markdown("### Sector-Specific Flags")
            st.caption(
                f"Domain considerations for {_industry} investments — "
                "shown independently of document extraction."
            )
            if _sector_flags:
                for _icon, _title, _body in _sector_flags:
                    st.info(f"**{_icon} {_title}** — {_body}")
            else:
                st.caption("No sector-specific flags configured for this profile.")


    # ── Tab: Comps ────────────────────────────────────────────────────────
    with tab_comps:
        comps = result.comps or []
        if not comps:
            st.markdown(
                "<div class='info-card'>"
                "<h4>Comparable Company Analysis — Requires API Integration</h4>"
                "<p>Connect PitchBook or Capital IQ credentials to auto-populate "
                "financial comparables for this deal.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

            # Pull peers from extracted data
            market_data     = result.extracted_data.get("market", {})
            co_data         = result.extracted_data.get("company_overview", {})
            peers           = []

            market_position = co_data.get("market_position")
            if (market_position and
                    isinstance(market_position, str) and
                    market_position not in ("not_provided", "N/A", "")):
                peers.append(market_position)

            key_competitors = market_data.get("key_competitors") or []
            if isinstance(key_competitors, list):
                for c in key_competitors:
                    if isinstance(c, str) and c not in ("not_provided", "N/A", ""):
                        if c not in peers:
                            peers.append(c)

            if peers:
                peers_md = "  ·  ".join(f"*{p}*" for p in peers)
                st.markdown(
                    f"**Identified peers from document analysis:** {peers_md}"
                )

            comp_position = market_data.get("competitive_position")
            if comp_position and comp_position not in ("not_provided", "N/A", ""):
                st.caption(f"Competitive position: {comp_position}")

        else:
            import pandas as pd
            rows = []
            for c in comps:
                rows.append({
                    "Company / Deal":  c.name,
                    "Type":            c.type.replace("_", " ").title(),
                    "EV/Revenue":      f"{c.ev_revenue:.1f}x" if c.ev_revenue else "N/A",
                    "EV/EBITDA":       f"{c.ev_ebitda:.1f}x" if c.ev_ebitda else "N/A",
                    "Confidence":      f"{c.confidence:.0%}",
                    "Rationale":       c.rationale,
                    "Key Differences": c.key_differences,
                })
            comp_df = pd.DataFrame(rows)
            st.dataframe(comp_df, width="stretch", hide_index=True)

        # PE Fund Matches — always visible
        st.markdown("---")
        st.markdown(
            "<div class='section-label'>PE Fund Matches</div>",
            unsafe_allow_html=True,
        )
        if st.session_state.fund_matches:
            matches = st.session_state.fund_matches
            for i, m in enumerate(matches, 1):
                bar_colour = _score_colour(m.total_score)
                with st.expander(
                    f"#{i}  {m.fund.name}  —  {m.total_score:.0%} match",
                    expanded=(i == 1),
                ):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"**Thesis:** {_escape_dollars(m.fund.thesis_summary)}")
                        st.caption(
                            _escape_dollars(
                                f"{m.fund.headquarters}  ·  {m.fund.fund_size_category} Market  ·  "
                                f"${m.fund.check_size_min_mm}M–${m.fund.check_size_max_mm}M checks  ·  "
                                f"{m.fund.investment_style}"
                            )
                        )
                        for reason in m.reasons[:4]:
                            st.write(_escape_dollars(f"✓ {reason}"))
                        for concern in m.concerns:
                            st.write(_escape_dollars(f"⚠ {concern}"))
                    with c2:
                        sub_scores = {
                            "Industry":  m.industry_score,
                            "Size":      m.size_score,
                            "Geography": m.geography_score,
                            "Strategic": m.strategic_score,
                        }
                        for label, s in sub_scores.items():
                            st.markdown(
                                f"<small style='color:#8888aa'>{label}</small><br>"
                                f"<div class='score-bar-bg'>"
                                f"<div class='score-bar-fg' style='width:{s*100:.0f}%;"
                                f"background:{_score_colour(s)}'></div></div>"
                                f"<small style='color:#8888aa'>{s:.0%}</small>",
                                unsafe_allow_html=True,
                            )
        else:
            st.caption("Fund matching data not available.")

    # ── Tab: Score ────────────────────────────────────────────────────────
    with tab_score:
        ds = result.deal_score
        if not ds:
            st.info("Deal scoring was disabled or not yet run.")
        else:
            mandate = st.session_state.get("firm_mandate", {})
            mandate_eval = _evaluate_mandate_fit(result.extracted_data, mandate)
            mandate_fit = mandate_eval.get("fit_pct")
            active_criteria = mandate_eval.get("active_criteria", 0)
            failed_n = mandate_eval.get("failed_n", 0)
            display_recommendation = ds.recommendation
            if active_criteria > 0 and mandate_fit is not None and mandate_fit < 50:
                display_recommendation = _downgrade_recommendation(display_recommendation)

            grade_col = _score_colour(ds.total_score)
            st.markdown(
                f"""
                <div style='background:{grade_col}18;border:1px solid {grade_col}55;
                            border-radius:12px;padding:1.5rem 2rem;text-align:center;
                            margin-bottom:1.2rem'>
                    <div style='font-size:3.5rem;font-weight:900;color:{grade_col};
                                line-height:1'>{ds.grade}</div>
                    <div style='font-size:1.3rem;color:#e8e8e8;margin-top:0.3rem'>
                        {ds.total_score:.0%} Overall Score</div>
                    <div style='font-size:0.95rem;color:#8888aa;margin-top:0.3rem'>
                        {display_recommendation}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(ds.summary)
            if active_criteria > 0 and mandate_fit is not None and mandate_fit < 50:
                firm_name = (mandate.get("firm_name") or "this firm").strip()
                st.warning(
                    f"⚠️ This deal falls outside {firm_name}'s investment mandate on {failed_n} criteria."
                )
            st.markdown(
                "<div class='section-label'>Key Observations</div>",
                unsafe_allow_html=True,
            )
            insights = (
                result.insights
                if hasattr(result, "insights")
                else st.session_state.get("_result", {}).get("insights", [])
            )
            if not isinstance(insights, list) or not insights:
                st.caption("Key observations will appear after analysis completes.")
            else:
                sev_cfg = {
                    "positive": ("insight-positive", "✅"),
                    "info": ("insight-info", "ℹ️"),
                    "warning": ("insight-warning", "⚠️"),
                }
                for item in insights:
                    if not isinstance(item, dict):
                        continue
                    severity = str(item.get("severity", "info")).lower()
                    css_cls, icon = sev_cfg.get(severity, sev_cfg["info"])
                    title = html.escape(str(item.get("title") or "Observation"))
                    detail = html.escape(str(item.get("detail") or item.get("content") or ""))
                    with st.container():
                        st.markdown(
                            f"<div class='insight-card {css_cls}'>"
                            f"<div class='insight-title'>{icon} {title}</div>"
                            f"<div class='insight-detail'>{_escape_dollars(detail)}</div>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
            st.markdown("---")

            st.markdown(
                "<div class='section-label'>Dimension Breakdown</div>",
                unsafe_allow_html=True,
            )
            for dim in ds.dimensions:
                score_colour = _score_colour(dim.score)
                c_label, c_bar, c_pct = st.columns([3, 5, 1])
                c_label.write(f"**{dim.dimension}**")
                c_bar.progress(dim.score)
                c_pct.markdown(
                    f"<span style='color:{score_colour};font-weight:700'>"
                    f"{dim.score:.0%}</span>",
                    unsafe_allow_html=True,
                )
                cc1, cc2 = st.columns([4, 1])
                cc1.caption(dim.rationale)
                cc2.caption(f"wt {dim.weight:.0%}  ·  data: {dim.data_quality.replace('_', ' ')}")
                st.markdown("")

            if active_criteria > 0 and mandate_fit is not None:
                st.markdown("---")
                st.markdown(
                    "<div class='section-label'>Mandate Fit</div>",
                    unsafe_allow_html=True,
                )
                firm_name = (mandate.get("firm_name") or "").strip()
                if firm_name:
                    st.markdown(f"**{firm_name} Mandate Fit: {mandate_fit}%**")
                else:
                    st.markdown(f"**Mandate Fit: {mandate_fit}%**")
                for _passed, line in mandate_eval.get("criteria", []):
                    st.markdown(_escape_dollars(line))

    # ── Tab: Q&A ──────────────────────────────────────────────────────────
    with tab_qa:
        st.markdown(
            "<div class='section-label'>Ask the Document</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Ask any question about this deal. Answers are grounded in the "
            "parsed document and extracted data."
        )

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_question = st.chat_input("Ask a question about this deal…")
        if user_question:
            st.session_state.messages.append({"role": "user", "content": user_question})
            with st.chat_message("user"):
                st.write(user_question)

            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    try:
                        pipeline = st.session_state.pipeline
                        document = st.session_state.document
                        answer   = pipeline.qa_engine.ask(
                            question=user_question,
                            document=document,
                            extracted_data=result.extracted_data,
                        )
                    except Exception as exc:
                        answer = f"Error: {exc}"
                st.write(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

else:
    _render_pipeline_dashboard()

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    "<div class='meridian-footer'>Meridian AI &nbsp;·&nbsp; PE Deal Intelligence</div>",
    unsafe_allow_html=True,
)
