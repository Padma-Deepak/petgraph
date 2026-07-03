from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import ingest, graph, query, conflicts, summary, reminders, insights

app = FastAPI(title="PetGraph API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(graph.router)
app.include_router(query.router)
app.include_router(conflicts.router)
app.include_router(summary.router)
app.include_router(reminders.router)
app.include_router(insights.router)


@app.on_event("startup")
async def startup():
    await init_db()
    from services.cognee_graph import detect_semantic_state
    await detect_semantic_state()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
