"""
llm_agent.py
────────────
Grok (xAI) agent with multi-turn tool-calling loop.

Flow:
  1) Build system prompt + user message
  2) Send to Grok with tool schemas
  3) If Grok issues tool calls → execute them → feed results back
  4) Repeat until Grok returns a final text response
  5) Return final answer + full trace
"""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI
from dotenv import load_dotenv

from tools import (
    TOOL_SCHEMAS,
    execute_tool,
    get_trace,
    clear_trace,
    clear_cache,
    _step,
)

load_dotenv()

logger = logging.getLogger(__name__)

GROK_API_KEY = os.getenv("GROK_API_KEY", "")
GROK_MODEL   = os.getenv("GROK_MODEL", "")

# ── Auto-detect LLM provider from key prefix ──────────────────────────────
# gsk_...  → Groq  (https://console.groq.com)
# xai-...  → xAI Grok (https://console.x.ai)
# sk-...   → OpenAI
if GROK_API_KEY.startswith("gsk_"):
    _BASE_URL = "https://api.groq.com/openai/v1"
    # llama-3.1-8b-instant: 500K tokens/day free tier (5x higher than 70b)
    # Switch to llama-3.3-70b-versatile for higher quality on paid tier
    GROK_MODEL = GROK_MODEL or "llama-3.1-8b-instant"
    _PROVIDER  = "Groq"
elif GROK_API_KEY.startswith("xai-"):
    _BASE_URL = "https://api.x.ai/v1"
    GROK_MODEL = GROK_MODEL or "grok-3-beta"
    _PROVIDER  = "xAI Grok"
else:
    # Default: OpenAI-compatible fallback
    _BASE_URL = "https://api.openai.com/v1"
    GROK_MODEL = GROK_MODEL or "gpt-4o-mini"
    _PROVIDER  = "OpenAI"

logger.info("LLM provider: %s | model: %s", _PROVIDER, GROK_MODEL)

client = OpenAI(
    api_key=GROK_API_KEY,
    base_url=_BASE_URL,
)

SYSTEM_PROMPT = """You are Monday BI — a Business Intelligence assistant for a B2B sales team.
Your ONLY purpose is to answer questions about the company's Monday.com deal pipeline and work orders.

════════════ AVAILABLE DATA FIELDS ════════════

DEALS board — each deal record has:
  • name          — deal/project name
  • owner         — owner code (e.g. OWNER_001, OWNER_002)
  • sector        — industry sector (e.g. Mining, Renewables, Aviation)
  • deal_value    — masked financial value of the deal (the deal's monetary size)
                    ALWAYS display monetary values with the ₹ symbol (Indian Rupees), never $.
  • deal_status   — Open / Closed Won / Lost
  • stage         — funnel stage (a.Lead → g.Lost)
  • probability_label — High / Medium / Low closure probability
  • close_date    — expected or actual close date
  • product       — product/service type for this deal (e.g. Lidar, Survey, DSP)

WORK ORDERS board — each record has:
  • name, sector, status, revenue_excl_gst, revenue_incl_gst,
    billed_excl_gst, collected, wo_status, completion_date

════════════ STRICT BEHAVIOUR RULES ════════════

1. GREETINGS / SMALL TALK
   - If the user says hi, hello, hey, thanks, bye, etc., respond warmly and briefly.
   - Example: "Hello! 👋 How can I help you with your pipeline data today?"
   - Do NOT mention deals, sectors, or numbers unprompted.

2. DATA QUESTIONS (your core job)
   - Always call the relevant tools FIRST before answering.
   - Lead with the headline number, then supporting detail.
   - IMPORTANT: if the user asks about a specific deal field (like "product"),
     filter and show the value of THAT field from the deal records.
     Do NOT substitute a different field (e.g. deal_value) for the asked field.
   - Always note any data quality issues (missing fields, incomplete records).
   - Never invent or estimate numbers — only report what the tools return.

3. FOLLOW-UP / CLARIFICATIONS
   - The conversation history is provided. ALWAYS read prior messages before answering.
   - If the user is correcting or clarifying a previous answer, understand what
     they originally wanted and give the correct answer this time.
   - Never ignore context from earlier in the conversation.

4. CUSTOMER / OWNER NAMES
   - The dataset contains customer codes and owner codes that may look like
     unusual names, fictional characters, animals, or random strings
     (e.g. "Scooby-Doo", "OWNER_002", "Alpha Corp", "XYZ-42").
   - NEVER refuse a query just because a name sounds fictional or unfamiliar.
   - ALWAYS call get_work_orders or get_deals and search the actual data.
   - If no matching record is found, say "No records found for [name]" — do NOT
     say you don't know about them or that they're off-topic.

5. OFF-TOPIC QUESTIONS (anything not about the deals / work-order data)
   - You MUST refuse politely. Do not attempt to answer.
   - Use this exact pattern:
     "Sorry, I'm only able to help with questions about your Monday.com deal pipeline
      and work orders. I can't assist with [topic]. Is there anything about your sales
      data I can help with?"
   - Examples of off-topic: recipes, general coding, news, weather, jokes,
     unrelated business topics, anything outside the pipeline/WO data.

6. AMBIGUOUS QUESTIONS
   - Ask ONE short clarifying question before calling any tool.

7. TONE
   - Professional, concise, data-driven.
   - ALWAYS use ₹ (Indian Rupees) for ALL monetary values. Never use $ or USD.
   - Never make up numbers. Never go off-topic.

════════════════════════════════════════════════
"""

