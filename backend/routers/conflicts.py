from fastapi import APIRouter
from services.conflict_detector import detect_conflicts

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


@router.get("")
async def get_conflicts():
    """Deterministic rule-based conflict detection — no LLM involved."""
    conflicts = await detect_conflicts()
    return {"conflicts": conflicts, "count": len(conflicts)}
