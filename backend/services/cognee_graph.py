"""
Cognee-owned knowledge graph layer.

Cognee's graph engine (Kuzu, embedded) is the single source of truth for the pet
health graph. This module is the only place that talks to the graph store:

  - seed loading writes the pre-computed graph directly via the engine's
    add_nodes/add_edges (no LLM required — preserves the key-free demo path)
  - all read paths (canvas, node detail, per-pet subgraph, conflict rules,
    pre-visit summary) query the Cognee graph, via adapter calls or Cypher
  - cognify() writes its semantic layer (chunks, entities, summaries) into the
    same graph; canvas endpoints filter to DOMAIN_TYPES, and the semantic layer
    is surfaced separately in the "How Cognee found this" drawer

SQLite is no longer a graph store — it keeps app bookkeeping only (documents,
reminders, insights).
"""
import json
import uuid

from config import DATA_DIR

# Node types that belong to the pet-health domain graph (shown on the canvas).
# Everything else in the store is Cognee's semantic layer (DocumentChunk,
# Entity, EntityType, TextSummary, ...) — queried by search, shown in the
# debug drawer, but not drawn as the pet graph.
DOMAIN_TYPES = {
    "pet", "owner", "provider", "visit",
    "symptom", "diagnosis", "medication", "vaccine",
}

_configured = False


def _configure():
    """Point Cognee's storage roots at DATA_DIR (works locally and in Docker)."""
    global _configured
    if _configured:
        return
    import cognee
    cognee.config.system_root_directory(str(DATA_DIR / ".cognee_system"))
    cognee.config.data_root_directory(str(DATA_DIR / ".cognee_data"))
    _configured = True


async def engine():
    """The Cognee graph engine (Kuzu adapter)."""
    _configure()
    from cognee.infrastructure.databases.graph import get_graph_engine
    return await get_graph_engine()


class _GraphNode:
    """Plain attribute bag: the adapter reads id/name/type via vars() and
    JSON-encodes every other attribute as the node's stored properties."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# ── writes ────────────────────────────────────────────────────────────────────

_RESERVED_KEYS = {"id", "name", "type", "properties", "source_doc_ids"}

# Cognee's cognify pipeline parses graph node IDs as UUIDs, so human-readable
# slugs break it. Node IDs are therefore deterministic UUIDv5 values derived
# from the slug (same slug → same UUID, so writes stay idempotent); the slug is
# kept as a property for readability/debugging.
_UUID_NS = uuid.uuid5(uuid.NAMESPACE_URL, "petgraph")

# node properties that reference other nodes by slug and need translating
_REF_KEYS = {"provider_id", "prescriber_id", "pet_id"}


def node_uid(slug_or_uuid: str) -> str:
    """Stable node UUID for a slug; already-UUID values pass through."""
    try:
        return str(uuid.UUID(slug_or_uuid))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(_UUID_NS, slug_or_uuid))


def _translate_props(props: dict) -> dict:
    return {
        k: (node_uid(v) if k in _REF_KEYS and v else v)
        for k, v in props.items()
    }


async def add_nodes(nodes: list[dict]) -> None:
    """Batch-insert app-format nodes ({id,type,name,properties,source_doc_ids}).

    Properties are stored flat: the adapter JSON-encodes every non-core attribute
    and, on read, merges that JSON back into the top level (dropping a literal
    "properties" key) — so nesting would be lost on round-trip.
    """
    eng = await engine()
    await eng.add_nodes([
        _GraphNode(
            id=node_uid(n["id"]),
            type=n["type"],
            name=n["name"],
            slug=n["id"],
            source_doc_ids=n.get("source_doc_ids", []),
            **{k: v for k, v in _translate_props(n.get("properties", {})).items()
               if k not in _RESERVED_KEYS},
        )
        for n in nodes
    ])


async def add_edges(edges: list[tuple[str, str, str, dict]]) -> None:
    """Batch-insert edges as (source_id, target_id, relationship, properties).
    Slug endpoints are translated to the stable node UUIDs."""
    eng = await engine()
    await eng.add_edges([
        (node_uid(src), node_uid(tgt), rel, props) for src, tgt, rel, props in edges
    ])


async def upsert_node(node: dict) -> str:
    """Insert a node, or merge properties/source_doc_ids into an existing one.

    The adapter's add_nodes only sets fields ON CREATE, so updates (e.g. a new
    alias or source document on an existing pet) go through an explicit SET.
    """
    uid = node_uid(node["id"])
    existing = await get_node(uid)
    if not existing:
        await add_nodes([node])
        return uid

    merged_props = {**existing.get("properties", {}), **node.get("properties", {})}
    aliases = set(existing.get("properties", {}).get("aliases") or [])
    aliases.update(node.get("properties", {}).get("aliases") or [])
    if aliases:
        merged_props["aliases"] = sorted(aliases)
    merged_sources = sorted(
        set(existing.get("source_doc_ids", [])) | set(node.get("source_doc_ids", []))
    )

    # Bind via UNWIND-map like the adapter's own writes: a bare top-level string
    # param in SET gets auto-parsed by Kuzu and stored as struct text, corrupting
    # the JSON; map-nested string params keep their exact value.
    eng = await engine()
    await eng.query(
        "UNWIND $rows AS row MATCH (n:Node) WHERE n.id = row.id "
        "SET n.name = row.name, n.properties = row.properties",
        {"rows": [{
            "id": uid,
            "name": node["name"],
            "properties": json.dumps({
                **{k: v for k, v in _translate_props(merged_props).items()
                   if k not in _RESERVED_KEYS},
                "source_doc_ids": merged_sources,
            }),
        }]},
    )
    return uid


async def reset() -> None:
    """Wipe the graph and vector stores (dev/demo reset)."""
    _configure()
    import cognee
    try:
        await cognee.prune.prune_data()
    except Exception:
        pass  # data root may not exist yet on first run
    await cognee.prune.prune_system(graph=True, vector=True, metadata=True)


# ── reads ─────────────────────────────────────────────────────────────────────

def _node_from_props(node_id: str, props: dict) -> dict:
    """Convert the adapter's (id, props) shape into the app node format."""
    inner = props.get("properties")
    if isinstance(inner, str):  # raw JSON string on some query paths
        try:
            inner = json.loads(inner)
        except (json.JSONDecodeError, TypeError):
            inner = {}
    if not isinstance(inner, dict):
        inner = {}
    # get_graph_data merges the stored JSON into the top-level props dict
    flat = {**{k: v for k, v in props.items() if k not in ("name", "type", "properties")},
            **inner}
    return {
        "id": node_id,
        "type": props.get("type", ""),
        "name": props.get("name", ""),
        "properties": {k: v for k, v in flat.items() if k != "source_doc_ids"},
        "source_doc_ids": flat.get("source_doc_ids") or [],
    }


