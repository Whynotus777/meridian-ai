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
    page_title="Meridian AI — PE Deal Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
    /* Brand colours */
    :root {
        --navy:   #1F4E79;
        --blue:   #2E75B6;
        --green:  #70AD47;
        --amber:  #FFC000;
        --red:    #C00000;
    }

    /* Top bar override */
    header[data-testid="stHeader"] { background-color: var(--navy); }

    /* Sidebar */
    section[data-testid="stSidebar"] { background-color: #F0F4F9; }
    section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 0.75rem 1rem;
    }

    /* Severity badge helpers (used inline) */
    .badge-critical { background:#C00000; color:white; padding:2px 8px; border-radius:4px; font-size:0.8rem; }
    .badge-high     { background:#FF0000; color:white; padding:2px 8px; border-radius:4px; font-size:0.8rem; }
    .badge-medium   { background:#FFC000; color:black; padding:2px 8px; border-radius:4px; font-size:0.8rem; }
    .badge-low      { background:#70AD47; color:white; padding:2px 8px; border-radius:4px; font-size:0.8rem; }

    /* Score bar */
    .score-bar-bg { background:#E2E8F0; border-radius:4px; height:12px; margin-top:2px; }
    .score-bar-fg { height:12px; border-radius:4px; }

    /* Chat bubbles */
    .chat-user     { background:#EEF2FF; border-radius:12px; padding:0.6rem 1rem; margin:4px 0; }
    .chat-assistant{ background:#F0FDF4; border-radius:12px; padding:0.6rem 1rem; margin:4px 0; }
</style>
""",
    unsafe_allow_html=True,
)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_num(val) -> str:
    if val is None or val == "not_provided":
        return "N/A"
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:,.0f}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_pct(val) -> str:
    if val is None or val == "not_provided":
        return "N/A"
    try:
        return f"{float(val):.1%}"
    except (ValueError, TypeError):
        return str(val)


def _score_colour(score: float) -> str:
    if score >= 0.75:
        return "#70AD47"
    if score >= 0.50:
        return "#FFC000"
    return "#C00000"


def _severity_colour(severity: str) -> str:
    return {
        "Critical": "#C00000",
        "High":     "#FF4444",
        "Medium":   "#FFC000",
        "Low":      "#70AD47",
    }.get(severity, "#888888")


def _get_pipeline():
    """Initialise and cache the MeridianPipeline."""
    try:
        from config.settings import PipelineConfig
        from core.pipeline import MeridianPipeline
        config = PipelineConfig(verbose=False)
        return MeridianPipeline(config)
    except Exception as e:
        return None, str(e)


def _run_analysis(uploaded_file, profile: str, progress_bar, status_text):
    """Run the full pipeline on an uploaded file."""
    pipeline = st.session_state.pipeline

    # Save to temp file
    ext = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        # We hook into the pipeline's log to drive progress
        steps = [
            ("Parsing document...",          0.10),
            ("Extracting structured data...", 0.30),
            ("Generating investment memo...", 0.50),
            ("Analyzing risks...",            0.65),
            ("Building comparable set...",    0.80),
            ("Scoring deal...",               0.90),
            ("Matching PE funds...",          0.95),
            ("Finalizing...",                 1.00),
        ]

        def _fake_progress(step_idx):
            msg, pct = steps[min(step_idx, len(steps) - 1)]
            status_text.text(f"  {msg}")
            progress_bar.progress(pct)

        _fake_progress(0)
        result = pipeline.analyze(tmp_path, scoring_profile=profile)

        _fake_progress(6)
        from scoring.fund_matcher import MatchingEngine
        engine = MatchingEngine()
        fund_matches = engine.match(result.extracted_data, top_n=5)
        st.session_state.fund_matches = fund_matches

        _fake_progress(7)
        st.session_state.result   = result
        st.session_state.document = result.document

        return result, None

    except Exception as exc:
        return None, str(exc)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image(
        "https://via.placeholder.com/200x50/1F4E79/FFFFFF?text=MERIDIAN+AI",
        use_container_width=True,
    )
    st.markdown("---")
    st.subheader("Upload CIM")

    uploaded_file = st.file_uploader(
        "Select a PDF or DOCX",
        type=["pdf", "docx", "doc"],
        help="Confidential Information Memorandum",
        label_visibility="collapsed",
    )

    scoring_profile = st.selectbox(
        "Scoring Profile",
        options=["balanced", "conservative", "growth"],
        format_func=lambda x: x.title(),
        help="Adjusts dimension weights for the deal score.",
    )

    analyze_btn = st.button(
        "Analyze CIM",
        type="primary",
        use_container_width=True,
        disabled=(uploaded_file is None),
    )

    st.markdown("---")

    if st.session_state.result:
        result = st.session_state.result
        co     = result.extracted_data.get("company_overview", {})
        ds     = result.deal_score

        st.subheader(co.get("company_name", "Unknown"))
        st.caption(co.get("industry", "") + " / " + co.get("sub_industry", ""))

        if ds:
            grade_colour = _score_colour(ds.total_score)
            st.markdown(
                f"**Deal Score:** "
                f"<span style='color:{grade_colour};font-size:1.2rem;font-weight:bold'>"
                f"{ds.total_score:.0%} ({ds.grade})</span>",
                unsafe_allow_html=True,
            )
            st.caption(ds.recommendation)

        if result.risks:
            critical = sum(1 for r in result.risks if r.severity == "Critical")
            high     = sum(1 for r in result.risks if r.severity == "High")
            if critical:
                st.error(f"{critical} Critical risk(s)")
            if high:
                st.warning(f"{high} High risk(s)")

        # Export buttons
        st.markdown("---")
        st.subheader("Export")

        col_x, col_w = st.columns(2)
        with col_x:
            if st.button("Excel", use_container_width=True):
                try:
                    from output.excel_export import export_excel
                    import tempfile as tf
                    with tf.NamedTemporaryFile(
                        delete=False, suffix=".xlsx"
                    ) as tmp:
                        path = export_excel(result, tmp.name)
                    with open(path, "rb") as f:
                        st.download_button(
                            "Download .xlsx",
                            f.read(),
                            file_name=f"{co.get('company_name', 'analysis')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                except Exception as e:
                    st.error(f"Export failed: {e}")

        with col_w:
            if st.button("Word", use_container_width=True):
                try:
                    from output.memo_formatter import export_memo_docx
                    import tempfile as tf
                    with tf.NamedTemporaryFile(
                        delete=False, suffix=".docx"
                    ) as tmp:
                        path = export_memo_docx(
                            result.memo,
                            result.extracted_data,
                            result.risks,
                            result.comps,
                            tmp.name,
                        )
                    with open(path, "rb") as f:
                        st.download_button(
                            "Download .docx",
                            f.read(),
                            file_name=f"{co.get('company_name', 'memo')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                except Exception as e:
                    st.error(f"Export failed: {e}")


# ---------------------------------------------------------------------------
# Main area — pipeline initialisation
# ---------------------------------------------------------------------------

# Initialise pipeline once
if st.session_state.pipeline is None:
    with st.spinner("Loading Meridian AI pipeline…"):
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

    progress_bar  = st.progress(0.0)
    status_text   = st.empty()
    start_time    = time.time()

    result, err = _run_analysis(
        uploaded_file, scoring_profile, progress_bar, status_text
    )

    progress_bar.empty()
    status_text.empty()

    if err:
        st.error(f"Analysis failed: {err}")
    else:
        elapsed = time.time() - start_time
        st.success(f"Analysis complete in {elapsed:.1f}s")
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

    # Page title
    st.markdown(
        f"<h2 style='color:#1F4E79;margin-bottom:0'>{co.get('company_name','Unknown Company')}</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{co.get('industry','N/A')} · {co.get('sub_industry','N/A')} · "
        f"{co.get('headquarters','N/A')} · {co.get('business_model','N/A')}"
    )

    # Key metrics strip
    cols = st.columns(5)
    metrics = [
        ("Revenue (LTM)",    _fmt_num(rev.get("ltm"))),
        ("EBITDA (LTM)",     _fmt_num(ebitda.get("ltm"))),
        ("EBITDA Margin",    _fmt_pct(ebitda.get("margin_ltm"))),
        ("Revenue CAGR",     _fmt_pct(rev.get("cagr_3yr"))),
        ("Recurring Rev %",  _fmt_pct(fin.get("recurring_revenue_pct"))),
    ]
    for col, (label, val) in zip(cols, metrics):
        col.metric(label, val)

    st.markdown("---")

    # Tabs
    tab_memo, tab_fin, tab_risks, tab_comps, tab_score, tab_qa = st.tabs(
        ["Memo", "Financials", "Risks", "Comps", "Score", "Q&A"]
    )

    # -----------------------------------------------------------------------
    # Tab: Memo
    # -----------------------------------------------------------------------
    with tab_memo:
        if result.memo:
            st.markdown(result.memo)
        else:
            st.info("Memo generation was disabled or not yet run.")

    # -----------------------------------------------------------------------
    # Tab: Financials
    # -----------------------------------------------------------------------
    with tab_fin:
        customers = result.extracted_data.get("customers", {})

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Income Statement")
            fin_rows = {
                "Revenue LTM":           _fmt_num(rev.get("ltm")),
                "Revenue (Prior Year)":  _fmt_num(rev.get("prior_year")),
                "Revenue (2yr Ago)":     _fmt_num(rev.get("two_years_ago")),
                "CAGR (3yr)":            _fmt_pct(rev.get("cagr_3yr")),
                "EBITDA LTM":            _fmt_num(ebitda.get("ltm")),
                "Adjusted EBITDA":       _fmt_num(ebitda.get("adjusted_ebitda_ltm")),
                "EBITDA Margin":         _fmt_pct(ebitda.get("margin_ltm")),
                "Gross Margin":          _fmt_pct(fin.get("gross_margin")),
                "Net Income":            _fmt_num(fin.get("net_income")),
            }
            for label, val in fin_rows.items():
                cc1, cc2 = st.columns([2, 1])
                cc1.write(label)
                cc2.write(f"**{val}**")

        with c2:
            st.subheader("Balance Sheet & Mix")
            bs_rows = {
                "Total Debt":              _fmt_num(fin.get("debt")),
                "Cash & Equivalents":      _fmt_num(fin.get("cash")),
                "CapEx (Annual)":          _fmt_num(fin.get("capex")),
                "Recurring Revenue %":     _fmt_pct(fin.get("recurring_revenue_pct")),
                "Total Customers":         str(customers.get("total_customers", "N/A")),
                "Top Cust. Conc.":         _fmt_pct(customers.get("top_customer_concentration")),
                "Top 10 Conc.":            _fmt_pct(customers.get("top_10_concentration")),
                "Customer Retention":      _fmt_pct(customers.get("customer_retention")),
                "Net Revenue Retention":   _fmt_pct(customers.get("net_revenue_retention")),
            }
            for label, val in bs_rows.items():
                cc1, cc2 = st.columns([2, 1])
                cc1.write(label)
                cc2.write(f"**{val}**")

        # Revenue by segment
        segments = fin.get("revenue_by_segment", [])
        if segments:
            st.subheader("Revenue by Segment")
            import pandas as pd
            seg_df = pd.DataFrame(segments)
            if "pct_of_total" in seg_df.columns:
                seg_df["pct_of_total"] = seg_df["pct_of_total"].apply(
                    lambda x: _fmt_pct(x) if x else "N/A"
                )
            if "revenue" in seg_df.columns:
                seg_df["revenue"] = seg_df["revenue"].apply(_fmt_num)
            st.dataframe(seg_df, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # Tab: Risks
    # -----------------------------------------------------------------------
    with tab_risks:
        risks = result.risks or []
        if not risks:
            st.info("No risks identified (or risk analysis was disabled).")
        else:
            critical = [r for r in risks if r.severity == "Critical"]
            high     = [r for r in risks if r.severity == "High"]
            medium   = [r for r in risks if r.severity == "Medium"]
            low      = [r for r in risks if r.severity == "Low"]

            # Summary counts
            rc, rh, rm, rl = st.columns(4)
            rc.metric("Critical", len(critical), delta_color="inverse")
            rh.metric("High",     len(high))
            rm.metric("Medium",   len(medium))
            rl.metric("Low",      len(low))
            st.markdown("---")

            for risk in risks:
                sev_colour = _severity_colour(risk.severity)
                with st.expander(
                    f"[{risk.severity}] {risk.category} — {risk.title}",
                    expanded=(risk.severity in ("Critical", "High")),
                ):
                    st.markdown(
                        f"<span style='background:{sev_colour};color:white;"
                        f"padding:2px 10px;border-radius:4px;font-weight:bold'>"
                        f"{risk.severity}</span> &nbsp; **{risk.category}**",
                        unsafe_allow_html=True,
                    )
                    st.write(risk.description)
                    if risk.mitigant:
                        st.success(f"**Mitigant:** {risk.mitigant}")
                    if risk.diligence_question:
                        st.info(f"**Diligence:** {risk.diligence_question}")
                    st.caption(f"Source: {risk.source}")

    # -----------------------------------------------------------------------
    # Tab: Comps
    # -----------------------------------------------------------------------
    with tab_comps:
        comps = result.comps or []
        if not comps:
            st.info("No comparable companies identified.")
        else:
            import pandas as pd
            rows = []
            for c in comps:
                rows.append({
                    "Company / Deal": c.name,
                    "Type":           c.type.replace("_", " ").title(),
                    "EV/Revenue":     f"{c.ev_revenue:.1f}x" if c.ev_revenue else "N/A",
                    "EV/EBITDA":      f"{c.ev_ebitda:.1f}x" if c.ev_ebitda else "N/A",
                    "Confidence":     f"{c.confidence:.0%}",
                    "Rationale":      c.rationale,
                    "Key Differences":c.key_differences,
                })
            comp_df = pd.DataFrame(rows)
            st.dataframe(comp_df, use_container_width=True, hide_index=True)

        # Fund matches section
        if st.session_state.fund_matches:
            st.subheader("PE Fund Matches")
            matches = st.session_state.fund_matches
            for i, m in enumerate(matches, 1):
                bar_width = int(m.total_score * 100)
                bar_colour = _score_colour(m.total_score)
                with st.expander(
                    f"#{i} {m.fund.name} — {m.total_score:.0%}",
                    expanded=(i == 1),
                ):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"**Thesis:** {m.fund.thesis_summary}")
                        st.caption(
                            f"{m.fund.headquarters} · {m.fund.fund_size_category} Market · "
                            f"${m.fund.check_size_min_mm}M–${m.fund.check_size_max_mm}M checks · "
                            f"{m.fund.investment_style}"
                        )
                        for reason in m.reasons[:4]:
                            st.write(f"✅ {reason}")
                        for concern in m.concerns:
                            st.write(f"⚠️ {concern}")
                    with c2:
                        sub_scores = {
                            "Industry":   m.industry_score,
                            "Size":       m.size_score,
                            "Geography":  m.geography_score,
                            "Strategic":  m.strategic_score,
                        }
                        for label, s in sub_scores.items():
                            st.markdown(
                                f"<small>{label}</small><br>"
                                f"<div class='score-bar-bg'>"
                                f"<div class='score-bar-fg' style='width:{s*100:.0f}%;"
                                f"background:{_score_colour(s)}'></div></div>"
                                f"<small>{s:.0%}</small>",
                                unsafe_allow_html=True,
                            )

    # -----------------------------------------------------------------------
    # Tab: Score
    # -----------------------------------------------------------------------
    with tab_score:
        ds = result.deal_score
        if not ds:
            st.info("Deal scoring was disabled or not yet run.")
        else:
            # Overall grade banner
            grade_col = _score_colour(ds.total_score)
            st.markdown(
                f"""
                <div style='background:{grade_col};color:white;border-radius:12px;
                            padding:1.5rem 2rem;text-align:center;margin-bottom:1rem'>
                    <div style='font-size:3rem;font-weight:900'>{ds.grade}</div>
                    <div style='font-size:1.4rem'>{ds.total_score:.0%} Overall Score</div>
                    <div style='font-size:1rem;opacity:0.9'>{ds.recommendation}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write(ds.summary)
            st.markdown("---")

            # Dimension breakdown
            st.subheader("Dimension Breakdown")
            for dim in ds.dimensions:
                score_colour = _score_colour(dim.score)
                st.markdown(f"**{dim.dimension}**  —  {dim.score:.0%} (weight {dim.weight:.0%})")
                st.progress(dim.score)
                c1, c2 = st.columns([3, 1])
                c1.caption(dim.rationale)
                c2.caption(f"Data: {dim.data_quality.replace('_', ' ').title()}")
                st.markdown("")

    # -----------------------------------------------------------------------
    # Tab: Q&A
    # -----------------------------------------------------------------------
    with tab_qa:
        st.subheader("Ask the CIM")
        st.caption(
            "Ask any question about this deal. Answers are grounded in the "
            "parsed CIM document and extracted data."
        )

        # Render conversation history
        for msg in st.session_state.messages:
            role = msg["role"]
            with st.chat_message(role):
                st.write(msg["content"])

        # Chat input
        user_question = st.chat_input("Ask a question about this deal…")
        if user_question:
            # Append and display user message
            st.session_state.messages.append(
                {"role": "user", "content": user_question}
            )
            with st.chat_message("user"):
                st.write(user_question)

            # Get answer
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
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer}
                )

else:
    # Landing state — no file uploaded yet
    st.markdown(
        """
        <div style='text-align:center;padding:4rem 2rem'>
            <h1 style='color:#1F4E79;font-size:2.5rem'>Meridian AI</h1>
            <p style='font-size:1.2rem;color:#555;margin-bottom:2rem'>
                PE Deal Intelligence Engine — CIM to IC Memo in minutes
            </p>
            <div style='display:flex;justify-content:center;gap:2rem;flex-wrap:wrap'>
                <div style='background:#EEF2FF;border-radius:12px;padding:1.5rem;width:180px'>
                    <div style='font-size:2rem'>📄</div>
                    <strong>Upload CIM</strong>
                    <p style='font-size:0.85rem;color:#666'>PDF or DOCX</p>
                </div>
                <div style='background:#EEF2FF;border-radius:12px;padding:1.5rem;width:180px'>
                    <div style='font-size:2rem'>🤖</div>
                    <strong>AI Extraction</strong>
                    <p style='font-size:0.85rem;color:#666'>Structured data from text</p>
                </div>
                <div style='background:#EEF2FF;border-radius:12px;padding:1.5rem;width:180px'>
                    <div style='font-size:2rem'>📊</div>
                    <strong>Full Analysis</strong>
                    <p style='font-size:0.85rem;color:#666'>Memo · Score · Risks · Comps</p>
                </div>
                <div style='background:#EEF2FF;border-radius:12px;padding:1.5rem;width:180px'>
                    <div style='font-size:2rem'>💬</div>
                    <strong>Q&A Engine</strong>
                    <p style='font-size:0.85rem;color:#666'>Ask anything about the deal</p>
                </div>
            </div>
            <p style='margin-top:3rem;color:#888;font-size:0.9rem'>
                Upload a CIM using the sidebar to get started.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
