"""Starts the web app: the API under /api and the chat page at /."""
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import admin, chat
from app.config import ROOT, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_s = get_settings()
logging.getLogger(__name__).info(
    "Knowledge base: index=%s namespace=%s embedding=%s", _s.pinecone_index_name, _s.pinecone_namespace, _s.embedding_model
)

app = FastAPI(title="IT Support Agentic RAG Copilot")
app.include_router(chat.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.mount("/", StaticFiles(directory=ROOT / "ui", html=True), name="ui")
