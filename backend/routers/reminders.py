from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import database as db
from services.reminders import generate_reminders

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class SnoozeBody(BaseModel):
    until: str  # ISO date


@router.get("")
async def list_reminders():
    reminders = await db.get_reminders()
    # un-snooze anything whose snooze window has passed
    from datetime import date
    today = date.today().isoformat()
    visible = []
    for r in reminders:
        if r["status"] == "snoozed" and (r.get("snoozed_until") or "") <= today:
            await db.set_reminder_status(r["id"], "open")
            r = {**r, "status": "open", "snoozed_until": None}
        if r["status"] == "open":
            visible.append(r)
    overdue = [r for r in visible if (r.get("due_date") or "9999") < today]
    return {"reminders": visible, "count": len(visible), "overdue_count": len(overdue)}


@router.post("/refresh")
async def refresh_reminders():
    count = await generate_reminders()
    return {"generated": count}


@router.post("/{reminder_id}/dismiss")
async def dismiss_reminder(reminder_id: str):
    await db.set_reminder_status(reminder_id, "dismissed")
    return {"status": "dismissed"}


@router.post("/{reminder_id}/snooze")
async def snooze_reminder(reminder_id: str, body: SnoozeBody):
    if not body.until:
        raise HTTPException(400, "until date required")
    await db.set_reminder_status(reminder_id, "snoozed", snoozed_until=body.until)
    return {"status": "snoozed", "until": body.until}
