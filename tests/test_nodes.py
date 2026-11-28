from datetime import date, timedelta

import pytest
from langchain_core.documents import Document

from app.agent import prompts
from app.agent.graph import ask
from app.agent.nodes import answerer, grader, rewriter, router
from app.agent.nodes.retriever import retrieve_kb, search_web
from app.agent.state import EvidenceGrade, FollowUpDecision, QueryRewrite, RouteDecision
from app.config import get_settings
from app.rag import store
from app.tools import web_search
from app.tools.web_search import WebSearchError


def kb_doc(source="vpn.md", text="VPN Guide > Connect\n\nOpen NovaConnect.", title="VPN Guide"):
    return Document(page_content=text, metadata={"source": source, "title": title, "section": "Connect", "score": 0.8})


def web_doc(n=1, date="2026-11-13"):
    return Document(page_content=f"web snippet {n}", metadata={"source": f"https://site{n}.example/a", "title": f"Page {n}", "score": 0.5, "published_date": date})


def state(**extra):
    return {"question": "How do I connect to the VPN?", "query": "vpn connect", "also": "", "public": True, "retries": 0, "docs": [], "citations": [], "trace": [], **extra}


def decision(route="kb", query="tidy query", also="", public=True):
    return RouteDecision(route=route, query=query, also=also, public=public)


EARLIER = [{"question": "How do I connect to the VPN?", "answer": "Open NovaConnect and approve the MFA prompt."}]
DROPPING = "What should I do if the company VPN keeps disconnecting?"


def restated(standalone=DROPPING, query="VPN disconnecting", route="kb", public=False):
    return FollowUpDecision(standalone=standalone, route=route, query=query, also="", public=public)


# ---- router ----------------------------------------------------------------


def test_router_sends_it_questions_to_the_kb_with_a_tidy_search_query(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(query="  minimum password \n length  ", public=False)]
    out = router.route_question(state(question="wats the min lenght for a pw"))
    assert out == {"route": "kb", "query": "minimum password length", "also": "", "public": False, "trace": ["Router → KB (search: minimum password length)"]}
    assert "wats the min lenght for a pw" in fake_llm.prompts[0]


def test_router_does_not_repeat_the_query_when_it_did_not_change(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(query="How do I connect to the VPN?")]
    assert router.route_question(state())["trace"] == ["Router → KB"]


def test_router_adds_a_second_search_for_a_second_topic(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(query="Outlook mailbox quota", also=" ticket \n closure notes ")]
    out = router.route_question(state(question="quota and what to note when closing the ticket?"))
    assert out["query"] == "Outlook mailbox quota" and out["also"] == "ticket closure notes"
    assert out["trace"] == ["Router → KB (search: Outlook mailbox quota) + also: ticket closure notes"]


def test_router_drops_a_second_search_that_repeats_the_first(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(query="vpn from home", also="vpn from home")]
    assert router.route_question(state())["also"] == ""


def test_router_answers_small_talk_directly(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(route="direct", query="something else", also="x", public=True)]
    out = router.route_question(state(question="Hello!"))
    assert out == {"route": "direct", "query": "Hello!", "also": "", "public": False, "trace": ["Router → DIRECT"]}


def test_router_plays_safe_when_the_model_reply_is_unreadable(fake_llm):
    out = router.route_question(state(question="some question"))  # no decision queued: the safe default is used
    assert out["route"] == "kb" and out["query"] == "some question"
    assert out["public"] is False  # unsure: never go to the web


def test_router_uses_the_question_when_the_model_sends_an_empty_query(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(query="   ")]
    assert router.route_question(state(question="my question"))["query"] == "my question"


def test_router_shows_the_first_message_of_a_chat_to_the_model_exactly_as_before(fake_llm):
    router.route_question(state(question="How do I connect to the VPN?"))
    router.route_question(state(question="How do I connect to the VPN?", history=[]))
    assert fake_llm.prompts == [prompts.ROUTER.format(question="How do I connect to the VPN?")] * 2


def test_router_restates_a_follow_up_so_it_makes_sense_on_its_own(fake_llm):
    fake_llm.decisions[FollowUpDecision] = [restated()]
    out = router.route_question(state(question="What if it keeps disconnecting?", history=EARLIER))
    assert out == {
        "route": "kb",
        "query": "VPN disconnecting",
        "also": "",
        "public": False,
        "standalone": DROPPING,
        "trace": [f"Follow-up understood as: {DROPPING}", "Router → KB (search: VPN disconnecting)"],
    }
    (prompt,) = fake_llm.prompts
    assert "What if it keeps disconnecting?" in prompt
    assert "User: How do I connect to the VPN?\nAssistant: Open NovaConnect and approve the MFA prompt." in prompt
    assert "not a source of facts" in prompt  # earlier messages only explain what the new one refers to