def _edge_out(src: str, tgt: str, rel: str, props: dict) -> dict:
    props = props or {}
    return {
        "id": f"{src}|{rel}|{tgt}",
        "source": src,
        "target": tgt,
        "relationship": rel,
        "properties": {k: v for k, v in props.items() if k != "source_doc_id"},
        "source_doc_id": props.get("source_doc_id"),
    }


async def get_full_graph(domain_only: bool = True) -> dict:
    """All nodes + edges in app format ({nodes, links})."""
    eng = await engine()
    raw_nodes, raw_edges = await eng.get_graph_data()

    nodes = [_node_from_props(nid, props) for nid, props in raw_nodes]
    if domain_only:
        nodes = [n for n in nodes if n["type"] in DOMAIN_TYPES]
    node_ids = {n["id"] for n in nodes}

    links = [
        _edge_out(src, tgt, rel, props)
        for src, tgt, rel, props in raw_edges
        if src in node_ids and tgt in node_ids and rel != "SELF"
    ]
    return {"nodes": nodes, "links": links}


async def get_node(node_id: str) -> dict | None:
    eng = await engine()
    rows = await eng.query(
        "MATCH (n:Node) WHERE n.id = $id RETURN n.id, n.name, n.type, n.properties",
        {"id": node_uid(node_id)},
    )
    if not rows:
        return None
    nid, name, ntype, props_json = rows[0]
    return _node_from_props(str(nid), {
        "name": name, "type": ntype, "properties": props_json,
    })


async def get_nodes_by_type(node_type: str) -> list[dict]:
    eng = await engine()
    rows = await eng.query(
        "MATCH (n:Node) WHERE n.type = $t RETURN n.id, n.name, n.type, n.properties",
        {"t": node_type},
    )
    return [
        _node_from_props(str(r[0]), {"name": r[1], "type": r[2], "properties": r[3]})
        for r in rows
    ]


async def get_neighbors(node_id: str) -> list[dict]:
    """One-hop neighbors with the connecting relationship and direction."""
    eng = await engine()
    uid = node_uid(node_id)
    out_rows = await eng.query(
        "MATCH (n:Node)-[r:EDGE]->(m:Node) WHERE n.id = $id "
        "RETURN m.id, m.name, m.type, m.properties, r.relationship_name",
        {"id": uid},
    )
    in_rows = await eng.query(
        "MATCH (m:Node)-[r:EDGE]->(n:Node) WHERE n.id = $id "
        "RETURN m.id, m.name, m.type, m.properties, r.relationship_name",
        {"id": uid},
    )
    neighbors = []
    for rows, direction in ((out_rows, "out"), (in_rows, "in")):
        for r in rows:
            node = _node_from_props(str(r[0]), {
                "name": r[1], "type": r[2], "properties": r[3],
            })
            neighbors.append({**node, "via": r[4], "direction": direction})
    return neighbors


