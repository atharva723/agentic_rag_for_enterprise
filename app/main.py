"""Starts the web app: the API under /api and the chat page at /."""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import audit
from app.api import account, admin, chat, conversations, streaming
from app.config import ROOT, get_settings
from app.headers import page_headers
from app.rag import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
_s = get_settings()
log.info("Knowledge base: index=%s namespace=%s embedding=%s", _s.pinecone_index_name, _s.pinecone_namespace, _s.embedding_model)


def warm_up() -> None:
    """Get the knowledge base ready before the first question. A problem here is only a warning: chat reports it properly when it is used."""
    try:
        store.warm_up()
    except Exception as exc:
        log.warning("Warm-up skipped: %s", exc)


def trim_audit() -> None:
    """Delete audit rows past the retention period. A problem here is only a warning: it is tried again each time a question is saved."""
    try:
        removed = audit.prune()
        if removed:
            log.info("Audit log: deleted %d row(s) older than %d days", removed, get_settings().audit_retention_days)
    except Exception as exc:
        log.warning("Audit clean-up skipped: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    trim_audit()
    threading.Thread(target=warm_up, daemon=True).start()  # in the background, so the server is ready at once
    yield
    await streaming.wait_for_jobs()  # an answer still being made finishes and saves before the process ends


class PageFiles(StaticFiles):
    """Serves the pages. "no-cache" makes the browser check for a newer file each time (cheap when nothing changed), so an update
    shows up at once instead of a new page running an old script. Every file also carries the security headers (app/headers.py)."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        response.headers.update(page_headers(get_settings().supabase_url))
        return response


app = FastAPI(title="IT Support Agentic RAG Copilot", lifespan=lifespan)
app.include_router(chat.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.mount("/", PageFiles(directory=ROOT / "ui", html=True), name="ui")
