"""
Graph traversal, symptom query, and pre-visit summary.
Uses Cognee hybrid search for semantic matching, then walks our SQLite graph.
"""
import asyncio
from collections import deque
from config import LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, ANTHROPIC_API_KEY
import database as db

_cognee_available = False
try:
    import cognee
    _cognee_available = True
except ImportError:
    pass


async def get_full_graph() -> dict:
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()
    return {
        "nodes": [_format_node(n) for n in nodes],
        "links": [_format_edge(e) for e in edges],
    }


async def symptom_query(query_text: str, history: list[dict] | None = None) -> dict:
    """
    1. BFS from keyword-matched anchors → graph animation path.
    2. Full pet medical history → LLM generates a contextual, connected response.
    Returns: {traversal_path, nodes, links, summary, citations, suggestions, anchor_nodes}
    """
    all_nodes = await db.get_all_nodes()
    all_edges = await db.get_all_edges()
    node_map = {n["id"]: n for n in all_nodes}

    # BFS for graph animation (keyword anchors → traversal highlights)
    anchor_ids = await _find_anchors(query_text, all_nodes)
    traversal_path = _bfs(anchor_ids, node_map, all_edges, max_depth=3)

    visited_ids = set(traversal_path)
    sub_nodes = [_format_node(node_map[nid]) for nid in visited_ids if nid in node_map]
    sub_edges = [
        _format_edge(e) for e in all_edges
        if e["source"] in visited_ids and e["target"] in visited_ids
    ]

    # Full-context intelligent response (not limited to BFS hits)
    bfs_nodes = [node_map[nid] for nid in traversal_path if nid in node_map]
    summary, citations, suggestions = await _generate_intelligent_response(
        query_text, all_nodes, all_edges, node_map,
        bfs_nodes=bfs_nodes, history=history or []
    )

    return {
        "anchor_nodes": anchor_ids,
        "traversal_path": traversal_path,
        "nodes": sub_nodes,
        "links": sub_edges,
        "summary": summary,
        "citations": citations,
        "suggestions": suggestions,
    }


async def pre_visit_summary(provider_id: str) -> dict:
    """Generate a summary of what's changed since the pet's last visit with this provider."""
    all_nodes = await db.get_all_nodes()
    all_edges = await db.get_all_edges()
    node_map = {n["id"]: n for n in all_nodes}

    provider = node_map.get(provider_id)
    if not provider:
        return {"error": "Provider not found"}

    # Find all visits with this provider
    visits_with_provider = [
        node_map[e["source"]] for e in all_edges
        if e["target"] == provider_id and e["relationship"] == "seen_at"
        and e["source"] in node_map
    ]

    if not visits_with_provider:
        return {"provider": provider["name"], "visits": [], "summary": "No prior visits found with this provider."}

    # Sort visits by date
    def visit_date(v):
        return v.get("properties", {}).get("date") or "0000-00-00"

    visits_with_provider.sort(key=visit_date)
    last_visit = visits_with_provider[-1]
    last_date = last_visit.get("properties", {}).get("date", "unknown")

    # Find the pet for this visit
    pet_edges = [e for e in all_edges if e["target"] == last_visit["id"] and e["relationship"] == "had_visit"]
    pet_id = pet_edges[0]["source"] if pet_edges else None
    pet = node_map.get(pet_id) if pet_id else None

    # Collect events since last visit
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
            node_date = props.get("date") or props.get("start_date", "0000-00-00")
            if node_date > last_date:
                if node["type"] == "medication":
                    new_meds.append(node)
                elif node["type"] == "vaccine":
                    new_vax.append(node)
                elif node["type"] == "diagnosis":
                    new_diagnoses.append(node)
                elif node["type"] == "visit":
                    # check if different provider
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


# ── helpers ──────────────────────────────────────────────────────────────────

