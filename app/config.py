"""All settings in one place. A value in .env (or an environment variable) wins; the default here is only a fallback."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"  # writes the final answers
    groq_fast_model: str = "openai/gpt-oss-20b"  # router, grader, rewriter: small decisions. Groq counts tokens per model, so two models = two daily budgets
    tavily_api_key: str = ""
    pinecone_api_key: str = ""
    pinecone_index_name: str = "fde-it-support-rag"  # the database: lowercase letters, digits and - only
    pinecone_namespace: str = "company-it-kb"  # a folder inside the index; ingest and chat must use the same one
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # makes 384-number vectors; a different size needs a new index

    top_k: int = 4  # pieces of evidence per search (KB chunks or web results)
    max_retries: int = 1  # how many times a weak query may be rewritten

    admin_api_key: str = ""  # empty = the staff endpoints are switched off
    upload_dir: Path = ROOT / "data" / "uploads"
    kb_dir: Path = ROOT / "data" / "kb"  # the folder `python -m app.rag.ingest` loads; subfolders such as batch-1/ are read too
    audit_db: Path = ROOT / "data" / "audit.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
