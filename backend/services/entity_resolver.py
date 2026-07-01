"""
Deterministic entity resolution: merges pet records that refer to the same animal
across documents with different name formats (Bella / Bella M. / Patient #4471).

Resolution strategy:
  - Same owner + same species + same breed + same sex → merge
  - Name similarity above threshold → merge (covers "Bella" vs "Bella M.")
  - Patient ID references are matched to known pets by species/breed/sex/owner fingerprint
"""
import re


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def pet_fingerprint(pet: dict) -> str:
    """Stable fingerprint for deduplication: owner+species+breed+sex."""
    owner = normalize_name(pet.get("owner_name", "unknown"))
    species = normalize_name(pet.get("species", "unknown"))
    breed = normalize_name(pet.get("breed", "unknown"))
    sex = normalize_name(pet.get("sex", "unknown"))
    return f"{owner}|{species}|{breed}|{sex}"


def base_name(name: str) -> str:
    """Extract the first token as base name for fuzzy matching."""
    return normalize_name(name).split()[0] if name else ""


def resolve_pets(extracted_pets: list[dict], existing_pet_nodes: list[dict]) -> dict[str, str]:
    """
    Given a list of newly extracted pet dicts and the current canonical pet nodes,
    return a mapping {raw_name → canonical_node_id}.

    Merge rules (applied in order):
    1. Fingerprint match (same owner+species+breed+sex) → same pet
    2. First-name token match + species match → same pet
    3. Otherwise → new pet node
    """
    mapping: dict[str, str] = {}

    for ep in extracted_pets:
        raw = ep.get("raw_name", ep.get("name", ""))
        fp = pet_fingerprint(ep)
        base = base_name(raw)

        matched_id = None

        # Rule 1: exact fingerprint
        for existing in existing_pet_nodes:
            ep_fp = pet_fingerprint({
                **ep,
                "owner_name": existing.get("properties", {}).get("owner_name", ep.get("owner_name", "")),
            })
            if pet_fingerprint(existing.get("properties", {})) == fp:
                matched_id = existing["id"]
                break

        # Rule 2: first-name + species
        if not matched_id:
            for existing in existing_pet_nodes:
                ex_base = base_name(existing["name"])
                ex_species = normalize_name(existing.get("properties", {}).get("species", ""))
                ep_species = normalize_name(ep.get("species", ""))
                if ex_base == base and (not ep_species or not ex_species or ex_species == ep_species):
                    matched_id = existing["id"]
                    break

        if matched_id:
            mapping[raw] = matched_id
        else:
            # Will create a new node — use species+name as stable ID basis
            sp = normalize_name(ep.get("species", "unknown"))
            nm = normalize_name(ep.get("name", raw))
            new_id = f"pet_{sp}_{nm.replace(' ', '_')}"
            mapping[raw] = new_id

    return mapping


def make_pet_node_id(species: str, name: str) -> str:
    sp = normalize_name(species or "unknown")
    nm = normalize_name(name or "unknown")
    return f"pet_{sp}_{nm.replace(' ', '_')}"


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


# Credential-like tokens that appear in names but don't distinguish providers
_PROVIDER_STOP_TOKENS = {"dr", "dvm", "dds", "ms", "mr", "mrs", "rn", "lvt", "dacvd", "dacvecc", "the", "k", "j"}


def resolve_providers(extracted_providers: list[dict], existing_provider_nodes: list[dict]) -> dict[str, str]:
    """
    Map extracted provider name strings → canonical node IDs.
    Matches against existing nodes so uploads merge with seed providers rather than
    creating duplicates with different IDs.

    Match rules (applied in order):
    1. Any significant name-token overlap + compatible provider type → use existing ID
    2. Otherwise → generate a new ID via make_provider_node_id
    """
    mapping: dict[str, str] = {}

    for ep in extracted_providers:
        raw = ep.get("name", "")
        ep_type = normalize_name(ep.get("type", ""))
        ep_sig = {t for t in normalize_name(raw).split()
                  if t not in _PROVIDER_STOP_TOKENS and len(t) > 1}

        matched_id = None
        for ex in existing_provider_nodes:
            ex_sig = {t for t in normalize_name(ex["name"]).split()
                      if t not in _PROVIDER_STOP_TOKENS and len(t) > 1}
            ex_type = normalize_name(ex.get("properties", {}).get("provider_type", ""))

            if ep_sig & ex_sig and (not ep_type or not ex_type or ep_type == ex_type):
                matched_id = ex["id"]
                break

        mapping[raw] = matched_id if matched_id else make_provider_node_id(raw, ep.get("clinic", ""))

    return mapping
