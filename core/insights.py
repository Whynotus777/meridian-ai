"""Deterministic insights engine — no LLM calls.

Generates investment insights from extracted financial data using
rule-based logic. Six rules implemented.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _sf(v) -> Optional[float]:
    """Safe float cast."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_pct(v: Optional[float]) -> str:
    return f"{v:.1%}" if v is not None else "N/A"


def _fmt_dollar(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e9:  return f"{sign}${av/1e9:.2f}B"
    if av >= 1e6:  return f"{sign}${av/1e6:.1f}M"
    if av >= 1e3:  return f"{sign}${av/1e3:.0f}K"
    return f"{sign}${av:,.0f}"


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------

def _rule_growth_deceleration(rev: Dict) -> Optional[Dict]:
    """RULE 1 — Revenue Growth Deceleration."""
    _raw = rev.get("history") or {}
    # Normalise: list [{year, value}] → dict {str(year): value}
    if isinstance(_raw, list):
        history = {str(item.get("year", i)): item.get("value")
                   for i, item in enumerate(_raw) if isinstance(item, dict)}
    else:
        history = _raw
    years   = sorted(history.keys())
    values  = [_sf(history.get(y)) for y in years]
    values  = [v for v in values if v is not None and v > 0]

    if len(values) < 3:
        return None

    rates = [(values[i] - values[i - 1]) / max(values[i - 1], 1)
             for i in range(1, len(values))]

    # Count consecutive drops in growth rate
    max_consecutive = 0
    current_run = 0
    for i in range(1, len(rates)):
        if rates[i] < rates[i - 1]:
            current_run += 1
            max_consecutive = max(max_consecutive, current_run)
        else:
            current_run = 0

    if max_consecutive < 2:
        return None

    highest = max(rates)
    lowest  = min(rates)
    n       = len(values) - 1
    return {
        "type":     "growth_deceleration",
        "title":    "Revenue Growth Decelerating",
        "detail":   (
            f"YoY growth has declined from {highest:.1%} to {lowest:.1%} over the past "
            f"{n} fiscal years, suggesting a transition from hypergrowth to a more mature phase."
        ),
        "severity": "warning",
        "metrics":  {"highest_growth": highest, "lowest_growth": lowest, "periods": n},
    }


def _rule_recurring_revenue(fin: Dict) -> Optional[Dict]:
    """RULE 2 — Recurring Revenue Quality."""
    pct = _sf(fin.get("recurring_revenue_pct"))
    if pct is None:
        return None

    if pct > 0.80:
        label   = "Strong"
        sev     = "positive"
        comment = "placing the business in the top tier of subscription models"
    elif pct >= 0.50:
        label   = "Mixed"
        sev     = "info"
        comment = "indicating mixed revenue predictability"
    else:
        label   = "Transactional"
        sev     = "warning"
        comment = "suggesting a predominantly transactional business"

    return {
        "type":     "recurring_revenue_quality",
        "title":    f"Recurring Revenue: {label}",
        "detail":   (
            f"Recurring revenue represents {pct:.1%} of total revenue, {comment}."
        ),
        "severity": sev,
        "metrics":  {"recurring_revenue_pct": pct},
    }


def _rule_customer_concentration(customers: Dict) -> Optional[Dict]:
    """RULE 3 — Customer Concentration Risk."""
    conc = _sf(customers.get("top_customer_concentration"))
    if conc is None or conc <= 0:
        return None

    if conc <= 0.20:
        return None   # Not flagged unless elevated

    return {
        "type":     "customer_concentration",
        "title":    "Elevated Customer Concentration",
        "detail":   (
            f"The largest customer represents {conc:.1%} of revenue, "
            "creating potential revenue volatility if that relationship changes."
        ),
        "severity": "warning",
        "metrics":  {"top_customer_concentration": conc},
    }


def _rule_ebitda_fcf_divergence(fin: Dict) -> Optional[Dict]:
    """RULE 4 — EBITDA vs FCF Divergence."""
    ebitda_val = _sf(fin.get("ebitda", {}).get("ltm")) if isinstance(fin.get("ebitda"), dict) else _sf(fin.get("ebitda_ltm"))
    fcf        = _sf(fin.get("free_cash_flow"))

    if ebitda_val is None or fcf is None:
        return None

    # Only flag if signs diverge
    if (ebitda_val >= 0) == (fcf >= 0):
        return None

    if ebitda_val > 0 and fcf < 0:
        note = "significant non-cash expenses or working capital absorption"
    else:
        note = "non-cash charges masking underlying cash generation"

    return {
        "type":     "ebitda_fcf_divergence",
        "title":    "EBITDA / Free Cash Flow Divergence",
        "detail":   (
            f"EBITDA is {'positive' if ebitda_val >= 0 else 'negative'} at {_fmt_dollar(ebitda_val)} "
            f"while free cash flow is {'positive' if fcf >= 0 else 'negative'} at {_fmt_dollar(fcf)}, "
            f"suggesting {note}."
        ),
        "severity": "info",
        "metrics":  {"ebitda_ltm": ebitda_val, "free_cash_flow": fcf},
    }


def _rule_capital_intensity(fin: Dict, rev: Dict) -> Optional[Dict]:
    """RULE 5 — Capital Intensity."""
    capex   = _sf(fin.get("capex"))
    rev_ltm = _sf(rev.get("ltm"))

    if capex is None or rev_ltm is None or rev_ltm <= 0:
        return None

    ratio = abs(capex) / rev_ltm

    if ratio > 0.10:
        label = "High"
        sev   = "warning"
    elif ratio >= 0.05:
        label = "Moderate"
        sev   = "info"
    else:
        label = "Low"
        sev   = "positive"

    return {
        "type":     "capital_intensity",
        "title":    f"Capital Intensity: {label}",
        "detail":   f"Capital expenditures represent {ratio:.1%} of revenue.",
        "severity": sev,
        "metrics":  {"capex_to_revenue": ratio, "capex": capex, "revenue_ltm": rev_ltm},
    }


def _rule_peer_percentile(extraction: Dict, peer_deals: List[Dict]) -> List[Dict]:
    """RULE 6 — Peer Percentile Benchmarks (requires ≥2 peers)."""
    if not peer_deals or len(peer_deals) < 2:
        return []

    fin      = extraction.get("financials", {})
    rev      = fin.get("revenue", {}) if isinstance(fin.get("revenue"), dict) else {}
    ebitda_d = fin.get("ebitda", {}) if isinstance(fin.get("ebitda"), dict) else {}
    co       = extraction.get("company_overview", {})
    sector   = co.get("industry", "this sector")

    checks = [
        ("ebitda_margin",        _sf(ebitda_d.get("margin_ltm")),            "EBITDA Margin",        "ebitda_margin"),
        ("revenue_cagr",         _sf(rev.get("cagr_3yr")),                    "Revenue CAGR",         "revenue_cagr"),
        ("recurring_revenue_pct",_sf(fin.get("recurring_revenue_pct")),       "Recurring Revenue %",  "recurring_revenue_pct"),
    ]

    insights = []
    for key, value, label, peer_field in checks:
        if value is None:
            continue

        peer_values = [
            p.get(peer_field)
            for p in peer_deals
            if p.get(peer_field) is not None
        ]
        peer_values = [_sf(v) for v in peer_values]
        peer_values = [v for v in peer_values if v is not None]

        if len(peer_values) < 2:
            continue

        n_below     = sum(1 for v in peer_values if v < value)
        percentile  = n_below / len(peer_values)
        median      = sorted(peer_values)[len(peer_values) // 2]

        if percentile >= 0.75:
            sev    = "positive"
            vs_med = f"above the median of {_fmt_pct(median)}"
        elif percentile <= 0.25:
            sev    = "warning"
            vs_med = f"below the median of {_fmt_pct(median)}"
        else:
            sev    = "info"
            vs_med = f"near the median of {_fmt_pct(median)}"

        insights.append({
            "type":     "peer_percentile",
            "title":    f"Peer Benchmark: {label}",
            "detail":   (
                f"{label} of {_fmt_pct(value)} ranks at the {percentile:.0%} percentile "
                f"among {sector} deals analyzed — {vs_med} across {len(peer_values)} peers."
            ),
            "severity": sev,
            "metrics":  {
                "value":      value,
                "percentile": percentile,
                "median":     median,
                "n_peers":    len(peer_values),
            },
        })

    return insights


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_insights(
    extraction: Dict[str, Any],
    peer_deals: Optional[List[Dict]] = None,
) -> List[Dict[str, Any]]:
    """Generate deterministic investment insights from extracted data.

    Args:
        extraction: Full extracted_data dict from the pipeline.
        peer_deals: Optional list of peer deal metric dicts from deal_store.

    Returns:
        List of insight dicts with keys:
            type, title, detail, severity, metrics
    """
    fin      = extraction.get("financials", {})
    rev      = fin.get("revenue", {}) if isinstance(fin.get("revenue"), dict) else {}
    customers = extraction.get("customers", {})

    results: List[Dict[str, Any]] = []

    # Rules 1-5: single-document checks
    for fn, args in [
        (_rule_growth_deceleration, (rev,)),
        (_rule_recurring_revenue,   (fin,)),
        (_rule_customer_concentration, (customers,)),
        (_rule_ebitda_fcf_divergence,  (fin,)),
        (_rule_capital_intensity,      (fin, rev)),
    ]:
        try:
            insight = fn(*args)
            if insight:
                results.append(insight)
        except Exception:
            pass

    # Rule 6: peer percentile (only if peers available)
    if peer_deals:
        try:
            results.extend(_rule_peer_percentile(extraction, peer_deals))
        except Exception:
            pass

    return results
