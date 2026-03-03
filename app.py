"""Meridian AI — Streamlit web application.

Upload a CIM → progress tracking → tabbed analysis display:
  Memo | Financials | Risks | Comps | Score | Q&A

Run with:
    streamlit run app.py
"""

import io
import os
import sys
import tempfile
import time
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

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
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
        margin-top: 1.5rem;
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


def _render_memo(memo_text: str):
    """Render the investment memo from a JSON string or plain markdown.

    Supports two JSON shapes:
      Format A — {"investment_committee_memo": {"executive_summary": ..., ...}}
      Format B — {"memo": {"sections": [{"heading": ..., "content": ...}, ...]}}

    All content is dollar-escaped before passing to st.markdown() to prevent
    Streamlit from mis-interpreting financial figures as LaTeX.
    """
    import json as _json

    # Keyed sections for Format A
    _SECTIONS = [
        ("executive_summary",       "Executive Summary"),
        ("company_overview",        "Company Overview"),
        ("financial_highlights",    "Financial Highlights"),
        ("growth_thesis",           "Growth Thesis"),
        ("key_risks_and_mitigants", "Key Risks & Mitigants"),
        ("valuation_context",       "Valuation Context"),
        ("key_diligence_questions", "Key Diligence Questions"),
        ("recommendation",          "Recommendation"),
    ]

    data = None
    try:
        data = _json.loads(memo_text)
    except (_json.JSONDecodeError, TypeError):
        pass

    if data is None:
        # Plain markdown — render the whole memo as one block.
        # Splitting by section would mangle numbered lists (diligence questions etc.).
        st.markdown(_escape_dollars(memo_text))
        return

    # ── Format A: investment_committee_memo keyed structure ───────────────
    icm = data.get("investment_committee_memo")
    if isinstance(icm, dict):
        rendered_any = False
        for key, title in _SECTIONS:
            if not st.session_state.get(f"_msec_{key}", True):
                continue
            val = icm.get(key)
            if not val:
                continue
            rendered_any = True
            st.markdown(
                f"<div class='memo-section-header'>{title}</div>",
                unsafe_allow_html=True,
            )
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        risk  = _escape_dollars(item.get("risk",     item.get("title", "")))
                        mitig = _escape_dollars(item.get("mitigant", item.get("mitigation", "")))
                        if mitig:
                            st.markdown(f"- **{risk}** — {mitig}")
                        else:
                            st.markdown(f"- {risk or _escape_dollars(str(item))}")
                    else:
                        st.markdown(f"- {_escape_dollars(str(item))}")
            else:
                st.markdown(_escape_dollars(str(val)))
        if rendered_any:
            return

    # ── Format B: memo.sections array structure ───────────────────────────
    memo_obj = data.get("memo", data)
    sections = memo_obj.get("sections") if isinstance(memo_obj, dict) else None
    _heading_to_key = {lbl.lower(): k for k, lbl in _MEMO_SECTION_LABELS}
    if isinstance(sections, list) and sections:
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            heading = sec.get("heading") or sec.get("title") or ""
            content = sec.get("content") or sec.get("body") or ""
            _sec_key = _heading_to_key.get(heading.strip().lower())
            if _sec_key and not st.session_state.get(f"_msec_{_sec_key}", True):
                continue
            if heading:
                st.markdown(
                    f"<div class='memo-section-header'>"
                    f"{_escape_dollars(heading)}</div>",
                    unsafe_allow_html=True,
                )
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        risk  = _escape_dollars(item.get("risk",     item.get("title", "")))
                        mitig = _escape_dollars(item.get("mitigant", item.get("mitigation", "")))
                        if mitig:
                            st.markdown(f"- **{risk}** — {mitig}")
                        else:
                            st.markdown(f"- {risk or _escape_dollars(str(item))}")
                    else:
                        st.markdown(f"- {_escape_dollars(str(item))}")
            elif isinstance(content, str) and content.strip():
                st.markdown(_escape_dollars(content))
        return

    # ── Fallback: unknown JSON shape, render raw ──────────────────────────
    st.markdown(_escape_dollars(memo_text))


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

    # ── Attempts 1 & 2 require valid JSON ────────────────────────────────
    data = None
    try:
        data = _json.loads(memo_text)
    except (_json.JSONDecodeError, TypeError):
        pass

    if data is not None:
        # ── Attempt 1: investment_committee_memo.key_risks_and_mitigants ──
        icm = data.get("investment_committee_memo")
        if isinstance(icm, dict):
            risks = icm.get("key_risks_and_mitigants")
            if isinstance(risks, list) and risks:
                return risks

        # ── Attempt 2: memo.sections — find section by heading ────────────
        memo_obj = data.get("memo", data)
        sections = memo_obj.get("sections") if isinstance(memo_obj, dict) else None
        if isinstance(sections, list):
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                heading = (sec.get("heading") or sec.get("title") or "")
                if "risk" not in heading.lower():
                    continue
                content = sec.get("content") or sec.get("body") or ""

                if isinstance(content, list):
                    return content

                if isinstance(content, str) and content.strip():
                    blocks = re.split(r"\n(?=\d+\.)", content.strip())
                    result = []
                    for block in blocks:
                        block = block.strip()
                        if not block:
                            continue
                        if "Mitigant:" in block:
                            parts         = block.split("Mitigant:", 1)
                            risk_text     = parts[0].strip().lstrip("0123456789. ")
                            mitigant_text = parts[1].strip()
                        else:
                            risk_text     = block.lstrip("0123456789. ").strip()
                            mitigant_text = ""
                        if risk_text:
                            result.append({"risk": risk_text, "mitigant": mitigant_text})
                    if result:
                        return result

    # ── Attempt 3: Plain text / markdown memo — regex extraction ─────────
    risk_section_match = re.search(
        r'(?:KEY RISKS|RISKS?\s*&\s*MITIGANTS?|5\.\s*KEY RISKS)(.*?)(?:\n\d+\.\s*[A-Z]|\n#{1,3}\s|\Z)',
        memo_text,
        re.DOTALL | re.IGNORECASE,
    )
    if risk_section_match:
        risk_text = risk_section_match.group(1).strip()
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
                entry = {"risk": title_line, "mitigant": mitigant}
                if description:
                    entry["description"] = description
                risks.append(entry)
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


