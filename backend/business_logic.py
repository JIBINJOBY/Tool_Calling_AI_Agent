"""
business_logic.py
─────────────────
Pure business-metric functions.
All functions are stateless and operate on clean deal / work-order dicts.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ─── Quarter helpers ────────────────────────────────────────────────────────

def _parse_quarter(quarter_str: str | None) -> tuple[int, int] | None:
    """
    Accept: 'Q1', 'Q2 2025', '2025-Q3', 'current', None
    Returns (year, quarter_number) or None if 'current' / unparseable.
    """
    if not quarter_str or quarter_str.lower() in {"current", "this quarter", ""}:
        today = date.today()
        return today.year, (today.month - 1) // 3 + 1

    q = quarter_str.upper().replace(" ", "").replace("-", "")
    # Formats: Q12025, 2025Q1, Q1
    import re
    m = re.search(r"Q([1-4])", q)
    y = re.search(r"(20\d{2}|19\d{2})", q)
    if not m:
        return None
    qnum = int(m.group(1))
    year = int(y.group(1)) if y else date.today().year
    return year, qnum


def _in_quarter(iso_date: str | None, year: int, qnum: int) -> bool:
    if not iso_date:
        return False
    try:
        d = datetime.fromisoformat(iso_date).date()
        q = (d.month - 1) // 3 + 1
        return d.year == year and q == qnum
    except ValueError:
        return False


def _quarter_label(year: int, qnum: int) -> str:
    return f"Q{qnum} {year}"


# ─── 1. Pipeline by sector ──────────────────────────────────────────────────

def pipeline_by_sector(
    deals: list[dict],
    sector: str | None = None,
    quarter: str | None = None,
) -> dict[str, Any]:
    """
    Calculate pipeline value for a sector (optional) and quarter (optional).
    Returns a structured insights dict.
    """
    quarter_info = _parse_quarter(quarter)
    label = "all time"
    if quarter_info:
        yr, qn = quarter_info
        label = _quarter_label(yr, qn)

    # Filter to open/active deals (not Closed Won / Dead)
    # Use deal_status (Open / Closed Won / Lost) as primary filter
    # Fall back to stage text if deal_status missing
    pipeline_deals = [
        d for d in deals
        if str(d.get("deal_status", "") or "").lower() not in {"closed won", "closed lost", "lost", "won", "dead"}
        and str(d.get("stage", "") or "").lower() not in {"closed won", "closed lost", "f. closed won", "g. lost"}
    ]

    # Sector filter (fuzzy)
    if sector:
        sec_lower = sector.lower()
        pipeline_deals = [
            d for d in pipeline_deals
            if d.get("sector") and sec_lower in d["sector"].lower()
        ]

    # Quarter filter
    if quarter_info:
        yr, qn = quarter_info
        pipeline_deals = [d for d in pipeline_deals if _in_quarter(d.get("close_date"), yr, qn)]

    usable = [d for d in pipeline_deals if d.get("deal_value") is not None]
    total_value = sum(d["deal_value"] for d in usable)
    count = len(pipeline_deals)
    avg_size = total_value / len(usable) if usable else 0.0
    data_coverage = round(len(usable) / count * 100, 1) if count else 0.0

    return {
        "sector": sector or "All Sectors",
        "period": label,
        "total_pipeline_value": round(total_value, 2),
        "deal_count": count,
        "avg_deal_size": round(avg_size, 2),
        "data_coverage_pct": f"{data_coverage}%",
        "caveat": f"{count - len(usable)} deal(s) excluded due to missing revenue." if count != len(usable) else None,
    }


# ─── 2. Closed revenue / actual revenue ────────────────────────────────────

def revenue_by_sector(
    deals: list[dict],
    quarter: str | None = None,
) -> dict[str, Any]:
    """Aggregate closed-won revenue by sector for a given period."""
    quarter_info = _parse_quarter(quarter)
    label = "all time"
    if quarter_info:
        yr, qn = quarter_info
        label = _quarter_label(yr, qn)

    closed_deals = [
        d for d in deals
        if str(d.get("deal_status", "") or "").lower() in {"closed won", "won", "closed"}
        or str(d.get("stage", "") or "").lower() in {"f. closed won", "closed won", "won"}
    ]

    if quarter_info:
        yr, qn = quarter_info
        closed_deals = [d for d in closed_deals if _in_quarter(d.get("close_date"), yr, qn)]

    # Group by sector
    sector_map: dict[str, list[float]] = {}
    for d in closed_deals:
        sec = d.get("sector") or "Unknown"
        val = d.get("deal_value")
        if val is not None:
            sector_map.setdefault(sec, []).append(val)

    breakdown: list[dict] = []
    grand_total = 0.0
    for sec, vals in sector_map.items():
        s = sum(vals)
        grand_total += s
        breakdown.append({"sector": sec, "revenue": round(s, 2), "deals": len(vals)})

    breakdown.sort(key=lambda x: x["revenue"], reverse=True)

    # Derived %
    for row in breakdown:
        row["pct"] = f"{round(row['revenue'] / grand_total * 100, 1)}%" if grand_total else "0%"

    return {
        "period": label,
        "grand_total_revenue": round(grand_total, 2),
        "breakdown_by_sector": breakdown,
        "closed_deal_count": len(closed_deals),
    }


# ─── 3. Revenue forecast ────────────────────────────────────────────────────

# Stage → approximate win probability
# Stage names match the actual Monday.com board values
_STAGE_PROBABILITY: dict[str, float] = {
    # Actual stages from the Deal funnel Data board
    "a. lead": 0.05,
    "b. sales qualified leads": 0.15,
    "c. proposal": 0.35,
    "d. negotiation": 0.60,
    "e. verbal commitment": 0.80,
    "f. closed won": 1.00,
    "g. lost": 0.00,
    # Generic fallbacks
    "discovery": 0.10,
    "qualified": 0.20,
    "demo": 0.30,
    "proposal": 0.35,
    "negotiation": 0.60,
    "pending": 0.50,
    "open": 0.15,
    "active": 0.25,
    "in progress": 0.40,
    # Probability label fallbacks (High/Medium/Low from Closure Probability column)
    "high": 0.80,
    "medium": 0.50,
    "low": 0.20,
}


def revenue_forecast(
    deals: list[dict],
    sector: str | None = None,
    quarter: str | None = None,
) -> dict[str, Any]:
    """
    Probability-weighted revenue forecast for open deals.
    """
    quarter_info = _parse_quarter(quarter)
    label = "all time" if not quarter_info else _quarter_label(*quarter_info)

    open_deals = [
        d for d in deals
        if str(d.get("deal_status", "") or "").lower()
        not in {"closed won", "closed lost", "dead", "lost", "won"}
        and str(d.get("stage", "") or "").lower()
        not in {"f. closed won", "g. lost", "closed won", "lost"}
    ]

    if sector:
        sec_lower = sector.lower()
        open_deals = [
            d for d in open_deals
            if d.get("sector") and sec_lower in d["sector"].lower()
        ]

    if quarter_info:
        yr, qn = quarter_info
        open_deals = [d for d in open_deals if _in_quarter(d.get("close_date"), yr, qn)]

    best_case = sum(d["deal_value"] for d in open_deals if d.get("deal_value"))
    weighted = 0.0
    for d in open_deals:
        val = d.get("deal_value") or 0.0
        stage_key = str(d.get("stage", "") or "").lower()
        prob = _STAGE_PROBABILITY.get(stage_key)
        if prob is None:
            # Fall back to Closure Probability label (High/Medium/Low)
            prob_label = str(d.get("probability_label", "") or "").lower()
            prob = _STAGE_PROBABILITY.get(prob_label, 0.20)
        weighted += val * prob

    return {
        "sector": sector or "All Sectors",
        "period": label,
        "best_case_forecast": round(best_case, 2),
        "weighted_forecast": round(weighted, 2),
        "open_deal_count": len(open_deals),
        "note": "Weighted forecast uses stage-based win-probability estimates.",
    }


# ─── 4. Sector performance comparison ──────────────────────────────────────

def sector_performance(
    deals: list[dict],
    quarter: str | None = None,
) -> dict[str, Any]:
    """
    Compare pipeline & closed revenue across all sectors.
    Returns top/weakest sector + full breakdown.
    """
    quarter_info = _parse_quarter(quarter)
    label = "all time" if not quarter_info else _quarter_label(*quarter_info)

    filtered = deals
    if quarter_info:
        yr, qn = quarter_info
        filtered = [d for d in deals if _in_quarter(d.get("close_date"), yr, qn)]

    sectors: dict[str, dict] = {}
    for d in filtered:
        sec = d.get("sector") or "Unknown"
        val = d.get("deal_value") or 0.0
        deal_status = str(d.get("deal_status", "") or "").lower()
        stage = str(d.get("stage", "") or "").lower()
        entry = sectors.setdefault(sec, {"pipeline": 0.0, "closed": 0.0, "total_deals": 0})
        entry["total_deals"] += 1
        is_closed = (
            deal_status in {"closed won", "won", "closed"}
            or stage in {"f. closed won", "closed won", "won"}
        )
        if is_closed:
            entry["closed"] += val
        else:
            entry["pipeline"] += val

    rows = []
    grand = sum(e["pipeline"] + e["closed"] for e in sectors.values()) or 1
    for sec, e in sectors.items():
        total = e["pipeline"] + e["closed"]
        rows.append({
            "sector": sec,
            "pipeline_value": round(e["pipeline"], 2),
            "closed_revenue": round(e["closed"], 2),
            "total_deals": e["total_deals"],
            "share_pct": f"{round(total / grand * 100, 1)}%",
        })

    rows.sort(key=lambda x: x["pipeline_value"] + x["closed_revenue"], reverse=True)
    top = rows[0]["sector"] if rows else "N/A"
    weakest = rows[-1]["sector"] if len(rows) > 1 else "N/A"

    return {
        "period": label,
        "top_sector": top,
        "weakest_sector": weakest,
        "breakdown": rows,
        "total_sectors_found": len(rows),
    }


# ─── 5. Conversion rate ─────────────────────────────────────────────────────

def conversion_rate(
    deals: list[dict],
    work_orders: list[dict],
) -> dict[str, Any]:
    """Calculate deal-to-work-order conversion rate and win-rate."""
    total_deals = len(deals)
    closed_won = sum(
        1 for d in deals
        if str(d.get("deal_status", "") or "").lower() in {"closed won", "won", "closed"}
        or str(d.get("stage", "") or "").lower() in {"f. closed won", "closed won", "won"}
    )
    total_wos = len(work_orders)
    completed_wos = sum(
        1 for wo in work_orders
        if str(wo.get("status", "") or "").lower() in {"done", "complete", "completed"}
    )

    win_rate = round(closed_won / total_deals * 100, 1) if total_deals else 0.0
    wo_completion = round(completed_wos / total_wos * 100, 1) if total_wos else 0.0

    return {
        "total_deals": total_deals,
        "closed_won": closed_won,
        "win_rate_pct": f"{win_rate}%",
        "total_work_orders": total_wos,
        "completed_work_orders": completed_wos,
        "wo_completion_rate_pct": f"{wo_completion}%",
    }
