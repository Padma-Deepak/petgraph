"""
Symptom query and pre-visit summary, orchestrated by Cognee.

Retrieval flow for a query:
  1. cognee vector retrieval (ChunksRetriever) → scored chunks (cosine distance)
  2. relevance decision from Cognee's own scores → strong / weak / none branch
  3. matched chunks → source documents → anchor nodes in the domain graph
     (provenance mapping: every domain node records its source_doc_ids)
  4. neighborhood subgraph around anchors via Cognee graph queries (Cypher) —
     drives the canvas traversal animation
  5. cognee GRAPH_COMPLETION for a graph-native semantic answer
  6. LLM composes the owner-facing response; the prompt branches on relevance,
     so unrelated history is never forced into the answer
Every step is captured in a `cognee_trace` payload for the debug drawer.
"""
import asyncio

from config import LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, ANTHROPIC_API_KEY
import database as db
from services import cognee_graph

# Cosine distance thresholds (lower = closer). Between the two = "moderate".
# Scored on name-neutralized queries (pet names swapped for "my pet") — the
# raw pet name matches every document and drowns out the symptom signal.
# Calibrated on seed data: related queries score 0.53–0.58, unrelated
# symptoms 0.59+ — so strong ≤ 0.55 and the moderate/weak boundary is 0.58.
RELEVANCE_STRONG = 0.55
RELEVANCE_WEAK = 0.58

CLINICAL_TYPES = {"symptom", "diagnosis", "medication", "vaccine", "visit"}


async def symptom_query(query_text: str, history: list[dict] | None = None) -> dict:
    graph = await cognee_graph.get_full_graph()
    node_map = {n["id"]: n for n in graph["nodes"]}

    trace: dict = {
        "semantic_status": cognee_graph.get_semantic_status(),
        "operations": [],
    }

    # 1) + 2) Cognee vector retrieval and relevance decision.
    # Retrieval runs on a name-neutralized query: the pet's name appears in
    # every record, so leaving it in makes any "<name> <symptom>" query look
    # close to the whole history regardless of the symptom.
    neutralized = _neutralize_names(query_text, graph["nodes"])
    if neutralized != query_text:
        trace["query_neutralized"] = neutralized
    chunks = await _cognee_chunk_search(neutralized, trace)
    relevance = _assess_relevance(chunks)
    trace["relevance"] = relevance

    # 3) anchors from matched documents (provenance mapping)
    anchor_ids: list[str] = []
    if relevance["level"] in ("strong", "moderate"):
        anchor_ids = _anchors_from_chunks(chunks, graph["nodes"])
    trace["anchor_nodes"] = anchor_ids

    # 4) subgraph around anchors via Cognee graph queries
    traversal_path, sub_nodes, sub_links = [], [], []
    if anchor_ids:
        traversal_path, sub_nodes, sub_links = await _anchor_neighborhood(anchor_ids, trace)

    # 5) Cognee graph-native completion (skipped when history is unrelated)
    cognee_insight = ""
    if relevance["level"] in ("strong", "moderate"):
        cognee_insight = await _cognee_graph_completion(query_text, trace)

    # 6) owner-facing response, branched on relevance
    path_nodes = [node_map[nid] for nid in traversal_path if nid in node_map]
    summary, citations, suggestions = await _generate_response(
        query_text, graph, node_map, path_nodes,
        relevance=relevance, cognee_insight=cognee_insight,
        history=history or [],
    )
    if relevance["level"] not in ("strong", "moderate"):
        citations = []  # no stretched provenance on unrelated answers

    return {
        "anchor_nodes": anchor_ids,
        "traversal_path": traversal_path,
        "nodes": sub_nodes,
        "links": sub_links,
        "summary": summary,
        "citations": citations,
        "suggestions": suggestions,
        "relevance": relevance,
        "cognee_trace": trace,
    }


# ── Cognee retrieval steps ────────────────────────────────────────────────────