def _make_json_bytes(result) -> bytes:
    """Serialise the full analysis result to UTF-8 JSON bytes."""
    import json
    from datetime import datetime
    ds = result.deal_score
    payload = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat(),
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


def _get_pipeline():
    """Initialise and cache the MeridianPipeline."""
    try:
        from config.settings import PipelineConfig
        from core.pipeline import MeridianPipeline
        config = PipelineConfig(verbose=False)
        return MeridianPipeline(config)
    except Exception as e:
        return None, str(e)


def _run_analysis(uploaded_file, profile: str, status):
    """Run each pipeline step individually so the status label updates in real time."""
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

        status.update(label="Parsing document…")
        _t = time.time()
        document = pipeline._parse_document(tmp_path)
        print(f"[TIMING] Parse:        {time.time() - _t:.1f}s")

        status.update(label="Extracting financial data…")
        _t = time.time()
        extracted_data = pipeline.extractor.extract(document)
        print(f"[TIMING] Extract:      {time.time() - _t:.1f}s")

        status.update(label="Generating investment memo…")
        _t = time.time()
        memo = (
            pipeline.memo_gen.generate(extracted_data)
            if pipeline.config.enable_memo_generation else ""
        )
        print(f"[TIMING] Memo:         {time.time() - _t:.1f}s")

        status.update(label="Analyzing risks…")
        _t = time.time()
        risks = (
            pipeline.risk_analyzer.analyze(extracted_data)
            if pipeline.config.enable_risk_analysis else []
        )
        print(f"[TIMING] Risks:        {time.time() - _t:.1f}s")

        status.update(label="Building comparable set…")
        _t = time.time()
        comps = (
            pipeline.comp_builder.build(extracted_data)
            if pipeline.config.enable_comp_builder else []
        )
        print(f"[TIMING] Comps:        {time.time() - _t:.1f}s")

        status.update(label="Scoring deal…")
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
        print(f"[TIMING] Scoring:      {time.time() - _t:.1f}s")

        status.update(label="Matching PE funds…")
        _t = time.time()
        fund_matches = MatchingEngine().match(extracted_data, top_n=5)
        st.session_state.fund_matches = fund_matches
        print(f"[TIMING] Fund match:   {time.time() - _t:.1f}s")

        print(f"[TIMING] TOTAL:        {time.time() - _t0:.1f}s")

        result = AnalysisResult(
            document=document,
            extracted_data=extracted_data,
            memo=memo,
            risks=risks,
            comps=comps,
            deal_score=deal_score,
            timing={},
        )

        st.session_state.result   = result
        st.session_state.document = document
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
    sel = st.session_state["_scoring_profile"]
    if sel in _PRESET_WEIGHTS:
        for dim, _, _, _ in _SLIDER_DIMS:
            st.session_state[f"_w_{dim}"] = _PRESET_WEIGHTS[sel][dim]


