"""
Ingestion pipeline — Cognee-first.

  1. cognee.add + cognee.cognify: the document enters Cognee's memory —
     chunking, embeddings, semantic entity extraction and dedup. This is the
     pipeline that powers hybrid search.
  2. Typed domain extraction (LLM): pets/providers/meds/vaccines with the
     properties the business rules need, canonicalized against entities already
     in the graph (canonical_id — no fuzzy string matching in app code).
  3. Typed nodes and edges are written into the same Cognee graph.
  4. Reminders and insights are re-derived from the updated graph.
"""
import asyncio
from typing import AsyncIterator

import database as db
from services import cognee_graph
from services.entity_extractor import extract_entities
from services.entity_resolver import (
    make_pet_node_id,
    make_owner_node_id,
    make_provider_node_id,
    make_medication_node_id,
    make_vaccine_node_id,
    make_symptom_node_id,
    make_diagnosis_node_id,
    make_visit_node_id,
    normalize_name,
)


async def ingest_document(
    content: str,
    filename: str,
    doc_type: str | None = None,
    provider_name: str | None = None,
    doc_date: str | None = None,
) -> AsyncIterator[dict]:
    """
    Full ingestion pipeline. Yields progress events as dicts:
      {"stage": str, "message": str, "pct": int}
    """
    import uuid

    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    await db.save_document({
        "id": doc_id,
        "filename": filename,
        "content": content,
        "doc_type": doc_type,
        "provider_name": provider_name,
        "doc_date": doc_date,
    })
    yield {"stage": "saved", "message": f"Saved document: {filename}", "pct": 8, "doc_id": doc_id}

    # Step 1: Cognee memory pipeline (chunking → embeddings → semantic graph)
    try:
        import cognee
        yield {"stage": "cognee_add", "message": "Adding to Cognee memory…", "pct": 15}
        await cognee.add(content, dataset_name="petgraph")
        yield {"stage": "cognee_cognify", "message": "Cognee cognify: building semantic graph…", "pct": 25}
        await asyncio.wait_for(cognee.cognify(datasets="petgraph"), timeout=420)
        cognee_graph.SEMANTIC_STATUS.update(state="ready", error=None)
        yield {"stage": "cognee_done", "message": "Cognee semantic graph updated ✓", "pct": 55}
    except Exception as e:
        yield {"stage": "cognee_warn",
               "message": f"Cognee semantic indexing failed (continuing): {str(e)[:120]}", "pct": 55}

    # Step 2: typed domain extraction, canonicalized against the existing graph
    yield {"stage": "extracting", "message": "Extracting health entities…", "pct": 60}
    try:
        existing_pets = await cognee_graph.get_nodes_by_type("pet")
        existing_providers = await cognee_graph.get_nodes_by_type("provider")
        entities = await extract_entities(content, doc_id, existing_pets, existing_providers)
    except Exception as e:
        yield {"stage": "error", "message": f"Entity extraction failed: {e}", "pct": 100}
        return

    n_entities = sum(len(v) for v in entities.values() if isinstance(v, list))
    yield {"stage": "extracted", "message": f"Found {n_entities} entities", "pct": 72}

    # Step 3: write typed nodes + edges into the Cognee graph
    yield {"stage": "graphing", "message": "Updating knowledge graph…", "pct": 78}
    try:
        await _build_graph(entities, doc_id)
    except Exception as e:
        yield {"stage": "error", "message": f"Graph build failed: {e}", "pct": 100}
        return

    await db.mark_document_processed(doc_id)

    # Step 4: refresh derived state from the updated graph
    try:
        from services import reminders, insights
        await reminders.generate_reminders()
        await insights.generate_insights()
        yield {"stage": "derived", "message": "Reminders & insights refreshed", "pct": 95}
    except Exception as e:
        yield {"stage": "derived_warn", "message": f"Reminder/insight refresh failed: {str(e)[:120]}", "pct": 95}

    yield {"stage": "done", "message": "Document ingested ✓", "pct": 100, "doc_id": doc_id}


def _canonical(entity: dict, known_ids: set[str]) -> str | None:
    """canonical_id from the extractor, validated against the actual graph."""
    cid = entity.get("canonical_id")
    return cid if cid and cid in known_ids else None


