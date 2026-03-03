"""
data_cleaning.py
────────────────
Normalize raw Monday.com item dicts into typed Python dicts.

Design goals
  • No silent data loss — every anomaly is counted and logged.
  • Return a data_quality_report alongside cleaned records.
  • Deterministic: same input → same output.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)


# ─── Sector normalisation ──────────────────────────────────────────────────

# Common aliases → canonical sector name
# Extended with sectors found in the actual company data
_SECTOR_ALIASES: dict[str, str] = {
    # Mining / Natural Resources
    "mining": "Mining",
    "mine": "Mining",
    "minerals": "Mining",
    # Energy
    "energy": "Energy",
    "energe": "Energy",
    "oil": "Energy",
    "gas": "Energy",
    "power": "Energy",
    "utilities": "Energy",
    # Technology
    "tech": "Technology",
    "technology": "Technology",
    "technologies": "Technology",
    "it": "Technology",
    "software": "Technology",
    # Finance
    "finance": "Finance",
    "financial": "Finance",
    "fintech": "Finance",
    "banking": "Finance",
    # Healthcare
    "healthcare": "Healthcare",
    "health care": "Healthcare",
    "health": "Healthcare",
    "pharma": "Healthcare",
    "pharmaceutical": "Healthcare",
    # Manufacturing
    "manufacturing": "Manufacturing",
    "manufacture": "Manufacturing",
    "industrial": "Manufacturing",
    # Agriculture / Environment
    "agriculture": "Agriculture",
    "agri": "Agriculture",
    "environment": "Environment",
    "environmental": "Environment",
    # Infrastructure / Construction
    "infrastructure": "Infrastructure",
    "construction": "Construction",
    "real estate": "Real Estate",
    "realestate": "Real Estate",
    # Geospatial / Surveying
    "geospatial": "Geospatial",
    "survey": "Geospatial",
    "surveying": "Geospatial",
    "gis": "Geospatial",
    "lidar": "Geospatial",
    "remote sensing": "Geospatial",
    # Government / Defence
    "government": "Government",
    "defence": "Government",
    "defense": "Government",
    "public sector": "Government",
    # Retail / Logistics
    "retail": "Retail",
    "logistics": "Logistics",
    "transport": "Logistics",
    "transportation": "Logistics",
    # Company-specific sectors (from actual Deal funnel + Work Order boards)
    "powerline": "Powerline",
    "power line": "Powerline",
    "railways": "Railways",
    "railway": "Railways",
    "rail": "Railways",
    "renewables": "Renewables",
    "renewable": "Renewables",
    "renewable energy": "Renewables",
    "solar": "Renewables",
    "wind": "Renewables",
    "aviation": "Aviation",
    "aerospace": "Aviation",
    "dsp": "DSP",
    "tender": "Tender",
    "security and surveillance": "Security & Surveillance",
    "security & surveillance": "Security & Surveillance",
    "surveillance": "Security & Surveillance",
    "security": "Security & Surveillance",
    # Misc
    "legal": "Legal",
    "education": "Education",
    "media": "Media",
    "telecom": "Telecommunications",
    "telecommunications": "Telecommunications",
    "sector/service": "Other",
    "others": "Other",
    "other": "Other",
    "misc": "Other",
    "none": "Other",
    "n/a": "Other",
}


def normalize_sector(raw: str | None) -> str | None:
    """Map messy sector strings to a canonical name; return None if blank."""
    if not raw:
        return None
    # Strip trailing/leading whitespace, remove "sector" suffix, lowercase
    cleaned = re.sub(r"\bsector\b", "", raw.strip().lower()).strip()
    return _SECTOR_ALIASES.get(cleaned, raw.strip().title())


# ─── Revenue normalisation ─────────────────────────────────────────────────

_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def normalize_revenue(raw: str | None) -> float | None:
    """Convert '$10,000', '10k', '1.5M', '10000' → float. None if unparseable."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text or text in {"n/a", "none", "-", ""}:
        return None

    # Remove currency symbols, spaces, commas
    text = re.sub(r"[$€£¥,\s]", "", text)

    # Handle multiplier suffix (k/m/b)
    match = re.match(r"^([+-]?\d+(?:\.\d+)?)([kmb])?$", text)
    if match:
        num = float(match.group(1))
        suffix = match.group(2)
        if suffix:
            num *= _MULTIPLIERS[suffix]
        return num

    # Last-ditch attempt
    try:
        return float(text)
    except ValueError:
        return None


