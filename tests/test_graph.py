import pytest

from app.agent import graph
from app.agent.graph import after_grade, after_router, build_graph
from app.config import get_settings

KB = ["route_question", "retrieve_kb", "grade_evidence"]
WEB = ["search_web", "grade_evidence"]


def test_chat_goes_straight_to_a_direct_answer():
    assert after_router({"route": "direct"}) == "answer_direct"
    assert after_router({"route": "kb"}) == "retrieve_kb"


def test_good_evidence_goes_to_an_answer():
    assert after_grade({"grade": "good", "source_used": "private_kb", "public": False, "retries": 0}) == "generate_answer"
    assert after_grade({"grade": "good", "source_used": "web_search", "public": True, "retries": 0}) == "generate_answer"


def test_weak_kb_evidence_goes_to_web_search_only_when_public_pages_could_help():
    assert after_grade({"grade": "weak", "source_used": "private_kb", "public": True, "retries": 0}) == "search_web"


def test_a_company_only_question_never_goes_to_the_web(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_retries", 1)
    company_only = {"grade": "weak", "source_used": "private_kb", "public": False, "retries": 0}
    assert after_grade(company_only) == "rewrite_query"  # one more try at the KB with a better query
    assert after_grade({**company_only, "retries": 1}) == "fallback_answer"  # then give up. Never search_web.


def test_weak_web_evidence_rewrites_once_then_falls_back(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_retries", 1)
    weak_web = {"grade": "weak", "source_used": "web_search", "public": True, "retries": 0}
    assert after_grade(weak_web) == "rewrite_query"
    assert after_grade({**weak_web, "retries": 1}) == "fallback_answer"


def test_graph_builds():
    assert build_graph() is not None


@pytest.mark.parametrize(
    "route, public, grades, expected",
    [
        ("direct", False, [], ["route_question", "answer_direct"]),
        ("kb", True, ["good"], [*KB, "generate_answer"]),
        ("kb", True, ["weak", "good"], [*KB, *WEB, "generate_answer"]),
        # weak everywhere: KB, web, rewrite once, KB, web, then the fallback answer
        ("kb", True, ["weak"] * 4, [*KB, *WEB, "rewrite_query", "retrieve_kb", "grade_evidence", *WEB, "fallback_answer"]),
        # a company-only question skips the web: KB, rewrite once, KB, then the fallback answer
        ("kb", False, ["weak"] * 2, [*KB, "rewrite_query", "retrieve_kb", "grade_evidence", "fallback_answer"]),
    ],
)
def test_whole_paths_with_fake_steps(monkeypatch, route, public, grades, expected):
    monkeypatch.setattr(get_settings(), "max_retries", 1)
    ran, grades = [], iter(grades)
    fakes = {
        "route_question": lambda s: {"route": route, "public": public},
        "retrieve_kb": lambda s: {"source_used": "private_kb"},
        "search_web": lambda s: {"source_used": "web_search"},
        "grade_evidence": lambda s: {"grade": next(grades)},
        "rewrite_query": lambda s: {"retries": s["retries"] + 1},
        "generate_answer": lambda s: {"answer": "ok"},
        "answer_direct": lambda s: {"answer": "ok"},
        "fallback_answer": lambda s: {"answer": "ok"},
    }
    for name, fake in fakes.items():

        def step(state, name=name, fake=fake):
            ran.append(name)
            return fake(state)

        step.__name__ = name
        monkeypatch.setattr(graph, name, step)

    build_graph().invoke({"question": "q", "query": "q", "also": "", "public": False, "retries": 0, "docs": [], "citations": [], "trace": []})
    assert ran == expected
