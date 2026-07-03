"""
Deterministic node-ID generation for typed domain entities.

The fuzzy cross-document resolution that used to live here (fingerprint /
name-token matching) is retired: Cognee's cognify pipeline dedupes its semantic
entities natively, and the typed extraction canonicalizes mentions against the
existing graph via canonical_id (see entity_extractor.py). What remains is
stable, auditable ID construction.
"""
import re


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def make_pet_node_id(species: str, name: str) -> str:
    sp = normalize_name(species or "unknown")
    nm = normalize_name(name or "unknown")
    return f"pet_{sp}_{nm.replace(' ', '_')}"


def make_owner_node_id(name: str) -> str:
    return f"owner_{normalize_name(name).replace(' ', '_')}"


def make_provider_node_id(provider_name: str, clinic: str) -> str:
    pn = normalize_name(provider_name or "unknown")
    cl = normalize_name(clinic or "unknown")
    return f"provider_{cl[:20].replace(' ', '_')}_{pn.split()[0] if pn else 'unk'}"


def make_medication_node_id(name: str, rx_number: str | None) -> str:
    nm = normalize_name(name or "unknown")
    rx = (rx_number or "").replace("-", "")
    suffix = rx if rx else nm.replace(" ", "_")[:20]
    return f"med_{suffix}"


def make_vaccine_node_id(name: str, date: str | None, pet_id: str) -> str:
    nm = normalize_name(name or "unknown").replace(" ", "_")[:20]
    dt = (date or "unknown").replace("-", "")
    return f"vax_{pet_id[-12:]}_{nm}_{dt}"


def make_symptom_node_id(name: str) -> str:
    nm = normalize_name(name or "unknown").replace(" ", "_")
    return f"sym_{nm[:30]}"


def make_diagnosis_node_id(name: str) -> str:
    nm = normalize_name(name or "unknown").replace(" ", "_")
    return f"dx_{nm[:30]}"


def make_visit_node_id(date: str | None, pet_id: str, provider_id: str) -> str:
    dt = (date or "unknown").replace("-", "")
    return f"visit_{pet_id[-8:]}_{provider_id[-8:]}_{dt}"