def _neutralize_names(query: str, nodes: list[dict]) -> str:
    """Swap pet/owner names (and recorded aliases) for neutral placeholders so
    vector distance reflects the symptom, not the name."""
    import re
    terms: list[tuple[str, str]] = []
    for n in nodes:
        if n["type"] == "pet":
            terms.append((n["name"], "my pet"))
            for alias in n.get("properties", {}).get("aliases") or []:
                terms.append((str(alias), "my pet"))
        elif n["type"] == "owner":
            terms.append((n["name"], "me"))
    out = query
    for term, repl in sorted(terms, key=lambda t: -len(t[0])):
        if len(term) < 3:
            continue
        out = re.sub(rf"\b{re.escape(term)}(?=\b|')", repl, out, flags=re.IGNORECASE)
    return out

async def _cognee_chunk_search(query: str, trace: dict) -> list[dict]:
    """Vector search via Cognee's ChunksRetriever, keeping its raw scores."""
    op = {"op": "vector_search", "engine": "cognee ChunksRetriever (LanceDB)",
          "collection": "DocumentChunk_text", "results": []}
    trace["operations"].append(op)
    try:
        from cognee.modules.retrieval.chunks_retriever import ChunksRetriever
        retriever = ChunksRetriever(top_k=6)
        scored = await asyncio.wait_for(retriever.get_retrieved_objects(query), timeout=25)
    except Exception as e:
        op["error"] = str(e)[:200]
        return []

    docs = await db.get_all_documents()
    results = []
    for s in scored or []:
        text = (s.payload or {}).get("text", "")
        doc = _match_chunk_to_document(text, docs)
        entry = {
            "text": text,
            "score": round(float(s.score), 4),
            "doc_id": doc["id"] if doc else None,
            "doc_filename": doc["filename"] if doc else None,
        }
        results.append(entry)
        op["results"].append({
            "snippet": text[:160], "score": entry["score"],
            "document": entry["doc_filename"],
        })
    return results


def _match_chunk_to_document(chunk_text: str, docs: list[dict]) -> dict | None:
    """Map a Cognee chunk back to the stored source document by content."""
    if not chunk_text:
        return None
    probe = chunk_text.strip()[:200]
    for d in docs:
        if probe and probe in d["content"]:
            return d
    # chunker may normalize whitespace — retry on a squashed comparison
    squashed = " ".join(probe.split())[:150]
    for d in docs:
        if squashed and squashed in " ".join(d["content"].split()):
            return d
    return None


def _assess_relevance(chunks: list[dict]) -> dict:
    """Branch on Cognee's own retrieval scores — no second relevance model."""
    scored = [c["score"] for c in chunks if c.get("doc_id")]
    if not scored:
        state = cognee_graph.get_semantic_status().get("state")
        return {
            "level": "unavailable" if state != "ready" else "none",
            "best_score": None,
            "thresholds": {"strong": RELEVANCE_STRONG, "weak": RELEVANCE_WEAK},
            "explanation": (
                "Cognee's semantic index is still being built — answers use general guidance only."
                if state != "ready"
                else "No records were close enough to this question to retrieve."
            ),
        }
    best = min(scored)
    if best <= RELEVANCE_STRONG:
        level, explanation = "strong", "Past records closely match this question (low vector distance)."
    elif best <= RELEVANCE_WEAK:
        level, explanation = "moderate", "Some past records are loosely related — treat the link as tentative."
    else:
        level, explanation = "weak", "Nothing in the records is a close match; the answer avoids referencing history."
    return {
        "level": level,
        "best_score": best,
        "thresholds": {"strong": RELEVANCE_STRONG, "weak": RELEVANCE_WEAK},
        "explanation": explanation,
    }


def _anchors_from_chunks(chunks: list[dict], nodes: list[dict]) -> list[str]:
    """Domain nodes whose provenance intersects the retrieved documents,
    best-scoring documents first, clinical node types prioritized."""
    doc_rank: dict[str, float] = {}
    for c in chunks:
        if c.get("doc_id") and c["doc_id"] not in doc_rank:
            doc_rank[c["doc_id"]] = c["score"]

    ranked: list[tuple[float, int, str]] = []
    for n in nodes:
        node_docs = set(n.get("source_doc_ids", [])) & set(doc_rank)
        if not node_docs:
            continue
        best_doc = min(doc_rank[d] for d in node_docs)
        type_prio = 0 if n["type"] in ("symptom", "diagnosis", "medication") else 1
        ranked.append((best_doc, type_prio, n["id"]))

    ranked.sort()
    return [nid for _, _, nid in ranked[:5]]


