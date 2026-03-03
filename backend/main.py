"""
main.py
────────
FastAPI application entry-point for the Monday BI Agent backend.

Endpoints
─────────
GET  /health          → liveness check
GET  /boards/columns  → list board columns (for debugging column ID mapping)
POST /chat            → main agent endpoint (accepts query, returns answer + trace)
POST /tools/test      → call a single tool directly (useful for testing)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monday_bi")

# ─── App ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Monday BI Agent backend starting up…")
    yield
    logger.info("👋 Backend shutting down.")


app = FastAPI(
    title="Monday BI Agent API",
    version="1.0.0",
    description="Tool-calling AI agent backed by xAI Grok + Monday.com GraphQL",
    lifespan=lifespan,
)

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    history: list[dict] = Field(
        default_factory=list,
        description="Prior conversation turns [{role, content}, ...] for multi-turn support"
    )


class TraceStep(BaseModel):
    step: str
    detail: str = ""


class ChatResponse(BaseModel):
    answer: str
    trace: list[TraceStep]
    model: str
    iterations: int
    query: str


class ToolTestRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: dict = Field(default_factory=dict, description="Tool arguments")


# ─── Routes ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    """Liveness probe — returns OK if the server is running."""
    return {"status": "ok", "service": "monday-bi-agent"}


@app.get("/boards/columns", tags=["Debug"])
async def list_columns():
    """
    Fetch column metadata from both Monday boards.
    Useful for verifying column IDs during setup.
    """
    try:
        from monday_api import (
            fetch_board_columns,
            DEALS_BOARD_ID,
            WORK_ORDERS_BOARD_ID,
        )

        result = {}
        if DEALS_BOARD_ID:
            result["deals_board"] = fetch_board_columns(DEALS_BOARD_ID)
        if WORK_ORDERS_BOARD_ID:
            result["work_orders_board"] = fetch_board_columns(WORK_ORDERS_BOARD_ID)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat(req: ChatRequest):
    """
    Main endpoint.  Runs the full Grok tool-calling agent loop.

    • The LLM decides which tools to call.
    • Tools execute live Monday.com API requests.
    • Data is cleaned + metrics computed.
    • The LLM summarises into a business insight.
    • The full tool trace is returned alongside the answer.
    """
    try:
        from llm_agent import run_agent

        logger.info("Incoming query: %r  (history: %d turns)", req.query, len(req.history))
        result = run_agent(req.query, history=req.history)

        return ChatResponse(
            answer=result["answer"],
            trace=[TraceStep(**s) for s in result["trace"]],
            model=result["model"],
            iterations=result["iterations"],
            query=req.query,
        )
    except Exception as exc:
        logger.exception("Agent error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/tools/test", tags=["Debug"])
async def test_tool(req: ToolTestRequest):
    """
    Directly execute a single tool (bypasses the LLM).
    Helpful for integration testing.
    """
    try:
        from tools import execute_tool, get_trace, clear_trace, clear_cache

        clear_trace()
        clear_cache()
        result_json = execute_tool(req.tool_name, req.arguments)
        import json

        return {"result": json.loads(result_json), "trace": get_trace()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─── Dev server ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=True)
