"""
Deterministic, rule-based conflict detection. NO LLM involved.
Reads nodes/edges from Cognee's graph (the single source of truth) and checks:
  1. Medication active at one provider but discontinued at another.
  2. Vaccine recorded at one provider but absent from another provider's records
     for the same pet within a relevant date window.

All logic is auditable graph-edge traversal — no probabilistic inference.
"""
from services import cognee_graph


async def detect_conflicts() -> list[dict]:
    graph = await cognee_graph.get_full_graph()
    nodes = graph["nodes"]
    edges = graph["links"]

    node_map = {n["id"]: n for n in nodes}
    conflicts: list[dict] = []

    conflicts += _medication_status_conflicts(node_map, edges)
    conflicts += _vaccine_missing_from_primary_vet(node_map, edges)

    return conflicts


# ── Rule 1: Medication active at one provider, discontinued at another ──────

def _medication_status_conflicts(node_map: dict, edges: list[dict]) -> list[dict]:
    conflicts = []
    med_nodes = [n for n in node_map.values() if n["type"] == "medication"]

    for med in med_nodes:
        # Find all edges involving this medication
        med_edges = [e for e in edges if e["source"] == med["id"] or e["target"] == med["id"]]

        # Collect all status records for this drug name (across prescriptions)
        same_drug_meds = [
            n for n in med_nodes
            if _drug_base_name(n["name"]) == _drug_base_name(med["name"])
        ]

        active_providers: list[dict] = []
        discontinued_providers: list[dict] = []

        for m in same_drug_meds:
            props = m.get("properties", {})
            status = props.get("status", "unknown")
            prov_id = props.get("prescriber_id")

            # Also check edges for administered_by / discontinued_by
            for e in edges:
                if e["source"] == m["id"]:
                    if e["relationship"] == "administered_by" and status in ("active", "prescribed", "uncertain"):
                        prov = node_map.get(e["target"])
                        if prov:
                            active_providers.append({
                                "provider": prov["name"],
                                "clinic": prov.get("properties", {}).get("clinic", ""),
                                "med_id": m["id"],
                                "source": m.get("source_doc_ids", []),
                                "date": props.get("start_date"),
                            })
                    elif e["relationship"] == "discontinued_by":
                        prov = node_map.get(e["target"])
                        if prov:
                            discontinued_providers.append({
                                "provider": prov["name"],
                                "clinic": prov.get("properties", {}).get("clinic", ""),
                                "med_id": m["id"],
                                "source": m.get("source_doc_ids", []),
                                "date": props.get("end_date"),
                            })

        if active_providers and discontinued_providers:
            # Avoid duplicate conflict reports
            conflict_key = f"med_{_drug_base_name(med['name'])}"
            if not any(c.get("conflict_key") == conflict_key for c in conflicts):
                ap = active_providers[0]
                dp = discontinued_providers[0]
                conflicts.append({
                    "conflict_key": conflict_key,
                    "type": "medication_status",
                    "severity": "high",
                    "medication": med["name"],
                    "description": (
                        f"{med['name']} is marked ACTIVE by {ap['provider']} ({ap['clinic']}) "
                        f"but DISCONTINUED by {dp['provider']} ({dp['clinic']}) on {dp['date'] or 'unknown date'}."
                    ),
                    "active_at": ap,
                    "discontinued_by": dp,
                    "suggested_question": (
                        f"Ask {dp['provider']} whether {med['name']} should still be continued — "
                        f"{ap['clinic']}'s record shows it as active, but {dp['clinic']} marked it "
                        f"discontinued{' on ' + dp['date'] if dp['date'] else ''}. "
                        f"Confirm which record is correct before refilling or discontinuing."
                    ),
                    "involved_nodes": list({ap["med_id"], dp["med_id"]}),
                })

    return conflicts


# ── Rule 2: Vaccine recorded at ER but missing from primary vet records ──────

