"""
Pre-computed graph for the 8 Bella/Charlie seed documents (Bengaluru, India).
Written directly into Cognee's graph engine (no LLM extraction needed), so the
demo works regardless of API key availability. When a key IS available, the
seed documents are additionally indexed into Cognee's semantic layer
(add + cognify) in the background to power hybrid search.

Timeline (today ≈ mid-2026):
  2025-09-14  groomer notes Bella's left-ear scratching            (doc 01)
  2025-12-06  Sunshine Vet: otitis externa dx, Surolan Rx          (doc 02)
  2026-02-16  owner note: both ears now, drops half-used           (doc 03)
  2026-02-17  CityPets ER: recurrent otitis, rabies booster        (doc 04)
  2026-04-12  Sunshine follow-up: ears resolved, new pruritus      (doc 07)
  2026-06-10  Dermatology: atopic dermatitis, immunotherapy        (doc 08)
  2025-10-04  Charlie grooming                                     (doc 06)
  2025-11-22  Charlie annual wellness; rabies DEFERRED (overdue!)  (doc 05)
"""
import database as db
from services import cognee_graph

# ── Canonical node definitions ────────────────────────────────────────────────

NODES = [
    # Owner
    {"id": "owner_ananya_sharma", "type": "owner", "name": "Ananya Sharma",
     "properties": {"phone": "+91 98450 12345"},
     "source_doc_ids": ["doc_seed_01", "doc_seed_02", "doc_seed_03", "doc_seed_04",
                        "doc_seed_05", "doc_seed_06", "doc_seed_07", "doc_seed_08"]},

    # Pets
    {"id": "pet_canine_bella", "type": "pet", "name": "Bella",
     "properties": {
         "species": "canine", "breed": "Golden Retriever", "sex": "female",
         "dob_approx": "2023", "weight_kg": 29.0,
         # Entity resolution: 3 different names across documents → 1 node
         "aliases": ["Bella", "Bella S.", "Patient #4471, canine, female, golden retriever"],
         "owner_name": "Ananya Sharma",
     },
     "source_doc_ids": ["doc_seed_01", "doc_seed_02", "doc_seed_03", "doc_seed_04",
                        "doc_seed_07", "doc_seed_08"]},

    {"id": "pet_feline_charlie", "type": "pet", "name": "Charlie",
     "properties": {
         "species": "feline", "breed": "Indian Domestic Shorthair (Indie)", "sex": "male",
         "dob_approx": "2016", "weight_kg": 5.1,
         "aliases": ["Charlie"],
         "owner_name": "Ananya Sharma",
     },
     "source_doc_ids": ["doc_seed_05", "doc_seed_06"]},

    # Providers
    {"id": "provider_furrytales_meera", "type": "provider", "name": "Meera R.",
     "properties": {"clinic": "Furry Tales Pet Spa, Indiranagar", "provider_type": "groomer"},
     "source_doc_ids": ["doc_seed_01", "doc_seed_06"]},

    {"id": "provider_sunshine_nair", "type": "provider", "name": "Dr. Priya Nair",
     "properties": {"clinic": "Sunshine Veterinary Clinic, Indiranagar", "provider_type": "vet"},
     "source_doc_ids": ["doc_seed_02", "doc_seed_05", "doc_seed_07"]},

    {"id": "provider_citypets_mehta", "type": "provider", "name": "Dr. Arjun Mehta",
     "properties": {"clinic": "CityPets 24x7 Emergency Hospital, Koramangala", "provider_type": "er"},
     "source_doc_ids": ["doc_seed_04"]},

    {"id": "provider_bvdc_rao", "type": "provider", "name": "Dr. Kavita Rao",
     "properties": {"clinic": "Bengaluru Veterinary Dermatology Centre, Jayanagar",
                    "provider_type": "specialist"},
     "source_doc_ids": ["doc_seed_08"]},

    # Visits — Bella
    {"id": "visit_bella_groomer_sep25", "type": "visit", "name": "Grooming 2025-09-14",
     "properties": {"date": "2025-09-14", "visit_type": "groomer",
                    "chief_complaint": "Routine grooming; left-ear scratching noted",
                    "provider_id": "provider_furrytales_meera", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_01"]},

    {"id": "visit_bella_vet_dec25", "type": "visit", "name": "Visit 2025-12-06",
     "properties": {"date": "2025-12-06", "visit_type": "vet",
                    "chief_complaint": "Persistent ear scratching, left ear, ~3 months",
                    "follow_up_date": "2025-12-27",
                    "provider_id": "provider_sunshine_nair", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_02"]},

    {"id": "visit_bella_owner_feb26", "type": "visit", "name": "Owner Note 2026-02-16",
     "properties": {"date": "2026-02-16", "visit_type": "owner_note",
                    "chief_complaint": "Head shaking, both ears now, restless at night",
                    "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_03"]},

    {"id": "visit_bella_er_feb26", "type": "visit", "name": "ER Visit 2026-02-17",
     "properties": {"date": "2026-02-17", "visit_type": "er",
                    "chief_complaint": "Bilateral ear scratching, head shaking x 3-4 days",
                    "provider_id": "provider_citypets_mehta", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_04"]},

    {"id": "visit_bella_vet_apr26", "type": "visit", "name": "Follow-up 2026-04-12",
     "properties": {"date": "2026-04-12", "visit_type": "vet",
                    "chief_complaint": "Otitis recheck (resolved); new paw licking + face rubbing",
                    "provider_id": "provider_sunshine_nair", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_07"]},

    {"id": "visit_bella_derm_jun26", "type": "visit", "name": "Dermatology 2026-06-10",
     "properties": {"date": "2026-06-10", "visit_type": "vet",
                    "chief_complaint": "Allergy workup — intradermal testing",
                    "follow_up_date": "2026-08-05",
                    "provider_id": "provider_bvdc_rao", "pet_id": "pet_canine_bella"},
     "source_doc_ids": ["doc_seed_08"]},

    # Visits — Charlie
    {"id": "visit_charlie_groomer_oct25", "type": "visit", "name": "Grooming 2025-10-04",
     "properties": {"date": "2025-10-04", "visit_type": "groomer",
                    "chief_complaint": "Routine grooming",
                    "provider_id": "provider_furrytales_meera", "pet_id": "pet_feline_charlie"},
     "source_doc_ids": ["doc_seed_06"]},

    {"id": "visit_charlie_vet_nov25", "type": "visit", "name": "Visit 2025-11-22",
     "properties": {"date": "2025-11-22", "visit_type": "vet",
                    "chief_complaint": "Annual wellness exam",
                    "provider_id": "provider_sunshine_nair", "pet_id": "pet_feline_charlie"},
     "source_doc_ids": ["doc_seed_05"]},

    # Symptoms
    {"id": "sym_ear_scratching", "type": "symptom", "name": "Ear scratching",
     "properties": {"description": "Scratching at left ear, head-shy during grooming",
                    "ear_side": "left", "date": "2025-09-14"},
     "source_doc_ids": ["doc_seed_01"]},

    {"id": "sym_head_shaking", "type": "symptom", "name": "Head shaking",
     "properties": {"description": "Head shaking and face rubbing on carpet; bilateral involvement",
                    "ear_side": "bilateral", "date": "2026-02-16"},
     "source_doc_ids": ["doc_seed_03", "doc_seed_04"]},

    {"id": "sym_paw_licking", "type": "symptom", "name": "Paw licking",
     "properties": {"description": "Frequent paw licking and face rubbing on furniture, onset ~March 2026",
                    "date": "2026-04-12"},
     "source_doc_ids": ["doc_seed_07", "doc_seed_08"]},

    # Diagnoses
    {"id": "dx_otitis_externa", "type": "diagnosis", "name": "Otitis externa",
     "properties": {"date": "2025-12-06",
                    "outcome": "resolved (Dec), recurrent (Feb), resolved again (Apr)"},
     "source_doc_ids": ["doc_seed_02", "doc_seed_04", "doc_seed_07"]},

    {"id": "dx_atopic_dermatitis", "type": "diagnosis", "name": "Atopic dermatitis",
     "properties": {"date": "2026-06-10", "outcome": "ongoing — immunotherapy started"},
     "source_doc_ids": ["doc_seed_08"]},

    # Medications — CONFLICT: Surolan discontinued by Sunshine, listed potentially-active by ER
    {"id": "med_SVC20251206B", "type": "medication", "name": "Surolan Ear Drops",
     "properties": {
         "dose": "5 drops, left ear, once daily",
         "frequency": "once daily x 14 days",
         "start_date": "2025-12-06",
         "end_date": "2025-12-20",
         "status": "discontinued",
         "rx_number": "SVC-2025-1206-B",
         "prescriber_id": "provider_sunshine_nair",
     },
     "source_doc_ids": ["doc_seed_02"]},

    {"id": "med_CPE20260217S", "type": "medication", "name": "Surolan Ear Drops",
     "properties": {
         "dose": "unknown",
         "status": "uncertain",  # ← ER listed as "potentially active"
         "start_date": "2026-02-17",
         "prescriber_id": "provider_citypets_mehta",
         "note": "ER listed as potentially active — owner unable to confirm discontinuation",
     },
     "source_doc_ids": ["doc_seed_04"]},

    {"id": "med_CPE20260217O", "type": "medication", "name": "Otibact Ear Drops",
     "properties": {
         "dose": "4 drops per affected ear, twice daily",
         "frequency": "BID x 7 days",
         "start_date": "2026-02-17",
         "end_date": "2026-02-24",
         "status": "completed",
         "rx_number": "CPE-2026-0217-1",
         "prescriber_id": "provider_citypets_mehta",
     },
     "source_doc_ids": ["doc_seed_04"]},

    {"id": "med_CPE20260217A", "type": "medication", "name": "Apoquel (oclacitinib)",
     "properties": {
         "dose": "16 mg, 1 tablet",
         "frequency": "BID x 5 days then SID x 14 days",
         "start_date": "2026-02-17",
         "end_date": "2026-03-08",
         "status": "completed",
         "rx_number": "CPE-2026-0217-2",
         "prescriber_id": "provider_citypets_mehta",
     },
     "source_doc_ids": ["doc_seed_04"]},

    {"id": "med_SVC20260412C", "type": "medication", "name": "Cytopoint (lokivetmab)",
     "properties": {
         "dose": "2 mg/kg SC",
         "frequency": "every 4-8 weeks as needed",
         "start_date": "2026-04-12",
         "status": "active",
         "rx_number": "SVC-2026-0412-C",
         "prescriber_id": "provider_sunshine_nair",
     },
     "source_doc_ids": ["doc_seed_07", "doc_seed_08"]},

    {"id": "med_BVDC20260610ASIT", "type": "medication", "name": "Allergen immunotherapy (ASIT)",
     "properties": {
         "dose": "custom serum, SC",
         "frequency": "weekly x 12 weeks (induction), then biweekly",
         "start_date": "2026-06-10",
         "end_date": "2026-08-29",
         "status": "active",
         "rx_number": "BVDC-2026-0610-ASIT",
         "prescriber_id": "provider_bvdc_rao",
     },
     "source_doc_ids": ["doc_seed_08"]},

    # Vaccines — CONFLICT: ER administered rabies 2026-02-17, primary vet's record is older
    {"id": "vax_bella_rabies_2025", "type": "vaccine", "name": "Rabies (Nobivac Rabies)",
     "properties": {"date": "2025-02-08", "next_due": "2026-02-08",
                    "provider_id": "provider_sunshine_nair"},
     "source_doc_ids": ["doc_seed_02"]},

    {"id": "vax_bella_dhppi_2025", "type": "vaccine", "name": "DHPPi+L (Nobivac)",
     "properties": {"date": "2025-08-17", "next_due": "2026-08-17",
                    "provider_id": "provider_sunshine_nair"},
     "source_doc_ids": ["doc_seed_02", "doc_seed_07"]},

    {"id": "vax_bella_rabies_er2026", "type": "vaccine", "name": "Rabies (Raksharab)",
     "properties": {
         "date": "2026-02-17", "next_due": "2027-02-17",
         "lot": "RR-2381-77A", "tag": "CPE-4471-RAB-26",
         "provider_id": "provider_citypets_mehta",
         "note": "Administered at ER — primary vet updated their records on 2026-04-12",
     },
     "source_doc_ids": ["doc_seed_04"]},

    # Charlie vaccines — rabies deferred at Nov 2025 wellness → now overdue
    {"id": "vax_charlie_tricat_2025", "type": "vaccine", "name": "Tricat (Nobivac Tricat Trio)",
     "properties": {"date": "2025-11-22", "next_due": "2026-11-22",
                    "provider_id": "provider_sunshine_nair"},
     "source_doc_ids": ["doc_seed_05"]},

    {"id": "vax_charlie_rabies_2025", "type": "vaccine", "name": "Rabies (Raksharab)",
     "properties": {"date": "2025-05-18", "next_due": "2026-05-18",
                    "provider_id": "provider_sunshine_nair",
                    "note": "Booster deferred at 2025-11-22 wellness (indoor cat) — owner to reschedule"},
     "source_doc_ids": ["doc_seed_05"]},
]


EDGES = [
    # Owner ↔ pets
    ("pet_canine_bella", "owner_ananya_sharma", "owned_by", "doc_seed_01"),
    ("pet_feline_charlie", "owner_ananya_sharma", "owned_by", "doc_seed_05"),

    # Bella → visits
    ("pet_canine_bella", "visit_bella_groomer_sep25", "had_visit", "doc_seed_01"),
    ("pet_canine_bella", "visit_bella_vet_dec25",     "had_visit", "doc_seed_02"),
    ("pet_canine_bella", "visit_bella_owner_feb26",   "had_visit", "doc_seed_03"),
    ("pet_canine_bella", "visit_bella_er_feb26",      "had_visit", "doc_seed_04"),
    ("pet_canine_bella", "visit_bella_vet_apr26",     "had_visit", "doc_seed_07"),
    ("pet_canine_bella", "visit_bella_derm_jun26",    "had_visit", "doc_seed_08"),

    # Charlie → visits
    ("pet_feline_charlie", "visit_charlie_groomer_oct25", "had_visit", "doc_seed_06"),
    ("pet_feline_charlie", "visit_charlie_vet_nov25",     "had_visit", "doc_seed_05"),

    # Visits → providers
    ("visit_bella_groomer_sep25",   "provider_furrytales_meera", "seen_at", "doc_seed_01"),
    ("visit_bella_vet_dec25",       "provider_sunshine_nair",    "seen_at", "doc_seed_02"),
    ("visit_bella_er_feb26",        "provider_citypets_mehta",   "seen_at", "doc_seed_04"),
    ("visit_bella_vet_apr26",       "provider_sunshine_nair",    "seen_at", "doc_seed_07"),
    ("visit_bella_derm_jun26",      "provider_bvdc_rao",         "seen_at", "doc_seed_08"),
    ("visit_charlie_groomer_oct25", "provider_furrytales_meera", "seen_at", "doc_seed_06"),
    ("visit_charlie_vet_nov25",     "provider_sunshine_nair",    "seen_at", "doc_seed_05"),

    # Bella → symptoms
    ("pet_canine_bella", "sym_ear_scratching", "has_symptom", "doc_seed_01"),
    ("pet_canine_bella", "sym_head_shaking",   "has_symptom", "doc_seed_03"),
    ("pet_canine_bella", "sym_paw_licking",    "has_symptom", "doc_seed_07"),

    # Symptoms linked across visits (same underlying condition)
    ("sym_ear_scratching", "sym_head_shaking", "same_condition_as", "doc_seed_03"),

    # Bella → diagnoses
    ("pet_canine_bella", "dx_otitis_externa",     "received_diagnosis", "doc_seed_02"),
    ("pet_canine_bella", "dx_atopic_dermatitis",  "received_diagnosis", "doc_seed_08"),

    # Diagnosis ↔ symptoms / conditions
    ("dx_otitis_externa",    "sym_ear_scratching", "explains_symptom", "doc_seed_02"),
    ("dx_otitis_externa",    "sym_head_shaking",   "explains_symptom", "doc_seed_04"),
    ("dx_atopic_dermatitis", "sym_paw_licking",    "explains_symptom", "doc_seed_08"),
    # Atopy is the predisposing factor behind the recurrent otitis
    ("dx_atopic_dermatitis", "dx_otitis_externa",  "predisposes",      "doc_seed_08"),

    # Bella → medications
    ("pet_canine_bella", "med_SVC20251206B",     "prescribed", "doc_seed_02"),
    ("pet_canine_bella", "med_CPE20260217S",     "prescribed", "doc_seed_04"),
    ("pet_canine_bella", "med_CPE20260217O",     "prescribed", "doc_seed_04"),
    ("pet_canine_bella", "med_CPE20260217A",     "prescribed", "doc_seed_04"),
    ("pet_canine_bella", "med_SVC20260412C",     "prescribed", "doc_seed_07"),
    ("pet_canine_bella", "med_BVDC20260610ASIT", "prescribed", "doc_seed_08"),

    # Diagnosis → medications
    ("dx_otitis_externa",    "med_SVC20251206B",     "treated_with", "doc_seed_02"),
    ("dx_otitis_externa",    "med_CPE20260217O",     "treated_with", "doc_seed_04"),
    ("dx_atopic_dermatitis", "med_SVC20260412C",     "treated_with", "doc_seed_07"),
    ("dx_atopic_dermatitis", "med_BVDC20260610ASIT", "treated_with", "doc_seed_08"),

    # Medications → providers (administered_by / discontinued_by)
    ("med_SVC20251206B",     "provider_sunshine_nair",  "discontinued_by", "doc_seed_02"),  # ← CONFLICT key
    ("med_CPE20260217S",     "provider_citypets_mehta", "administered_by", "doc_seed_04"),  # ← CONFLICT key
    ("med_CPE20260217O",     "provider_citypets_mehta", "administered_by", "doc_seed_04"),
    ("med_CPE20260217A",     "provider_citypets_mehta", "administered_by", "doc_seed_04"),
    ("med_SVC20260412C",     "provider_sunshine_nair",  "administered_by", "doc_seed_07"),
    ("med_BVDC20260610ASIT", "provider_bvdc_rao",       "administered_by", "doc_seed_08"),

    # Visit follow-up chain
    ("visit_bella_er_feb26",   "visit_bella_vet_dec25", "follow_up_to", "doc_seed_04"),
    ("visit_bella_vet_apr26",  "visit_bella_er_feb26",  "follow_up_to", "doc_seed_07"),
    ("visit_bella_derm_jun26", "visit_bella_vet_apr26", "follow_up_to", "doc_seed_08"),

    # Bella → vaccines
    ("pet_canine_bella", "vax_bella_rabies_2025",   "received_vaccine", "doc_seed_02"),
    ("pet_canine_bella", "vax_bella_dhppi_2025",    "received_vaccine", "doc_seed_02"),
    ("pet_canine_bella", "vax_bella_rabies_er2026", "received_vaccine", "doc_seed_04"),

    # Vaccines → providers
    ("vax_bella_rabies_2025",   "provider_sunshine_nair",  "administered_by", "doc_seed_02"),
    ("vax_bella_dhppi_2025",    "provider_sunshine_nair",  "administered_by", "doc_seed_02"),
    ("vax_bella_rabies_er2026", "provider_citypets_mehta", "administered_by", "doc_seed_04"),  # ← CONFLICT key

    # Charlie vaccines
    ("pet_feline_charlie", "vax_charlie_tricat_2025", "received_vaccine", "doc_seed_05"),
    ("pet_feline_charlie", "vax_charlie_rabies_2025", "received_vaccine", "doc_seed_05"),
    ("vax_charlie_tricat_2025", "provider_sunshine_nair", "administered_by", "doc_seed_05"),
    ("vax_charlie_rabies_2025", "provider_sunshine_nair", "administered_by", "doc_seed_05"),
]

SEED_DOCUMENTS = [
    {"id": "doc_seed_01", "filename": "01_groomer_september.txt",    "doc_type": "groomer_note", "provider_name": "Meera R., Furry Tales Pet Spa",            "doc_date": "2025-09-14"},
    {"id": "doc_seed_02", "filename": "02_vet_december.txt",         "doc_type": "vet_visit",    "provider_name": "Dr. Priya Nair, Sunshine Veterinary Clinic", "doc_date": "2025-12-06"},
    {"id": "doc_seed_03", "filename": "03_owner_note_february.txt",  "doc_type": "owner_note",   "provider_name": None,                                          "doc_date": "2026-02-16"},
    {"id": "doc_seed_04", "filename": "04_er_discharge_february.txt","doc_type": "er_discharge", "provider_name": "Dr. Arjun Mehta, CityPets 24x7 Emergency",   "doc_date": "2026-02-17"},
    {"id": "doc_seed_05", "filename": "05_charlie_vet.txt",          "doc_type": "vet_visit",    "provider_name": "Dr. Priya Nair, Sunshine Veterinary Clinic", "doc_date": "2025-11-22"},
    {"id": "doc_seed_06", "filename": "06_charlie_groomer.txt",      "doc_type": "groomer_note", "provider_name": "Meera R., Furry Tales Pet Spa",            "doc_date": "2025-10-04"},
    {"id": "doc_seed_07", "filename": "07_bella_followup_april.txt", "doc_type": "vet_visit",    "provider_name": "Dr. Priya Nair, Sunshine Veterinary Clinic", "doc_date": "2026-04-12"},
    {"id": "doc_seed_08", "filename": "08_bella_derm_june.txt",      "doc_type": "specialist",   "provider_name": "Dr. Kavita Rao, Bengaluru Veterinary Dermatology Centre", "doc_date": "2026-06-10"},
]


async def load_seed_graph(seed_docs_dir) -> list[dict]:
    """
    Load all seed documents (SQLite bookkeeping) and write the pre-computed
    graph directly into Cognee's graph engine — no LLM needed. Semantic
    indexing of the raw documents (add + cognify) is kicked off in the
    background when possible.
    """
    import asyncio
    from pathlib import Path

    events = []
    docs = []
    for doc_meta in SEED_DOCUMENTS:
        path = Path(seed_docs_dir) / doc_meta["filename"]
        content = path.read_text(encoding="utf-8") if path.exists() else "(content not found)"
        await db.save_document({**doc_meta, "content": content})
        await db.mark_document_processed(doc_meta["id"])
        docs.append({**doc_meta, "content": content})
        events.append({"stage": "saved", "message": f"Saved {doc_meta['filename']}", "pct": 10,
                        "file": doc_meta["filename"]})

    # Batch write the pet graph into Cognee's graph store
    await cognee_graph.add_nodes(NODES)
    await cognee_graph.add_edges([
        (src, tgt, rel, {"source_doc_id": doc}) for src, tgt, rel, doc in EDGES
    ])
    events.append({"stage": "graph", "message": f"Cognee graph: {len(NODES)} nodes, {len(EDGES)} edges", "pct": 80})

    # Derived app state from the fresh graph
    from services import reminders, insights
    await reminders.generate_reminders()
    await insights.generate_insights()

    # Semantic layer (vector + cognify graph) — background, needs an LLM key
    asyncio.create_task(cognee_graph.index_documents_semantic(docs))
    events.append({"stage": "done",
                   "message": f"Seed graph loaded: {len(NODES)} nodes, {len(EDGES)} edges; semantic indexing queued",
                   "pct": 100})
    return events