# ─── Date parsing ──────────────────────────────────────────────────────────

def normalize_date(raw: str | None) -> str | None:
    """Parse any date string → ISO-8601 'YYYY-MM-DD'. None if blank/unparseable."""
    if not raw or str(raw).strip() in {"", "None", "null", "N/A", "-"}:
        return None
    try:
        dt = dateutil_parser.parse(str(raw), fuzzy=True)
        return dt.date().isoformat()
    except (ValueError, OverflowError):
        return None


# ─── Column value extraction ───────────────────────────────────────────────

def _col_text(column_values: list[dict], col_id: str) -> str | None:
    """Extract the 'text' field for a given column id."""
    for cv in column_values:
        if cv.get("id") == col_id:
            text = cv.get("text")
            return str(text).strip() if text not in (None, "") else None
    return None


def _col_value(column_values: list[dict], col_id: str) -> Any:
    """Extract parsed JSON 'value' for a given column id."""
    for cv in column_values:
        if cv.get("id") == col_id:
            raw_val = cv.get("value")
            if raw_val:
                try:
                    return json.loads(raw_val)
                except (json.JSONDecodeError, TypeError):
                    return raw_val
    return None


# ─── Data-quality report ───────────────────────────────────────────────────

@dataclass
class DataQualityReport:
    total_raw: int = 0
    usable: int = 0
    missing_sector: int = 0
    missing_revenue: int = 0
    missing_date: int = 0
    missing_stage: int = 0
    normalised_sectors: int = 0  # rows where sector was transformed
    revenue_parse_failures: int = 0
    date_parse_failures: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def usable_pct(self) -> float:
        if self.total_raw == 0:
            return 0.0
        return round(self.usable / self.total_raw * 100, 1)

    def to_dict(self) -> dict:
        return {
            "total_raw": self.total_raw,
            "usable": self.usable,
            "usable_pct": f"{self.usable_pct}%",
            "missing_sector": self.missing_sector,
            "missing_revenue": self.missing_revenue,
            "missing_date": self.missing_date,
            "missing_stage": self.missing_stage,
            "normalised_sectors": self.normalised_sectors,
            "revenue_parse_failures": self.revenue_parse_failures,
            "date_parse_failures": self.date_parse_failures,
            "issues": self.issues,
        }


# ─── Column ID maps — sourced live from Monday.com boards ──────────────────
#
# DEALS board  (id: 5026964857) — "Deal funnel Data"
#   Verified via GET /boards/columns on 2026-03-03
DEAL_COLUMN_MAP = {
    "name":         "name",                 # item name  (always present)
    "owner":        "color_mm1398d7",       # Owner code  (status)
    "client":       "dropdown_mm13jzv9",   # Client Code  (dropdown)
    "deal_status":  "color_mm13926x",      # Deal Status — Open / Closed Won / etc.
    "close_date":   "date_mm13zryd",       # Close Date (A)  (date)
    "probability":  "color_mm133ztk",      # Closure Probability — High/Medium/Low
    "value":        "numeric_mm13bawk",    # Masked Deal value  (numbers)
    "tentative_date": "date_mm13dhvm",    # Tentative Close Date  (date)
    "stage":        "color_mm13efd",       # Deal Stage  (status)
    "product":      "color_mm13x5y4",      # Product deal  (status)
    "sector":       "color_mm13ftj9",      # Sector/service  (status)  ← KEY
    "created_date": "date_mm13y1n9",       # Created Date  (date)
}

