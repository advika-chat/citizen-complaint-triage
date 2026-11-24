from fastapi.testclient import TestClient

import embeddings
from database import SessionLocal
from main import app
from models import Category, Complaint, Urgency

client = TestClient(app)

VECTORS = {
    "light": [1.0, 0.0, 0.0],
    "sewage": [0.0, 1.0, 0.0],
    "lamp": [0.9, 0.1, 0.0],
}


def add(text, vec):
    with SessionLocal() as db:
        c = Complaint(raw_text=text, category=Category.other, urgency=Urgency.low, summary=text,
                      suggested_department="x", embedding=vec)
        db.add(c)
        db.commit()
        return str(c.id)


def configure(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("EMBEDDING_MODEL", "m")
    monkeypatch.setattr(embeddings, "embed_text", lambda text, complaint_id=None: VECTORS[text])


def test_search_orders_by_similarity(monkeypatch):
    configure(monkeypatch)
    add("sewage", VECTORS["sewage"])
    add("light", VECTORS["light"])
    add("lamp", VECTORS["lamp"])
    r = client.get("/complaints/search", params={"q": "light", "limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert [x["summary"] for x in body] == ["light", "lamp", "sewage"]
    assert body[0]["similarity"] > body[1]["similarity"] > body[2]["similarity"]


def test_search_without_key_503():
    assert client.get("/complaints/search", params={"q": "x"}).status_code == 503


def test_embedding_failure_never_fails_submission(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("EMBEDDING_MODEL", "m")

    def boom(*a, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(embeddings, "embed_text", boom)
    r = client.post("/complaints", data={"text": "streetlight out"})
    assert r.status_code == 201