async def _anchor_neighborhood(anchor_ids: list[str], trace: dict) -> tuple[list, list, list]:
    """1–2 hop neighborhood around the anchors, via Cypher on Cognee's graph.
    Ordered anchors → 1-hop → 2-hop for the traversal animation."""
    eng = await cognee_graph.engine()
    cypher_1 = ("MATCH (a:Node)-[:EDGE]-(m:Node) WHERE a.id IN $ids "
                "RETURN DISTINCT m.id")
    cypher_2 = ("MATCH (a:Node)-[:EDGE*2..2]-(m:Node) WHERE a.id IN $ids "
                "RETURN DISTINCT m.id")
    hop1 = {str(r[0]) for r in await eng.query(cypher_1, {"ids": anchor_ids})}
    hop2 = {str(r[0]) for r in await eng.query(cypher_2, {"ids": anchor_ids})}
    trace["operations"].append({
        "op": "graph_neighborhood",
        "engine": "cognee.graph (kuzu/cypher)",
        "cypher": "MATCH (a:Node)-[:EDGE*1..2]-(m:Node) WHERE a.id IN $anchors",
        "hop1_count": len(hop1), "hop2_count": len(hop2),
    })

    ordered: list[str] = list(anchor_ids)
    for nid in sorted(hop1 - set(ordered)):
        ordered.append(nid)
    for nid in sorted(hop2 - set(ordered) - hop1):
        ordered.append(nid)

    node_rows = await eng.query(
        "MATCH (n:Node) WHERE n.id IN $ids RETURN n.id, n.name, n.type, n.properties",
        {"ids": ordered},
    )
    nodes = [
        cognee_graph._node_from_props(str(r[0]), {"name": r[1], "type": r[2], "properties": r[3]})
        for r in node_rows
    ]
    nodes = [n for n in nodes if n["type"] in cognee_graph.DOMAIN_TYPES]
    kept = {n["id"] for n in nodes}
    ordered = [nid for nid in ordered if nid in kept]

    edge_rows = await eng.query(
        "MATCH (n:Node)-[r:EDGE]->(m:Node) WHERE n.id IN $ids AND m.id IN $ids "
        "RETURN n.id, m.id, r.relationship_name",
        {"ids": list(kept)},
    )
    links = [cognee_graph._edge_out(str(r[0]), str(r[1]), str(r[2]), {}) for r in edge_rows]
    return ordered, nodes, links


async def _cognee_graph_completion(query: str, trace: dict) -> str:
    """Cognee's graph-native answer (GRAPH_COMPLETION) over the indexed docs."""
    op = {"op": "graph_completion", "engine": "cognee.search(GRAPH_COMPLETION)"}
    trace["operations"].append(op)
    try:
        import cognee
        results = await asyncio.wait_for(cognee.search(query), timeout=30)
    except Exception as e:
        op["error"] = str(e)[:200]
        return ""
    parts = []
    for r in (results or [])[:3]:
        val = getattr(r, "search_result", None) or (r if isinstance(r, str) else None)
        if val:
            parts.append(str(val)[:400])
    op["answer"] = parts[0][:200] if parts else None
    return " | ".join(parts)


# ── response generation ───────────────────────────────────────────────────────

