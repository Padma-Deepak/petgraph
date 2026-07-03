import json
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from sse_starlette.sse import EventSourceResponse

from config import SEED_DOCS_DIR
from services.ingestion import ingest_document
from services import cognee_graph
from seed_graph import load_seed_graph
import database as db

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

DOC_META = {
    "01_groomer_september.txt":     {"doc_type": "groomer_note", "provider_name": "Meera R., Furry Tales Pet Spa",              "doc_date": "2025-09-14"},
    "02_vet_december.txt":          {"doc_type": "vet_visit",    "provider_name": "Dr. Priya Nair, Sunshine Veterinary Clinic", "doc_date": "2025-12-06"},
    "03_owner_note_february.txt":   {"doc_type": "owner_note",   "provider_name": None,                                          "doc_date": "2026-02-16"},
    "04_er_discharge_february.txt": {"doc_type": "er_discharge", "provider_name": "Dr. Arjun Mehta, CityPets 24x7 Emergency",   "doc_date": "2026-02-17"},
    "05_charlie_vet.txt":           {"doc_type": "vet_visit",    "provider_name": "Dr. Priya Nair, Sunshine Veterinary Clinic", "doc_date": "2025-11-22"},
    "06_charlie_groomer.txt":       {"doc_type": "groomer_note", "provider_name": "Meera R., Furry Tales Pet Spa",              "doc_date": "2025-10-04"},
    "07_bella_followup_april.txt":  {"doc_type": "vet_visit",    "provider_name": "Dr. Priya Nair, Sunshine Veterinary Clinic", "doc_date": "2026-04-12"},
    "08_bella_derm_june.txt":       {"doc_type": "specialist",   "provider_name": "Dr. Kavita Rao, Bengaluru Veterinary Dermatology Centre", "doc_date": "2026-06-10"},
}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document and stream ingestion progress via SSE (uses LLM extraction)."""
    content = (await file.read()).decode("utf-8", errors="replace")
    meta = DOC_META.get(file.filename, {})

    async def event_stream():
        async for event in ingest_document(
            content=content,
            filename=file.filename,
            **meta,
        ):
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_stream())


@router.get("/seed")
async def seed_all():
    """
    Load seed documents using a pre-computed graph written directly into
    Cognee's graph engine (no LLM needed). Resets everything first.
    """
    await db.reset_db()
    await cognee_graph.reset()
    await load_seed_graph(SEED_DOCS_DIR)
    graph = await cognee_graph.get_full_graph()
    return {
        "message": "Seed graph loaded into Cognee",
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["links"]),
    }


@router.delete("/reset")
async def reset():
    """Wipe the Cognee graph/vector stores and app bookkeeping (dev only)."""
    await db.reset_db()
    await cognee_graph.reset()
    return {"message": "Graph reset"}


@router.get("/documents")
async def list_documents():
    docs = await db.get_all_documents()
    return {"documents": docs}
