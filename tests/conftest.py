"""Shared test helpers: an in-memory Pinecone, a fake embedder, a fake LLM and a fake Supabase, so no test needs keys, a network or a model download."""
import math
import re
import zlib
from types import SimpleNamespace

import httpx
import pytest

from app.agent import llm
from app.config import get_settings
from app.rag import store
from app.supabase import client as supabase_client

DIM = 256


def fake_embed(texts, *, query=False):
    """Word-overlap vectors: texts that share words get similar vectors. Always the same for the same text."""
    out = []
    for text in texts:
        vector = [0.0] * DIM
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[zlib.crc32(word.encode()) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        out.append([x / norm for x in vector])
    return out


class FakeIndex:
    """Remembers records per namespace and answers the few calls store.py makes."""

    def __init__(self):
        self.data = {}  # namespace -> {id: record}

    def upsert(self, *, vectors, namespace="", **_):
        self.data.setdefault(namespace, {}).update({v["id"]: v for v in vectors})

    def query(self, *, top_k, vector, namespace="", include_metadata=False, **_):
        def score(record):
            return sum(a * b for a, b in zip(vector, record["values"]))

        best = sorted(self.data.get(namespace, {}).values(), key=score, reverse=True)[:top_k]
        matches = [SimpleNamespace(id=r["id"], score=score(r), metadata=dict(r["metadata"])) for r in best]
        return SimpleNamespace(matches=matches)

    def delete(self, *, delete_all=False, filter=None, namespace="", **_):
        records = self.data.get(namespace, {})
        if delete_all:
            records.clear()
        elif filter:
            ((field, condition),) = filter.items()
            for record_id in [i for i, r in records.items() if r["metadata"].get(field) == condition["$eq"]]:
                del records[record_id]

    def describe_index_stats(self):
        counts = {ns: SimpleNamespace(vector_count=len(records)) for ns, records in self.data.items() if records}
        return SimpleNamespace(namespaces=counts)


class FakePinecone:
    """Stands in for pinecone.Pinecone. The index starts out missing. `deleted` must always stay empty."""

    def __init__(self):
        self.live, self.dimension, self.created, self.deleted = None, None, [], []
        self.indexes = SimpleNamespace(
            exists=lambda name: self.live is not None,
            create=self._create,
            describe=lambda name: SimpleNamespace(host="fake-host", dimension=self.dimension),
            delete=lambda name: self.deleted.append(name),
        )

    def __call__(self, *, api_key):
        return self

    def index(self, *, host):
        return self.live

    def _create(self, **kwargs):
        self.created.append(kwargs)
        self.live, self.dimension = FakeIndex(), kwargs["dimension"]


@pytest.fixture
def pinecone(monkeypatch):
    """Swap Pinecone and the embedding model for fakes, and point the settings at a test index."""
    fake = FakePinecone()
    monkeypatch.setattr(store, "Pinecone", fake)
    monkeypatch.setattr(store, "embed", fake_embed)
    settings = get_settings()
    monkeypatch.setattr(settings, "pinecone_api_key", "test-key")
    monkeypatch.setattr(settings, "pinecone_index_name", "test-index")
    monkeypatch.setattr(settings, "pinecone_namespace", "test-ns")
    for cached in (store._pc, store._size, store._index):
        cached.cache_clear()
    yield fake
    for cached in (store._pc, store._size, store._index):
        cached.cache_clear()


class FakeLLM:
    """Stands in for app.agent.llm, so no test spends tokens.

    decisions: {schema class: [answers in order]}. When the list is empty the node's safe default is used.
    texts: replies for the text calls (the answer model and the fast model).
    prompts: everything that was sent. models / decision_models: "fast" or "answer" for each text call / each decision.
    """

    def __init__(self):
        self.decisions, self.texts, self.prompts, self.models, self.decision_models = {}, [], [], [], []

    def decide(self, schema, prompt, default, fast=True):
        self.prompts.append(prompt)
        self.decision_models.append("fast" if fast else "answer")
        queue = self.decisions.get(schema)
        return queue.pop(0) if queue else default

    def get_llm(self, fast=False):
        outer = self

        class Model:
            def invoke(self, prompt):
                outer.prompts.append(prompt)
                outer.models.append("fast" if fast else "answer")
                return SimpleNamespace(content=outer.texts.pop(0) if outer.texts else "a reply")

        return Model()


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "decide", fake.decide)
    monkeypatch.setattr(llm, "get_llm", fake.get_llm)
    return fake


class FakeSupabase:
    """Stands in for the Supabase server. Set what it answers, then read what it was sent."""

    url, publishable = "https://abc.supabase.co", "sb_publishable_test"

    def __init__(self):
        self.status, self.payload, self.error, self.requests = 200, [], None, []
        self.router = None  # a function(request) -> response, for tests that need more than one canned answer

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        if self.router:
            return self.router(request)
        return httpx.Response(self.status, json=self.payload)


@pytest.fixture
def supabase(monkeypatch):
    """Swap the network for a fake Supabase. The real request() still runs, so URL and header handling are tested."""
    fake = FakeSupabase()
    settings = get_settings()
    monkeypatch.setattr(settings, "supabase_url", fake.url + "/")  # the trailing slash must not double up
    monkeypatch.setattr(settings, "supabase_publishable_key", fake.publishable)
    real_client = httpx.Client
    monkeypatch.setattr(supabase_client.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake.handle), **kwargs))
    supabase_client._http.cache_clear()
    yield fake
    supabase_client._http.cache_clear()
