"""
App-level bookkeeping store (SQLite). The knowledge graph itself lives in
Cognee's graph engine (see services/cognee_graph.py) — this module only keeps
what is app state, not pet memory: documents, reminders, and insights.
"""
import aiosqlite
import uuid
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
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                pet_id TEXT,
                pet_name TEXT,
                kind TEXT NOT NULL,           -- vaccine_due | follow_up | medication_end
                title TEXT NOT NULL,
                details TEXT,
                due_date TEXT,
                source_node_id TEXT,
                status TEXT DEFAULT 'open',   -- open | dismissed | snoozed
                snoozed_until TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS insights (
                id TEXT PRIMARY KEY,
                pet_id TEXT,
                pet_name TEXT,
                kind TEXT NOT NULL,           -- overdue_vaccine | life_stage | recurring_pattern | checkup_gap
                title TEXT NOT NULL,
                body TEXT,
                why TEXT,                     -- plain-language "why we flagged this"
                source TEXT DEFAULT 'pet_records',  -- pet_records | breed_knowledge (trust label)
                status TEXT DEFAULT 'open',   -- open | dismissed
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        # Legacy tables from the pre-Cognee architecture (graph now lives in Cognee)
        await db.executescript("DROP TABLE IF EXISTS nodes; DROP TABLE IF EXISTS edges;")
        await db.commit()


# ── documents ─────────────────────────────────────────────────────────────────

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


# ── reminders ─────────────────────────────────────────────────────────────────

async def upsert_reminder(reminder: dict) -> str:
    """Insert a reminder; an existing row keeps its status (dismiss survives
    re-generation on the next ingestion pass)."""
    rid = reminder["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO reminders (id, pet_id, pet_name, kind, title, details, due_date, source_node_id)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, details=excluded.details, due_date=excluded.due_date""",
            (rid, reminder.get("pet_id"), reminder.get("pet_name"), reminder["kind"],
             reminder["title"], reminder.get("details"), reminder.get("due_date"),
             reminder.get("source_node_id")),
        )
        await db.commit()
    return rid


async def get_reminders(include_dismissed: bool = False) -> list[dict]:
    q = "SELECT * FROM reminders"
    if not include_dismissed:
        q += " WHERE status != 'dismissed'"
    q += " ORDER BY due_date IS NULL, due_date"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(q) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def set_reminder_status(reminder_id: str, status: str, snoozed_until: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reminders SET status=?, snoozed_until=? WHERE id=?",
            (status, snoozed_until, reminder_id),
        )
        await db.commit()


# ── insights ──────────────────────────────────────────────────────────────────

async def upsert_insight(insight: dict) -> str:
    rid = insight["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO insights (id, pet_id, pet_name, kind, title, body, why, source)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, body=excluded.body, why=excluded.why""",
            (rid, insight.get("pet_id"), insight.get("pet_name"), insight["kind"],
             insight["title"], insight.get("body"), insight.get("why"),
             insight.get("source", "pet_records")),
        )
        await db.commit()
    return rid


async def get_insights(include_dismissed: bool = False) -> list[dict]:
    q = "SELECT * FROM insights"
    if not include_dismissed:
        q += " WHERE status != 'dismissed'"
    q += " ORDER BY created_at DESC"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(q) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def set_insight_status(insight_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE insights SET status=? WHERE id=?", (status, insight_id))
        await db.commit()


async def reset_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("DELETE FROM documents; DELETE FROM reminders; DELETE FROM insights;")
        await db.commit()
