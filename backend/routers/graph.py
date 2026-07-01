from fastapi import APIRouter, HTTPException
import database as db

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
async def get_graph():
    """All nodes and links for react-force-graph."""
    nodes = await db.get_all_nodes()
    edges = await db.get_all_edges()
    return {
        "nodes": nodes,
        "links": [_edge_to_link(e) for e in edges],
    }


@router.get("/node/{node_id}")
async def get_node(node_id: str):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    neighbors = await db.get_adjacent(node_id)
    docs = await db.get_all_documents()
    doc_map = {d["id"]: d for d in docs}
    source_docs = [doc_map[did] for did in node.get("source_doc_ids", []) if did in doc_map]
    return {**node, "neighbors": neighbors, "source_documents": source_docs}


@router.get("/pets")
async def get_pets():
    pets = await db.get_nodes_by_type("pet")
    return {"pets": pets}


@router.get("/providers")
async def get_providers():
    providers = await db.get_nodes_by_type("provider")
    return {"providers": providers}


def _edge_to_link(e: dict) -> dict:
    return {
        "id": e["id"],
        "source": e["source"],
        "target": e["target"],
        "relationship": e["relationship"],
        "properties": e.get("properties", {}),
        "source_doc_id": e.get("source_doc_id"),
    }