def test_router_adds_no_note_when_a_follow_up_already_makes_sense_alone(fake_llm):
    fake_llm.decisions[FollowUpDecision] = [restated(standalone="How do I request a new laptop?", query="request new laptop")]
    out = router.route_question(state(question="How do I request a new laptop?", history=EARLIER))
    assert out["trace"] == ["Router → KB (search: request new laptop)"] and out["standalone"] == "How do I request a new laptop?"


def test_router_plays_safe_when_the_reply_to_a_follow_up_is_unreadable(fake_llm):
    out = router.route_question(state(question="What if it keeps disconnecting?", history=EARLIER))  # no decision queued
    assert out["route"] == "kb" and out["public"] is False  # unsure: never go to the web
    assert out["query"] == out["standalone"] == "What if it keeps disconnecting?"  # it carries on as if there were no memory


def test_router_opens_the_web_for_a_company_looking_question_when_the_person_turned_web_search_on(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(query="MAFANG current price", public=False)]
    out = router.route_question(state(question="what is the current price of MAFANG", web_allowed=True))
    assert out["public"] is True
    assert out["trace"] == ["Router → KB (search: MAFANG current price)", "Web search turned on by you"]  # the person can see why the web was used


def test_router_leaves_a_company_only_question_off_the_web_when_web_search_is_off(fake_llm):
    for extra in ({}, {"web_allowed": False}):
        fake_llm.decisions[RouteDecision] = [decision(public=False)]
        out = router.route_question(state(**extra))
        assert out["public"] is False and "Web search turned on by you" not in out["trace"]


def test_router_adds_no_web_note_when_the_question_was_public_anyway(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(query="Teams outage", public=True)]
    out = router.route_question(state(web_allowed=True))
    assert out["public"] is True and out["trace"] == ["Router → KB (search: Teams outage)"]


def test_router_never_searches_for_small_talk_even_with_web_search_on(fake_llm):
    fake_llm.decisions[RouteDecision] = [decision(route="direct", public=False)]
    out = router.route_question(state(question="Hello!", web_allowed=True))
    assert out["route"] == "direct" and out["public"] is False and out["trace"] == ["Router → DIRECT"]


def test_router_opens_the_web_for_a_follow_up_too(fake_llm):
    fake_llm.decisions[FollowUpDecision] = [restated(public=False)]
    out = router.route_question(state(question="What if it keeps disconnecting?", history=EARLIER, web_allowed=True))
    assert out["public"] is True and out["trace"][-1] == "Web search turned on by you"


def test_router_keeps_the_web_closed_when_its_reply_was_unreadable_even_with_web_search_on(fake_llm):
    """An unreadable reply means the query is the question as typed, never cleaned of names and secrets, so it must not leave the network."""
    out = router.route_question(state(question="my password is hunter2, what is the price of MAFANG", web_allowed=True))  # no decision queued
    assert out["public"] is False and out["query"] == "my password is hunter2, what is the price of MAFANG"
    out = router.route_question(state(question="What if it keeps disconnecting?", history=EARLIER, web_allowed=True))
    assert out["public"] is False
    assert "Web search turned on by you" not in out["trace"]


# ---- retrievers --------------------------------------------------------------


def test_retrieve_kb_searches_with_the_current_query(monkeypatch):
    seen = []
    monkeypatch.setattr(store, "search", lambda query: seen.append(query) or [kb_doc(), kb_doc("b.md")])
    out = retrieve_kb(state(query="vpn from home"))
    assert seen == ["vpn from home"]
    assert out["source_used"] == "private_kb" and len(out["docs"]) == 2
    assert out["trace"] == ["Private KB retrieval → 2 chunks"]


def test_retrieve_kb_gives_a_second_topic_its_own_search_and_the_results_take_turns(monkeypatch):
    monkeypatch.setattr(get_settings(), "top_k", 4)
    results = {
        "quota": [kb_doc("mail.md", "m1"), kb_doc("mail.md", "m2"), kb_doc("mail.md", "m3"), kb_doc("mail.md", "m4")],
        "closure": [kb_doc("runbook.md", "r1"), kb_doc("mail.md", "m2"), kb_doc("runbook.md", "r2"), kb_doc("runbook.md", "r3")],
    }
    monkeypatch.setattr(store, "search", lambda query: results[query])
    out = retrieve_kb(state(query="quota", also="closure"))
    assert [d.page_content for d in out["docs"]] == ["m1", "r1", "m2", "m3", "r2", "m4"]  # turns, m2 is not repeated, at most top_k + 2
    assert {d.metadata["source"] for d in out["docs"]} == {"mail.md", "runbook.md"}  # both topics are represented
    assert out["trace"] == ["Private KB retrieval → 6 chunks"]