def _vaccine_missing_from_primary_vet(node_map: dict, edges: list[dict]) -> list[dict]:
    conflicts = []

    vax_nodes = [n for n in node_map.values() if n["type"] == "vaccine"]
    provider_nodes = {n["id"]: n for n in node_map.values() if n["type"] == "provider"}

    # Group vaccines by pet
    pet_vaccines: dict[str, list[dict]] = {}
    for e in edges:
        if e["relationship"] == "received_vaccine" and e["source"] in node_map:
            pet_id = e["source"]
            vax = node_map.get(e["target"])
            if vax and node_map[pet_id]["type"] == "pet":
                pet_vaccines.setdefault(pet_id, []).append(vax)

    for pet_id, vax_list in pet_vaccines.items():
        # Group by vaccine base name (e.g. "Rabies")
        by_name: dict[str, list[dict]] = {}
        for vax in vax_list:
            base = _vaccine_base_name(vax["name"])
            by_name.setdefault(base, []).append(vax)

        for vax_base, records in by_name.items():
            if len(records) < 2:
                continue

            # Find which providers administered each
            providers_per_record: dict[str, dict] = {}
            for vax in records:
                for e in edges:
                    if e["source"] == vax["id"] and e["relationship"] == "administered_by":
                        prov = provider_nodes.get(e["target"])
                        if prov:
                            providers_per_record[vax["id"]] = prov

            # Find ER providers vs primary vets
            er_records = [
                vax for vax in records
                if providers_per_record.get(vax["id"], {}).get("properties", {}).get("provider_type") == "er"
            ]
            primary_records = [
                vax for vax in records
                if providers_per_record.get(vax["id"], {}).get("properties", {}).get("provider_type") == "vet"
            ]

            if er_records and primary_records:
                # Check if ER vaccine date is NEWER than the most recent primary vet record
                def vax_date(v):
                    return v.get("properties", {}).get("date") or "0000-00-00"

                latest_er = max(er_records, key=vax_date)
                latest_primary = max(primary_records, key=vax_date)

                if vax_date(latest_er) > vax_date(latest_primary):
                    er_prov = providers_per_record.get(latest_er["id"], {})
                    primary_prov = providers_per_record.get(latest_primary["id"], {})
                    pet = node_map.get(pet_id, {})

                    conflict_key = f"vax_{pet_id}_{vax_base}"
                    if not any(c.get("conflict_key") == conflict_key for c in conflicts):
                        conflicts.append({
                            "conflict_key": conflict_key,
                            "type": "vaccine_record_mismatch",
                            "severity": "medium",
                            "vaccine": vax_base,
                            "pet": pet.get("name", pet_id),
                            "description": (
                                f"{vax_base} vaccine was administered at {er_prov.get('name', 'ER')} "
                                f"on {vax_date(latest_er)}, but {primary_prov.get('name', 'primary vet')}'s "
                                f"records only show a prior dose from {vax_date(latest_primary)}. "
                                f"The ER vaccination has not been recorded in the primary vet's system."
                            ),
                            "er_record": {
                                "provider": er_prov.get("name"),
                                "date": vax_date(latest_er),
                                "source": latest_er.get("source_doc_ids", []),
                            },
                            "primary_record": {
                                "provider": primary_prov.get("name"),
                                "date": vax_date(latest_primary),
                                "source": latest_primary.get("source_doc_ids", []),
                            },
                            "suggested_question": (
                                f"Ask {primary_prov.get('name', 'your primary vet')} to update {pet.get('name', 'your pet')}'s "
                                f"records to include the {vax_base} booster administered at "
                                f"{er_prov.get('name', 'the emergency clinic')} on {vax_date(latest_er)}. "
                                f"Confirm whether any follow-up is needed given the updated vaccination date."
                            ),
                            "involved_nodes": [latest_er["id"], latest_primary["id"]],
                        })

    return conflicts


def _drug_base_name(name: str) -> str:
    """Normalize drug name for comparison (first significant word)."""
    return name.lower().split()[0] if name else ""


def _vaccine_base_name(name: str) -> str:
    """Normalize vaccine name (e.g. 'Rabies', 'FVRCP')."""
    first_word = name.lower().split()[0] if name else ""
    # Map common variants
    if "rabies" in name.lower():
        return "rabies"
    if "fvrcp" in name.lower() or "feline viral" in name.lower():
        return "fvrcp"
    return first_word