MAX_TOOL_ITERATIONS = 8  # safety cap

# ── Keywords used for lightweight intent pre-check ────────────────────────
_GREETING_TOKENS = {
    "hi", "hello", "hey", "helo", "hii", "hiii", "howdy", "sup", "yo",
    "good morning", "good afternoon", "good evening", "greetings",
    "thanks", "thank you", "cheers", "bye", "goodbye", "see you",
}

_OFFTOPIC_SIGNALS = [
    "recipe", "cook", "bake", "cake", "food", "movie", "music", "song",
    "weather", "news", "joke", "funny", "poem", "write a story",
    "translate", "currency", "stock price", "crypto", "bitcoin",
    "who is", "what is the capital", "how to make", "how do i install",
    "code in", "write a function", "python script", "javascript",
    "restaurant", "hotel", "flight", "travel", "sport", "football",
    "cricket", "election", "politics", "celebrity",
]

_DATA_SIGNALS = [
    # Core BI terms
    "deal", "deals", "sector", "pipeline", "revenue", "work order",
    "wo ", " wo", "conversion", "forecast", "stage", "won", "lost",
    "open", "closed", "probability", "billed", "collected", "gst",
    "performance", "funnel", "lead", "proposal", "negotiation",
    "monday", "board", "sales", "win rate", "completion",
    # Owner / customer / project lookups
    "owner", "owner_", "customer", "client", "project", "account",
    "executed", "execute", "recurring", "last", "latest", "recent",
    "month", "quarter", "year", "date", "when", "status",
    "show me", "list", "find", "get", "fetch", "what is", "what are",
    "how many", "how much", "which", "top", "bottom", "highest", "lowest",
    "average", "total", "sum", "count", "breakdown",
]


def _classify_intent(query: str) -> str:
    """Return 'greeting', 'offtopic', or 'data'."""
    q = query.lower().strip()
    # Pure greeting (short message or matches greeting token set)
    tokens = set(q.rstrip("!?.").split())
    if tokens & _GREETING_TOKENS and len(q) <= 60:
        return "greeting"
    # Contains a data signal → always treat as data question
    if any(sig in q for sig in _DATA_SIGNALS):
        return "data"
    # Contains explicit off-topic signal
    if any(sig in q for sig in _OFFTOPIC_SIGNALS):
        return "offtopic"
    # Very short with no data signal → likely small talk
    if len(q.split()) <= 4 and not any(sig in q for sig in _DATA_SIGNALS):
        return "greeting"
    return "data"  # default: let the LLM decide