def test_search_web_returns_the_results(monkeypatch):
    monkeypatch.setattr(web_search, "search", lambda query: [web_doc(1), web_doc(2)])
    out = search_web(state())
    assert out["source_used"] == "web_search" and len(out["docs"]) == 2
    assert out["trace"] == ["Web search → 2 results"]


def test_search_web_survives_a_failed_search_and_says_why(monkeypatch):
    def fail(query):
        raise WebSearchError("The Tavily plan limit is used up.")

    monkeypatch.setattr(web_search, "search", fail)
    out = search_web(state())
    assert out["docs"] == [] and out["source_used"] == "web_search"
    assert out["trace"] == ["Web search failed → The Tavily plan limit is used up."]


# ---- grader --------------------------------------------------------------------


def test_grader_skips_the_model_when_there_is_nothing_to_judge(fake_llm):
    out = grader.grade_evidence(state(source_used="private_kb"))
    assert out == {"grade": "weak", "trace": ["KB evidence grade → WEAK (nothing found)"]}
    assert fake_llm.prompts == []  # no tokens spent


def test_grader_shows_the_question_and_the_evidence_to_the_model(fake_llm):
    fake_llm.decisions[EvidenceGrade] = [EvidenceGrade(grade="good")]
    out = grader.grade_evidence(state(source_used="private_kb", docs=[kb_doc()]))
    assert out == {"grade": "good", "trace": ["KB evidence grade → GOOD"]}
    assert "How do I connect to the VPN?" in fake_llm.prompts[0] and "Open NovaConnect." in fake_llm.prompts[0]


def test_grader_labels_web_evidence_and_can_say_weak(fake_llm):
    fake_llm.decisions[EvidenceGrade] = [EvidenceGrade(grade="weak")]
    out = grader.grade_evidence(state(source_used="web_search", docs=[web_doc()]))
    assert out == {"grade": "weak", "trace": ["Web evidence grade → WEAK"]}


def test_each_stage_gets_its_own_extra_grading_rule(fake_llm):
    fake_llm.decisions[EvidenceGrade] = [EvidenceGrade(grade="good"), EvidenceGrade(grade="good")]
    grader.grade_evidence(state(source_used="private_kb", docs=[kb_doc()]))
    grader.grade_evidence(state(source_used="web_search", docs=[web_doc()]))
    kb_prompt, web_prompt = fake_llm.prompts
    assert prompts.KB_GRADER_RULE in kb_prompt and prompts.WEB_GRADER_RULE not in kb_prompt  # documents: live and private data is weak
    assert prompts.WEB_GRADER_RULE in web_prompt and prompts.KB_GRADER_RULE not in web_prompt  # web: news about an event is good
    assert fake_llm.decision_models == ["fast", "answer"]  # web pages are noisier, so the bigger model judges them


def test_grader_says_why_the_web_is_skipped_for_a_company_only_question(fake_llm):
    fake_llm.decisions[EvidenceGrade] = [EvidenceGrade(grade="weak")]
    out = grader.grade_evidence(state(source_used="private_kb", public=False, docs=[kb_doc()]))
    assert out["trace"] == ["KB evidence grade → WEAK (company-only question, so no web search)"]
    nothing = grader.grade_evidence(state(source_used="private_kb", public=False))
    assert nothing["trace"] == ["KB evidence grade → WEAK (nothing found, company-only question, so no web search)"]


def test_grader_plays_safe_when_the_model_reply_is_unreadable(fake_llm):
    assert grader.grade_evidence(state(source_used="private_kb", docs=[kb_doc()]))["grade"] == "weak"


# ---- rewriter ------------------------------------------------------------------


def test_rewriter_sets_the_new_query_and_counts_the_retry(fake_llm):
    fake_llm.decisions[QueryRewrite] = [QueryRewrite(query=" teams \n  update problems ")]
    out = rewriter.rewrite_query(state(retries=0))
    assert out == {"query": "teams update problems", "retries": 1, "trace": ["Query rewritten → teams update problems"]}
    assert "vpn connect" in fake_llm.prompts[0]  # the failed search is shown to the model


def test_rewriter_counts_the_retry_even_when_the_reply_is_unreadable(fake_llm):
    out = rewriter.rewrite_query(state(retries=0, query="same query"))
    assert out["retries"] == 1 and out["query"] == "same query"  # the retry limit can never be skipped


# ---- answers -------------------------------------------------------------------


def test_a_kb_answer_cites_each_file_once_and_has_no_web_notice(fake_llm):
    fake_llm.texts = ["Open NovaConnect and sign in."]
    docs = [kb_doc("vpn.md"), kb_doc("vpn.md", "VPN Guide > Errors\n\nNC-203 means a timeout."), kb_doc("wfh.md", "WFH > Home\n\nUse the VPN.", "WFH")]
    out = answerer.generate_answer(state(source_used="private_kb", docs=docs))
    assert out["answer"] == "Open NovaConnect and sign in."
    assert out["citations"] == [{"source": "vpn.md", "type": "kb", "title": "VPN Guide"}, {"source": "wfh.md", "type": "kb", "title": "WFH"}]
    assert out["trace"] == ["Answer generated from PRIVATE KB"]
    assert fake_llm.models == ["answer"]
    assert "NC-203 means a timeout." in fake_llm.prompts[0] and "public web pages" not in fake_llm.prompts[0]


