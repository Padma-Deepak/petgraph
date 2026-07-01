"""
Ingestion pipeline: Cognee semantic indexing + custom domain entity extraction + SQLite graph building.

Cognee role: add() + cognify() builds the vector+graph index for semantic search.
Our role: entity extraction → SQLite graph → entity resolution.
"""
import asyncio
import uuid
from typing import AsyncIterator

import database as db
from services.entity_extractor import extract_entities
from services.entity_resolver import (
    resolve_pets,
    resolve_providers,
    make_pet_node_id,
    make_provider_node_id,
    make_medication_node_id,
    make_vaccine_node_id,
    make_symptom_node_id,
    make_diagnosis_node_id,
    make_visit_node_id,
    normalize_name,
)

_cognee_available = False
try:
    import cognee
    _cognee_available = True
except ImportError:
    pass


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
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    did = await db.save_document({
        "id": doc_id,
        "filename": filename,
        "content": content,
        "doc_type": doc_type,
        "provider_name": provider_name,
        "doc_date": doc_date,
    })

    yield {"stage": "saved", "message": f"Saved document: {filename}", "pct": 10, "doc_id": doc_id}

    # Step 1: Cognee semantic indexing
    if _cognee_available:
        try:
            await cognee.add(content, dataset_name="petgraph")
            yield {"stage": "cognee_add", "message": "Added to Cognee index", "pct": 25}
            await asyncio.wait_for(cognee.cognify(), timeout=120)
            yield {"stage": "cognee_cognify", "message": "Cognee knowledge graph updated", "pct": 45}
        except Exception as e:
            yield {"stage": "cognee_warn", "message": f"Cognee indexing skipped: {e}", "pct": 45}
    else:
        yield {"stage": "cognee_skip", "message": "Cognee not available, using direct extraction", "pct": 45}

    # Step 2: Domain entity extraction (LLM)
    yield {"stage": "extracting", "message": "Extracting entities from document…", "pct": 50}
    try:
        entities = await extract_entities(content, doc_id)
    except Exception as e:
        yield {"stage": "error", "message": f"Entity extraction failed: {e}", "pct": 100}
        return

    yield {"stage": "extracted", "message": f"Found {sum(len(v) for v in entities.values() if isinstance(v, list))} entities", "pct": 65}

    # Step 3: Build graph nodes + edges
    yield {"stage": "graphing", "message": "Building knowledge graph…", "pct": 70}
    try:
        await _build_graph(entities, doc_id)
    except Exception as e:
        yield {"stage": "error", "message": f"Graph build failed: {e}", "pct": 100}
        return

    await db.mark_document_processed(doc_id)
    yield {"stage": "done", "message": "Document ingested ✓", "pct": 100, "doc_id": doc_id}


