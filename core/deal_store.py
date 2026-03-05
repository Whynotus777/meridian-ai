"""SQLite deal persistence — stores analysis results for cross-deal benchmarking.

DB location: ~/.meridian/deals.db
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.pipeline import AnalysisResult

_DB_DIR  = os.path.expanduser("~/.meridian")
_DB_PATH = os.path.join(_DB_DIR, "deals.db")

_DDL = """
CREATE TABLE IF NOT EXISTS deal_summaries (
    deal_id             TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    industry            TEXT,
    sub_industry        TEXT,
    headquarters        TEXT,
    business_model      TEXT,
    created_at          TEXT NOT NULL,

    revenue_ltm         REAL,
    ebitda_ltm          REAL,
    ebitda_margin       REAL,
    gross_margin        REAL,
    revenue_cagr        REAL,
    recurring_revenue_pct REAL,
    customer_concentration REAL,
    net_income          REAL,
    free_cash_flow      REAL,
    capex               REAL,
    debt                REAL,
    cash                REAL,
    employee_count      INTEGER,

    deal_score          REAL,
    deal_grade          TEXT,
    recommendation      TEXT,

    currency            TEXT DEFAULT 'USD',
    document_name       TEXT,
    document_pages      INTEGER,
    analysis_duration   REAL,

    full_result_json    TEXT,

    UNIQUE(company_name, created_at)
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    return conn


def _sf(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return None if str(v).lower() in ("not_provided", "none", "n/a") else f
    except (TypeError, ValueError):
        return None


def _si(v) -> Optional[int]:
    f = _sf(v)
    return int(f) if f is not None else None


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def save_deal(
    result: "AnalysisResult",
    document_name: str = "",
    pages: int = 0,
    duration: float = 0.0,
) -> str:
    """Persist an AnalysisResult to the deal database.

    Returns the generated deal_id (UUID4 string).
    """
    ed  = result.extracted_data
    co  = ed.get("company_overview", {})
    fin = ed.get("financials", {})
    rev = fin.get("revenue", {}) if isinstance(fin.get("revenue"), dict) else {}
    ebitda = fin.get("ebitda", {}) if isinstance(fin.get("ebitda"), dict) else {}
    customers = ed.get("customers", {})
    ds  = result.deal_score

    deal_id = str(uuid.uuid4())
    now     = datetime.now(timezone.utc).isoformat()

    # Serialise full result (best-effort)
    try:
        import dataclasses
        def _default(obj):
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            return str(obj)
        full_json = json.dumps(
            {"extracted_data": ed, "memo": result.memo, "narrative_gaps": getattr(result, "narrative_gaps", [])},
            default=_default,
        )
    except Exception:
        full_json = "{}"

    row = {
        "deal_id":               deal_id,
        "company_name":          co.get("company_name", "Unknown"),
        "industry":              co.get("industry"),
        "sub_industry":          co.get("sub_industry"),
        "headquarters":          co.get("headquarters"),
        "business_model":        co.get("business_model"),
        "created_at":            now,
        "revenue_ltm":           _sf(rev.get("ltm")),
        "ebitda_ltm":            _sf(ebitda.get("ltm")) or _sf(ebitda.get("adjusted_ebitda_ltm")),
        "ebitda_margin":         _sf(ebitda.get("margin_ltm")),
        "gross_margin":          _sf(fin.get("gross_margin")),
        "revenue_cagr":          _sf(rev.get("cagr_3yr")),
        "recurring_revenue_pct": _sf(fin.get("recurring_revenue_pct")),
        "customer_concentration":_sf(customers.get("top_customer_concentration")),
        "net_income":            _sf(fin.get("net_income")),
        "free_cash_flow":        _sf(fin.get("free_cash_flow")),
        "capex":                 _sf(fin.get("capex")),
        "debt":                  _sf(fin.get("debt")),
        "cash":                  _sf(fin.get("cash")),
        "employee_count":        _si(co.get("employee_count") or co.get("employees")),
        "deal_score":            _sf(ds.total_score) if ds else None,
        "deal_grade":            ds.grade if ds else None,
        "recommendation":        ds.recommendation if ds else None,
        "currency":              fin.get("currency") or "USD",
        "document_name":         document_name,
        "document_pages":        pages,
        "analysis_duration":     duration,
        "full_result_json":      full_json,
    }

    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    with _connect() as conn:
        conn.execute(
            f"INSERT OR IGNORE INTO deal_summaries ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )
    return deal_id


def list_deals(sector: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Return summary dicts for stored deals, optionally filtered by sector."""
    with _connect() as conn:
        if sector:
            rows = conn.execute(
                "SELECT * FROM deal_summaries WHERE industry = ? ORDER BY created_at DESC LIMIT ?",
                (sector, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM deal_summaries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_deal(deal_id: str) -> Optional[Dict]:
    """Return a single deal by ID."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM deal_summaries WHERE deal_id = ?", (deal_id,)
        ).fetchone()
    return dict(row) if row else None


def get_peer_deals(industry: str, exclude_id: Optional[str] = None) -> List[Dict]:
    """Return deals in the same industry, excluding a specific deal_id."""
    if not industry or industry.lower() in ("n/a", "not_provided", "unknown"):
        return []
    with _connect() as conn:
        if exclude_id:
            rows = conn.execute(
                "SELECT * FROM deal_summaries WHERE industry = ? AND deal_id != ? ORDER BY created_at DESC",
                (industry, exclude_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM deal_summaries WHERE industry = ? ORDER BY created_at DESC",
                (industry,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_all_metrics() -> List[Dict]:
    """Return all deals as metric dicts (no full_result_json)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT deal_id, company_name, industry, revenue_ltm, ebitda_ltm, "
            "ebitda_margin, gross_margin, revenue_cagr, recurring_revenue_pct, "
            "customer_concentration, deal_score, deal_grade, currency "
            "FROM deal_summaries ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_percentile(
    value: float,
    field_name: str,
    industry: Optional[str] = None,
) -> Optional[float]:
    """Compute percentile of value against stored deals for a given metric field.

    Returns 0.0–1.0 or None if insufficient data.
    """
    with _connect() as conn:
        if industry:
            rows = conn.execute(
                f"SELECT {field_name} FROM deal_summaries "
                f"WHERE industry = ? AND {field_name} IS NOT NULL",
                (industry,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {field_name} FROM deal_summaries WHERE {field_name} IS NOT NULL"
            ).fetchall()

    values = [r[0] for r in rows if r[0] is not None]
    if len(values) < 2:
        return None

    n_below = sum(1 for v in values if v < value)
    return n_below / len(values)
