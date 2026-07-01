"""
Pre-computed graph for the 6 Bella/Charlie seed documents.
Loaded directly into SQLite without LLM extraction.
This guarantees the demo works regardless of API key availability
while keeping the LLM extraction path live for uploaded documents.
"""
import database as db

# ── Canonical node definitions ────────────────────────────────────────────────

NODES = [
    # Owners
    {"id": "owner_sarah_mitchell", "type": "owner", "name": "Sarah Mitchell",
     "properties": {"phone": "555-234-7890"},
     "source_doc_ids": ["doc_seed_01", "doc_seed_02", "doc_seed_03", "doc_seed_04", "doc_seed_05", "doc_seed_06"]},

    # Pets
    {"id": "pet_canine_bella", "type": "pet", "name": "Bella",
     "properties": {
         "species": "canine", "breed": "Golden Retriever", "sex": "female",
         "dob_approx": "2022", "weight_lbs": 62,
         # Entity resolution: 3 different names across documents → 1 node
         "aliases": ["Bella", "Bella M.", "Patient #4471, canine, female, golden retriever"],
         "owner_name": "Sarah Mitchell",
     },
     "source_doc_ids": ["doc_seed_01", "doc_seed_02", "doc_seed_03", "doc_seed_04"]},

    {"id": "pet_feline_charlie", "type": "pet", "name": "Charlie",
     "properties": {
         "species": "feline", "breed": "Domestic Shorthair", "sex": "male",
         "dob_approx": "2021", "weight_lbs": 11.2,
         "aliases": ["Charlie"],
         "owner_name": "Sarah Mitchell",
     },
     "source_doc_ids": ["doc_seed_05", "doc_seed_06"]},

    # Providers
    {"id": "provider_paws_claws_jenna", "type": "provider", "name": "Jenna K.",
     "properties": {"clinic": "Paws & Claws Grooming Studio", "provider_type": "groomer"},
     "source_doc_ids": ["doc_seed_01", "doc_seed_06"]},

    {"id": "provider_westside_singh", "type": "provider", "name": "Dr. Priya Singh",
     "properties": {"clinic": "Westside Veterinary Clinic", "provider_type": "vet"},
     "source_doc_ids": ["doc_seed_02", "doc_seed_05"]},

    {"id": "provider_eastside_webb", "type": "provider", "name": "Dr. Marcus Webb",
     "properties": {"clinic": "Eastside Animal Emergency Center", "provider_type": "er"},
     "source_doc_ids": ["doc_seed_04"]},

    # Visits — Bella
    {"id": "visit_bella_groomer_march", "type": "visit", "name": "Visit 2025-03-08",
     "properties": {"date": "2025-03-08", "visit_type": "groomer",
                    "chief_complaint": "Routine grooming; ear scratching noted",
                    "provider_id": "provider_paws_claws_jenna", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_01"]},

    {"id": "visit_bella_vet_june", "type": "visit", "name": "Visit 2025-06-14",
     "properties": {"date": "2025-06-14", "visit_type": "vet",
                    "chief_complaint": "Persistent ear scratching, left ear, ~3 months",
                    "provider_id": "provider_westside_singh", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_02"]},

    {"id": "visit_bella_owner_aug", "type": "visit", "name": "Owner Note 2025-08-17",
     "properties": {"date": "2025-08-17", "visit_type": "owner_note",
                    "chief_complaint": "Head shaking, ear rubbing, restlessness",
                    "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_03"]},

    {"id": "visit_bella_er_aug", "type": "visit", "name": "ER Visit 2025-08-18",
     "properties": {"date": "2025-08-18", "visit_type": "er",
                    "chief_complaint": "Bilateral ear scratching, head shaking x 3 days",
                    "provider_id": "provider_eastside_webb", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_04"]},

    # Visits — Charlie
    {"id": "visit_charlie_vet_may", "type": "visit", "name": "Visit 2025-05-20",
     "properties": {"date": "2025-05-20", "visit_type": "vet",
                    "chief_complaint": "Annual wellness exam",
                    "provider_id": "provider_westside_singh", "pet_id": "pet_feline_charlie"},
     "source_doc_ids": ["doc_seed_05"]},

    {"id": "visit_charlie_groomer_apr", "type": "visit", "name": "Visit 2025-04-05",
     "properties": {"date": "2025-04-05", "visit_type": "groomer",
                    "chief_complaint": "Routine grooming",
                    "provider_id": "provider_paws_claws_jenna", "pet_id": "pet_feline_charlie"},
     "source_doc_ids": ["doc_seed_06"]},

    # Symptoms
    {"id": "sym_ear_scratching", "type": "symptom", "name": "Ear scratching",
     "properties": {"description": "Dog scratching at ear, head-shy during grooming",
                    "ear_side": "left", "date": "2025-03-08"},
     "source_doc_ids": ["doc_seed_01"]},

    {"id": "sym_head_shaking", "type": "symptom", "name": "Head shaking",
     "properties": {"description": "Head shaking and face rubbing on carpet; bilateral involvement",
                    "ear_side": "bilateral", "date": "2025-08-17"},
     "source_doc_ids": ["doc_seed_03", "doc_seed_04"]},

    # Diagnoses
    {"id": "dx_otitis_externa", "type": "diagnosis", "name": "Otitis externa",
     "properties": {"date": "2025-06-14", "outcome": "resolved (June), recurrent (August)"},
     "source_doc_ids": ["doc_seed_02", "doc_seed_04"]},

    # Medications — CONFLICT: Zymox Otic discontinued by Westside, listed active by ER
    {"id": "med_WVC20250614B", "type": "medication", "name": "Zymox Otic",
     "properties": {
         "dose": "5-6 drops, left ear, once daily",
         "frequency": "once daily x 14 days",
         "start_date": "2025-06-14",
         "end_date": "2025-07-05",
         "status": "discontinued",
         "rx_number": "WVC-2025-0614-B",
         "prescriber_id": "provider_westside_singh",
     },
     "source_doc_ids": ["doc_seed_02"]},

    {"id": "med_EAEC20250818Z", "type": "medication", "name": "Zymox Otic",
     "properties": {
         "dose": "unknown",
         "status": "uncertain",  # ← ER listed as "potentially active"
         "start_date": "2025-08-18",
         "prescriber_id": "provider_eastside_webb",
         "note": "ER listed as potentially active — owner unable to confirm discontinuation",
     },
     "source_doc_ids": ["doc_seed_04"]},

    {"id": "med_EAEC20250818M", "type": "medication", "name": "Mometamax Otic",
     "properties": {
         "dose": "4 drops per affected ear, twice daily",
         "frequency": "BID x 7 days",
         "start_date": "2025-08-18",
         "status": "prescribed",
         "rx_number": "EAEC-2025-0818-1",
         "prescriber_id": "provider_eastside_webb",
     },
     "source_doc_ids": ["doc_seed_04"]},

    {"id": "med_EAEC20250818A", "type": "medication", "name": "Apoquel",
     "properties": {
         "dose": "16mg, 1 tablet",
         "frequency": "BID x 5 days then SID x 14 days",
         "start_date": "2025-08-18",
         "status": "prescribed",
         "rx_number": "EAEC-2025-0818-2",
         "prescriber_id": "provider_eastside_webb",
     },
     "source_doc_ids": ["doc_seed_04"]},

    # Vaccines — CONFLICT: ER administered rabies on 2025-08-18, not in Westside records
    {"id": "vax_bella_rabies_2023", "type": "vaccine", "name": "Rabies",
     "properties": {"date": "2023-05-10", "next_due": "2026-05-10",
                    "provider_id": "provider_westside_singh"},
     "source_doc_ids": ["doc_seed_02"]},

    {"id": "vax_bella_rabies_er2025", "type": "vaccine", "name": "Rabies",
     "properties": {
         "date": "2025-08-18", "next_due": "2028-08-18",
         "lot": "238-177-A", "tag": "ER-4471-RAB-25",
         "provider_id": "provider_eastside_webb",
         "note": "Administered at ER — NOT yet recorded in Westside Vet records",
     },
     "source_doc_ids": ["doc_seed_04"]},

    # Charlie vaccines
    {"id": "vax_charlie_fvrcp_2025", "type": "vaccine", "name": "FVRCP",
     "properties": {"date": "2025-05-20", "next_due": "2028-05-20",
                    "provider_id": "provider_westside_singh"},
     "source_doc_ids": ["doc_seed_05"]},

    {"id": "vax_charlie_rabies_2025", "type": "vaccine", "name": "Rabies",
     "properties": {"date": "2025-05-20", "next_due": "2026-05-20",
                    "provider_id": "provider_westside_singh"},
     "source_doc_ids": ["doc_seed_05"]},
]


EDGES = [
    # Owner ↔ pets
    ("pet_canine_bella", "owner_sarah_mitchell", "owned_by", "doc_seed_01"),
    ("pet_feline_charlie", "owner_sarah_mitchell", "owned_by", "doc_seed_05"),

    # Bella → visits
    ("pet_canine_bella", "visit_bella_groomer_march", "had_visit", "doc_seed_01"),
    ("pet_canine_bella", "visit_bella_vet_june",      "had_visit", "doc_seed_02"),
    ("pet_canine_bella", "visit_bella_owner_aug",     "had_visit", "doc_seed_03"),
    ("pet_canine_bella", "visit_bella_er_aug",        "had_visit", "doc_seed_04"),

    # Charlie → visits
    ("pet_feline_charlie", "visit_charlie_vet_may",     "had_visit", "doc_seed_05"),
    ("pet_feline_charlie", "visit_charlie_groomer_apr", "had_visit", "doc_seed_06"),

    # Visits → providers
    ("visit_bella_groomer_march", "provider_paws_claws_jenna",   "seen_at", "doc_seed_01"),
    ("visit_bella_vet_june",      "provider_westside_singh",     "seen_at", "doc_seed_02"),
    ("visit_bella_er_aug",        "provider_eastside_webb",      "seen_at", "doc_seed_04"),
    ("visit_charlie_vet_may",     "provider_westside_singh",     "seen_at", "doc_seed_05"),
    ("visit_charlie_groomer_apr", "provider_paws_claws_jenna",   "seen_at", "doc_seed_06"),

    # Bella → symptoms
    ("pet_canine_bella", "sym_ear_scratching", "has_symptom", "doc_seed_01"),
    ("pet_canine_bella", "sym_head_shaking",   "has_symptom", "doc_seed_03"),

    # Symptoms linked across visits (same_condition_as)
    ("sym_ear_scratching", "sym_head_shaking", "same_condition_as", "doc_seed_03"),

    # Bella → diagnoses
    ("pet_canine_bella", "dx_otitis_externa", "received_diagnosis", "doc_seed_02"),

    # Diagnosis ↔ symptoms
    ("dx_otitis_externa", "sym_ear_scratching", "explains_symptom", "doc_seed_02"),
    ("dx_otitis_externa", "sym_head_shaking",   "explains_symptom", "doc_seed_04"),

    # Bella → medications
    ("pet_canine_bella", "med_WVC20250614B",  "prescribed", "doc_seed_02"),
    ("pet_canine_bella", "med_EAEC20250818Z", "prescribed", "doc_seed_04"),
    ("pet_canine_bella", "med_EAEC20250818M", "prescribed", "doc_seed_04"),
    ("pet_canine_bella", "med_EAEC20250818A", "prescribed", "doc_seed_04"),

    # Diagnosis → medications
    ("dx_otitis_externa", "med_WVC20250614B",  "treated_with", "doc_seed_02"),
    ("dx_otitis_externa", "med_EAEC20250818M", "treated_with", "doc_seed_04"),

    # Medications → providers (administered_by / discontinued_by)
    ("med_WVC20250614B",  "provider_westside_singh",   "discontinued_by", "doc_seed_02"),  # ← CONFLICT key
    ("med_EAEC20250818Z", "provider_eastside_webb",    "administered_by", "doc_seed_04"),  # ← CONFLICT key
    ("med_EAEC20250818M", "provider_eastside_webb",    "administered_by", "doc_seed_04"),
    ("med_EAEC20250818A", "provider_eastside_webb",    "administered_by", "doc_seed_04"),

    # Visits follow-up chain
    ("visit_bella_er_aug", "visit_bella_vet_june", "follow_up_to", "doc_seed_04"),

    # Bella → vaccines
    ("pet_canine_bella", "vax_bella_rabies_2023",   "received_vaccine", "doc_seed_02"),
    ("pet_canine_bella", "vax_bella_rabies_er2025", "received_vaccine", "doc_seed_04"),

    # Vaccines → providers
    ("vax_bella_rabies_2023",   "provider_westside_singh", "administered_by", "doc_seed_02"),
    ("vax_bella_rabies_er2025", "provider_eastside_webb",  "administered_by", "doc_seed_04"),  # ← CONFLICT key

    # Charlie vaccines
    ("pet_feline_charlie", "vax_charlie_fvrcp_2025",  "received_vaccine", "doc_seed_05"),
    ("pet_feline_charlie", "vax_charlie_rabies_2025", "received_vaccine", "doc_seed_05"),
    ("vax_charlie_fvrcp_2025",  "provider_westside_singh", "administered_by", "doc_seed_05"),
    ("vax_charlie_rabies_2025", "provider_westside_singh", "administered_by", "doc_seed_05"),
]

SEED_DOCUMENTS = [
    {"id": "doc_seed_01", "filename": "01_groomer_march.txt",       "doc_type": "groomer_note",  "provider_name": "Jenna K., Paws & Claws", "doc_date": "2025-03-08"},
    {"id": "doc_seed_02", "filename": "02_vet_june.txt",            "doc_type": "vet_visit",     "provider_name": "Dr. Priya Singh, Westside Vet", "doc_date": "2025-06-14"},
    {"id": "doc_seed_03", "filename": "03_owner_note_august.txt",   "doc_type": "owner_note",    "provider_name": None, "doc_date": "2025-08-17"},
    {"id": "doc_seed_04", "filename": "04_er_discharge_august.txt", "doc_type": "er_discharge",  "provider_name": "Dr. Marcus Webb, Eastside Emergency", "doc_date": "2025-08-18"},
    {"id": "doc_seed_05", "filename": "05_charlie_vet.txt",         "doc_type": "vet_visit",     "provider_name": "Dr. Priya Singh, Westside Vet", "doc_date": "2025-05-20"},
    {"id": "doc_seed_06", "filename": "06_charlie_groomer.txt",     "doc_type": "groomer_note",  "provider_name": "Jenna K., Paws & Claws", "doc_date": "2025-04-05"},
]


async def load_seed_graph(seed_docs_dir) -> list[dict]:
    """
    Load all seed documents into the DB and build the pre-computed graph.
    Yields progress dicts.
    """
    events = []

    # Save document records with actual content
    from pathlib import Path
    for doc_meta in SEED_DOCUMENTS:
        path = Path(seed_docs_dir) / doc_meta["filename"]
        content = path.read_text(encoding="utf-8") if path.exists() else "(content not found)"
        await db.save_document({**doc_meta, "content": content})
        await db.mark_document_processed(doc_meta["id"])
        events.append({"stage": "saved", "message": f"Saved {doc_meta['filename']}", "pct": 10,
                        "file": doc_meta["filename"]})

    # Insert nodes
    for i, node in enumerate(NODES):
        await db.upsert_node(node)
        pct = 20 + int(50 * i / len(NODES))
        events.append({"stage": "node", "message": f"Node: {node['name']} ({node['type']})", "pct": pct,
                        "file": "graph"})

    # Insert edges
    for i, (src, tgt, rel, doc) in enumerate(EDGES):
        await db.upsert_edge({"source_id": src, "target_id": tgt, "relationship": rel, "source_doc_id": doc})
        pct = 70 + int(25 * i / len(EDGES))
        events.append({"stage": "edge", "message": f"Edge: {src[-12:]} → {rel} → {tgt[-12:]}", "pct": pct,
                        "file": "graph"})

    events.append({"stage": "done", "message": f"Seed graph loaded: {len(NODES)} nodes, {len(EDGES)} edges", "pct": 100})
    return events