async def _find_anchors(query: str, all_nodes: list[dict]) -> list[str]:
    """Find relevant nodes using Cognee search + fallback keyword matching."""
    q_lower = query.lower()

    # Keyword fallback (always run for speed + reliability in demo)
    keyword_anchors = []
    priority_types = {"symptom", "diagnosis", "medication"}
    for n in all_nodes:
        name_lower = n["name"].lower()
        desc = n.get("properties", {}).get("description", "").lower()
        if any(word in name_lower or word in desc for word in q_lower.split()):
            keyword_anchors.append((0 if n["type"] in priority_types else 1, n["id"]))

    keyword_anchors.sort()
    result = [nid for _, nid in keyword_anchors[:5]]

    if _cognee_available and OPENAI_API_KEY:
        try:
            from cognee.modules.search.types.SearchType import SearchType
            cognee_results = await asyncio.wait_for(
                cognee.search(query, query_type=SearchType.CHUNKS), timeout=20
            )
            for cr in (cognee_results or [])[:5]:
                text = str(getattr(cr, "search_result", "") or "")
                text_lower = text.lower()
                for n in all_nodes:
                    if n["name"].lower() in text_lower and n["id"] not in result:
                        result.insert(0, n["id"])
        except Exception:
            pass

    # Always anchor to at least one clinical node
    if not result:
        for n in all_nodes:
            if n["type"] in ("symptom", "diagnosis"):
                result.append(n["id"])
                break

    return result[:5]


def _bfs(start_ids: list[str], node_map: dict, edges: list[dict], max_depth: int = 3) -> list[str]:
    """BFS traversal returning ordered list of visited node IDs."""
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()

    for sid in start_ids:
        if sid in node_map:
            queue.append((sid, 0))
            visited.add(sid)

    path: list[str] = []
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e["source"], []).append(e["target"])
        adj.setdefault(e["target"], []).append(e["source"])

    while queue:
        nid, depth = queue.popleft()
        path.append(nid)
        if depth < max_depth:
            for neighbor in adj.get(nid, []):
                if neighbor not in visited and neighbor in node_map:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

    return path


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

        # Visits
        visits = sorted(
            [node_map[e["target"]] for e in all_edges
             if e["source"] == pet["id"] and e["relationship"] == "had_visit" and e["target"] in node_map],
            key=lambda v: v.get("properties", {}).get("date") or "0000"
        )
        if visits:
            lines.append("Visit history:")
            for v in visits:
                vp = v.get("properties", {})
                prov = node_map.get(vp.get("provider_id", ""), {})
                clinic = prov.get("properties", {}).get("clinic", "")
                complaint = vp.get("chief_complaint") or vp.get("visit_type") or "routine"
                lines.append(f"  [{vp.get('date','?')}] {prov.get('name','?')} ({clinic}) — {complaint}")

        # Symptoms (with dates)
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

        # Diagnoses
        dxs = [node_map[e["target"]] for e in all_edges
               if e["source"] == pet["id"] and e["relationship"] == "received_diagnosis" and e["target"] in node_map]
        if dxs:
            lines.append("Diagnoses:")
            for dx in dxs:
                dp = dx.get("properties", {})
                outcome = dp.get("outcome", "")
                lines.append(f"  [{dp.get('date','?')}] {dx['name']}{' — ' + outcome if outcome else ''}")

        # Medications (active and discontinued, with prescriber)
        meds = [node_map[e["target"]] for e in all_edges
                if e["source"] == pet["id"] and e["relationship"] == "prescribed" and e["target"] in node_map]
        if meds:
            lines.append("Medications:")
            for med in meds:
                mp = med.get("properties", {})
                prescriber = node_map.get(mp.get("prescriber_id", ""), {}).get("name", "")
                parts = [f"{med['name']} ({mp.get('status','?')})"]
                if mp.get("dose"): parts.append(mp["dose"])
                if mp.get("start_date"): parts.append(f"started {mp['start_date']}")
                if mp.get("end_date"): parts.append(f"ended {mp['end_date']}")
                if prescriber: parts.append(f"Rx by {prescriber}")
                lines.append("  " + ", ".join(parts))

        # Vaccines
        vaxes = [node_map[e["target"]] for e in all_edges
                 if e["source"] == pet["id"] and e["relationship"] == "received_vaccine" and e["target"] in node_map]
        if vaxes:
            lines.append("Vaccines:")
            for vax in vaxes:
                vp = vax.get("properties", {})
                prov_name = node_map.get(vp.get("provider_id", ""), {}).get("name", "")
                next_due = f" (next due: {vp['next_due']})" if vp.get("next_due") else ""
                lines.append(f"  [{vp.get('date','?')}] {vax['name']}{next_due}{' — ' + prov_name if prov_name else ''}")

    # Provider directory — so the LLM can name specific vets
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