async def _generate_response(
    query: str,
    graph: dict,
    node_map: dict,
    path_nodes: list[dict],
    relevance: dict,
    cognee_insight: str,
    history: list[dict],
) -> tuple[str, list[dict], list[str]]:
    citations: list[dict] = []
    for n in path_nodes:
        if n["type"] not in ("symptom", "diagnosis", "medication", "vaccine"):
            continue
        props = n.get("properties", {})
        date = props.get("date") or props.get("start_date") or ""
        provider_name = ""
        for pkey in ("provider_id", "prescriber_id"):
            pid = props.get(pkey)
            if pid and pid in node_map:
                provider_name = node_map[pid]["name"]
                break
        citations.append({
            "entity": n["name"], "type": n["type"], "date": date,
            "source": (n.get("source_doc_ids") or ["unknown"])[0],
            "provider": provider_name,
        })

    pet_context = _build_pet_context(graph["nodes"], graph["links"], node_map)

    history_block = ""
    if history:
        turns = [
            f"{'Owner' if m['role'] == 'user' else 'PetGraph'}: {m['content']}"
            for m in history[-6:]
        ]
        history_block = "Conversation so far:\n" + "\n".join(turns) + "\n\n"

    cognee_block = (
        f"\n\nSemantic graph context (from Cognee):\n{cognee_insight}\n" if cognee_insight else ""
    )

    if relevance["level"] in ("strong", "moderate"):
        connection_rule = (
            "1. CONNECT TO HISTORY: Cognee's retrieval found related past records "
            f"(confidence: {relevance['level']}). Reference the specific related records, and "
            "briefly say WHY they are related (same symptom area, same condition, recency). "
            'After every clinical fact write [Provider · Date] (e.g. "otitis externa [Dr. Nair · 2025-12-06]").'
        )
    else:
        connection_rule = (
            "1. NO RELATED HISTORY: Retrieval found no closely related past records for this "
            "question. Say so plainly in one honest sentence (e.g. 'Nothing in the records "
            "looks connected to this'). Then give general, practical next-step guidance for "
            "the concern itself. Do NOT cite, reference, or stretch any past record into the answer."
        )

    prompt = (
        f"{history_block}"
        f'Owner says: "{query}"\n\n'
        f"You are a knowledgeable pet health assistant. The owner's complete pet medical records are below.\n\n"
        f"RESPOND AS JSON with keys 'summary' and 'suggestions'. Rules:\n\n"
        f"summary (3-5 sentences, plain English for a pet owner):\n"
        f"  {connection_rule}\n"
        f"  2. SPECIFIC NEXT STEP: If a vet visit is warranted, name the SPECIFIC provider from the "
        f"directory who has treated this pet for similar issues, give their clinic, and say why. "
        f"If not urgent, give home monitoring tips with clear escalation criteria.\n"
        f"  3. FOLLOW-UP: End with one targeted clarifying question that would sharpen your advice.\n\n"
        f"suggestions (array of exactly 3 items):\n"
        f"  Mix of follow-up symptom questions, specific next actions, and deeper history queries. "
        f"Keep each under 12 words.\n\n"
        f"Output ONLY valid JSON, no markdown fences.\n\n"
        f"Pet medical records:\n{pet_context}"
        f"{cognee_block}"
    )

    try:
        raw = await _llm_call(prompt)
        parsed = _parse_json_response(raw)
        summary_text = parsed.get("summary", "")
        suggestions = parsed.get("suggestions", [])[:3]
        if not isinstance(suggestions, list):
            suggestions = []
    except Exception:
        summary_text = _fallback_summary(path_nodes, relevance)
        suggestions = [
            "What medications is she currently on?",
            "When was her last vet visit?",
            "Is she eating and drinking normally?",
        ]

    return summary_text, citations, suggestions


# ── pre-visit summary ─────────────────────────────────────────────────────────

