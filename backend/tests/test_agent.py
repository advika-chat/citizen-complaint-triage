import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import agent
import embeddings
import llm_classifier
from database import SessionLocal
from main import app
from models import Category, Complaint, Urgency

client = TestClient(app)


class Msg:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in self.tool_calls]}


def tool_call(name, args, cid="c1"):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def create_response(*calls):
    return SimpleNamespace(choices=[SimpleNamespace(message=Msg(list(calls)))], usage=None)


def final_response(**over):
    base = dict(category="streetlight", urgency="medium", summary="Streetlight out.",
                suggested_department="Public Works - Street Lighting", duplicate_of=None, reasoning="Matches existing.")
    base.update(over)
    parsed = SimpleNamespace(**base)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))], usage=None)


class FakeClient:
    def __init__(self, creates, final):
        self.creates, self.final, self.create_calls, self.parse_calls = list(creates), final, 0, 0
        outer = self

        def create(**kwargs):
            outer.create_calls += 1
            item = outer.creates.pop(0) if len(outer.creates) > 1 else outer.creates[0]
            if isinstance(item, Exception):
                raise item
            return item

        def parse(**kwargs):
            outer.parse_calls += 1
            if isinstance(outer.final, Exception):
                raise outer.final
            return outer.final

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("EMBEDDING_MODEL", "e")
    monkeypatch.setattr(embeddings, "embed_text", lambda text, complaint_id=None: [1.0, 0.0])


def existing(vec=(1.0, 0.0)):
    with SessionLocal() as db:
        c = Complaint(raw_text="lamp out on Congress", category=Category.streetlight, urgency=Urgency.medium,
                      summary="Lamp out on Congress", suggested_department="x", embedding=list(vec))
        db.add(c)
        db.commit()
        return str(c.id)


def run(fake, monkeypatch, lat=None, lng=None):
    monkeypatch.setattr(agent, "get_client", lambda: fake)
    with SessionLocal() as db:
        return agent.run_agent(db, "streetlight out on Congress", lat, lng)


def test_tool_then_final_with_valid_duplicate(configured, monkeypatch):
    dup = existing()
    fake = FakeClient([create_response(tool_call("find_similar_complaints", {"text": "x"})), create_response()],
                      final_response(duplicate_of=dup))
    res = run(fake, monkeypatch)
    assert str(res.duplicate_of) == dup and res.classification.used_fallback is False
    assert res.classification.prompt_version == "agent_v1"
    assert [s["type"] for s in res.trace] == ["tool", "final"] and res.trace[0]["tool"] == "find_similar_complaints"


def test_duplicate_not_returned_by_a_tool_is_nulled(configured, monkeypatch):
    existing()
    fake = FakeClient([create_response(tool_call("find_similar_complaints", {"text": "x"})), create_response()],
                      final_response(duplicate_of="11111111-1111-1111-1111-111111111111"))
    assert run(fake, monkeypatch).duplicate_of is None


def test_tool_error_makes_agent_return_none(configured, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("tool failed")

    monkeypatch.setattr(embeddings, "embed_text", boom)
    fake = FakeClient([create_response(tool_call("find_similar_complaints", {"text": "x"}))], final_response())
    assert run(fake, monkeypatch) is None


def test_max_three_turns_enforced(configured, monkeypatch):
    fake = FakeClient([create_response(tool_call("lookup_department", {"category": "water"}))], final_response())
    res = run(fake, monkeypatch)
    assert fake.create_calls == 3 and fake.parse_calls == 1 and res is not None


def test_nearby_tool_only_offered_with_coordinates():
    assert "get_nearby_complaints" not in [t["function"]["name"] for t in agent.tool_specs(False)]
    assert "get_nearby_complaints" in [t["function"]["name"] for t in agent.tool_specs(True)]


def test_nearby_finds_close_complaints(configured):
    with SessionLocal() as db:
        db.add(Complaint(raw_text="a", category=Category.other, urgency=Urgency.low, summary="near",
                         suggested_department="x", latitude=30.2672, longitude=-97.7431))
        db.add(Complaint(raw_text="b", category=Category.other, urgency=Urgency.low, summary="far",
                         suggested_department="x", latitude=30.30, longitude=-97.70))
        db.commit()
        ctx = agent.Context(db=db, text="t", latitude=None, longitude=None)
        out = agent.get_nearby_complaints(ctx, 30.2673, -97.7432, 200)
    assert [r["summary"] for r in out] == ["near"]


def test_post_stores_duplicate_and_trace(configured, monkeypatch):
    dup = existing()
    fake = FakeClient([create_response(tool_call("find_similar_complaints", {"text": "x"})), create_response()],
                      final_response(duplicate_of=dup))
    monkeypatch.setattr(agent, "get_client", lambda: fake)
    r = client.post("/complaints", data={"text": "streetlight out on Congress"})
    assert r.status_code == 201
    body = r.json()
    assert body["duplicate_of"] == dup and body["agent_trace"][0]["tool"] == "find_similar_complaints"
    assert body["prompt_version"] == "agent_v1"


def test_post_survives_agent_failure(configured, monkeypatch):
    broken = FakeClient([RuntimeError("down")], RuntimeError("down"))
    monkeypatch.setattr(agent, "get_client", lambda: broken)
    monkeypatch.setattr(llm_classifier, "get_client", lambda: broken)  # single-shot also fails
    r = client.post("/complaints", data={"text": "water main leak"})
    assert r.status_code == 201 and r.json()["used_fallback"] is True and r.json()["duplicate_of"] is None