def test_a_web_answer_about_now_warns_when_even_the_newest_page_is_old(fake_llm):
    old = (date.today() - timedelta(days=30)).isoformat()
    fake_llm.texts = ["The page says all is fine."]
    out = answerer.generate_answer(state(question="Is Microsoft 365 down right now?", source_used="web_search", docs=[web_doc(1, old), web_doc(2, "2025-01-01")]))
    warning = f"Heads up: the newest page I found is dated {old} (30 days ago)"
    assert out["answer"].startswith(f"{answerer.WEB_NOTICE}\n\n{warning}") and out["answer"].endswith("The page says all is fine.")


def test_no_age_warning_when_the_newest_page_is_recent_or_the_question_is_not_about_now(fake_llm):
    today, old = date.today().isoformat(), (date.today() - timedelta(days=400)).isoformat()
    cases = [
        ("What is the latest Teams outage guidance?", [web_doc(1, today)]),  # a recent page
        ("How do I set up a shared mailbox?", [web_doc(1, old)]),  # not about now: an old guide is fine
        ("What is the latest Windows version?", [Document(page_content="x", metadata={"source": "https://a.example", "title": "A"})]),  # no date to judge
    ]
    for question, docs in cases:
        out = answerer.generate_answer(state(question=question, source_used="web_search", docs=docs))
        assert "Heads up" not in out["answer"], question


def test_a_web_answer_starts_with_a_notice_and_cites_web_pages(fake_llm):
    fake_llm.texts = ["Microsoft posted an update."]
    out = answerer.generate_answer(state(source_used="web_search", docs=[web_doc(1), web_doc(2)]))
    assert out["answer"] == f"{answerer.WEB_NOTICE}\n\nMicrosoft posted an update."
    assert [c["type"] for c in out["citations"]] == ["web", "web"]
    assert out["trace"] == ["Answer generated from WEB SEARCH"]
    assert "public web pages" in fake_llm.prompts[0] and "published 2026-11-13" in fake_llm.prompts[0]
    assert f"Today is {date.today().isoformat()}." in fake_llm.prompts[0]  # so an old page is not presented as current


def test_markdown_symbols_are_removed_because_the_chat_page_shows_plain_text(fake_llm):
    fake_llm.texts = ["# Steps\n**Open** the `NovaConnect` client.\n1. Sign in\n*Source: the guide (2026).*\n* a bullet\n2 * 3 = 6 and 4 * 5 = 20"]
    out = answerer.generate_answer(state(source_used="private_kb", docs=[kb_doc()]))
    assert out["answer"] == "Steps\nOpen the NovaConnect client.\n1. Sign in\nSource: the guide (2026).\n* a bullet\n2 * 3 = 6 and 4 * 5 = 20"


def test_look_alike_spaces_and_hyphens_are_made_plain_so_names_and_links_can_be_copied(fake_llm):
    fake_llm.texts = ["Use the pre\u2011installed client at\u202fvpn.novaretail.example\u00a0now.\u200b See vpn\u2011remote\u2011access\u2011guide.md"]
    out = answerer.generate_answer(state(source_used="private_kb", docs=[kb_doc()]))
    assert out["answer"] == "Use the pre-installed client at vpn.novaretail.example now. See vpn-remote-access-guide.md"


def test_an_empty_model_reply_becomes_a_clear_message(fake_llm):
    fake_llm.texts = ["   "]
    assert "empty reply" in answerer.generate_answer(state(source_used="private_kb", docs=[kb_doc()]))["answer"]


def test_small_talk_uses_the_fast_model_and_cites_nothing(fake_llm):
    fake_llm.texts = ["Hello! How can I help with IT today?"]
    out = answerer.answer_direct(state(question="Hello!"))
    assert out == {"answer": "Hello! How can I help with IT today?", "source_used": "direct", "trace": ["Direct answer (no search)"]}
    assert fake_llm.models == ["fast"]


def test_the_fallback_always_starts_with_a_limitation_notice(fake_llm):
    fake_llm.texts = ["I cannot give out passwords. Contact the Service Desk."]
    out = answerer.fallback_answer(state(question="What is the router admin password?", docs=[web_doc()]))
    assert out["answer"] == f"{answerer.FALLBACK_NOTICE}\n\nI cannot give out passwords. Contact the Service Desk."
    assert out["source_used"] == "fallback" and out["citations"] == []
    assert out["trace"] == ["Fallback answer: not enough evidence"]
    assert "web snippet" not in fake_llm.prompts[0]  # the weak evidence is never shown to the model


