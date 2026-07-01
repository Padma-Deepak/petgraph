from fastapi import APIRouter
from pydantic import BaseModel
from services.graph_service import symptom_query

router = APIRouter(prefix="/api/query", tags=["query"])


class SymptomQuery(BaseModel):
    text: str


@router.post("/symptom")
async def query_symptom(body: SymptomQuery):
    """
    Hybrid graph+vector symptom query.
    Returns traversal path, subgraph, longitudinal summary, and citations.
    """
    result = await symptom_query(body.text)
    return result
