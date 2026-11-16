"""Pinecone and embeddings. The only file that talks to the vector database."""
import hashlib
import logging
import re
from functools import lru_cache

from langchain_core.documents import Document
from pinecone import Pinecone, ServerlessSpec

from app.config import get_settings

log = logging.getLogger(__name__)

CLOUD, REGION = "aws", "us-east-1"  # the only place the free Pinecone plan can run
BATCH = 100  # chunks per upload request


# ---- embeddings -------------------------------------------------------------


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer  # slow to import, so only when first needed

    name = get_settings().embedding_model
    log.info("Loading embedding model %s (the first run downloads it)", name)
    return SentenceTransformer(name)


def embed(texts: list[str], *, query: bool = False) -> list[list[float]]:
    """Turn texts into vectors. Use query=True for a user's question, False for document chunks."""
    model = _model()
    encode = model.encode_query if query else model.encode_document
    return encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False).tolist()


@lru_cache
def _size() -> int:
    """How many numbers the model puts in each vector (384 for bge-small)."""
    return len(embed(["size check"])[0])


# ---- the index --------------------------------------------------------------


@lru_cache
def _pc() -> Pinecone:
    key = get_settings().pinecone_api_key
    if not key:
        raise RuntimeError("PINECONE_API_KEY is missing. Put it in .env (see app/rag/README.md).")
    return Pinecone(api_key=key)


def _index_name() -> str:
    name = get_settings().pinecone_index_name
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,43}[a-z0-9])?", name):
        raise RuntimeError(
            f"PINECONE_INDEX_NAME '{name}' is not allowed. Use lowercase letters, digits and - only "
            "(at most 45 characters, and no - at the start or the end)."
        )
    return name


def ensure_index() -> None:
    """Create the index if it is missing. Only ingest calls this, so a typo in the name can't make chat build one."""
    name = _index_name()
    if _pc().indexes.exists(name):
        return
    log.info("Creating Pinecone index '%s' (%d numbers per vector, cosine, %s %s)", name, _size(), CLOUD, REGION)
    _pc().indexes.create(
        name=name,
        vector_type="dense",
        dimension=_size(),
        metric="cosine",
        spec=ServerlessSpec(cloud=CLOUD, region=REGION),
        deletion_protection="enabled",  # Pinecone refuses to delete it until you switch this off in the console
    )


@lru_cache
def _index():
    """Open the existing index and check that it fits the embedding model. Never deletes or changes anything."""
    name = _index_name()
    if not _pc().indexes.exists(name):
        raise RuntimeError(f"Pinecone index '{name}' does not exist yet. Create it by running: python -m app.rag.ingest")
    info = _pc().indexes.describe(name)
    if info.dimension != _size():
        raise RuntimeError(
            f"Index '{name}' stores {info.dimension}-number vectors, but the embedding model "
            f"'{get_settings().embedding_model}' makes {_size()}-number ones. Nothing was changed. "
            "Set a new PINECONE_INDEX_NAME in .env (the next ingest creates it), or delete the old index "
            "yourself in the Pinecone console (switch off its deletion protection first)."
        )
    return _pc().index(host=info.host)


def _has_chunks(index, namespace: str) -> bool:
    summary = (index.describe_index_stats().namespaces or {}).get(namespace)
    return bool(summary and summary.vector_count)


# ---- read and write ---------------------------------------------------------


def search(query: str, k: int | None = None) -> list[Document]:
    """Return the k most similar chunks (default: settings.top_k). Each has a "score" in its metadata."""
    s = get_settings()
    result = _index().query(
        vector=embed([query], query=True)[0], top_k=k or s.top_k, namespace=s.pinecone_namespace, include_metadata=True
    )
    docs = []
    for match in result.matches:
        meta = dict(match.metadata or {})
        docs.append(Document(page_content=meta.pop("text", ""), metadata={**meta, "score": round(match.score, 4)}))
    if not docs:
        log.warning(
            "Search found nothing: namespace '%s' in index '%s' looks empty. Run: python -m app.rag.ingest",
            s.pinecone_namespace,
            s.pinecone_index_name,
        )
    return docs


def _id_prefix(source: str) -> str:
    """A file name made safe for a Pinecone id (ASCII only). Odd names get a short hash so two never collide."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", source)
    return safe if safe == source else f"{safe}-{hashlib.sha1(source.encode()).hexdigest()[:6]}"


def add_chunks(chunks: list[Document]) -> int:
    """Embed and store chunks. A file uploaded again replaces its old chunks, so nothing goes stale or doubles up."""
    if not chunks:
        return 0
    ensure_index()
    index, namespace = _index(), get_settings().pinecone_namespace
    for source in {c.metadata["source"] for c in chunks}:
        if _has_chunks(index, namespace):  # a namespace that doesn't exist yet has nothing to remove
            index.delete(filter={"source": {"$eq": source}}, namespace=namespace)
    numbers: dict[str, int] = {}
    records = []
    for chunk, vector in zip(chunks, embed([c.page_content for c in chunks])):
        source = chunk.metadata["source"]
        numbers[source] = n = numbers.get(source, 0) + 1
        meta = {k: v for k, v in chunk.metadata.items() if isinstance(v, (str, int, float, bool))}  # no nulls or lists
        records.append({"id": f"{_id_prefix(source)}::{n:04d}", "values": vector, "metadata": {**meta, "text": chunk.page_content}})
    index.upsert(vectors=records, namespace=namespace, batch_size=BATCH, show_progress=False)
    return len(records)


def reset() -> None:
    """Delete every chunk in our namespace. The index itself stays."""
    ensure_index()
    index, namespace = _index(), get_settings().pinecone_namespace
    if _has_chunks(index, namespace):
        index.delete(delete_all=True, namespace=namespace)


def count() -> int:
    """How many chunks are stored in our namespace (the number can lag a few seconds after an upload)."""
    summary = (_index().describe_index_stats().namespaces or {}).get(get_settings().pinecone_namespace)
    return summary.vector_count if summary else 0


if __name__ == "__main__":
    # python -m app.rag.store                  shows what is stored
    # python -m app.rag.store "your question"  also shows the best matches
    import sys

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("app").setLevel(logging.INFO)  # show our own progress; keep the Pinecone and HTTP chatter quiet
    s = get_settings()
    print(f"index: {s.pinecone_index_name} | namespace: {s.pinecone_namespace} | model: {s.embedding_model}")
    print(f"chunks stored: {count()}")
    if len(sys.argv) > 1:
        for doc in search(" ".join(sys.argv[1:])):
            m = doc.metadata
            print(f"  {m['score']:.3f}  {m['source']}  >  {m.get('section') or m.get('title', '')}")
