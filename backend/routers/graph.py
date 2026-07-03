from fastapi import APIRouter, HTTPException

import database as db
from services import cognee_graph

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
async def get_graph():
    """All domain nodes and links, served from Cognee's graph engine."""
    return await cognee_graph.get_full_graph()


@router.get("/cognee/status")
async def cognee_status():
    """Semantic-layer state + node counts — powers the 'How Cognee found this' drawer."""
    stats = await cognee_graph.get_semantic_layer_stats()
    return {**cognee_graph.get_semantic_status(), **stats}


@router.get("/node/{node_id}")
async def get_node(node_id: str):
    node = await cognee_graph.get_node(node_id)
    if not node or node["type"] not in cognee_graph.DOMAIN_TYPES:
        raise HTTPException(404, "Node not found")
    neighbors = await cognee_graph.get_neighbors(node_id)
    neighbors = [n for n in neighbors if n["type"] in cognee_graph.DOMAIN_TYPES]
    docs = await db.get_all_documents()
    doc_map = {d["id"]: d for d in docs}
    source_docs = [doc_map[did] for did in node.get("source_doc_ids", []) if did in doc_map]
    return {**node, "neighbors": neighbors, "source_documents": source_docs}


@router.get("/pets")
async def get_pets():
    return {"pets": await cognee_graph.get_nodes_by_type("pet")}


@router.get("/providers")
async def get_providers():
    return {"providers": await cognee_graph.get_nodes_by_type("provider")}


@router.get("/pet/{pet_id}/subgraph")
async def get_pet_subgraph(pet_id: str):
    """Per-pet subgraph via a Cognee graph query (directed Cypher traversal)."""
    pet = await cognee_graph.get_node(pet_id)
    if not pet or pet["type"] != "pet":
        raise HTTPException(404, "Pet not found")
    return await cognee_graph.get_pet_subgraph(pet_id)