# WORK ORDERS board  (id: 5026964868) — "Work_Order_Tracker Data"
#   Verified via GET /boards/columns on 2026-03-03
WORK_ORDER_COLUMN_MAP = {
    "name":             "name",                # item name
    "customer":         "dropdown_mm134dj6",   # Customer Name Code
    "serial":           "dropdown_mm131ff8",   # Serial #
    "nature_of_work":   "color_mm1329q8",      # Nature of Work
    "status":           "color_mm13w00m",      # Execution Status  ← KEY
    "delivery_date":    "date_mm138hd1",       # Data Delivery Date
    "po_date":          "date_mm13de9z",       # Date of PO/LOI
    "sector":           "color_mm13f7n6",      # Sector  ← KEY
    "type_of_work":     "color_mm13806e",      # Type of Work
    "revenue_excl_gst": "numeric_mm139t2t",   # Amount in Rupees (Excl GST)
    "revenue_incl_gst": "numeric_mm13cbge",   # Amount in Rupees (Incl GST)
    "billed_excl_gst":  "numeric_mm13c1hn",   # Billed Value (Excl GST)
    "billed_incl_gst":  "numeric_mm13451w",   # Billed Value (Incl GST)
    "collected":        "numeric_mm1311cp",   # Collected Amount (Incl GST)
    "wo_status":        "color_mm1370ze",      # WO Status (billed)
    "billing_status":   "color_mm134se9",      # Billing Status
    "completion_date":  "date_mm138hd1",       # Data Delivery Date (proxy for completion)
}


# ─── Public cleaning functions ─────────────────────────────────────────────

def clean_deals(raw_items: list[dict]) -> tuple[list[dict], DataQualityReport]:
    """
    Convert raw Monday items → list of typed deal dicts.
    Returns (cleaned_deals, quality_report).
    """
    report = DataQualityReport(total_raw=len(raw_items))
    cleaned: list[dict] = []

    for item in raw_items:
        cvs = item.get("column_values", [])

        # ── Sector ──
        raw_sector = _col_text(cvs, DEAL_COLUMN_MAP["sector"])
        if raw_sector is None:
            report.missing_sector += 1
        canonical_sector = normalize_sector(raw_sector)
        if canonical_sector and raw_sector and canonical_sector != raw_sector.strip():
            report.normalised_sectors += 1

        # ── Revenue / Deal Value ──
        raw_value = _col_text(cvs, DEAL_COLUMN_MAP["value"])
        deal_value = normalize_revenue(raw_value)
        if raw_value and deal_value is None:
            report.revenue_parse_failures += 1
        if deal_value is None:
            report.missing_revenue += 1

        # ── Deal Status (Open / Closed Won / etc.) ──
        deal_status = _col_text(cvs, DEAL_COLUMN_MAP["deal_status"])

        # ── Deal Stage (granular funnel stage) ──
        stage = _col_text(cvs, DEAL_COLUMN_MAP["stage"])
        if stage is None and deal_status is None:
            report.missing_stage += 1

        # ── Closure Probability label ──
        probability_label = _col_text(cvs, DEAL_COLUMN_MAP["probability"])

        # ── Close Date — prefer actual close date, fall back to tentative ──
        raw_date = _col_text(cvs, DEAL_COLUMN_MAP["close_date"])
        if not raw_date:
            raw_date = _col_text(cvs, DEAL_COLUMN_MAP["tentative_date"])
        close_date = normalize_date(raw_date)
        if raw_date and close_date is None:
            report.date_parse_failures += 1
        if close_date is None:
            report.missing_date += 1

        # ── Owner (stored as status/text in this board) ──
        owner = _col_text(cvs, DEAL_COLUMN_MAP["owner"])

        # ── Product deal type (e.g. Lidar, Survey, DSP, etc.) ──
        product = _col_text(cvs, DEAL_COLUMN_MAP["product"])

        record = {
            "id": item.get("id"),
            "name": item.get("name", "").strip() or "Unnamed Deal",
            "sector": canonical_sector,
            "deal_value": deal_value,
            "deal_status": deal_status,   # Open / Closed Won / Lost
            "stage": stage,               # B. Sales Qualified Leads / etc.
            "probability_label": probability_label,  # High / Medium / Low
            "close_date": close_date,
            "owner": owner,
            "product": product,           # Product deal type
        }
        cleaned.append(record)

    # A deal is "usable" if it has sector + value
    report.usable = sum(
        1 for d in cleaned if d["sector"] is not None and d["deal_value"] is not None
    )

    if report.missing_sector:
        report.issues.append(f"{report.missing_sector} deal(s) missing sector info.")
    if report.missing_revenue:
        report.issues.append(f"{report.missing_revenue} deal(s) missing revenue/value.")
    if report.date_parse_failures:
        report.issues.append(f"{report.date_parse_failures} date(s) could not be parsed.")

    logger.info("Clean deals: %d/%d usable", report.usable, report.total_raw)
    return cleaned, report


