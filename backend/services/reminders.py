"""
Reminders — date-driven, concrete follow-ups derived from the Cognee graph.
Deterministic (no LLM). Generated automatically after ingestion/seed; stored in
SQLite (app state, not pet memory). Dismissals survive re-generation because
reminder IDs are stable hashes of their identity.
"""
import hashlib
from datetime import date, timedelta

import database as db
from services import cognee_graph

# Fallback booster interval when a record has no explicit next-due date.
# Indian practice: annual boosters for the core vaccines.
DEFAULT_BOOSTER_DAYS = 365


def _rid(*parts: str) -> str:
    return "rem_" + hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:12]


def _vaccine_base_name(name: str) -> str:
    low = (name or "").lower()
    if "rabies" in low or "arv" in low:
        return "rabies"
    return low.split()[0] if low else ""


def _add_days(iso_date: str, days: int) -> str | None:
    try:
        y, m, d = (int(x) for x in iso_date[:10].split("-"))
        return (date(y, m, d) + timedelta(days=days)).isoformat()
    except (ValueError, AttributeError):
        return None


async def generate_reminders() -> int:
    """Derive reminders from the current graph; returns how many are active."""
    graph = await cognee_graph.get_full_graph()
    nodes, edges = graph["nodes"], graph["links"]
    node_map = {n["id"]: n for n in nodes}

    pets = {n["id"]: n for n in nodes if n["type"] == "pet"}
    count = 0

    # ── vaccine boosters: latest dose per (pet, vaccine) → next due ──────────
    pet_vaccines: dict[str, list[dict]] = {}
    for e in edges:
        if e["relationship"] == "received_vaccine" and e["source"] in pets:
            vax = node_map.get(e["target"])
            if vax:
                pet_vaccines.setdefault(e["source"], []).append(vax)

    for pet_id, vaxes in pet_vaccines.items():
        latest_by_name: dict[str, dict] = {}
        for vax in vaxes:
            base = _vaccine_base_name(vax["name"])
            cur = latest_by_name.get(base)
            if not cur or (vax.get("properties", {}).get("date") or "") > (cur.get("properties", {}).get("date") or ""):
                latest_by_name[base] = vax

        for base, vax in latest_by_name.items():
            props = vax.get("properties", {})
            due = props.get("next_due") or (
                _add_days(props.get("date") or "", DEFAULT_BOOSTER_DAYS) if props.get("date") else None
            )
            if not due:
                continue
            pet = pets[pet_id]
            await db.upsert_reminder({
                "id": _rid("vaccine", pet_id, base),
                "pet_id": pet_id,
                "pet_name": pet["name"],
                "kind": "vaccine_due",
                "title": f"{vax['name']} booster due for {pet['name']}",
                "details": f"Last dose {props.get('date', 'unknown')}."
                           + (f" Recorded next-due {props['next_due']}." if props.get("next_due") else
                              " Due date estimated from the annual booster schedule."),
                "due_date": due,
                "source_node_id": vax["id"],
            })
            count += 1

    # ── follow-up appointments mentioned in visit records ─────────────────────
    for n in nodes:
        if n["type"] != "visit":
            continue
        props = n.get("properties", {})
        fup = props.get("follow_up_date")
        if not fup:
            continue
        pet = pets.get(props.get("pet_id") or "")
        provider = node_map.get(props.get("provider_id") or "")
        # skip if a later visit with the same provider already happened
        satisfied = any(
            m["type"] == "visit"
            and m.get("properties", {}).get("provider_id") == props.get("provider_id")
            and (m.get("properties", {}).get("date") or "") >= fup
            for m in nodes if m["id"] != n["id"]
        )
        if satisfied:
            continue
        await db.upsert_reminder({
            "id": _rid("follow_up", n["id"]),
            "pet_id": pet["id"] if pet else None,
            "pet_name": pet["name"] if pet else None,
            "kind": "follow_up",
            "title": f"Follow-up visit for {pet['name'] if pet else 'your pet'}"
                     + (f" with {provider['name']}" if provider else ""),
            "details": f"Recheck requested at the {props.get('date', '')} visit"
                       + (f" ({props.get('chief_complaint')})" if props.get("chief_complaint") else "") + ".",
            "due_date": fup,
            "source_node_id": n["id"],
        })
        count += 1

    # ── medication course end / review dates ─────────────────────────────────
    for n in nodes:
        if n["type"] != "medication":
            continue
        props = n.get("properties", {})
        end = props.get("end_date")
        if not end or props.get("status") in ("discontinued", "completed"):
            continue
        pet_id = next((e["source"] for e in edges
                       if e["target"] == n["id"] and e["relationship"] == "prescribed"), None)
        pet = pets.get(pet_id or "")
        await db.upsert_reminder({
            "id": _rid("med_end", n["id"]),
            "pet_id": pet_id,
            "pet_name": pet["name"] if pet else None,
            "kind": "medication_end",
            "title": f"{n['name']} course ends — review needed",
            "details": f"Course for {pet['name'] if pet else 'your pet'} ends {end}. "
                       "Check with the prescribing vet whether to stop, refill, or re-evaluate.",
            "due_date": end,
            "source_node_id": n["id"],
        })
        count += 1

    return count
