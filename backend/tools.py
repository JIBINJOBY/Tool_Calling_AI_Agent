"""
tools.py
────────
Defines the five BI tools available to the Grok LLM agent.

Each tool has:
  • An OpenAI-compatible JSON schema (for tool_calling)
  • An executor function that performs the actual work
  • A trace-step emitter so every action is visible in the UI

Trace steps look like:
  {"step": "Calling get_deals()", "detail": "Fetching from Monday.com board 12345"}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from monday_api import fetch_deals, fetch_work_orders
from data_cleaning import clean_deals, clean_work_orders
from business_logic import (
    pipeline_by_sector,
    revenue_by_sector,
    revenue_forecast,
    sector_performance,
    conversion_rate,
)

logger = logging.getLogger(__name__)

# Shared trace collector — cleared per request by the agent
_trace: list[dict] = []


def _step(step: str, detail: str = "") -> None:
    entry = {"step": step, "detail": detail}
    _trace.append(entry)
    logger.info("[TRACE] %s — %s", step, detail)


def get_trace() -> list[dict]:
    return list(_trace)


def clear_trace() -> None:
    _trace.clear()


# ─── Tool schemas (OpenAI function-calling format) ─────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_deals",
            "description": (
                "Fetch all deals from the Monday.com Deals board, "
                "clean and normalise the data. Returns structured deal records "
                "and a data-quality report."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_orders",
            "description": (
                "Fetch all work orders from the Monday.com Work Orders board, "
                "clean and normalise the data."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_pipeline",
            "description": (
                "Calculate the open pipeline value for a given sector and/or "
                "quarter. Requires deals data (call get_deals first)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {
                        "type": "string",
                        "description": "Sector name to filter by, e.g. 'Energy', 'Technology'. Leave blank for all sectors.",
                    },
                    "quarter": {
                        "type": "string",
                        "description": "Quarter to filter by, e.g. 'Q1', 'Q2 2025', 'current'. Leave blank for all time.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sector_performance",
            "description": (
                "Compare pipeline and closed revenue across all sectors. "
                "Returns top and weakest sectors with full breakdown."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "quarter": {
                        "type": "string",
                        "description": "Quarter filter, e.g. 'Q1 2025', 'current'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "revenue_forecast",
            "description": (
                "Generate a probability-weighted revenue forecast for open deals. "
                "Uses stage-based win-probability estimates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Optional sector filter."},
                    "quarter": {"type": "string", "description": "Optional quarter filter."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conversion_rate",
            "description": (
                "Calculate deal win-rate and work-order completion rate. "
                "Requires both deals and work orders (call get_deals and get_work_orders first)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ─── Tool executors ────────────────────────────────────────────────────────

# In-memory cache per request (set by agent before execution)
_request_cache: dict[str, Any] = {}


def set_cache(key: str, value: Any) -> None:
    _request_cache[key] = value


def get_cache(key: str) -> Any:
    return _request_cache.get(key)


def clear_cache() -> None:
    _request_cache.clear()


def _exec_get_deals(**_kwargs) -> dict:
    _step("Calling get_deals()", "Fetching live deals from Monday.com GraphQL API")
    raw = fetch_deals()
    _step("Retrieved raw deals", f"{len(raw)} items fetched from Monday.com")
    deals, report = clean_deals(raw)
    _step(
        "Normalised deal fields",
        f"Sector aliases resolved: {report.normalised_sectors} | "
        f"Usable: {report.usable}/{report.total_raw} ({report.usable_pct}%)",
    )
    set_cache("deals", deals)
    set_cache("deals_report", report)
    return {
        "status": "ok",
        "deal_count": len(deals),
        "data_quality": report.to_dict(),
        "sample": deals[:3] if deals else [],
    }


def _exec_get_work_orders(**_kwargs) -> dict:
    _step("Calling get_work_orders()", "Fetching live work orders from Monday.com GraphQL API")
    raw = fetch_work_orders()
    _step("Retrieved raw work orders", f"{len(raw)} items fetched from Monday.com")
    wos, report = clean_work_orders(raw)
    _step("Normalised work order fields", f"Usable: {report.usable}/{report.total_raw}")
    set_cache("work_orders", wos)
    set_cache("work_orders_report", report)
    return {
        "status": "ok",
        "work_order_count": len(wos),
        "data_quality": report.to_dict(),
    }


def _exec_calculate_pipeline(sector: str = "", quarter: str = "", **_kwargs) -> dict:
    deals = get_cache("deals")
    if deals is None:
        _step("⚠️ Cache miss", "Deals not loaded — calling get_deals() automatically")
        _exec_get_deals()
        deals = get_cache("deals") or []

    _step(
        "calculate_pipeline()",
        f"sector={sector or 'ALL'} | quarter={quarter or 'all time'} | "
        f"deals available={len(deals)}",
    )
    result = pipeline_by_sector(deals, sector=sector or None, quarter=quarter or None)
    _step("Pipeline computed", f"Total pipeline: ₹{result['total_pipeline_value']:,.2f}")
    return result


def _exec_sector_performance(quarter: str = "", **_kwargs) -> dict:
    deals = get_cache("deals")
    if deals is None:
        _step("⚠️ Cache miss", "Deals not loaded — calling get_deals() automatically")
        _exec_get_deals()
        deals = get_cache("deals") or []

    _step("sector_performance()", f"Comparing sectors | quarter={quarter or 'all time'}")
    result = sector_performance(deals, quarter=quarter or None)
    _step(
        "Sector comparison done",
        f"Top: {result['top_sector']} | Weakest: {result['weakest_sector']}",
    )
    return result


def _exec_revenue_forecast(sector: str = "", quarter: str = "", **_kwargs) -> dict:
    deals = get_cache("deals")
    if deals is None:
        _step("⚠️ Cache miss", "Deals not loaded — calling get_deals() automatically")
        _exec_get_deals()
        deals = get_cache("deals") or []

    _step(
        "revenue_forecast()",
        f"sector={sector or 'ALL'} | quarter={quarter or 'all time'}",
    )
    result = revenue_forecast(deals, sector=sector or None, quarter=quarter or None)
    _step(
        "Forecast complete",
        f"Weighted forecast: ₹{result['weighted_forecast']:,.2f} | "
        f"Best case: ₹{result['best_case_forecast']:,.2f}",
    )
    return result


def _exec_conversion_rate(**_kwargs) -> dict:
    deals = get_cache("deals")
    wos = get_cache("work_orders")
    if deals is None:
        _step("⚠️ Cache miss", "Deals not loaded — calling get_deals() automatically")
        _exec_get_deals()
        deals = get_cache("deals") or []
    if wos is None:
        _step("⚠️ Cache miss", "Work orders not loaded — calling get_work_orders() automatically")
        _exec_get_work_orders()
        wos = get_cache("work_orders") or []

    _step("conversion_rate()", f"deals={len(deals)} | work_orders={len(wos)}")
    result = conversion_rate(deals, wos)
    _step("Conversion rate computed", f"Win rate: {result['win_rate_pct']}")
    return result


# ─── Dispatcher ─────────────────────────────────────────────────────────────

_EXECUTORS: dict[str, Callable] = {
    "get_deals": _exec_get_deals,
    "get_work_orders": _exec_get_work_orders,
    "calculate_pipeline": _exec_calculate_pipeline,
    "sector_performance": _exec_sector_performance,
    "revenue_forecast": _exec_revenue_forecast,
    "conversion_rate": _exec_conversion_rate,
}


def execute_tool(name: str, arguments: str | dict) -> str:
    """
    Execute a named tool with JSON-encoded or dict arguments.
    Returns JSON-encoded result string (as required by OpenAI tool calling protocol).
    """
    if isinstance(arguments, str):
        try:
            kwargs = json.loads(arguments) or {}
        except json.JSONDecodeError:
            kwargs = {}
    else:
        kwargs = arguments or {}

    executor = _EXECUTORS.get(name)
    if executor is None:
        result = {"error": f"Unknown tool: {name}"}
    else:
        try:
            result = executor(**kwargs)
        except Exception as exc:
            logger.exception("Tool %s raised an error", name)
            _step(f"❌ Error in {name}()", str(exc))
            result = {"error": str(exc)}

    return json.dumps(result, default=str)
