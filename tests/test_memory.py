from app.agent import memory
from app.config import get_settings


def turn(n, answer="an answer"):
    return {"question": f"question {n}", "answer": answer}


def test_only_the_last_few_exchanges_are_kept(monkeypatch):
    monkeypatch.setattr(get_settings(), "memory_turns", 2)
    assert [t["question"] for t in memory.recent([turn(1), turn(2), turn(3)])] == ["question 2", "question 3"]


def test_long_texts_are_cut_and_put_on_one_line(monkeypatch):
    monkeypatch.setattr(get_settings(), "memory_turns", 3)
    (kept,) = memory.recent([{"question": "a\n\n  b", "answer": "word " * 200}])
    assert kept["question"] == "a b"
    assert len(kept["answer"]) <= memory.MAX_CHARS + 1 and kept["answer"].endswith("…")  # the cut text plus the "…"


def test_the_callers_list_is_left_as_it_was(monkeypatch):
    monkeypatch.setattr(get_settings(), "memory_turns", 3)
    original = [turn(1, "x " * 300)]
    memory.recent(original)
    assert original == [turn(1, "x " * 300)]


def test_a_first_message_has_no_memory_and_memory_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "memory_turns", 3)
    assert memory.recent(None) == memory.recent([]) == []
    monkeypatch.setattr(get_settings(), "memory_turns", 0)
    assert memory.recent([turn(1)]) == []