def run_agent(user_query: str, history: list[dict] | None = None) -> dict:
    """
    Entry point.  Returns:
      {
        "answer":  str,        # final LLM response
        "trace":   list[dict], # tool call trace steps
        "model":   str,
        "iterations": int,
      }

    history: list of {"role": "user"|"assistant", "content": str} from prior turns.
    """
    clear_trace()
    clear_cache()

    _step("Agent started", f"Query: {user_query!r}")

    # ── If there is prior conversation history, any message is potentially
    #    a follow-up/clarification — skip the off-topic fast-path so the LLM
    #    can use full context to respond correctly.
    has_history = bool(history)

    # ── Fast-path: greeting ───────────────────────────────────────────────
    intent = _classify_intent(user_query)
    if intent == "greeting" and not has_history:
        _step("Intent: greeting", "Returning canned response")
        return {
            "answer": "Hello! 👋 How can I help you with your Monday.com pipeline data today?",
            "trace": get_trace(),
            "model": GROK_MODEL,
            "iterations": 0,
        }

    # ── Fast-path: off-topic (only when no prior context) ────────────────
    if intent == "offtopic" and not has_history:
        _step("Intent: off-topic", "Refusing politely")
        return {
            "answer": (
                "Sorry, I'm only able to help with questions about your "
                "Monday.com deal pipeline and work orders. "
                "I can't assist with that. "
                "Is there anything about your sales data I can help with?"
            ),
            "trace": get_trace(),
            "model": GROK_MODEL,
            "iterations": 0,
        }

    _step("Model selected", GROK_MODEL)


    # Build message list: system → conversation history → current user message
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in history:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_query})

    iteration = 0
    final_answer = ""

    while iteration < MAX_TOOL_ITERATIONS:
        iteration += 1
        _step(f"LLM call #{iteration}", f"Sending {len(messages)} message(s) to {GROK_MODEL}")

        try:
            response = client.chat.completions.create(
                model=GROK_MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception as api_err:
            err_str = str(api_err)
            # Friendly rate-limit message instead of raw 429 dump
            if "429" in err_str or "rate_limit" in err_str.lower():
                import re as _re
                wait = _re.search(r"try again in ([\d]+m[\d.]+s|[\d.]+s)", err_str)
                wait_str = f" Please wait {wait.group(1)} and try again." if wait else " Please try again in a few minutes."
                _step("⚠️ Rate limit hit", err_str[:120])
                return {
                    "answer": f"⏳ **Daily token limit reached** for the free Groq tier (100K tokens/day).{wait_str}\n\nTip: Upgrade at https://console.groq.com/settings/billing to remove this limit.",
                    "trace": get_trace(),
                    "model": GROK_MODEL,
                    "iterations": iteration,
                }
            raise

        msg = response.choices[0].message

        # ── Append assistant turn to history (v2-compatible serialisation) ──
        # Cap tool calls at 5 per turn to guard against model hallucinations
        capped_tool_calls = (msg.tool_calls or [])[:5]
        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if capped_tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in capped_tool_calls
            ]
        messages.append(assistant_entry)

        # ── Check for tool calls ──
        if capped_tool_calls:
            # Safety cap: never execute more than 5 tool calls in one LLM turn
            tool_calls_to_run = capped_tool_calls
            _step(
                f"Tool calls requested ({len(tool_calls_to_run)})",
                ", ".join(tc.function.name for tc in tool_calls_to_run),
            )
            for tc in tool_calls_to_run:
                tool_name = tc.function.name
                tool_args = tc.function.arguments
                _step(f"→ Executing {tool_name}()", f"args: {tool_args}")

                result_json = execute_tool(tool_name, tool_args)

                # Feed result back into conversation
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_json,
                    }
                )
            # Continue loop so LLM can reason over results
            continue

        # ── No more tool calls → final answer ──
        final_answer = msg.content or ""
        _step("Agent finished", f"Answer length: {len(final_answer)} chars")
        break
    else:
        final_answer = (
            "I reached the maximum number of tool-call iterations. "
            "Please try a more specific question."
        )
        _step("⚠️ Max iterations reached", f"Limit: {MAX_TOOL_ITERATIONS}")

    return {
        "answer": final_answer,
        "trace": get_trace(),
        "model": GROK_MODEL,
        "iterations": iteration,
    }
