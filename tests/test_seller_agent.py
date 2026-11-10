import json
import types

import httpx
from groq import AuthenticationError, NotFoundError, RateLimitError

from backend.agent.seller_agent import SellerAgent


def _resp(code):
    return httpx.Response(code, request=httpx.Request("POST", "https://api.groq.com/test"))


def _json(reply="Test reply?", **extra):
    data = {
        "reply": reply,
        "topic_covered": None,
        "seller_facts": [],
        "recommendations_given": False,
        "agreed_actions": [],
        "conversation_complete": False,
    }
    data.update(extra)
    return json.dumps(data)


class FakeClient:
    """Mimics client.chat.completions.create() with scripted outputs."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls += 1
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        message = types.SimpleNamespace(content=out)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def test_greeting_is_professional_and_has_no_numbers_yet():
    agent = SellerAgent(client=FakeClient([]))
    text = agent.greeting()
    assert "Rahul" in text
    assert "Virtual Key Account Manager" in text
    assert "32.5" not in text


def test_empty_message_is_rejected_without_api_call():
    client = FakeClient([])
    agent = SellerAgent(client=client)
    result = agent.respond("   ")
    assert not result.ok and result.error_type == "empty_message"
    assert client.calls == 0


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    result = SellerAgent().respond("my sales dropped")
    assert not result.ok and result.error_type == "missing_api_key"


def test_successful_turn_updates_state_and_history():
    client = FakeClient([_json(
        "Are any of them your best sellers?",
        topic_covered="stockouts",
        seller_facts=["Best-sellers are out of stock"],
    )])
    agent = SellerAgent(client=client)
    agent.greeting()
    result = agent.respond("Sales are down")
    assert result.ok
    assert agent.state.covered_topics == {"stockouts"}
    assert agent.state.seller_facts == ["Best-sellers are out of stock"]
    assert len(agent.history) == 3  # greeting, user, assistant


def test_rate_limit_falls_back_to_second_model():
    err = RateLimitError("rate limited", response=_resp(429), body=None)
    client = FakeClient([err, _json("Fallback reply")])
    result = SellerAgent(client=client).respond("hello")
    assert result.ok and result.text == "Fallback reply"
    assert client.calls == 2


def test_rate_limit_on_all_models_returns_friendly_error():
    err = RateLimitError("rate limited", response=_resp(429), body=None)
    client = FakeClient([err, err])
    result = SellerAgent(client=client).respond("hello")
    assert not result.ok and result.error_type == "rate_limit"


def test_invalid_json_returns_error_and_keeps_history_clean():
    client = FakeClient(["not json", "still not json"])
    agent = SellerAgent(client=client)
    agent.greeting()
    result = agent.respond("hello")
    assert not result.ok and result.error_type == "invalid_response"
    assert client.calls == 2
    assert len(agent.history) == 1  # only the greeting


def test_invalid_api_key():
    err = AuthenticationError("bad key", response=_resp(401), body=None)
    result = SellerAgent(client=FakeClient([err])).respond("hello")
    assert not result.ok and result.error_type == "invalid_api_key"


def test_agreed_actions_ignored_before_recommendations():
    client = FakeClient([_json(agreed_actions=["Restock best-sellers"])])
    agent = SellerAgent(client=client)
    agent.respond("sure, I'll restock")
    assert agent.state.agreed_actions == []


def test_agreed_actions_recorded_after_recommendations():
    client = FakeClient([
        _json("Here are three suggestions...", recommendations_given=True),
        _json("Great, noted.", agreed_actions=["Restock best-sellers"]),
    ])
    agent = SellerAgent(client=client)
    agent.respond("what should I do?")
    agent.respond("I'll restock my best-sellers")
    assert agent.state.agreed_actions == ["Restock best-sellers"]

def test_model_not_found_falls_back_to_second_model():
    err = NotFoundError("model not found", response=_resp(404), body=None)
    client = FakeClient([err, _json("Fallback reply")])
    result = SellerAgent(client=client).respond("hello")
    assert result.ok and client.calls == 2