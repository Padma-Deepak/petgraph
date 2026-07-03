# PetGraph — Audit (Upgrade Pass, 2026-07-03)

Audit of the existing MVP against the upgrade-pass spec, done **before** any code changes.
Verdicts: **PASS** / **PARTIAL** / **FAIL** per feature, plus Priority-1/2 findings.

## Environment facts (verified)

- `cognee==1.2.2` installed; graph backends available: **Kuzu (embedded, default)**, Neo4j,
  Neptune, Postgres; vector: **LanceDB (embedded, default)**, pgvector.
- The graph adapter (`get_graph_engine()`) exposes `add_nodes/add_edges` (no LLM needed),
  `get_graph_data`, `get_neighbors`, `get_connections`, `get_nodeset_subgraph`,
  `get_neighborhood`, and raw Cypher via `query()` (Kuzu speaks Cypher).
  Search types include `GRAPH_COMPLETION`, `HYBRID_COMPLETION`, `CHUNKS`, `TEMPORAL`.
- `backend/.env` **does** contain `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `LLM_API_KEY`
  (CLAUDE.md's "no key configured" note is stale). Validity untested at audit time.

## Feature verification (items 1–7)

### 1. Document ingestion — PARTIAL
- ✅ `.txt` upload with SSE progress (`routers/ingest.py`), LLM extraction (`entity_extractor.py`).
- ✅ Fast seed loader without LLM (`seed_graph.py`).
- ❌ **Cognee is decorative at ingestion.** `cognee.add()` + fire-and-forget `cognify()`
  (`ingestion.py:314` — `except: pass`) run beside the real pipeline; the graph that the app
  uses is built by custom LLM extraction into SQLite. Exactly the Priority-1 anti-pattern.
- ❌ **Seed path never touches Cognee at all** — after `GET /seed`, every Cognee search runs
  against an empty index.
- ❌ `seed_documents/` has **8** files but the seed graph/loader only covers 6.
  `07_bella_followup_oct.txt` and `08_bella_derm_dec.txt` (Cytopoint, atopy workup, derm
  referral) exist on disk but are absent from `NODES`/`EDGES`/`SEED_DOCUMENTS`/`DOC_META`.

### 2. Knowledge graph — PARTIAL
- ✅ Node types + typed edges, REST endpoints for full graph, node detail (neighbors + source
  docs), pets/providers views (`routers/graph.py`).
- ❌ The graph lives in **SQLite `nodes`/`edges` tables** (`database.py`) — SQLite is the
  source of truth; Cognee holds (at best) a parallel semantic index. This is the "backwards"
  architecture the spec calls out.

### 3. Interactive graph canvas — PASS (functional)
- ✅ react-force-graph-2d, traversal path animation, click-to-open detail panel.
- ⚠ UI-simplicity issues deferred to the Priority-2 pass: three dense panes at full size,
  technical jargon in user-facing chrome ("nodes/edges" counters, "N anchors → M hops",
  "● traversing").

### 4. Per-pet filtering — PARTIAL
- ✅ Works: directed BFS from the pet node, client-side in `App.tsx:26-53`; Bella/Charlie stay
  separate despite the shared owner.
- ❌ Hand-rolled BFS duplicating what Cognee's graph engine can serve
  (`get_nodeset_subgraph` / Cypher on Kuzu). Priority-1 replacement target.

### 5. Natural-language / symptom query — PARTIAL
- ✅ Conversation history, traversal path, summary, citations, follow-up suggestions all wired.
- ❌ **Not Cognee-native hybrid search.** `graph_service.py` does keyword matching over SQLite
  node names + custom BFS; `cognee.search(CHUNKS)` is a best-effort side call whose text is
  string-matched back onto SQLite nodes; `GRAPH_COMPLETION` output is pasted into the LLM
  prompt as a text blob. Vector search and graph walk are stitched in app code — exactly what
  Priority 1 says to replace.
- ❌ **No relevance-aware branching** — worse, `_find_anchors` force-anchors to an arbitrary
  symptom/diagnosis node when nothing matches (`graph_service.py:188-193`), guaranteeing a
  stretched connection. Spec requires the opposite (honest "no closely related history").

### 6. Conflict detection — PASS (rules) / PARTIAL (data source)
- ✅ Deterministic, rule-based, no LLM (`conflict_detector.py`): medication
  active-vs-discontinued across providers; ER vaccine newer than primary-vet record. Both fire
  on seed data.
- ⚠ Reads from the SQLite shadow graph. Rules should stay custom (per spec) but must read
  from Cognee's graph once it owns the data.

### 7. Pre-visit summary — PARTIAL
- ✅ Works: finds last visit with provider, diffs events since, LLM brief with fallback.
- ⚠ Same SQLite source as feature 5 (consistent with it), but repoints to Cognee with the rest.

### Entity resolution (cross-cutting) — FAIL per Priority 1
- Custom fingerprint/string matching (`entity_resolver.py`) handles Bella / "Bella M." /
  "Patient #4471". Works on seed data, but it is hand-rolled dedup, not Cognee's entity
  resolution. Replacement target when ingestion routes through `cognify`.

### Breed-knowledge layer — N/A
- Not present in the current build (no code, no UI). The "general breed knowledge, not from
  your pet's records" labeling rule therefore has nothing to attach to; noted so the insights
  feature keeps the trust-level separation when added.

## New-feature gaps (all missing, as expected)

- **Reminders** — nothing exists (no table, no endpoint, no UI).
- **Relevance-aware retrieval** — absent; current behavior actively forces connections (see #5).
- **Proactive insights** — absent; nothing runs analysis passes over the graph.
- **"How Cognee found this" panel** — absent; no retrieval trace surfaced anywhere.

## Localization — FAIL (US throughout)

- Owner "Sarah Mitchell", phone `555-234-7890`; clinics in **Sacramento, CA** with US
  addresses; providers Dr. Priya Singh / Dr. Marcus Webb / Dr. Lisa Chen (DACVD/DACVECC US
  credentials).
- Medications: Zymox Otic, Mometamax, Apoquel, Cytopoint, Imrab 3 — US brand set.
- Vaccine schedule is US-style (3-year rabies booster "good through 2028", DHPP, Bordetella);
  Indian practice is annual rabies boosters and a different core set (ARV, DHPPi+L).
- Units: lbs, °F. No currency appears.
- Applies to all 8 seed docs, the entire pre-computed `seed_graph.py`, `DOC_META`, and
  frontend starter prompts.

## Priority-1 remediation plan (approved direction per spec)

Cognee becomes the owner of the pet graph + vector store; SQLite shrinks to app bookkeeping
(documents metadata, reminders, insight/dismissal state).

1. **Seed path (no LLM, preserved):** write the pre-computed graph directly into Cognee's
   graph engine via `add_nodes`/`add_edges` — key-free demo still works; graph browsing,
   per-pet filter, and conflicts run without any LLM.
2. **Graph endpoints** read from Cognee (`get_graph_data`, `get_neighbors`).
3. **Per-pet subgraph** served by Cognee graph queries (Cypher on Kuzu / `get_nodeset_subgraph`)
   via a new server endpoint; client BFS removed.
4. **Upload ingestion** routes through `cognee.add` + `cognify` (semantic layer + Cognee's own
   entity dedup) with typed domain nodes written to the same Cognee graph; custom
   `entity_resolver.py` retired from the pet-graph path.
5. **Symptom query** uses `cognee.search` (GRAPH_COMPLETION / CHUNKS with scores) as the
   retrieval engine; traversal path for the animation derives from Cognee neighborhood calls,
   not a hand BFS. Relevance branching keys off Cognee's own scores; the "anchor to anything"
   fallback is deleted.
6. **Conflicts + pre-visit summary** read nodes/edges from Cognee's graph.
7. **"How Cognee found this" drawer** shows the actual operation (search type, matched
   chunks/entities, scores, graph hops) for query and summary flows.

Risk note: Cognee internal adapter APIs are version-pinned (1.2.2) — implementation verifies
each call against the installed package rather than docs.

## Build order for this pass (per spec)

1. ✅ This audit.
2. Priority-1 Cognee re-architecture (items above).
3. Relevance-aware retrieval branching.
4. Reminders (SQLite-backed, auto-generated post-ingestion, dismiss/snooze, badge UI).
5. Proactive insights (on-ingestion analysis pass over Cognee graph, separate feed,
   trust-level labeling).
6. Indian localization of all seed docs (rewrite 8 docs), seed graph, DOC_META, prompts,
   schedules (annual rabies etc.), names/phones/₹/kg/°C.
7. UI simplification (Priority 2): query-first layout, progressive disclosure for canvas /
   provenance / debug drawer, plain-language copy.
