import logging
import sys
import threading
import time
import types

import pytest
from langchain_core.documents import Document

from app.config import get_settings
from app.rag import store

from conftest import DIM, FakeIndex


def pieces(source, *texts, section="Part"):
    return [Document(page_content=t, metadata={"source": source, "section": section}) for t in texts]


def stored_ids(pinecone):
    return sorted(pinecone.live.data.get("test-ns", {}))


def test_first_upload_creates_a_protected_index_and_stores_chunks(pinecone):
    assert store.add_chunks(pieces("a.md", "one", "two")) == 2
    assert len(pinecone.created) == 1
    assert pinecone.created[0]["dimension"] == DIM
    assert pinecone.created[0]["deletion_protection"] == "enabled"
    assert stored_ids(pinecone) == ["a.md::0001", "a.md::0002"]


def test_chunks_keep_their_text_and_clean_metadata(pinecone):
    chunk = Document(page_content="hello", metadata={"source": "a.md", "page": 3, "section": None, "tags": ["x"]})
    store.add_chunks([chunk])
    meta = pinecone.live.data["test-ns"]["a.md::0001"]["metadata"]
    assert meta == {"source": "a.md", "page": 3, "text": "hello"}  # no null, no list


def test_uploading_a_file_again_replaces_its_old_chunks(pinecone):
    store.add_chunks(pieces("a.md", "one", "two", "three") + pieces("b.md", "other"))
    store.add_chunks(pieces("a.md", "new one", "new two"))
    assert stored_ids(pinecone) == ["a.md::0001", "a.md::0002", "b.md::0001"]
    assert pinecone.live.data["test-ns"]["a.md::0001"]["metadata"]["text"] == "new one"


def test_odd_file_names_get_safe_unique_ids(pinecone):
    store.add_chunks(pieces("résumé final.pdf", "x") + pieces("表格.pdf", "y") + pieces("文档.pdf", "z"))
    ids = stored_ids(pinecone)
    assert all(i.isascii() for i in ids)
    assert len(set(ids)) == 3


def test_search_returns_the_best_match_first_with_its_score(pinecone):
    store.add_chunks(
        pieces("vpn.md", "connect to the vpn from home", section="VPN")
        + pieces("wifi.md", "guest wifi password for visitors", section="Wi-Fi")
    )
    best = store.search("how do I connect to the vpn")[0]
    assert best.page_content == "connect to the vpn from home"
    assert best.metadata["source"] == "vpn.md"
    assert best.metadata["section"] == "VPN"
    assert 0 < best.metadata["score"] <= 1
    assert "text" not in best.metadata


def test_search_on_an_empty_namespace_returns_nothing_and_warns(pinecone, caplog):
    store.ensure_index()
    with caplog.at_level(logging.WARNING):
        assert store.search("anything") == []
    assert "looks empty" in caplog.text


def test_chat_search_never_creates_an_index(pinecone):
    with pytest.raises(RuntimeError, match="does not exist"):
        store.search("anything")
    assert pinecone.created == []


def test_a_size_mismatch_stops_with_advice_and_deletes_nothing(pinecone):
    pinecone.live, pinecone.dimension = FakeIndex(), 999
    pinecone.live.data["test-ns"] = {"keep": {"id": "keep", "values": [], "metadata": {}}}
    with pytest.raises(RuntimeError, match="999.*new PINECONE_INDEX_NAME"):
        store.search("anything")
    with pytest.raises(RuntimeError, match="999"):
        store.add_chunks(pieces("a.md", "x"))
    assert pinecone.deleted == []
    assert "keep" in pinecone.live.data["test-ns"]


def test_a_missing_api_key_says_where_to_put_it(pinecone, monkeypatch):
    monkeypatch.setattr(get_settings(), "pinecone_api_key", "")
    with pytest.raises(RuntimeError, match="PINECONE_API_KEY.*\\.env"):
        store.search("anything")


@pytest.mark.parametrize("name", ["My_Index", "UPPER", "-start", "end-", "a" * 46])
def test_a_bad_index_name_is_explained_before_pinecone_sees_it(pinecone, monkeypatch, name):
    monkeypatch.setattr(get_settings(), "pinecone_index_name", name)
    with pytest.raises(RuntimeError, match="not allowed"):
        store.ensure_index()
    assert pinecone.created == []


def test_reset_empties_only_our_namespace(pinecone):
    store.add_chunks(pieces("a.md", "one", "two"))
    pinecone.live.upsert(vectors=[{"id": "x", "values": [], "metadata": {}}], namespace="other-ns")
    store.reset()
    assert store.count() == 0
    assert "x" in pinecone.live.data["other-ns"]


def test_count_reports_the_chunks_in_our_namespace(pinecone):
    store.add_chunks(pieces("a.md", "one", "two", "three"))
    assert store.count() == 3


def test_warm_up_prepares_the_model_and_the_index(pinecone, monkeypatch):
    store.ensure_index()
    asked = []
    monkeypatch.setattr(store, "embed", lambda texts, **kw: asked.append(texts) or [[0.0] * DIM])
    store._index.cache_clear()
    store.warm_up()
    assert asked == [["warm up"]]  # the model was used once
    assert store._index.cache_info().currsize == 1  # and the index is open, so the first question does not open it


def test_warm_up_before_the_first_ingest_says_the_index_is_missing(pinecone):
    with pytest.raises(RuntimeError, match="does not exist"):
        store.warm_up()
    assert pinecone.created == []  # warming up never creates an index


def test_two_callers_at_once_load_the_embedding_model_only_once(monkeypatch):
    loaded = []

    class SlowModel:
        def __init__(self, name):
            time.sleep(0.2)  # long enough for the second caller to arrive while the first is loading
            loaded.append(name)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=SlowModel))
    store._load_model.cache_clear()
    try:
        results = []
        threads = [threading.Thread(target=lambda: results.append(store._model())) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(loaded) == 1 and results[0] is results[1]
    finally:
        store._load_model.cache_clear()