def clean_work_orders(raw_items: list[dict]) -> tuple[list[dict], DataQualityReport]:
    """Convert raw Monday items → list of typed work-order dicts."""
    report = DataQualityReport(total_raw=len(raw_items))
    cleaned: list[dict] = []

    for item in raw_items:
        cvs = item.get("column_values", [])

        # Execution Status  (Completed / In Progress / Pending / etc.)
        exec_status = _col_text(cvs, WORK_ORDER_COLUMN_MAP["status"])
        wo_status   = _col_text(cvs, WORK_ORDER_COLUMN_MAP["wo_status"])   # WO Status (billed)
        status = exec_status or wo_status
        if status is None:
            report.missing_stage += 1

        sector = normalize_sector(_col_text(cvs, WORK_ORDER_COLUMN_MAP["sector"]))

        # Revenue — use Excl-GST as primary (cleaner for business metrics)
        raw_revenue = _col_text(cvs, WORK_ORDER_COLUMN_MAP["revenue_excl_gst"])
        revenue = normalize_revenue(raw_revenue)
        if raw_revenue and revenue is None:
            report.revenue_parse_failures += 1
        if revenue is None:
            report.missing_revenue += 1

        # Billed value
        billed = normalize_revenue(_col_text(cvs, WORK_ORDER_COLUMN_MAP["billed_excl_gst"]))
        collected = normalize_revenue(_col_text(cvs, WORK_ORDER_COLUMN_MAP["collected"]))

        raw_date = _col_text(cvs, WORK_ORDER_COLUMN_MAP["completion_date"])
        completion_date = normalize_date(raw_date)
        if raw_date and completion_date is None:
            report.date_parse_failures += 1

        po_date = normalize_date(_col_text(cvs, WORK_ORDER_COLUMN_MAP["po_date"]))
        nature  = _col_text(cvs, WORK_ORDER_COLUMN_MAP["nature_of_work"])
        type_of_work = _col_text(cvs, WORK_ORDER_COLUMN_MAP["type_of_work"])

        record = {
            "id": item.get("id"),
            "name": item.get("name", "").strip() or "Unnamed Work Order",
            "sector": sector,
            "status": status,               # Execution Status
            "nature_of_work": nature,
            "type_of_work": type_of_work,
            "revenue": revenue,             # Amount Excl GST
            "billed": billed,               # Billed Excl GST
            "collected": collected,         # Collected Incl GST
            "completion_date": completion_date,
            "po_date": po_date,
        }
        cleaned.append(record)

    report.usable = sum(1 for wo in cleaned if wo["status"] is not None)
    logger.info("Clean work orders: %d/%d usable", report.usable, report.total_raw)
    return cleaned, report