async def _build_graph(entities: dict, doc_id: str):
    existing_pets = await cognee_graph.get_nodes_by_type("pet")
    existing_providers = await cognee_graph.get_nodes_by_type("provider")
    known_pet_ids = {p["id"] for p in existing_pets}
    known_provider_ids = {p["id"] for p in existing_providers}

    edges: list[tuple[str, str, str, dict]] = []

    # --- Owners ---
    owner_ids: dict[str, str] = {}
    for o in entities.get("owners", []):
        oid = make_owner_node_id(o["name"])
        await cognee_graph.upsert_node({
            "id": oid,
            "type": "owner",
            "name": o["name"],
            "properties": {"phone": o.get("phone")},
            "source_doc_ids": [doc_id],
        })
        owner_ids[o["name"]] = oid

    # --- Providers ---
    provider_ids: dict[str, str] = {}
    for p in entities.get("providers", []):
        pid = _canonical(p, known_provider_ids) or make_provider_node_id(p["name"], p.get("clinic", ""))
        await cognee_graph.upsert_node({
            "id": pid,
            "type": "provider",
            "name": p["name"],
            "properties": {
                "clinic": p.get("clinic"),
                "provider_type": p.get("type", "vet"),
            },
            "source_doc_ids": [doc_id],
        })
        provider_ids[p["name"]] = pid

    # --- Pets ---
    pet_ids: dict[str, str] = {}  # raw_name (normalized) → node id
    for ep in entities.get("pets", []):
        raw_name = ep.get("raw_name", ep.get("name", ""))
        pid_pet = _canonical(ep, known_pet_ids) or make_pet_node_id(ep.get("species", ""), ep.get("name", raw_name))
        await cognee_graph.upsert_node({
            "id": pid_pet,
            "type": "pet",
            "name": ep.get("name", raw_name),
            "properties": {
                "species": ep.get("species"),
                "breed": ep.get("breed"),
                "sex": ep.get("sex"),
                "dob_approx": ep.get("dob_approx"),
                "weight_kg": ep.get("weight_kg"),
                "aliases": [raw_name],
                "owner_name": next(iter(owner_ids), None),
            },
            "source_doc_ids": [doc_id],
        })
        pet_ids[normalize_name(raw_name)] = pid_pet

        if owner_ids:
            owner_id = next(iter(owner_ids.values()))
            edges.append((pid_pet, owner_id, "owned_by", {"source_doc_id": doc_id}))

    def resolve_pet_id(raw_name: str) -> str | None:
        return pet_ids.get(normalize_name(raw_name or ""))

    # --- Visits ---
    for v in entities.get("visits", []):
        pet_id = resolve_pet_id(v.get("pet_raw_name", ""))
        prov_id = provider_ids.get(v.get("provider_name", ""))
        vid = make_visit_node_id(v.get("date"), pet_id or "unknown", prov_id or "unknown")
        await cognee_graph.upsert_node({
            "id": vid,
            "type": "visit",
            "name": f"Visit {v.get('date', 'undated')}",
            "properties": {
                "date": v.get("date"),
                "visit_type": v.get("type"),
                "chief_complaint": v.get("chief_complaint"),
                "follow_up_date": v.get("follow_up_date"),
                "provider_id": prov_id,
                "pet_id": pet_id,
            },
            "source_doc_ids": [doc_id],
        })
        if pet_id:
            edges.append((pet_id, vid, "had_visit", {"source_doc_id": doc_id}))
        if prov_id:
            edges.append((vid, prov_id, "seen_at", {"source_doc_id": doc_id}))

    # --- Symptoms ---
    for s in entities.get("symptoms", []):
        pet_id = resolve_pet_id(s.get("pet_raw_name", ""))
        sid = make_symptom_node_id(s["name"])
        await cognee_graph.upsert_node({
            "id": sid,
            "type": "symptom",
            "name": s["name"],
            "properties": {
                "description": s.get("description"),
                "ear_side": s.get("ear_side"),
                "date": s.get("date"),
            },
            "source_doc_ids": [doc_id],
        })
        if pet_id:
            edges.append((pet_id, sid, "has_symptom",
                          {"date": s.get("date"), "source_doc_id": doc_id}))

    # --- Diagnoses ---
    for dx in entities.get("diagnoses", []):
        pet_id = resolve_pet_id(dx.get("pet_raw_name", ""))
        did_dx = make_diagnosis_node_id(dx["name"])
        await cognee_graph.upsert_node({
            "id": did_dx,
            "type": "diagnosis",
            "name": dx["name"],
            "properties": {"date": dx.get("date"), "outcome": dx.get("outcome")},
            "source_doc_ids": [doc_id],
        })
        if pet_id:
            edges.append((pet_id, did_dx, "received_diagnosis",
                          {"date": dx.get("date"), "source_doc_id": doc_id}))

    # --- Medications ---
    for med in entities.get("medications", []):
        pet_id = resolve_pet_id(med.get("pet_raw_name", ""))
        prov_id = provider_ids.get(med.get("prescriber_name", ""))
        med_id = make_medication_node_id(med["name"], med.get("rx_number"))
        await cognee_graph.upsert_node({
            "id": med_id,
            "type": "medication",
            "name": med["name"],
            "properties": {
                "dose": med.get("dose"),
                "frequency": med.get("frequency"),
                "start_date": med.get("start_date"),
                "end_date": med.get("end_date"),
                "status": med.get("status", "unknown"),
                "rx_number": med.get("rx_number"),
                "prescriber_id": prov_id,
            },
            "source_doc_ids": [doc_id],
        })
        if pet_id:
            edges.append((pet_id, med_id, "prescribed",
                          {"status": med.get("status"), "date": med.get("start_date"),
                           "source_doc_id": doc_id}))
        if prov_id:
            rel = "discontinued_by" if med.get("status") == "discontinued" else "administered_by"
            edges.append((med_id, prov_id, rel, {"source_doc_id": doc_id}))

    # --- Vaccines ---
    for vax in entities.get("vaccines", []):
        pet_id = resolve_pet_id(vax.get("pet_raw_name", ""))
        prov_id = provider_ids.get(vax.get("provider_name", ""))
        vax_id = make_vaccine_node_id(vax["name"], vax.get("date"), pet_id or "unknown")
        await cognee_graph.upsert_node({
            "id": vax_id,
            "type": "vaccine",
            "name": vax["name"],
            "properties": {
                "date": vax.get("date"),
                "next_due": vax.get("next_due"),
                "lot": vax.get("lot"),
                "provider_id": prov_id,
            },
            "source_doc_ids": [doc_id],
        })
        if pet_id:
            edges.append((pet_id, vax_id, "received_vaccine",
                          {"date": vax.get("date"), "source_doc_id": doc_id}))
        if prov_id:
            edges.append((vax_id, prov_id, "administered_by", {"source_doc_id": doc_id}))

    if edges:
        await cognee_graph.add_edges(edges)