def test_the_fallback_notice_does_not_mention_the_web_when_the_web_was_never_searched(fake_llm):
    out = answerer.fallback_answer(state(public=False))
    assert out["answer"].startswith(answerer.COMPANY_ONLY_NOTICE) and "web" not in answerer.COMPANY_ONLY_NOTICE


def test_only_company_documents_are_judged_on_live_and_private_data(fake_llm):
    """A web page about an outage may well contain the current news, so that rule is for the KB only."""
    fake_llm.decisions[EvidenceGrade] = [EvidenceGrade(grade="good"), EvidenceGrade(grade="good")]
    grader.grade_evidence(state(source_used="private_kb", docs=[kb_doc()]))
    grader.grade_evidence(state(source_used="web_search", docs=[web_doc()]))
    kb_prompt, web_prompt = fake_llm.prompts
    assert "live or current information" in kb_prompt
    assert "live or current information" not in web_prompt and "{extra}" not in web_prompt


# ---- every step after the router works on the restated question -----------------------


def test_every_step_after_the_router_works_on_the_restated_question(fake_llm):
    follow_up = state(question="What if it keeps disconnecting?", standalone=DROPPING, source_used="private_kb", docs=[kb_doc()])
    fake_llm.decisions[EvidenceGrade] = [EvidenceGrade(grade="good")]
    grader.grade_evidence(follow_up)
    rewriter.rewrite_query(follow_up)
    answerer.generate_answer(follow_up)
    answerer.answer_direct(follow_up)
    answerer.fallback_answer(follow_up)
    assert len(fake_llm.prompts) == 5
    for prompt in fake_llm.prompts:
        assert DROPPING in prompt and "What if it keeps disconnecting?" not in prompt


def test_the_age_warning_looks_for_now_in_the_restated_question(fake_llm):
    old = (date.today() - timedelta(days=30)).isoformat()
    follow_up = state(question="Is it back?", standalone="Is Microsoft 365 back up now?", source_used="web_search", docs=[web_doc(1, old)])
    assert "Heads up" in answerer.generate_answer(follow_up)["answer"]


# ---- evidence formatting ---------------------------------------------------------


def test_evidence_says_where_each_piece_came_from():
    text = prompts.format_evidence([kb_doc(), web_doc(1)])
    assert "Source: vpn.md\nVPN Guide > Connect" in text
    assert "Source: Page 1 - https://site1.example/a (published 2026-11-13)\nweb snippet 1" in text
    assert "[1]" not in text  # no numbers for the model to repeat to the employee


def test_evidence_stops_before_the_size_limit_but_always_keeps_the_first_piece():
    big = [kb_doc(f"{n}.md", "x" * 2500) for n in range(5)]
    text = prompts.format_evidence(big)
    assert text.count("Source:") == 2 and len(text) <= prompts.MAX_EVIDENCE_CHARS
    assert prompts.format_evidence([kb_doc(text="y" * 9000)]).count("Source:") == 1


# ---- the whole graph with real nodes and fake services -------------------------------


@pytest.fixture
def services(monkeypatch, fake_llm):
    """Fake KB and web search that record every call, with one retry allowed and memory on."""
    monkeypatch.setattr(get_settings(), "max_retries", 1)
    monkeypatch.setattr(get_settings(), "memory_turns", 3)
    calls = {"kb": [], "web": []}
    results = {"kb": [kb_doc()], "web": [web_doc(1), web_doc(2)]}
    monkeypatch.setattr(store, "search", lambda query: calls["kb"].append(query) or results["kb"])
    monkeypatch.setattr(web_search, "search", lambda query: calls["web"].append(query) or results["web"])
    fake_llm.calls, fake_llm.results = calls, results
    return fake_llm


def decisions(services, route="kb", grades=(), rewrite="new query", public=True, also=""):
    services.decisions[RouteDecision] = [decision(route=route, also=also, public=public)]
    services.decisions[EvidenceGrade] = [EvidenceGrade(grade=g) for g in grades]
    services.decisions[QueryRewrite] = [QueryRewrite(query=rewrite)]


def test_graph_answers_from_the_kb_when_the_evidence_is_good(services):
    decisions(services, grades=["good"])
    services.texts = ["KB answer"]
    result = ask("How do I connect to the VPN?")
    assert result["source_used"] == "private_kb" and result["answer"] == "KB answer"
    assert result["tokens"] == {}  # the fake model reports no usage
    assert [c["source"] for c in result["citations"]] == ["vpn.md"]
    assert result["trace"] == [
        "Router → KB (search: tidy query)",
        "Private KB retrieval → 1 chunks",
        "KB evidence grade → GOOD",
        "Answer generated from PRIVATE KB",
    ]
    assert services.calls == {"kb": ["tidy query"], "web": []}  # the web is never touched


