from fastapi import APIRouter
from pydantic import BaseModel
from services.graph_service import symptom_query

router = APIRouter(prefix="/api/query", tags=["query"])


class HistoryMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class SymptomQuery(BaseModel):
    text: str
    history: list[HistoryMessage] = []


@router.post("/symptom")
async def query_symptom(body: SymptomQuery):
    """
    Hybrid graph+vector symptom query with conversation history.
    Returns traversal path, subgraph, longitudinal summary, citations, and follow-up suggestions.
    """
    history = [{"role": m.role, "content": m.content} for m in body.history]
    result = await symptom_query(body.text, history=history)
    return result