async def get_pet_subgraph(pet_id: str, max_hops: int = 4) -> dict:
    """Directed reach from a pet node, served by a Cognee graph query (Cypher on
    Kuzu). Follows edges source→target only, so two pets sharing an owner keep
    separate subgraphs — replaces the hand-rolled client-side BFS."""
    eng = await engine()
    pet_uid = node_uid(pet_id)
    reach_rows = await eng.query(
        f"MATCH (p:Node)-[:EDGE*1..{max_hops}]->(m:Node) "
        "WHERE p.id = $id RETURN DISTINCT m.id",
        {"id": pet_uid},
    )
    ids = {pet_uid} | {str(r[0]) for r in reach_rows}

    node_rows = await eng.query(
        "MATCH (n:Node) WHERE n.id IN $ids RETURN n.id, n.name, n.type, n.properties",
        {"ids": list(ids)},
    )
    nodes = [
        _node_from_props(str(r[0]), {"name": r[1], "type": r[2], "properties": r[3]})
        for r in node_rows
    ]
    nodes = [n for n in nodes if n["type"] in DOMAIN_TYPES]
    kept_ids = {n["id"] for n in nodes}

    edge_rows = await eng.query(
        "MATCH (n:Node)-[r:EDGE]->(m:Node) WHERE n.id IN $ids AND m.id IN $ids "
        "RETURN n.id, m.id, r.relationship_name, r.properties",
        {"ids": list(kept_ids)},
    )
    links = []
    for r in edge_rows:
        props = {}
        if r[3]:
            try:
                props = json.loads(r[3])
            except (json.JSONDecodeError, TypeError):
                props = {}
        links.append(_edge_out(str(r[0]), str(r[1]), str(r[2]), props))

    return {
        "nodes": nodes,
        "links": links,
        "query": {
            "engine": "cognee.graph (kuzu/cypher)",
            "cypher": f"MATCH (p:Node)-[:EDGE*1..{max_hops}]->(m) WHERE p.id = $id",
            "reached": len(kept_ids),
        },
    }


# ── semantic layer (vector store + cognify graph) ────────────────────────────

# Tracked so the UI's "How Cognee found this" drawer can say whether hybrid
# search is live, still indexing, or unavailable (no LLM key / error).
SEMANTIC_STATUS: dict = {"state": "empty", "docs_indexed": 0, "error": None}


async def index_documents_semantic(docs: list[dict]) -> None:
    """Add raw documents to Cognee and run cognify (embeddings + semantic graph).

    Requires an LLM/embedding key; failures degrade gracefully — the domain
    graph and rule-based features keep working, only hybrid search stays off.
    """
    _configure()
    import cognee
    SEMANTIC_STATUS.update(state="indexing", error=None)
    try:
        for doc in docs:
            await cognee.add(doc["content"], dataset_name="petgraph")
            SEMANTIC_STATUS["docs_indexed"] = SEMANTIC_STATUS.get("docs_indexed", 0) + 1
        await cognee.cognify(datasets="petgraph")
        SEMANTIC_STATUS["state"] = "ready"
    except Exception as e:  # no key, quota, network — demo must survive all
        SEMANTIC_STATUS.update(state="error", error=str(e)[:300])


def get_semantic_status() -> dict:
    return dict(SEMANTIC_STATUS)


async def detect_semantic_state() -> None:
    """Recover SEMANTIC_STATUS after a restart: the cognify output lives on
    disk, so if chunks are already indexed, hybrid search is ready even though
    this process never ran index_documents_semantic()."""
    if SEMANTIC_STATUS["state"] != "empty":
        return
    try:
        stats = await get_semantic_layer_stats()
        chunks = stats["semantic_nodes"].get("DocumentChunk", 0)
        if chunks:
            SEMANTIC_STATUS.update(state="ready", docs_indexed=chunks, error=None)
    except Exception:
        pass  # stay "empty" — status is informational only


async def get_semantic_layer_stats() -> dict:
    """Counts of Cognee's own cognify-produced nodes — for the debug drawer."""
    eng = await engine()
    rows = await eng.query(
        "MATCH (n:Node) RETURN n.type, count(n.id)", {},
    )
    counts = {str(r[0]): int(r[1]) for r in rows if r[0]}
    semantic = {t: c for t, c in counts.items() if t not in DOMAIN_TYPES}
    domain = {t: c for t, c in counts.items() if t in DOMAIN_TYPES}
    return {"domain_nodes": domain, "semantic_nodes": semantic}
