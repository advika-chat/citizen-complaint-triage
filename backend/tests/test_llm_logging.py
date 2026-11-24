from fastapi.testclient import TestClient
from sqlalchemy import select

import llm_logging
from database import SessionLocal
from main import app
from models import LlmCall

client = TestClient(app)


def test_call_writes_row():
    llm_logging.log_llm_call(kind="classify", model="m", latency_ms=120, success=True, prompt_version="classify_v1")
    with SessionLocal() as db:
        rows = db.scalars(select(LlmCall)).all()
    assert len(rows) == 1 and rows[0].kind == "classify" and rows[0].est_cost_usd == 0.0


def test_logger_failure_does_not_raise(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(llm_logging, "SessionLocal", boom)
    llm_logging.log_llm_call(kind="classify", model="m", latency_ms=1, success=True)  # must not raise


def test_llm_analytics_endpoint():
    assert client.get("/analytics/llm").json()["total_calls"] == 0
    for ms in (100, 200, 300):
        llm_logging.log_llm_call(kind="classify", model="m", latency_ms=ms, success=ms != 300)
    body = client.get("/analytics/llm").json()
    assert body["total_calls"] == 3 and body["p50_latency_ms"] == 200 and abs(body["success_rate"] - 2 / 3) < 1e-9
    assert body["by_kind"] == {"classify": 3}
