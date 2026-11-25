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
    memory_turns: int = 3  # earlier question-and-answer pairs of the same chat that a follow-up may use. 0 = every question is answered on its own
    rate_limit_per_minute: int = 5  # questions one signed-in person may ask per minute: each one spends free AI tokens. 0 = no limit
    rate_limit_per_day: int = 20  # ...and in any 24 hours (about 60 to 100 questions a day fit the free AI plan, for everybody together). 0 = no limit

    admin_api_key: str = ""  # empty = the staff endpoints are switched off
    upload_dir: Path = ROOT / "data" / "uploads"
    kb_dir: Path = ROOT / "data" / "kb"  # the folder `python -m app.rag.ingest` loads; subfolders such as batch-1/ are read too
    audit_db: Path = ROOT / "data" / "audit.db"
    audit_retention_days: int = 90  # audit rows older than this are deleted (at start-up, and each time a question is saved). 0 = keep everything

    supabase_url: str = ""  # https://<project>.supabase.co (accounts and saved chats). Empty = no Supabase
    supabase_publishable_key: str = ""  # sb_publishable_...  Safe to show in a browser: row-level security in the database protects the data
    supabase_secret_key: str = ""  # sb_secret_...  Skips row-level security. Only `python -m app.supabase.check --full` reads it, to make and delete test users. The running app never uses it


@lru_cache
def get_settings() -> Settings:
    return Settings()