async def _generate_intelligent_response(
    query: str,
    all_nodes: list[dict],
    all_edges: list[dict],
    node_map: dict,
    bfs_nodes: list[dict],
    history: list[dict] | None = None,
) -> tuple[str, list[dict], list[str]]:
    """
    Generate a tailored, contextually-aware response using the pet's FULL medical history.
    The LLM sees every symptom, diagnosis, medication, and provider — not just BFS fragments.
    Citations are extracted from the focused BFS subgraph for the UI strip.
    """
    # Citations strip from BFS (focused, not overwhelming)
    citations: list[dict] = []
    for n in bfs_nodes:
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

    # Full medical history for the LLM
    pet_context = _build_pet_context(all_nodes, all_edges, node_map)

    # Cognee GRAPH_COMPLETION: semantic graph-native reasoning over the indexed docs
    cognee_insight = ""
    if _cognee_available and OPENAI_API_KEY:
        try:
            gc_results = await asyncio.wait_for(
                cognee.search(query),  # default query_type=GRAPH_COMPLETION
                timeout=20,
            )
            if gc_results:
                parts = []
                for r in gc_results[:3]:
                    val = getattr(r, "search_result", None)
                    if val:
                        parts.append(str(val)[:400])
                if parts:
                    cognee_insight = "Graph-derived insight: " + " | ".join(parts)
        except Exception:
            pass

    history_block = ""
    if history:
        turns = [
            f"{'Owner' if m['role'] == 'user' else 'PetGraph'}: {m['content']}"
            for m in history[-6:]
        ]
        history_block = "Conversation so far:\n" + "\n".join(turns) + "\n\n"

    cognee_block = f"\n\nSemantic graph context (from Cognee):\n{cognee_insight}\n" if cognee_insight else ""

    prompt = (
        f"{history_block}"
        f'Owner says: "{query}"\n\n'
        f"You are a knowledgeable pet health assistant. The owner's complete pet medical records are below.\n\n"
        f"RESPOND AS JSON with keys 'summary' and 'suggestions'. Rules:\n\n"
        f"summary (3-5 sentences, plain English for a pet owner):\n"
        f"  1. CONNECT TO HISTORY: Explicitly check whether this symptom or concern appears in the records "
        f"or could relate to a prior diagnosis, active medication, or past condition. State clearly if you "
        f"found a connection or found nothing — never be vague.\n"
        f"  2. INLINE CITATIONS: After every clinical fact write [Provider · Date] "
        f'(e.g. "Bella had otitis externa [Dr. Webb · 2025-08-18]").\n'
        f"  3. SPECIFIC NEXT STEP: If a vet visit is warranted, name the SPECIFIC provider from the "
        f"directory who has treated this pet for similar issues, give their clinic, and say why they are "
        f"the right choice. If not urgent, give home monitoring tips with clear escalation criteria.\n"
        f"  4. FOLLOW-UP: End with one targeted clarifying question that would sharpen your advice.\n\n"
        f"suggestions (array of exactly 3 items):\n"
        f"  Mix of: follow-up symptom questions, specific next actions ('Book with Dr. X'), "
        f"and deeper history queries grounded in what is in the records. Keep each under 12 words.\n\n"
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
        summary_text = _fallback_summary(bfs_nodes)
        suggestions = ["What medications is she currently on?", "When was her last vet visit?", "Is she eating and drinking normally?"]

    return summary_text, citations, suggestions


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    import json, re
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
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


def _fallback_summary(nodes: list[dict]) -> str:
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


def _format_node(n: dict) -> dict:
    return {
        "id": n["id"],
        "type": n["type"],
        "name": n["name"],
        "properties": n.get("properties", {}),
        "source_doc_ids": n.get("source_doc_ids", []),
    }


def _format_edge(e: dict) -> dict:
    return {
        "id": e["id"],
        "source": e["source"],
        "target": e["target"],
        "relationship": e["relationship"],
        "properties": e.get("properties", {}),
        "source_doc_id": e.get("source_doc_id"),
    }