async def _build_graph(entities: dict, doc_id: str):
    existing_pets = await db.get_nodes_by_type("pet")

    # --- Owners ---
    owner_ids: dict[str, str] = {}
    for o in entities.get("owners", []):
        oid = f"owner_{normalize_name(o['name']).replace(' ', '_')}"
        await db.upsert_node({
            "id": oid,
            "type": "owner",
            "name": o["name"],
            "properties": {"phone": o.get("phone")},
            "source_doc_ids": [doc_id],
        })
        owner_ids[o["name"]] = oid

    # --- Providers (with entity resolution against existing nodes) ---
    existing_providers = await db.get_nodes_by_type("provider")
    extracted_providers = entities.get("providers", [])
    provider_mapping = resolve_providers(extracted_providers, existing_providers)

    provider_ids: dict[str, str] = {}
    for p in extracted_providers:
        pid = provider_mapping[p["name"]]
        await db.upsert_node({
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

    # --- Pets (with entity resolution) ---
    extracted_pets = entities.get("pets", [])
    # Attach owner info for fingerprinting
    for ep in extracted_pets:
        if owner_ids:
            ep["owner_name"] = next(iter(owner_ids))
    pet_mapping = resolve_pets(extracted_pets, existing_pets)

    for ep in extracted_pets:
        raw_name = ep.get("raw_name", ep.get("name", ""))
        pid_pet = pet_mapping[raw_name]
        existing = await db.get_node(pid_pet)
        aliases = []
        if existing:
            aliases = existing.get("properties", {}).get("aliases", [])
        if raw_name not in aliases:
            aliases.append(raw_name)

        await db.upsert_node({
            "id": pid_pet,
            "type": "pet",
            "name": ep.get("name", raw_name),
            "properties": {
                "species": ep.get("species"),
                "breed": ep.get("breed"),
                "sex": ep.get("sex"),
                "dob_approx": ep.get("dob_approx"),
                "weight_lbs": ep.get("weight_lbs"),
                "aliases": aliases,
                "owner_name": next(iter(owner_ids), None),
            },
            "source_doc_ids": [doc_id],
        })

        # Link pet ↔ owner
        if owner_ids:
            owner_id = next(iter(owner_ids.values()))
            await db.upsert_edge({
                "source_id": pid_pet, "target_id": owner_id,
                "relationship": "owned_by", "source_doc_id": doc_id,
            })

    def resolve_pet_id(raw_name: str) -> str | None:
        if not raw_name:
            return None
        for k, v in pet_mapping.items():
            if normalize_name(k) == normalize_name(raw_name):
                return v
        return None

    # --- Visits ---
    visit_ids: dict[str, str] = {}
    for v in entities.get("visits", []):
        pet_id = resolve_pet_id(v.get("pet_raw_name", ""))
        prov_id = provider_ids.get(v.get("provider_name", ""))
        vid = make_visit_node_id(v.get("date"), pet_id or "unknown", prov_id or "unknown")
        await db.upsert_node({
            "id": vid,
            "type": "visit",
            "name": f"Visit {v.get('date', 'undated')}",
            "properties": {
                "date": v.get("date"),
                "visit_type": v.get("type"),
                "chief_complaint": v.get("chief_complaint"),
                "provider_id": prov_id,
                "pet_id": pet_id,
            },
            "source_doc_ids": [doc_id],
        })
        key = f"{v.get('date')}_{v.get('pet_raw_name')}"
        visit_ids[key] = vid

        if pet_id:
            await db.upsert_edge({"source_id": pet_id, "target_id": vid, "relationship": "had_visit", "source_doc_id": doc_id})
        if prov_id:
            await db.upsert_edge({"source_id": vid, "target_id": prov_id, "relationship": "seen_at", "source_doc_id": doc_id})

    # --- Symptoms ---
    for s in entities.get("symptoms", []):
        pet_id = resolve_pet_id(s.get("pet_raw_name", ""))
        sid = make_symptom_node_id(s["name"])
        await db.upsert_node({
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
            await db.upsert_edge({
                "source_id": pet_id, "target_id": sid,
                "relationship": "has_symptom",
                "properties": {"date": s.get("date")},
                "source_doc_id": doc_id,
            })

    # --- Diagnoses ---
    for dx in entities.get("diagnoses", []):
        pet_id = resolve_pet_id(dx.get("pet_raw_name", ""))
        did_dx = make_diagnosis_node_id(dx["name"])
        await db.upsert_node({
            "id": did_dx,
            "type": "diagnosis",
            "name": dx["name"],
            "properties": {"date": dx.get("date"), "outcome": dx.get("outcome")},
            "source_doc_ids": [doc_id],
        })
        if pet_id:
            await db.upsert_edge({
                "source_id": pet_id, "target_id": did_dx,
                "relationship": "received_diagnosis",
                "properties": {"date": dx.get("date")},
                "source_doc_id": doc_id,
            })

    # --- Medications ---
    for med in entities.get("medications", []):
        pet_id = resolve_pet_id(med.get("pet_raw_name", ""))
        prov_id = provider_ids.get(med.get("prescriber_name", ""))
        med_id = make_medication_node_id(med["name"], med.get("rx_number"))
        await db.upsert_node({
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
            await db.upsert_edge({
                "source_id": pet_id, "target_id": med_id,
                "relationship": "prescribed",
                "properties": {"status": med.get("status"), "date": med.get("start_date")},
                "source_doc_id": doc_id,
            })
        if prov_id:
            rel = "discontinued_by" if med.get("status") == "discontinued" else "administered_by"
            await db.upsert_edge({
                "source_id": med_id, "target_id": prov_id,
                "relationship": rel,
                "source_doc_id": doc_id,
            })

    # --- Vaccines ---
    for vax in entities.get("vaccines", []):
        pet_id = resolve_pet_id(vax.get("pet_raw_name", ""))
        prov_id = provider_ids.get(vax.get("provider_name", ""))
        vax_id = make_vaccine_node_id(vax["name"], vax.get("date"), pet_id or "unknown")
        await db.upsert_node({
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
            await db.upsert_edge({
                "source_id": pet_id, "target_id": vax_id,
                "relationship": "received_vaccine",
                "properties": {"date": vax.get("date")},
                "source_doc_id": doc_id,
            })
        if prov_id:
            await db.upsert_edge({
                "source_id": vax_id, "target_id": prov_id,
                "relationship": "administered_by",
                "source_doc_id": doc_id,
            })
