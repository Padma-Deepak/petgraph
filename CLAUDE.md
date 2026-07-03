# PetGraph — Unified Pet Health Record

Hackathon MVP. FastAPI + React knowledge graph for pet health records, powered by Cognee.
Cognee's embedded stores (Kuzu graph + LanceDB vectors) own the pet graph; SQLite holds
app state only (documents, reminders, insights). Seed data is Indian-localized (Bengaluru).

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, Python 3.11+, cognee 1.2.2 (Kuzu graph + LanceDB vectors, embedded) |
| App state | aiosqlite (SQLite) at `backend/petgraph.db` — documents, reminders, insights only |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Graph viz | react-force-graph-2d |
| LLM | OpenAI (default) or Anthropic — set via env |

## Running locally

**Backend** (port 8000):
```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
Startup takes ~10–30 s (Cognee imports). CORS is pre-configured for ports 5173 and 3000.

**Frontend** (port 5173):
```
cd frontend
npm install
npm run dev
```

⚠ If Docker Desktop is running another app on 5173, `localhost:5173` may resolve to it
(IPv6 `::1`) instead of Vite (IPv4). Open **http://127.0.0.1:5173** instead.

⚠ Cognee spawns Kuzu worker subprocesses that hold the graph DB lock. If you kill the
backend, kill the whole tree (`taskkill /T /F /PID <pid>`) or the next start fails with
"Could not set lock on file".

## Environment variables

Stored in `backend/.env` (create if missing):

```
OPENAI_API_KEY=sk-...        # default LLM provider
ANTHROPIC_API_KEY=sk-ant-... # alternative
LLM_PROVIDER=openai          # "openai" | "anthropic"
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...           # mirror of the key, read by Cognee
OPENAI_BASE_URL=https://api.openai.com/v1  # guards against user-level env overrides
COGNEE_SKIP_CONNECTION_TEST=true
```

LLM is only needed for document upload (cognify), query, and summary. **Seed loading,
graph browsing, per-pet filter, reminders, insights, and conflicts all work without a key.**

## Features

### 1. Document ingestion (`/api/ingest`)
- `POST /upload` — upload a `.txt` health record; SSE progress; extraction + `cognee.add`/`cognify`
- `GET /seed` — fast seed load: pre-computed graph written straight into Cognee's graph
  engine (no LLM); resets DB first; semantic indexing (cognify) queued in the background
- `DELETE /reset` — wipe all data (dev only)
- `GET /documents` — list all ingested documents

Seed documents in `backend/seed_documents/`: 8 files, 2 pets (Bella the dog, Charlie the
cat), Bengaluru providers, Sept 2025 – June 2026 timeline.

### 2. Knowledge graph (`/api/graph`) — Cognee-owned
- `GET /api/graph` — domain nodes + edges (Cognee semantic-layer nodes filtered out)
- `GET /api/graph/node/{id}` — node detail + neighbors + source documents
- `GET /api/graph/pets`, `GET /api/graph/providers`
- `GET /api/graph/pet/{id}/subgraph` — per-pet subgraph via Cypher on Kuzu (used by the
  UI's pet filter; keeps Bella/Charlie separate despite the shared owner)
- `GET /api/graph/cognee/status` — semantic index state + node counts (debug drawer)

### 3. Symptom / NL query (`/api/query`) — relevance-aware
`POST /api/query/symptom`, requires LLM. Pipeline (`services/graph_service.py`):
1. Pet/owner names in the query are neutralized to "my pet" before retrieval — raw names
   match every record and drown out the symptom signal.
2. Cognee ChunksRetriever (LanceDB) returns scored chunks; relevance branches on the best
   cosine distance: strong ≤ 0.55 < moderate ≤ 0.58 < weak. Thresholds calibrated on seed data.
3. Strong/moderate → anchors from matched docs, neighborhood subgraph via Cypher (drives
   the canvas animation), GRAPH_COMPLETION context, citations.
   Weak/none → honest "no closely related history", general guidance, **no citations,
   no traversal** — never force a connection.
4. Every step lands in `cognee_trace` for the UI's "How Cognee found this" drawer.

### 4. Reminders (`/api/reminders`) — no LLM
Auto-generated after seed/ingestion (`services/reminders.py`): vaccine boosters (recorded
next-due, else annual — Indian practice), follow-up appointments, medication end dates.
`GET /` (auto-unsnoozes lapsed), `POST /refresh`, `POST /{id}/dismiss`, `POST /{id}/snooze`.
Stored in SQLite; IDs are stable hashes so dismissals survive regeneration.

### 5. Proactive insights (`/api/insights`) — no LLM
Analysis pass over the Cognee graph after seed/ingestion (`services/insights.py`):
recurring symptom patterns, overdue vaccines, checkup gaps, life-stage milestones.
Each carries a "why flagged" plus a trust label: `pet_records` (from this pet's history)
vs `general_guideline` (pet data + standard practice). The UI must never blur the two.

### 6. Conflict detection (`/api/conflicts`) — no LLM
Deterministic rules over the Cognee graph: medication active-vs-discontinued across
providers; ER vaccine newer than the primary vet's record. Both fire on seed data.

### 7. Pre-visit summary (`/api/summary/{provider_id}`)
LLM brief of what changed since the pet's last visit with that provider (with fallback).

## Frontend structure (query-first, plain language)

Tabs: **Ask** (default; chat with relevance chip, "Why this answer" citations drawer,
"How Cognee found this" technical drawer) · **Health map** (canvas + pet filter chips) ·
**Reminders** (badge; red when overdue) · **Worth knowing** (insights feed, trust badges) ·
**Alerts** (conflicts) · **Visit prep** · **Records** (seed + upload).

Rule: no graph jargon (node/edge/BFS/vector) in user-facing copy — technical terms live
only inside the "How Cognee found this" drawer.

```
petgraph/
  backend/
    main.py               # FastAPI app, router mounting, startup recovery
    config.py             # env vars, paths
    database.py           # SQLite app state (documents, reminders, insights)
    seed_graph.py         # pre-computed seed → Cognee graph engine
    routers/              # ingest, graph, query, conflicts, summary, reminders, insights
    services/
      cognee_graph.py     # ALL graph-store access (adapter calls + Cypher)
      graph_service.py    # relevance-aware query + pre-visit summary
      reminders.py        # reminder generation rules
      insights.py         # insight generation rules
      conflict_detector.py
      ingestion.py        # upload pipeline (extraction + cognee add/cognify)
      entity_extractor.py / entity_resolver.py   # upload path helpers
    seed_documents/       # 8 Indian-localized .txt records
  frontend/
    src/
      App.tsx             # tab navigation, badges, pet filter (server subgraph)
      api/client.ts       # axios API wrapper
      components/
        AskPanel.tsx        # primary chat (relevance chip + disclosure drawers)
        GraphCanvas.tsx     # force graph + traversal animation
        RemindersPanel.tsx  # dismiss / snooze
        InsightsPanel.tsx   # trust-labeled feed
        ConflictPanel.tsx / PreVisitSummary.tsx / NodeDetailPanel.tsx / DocumentUpload.tsx
```

## Known state (2026-07-03, post upgrade pass)
- All features above verified end-to-end (seed → reminders 6 / insights 3 / conflicts 2;
  relevance branches correctly on related vs unrelated queries; UI screenshot-checked,
  no horizontal scroll at 1366 px).
- `AUDIT.md` documents the pre-upgrade audit that drove this architecture.
- LLM key in `backend/.env` is configured and working.
