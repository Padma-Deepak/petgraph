import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent
# DATA_DIR is /data inside Docker (named volume). Falls back to BASE_DIR for local dev.
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR)))
DB_PATH = DATA_DIR / "petgraph.db"
SEED_DOCS_DIR = Path(os.getenv("SEED_DOCS_DIR", str(BASE_DIR / "seed_documents")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

def get_llm_key() -> str:
    if LLM_PROVIDER == "anthropic":
        return ANTHROPIC_API_KEY
    return OPENAI_API_KEY