def _on_weight_slider():
    """Switch profile label to a matching preset or 'Custom' when sliders move."""
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
        "<div class='meridian-logo'>Meridian <span>AI</span></div>"
        "<div class='meridian-tagline'>PE Deal Intelligence</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Upload
    st.markdown("<div class='section-label'>Upload CIM</div>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Select a PDF or DOCX",
        type=["pdf", "docx", "doc"],
        help="Confidential Information Memorandum",
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

    analyze_btn = st.button(
        "Analyze CIM",
        type="primary",
        use_container_width=True,
        disabled=(uploaded_file is None),
    )

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
                f"{ds.recommendation}</p>",
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
            st.session_state["_json_bytes"]  = None
            st.session_state["_json_err"]    = None
            try:
                st.session_state["_xlsx_bytes"] = _make_xlsx_bytes(result)
            except Exception as _e:
                st.session_state["_xlsx_err"] = str(_e)
            try:
                st.session_state["_docx_bytes"] = _make_docx_bytes(result)
            except Exception as _e:
                st.session_state["_docx_err"] = str(_e)
            try:
                st.session_state["_json_bytes"] = _make_json_bytes(result)
            except Exception as _e:
                st.session_state["_json_err"] = str(_e)

        company_slug = co.get("company_name", "analysis").replace(" ", "_")

        if st.session_state["_xlsx_bytes"] is not None:
            st.download_button(
                label="Excel Report",
                data=st.session_state["_xlsx_bytes"],
                file_name=f"{company_slug}_analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.caption(f"Excel unavailable: {st.session_state['_xlsx_err']}")

        if st.session_state["_docx_bytes"] is not None:
            st.download_button(
                label="IC Memo (Word)",
                data=st.session_state["_docx_bytes"],
                file_name=f"{company_slug}_memo.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        else:
            st.caption(f"Word unavailable: {st.session_state['_docx_err']}")

        if st.session_state["_json_bytes"] is not None:
            st.download_button(
                label="Raw JSON",
                data=st.session_state["_json_bytes"],
                file_name=f"{company_slug}_raw.json",
                mime="application/json",
                use_container_width=True,
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

if analyze_btn and uploaded_file:
    st.session_state.result       = None
    st.session_state.document     = None
    st.session_state.messages     = []
    st.session_state.fund_matches = None

    start_time = time.time()

    with st.status("Analyzing CIM…", expanded=True) as _status:
        result, err = _run_analysis(uploaded_file, scoring_profile, _status)
        if err:
            _status.update(label="Analysis failed.", state="error")
        else:
            elapsed = time.time() - start_time
            _status.update(
                label=f"Analysis complete — {elapsed:.1f}s",
                state="complete",
            )

    if err:
        st.error(f"Analysis failed: {err}")
    else:
        st.rerun()

# ---------------------------------------------------------------------------
# Results tabs
# ---------------------------------------------------------------------------

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
    cols = st.columns(5)
    metrics = [
        ("Revenue (LTM)",   _fmt_num(rev.get("ltm"))),
        ("EBITDA (LTM)",    _fmt_num(ebitda.get("ltm"))),
        ("EBITDA Margin",   _fmt_pct(ebitda.get("margin_ltm"))),
        ("Revenue CAGR",    _fmt_pct(rev.get("cagr_3yr"))),
        ("Recurring Rev %", _fmt_pct(fin.get("recurring_revenue_pct"))),
    ]
    for col, (label, val) in zip(cols, metrics):
        col.metric(label, val)

    st.markdown("---")

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_memo, tab_fin, tab_risks, tab_comps, tab_score, tab_qa = st.tabs(
        ["Memo", "Financials", "Risks", "Comps", "Score", "Q&A"]
    )

    # ── Tab: Memo ─────────────────────────────────────────────────────────
    with tab_memo:
        if result.memo:
            _render_memo(result.memo)
        else:
            st.info("Memo generation was disabled or not yet run.")

    # ── Tab: Financials ───────────────────────────────────────────────────
    with tab_fin:
        customers = result.extracted_data.get("customers", {})

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                "<div class='section-label'>Income Statement</div>",
                unsafe_allow_html=True,
            )
            fin_rows = {
                "Revenue LTM":          _fmt_num(rev.get("ltm")),
                "Revenue (Prior Year)": _fmt_num(rev.get("prior_year")),
                "Revenue (2yr Ago)":    _fmt_num(rev.get("two_years_ago")),
                "CAGR (3yr)":           _fmt_pct(rev.get("cagr_3yr")),
                "EBITDA LTM":           _fmt_num(ebitda.get("ltm")),
                "Adjusted EBITDA":      _fmt_num(ebitda.get("adjusted_ebitda_ltm")),
                "EBITDA Margin":        _fmt_pct(ebitda.get("margin_ltm")),
                "Gross Margin":         _fmt_pct(fin.get("gross_margin")),
                "Net Income":           _fmt_num(fin.get("net_income")),
            }
            for label, val in fin_rows.items():
                cc1, cc2 = st.columns([2, 1])
                cc1.write(label)
                cc2.write(f"**{val}**")

        with c2:
            st.markdown(
                "<div class='section-label'>Balance Sheet & Revenue Mix</div>",
                unsafe_allow_html=True,
            )
            bs_rows = {
                "Total Debt":            _fmt_num(fin.get("debt")),
                "Cash & Equivalents":   _fmt_num(fin.get("cash")),
                "CapEx (Annual)":        _fmt_num(fin.get("capex")),
                "Recurring Revenue %":  _fmt_pct(fin.get("recurring_revenue_pct")),
                "Total Customers":       str(customers.get("total_customers", "N/A")),
                "Top Customer Conc.":   _fmt_pct(customers.get("top_customer_concentration")),
                "Top 10 Conc.":         _fmt_pct(customers.get("top_10_concentration")),
                "Customer Retention":   _fmt_pct(customers.get("customer_retention")),
                "Net Revenue Retention": _fmt_pct(customers.get("net_revenue_retention")),
            }
            for label, val in bs_rows.items():
                cc1, cc2 = st.columns([2, 1])
                cc1.write(label)
                cc2.write(f"**{val}**")

        # Revenue by segment
        segments = fin.get("revenue_by_segment", [])
        if segments:
            st.markdown("---")
            st.markdown(
                "<div class='section-label'>Revenue by Segment</div>",
                unsafe_allow_html=True,
            )
            import pandas as pd
            seg_df = pd.DataFrame(segments)
            if "pct_of_total" in seg_df.columns:
                seg_df["pct_of_total"] = seg_df["pct_of_total"].apply(
                    lambda x: _fmt_pct(x) if x else "N/A"
                )
            if "revenue" in seg_df.columns:
                seg_df["revenue"] = seg_df["revenue"].apply(_fmt_num)
            st.dataframe(seg_df, use_container_width=True, hide_index=True)

    # ── Tab: Risks ────────────────────────────────────────────────────────
    with tab_risks:
        memo_risks      = _extract_memo_risks(result.memo)
        heuristic_risks = [r for r in (result.risks or []) if r.source == "heuristic"]
        llm_risks       = [r for r in (result.risks or []) if r.source == "llm"]

        has_any = memo_risks or heuristic_risks or llm_risks

        if not has_any:
            st.info("No risks identified (or risk analysis was disabled).")

        # ── Section 1: Diligence Risks from Memo ─────────────────────────
        # Flat sibling if-block — not nested inside the has_any else branch
        if memo_risks:
            st.markdown("### Diligence Risks from Memo")
            st.caption("Qualitative risks identified through AI analysis of the CIM narrative.")
            for item in memo_risks:
                if isinstance(item, dict):
                    title       = (item.get("risk") or item.get("title") or "").strip()
                    description = (item.get("description") or "").strip()
                    mitigant    = (item.get("mitigant") or item.get("mitigation") or "").strip()
                    label       = item.get("risk", "")
                    if ": " in label and len(label) > 80:
                        label = label.split(": ")[0]
                    label = label[:80] or description[:80]
                    if not label:
                        continue
                    with st.expander(label, expanded=True):
                        if description:
                            st.markdown(_escape_dollars(description))
                        else:
                            st.markdown(f"**{_escape_dollars(title)}**")
                        if mitigant:
                            st.success(f"**Mitigant:** {_escape_dollars(mitigant)}")
                elif isinstance(item, str) and item.strip():
                    with st.expander(item.strip()[:80], expanded=True):
                        st.markdown(f"**{_escape_dollars(item.strip())}**")

        if llm_risks:
            if memo_risks:
                st.markdown("---")
            st.markdown("### Diligence Risks (AI Risk Analyzer)")
            st.caption("Risks identified through structured AI analysis.")
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

        # ── Section 2: Automated Flags ────────────────────────────────────
        # Also a flat sibling — always rendered independently
        if heuristic_risks:
            if memo_risks or llm_risks:
                st.markdown("---")
            st.markdown("### Automated Flags")
            st.caption("Rule-based checks triggered by extracted financial and operational metrics.")
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

        if has_any:
            st.caption("Meridian AI · Risk Assessment")

        # ── Sector-Specific Flags ─────────────────────────────────────────
        _industry = st.session_state.get("industry_profile", "General")
        _sector_flags = _SECTOR_FLAGS.get(_industry, [])
        if _sector_flags:
            st.markdown("---")
            st.markdown("### Sector-Specific Flags")
            st.caption(
                f"Domain considerations for {_industry} investments — "
                "shown independently of document extraction."
            )
            for _icon, _title, _body in _sector_flags:
                st.info(f"**{_icon} {_title}** — {_body}")

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
            st.dataframe(comp_df, use_container_width=True, hide_index=True)

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
                        st.markdown(f"**Thesis:** {m.fund.thesis_summary}")
                        st.caption(
                            f"{m.fund.headquarters}  ·  {m.fund.fund_size_category} Market  ·  "
                            f"${m.fund.check_size_min_mm}M–${m.fund.check_size_max_mm}M checks  ·  "
                            f"{m.fund.investment_style}"
                        )
                        for reason in m.reasons[:4]:
                            st.write(f"✓ {reason}")
                        for concern in m.concerns:
                            st.write(f"⚠ {concern}")
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
                        {ds.recommendation}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(ds.summary)
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

    # ── Tab: Q&A ──────────────────────────────────────────────────────────
    with tab_qa:
        st.markdown(
            "<div class='section-label'>Ask the CIM</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Ask any question about this deal. Answers are grounded in the "
            "parsed CIM document and extracted data."
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
    # ── Landing state ─────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='text-align:center;padding:7rem 2rem 4rem;max-width:520px;margin:0 auto'>
            <div style='font-size:3.2rem;font-weight:900;color:#e8e8e8;
                        letter-spacing:-1.5px;line-height:1;margin-bottom:0.5rem'>
                Meridian <span style='color:#E07A5F'>AI</span>
            </div>
            <p style='font-size:1rem;color:#8888aa;margin-bottom:0;line-height:1.7'>
                PE Deal Intelligence Engine<br>
                Upload a CIM to generate an IC memo, risk register,<br>
                deal score, and PE fund matches.
            </p>
            <p style='margin-top:3rem;color:#555577;font-size:0.82rem;
                      letter-spacing:0.05em;text-transform:uppercase'>
                Upload a CIM using the sidebar to begin
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div style='text-align:center;max-width:480px;margin:0 auto;padding:0 2rem 5rem'>
            <p style='color:#3d3d5c;font-size:0.72rem;font-weight:700;
                      letter-spacing:0.12em;text-transform:uppercase;margin-bottom:0.6rem'>
                Coming Soon
            </p>
            <p style='color:#3d3d5c;font-size:0.8rem;line-height:2;margin:0'>
                · PitchBook &amp; Capital IQ integration — auto-populate comp sets<br>
                · CRM sync — Affinity, DealCloud, Salesforce<br>
                · Data room ingestion — bulk analyze 100+ documents<br>
                · Custom IC memo templates per firm<br>
                · Deal pipeline dashboard with historical scoring<br>
                · Portfolio company benchmarking
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    "<div class='meridian-footer'>Meridian AI &nbsp;·&nbsp; PE Deal Intelligence</div>",
    unsafe_allow_html=True,
)
