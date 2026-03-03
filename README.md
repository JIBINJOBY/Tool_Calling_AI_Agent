# Monday BI Agent

A **Tool-Calling AI Agent** that connects to your Monday.com boards, runs live GraphQL queries, cleans messy data, computes business metrics, and returns actionable insights — all powered by **xAI Grok** with full tool-call transparency.

---

## Architecture

```
User (Browser)
   ↓
React Frontend  (Vite · Chat UI + Tool Trace Panel)
   ↓  HTTP
FastAPI Backend
   ↓
Grok LLM  (xAI — tool-calling loop)
   ↓
Tool Functions  (get_deals, calculate_pipeline, sector_performance, …)
   ↓
Monday.com GraphQL API  (live, no caching)
```

---

## Project Structure

```
monday-bi-agent/
│
├── backend/
│   ├── main.py            # FastAPI app — /chat, /health, /tools/test
│   ├── llm_agent.py       # Grok agent with multi-turn tool-calling loop
│   ├── tools.py           # Tool schemas + executors + trace emitter
│   ├── monday_api.py      # Monday.com GraphQL client
│   ├── data_cleaning.py   # Sector/revenue/date normalisation + quality report
│   ├── business_logic.py  # Pipeline, forecast, sector comparison, conversion rate
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                        # Root layout
│   │   ├── App.css                        # Global dark-theme styles
│   │   └── components/
│   │       ├── ChatWindow.jsx             # Chat messages + input
│   │       ├── MessageBubble.jsx          # Individual message rendering
│   │       └── ToolTracePanel.jsx         # Live tool-call trace sidebar
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── .env.example           # Copy → .env and fill in your keys
├── decision_log.md
├── setup.bat              # Windows one-click setup
└── setup.sh               # Unix one-click setup
```

---

## Quick Start

### 1 — Clone & configure environment

```bash
git clone <repo>
cd monday-bi-agent

# Copy and fill in your API keys
cp .env.example .env
```

Edit `.env`:

| Variable                    | Where to get it                                   |
|-----------------------------|---------------------------------------------------|
| `MONDAY_API_TOKEN`          | Monday.com → Profile → Developer → Access Tokens |
| `MONDAY_DEALS_BOARD_ID`     | URL when you open your Deals board                |
| `MONDAY_WORK_ORDERS_BOARD_ID` | URL when you open your Work Orders board        |
| `GROK_API_KEY`              | https://console.x.ai                             |
| `GROK_MODEL`                | `grok-3-beta` (default)                           |

### 2 — Windows (automated)

```bat
setup.bat
```

### 2 — Unix / macOS (automated)

```bash
chmod +x setup.sh && ./setup.sh
```

### 3 — Manual setup

**Backend**
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Unix:
source .venv/bin/activate

pip install -r requirements.txt
# copy .env.example → .env siblings directory
copy ..\\.env.example ..\\.env
python main.py
```

**Frontend** (separate terminal)
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

---

## API Endpoints

| Method | Path              | Description                         |
|--------|-------------------|-------------------------------------|
| GET    | `/health`         | Liveness check                      |
| POST   | `/chat`           | Main agent endpoint                 |
| GET    | `/boards/columns` | Debug — list board column IDs       |
| POST   | `/tools/test`     | Debug — call a single tool directly |

### POST /chat

```json
// Request
{ "query": "How's our energy pipeline this quarter?" }

// Response
{
  "answer": "Your Energy pipeline for Q1 2026 stands at $4.2M across 12 open deals…",
  "trace": [
    { "step": "Agent started",        "detail": "Query: 'How's our energy pipeline…'" },
    { "step": "Calling get_deals()",  "detail": "Fetching live deals from Monday.com GraphQL API" },
    { "step": "Retrieved raw deals",  "detail": "84 items fetched from Monday.com" },
    { "step": "Normalised deal fields","detail": "Sector aliases resolved: 7 | Usable: 79/84 (94.0%)" },
    { "step": "calculate_pipeline()", "detail": "sector=Energy | quarter=Q1 2026 | deals available=79" },
    { "step": "Pipeline computed",    "detail": "Total pipeline: $4,200,000.00" },
    { "step": "Agent finished",       "detail": "Answer length: 312 chars" }
  ],
  "model": "grok-3-beta",
  "iterations": 2
}
```

---

## Available Tools

| Tool                 | What it does                                                     |
|----------------------|------------------------------------------------------------------|
| `get_deals`          | Fetch & clean all deals from Monday.com Deals board              |
| `get_work_orders`    | Fetch & clean all work orders from Monday.com Work Orders board  |
| `calculate_pipeline` | Open pipeline value by sector and/or quarter                     |
| `sector_performance` | Compare all sectors — top, weakest, share %                      |
| `revenue_forecast`   | Probability-weighted forecast using stage win-rates              |
| `conversion_rate`    | Deal win-rate + work-order completion rate                       |

---

## Monday.com Column ID Mapping

If your board has custom column IDs, update the maps in `backend/data_cleaning.py`:

```python
DEAL_COLUMN_MAP = {
    "sector":     "your_actual_sector_column_id",
    "value":      "your_actual_value_column_id",
    "stage":      "your_actual_status_column_id",
    "close_date": "your_actual_date_column_id",
    "owner":      "your_actual_people_column_id",
}
```

Use `GET /boards/columns` to inspect column IDs at runtime.

---

## Deployment

### Render (recommended)

**Backend**
1. New Web Service → Connect repo
2. Root directory: `backend`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables from `.env`

**Frontend**
1. New Static Site → Connect repo
2. Root directory: `frontend`
3. Build command: `npm install && npm run build`
4. Publish directory: `dist`
5. Set `VITE_API_BASE` to your backend URL

---

## Data Quality

Every response includes a **data quality report**:
- Total records fetched
- % usable (have sector + value)
- Count of missing fields
- Normalisation actions taken (e.g. "Energy Sector" → "Energy")

This is surfaced in the agent's answer so stakeholders know how to interpret the numbers.
