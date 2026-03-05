"""Main pipeline orchestrator.

This is the core engine: CIM document → full investment analysis.
Coordinates all modules in sequence.
"""

import os
import json
import re
import time
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field

from config.settings import PipelineConfig, ModelConfig
from config.scoring_weights import ScoringWeights, PROFILES
from parsers.pdf_parser import PDFParser, ParsedDocument
from parsers.docx_parser import DOCXParser
from core.extractor import CIMExtractor
from core.memo_generator import MemoGenerator
from core.risk_analyzer import RiskAnalyzer, RiskFlag
from core.comp_builder import CompBuilder, Comparable
from core.qa_engine import QAEngine
from scoring.deal_scorer import DealScorer, DealScore
from output.json_export import export_full_analysis
from core.insights import generate_insights
from core.deal_store import save_deal, get_peer_deals


# ---------------------------------------------------------------------------
# Narrative gap detection helpers
# ---------------------------------------------------------------------------

def _safe_float(v) -> Optional[float]:
    """Safely convert a value to float; return None on failure."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm_pct(v: Optional[float]) -> Optional[float]:
    """LLMs sometimes return 22.5 instead of 0.225. If |v| > 1.5 treat as raw %."""
    if v is None:
        return None
    return v / 100.0 if abs(v) > 1.5 else v


def _split_sentences(memo_text: str) -> List[Tuple[str, str]]:
    """Split memo markdown into (sentence, section_heading) pairs."""
    results: List[Tuple[str, str]] = []
    current_section = "Memo"
    for line in memo_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            current_section = line.lstrip("#").strip()
            continue
        for part in re.split(r"(?<=[.!?;])\s+", line):
            part = part.strip()
            if part:
                results.append((part, current_section))
    return results


def detect_narrative_gaps(
    extraction: Dict[str, Any],
    memo_data: str,
    doc_text: str = "",
) -> List[Dict[str, Any]]:
    """Programmatically compare memo narrative claims against extracted financials.

    No LLM call — pure regex + arithmetic.

    Returns a list of gap dicts:
        {claim, claim_source, extracted_value, status, gap, severity}
    where status ∈ {confirmed, discrepancy, unverifiable}
    and   severity ∈ {info, warning, critical}
    """
    gaps: List[Dict[str, Any]] = []

    if not memo_data:
        return gaps

    # ── Extract plain text from JSON memo if applicable ────────────────────
    memo_text = memo_data
    try:
        parsed = json.loads(memo_data)
        if isinstance(parsed, dict):
            parts = []
            for section in (parsed.get("sections") or []):
                heading = section.get("heading") or section.get("title") or ""
                content = section.get("content") or ""
                if heading:
                    parts.append(f"## {heading}")
                if isinstance(content, str):
                    parts.append(content)
            if parts:
                memo_text = "\n\n".join(parts)
    except (json.JSONDecodeError, TypeError):
        pass

    # ── Extract key metrics ────────────────────────────────────────────────
    fin       = extraction.get("financials", {})
    rev       = fin.get("revenue", {})
    ebitda    = fin.get("ebitda", {})
    customers = extraction.get("customers", {})

    rev_ltm          = _safe_float(rev.get("ltm"))
    ebitda_ltm       = _safe_float(ebitda.get("ltm")) or _safe_float(ebitda.get("adjusted_ebitda_ltm"))
    fcf_ltm          = _safe_float(fin.get("free_cash_flow") or fin.get("fcf"))
    ebitda_margin    = _norm_pct(_safe_float(ebitda.get("margin_ltm")))
    gross_margin     = _norm_pct(_safe_float(fin.get("gross_margin")))
    cagr_3yr         = _norm_pct(_safe_float(rev.get("cagr_3yr")))
    recurring_rev_pct = _norm_pct(_safe_float(fin.get("recurring_revenue_pct")))
    top_cust_conc    = _norm_pct(_safe_float(customers.get("top_customer_concentration")))
    retention        = _norm_pct(_safe_float(customers.get("customer_retention")))
    _raw_history     = rev.get("history") or {}
    # Normalise: list [{year, value}] → dict {str(year): value}
    if isinstance(_raw_history, list):
        rev_history = {str(item.get("year", i)): item.get("value")
                       for i, item in enumerate(_raw_history) if isinstance(item, dict)}
    else:
        rev_history = _raw_history

    # ── Compiled patterns ──────────────────────────────────────────────────
    # Sign group captures ASCII minus, en-dash (–), unicode minus (−)
    _dollar_pat    = re.compile(
        r'(?P<dsign>[-\u2013\u2212])?\s*\$\s*(?P<dnum>[\d,]+(?:\.\d+)?)'
        r'\s*(?P<dunit>million|MM|M|billion|B|bn|thousand|K)?',
        re.IGNORECASE,
    )
    _pct_pat       = re.compile(
        r'(?<![.\d])(?P<psign>[-\u2013\u2212])?\s*(?P<pnum>[\d]+(?:\.\d+)?)\s*%'
    )
    _rev_kw        = re.compile(r'\brevenue\b|\bsales\b|\btop[ -]line\b', re.IGNORECASE)
    _ebitda_kw     = re.compile(r'\bebitda\b', re.IGNORECASE)
    _margin_kw     = re.compile(r'\bmargin\b', re.IGNORECASE)
    _profit_kw     = re.compile(r'\bprofit\b', re.IGNORECASE)
    _gross_kw      = re.compile(r'\bgross\b', re.IGNORECASE)
    _cagr_kw       = re.compile(r'\bcagr\b|\bcompound(ed)? annual\b|\bgrowth rate\b', re.IGNORECASE)
    _recurring_kw  = re.compile(r'\brecurring\b|\bsubscription\b|\bARR\b', re.IGNORECASE)
    _retention_kw  = re.compile(r'\bretention\b|\bnet retention\b', re.IGNORECASE)
    _fcf_kw        = re.compile(r'\bfree cash flow\b|\bFCF\b|\bcash flow\b', re.IGNORECASE)

    # ── Local helpers ──────────────────────────────────────────────────────
    def _parse_dollar(s: str) -> Optional[float]:
        m = _dollar_pat.search(s)
        if not m:
            return None
        num = float(m.group("dnum").replace(",", ""))
        suffix = (m.group("dunit") or "").upper()
        mult = {"M": 1e6, "MM": 1e6, "MILLION": 1e6,
                "B": 1e9, "BN": 1e9, "BILLION": 1e9,
                "K": 1e3, "THOUSAND": 1e3}
        val = num * mult.get(suffix, 1.0)
        return -val if m.group("dsign") else val

    def _parse_pct(s: str) -> Optional[float]:
        m = _pct_pat.search(s)
        if not m:
            return None
        val = float(m.group("pnum")) / 100.0
        return -val if m.group("psign") else val

    def _parse_pct_near(s: str, anchor_pat) -> Optional[float]:
        """Pick the % value nearest to anchor_pat.

        Strategy: prefer the first match that appears AFTER the anchor keyword
        (handles 'gross margin 70% … recurring 85%' correctly).
        Falls back to nearest-overall if nothing follows the anchor.
        """
        anch = anchor_pat.search(s)
        if not anch:
            return _parse_pct(s)
        anchor_end = anch.end()
        # First preference: smallest-distance % that starts AFTER anchor ends
        after: list = [(m, m.start() - anchor_end)
                       for m in _pct_pat.finditer(s) if m.start() >= anchor_end]
        if after:
            best_m = min(after, key=lambda t: t[1])[0]
            val = float(best_m.group("pnum")) / 100.0
            return -val if best_m.group("psign") else val
        # Fallback: nearest by absolute distance
        best_val: Optional[float] = None
        best_dist = float("inf")
        for m in _pct_pat.finditer(s):
            dist = abs(m.start() - anch.start())
            if dist < best_dist:
                best_dist = dist
                val = float(m.group("pnum")) / 100.0
                best_val = -val if m.group("psign") else val
        return best_val

    def _parse_dollar_near(s: str, anchor_pat) -> Optional[float]:
        """Pick the $ value that appears first AFTER anchor_pat in s.

        Falls back to _parse_dollar (first match) if nothing follows.
        """
        anch = anchor_pat.search(s)
        if not anch:
            return _parse_dollar(s)
        anchor_end = anch.end()
        after: list = [(m, m.start() - anchor_end)
                       for m in _dollar_pat.finditer(s) if m.start() >= anchor_end]
        if after:
            best_m = min(after, key=lambda t: t[1])[0]
            num = float(best_m.group("dnum").replace(",", ""))
            suffix = (best_m.group("dunit") or "").upper()
            mult = {"M": 1e6, "MM": 1e6, "MILLION": 1e6,
                    "B": 1e9, "BN": 1e9, "BILLION": 1e9,
                    "K": 1e3, "THOUSAND": 1e3}
            val = num * mult.get(suffix, 1.0)
            return -val if best_m.group("dsign") else val
        return _parse_dollar(s)

    def _fmt_pct(v: Optional[float]) -> str:
        return f"{v:.1%}" if v is not None else "N/A"

    def _fmt_dollar(v: Optional[float]) -> str:
        if v is None:
            return "N/A"
        sign = "-" if v < 0 else ""
        av = abs(v)
        if av >= 1e9:
            return f"{sign}${av/1e9:.2f}B"
        if av >= 1e6:
            return f"{sign}${av/1e6:.1f}M"
        if av >= 1e3:
            return f"{sign}${av/1e3:.0f}K"
        return f"{sign}${av:,.0f}"

    def _add(claim, source, extracted_val, status, gap_desc, severity):
        gaps.append({
            "claim":           claim,
            "claim_source":    source,
            "extracted_value": extracted_val,
            "status":          status,
            "gap":             gap_desc,
            "severity":        severity,
        })

    # ── Per-sentence quantitative checks (elif = one metric per sentence) ───
    # Priority order (highest first):
    #   1. EBITDA margin  2. CAGR  3. Recurring  4. Gross margin
    #   5. Retention  6. FCF dollar  7. EBITDA dollar  8. Revenue dollar
    sentences = _split_sentences(memo_text)
    seen = {k: False for k in ("revenue", "ebitda", "ebitda_margin", "gross_margin",
                                "cagr", "recurring_pct", "retention", "fcf")}

    for sentence, source in sentences:
        s = sentence.strip()
        if len(s) < 15:
            continue

        # P1: EBITDA margin — "ebitda" AND "margin" in same sentence
        if _ebitda_kw.search(s) and _margin_kw.search(s):
            if not seen["ebitda_margin"]:
                pct = _parse_pct_near(s, _ebitda_kw)
                if pct is not None:
                    seen["ebitda_margin"] = True
                    if ebitda_margin is None:
                        _add(f"EBITDA margin {_fmt_pct(pct)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        diff = abs(pct - ebitda_margin)
                        if diff <= 0.03:
                            _add(f"EBITDA margin {_fmt_pct(pct)}", source,
                                 f"ebitda.margin_ltm = {_fmt_pct(ebitda_margin)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if diff <= 0.08 else "critical"
                            _add(f"EBITDA margin {_fmt_pct(pct)}", source,
                                 f"ebitda.margin_ltm = {_fmt_pct(ebitda_margin)}", "discrepancy",
                                 f"Memo claims {_fmt_pct(pct)} but extracted margin = {_fmt_pct(ebitda_margin)} (diff {diff:.1%})",
                                 sev)

        # P2: CAGR / growth rate
        elif _cagr_kw.search(s):
            if not seen["cagr"]:
                pct = _parse_pct_near(s, _cagr_kw)
                if pct is not None:
                    seen["cagr"] = True
                    if cagr_3yr is None:
                        _add(f"Revenue CAGR {_fmt_pct(pct)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        diff = abs(pct - cagr_3yr)
                        if diff <= 0.05:
                            _add(f"Revenue CAGR {_fmt_pct(pct)}", source,
                                 f"rev.cagr_3yr = {_fmt_pct(cagr_3yr)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if diff <= 0.15 else "critical"
                            _add(f"Revenue CAGR {_fmt_pct(pct)}", source,
                                 f"rev.cagr_3yr = {_fmt_pct(cagr_3yr)}", "discrepancy",
                                 f"Memo claims {_fmt_pct(pct)} CAGR but extracted 3yr CAGR = {_fmt_pct(cagr_3yr)} (diff {diff:.1%})",
                                 sev)

        # P3: Recurring revenue — BEFORE gross; not ebitda sentences
        elif _recurring_kw.search(s) and not _ebitda_kw.search(s):
            if not seen["recurring_pct"]:
                pct = _parse_pct_near(s, _recurring_kw)
                if pct is not None and 0.05 < pct <= 1.0:
                    seen["recurring_pct"] = True
                    if recurring_rev_pct is None:
                        _add(f"Recurring revenue {_fmt_pct(pct)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        diff = abs(pct - recurring_rev_pct)
                        if diff <= 0.05:
                            _add(f"Recurring revenue {_fmt_pct(pct)}", source,
                                 f"recurring_revenue_pct = {_fmt_pct(recurring_rev_pct)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if diff <= 0.15 else "critical"
                            _add(f"Recurring revenue {_fmt_pct(pct)}", source,
                                 f"recurring_revenue_pct = {_fmt_pct(recurring_rev_pct)}", "discrepancy",
                                 f"Memo claims {_fmt_pct(pct)} recurring but extracted = {_fmt_pct(recurring_rev_pct)} (diff {diff:.1%})",
                                 sev)

        # P4: Gross margin — "gross" AND ("margin" OR "profit"), not ebitda/recurring
        elif (_gross_kw.search(s)
              and (_margin_kw.search(s) or _profit_kw.search(s))
              and not _ebitda_kw.search(s)
              and not _recurring_kw.search(s)):
            if not seen["gross_margin"]:
                pct = _parse_pct_near(s, _gross_kw)
                if pct is not None and pct > 0.05:
                    seen["gross_margin"] = True
                    if gross_margin is None:
                        _add(f"Gross margin {_fmt_pct(pct)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        diff = abs(pct - gross_margin)
                        if diff <= 0.03:
                            _add(f"Gross margin {_fmt_pct(pct)}", source,
                                 f"fin.gross_margin = {_fmt_pct(gross_margin)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if diff <= 0.08 else "critical"
                            _add(f"Gross margin {_fmt_pct(pct)}", source,
                                 f"fin.gross_margin = {_fmt_pct(gross_margin)}", "discrepancy",
                                 f"Memo claims {_fmt_pct(pct)} but extracted = {_fmt_pct(gross_margin)} (diff {diff:.1%})",
                                 sev)

        # P5: Customer retention
        elif _retention_kw.search(s):
            if not seen["retention"]:
                pct = _parse_pct_near(s, _retention_kw)
                if pct is not None and 0.50 < pct <= 1.0:
                    seen["retention"] = True
                    if retention is None:
                        _add(f"Customer retention {_fmt_pct(pct)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        diff = abs(pct - retention)
                        if diff <= 0.05:
                            _add(f"Customer retention {_fmt_pct(pct)}", source,
                                 f"customers.customer_retention = {_fmt_pct(retention)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if diff <= 0.10 else "critical"
                            _add(f"Customer retention {_fmt_pct(pct)}", source,
                                 f"customers.customer_retention = {_fmt_pct(retention)}", "discrepancy",
                                 f"Memo claims {_fmt_pct(pct)} retention but extracted = {_fmt_pct(retention)} (diff {diff:.1%})",
                                 sev)

        # P6: Free cash flow dollar — BEFORE EBITDA dollar
        elif _fcf_kw.search(s):
            if not seen["fcf"]:
                dollar = _parse_dollar_near(s, _fcf_kw)
                if dollar is not None and dollar != 0:
                    seen["fcf"] = True
                    if fcf_ltm is None:
                        _add(f"Free cash flow {_fmt_dollar(dollar)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        delta = abs(dollar - fcf_ltm) / max(abs(fcf_ltm), 1)
                        if delta <= 0.15:
                            _add(f"Free cash flow {_fmt_dollar(dollar)}", source,
                                 f"fin.free_cash_flow = {_fmt_dollar(fcf_ltm)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if delta <= 0.30 else "critical"
                            _add(f"Free cash flow {_fmt_dollar(dollar)}", source,
                                 f"fin.free_cash_flow = {_fmt_dollar(fcf_ltm)}", "discrepancy",
                                 f"Memo claims {_fmt_dollar(dollar)} but extracted FCF = {_fmt_dollar(fcf_ltm)} (Δ {delta:.0%})",
                                 sev)

        # P7: EBITDA dollar — "ebitda" without "margin" AND without FCF anchors
        elif _ebitda_kw.search(s) and not _margin_kw.search(s) and not _fcf_kw.search(s):
            if not seen["ebitda"]:
                dollar = _parse_dollar_near(s, _ebitda_kw)
                if dollar is not None and dollar != 0:
                    seen["ebitda"] = True
                    if ebitda_ltm is None:
                        _add(f"EBITDA {_fmt_dollar(dollar)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        delta = abs(dollar - ebitda_ltm) / max(abs(ebitda_ltm), 1)
                        if delta <= 0.15:
                            _add(f"EBITDA {_fmt_dollar(dollar)}", source,
                                 f"ebitda.ltm = {_fmt_dollar(ebitda_ltm)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if delta <= 0.30 else "critical"
                            _add(f"EBITDA {_fmt_dollar(dollar)}", source,
                                 f"ebitda.ltm = {_fmt_dollar(ebitda_ltm)}", "discrepancy",
                                 f"Memo claims {_fmt_dollar(dollar)} but extracted = {_fmt_dollar(ebitda_ltm)} (Δ {delta:.0%})",
                                 sev)

        # P8: Revenue dollar — broadest, only if no ebitda/gross/FCF keywords
        elif (_rev_kw.search(s)
              and not _ebitda_kw.search(s)
              and not _gross_kw.search(s)
              and not _fcf_kw.search(s)):
            if not seen["revenue"]:
                dollar = _parse_dollar_near(s, _rev_kw)
                if dollar and dollar > 0:
                    seen["revenue"] = True
                    if rev_ltm is None:
                        _add(f"Revenue {_fmt_dollar(dollar)}", source,
                             "N/A (not extracted)", "unverifiable", None, "info")
                    else:
                        delta = abs(dollar - rev_ltm) / max(abs(rev_ltm), 1)
                        if delta <= 0.10:
                            _add(f"Revenue {_fmt_dollar(dollar)}", source,
                                 f"rev.ltm = {_fmt_dollar(rev_ltm)}", "confirmed", None, "info")
                        else:
                            sev = "warning" if delta <= 0.30 else "critical"
                            _add(f"Revenue {_fmt_dollar(dollar)}", source,
                                 f"rev.ltm = {_fmt_dollar(rev_ltm)}", "discrepancy",
                                 f"Memo claims {_fmt_dollar(dollar)} but extracted LTM = {_fmt_dollar(rev_ltm)} (Δ {delta:.0%})",
                                 sev)

    # ── Qualitative keyword checks ─────────────────────────────────────────
    memo_lower = memo_text.lower()

    # High recurring revenue
    if re.search(r'\bhigh recurring\b|\bstrongly recurring\b|\bhighly recurring\b', memo_lower):
        if recurring_rev_pct is not None:
            if recurring_rev_pct >= 0.70:
                _add("High recurring revenue", "Memo (qualitative)",
                     f"recurring_revenue_pct = {_fmt_pct(recurring_rev_pct)}", "confirmed", None, "info")
            else:
                _add("High recurring revenue", "Memo (qualitative)",
                     f"recurring_revenue_pct = {_fmt_pct(recurring_rev_pct)}", "discrepancy",
                     f"Memo claims high recurring but extracted = {_fmt_pct(recurring_rev_pct)} (< 70% threshold)",
                     "warning")
        else:
            _add("High recurring revenue", "Memo (qualitative)",
                 "N/A (not extracted)", "unverifiable", None, "info")

    # Strong / healthy margins
    if re.search(r'\bstrong margin|\bhigh margin|\bstrong ebitda\b|\bhealthy margin', memo_lower):
        if ebitda_margin is not None:
            if ebitda_margin >= 0.10:
                _add("Strong/healthy EBITDA margins", "Memo (qualitative)",
                     f"ebitda.margin_ltm = {_fmt_pct(ebitda_margin)}", "confirmed", None, "info")
            else:
                _add("Strong/healthy EBITDA margins", "Memo (qualitative)",
                     f"ebitda.margin_ltm = {_fmt_pct(ebitda_margin)}", "discrepancy",
                     f"Memo claims strong margins but extracted EBITDA margin = {_fmt_pct(ebitda_margin)} (< 10% threshold)",
                     "warning")
        else:
            _add("Strong/healthy EBITDA margins", "Memo (qualitative)",
                 "N/A (not extracted)", "unverifiable", None, "info")

    # Minimal customer concentration
    if re.search(
        r'\bminimal concentration\b|\bno single customer\b|\bdiversified customer\b'
        r'|\blow concentration\b|\bno customer concentration\b|\bwell[ -]diversified\b',
        memo_lower,
    ):
        if top_cust_conc is not None:
            if top_cust_conc <= 0.20:
                _add("Minimal/low customer concentration", "Memo (qualitative)",
                     f"top_customer_conc = {_fmt_pct(top_cust_conc)}", "confirmed", None, "info")
            else:
                _add("Minimal/low customer concentration", "Memo (qualitative)",
                     f"top_customer_conc = {_fmt_pct(top_cust_conc)}", "discrepancy",
                     f"Memo claims minimal concentration but top_customer_conc = {_fmt_pct(top_cust_conc)} (> 20%)",
                     "warning")
        else:
            _add("Minimal/low customer concentration", "Memo (qualitative)",
                 "N/A (not extracted)", "unverifiable", None, "info")

    # Consistent growth
    if re.search(
        r'\bconsistent growth\b|\bsteady growth\b|\bconsistent revenue growth\b'
        r'|\byear[ -]over[ -]year growth\b|\byoy growth\b',
        memo_lower,
    ):
        if rev_history:
            years  = sorted(rev_history.keys())
            values = [_safe_float(rev_history.get(y)) for y in years]
            values = [v for v in values if v is not None and v > 0]
            if len(values) >= 2:
                growths = [values[i] > values[i - 1] for i in range(1, len(values))]
                if all(growths):
                    _add("Consistent revenue growth", "Memo (qualitative)",
                         f"All {len(growths)} YoY periods positive", "confirmed", None, "info")
                else:
                    neg = growths.count(False)
                    _add("Consistent revenue growth", "Memo (qualitative)",
                         f"{neg} of {len(growths)} periods show revenue decline", "discrepancy",
                         f"Memo claims consistent growth but {neg}/{len(growths)} periods show decline",
                         "warning")
            else:
                _add("Consistent revenue growth", "Memo (qualitative)",
                     "N/A (insufficient history)", "unverifiable", None, "info")
        else:
            _add("Consistent revenue growth", "Memo (qualitative)",
                 "N/A (no history extracted)", "unverifiable", None, "info")

    # ── Never return empty — fallback from extraction data ─────────────────
    if not gaps:
        _note = (
            "No verifiable narrative claims detected in memo text. "
            "Showing extracted metrics for manual verification."
        )
        for label, val, is_pct in [
            ("Revenue (LTM)",        rev_ltm,           False),
            ("EBITDA (LTM)",         ebitda_ltm,        False),
            ("EBITDA Margin",        ebitda_margin,     True),
            ("Gross Margin",         gross_margin,      True),
            ("Revenue CAGR (3yr)",   cagr_3yr,          True),
            ("Recurring Revenue %",  recurring_rev_pct, True),
            ("Customer Retention %", retention,         True),
        ]:
            if val is not None:
                fmt_val = _fmt_pct(val) if is_pct else _fmt_dollar(val)
                _add(
                    f"{label} = {fmt_val}",
                    "Extracted data (no memo claim)",
                    fmt_val,
                    "unverifiable",
                    _note,
                    "info",
                )

    return gaps


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    """Complete analysis output from the pipeline."""
    document: ParsedDocument
    extracted_data: Dict[str, Any]
    memo: str
    risks: List[RiskFlag]
    comps: List[Comparable]
    deal_score: DealScore
    timing: Dict[str, float]
    narrative_gaps: List[Dict[str, Any]] = field(default_factory=list)
    insights: List[Dict[str, Any]] = field(default_factory=list)


class MeridianPipeline:
    """Main pipeline: CIM → full investment analysis.

    Usage:
        pipeline = MeridianPipeline()
        result = pipeline.analyze("path/to/cim.pdf")
        pipeline.export(result, "output/analysis.json")
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

        # Initialize components
        self.extractor = CIMExtractor(self.config.model)
        self.memo_gen = MemoGenerator(self.config.model)
        self.risk_analyzer = RiskAnalyzer(self.config.model)
        self.comp_builder = CompBuilder(self.config.model)
        self.qa_engine = QAEngine(self.config.model)
        self.deal_scorer = DealScorer()

    def analyze(
        self,
        filepath: str,
        scoring_profile: str = "balanced",
        with_citations: bool = False,
    ) -> AnalysisResult:
        """Run the full analysis pipeline on a CIM document.

        Args:
            filepath: Path to PDF or DOCX CIM file.
            scoring_profile: "balanced", "conservative", or "growth".
            with_citations: Enable additive citation fields in extraction output.

        Returns:
            AnalysisResult with all outputs.
        """
        timing = {}

        # Step 1: Parse document
        self._log("Step 1/6: Parsing document...")
        t0 = time.time()
        document = self._parse_document(filepath)
        timing["parse"] = time.time() - t0
        self._log(
            f"  Parsed {document.total_pages} pages, "
            f"{len(document.tables)} tables, "
            f"{len(document.raw_text):,} chars"
        )

        # Step 2: Extract structured data
        self._log("Step 2/6: Extracting structured data...")
        t0 = time.time()
        extracted_data = self.extractor.extract(
            document,
            with_citations=with_citations,
        )
        timing["extract"] = time.time() - t0
        company_name = extracted_data.get("company_overview", {}).get(
            "company_name", "Unknown"
        )
        self._log(f"  Extracted profile for: {company_name}")

        # Step 3: Generate memo
        memo = ""
        narrative_gaps: List[Dict[str, Any]] = []
        if self.config.enable_memo_generation:
            self._log("Step 3/6: Generating investment memo...")
            t0 = time.time()
            memo = self.memo_gen.generate(extracted_data)
            timing["memo"] = time.time() - t0
            self._log(f"  Memo: {len(memo):,} chars")
            if memo:
                narrative_gaps = detect_narrative_gaps(extracted_data, memo, document.raw_text)
                print(f"[narrative debug] gaps={len(narrative_gaps)}: {narrative_gaps[:2]}")

        # Step 4: Risk analysis
        risks = []
        if self.config.enable_risk_analysis:
            self._log("Step 4/6: Analyzing risks...")
            t0 = time.time()
            risks = self.risk_analyzer.analyze(extracted_data)
            timing["risk"] = time.time() - t0
            critical = len([r for r in risks if r.severity == "Critical"])
            high = len([r for r in risks if r.severity == "High"])
            self._log(
                f"  {len(risks)} risks identified "
                f"({critical} critical, {high} high)"
            )

        # Step 5: Comp builder
        comps = []
        if self.config.enable_comp_builder:
            self._log("Step 5/6: Building comparable sets...")
            t0 = time.time()
            comps = self.comp_builder.build(extracted_data)
            timing["comps"] = time.time() - t0
            self._log(f"  {len(comps)} comparables identified")

        # Step 6: Deal scoring
        deal_score = None
        if self.config.enable_deal_scoring:
            self._log("Step 6/6: Scoring deal...")
            t0 = time.time()
            weights = PROFILES.get(scoring_profile)
            self.deal_scorer = DealScorer(weights)
            deal_score = self.deal_scorer.score(extracted_data)
            timing["score"] = time.time() - t0
            self._log(
                f"  Score: {deal_score.total_score:.0%} "
                f"(Grade: {deal_score.grade}) — "
                f"{deal_score.recommendation}"
            )

        total_time = sum(timing.values())
        timing["total"] = total_time
        self._log(f"\nPipeline complete in {total_time:.1f}s")

        result = AnalysisResult(
            document=document,
            extracted_data=extracted_data,
            memo=memo,
            risks=risks,
            comps=comps,
            deal_score=deal_score,
            timing=timing,
            narrative_gaps=narrative_gaps,
        )

        # Persist + generate insights (best-effort — never block the pipeline)
        try:
            doc_name = os.path.basename(filepath)
            deal_id = save_deal(
                result,
                document_name=doc_name,
                pages=document.total_pages,
                duration=total_time,
            )
            industry = extracted_data.get("company_overview", {}).get("industry", "")
            peers = get_peer_deals(industry, exclude_id=deal_id)
            result.insights = generate_insights(extracted_data, peer_deals=peers or None)
            print(f"[insights debug] generated {len(result.insights)} insights")
            self._log(
                f"  Saved deal {deal_id[:8]}… | "
                f"{len(peers)} peer(s) | {len(result.insights)} insight(s)"
            )
        except Exception as exc:
            self._log(f"  [deal_store] skipped: {exc}")

        return result

    def ask(
        self,
        question: str,
        filepath: str,
        extracted_data: Optional[Dict] = None,
    ) -> str:
        """Ask a question about a CIM document.

        Args:
            question: Natural language question.
            filepath: Path to the CIM file.
            extracted_data: Optional pre-extracted data (saves re-extraction).
        """
        document = self._parse_document(filepath)
        return self.qa_engine.ask(question, document, extracted_data)

    def export(self, result: AnalysisResult, output_path: str) -> str:
        """Export analysis results to JSON."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        return export_full_analysis(
            extracted_data=result.extracted_data,
            memo=result.memo,
            risks=result.risks,
            comps=result.comps,
            deal_score=result.deal_score,
            output_path=output_path,
        )

    def _parse_document(self, filepath: str) -> ParsedDocument:
        """Route to the correct parser based on file extension."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".pdf", ".htm", ".html"):
            # PyMuPDF handles both PDF and HTML (SEC EDGAR filings) natively
            parser = PDFParser(
                max_pages=self.config.parser.max_pages,
                extract_tables=self.config.parser.table_extraction,
            )
        elif ext in (".docx", ".doc"):
            parser = DOCXParser()
        else:
            raise ValueError(f"Unsupported file type: {ext}. Use PDF, HTML, or DOCX.")
        return parser.parse(filepath)

    def _log(self, msg: str):
        if self.config.verbose:
            print(msg)
