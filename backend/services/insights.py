"""
Proactive insights — inferred observations from analyzing the pet's own graph
over time, generated without a user query. Deterministic rules (no LLM), run
after ingestion/seed. Distinct from reminders (those are date-driven and
concrete); each insight carries a plain-language "why we flagged this".

Trust labeling: `source` is 'pet_records' when the flag comes purely from this
pet's history, and 'general_guideline' when it combines the pet's data with
standard veterinary practice (age milestones, checkup cadence). The two must
never blur together in the UI.
"""
import hashlib
from datetime import date

import database as db
from services import cognee_graph

SENIOR_AGE_YEARS_DOG = 7
SENIOR_AGE_YEARS_CAT = 10
CHECKUP_GAP_DAYS = 365
VACCINE_OVERDUE_GRACE_DAYS = 30


def _iid(*parts: str) -> str:
    return "ins_" + hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:12]


def _days_since(iso_date: str) -> int | None:
    try:
        y, m, d = (int(x) for x in iso_date[:10].split("-"))
        return (date.today() - date(y, m, d)).days
    except (ValueError, AttributeError):
        return None


async def generate_insights() -> int:
    graph = await cognee_graph.get_full_graph()
    nodes, edges = graph["nodes"], graph["links"]
    node_map = {n["id"]: n for n in nodes}
    pets = [n for n in nodes if n["type"] == "pet"]
    count = 0

    for pet in pets:
        count += await _recurring_patterns(pet, nodes, edges, node_map)
        count += await _overdue_vaccines(pet, edges, node_map)
        count += await _checkup_gap(pet, edges, node_map)
        count += await _life_stage(pet)

    return count


async def _recurring_patterns(pet, nodes, edges, node_map) -> int:
    """Same symptom/condition appearing on multiple distinct dates — a pattern
    no single visit shows; worth raising with a vet as possibly chronic."""
    count = 0

    # collect dated symptom occurrences per symptom node
    occurrences: dict[str, set[str]] = {}
    for e in edges:
        if e["source"] == pet["id"] and e["relationship"] == "has_symptom":
            sym = node_map.get(e["target"])
            if not sym:
                continue
            d = e.get("properties", {}).get("date") or sym.get("properties", {}).get("date")
            if d:
                occurrences.setdefault(sym["id"], set()).add(d[:10])

    # merge symptoms that are marked as the same condition
    same_condition: dict[str, str] = {}
    for e in edges:
        if e["relationship"] == "same_condition_as":
            root = same_condition.get(e["source"], e["source"])
            same_condition[e["target"]] = root
    merged: dict[str, set[str]] = {}
    for sid, dates in occurrences.items():
        root = same_condition.get(sid, sid)
        merged.setdefault(root, set()).update(dates)

    for sid, dates in merged.items():
        if len(dates) < 2:
            continue
        sym = node_map.get(sid)
        if not sym:
            continue
        span = sorted(dates)
        # find a diagnosis that explains it, if any
        dx = next(
            (node_map[e["source"]] for e in edges
             if e["target"] == sid and e["relationship"] == "explains_symptom"
             and e["source"] in node_map),
            None,
        )
        label = dx["name"] if dx else sym["name"]
        await db.upsert_insight({
            "id": _iid("recurring", pet["id"], sid),
            "pet_id": pet["id"],
            "pet_name": pet["name"],
            "kind": "recurring_pattern",
            "title": f"{label} keeps coming back for {pet['name']}",
            "body": f"Recorded on {len(span)} separate occasions ({span[0]} to {span[-1]}). "
                    "A repeating issue like this is worth discussing with your vet as possibly "
                    "chronic rather than treating each episode as one-off.",
            "why": "Flagged because the same problem appears in records from multiple visits "
                   "— a pattern only visible across the whole history.",
            "source": "pet_records",
        })
        count += 1
    return count


async def _overdue_vaccines(pet, edges, node_map) -> int:
    """A booster that should have happened by now (with grace period) but hasn't."""
    count = 0
    latest_by_name: dict[str, dict] = {}
    for e in edges:
        if e["source"] == pet["id"] and e["relationship"] == "received_vaccine":
            vax = node_map.get(e["target"])
            if not vax:
                continue
            base = vax["name"].lower().split()[0]
            cur = latest_by_name.get(base)
            if not cur or (vax.get("properties", {}).get("date") or "") > (cur.get("properties", {}).get("date") or ""):
                latest_by_name[base] = vax

    for base, vax in latest_by_name.items():
        due = vax.get("properties", {}).get("next_due")
        if not due:
            continue
        overdue_days = _days_since(due)
        if overdue_days is None or overdue_days < VACCINE_OVERDUE_GRACE_DAYS:
            continue
        await db.upsert_insight({
            "id": _iid("overdue_vax", pet["id"], base),
            "pet_id": pet["id"],
            "pet_name": pet["name"],
            "kind": "overdue_vaccine",
            "title": f"{vax['name']} booster looks overdue for {pet['name']}",
            "body": f"The records show it was due {due} — about {overdue_days} days ago — and no "
                    "newer dose has been recorded by any provider.",
            "why": "Flagged by comparing the recorded due date against every provider's records "
                   "in the graph, not just one clinic's file.",
            "source": "pet_records",
        })
        count += 1
    return count


async def _checkup_gap(pet, edges, node_map) -> int:
    """No vet visit in over a year → routine checkup suggestion."""
    vet_visit_dates = []
    for e in edges:
        if e["source"] == pet["id"] and e["relationship"] == "had_visit":
            v = node_map.get(e["target"])
            if v and v.get("properties", {}).get("visit_type") in ("vet", "er"):
                d = v.get("properties", {}).get("date")
                if d:
                    vet_visit_dates.append(d)
    if not vet_visit_dates:
        return 0
    last = max(vet_visit_dates)
    gap = _days_since(last)
    if gap is None or gap < CHECKUP_GAP_DAYS:
        return 0
    await db.upsert_insight({
        "id": _iid("checkup_gap", pet["id"]),
        "pet_id": pet["id"],
        "pet_name": pet["name"],
        "kind": "checkup_gap",
        "title": f"{pet['name']} hasn't seen a vet in over a year",
        "body": f"Last vet visit on record is {last} ({gap} days ago). An annual wellness check "
                "is standard practice, even when everything seems fine.",
        "why": "Flagged from this pet's own visit history combined with the standard "
               "annual-checkup guideline.",
        "source": "general_guideline",
    })
    return 1


async def _life_stage(pet) -> int:
    """Age/life-stage milestone with a standard action attached."""
    props = pet.get("properties", {})
    dob = props.get("dob_approx")
    species = (props.get("species") or "").lower()
    if not dob:
        return 0
    try:
        birth_year = int(str(dob)[:4])
    except ValueError:
        return 0
    age_years = date.today().year - birth_year
    senior_at = SENIOR_AGE_YEARS_CAT if species == "feline" else SENIOR_AGE_YEARS_DOG
    if age_years < senior_at:
        return 0
    await db.upsert_insight({
        "id": _iid("life_stage_senior", pet["id"]),
        "pet_id": pet["id"],
        "pet_name": pet["name"],
        "kind": "life_stage",
        "title": f"{pet['name']} is entering the senior years",
        "body": f"At roughly {age_years}, {'cats' if species == 'feline' else 'dogs'} benefit from "
                "twice-yearly checkups and age-appropriate bloodwork rather than the annual routine.",
        "why": "Based on the birth year in the records plus the standard senior-care guideline — "
               "not on anything specific in this pet's medical history.",
        "source": "general_guideline",
    })
    return 1
