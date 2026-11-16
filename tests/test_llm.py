import httpx
import pytest
from groq import BadRequestError
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

from app.agent import llm
from app.agent.state import EvidenceGrade
from app.config import get_settings


class FakeStructuredModel:
    """What ChatGroq(...).with_structured_output(...) returns: something with .invoke()."""

    def __init__(self, outcome):
        self.outcome, self.asked = outcome, []

    def with_structured_output(self, schema, **options):
        self.asked.append((schema, options))
        return self

    def invoke(self, prompt):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def fast_model(monkeypatch):
    def install(outcome):
        model = FakeStructuredModel(outcome)
        monkeypatch.setattr(llm, "get_llm", lambda fast=False: model if fast else pytest.fail("a decision must use the fast model"))
        return model

    return install


def test_a_decision_uses_the_fast_model_with_strict_json(fast_model):
    model = fast_model(EvidenceGrade(grade="good"))
    assert llm.decide(EvidenceGrade, "prompt", EvidenceGrade(grade="weak")).grade == "good"
    assert model.asked == [(EvidenceGrade, {"method": "json_schema", "strict": True})]


def test_a_harder_decision_can_ask_for_the_bigger_model(monkeypatch):
    model, used = FakeStructuredModel(EvidenceGrade(grade="good")), []
    monkeypatch.setattr(llm, "get_llm", lambda fast=False: used.append(fast) or model)
    assert llm.decide(EvidenceGrade, "prompt", EvidenceGrade(grade="weak"), fast=False).grade == "good"
    assert used == [False]


@pytest.mark.parametrize("problem", [OutputParserException("not json"), ValidationError.from_exception_data("EvidenceGrade", [])])
def test_an_unreadable_decision_gives_the_safe_default(fast_model, problem):
    fast_model(problem)
    assert llm.decide(EvidenceGrade, "prompt", EvidenceGrade(grade="weak")).grade == "weak"


def test_other_errors_are_not_hidden(fast_model):
    fast_model(RuntimeError("the service is down"))
    with pytest.raises(RuntimeError, match="the service is down"):
        llm.decide(EvidenceGrade, "prompt", EvidenceGrade(grade="weak"))


def bad_request(message):
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.test/chat"))
    return BadRequestError(message, response=response, body={"error": {"message": message}})


def test_a_decision_the_model_did_not_finish_gives_the_safe_default(fast_model):
    fast_model(bad_request("json_validate_failed: max completion tokens reached before generating a valid document"))
    assert llm.decide(EvidenceGrade, "prompt", EvidenceGrade(grade="weak")).grade == "weak"


def test_other_bad_requests_are_not_hidden(fast_model):
    fast_model(bad_request("the prompt is too long"))
    with pytest.raises(BadRequestError):
        llm.decide(EvidenceGrade, "prompt", EvidenceGrade(grade="weak"))


def test_a_query_is_made_one_line_and_short_with_a_fallback():
    assert llm.one_line("  a \n  b\tc ", "fallback") == "a b c"
    assert llm.one_line("  \n ", "fallback") == "fallback"
    assert len(llm.one_line("word " * 200, "fallback")) == 300


def test_a_missing_groq_key_says_where_to_put_it(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    llm.get_llm.cache_clear()
    with pytest.raises(RuntimeError, match=r"GROQ_API_KEY.*\.env"):
        llm.get_llm()
    llm.get_llm.cache_clear()


def test_the_two_models_are_different_and_cheap_to_run(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_key", "gsk_test")
    llm.get_llm.cache_clear()
    answer, fast = llm.get_llm(), llm.get_llm(fast=True)
    assert answer.model_name == settings.groq_model and fast.model_name == settings.groq_fast_model
    assert answer.model_name != fast.model_name  # two models = two separate token budgets on Groq
    assert answer.reasoning_effort == fast.reasoning_effort == "low"
    assert fast.max_tokens < answer.max_tokens
    assert llm.get_llm() is answer and llm.get_llm(fast=True) is fast  # one client for each
    llm.get_llm.cache_clear()
