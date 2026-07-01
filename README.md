# PetGraph

Unified pet health record powered by Cognee's hybrid graph-vector retrieval.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + uvicorn + aiosqlite |
| Graph retrieval | Cognee 1.2.2 (pip) |
| Frontend | React 18 + Vite + Tailwind + react-force-graph-2d |
| Optional DBs | PostgreSQL/pgvector, Neo4j 5.26, Redis (via Docker profiles) |

---

## Quickstart (Docker — recommended)

### 1. Prerequisites

- Docker Desktop ≥ 4.x with Compose V2 (`docker compose version`)
- An OpenAI API key (only needed for the document-upload LLM path; the seed graph demo works without one)

### 2. Configure secrets

```bash
cd backend
cp .env.example .env
# Edit .env — paste your OPENAI_API_KEY and LLM_API_KEY
```

### 3. Build and run

```bash
# From the project root (where docker-compose.yml lives)
docker compose up --build
```

- **API** → http://localhost:8000
- **UI**  → http://localhost:5173

The first boot takes 60–90 seconds while Cognee initialises its internal databases.

### 4. Load the demo graph

Open the UI, click **🚀 Load Seed Data**, and the pre-computed 23-node / 38-edge graph appears instantly — no API key required.

---

## With Cognee's full backend stack

Activate Postgres (pgvector), Neo4j, and Redis using Docker Compose profiles.
These services use the same configuration as the [official Cognee docker-compose](https://github.com/topoteretes/cognee).

```bash
docker compose --profile postgres --profile neo4j --profile redis up --build
```

Then update `backend/.env`:

```
DB_PROVIDER=postgres
DB_HOST=postgres
GRAPH_DATABASE_PROVIDER=neo4j
GRAPH_DATABASE_URL=bolt://neo4j:7687
```

Neo4j browser: http://localhost:7474 (login: `neo4j` / `pleaseletmein`)

---

## Local development (no Docker)

### Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # fill in your key
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Project layout

```
petgraph/
├── docker-compose.yml          # orchestration (+ official Cognee infra profiles)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # env-var config (DATA_DIR, DB_PATH, LLM keys)
│   ├── database.py             # SQLite graph store (aiosqlite)
│   ├── seed_graph.py           # pre-computed 23-node demo graph (no LLM needed)
│   ├── seed_documents/         # 6 source text files with deliberate conflicts
│   ├── routers/
│   │   ├── ingest.py           # POST /upload (SSE), GET /seed, DELETE /reset
│   │   ├── graph.py            # GET /graph, GET /query, GET /conflicts
│   │   └── summary.py          # GET /pre-visit-summary
│   └── services/
│       ├── ingestion.py        # LLM-based entity extraction (document upload path)
│       ├── graph_service.py    # BFS traversal + Cognee search + LLM summary
│       └── conflict_detector.py # rule-based conflict detection (no LLM)
└── frontend/
    ├── Dockerfile
    ├── vite.config.ts          # proxy: VITE_API_TARGET or localhost:8000
    └── src/
        ├── components/
        │   ├── GraphCanvas.tsx      # react-force-graph-2d, drag-to-pin, traversal anim
        │   ├── DocumentUpload.tsx   # seed button + SSE upload progress
        │   ├── TraversalPanel.tsx   # symptom query → BFS animation
        │   ├── ConflictPanel.tsx    # rule-based conflicts display
        │   ├── PreVisitSummary.tsx  # pre-visit summary generator
        │   └── NodeDetailPanel.tsx  # entity resolution + node details overlay
        └── types.ts
```

---

## Key demo scenarios

| Scenario | How to reproduce |
|---|---|
| Entity resolution | Click the **Bella** node → NodeDetailPanel shows 3 aliases merged into one node |
| Medication conflict | Conflicts tab → Zymox Otic discontinued by Westside but listed active by ER |
| Missing vaccine record | Conflicts tab → Rabies booster at ER not in primary vet records |
| Graph traversal | Query tab → type "ear infection" → watch BFS animation ripple through the graph |
| Pre-visit summary | Pre-Visit tab → select a provider → generates what's changed since last visit |

---

## Environment variables

See `backend/.env.example` for the full list.
Critical ones for Docker:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | LLM extraction + summaries |
| `LLM_API_KEY` | — | Cognee's internal LLM calls (same value as above) |
| `DATA_DIR` | `/data` (Docker) | SQLite + Cognee system file location |
| `VITE_API_TARGET` | `http://petgraph-api:8000` | Frontend proxy target inside Docker |
| `DB_PROVIDER` | `sqlite` | Set to `postgres` when postgres profile is active |
| `GRAPH_DATABASE_PROVIDER` | `networkx` | Set to `neo4j` when neo4j profile is active |