async def pre_visit_summary(provider_id: str) -> dict:
    """What changed since the pet's last visit with this provider — reads the
    same Cognee-backed graph as the query flow."""
    graph = await cognee_graph.get_full_graph()
    all_nodes, all_edges = graph["nodes"], graph["links"]
    node_map = {n["id"]: n for n in all_nodes}

    provider = node_map.get(provider_id)
    if not provider:
        return {"error": "Provider not found"}

    visits_with_provider = [
        node_map[e["source"]] for e in all_edges
        if e["target"] == provider_id and e["relationship"] == "seen_at"
        and e["source"] in node_map
    ]

    if not visits_with_provider:
        return {"provider": provider["name"], "visits": [],
                "summary": "No prior visits found with this provider."}

    def visit_date(v):
        return v.get("properties", {}).get("date") or "0000-00-00"

    visits_with_provider.sort(key=visit_date)
    last_visit = visits_with_provider[-1]
    last_date = last_visit.get("properties", {}).get("date", "unknown")

    pet_edges = [e for e in all_edges if e["target"] == last_visit["id"] and e["relationship"] == "had_visit"]
    pet_id = pet_edges[0]["source"] if pet_edges else None
    pet = node_map.get(pet_id) if pet_id else None

    new_meds: list[dict] = []
    new_vax: list[dict] = []
    new_diagnoses: list[dict] = []
    new_providers: list[dict] = []

    if pet_id:
        for e in all_edges:
            if e["source"] != pet_id:
                continue
            node = node_map.get(e["target"])
            if not node:
                continue
            props = node.get("properties", {})
            node_date = props.get("date") or props.get("start_date") or "0000-00-00"
            if node_date > last_date:
                if node["type"] == "medication":
                    new_meds.append(node)
                elif node["type"] == "vaccine":
                    new_vax.append(node)
                elif node["type"] == "diagnosis":
                    new_diagnoses.append(node)
                elif node["type"] == "visit":
                    prov_edges = [
                        node_map.get(ev["target"]) for ev in all_edges
                        if ev["source"] == node["id"] and ev["relationship"] == "seen_at"
                    ]
                    for p in prov_edges:
                        if p and p["id"] != provider_id:
                            new_providers.append(p)

    context = {
        "provider_name": provider["name"],
        "pet_name": pet["name"] if pet else "Unknown",
        "last_visit_date": last_date,
        "new_medications": [n["name"] for n in new_meds],
        "new_vaccines": [n["name"] for n in new_vax],
        "new_diagnoses": [n["name"] for n in new_diagnoses],
        "other_providers_seen": list({p["name"] for p in new_providers}),
    }

    summary = await _generate_pre_visit_text(context)

    return {
        "provider": provider["name"],
        "pet": pet["name"] if pet else "Unknown",
        "last_visit_date": last_date,
        "new_medications": [{"name": n["name"], **n.get("properties", {})} for n in new_meds],
        "new_vaccines": [{"name": n["name"], **n.get("properties", {})} for n in new_vax],
        "new_diagnoses": [{"name": n["name"], **n.get("properties", {})} for n in new_diagnoses],
        "other_providers_seen": list({p["name"] for p in new_providers}),
        "summary": summary,
    }


# ── shared helpers ────────────────────────────────────────────────────────────

def _build_pet_context(all_nodes: list[dict], all_edges: list[dict], node_map: dict) -> str:
    """Build a complete, structured medical history for every pet — used as LLM context."""
    pets = [n for n in all_nodes if n["type"] == "pet"]
    providers = [n for n in all_nodes if n["type"] == "provider"]
    lines: list[str] = []

    for pet in pets:
        pp = pet.get("properties", {})
        lines.append(
            f"\n=== {pet['name']} | {pp.get('species','')} | {pp.get('breed','')} | {pp.get('sex','')} ==="
        )
        for e in all_edges:
            if e["source"] == pet["id"] and e["relationship"] == "owned_by":
                owner = node_map.get(e["target"])
                if owner:
                    lines.append(f"Owner: {owner['name']}")

        visits = sorted(
            [node_map[e["target"]] for e in all_edges
             if e["source"] == pet["id"] and e["relationship"] == "had_visit" and e["target"] in node_map],
            key=lambda v: v.get("properties", {}).get("date") or "0000"
        )
        if visits:
            lines.append("Visit history:")
            for v in visits:
                vp = v.get("properties", {})
                prov = node_map.get(vp.get("provider_id", "") or "", {})
                clinic = prov.get("properties", {}).get("clinic", "")
                complaint = vp.get("chief_complaint") or vp.get("visit_type") or "routine"
                lines.append(f"  [{vp.get('date','?')}] {prov.get('name','?')} ({clinic}) — {complaint}")

        syms = []
        for e in all_edges:
            if e["source"] == pet["id"] and e["relationship"] == "has_symptom":
                s = node_map.get(e["target"])
                if s:
                    d = e.get("properties", {}).get("date") or s.get("properties", {}).get("date") or ""
                    syms.append((d, s))
        if syms:
            lines.append("Symptom history:")
            for d, s in sorted(syms, key=lambda x: x[0]):
                desc = s.get("properties", {}).get("description", "")
                lines.append(f"  [{d or '?'}] {s['name']}{': ' + desc if desc else ''}")

        dxs = [node_map[e["target"]] for e in all_edges
               if e["source"] == pet["id"] and e["relationship"] == "received_diagnosis" and e["target"] in node_map]
        if dxs:
            lines.append("Diagnoses:")
            for dx in dxs:
                dp = dx.get("properties", {})
                outcome = dp.get("outcome", "")
                lines.append(f"  [{dp.get('date','?')}] {dx['name']}{' — ' + outcome if outcome else ''}")

        meds = [node_map[e["target"]] for e in all_edges
                if e["source"] == pet["id"] and e["relationship"] == "prescribed" and e["target"] in node_map]
        if meds:
            lines.append("Medications:")
            for med in meds:
                mp = med.get("properties", {})
                prescriber = node_map.get(mp.get("prescriber_id", "") or "", {}).get("name", "")
                parts = [f"{med['name']} ({mp.get('status','?')})"]
                if mp.get("dose"): parts.append(mp["dose"])
                if mp.get("start_date"): parts.append(f"started {mp['start_date']}")
                if mp.get("end_date"): parts.append(f"ended {mp['end_date']}")
                if prescriber: parts.append(f"Rx by {prescriber}")
                lines.append("  " + ", ".join(parts))

        vaxes = [node_map[e["target"]] for e in all_edges
                 if e["source"] == pet["id"] and e["relationship"] == "received_vaccine" and e["target"] in node_map]
        if vaxes:
            lines.append("Vaccines:")
            for vax in vaxes:
                vp = vax.get("properties", {})
                prov_name = node_map.get(vp.get("provider_id", "") or "", {}).get("name", "")
                next_due = f" (next due: {vp['next_due']})" if vp.get("next_due") else ""
                lines.append(f"  [{vp.get('date','?')}] {vax['name']}{next_due}{' — ' + prov_name if prov_name else ''}")

    if providers:
        lines.append("\n=== Provider Directory ===")
        for p in providers:
            pp = p.get("properties", {})
            record_count = sum(
                1 for e in all_edges
                if e["target"] == p["id"] and e["relationship"] in ("seen_at", "administered_by", "discontinued_by")
            )
            lines.append(
                f"  {p['name']} ({pp.get('provider_type','vet')}) — {pp.get('clinic','?')} [{record_count} records on file]"
            )

    return "\n".join(lines)


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    import json, re
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text.strip())


