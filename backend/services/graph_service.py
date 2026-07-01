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
    1. Cognee semantic search → find anchor nodes.
    2. BFS from anchors → traversal path.
    3. Generate longitudinal summary with citations.
    Returns: {traversal_path, nodes, links, summary, citations, anchor_nodes}
    """
    all_nodes = await db.get_all_nodes()
    all_edges = await db.get_all_edges()

    node_map = {n["id"]: n for n in all_nodes}

    # Step 1: find anchor nodes via Cognee or fallback keyword matching
    anchor_ids = await _find_anchors(query_text, all_nodes)

    # Step 2: BFS up to depth 3 from anchors
    traversal_path = _bfs(anchor_ids, node_map, all_edges, max_depth=3)

    # Collect subgraph
    visited_ids = set(traversal_path)
    sub_nodes = [_format_node(node_map[nid]) for nid in visited_ids if nid in node_map]
    sub_edges = [
        _format_edge(e) for e in all_edges
        if e["source"] in visited_ids and e["target"] in visited_ids
    ]

    # Step 3: generate summary
    context_nodes = [node_map[nid] for nid in traversal_path if nid in node_map]
    summary, citations, suggestions = await _generate_summary(
        query_text, context_nodes, node_map, history=history or []
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
            from cognee.api.v1.search import SearchType
            cognee_results = await asyncio.wait_for(
                cognee.search(query, search_type=SearchType.CHUNKS), timeout=20
            )
            for cr in (cognee_results or [])[:5]:
                # Extract text from various Cognee result shapes
                text = ""
                for attr in ("text", "description", "layer_description", "content", "chunk_text"):
                    val = getattr(cr, attr, None)
                    if val:
                        text = str(val)
                        break
                if not text and isinstance(cr, dict):
                    text = str(cr)
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


async def _generate_summary(
    query: str,
    nodes: list[dict],
    node_map: dict | None = None,
    history: list[dict] | None = None,
) -> tuple[str, list[dict], list[str]]:
    """
    Generate a longitudinal summary with inline [Provider · Date] citations
    and 2–3 suggested follow-up questions, informed by conversation history.
    Returns (summary_text, citations, suggestions).
    """
    if not nodes:
        return "No relevant history found.", [], []

    nm = node_map or {}
    context_lines = []
    citations = []

    for n in nodes:
        props = n.get("properties", {})
        date = props.get("date") or props.get("start_date") or ""
        source_docs = n.get("source_doc_ids", [])

        provider_name = ""
        for pkey in ("provider_id", "prescriber_id"):
            pid = props.get(pkey)
            if pid and pid in nm:
                provider_name = nm[pid]["name"]
                break

        cite_parts = [p for p in (provider_name, date) if p]
        cite_hint = " · ".join(cite_parts)

        line = f"- [{n['type'].upper()}] {n['name']}"
        if cite_hint:
            line += f"  [cite: {cite_hint}]"
        context_lines.append(line)

        if n["type"] in ("symptom", "diagnosis", "medication", "vaccine"):
            citations.append({
                "entity": n["name"],
                "type": n["type"],
                "date": date,
                "source": source_docs[0] if source_docs else "unknown",
                "provider": provider_name,
            })

    context = "\n".join(context_lines)

    # Build conversation history block (last 6 turns, clean text only)
    history_block = ""
    if history:
        lines = []
        for msg in history[-6:]:
            role = "Owner" if msg["role"] == "user" else "PetGraph"
            lines.append(f"{role}: {msg['content']}")
        history_block = "Conversation so far:\n" + "\n".join(lines) + "\n\n"

    prompt = (
        f"{history_block}"
        f'Owner now asks: "{query}"\n\n'
        f"Using the pet health graph nodes below, respond in JSON with exactly two keys:\n"
        f'  "summary": 2–4 sentences answering the question. '
        f"If this is a follow-up, connect it to the prior conversation. "
        f"Embed inline citations as [Provider · Date] immediately after each clinical fact "
        f'(e.g. "Bella had otitis externa [Dr. Webb · 2025-08-18]"). '
        f"Use the [cite: ...] hints to form citations. Write in plain English for a pet owner.\n"
        f'  "suggestions": array of exactly 3 short follow-up questions the owner might want to ask next, '
        f"grounded in what was found. Keep each under 10 words.\n\n"
        f"Respond with ONLY valid JSON — no markdown fences, no extra text.\n\n"
        f"Graph nodes:\n{context}"
    )

    try:
        raw = await _llm_call(prompt)
        parsed = _parse_json_response(raw)
        summary_text = parsed.get("summary", _fallback_summary(nodes))
        suggestions = parsed.get("suggestions", [])[:3]
        if not isinstance(suggestions, list):
            suggestions = []
    except Exception:
        summary_text = _fallback_summary(nodes)
        suggestions = []

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
