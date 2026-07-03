from fastapi import APIRouter

import database as db
from services.insights import generate_insights

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("")
async def list_insights():
    insights = await db.get_insights()
    return {"insights": insights, "count": len(insights)}


@router.post("/refresh")
async def refresh_insights():
    count = await generate_insights()
    return {"generated": count}


@router.post("/{insight_id}/dismiss")
async def dismiss_insight(insight_id: str):
    await db.set_insight_status(insight_id, "dismissed")
    return {"status": "dismissed"}
