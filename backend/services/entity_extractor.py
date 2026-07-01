"""
LLM-based entity extraction from raw document text.
Returns structured domain entities that we store in SQLite.
Cognee handles semantic indexing; this handles domain modelling.
"""
import json
import re
from config import LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, ANTHROPIC_API_KEY

EXTRACTION_PROMPT = """You are a veterinary health record parser. Extract ALL entities from the following document.

Return ONLY valid JSON matching this exact schema (no prose, no markdown fences):

{
  "pets": [
    {
      "name": "canonical name",
      "raw_name": "name exactly as written in doc",
      "species": "canine|feline|other",
      "breed": "breed string",
      "sex": "male|female|unknown",
      "dob_approx": "YYYY or null",
      "weight_lbs": number_or_null
    }
  ],
  "owners": [
    {"name": "full name", "phone": "phone or null"}
  ],
  "providers": [
    {
      "name": "Dr. X or Jenna K. etc",
      "clinic": "clinic name",
      "type": "vet|groomer|er|boarder"
    }
  ],
  "visits": [
    {
      "date": "YYYY-MM-DD or null",
      "type": "vet|groomer|er|owner_note",
      "pet_raw_name": "pet name as in doc",
      "provider_name": "provider name or null",
      "chief_complaint": "brief string or null"
    }
  ],
  "symptoms": [
    {
      "name": "normalized symptom name",
      "description": "as described in doc",
      "date": "YYYY-MM-DD or null",
      "pet_raw_name": "pet name as in doc",
      "ear_side": "left|right|bilateral|null"
    }
  ],
  "diagnoses": [
    {
      "name": "diagnosis name",
      "date": "YYYY-MM-DD or null",
      "pet_raw_name": "pet name as in doc",
      "outcome": "resolved|ongoing|unknown"
    }
  ],
  "medications": [
    {
      "name": "drug name",
      "dose": "dose string or null",
      "frequency": "frequency string or null",
      "start_date": "YYYY-MM-DD or null",
      "end_date": "YYYY-MM-DD or null",
      "status": "active|discontinued|prescribed|uncertain",
      "rx_number": "Rx# or null",
      "prescriber_name": "provider name or null",
      "pet_raw_name": "pet name as in doc"
    }
  ],
  "vaccines": [
    {
      "name": "vaccine name",
      "date": "YYYY-MM-DD or null",
      "provider_name": "provider name or null",
      "pet_raw_name": "pet name as in doc",
      "next_due": "YYYY-MM-DD or null",
      "lot": "lot number or null"
    }
  ]
}

"""


async def extract_entities(document_text: str, doc_id: str) -> dict:
    """Call LLM to extract structured entities from document text."""
    prompt = EXTRACTION_PROMPT + "\n\nDOCUMENT:\n" + document_text

    raw = ""
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        raw = await _extract_anthropic(prompt)
    elif OPENAI_API_KEY:
        raw = await _extract_openai(prompt)
    else:
        raise RuntimeError("No LLM API key configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env")

    return _parse_json(raw)


async def _extract_openai(prompt: str) -> str:
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _extract_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    msg = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    # Strip markdown fences if model added them
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find the JSON object in the response
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