async def _generate_pre_visit_text(context: dict) -> str:
    prompt = (
        f"Write a concise pre-visit briefing (3-5 bullet points) for {context['pet_name']}'s upcoming "
        f"appointment with {context['provider_name']}. Their last visit was on {context['last_visit_date']}.\n\n"
        f"Since then:\n"
        f"- New medications: {', '.join(context['new_medications']) or 'none'}\n"
        f"- New vaccines: {', '.join(context['new_vaccines']) or 'none'}\n"
        f"- New diagnoses: {', '.join(context['new_diagnoses']) or 'none'}\n"
        f"- Other providers seen: {', '.join(context['other_providers_seen']) or 'none'}\n\n"
        f"Format as bullet points. Be specific. Flag anything that needs the provider's attention."
    )
    try:
        return await _llm_call(prompt)
    except Exception:
        return _fallback_pre_visit(context)


async def _llm_call(prompt: str) -> str:
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    elif OPENAI_API_KEY:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    raise RuntimeError("No LLM configured")


def _fallback_summary(nodes: list[dict], relevance: dict) -> str:
    if relevance["level"] not in ("strong", "moderate"):
        return (
            "No closely related history found in the records for this question. "
            "Monitor your pet and contact your vet if symptoms persist or worsen."
        )
    types = [n["type"] for n in nodes]
    dates = [n.get("properties", {}).get("date") for n in nodes if n.get("properties", {}).get("date")]
    dates.sort()
    return (
        f"Found {len(nodes)} related records: {', '.join(set(types))}. "
        + (f"Dates range from {dates[0]} to {dates[-1]}." if dates else "")
    )


def _fallback_pre_visit(ctx: dict) -> str:
    lines = [f"Pre-visit summary for {ctx['pet_name']} — last seen by {ctx['provider_name']} on {ctx['last_visit_date']}."]
    if ctx["new_medications"]:
        lines.append(f"• New medications since last visit: {', '.join(ctx['new_medications'])}")
    if ctx["new_vaccines"]:
        lines.append(f"• Vaccines administered elsewhere: {', '.join(ctx['new_vaccines'])}")
    if ctx["other_providers_seen"]:
        lines.append(f"• Also seen by: {', '.join(ctx['other_providers_seen'])}")
    return "\n".join(lines)