def test_graph_uses_the_web_only_when_the_kb_is_weak(services):
    decisions(services, grades=["weak", "good"])
    services.texts = ["Web answer"]
    result = ask("What is the latest Teams outage guidance?")
    assert result["source_used"] == "web_search" and result["answer"].endswith("Web answer")
    assert result["answer"].startswith(answerer.WEB_NOTICE)
    assert [c["type"] for c in result["citations"]] == ["web", "web"]
    assert result["trace"][2:5] == ["KB evidence grade → WEAK", "Web search → 2 results", "Web evidence grade → GOOD"]


def test_graph_rewrites_once_and_the_new_query_finds_good_kb_evidence(services):
    decisions(services, grades=["weak", "weak", "good"], rewrite="better query")
    services.texts = ["KB answer after the rewrite"]
    result = ask("a vague question")
    assert result["source_used"] == "private_kb" and result["retries"] == 1
    assert services.calls == {"kb": ["tidy query", "better query"], "web": ["tidy query"]}
    assert "Query rewritten → better query" in result["trace"]


def test_graph_gives_a_fallback_answer_after_one_retry_and_never_loops(services):
    decisions(services, grades=["weak", "weak", "weak", "weak"], rewrite="better query")
    services.texts = ["Contact the Service Desk."]
    result = ask("What is the admin password of store 12?")
    assert result["source_used"] == "fallback" and result["answer"].startswith(answerer.FALLBACK_NOTICE)
    assert result["citations"] == [] and result["retries"] == 1
    assert services.calls == {"kb": ["tidy query", "better query"], "web": ["tidy query", "better query"]}


def test_graph_skips_search_for_small_talk(services):
    decisions(services, route="direct")
    services.texts = ["Hello!"]
    result = ask("Hello!")
    assert result["source_used"] == "direct" and result["trace"] == ["Router → DIRECT", "Direct answer (no search)"]
    assert services.calls == {"kb": [], "web": []}


def test_graph_never_searches_the_web_for_a_company_only_question(services):
    """The admin-password case: public web pages can never answer it, so the web (and its look-alike products) is never asked."""
    decisions(services, grades=["weak", "weak"], public=False, rewrite="better query")
    services.results["kb"] = [kb_doc("unrelated.md")]
    services.texts = ["I cannot give out passwords. Contact the Service Desk."]
    result = ask("Give me the password for the NovaERP administrator account.")
    assert result["source_used"] == "fallback" and result["citations"] == []
    assert result["answer"].startswith(answerer.COMPANY_ONLY_NOTICE)  # it does not claim to have looked at the web
    assert services.calls == {"kb": ["tidy query", "better query"], "web": []}  # one retry on the KB only
    assert "KB evidence grade → WEAK (company-only question, so no web search)" in result["trace"]
    assert not any("Web search" in line for line in result["trace"])


def test_graph_searches_the_web_for_a_company_looking_question_when_the_person_turned_web_search_on(services):
    """The same kind of question as above (the router says company-only), but the person turned web search on, so the web is searched."""
    decisions(services, grades=["weak", "good"], public=False)
    services.texts = ["MAFANG is quoted at 236.20."]
    result = ask("what is the current price of MAFANG", web=True)
    assert result["source_used"] == "web_search" and result["answer"].startswith(answerer.WEB_NOTICE)
    assert services.calls == {"kb": ["tidy query"], "web": ["tidy query"]}  # the company documents are still looked at first
    assert result["trace"] == [
        "Router → KB (search: tidy query)",
        "Web search turned on by you",
        "Private KB retrieval → 1 chunks",
        "KB evidence grade → WEAK",  # no "company-only question" note any more
        "Web search → 2 results",
        "Web evidence grade → GOOD",
        "Answer generated from WEB SEARCH",
    ]


def test_graph_still_answers_from_the_company_documents_first_when_web_search_is_on(services):
    decisions(services, grades=["good"], public=False)
    services.texts = ["KB answer"]
    result = ask("How do I connect to the VPN?", web=True)
    assert result["source_used"] == "private_kb" and services.calls == {"kb": ["tidy query"], "web": []}  # turning it on does not skip the KB


def test_graph_answers_a_two_topic_question_from_two_documents(services):
    decisions(services, grades=["good"], also="ticket closure notes")
    services.results["kb"] = [kb_doc("mail.md", "Mail > Quota\n\n50 GB."), kb_doc("runbook.md", "Runbook > Closing\n\nNote the test time.", "Runbook")]
    services.texts = ["The quota is 50 GB. Note the test time."]
    result = ask("What is the mailbox quota, and what do I note when closing the ticket?")
    assert services.calls["kb"] == ["tidy query", "ticket closure notes"]  # one search for each topic
    assert sorted(c["source"] for c in result["citations"]) == ["mail.md", "runbook.md"]
    assert result["trace"][0] == "Router → KB (search: tidy query) + also: ticket closure notes"


