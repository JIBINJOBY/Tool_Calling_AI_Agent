"""
monday_api.py
─────────────
Low-level client for the Monday.com GraphQL v2 API.

All raw requests are made here.  Nothing is cached intentionally
(live API calls required).
"""

import os
import logging
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_TOKEN = os.getenv("MONDAY_API_TOKEN", "")
DEALS_BOARD_ID = os.getenv("MONDAY_DEALS_BOARD_ID", "")
WORK_ORDERS_BOARD_ID = os.getenv("MONDAY_WORK_ORDERS_BOARD_ID", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": MONDAY_API_TOKEN,
        "Content-Type": "application/json",
        "API-Version": "2023-10",
    }


def _run_query(query: str, variables: dict | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against Monday.com, raise on HTTP/API error."""
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(
        MONDAY_API_URL,
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Monday.com GraphQL errors: {data['errors']}")

    return data


# ─── Public fetch functions ────────────────────────────────────────────────

def fetch_deals(limit: int = 500) -> list[dict]:
    """
    Fetch all items from the Deals board.
    Returns a flat list of raw Monday item dicts with column_values.
    """
    board_id = int(DEALS_BOARD_ID)
    query = """
    query($boardId: [ID!], $limit: Int!) {
      boards(ids: $boardId) {
        name
        items_page(limit: $limit) {
          items {
            id
            name
            column_values {
              id
              text
              value
            }
          }
        }
      }
    }
    """
    data = _run_query(query, {"boardId": [str(board_id)], "limit": limit})
    boards = data.get("data", {}).get("boards", [])
    if not boards:
        return []
    items = boards[0].get("items_page", {}).get("items", [])
    logger.info("Fetched %d deals from Monday.com", len(items))
    return items


def fetch_work_orders(limit: int = 500) -> list[dict]:
    """
    Fetch all items from the Work Orders board.
    """
    board_id = int(WORK_ORDERS_BOARD_ID)
    query = """
    query($boardId: [ID!], $limit: Int!) {
      boards(ids: $boardId) {
        name
        items_page(limit: $limit) {
          items {
            id
            name
            column_values {
              id
              text
              value
            }
          }
        }
      }
    }
    """
    data = _run_query(query, {"boardId": [str(board_id)], "limit": limit})
    boards = data.get("data", {}).get("boards", [])
    if not boards:
        return []
    items = boards[0].get("items_page", {}).get("items", [])
    logger.info("Fetched %d work orders from Monday.com", len(items))
    return items


def fetch_board_columns(board_id: str) -> list[dict]:
    """Return column metadata (id, title, type) for a board."""
    query = """
    query($boardId: [ID!]) {
      boards(ids: $boardId) {
        columns {
          id
          title
          type
        }
      }
    }
    """
    data = _run_query(query, {"boardId": [str(board_id)]})
    boards = data.get("data", {}).get("boards", [])
    if not boards:
        return []
    return boards[0].get("columns", [])
