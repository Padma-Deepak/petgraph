from fastapi import APIRouter, HTTPException
from services.graph_service import pre_visit_summary

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.get("/{provider_id}")
async def get_pre_visit_summary(provider_id: str):
    """Pre-visit summary: what changed since the pet's last visit with this provider."""
    result = await pre_visit_summary(provider_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result