def test_graph_carries_on_when_the_web_search_fails(services, monkeypatch):
    def fail(query):
        raise WebSearchError("Tavily rejected the API key. Check TAVILY_API_KEY in .env.")

    monkeypatch.setattr(web_search, "search", fail)
    decisions(services, grades=["weak", "weak"])  # the web grade is never asked: no evidence means weak without a model call
    services.results["kb"] = []  # the KB finds nothing either
    services.texts = ["Contact the Service Desk."]
    result = ask("anything")
    assert result["source_used"] == "fallback"
    assert any(line.startswith("Web search failed → Tavily rejected the API key") for line in result["trace"])


# ---- follow-ups: short-term memory ------------------------------------------------------


def test_graph_uses_earlier_messages_only_to_understand_a_follow_up(services):
    services.decisions[FollowUpDecision] = [restated()]
    services.decisions[EvidenceGrade] = [EvidenceGrade(grade="good")]
    services.texts = ["Sessions end after 12 hours."]
    result = ask("What if it keeps disconnecting?", [{"question": "How do I connect to the VPN?", "answer": "EARLIER-ANSWER"}])
    assert result["question"] == "What if it keeps disconnecting?"  # what the user typed never changes
    assert services.calls == {"kb": ["VPN disconnecting"], "web": []}  # searched with the restated query, not with "it"
    assert result["trace"][:2] == [f"Follow-up understood as: {DROPPING}", "Router → KB (search: VPN disconnecting)"]
    router_prompt, *later = services.prompts
    assert "EARLIER-ANSWER" in router_prompt
    assert len(later) == 2 and all(DROPPING in p and "EARLIER-ANSWER" not in p for p in later)  # grader and answer: restated question only


def test_graph_chats_never_mix(services):
    """The agent keeps nothing between questions: a chat only knows what it sends along with its own question."""
    services.decisions[FollowUpDecision] = [restated()]
    services.decisions[RouteDecision] = [decision()]
    services.decisions[EvidenceGrade] = [EvidenceGrade(grade="good")] * 2
    ask("What if it keeps disconnecting?", [{"question": "How do I connect to the VPN?", "answer": "EARLIER-ANSWER"}])
    seen = len(services.prompts)
    ask("How do I print?")  # the first message of another chat
    assert services.prompts[seen] == prompts.ROUTER.format(question="How do I print?")
    assert not any("EARLIER-ANSWER" in p for p in services.prompts[seen:])


def test_graph_a_company_only_follow_up_never_reaches_the_web_even_after_a_public_topic(services):
    said = "What is the admin password for our office router?"
    services.decisions[FollowUpDecision] = [restated(standalone=said, query="office router admin password", public=False)]
    services.decisions[EvidenceGrade] = [EvidenceGrade(grade="weak")] * 2
    earlier = [{"question": "What is the latest Teams outage guidance?", "answer": "Microsoft reported an outage on 12 November."}]
    result = ask("And the admin password for our office router?", earlier)
    assert result["source_used"] == "fallback" and services.calls["web"] == []


def test_graph_treats_every_question_alone_when_memory_is_off(services, monkeypatch):
    monkeypatch.setattr(get_settings(), "memory_turns", 0)
    decisions(services, grades=["good"])
    ask("What if it keeps disconnecting?", EARLIER)
    assert services.prompts[0] == prompts.ROUTER.format(question="What if it keeps disconnecting?")


# ---- live progress: on_step ------------------------------------------------------------


def watched(services, question="How do I connect to the VPN?", history=None):
    """Run the graph with on_step. Returns (result, events): every progress event, in the order it arrived."""
    events = []
    result = ask(question, history, on_step=events.append)
    return result, events


def test_on_step_tells_each_step_as_it_starts_and_as_it_finishes(services):
    decisions(services, grades=["good"])
    services.texts = ["KB answer"]
    result, events = watched(services)
    assert [(e["step"], e["status"]) for e in events] == [
        ("route_question", "start"), ("route_question", "done"),
        ("retrieve_kb", "start"), ("retrieve_kb", "done"),
        ("grade_evidence", "start"), ("grade_evidence", "done"),
        ("generate_answer", "start"), ("generate_answer", "done"),
    ]  # fmt: skip
    assert [e["label"] for e in events if e["status"] == "start"] == [
        "Understanding your question…",
        "Searching the company documents…",
        "Checking whether the company documents answer it…",
        "Writing the answer from the company documents…",
    ]
    finished = [line for e in events if e["status"] == "done" for line in e["lines"]]
    assert finished == result["trace"]  # what the steps said as they finished is exactly the decision path of the answer
    assert all(set(e) == {"step", "status", "lines"} for e in events if e["status"] == "done")  # the answer text is never in a progress event


