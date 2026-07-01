import json
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from sse_starlette.sse import EventSourceResponse

from config import SEED_DOCS_DIR
from services.ingestion import ingest_document
from seed_graph import load_seed_graph
import database as db

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

DOC_META = {
    "01_groomer_march.txt":      {"doc_type": "groomer_note",  "provider_name": "Jenna K., Paws & Claws",              "doc_date": "2025-03-08"},
    "02_vet_june.txt":           {"doc_type": "vet_visit",     "provider_name": "Dr. Priya Singh, Westside Vet",       "doc_date": "2025-06-14"},
    "03_owner_note_august.txt":  {"doc_type": "owner_note",    "provider_name": None,                                   "doc_date": "2025-08-17"},
    "04_er_discharge_august.txt":{"doc_type": "er_discharge",  "provider_name": "Dr. Marcus Webb, Eastside Emergency", "doc_date": "2025-08-18"},
    "05_charlie_vet.txt":        {"doc_type": "vet_visit",     "provider_name": "Dr. Priya Singh, Westside Vet",       "doc_date": "2025-05-20"},
    "06_charlie_groomer.txt":    {"doc_type": "groomer_note",  "provider_name": "Jenna K., Paws & Claws",              "doc_date": "2025-04-05"},
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
    Load seed documents using a pre-computed graph (no LLM needed).
    Returns JSON on completion — no SSE needed for this fast operation.
    """
    await db.reset_db()
    events = await load_seed_graph(SEED_DOCS_DIR)
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()
    return {
        "message": "Seed graph loaded",
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


@router.delete("/reset")
async def reset():
    """Wipe all graph data and documents (dev only)."""
    await db.reset_db()
    return {"message": "Graph reset"}


@router.get("/documents")
async def list_documents():
    docs = await db.get_all_documents()
    return {"documents": docs}
