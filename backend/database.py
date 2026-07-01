import aiosqlite
import json
import uuid
from pathlib import Path
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                doc_type TEXT,
                provider_name TEXT,
                doc_date TEXT,
                processed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                properties TEXT NOT NULL DEFAULT '{}',
                source_doc_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                properties TEXT NOT NULL DEFAULT '{}',
                source_doc_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


async def get_all_nodes() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM nodes ORDER BY created_at") as cur:
            rows = await cur.fetchall()
    return [_node_row(r) for r in rows]


async def get_all_edges() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM edges ORDER BY created_at") as cur:
            rows = await cur.fetchall()
    return [_edge_row(r) for r in rows]


async def get_node(node_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)) as cur:
            row = await cur.fetchone()
    return _node_row(row) if row else None


async def get_nodes_by_type(node_type: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM nodes WHERE type = ?", (node_type,)) as cur:
            rows = await cur.fetchall()
    return [_node_row(r) for r in rows]


async def upsert_node(node: dict) -> str:
    nid = node["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT properties, source_doc_ids FROM nodes WHERE id = ?", (nid,)) as cur:
            existing = await cur.fetchone()
        if existing:
            old_props = json.loads(existing["properties"])
            old_sources = json.loads(existing["source_doc_ids"])
            merged_props = {**old_props, **node.get("properties", {})}
            # keep aliases list merged
            old_aliases = old_props.get("aliases", [])
            new_aliases = node.get("properties", {}).get("aliases", [])
            merged_props["aliases"] = list(set(old_aliases + new_aliases))
            merged_sources = list(set(old_sources + node.get("source_doc_ids", [])))
            await db.execute(
                "UPDATE nodes SET properties=?, source_doc_ids=?, name=? WHERE id=?",
                (json.dumps(merged_props), json.dumps(merged_sources), node["name"], nid),
            )
        else:
            await db.execute(
                "INSERT INTO nodes (id, type, name, properties, source_doc_ids) VALUES (?,?,?,?,?)",
                (
                    nid,
                    node["type"],
                    node["name"],
                    json.dumps(node.get("properties", {})),
                    json.dumps(node.get("source_doc_ids", [])),
                ),
            )
        await db.commit()
    return nid


async def upsert_edge(edge: dict) -> str:
    eid = edge.get("id") or f"e_{uuid.uuid4().hex[:10]}"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM edges WHERE source_id=? AND target_id=? AND relationship=?",
            (edge["source_id"], edge["target_id"], edge["relationship"]),
        ) as cur:
            existing = await cur.fetchone()
        if not existing:
            await db.execute(
                "INSERT INTO edges (id, source_id, target_id, relationship, properties, source_doc_id) VALUES (?,?,?,?,?,?)",
                (
                    eid,
                    edge["source_id"],
                    edge["target_id"],
                    edge["relationship"],
                    json.dumps(edge.get("properties", {})),
                    edge.get("source_doc_id"),
                ),
            )
            await db.commit()
    return eid


async def get_adjacent(node_id: str) -> list[dict]:
    """Return all nodes reachable from node_id in one hop (any direction)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        result = []
        async with db.execute(
            "SELECT e.relationship, e.source_doc_id, n.* "
            "FROM edges e JOIN nodes n ON n.id = e.target_id "
            "WHERE e.source_id = ?", (node_id,)
        ) as cur:
            for row in await cur.fetchall():
                result.append({**_node_row(row), "via": row["relationship"], "direction": "out"})
        async with db.execute(
            "SELECT e.relationship, e.source_doc_id, n.* "
            "FROM edges e JOIN nodes n ON n.id = e.source_id "
            "WHERE e.target_id = ?", (node_id,)
        ) as cur:
            for row in await cur.fetchall():
                result.append({**_node_row(row), "via": row["relationship"], "direction": "in"})
    return result


async def get_document(doc_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_all_documents() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM documents ORDER BY created_at") as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def save_document(doc: dict) -> str:
    did = doc.get("id") or f"doc_{uuid.uuid4().hex[:10]}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO documents (id, filename, content, doc_type, provider_name, doc_date) VALUES (?,?,?,?,?,?)",
            (did, doc["filename"], doc["content"], doc.get("doc_type"), doc.get("provider_name"), doc.get("doc_date")),
        )
        await db.commit()
    return did


async def mark_document_processed(doc_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE documents SET processed=1 WHERE id=?", (doc_id,))
        await db.commit()


async def reset_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("DELETE FROM edges; DELETE FROM nodes; DELETE FROM documents;")
        await db.commit()


def _node_row(r) -> dict:
    return {
        "id": r["id"],
        "type": r["type"],
        "name": r["name"],
        "properties": json.loads(r["properties"]),
        "source_doc_ids": json.loads(r["source_doc_ids"]),
    }


def _edge_row(r) -> dict:
    return {
        "id": r["id"],
        "source": r["source_id"],
        "target": r["target_id"],
        "relationship": r["relationship"],
        "properties": json.loads(r["properties"]),
        "source_doc_id": r["source_doc_id"],
    }