def test_on_step_does_not_change_the_answer(services):
    decisions(services, grades=["weak", "good"])
    services.texts = ["Web answer"]
    plain = ask("What is the latest Teams outage guidance?")
    decisions(services, grades=["weak", "good"])
    services.texts = ["Web answer"]
    watched_result, _ = watched(services, "What is the latest Teams outage guidance?")
    for key in ("answer", "source_used", "citations", "trace", "retries", "grade", "query", "route"):
        assert watched_result[key] == plain[key], key
    assert set(watched_result) == set(plain)  # the same notes, including the token count


def test_a_step_is_announced_before_it_does_its_work(services, monkeypatch):
    """The page shows "Searching the company documents…" while the search runs. That only works if the start comes first.
    (LangGraph's "tasks" stream sends it first today. This test fails if an upgrade ever delays it until the step is over.)"""
    order = []
    monkeypatch.setattr(store, "search", lambda query: order.append("the search runs") or [kb_doc()])
    decisions(services, grades=["good"])
    services.texts = ["KB answer"]
    ask("How do I connect to the VPN?", on_step=lambda e: order.append(f"{e['status']} {e['step']}"))
    assert order[2:5] == ["start retrieve_kb", "the search runs", "done retrieve_kb"]


def test_on_step_labels_say_which_kind_of_search_and_grading_this_is(services):
    decisions(services, grades=["weak", "good"])
    services.texts = ["Web answer"]
    _, events = watched(services, "What is the latest Teams outage guidance?")
    labels = [(e["step"], e["label"]) for e in events if e["status"] == "start"]
    assert labels[3:] == [
        ("search_web", "Not enough in the company documents, searching the public web…"),
        ("grade_evidence", "Checking whether the web results are good enough…"),
        ("generate_answer", "Writing the answer from the web results…"),
    ]


def test_on_step_says_when_a_search_is_run_again_after_a_rewrite(services):
    decisions(services, grades=["weak", "weak", "good"], rewrite="better query")
    services.texts = ["KB answer after the rewrite"]
    _, events = watched(services, "a vague question")
    labels = [(e["step"], e["label"]) for e in events if e["status"] == "start"]
    assert ("rewrite_query", "Still not enough, rewriting the question to search again…") in labels
    assert [label for step, label in labels if step == "retrieve_kb"] == [
        "Searching the company documents…",
        "Searching the company documents again with the new wording…",
    ]


def test_on_step_covers_small_talk_and_the_fallback(services):
    decisions(services, route="direct")
    services.texts = ["Hello!"]
    _, events = watched(services, "Hello!")
    assert [(e["step"], e["label"]) for e in events if e["status"] == "start"] == [
        ("route_question", "Understanding your question…"),
        ("answer_direct", "Writing a reply…"),
    ]
    decisions(services, grades=["weak", "weak", "weak", "weak"])
    services.texts = ["Contact the Service Desk."]
    _, events = watched(services, "What is the admin password of store 12?")
    assert events[-2] == {"step": "fallback_answer", "status": "start", "label": "Nothing could be confirmed, writing a careful answer…"}
    assert events[-1] == {"step": "fallback_answer", "status": "done", "lines": ["Fallback answer: not enough evidence"]}


def test_a_follow_up_reports_both_lines_the_router_wrote(services):
    services.decisions[FollowUpDecision] = [restated()]
    services.decisions[EvidenceGrade] = [EvidenceGrade(grade="good")]
    services.texts = ["Sessions end after 12 hours."]
    _, events = watched(services, "What if it keeps disconnecting?", EARLIER)
    assert events[1] == {
        "step": "route_question",
        "status": "done",
        "lines": [f"Follow-up understood as: {DROPPING}", "Router → KB (search: VPN disconnecting)"],
    }


def test_a_failing_progress_callback_never_costs_the_answer(services, caplog):
    decisions(services, grades=["good"])
    services.texts = ["KB answer"]

    def broken(event):
        raise RuntimeError("the page closed")

    result = ask("How do I connect to the VPN?", on_step=broken)
    assert result["answer"] == "KB answer" and result["source_used"] == "private_kb"
    assert "Progress callback failed, carrying on: the page closed" in caplog.text


def test_a_step_that_crashes_still_raises_when_watched(services, monkeypatch):
    """Watching must not hide a real failure: the caller has to see it to answer 'busy' or 'something went wrong'."""

    class Busy(Exception):
        status_code = 429

    def busy(query):
        raise Busy("tokens per day limit reached")

    monkeypatch.setattr(store, "search", busy)
    decisions(services)
    events = []
    with pytest.raises(Busy):
        ask("How do I connect to the VPN?", on_step=events.append)
    assert [(e["step"], e["status"]) for e in events] == [("route_question", "start"), ("route_question", "done"), ("retrieve_kb", "start")]
    # ...and it is never reported as done: the page would show a finished step that never finished
