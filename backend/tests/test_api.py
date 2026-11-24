import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import rate_limit
from database import SessionLocal
from main import app
from models import Category, Complaint, Status, Urgency

client = TestClient(app)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def make(text="x", category=Category.other, urgency=Urgency.medium, status=Status.open, days_ago=0, summary=None):
    with SessionLocal() as db:
        c = Complaint(
            raw_text=text, category=category, urgency=urgency, status=status,
            summary=summary or text[:50], suggested_department="General Services",
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )
        db.add(c)
        db.commit()
        return str(c.id)


def test_create_complaint_without_key_uses_fallback():
    r = client.post("/complaints", data={"text": "streetlight is out"})
    assert r.status_code == 201
    body = r.json()
    assert (body["category"], body["urgency"], body["status"]) == ("other", "medium", "open")
    assert body["used_fallback"] is True and body["model"] is None and body["notes"] == []


def test_blank_text_422():
    assert client.post("/complaints", data={"text": "   "}).status_code == 422


def test_overlong_text_422():
    assert client.post("/complaints", data={"text": "a" * 4001}).status_code == 422


def test_bad_coordinates_422():
    assert client.post("/complaints", data={"text": "x", "latitude": "99"}).status_code == 422
    assert client.post("/complaints", data={"text": "x", "longitude": "-181"}).status_code == 422


def test_invalid_photo_type_422():
    r = client.post("/complaints", data={"text": "x"}, files={"photo": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422


def test_oversize_photo_422():
    big = b"0" * (5 * 1024 * 1024 + 1)
    r = client.post("/complaints", data={"text": "x"}, files={"photo": ("a.png", big, "image/png")})
    assert r.status_code == 422


def test_valid_photo_is_served():
    r = client.post("/complaints", data={"text": "x"}, files={"photo": ("../evil name.png", PNG, "image/png")})
    assert r.status_code == 201
    url = r.json()["photo_url"]
    assert url.startswith("/uploads/") and url.endswith(".png") and "evil" not in url
    assert client.get(url).status_code == 200


def test_list_filters_search_and_total():
    make("sewage leak", Category.water, Urgency.high)
    make("pothole", Category.other, Urgency.medium, Status.resolved)
    make("faded paint", Category.other, Urgency.low)
    body = client.get("/complaints").json()
    assert body["total"] == 3 and len(body["items"]) == 3
    assert client.get("/complaints", params={"category": "water"}).json()["total"] == 1
    assert client.get("/complaints", params={"status": "resolved"}).json()["total"] == 1
    assert client.get("/complaints", params={"urgency": "low"}).json()["total"] == 1
    assert client.get("/complaints", params={"q": "SEWAGE"}).json()["total"] == 1


def test_urgency_sort_and_pagination():
    make("a", urgency=Urgency.high)
    make("b", urgency=Urgency.low)
    make("c", urgency=Urgency.medium)
    asc = [i["urgency"] for i in client.get("/complaints", params={"sort": "urgency", "order": "asc"}).json()["items"]]
    assert asc == ["low", "medium", "high"]
    page = client.get("/complaints", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert len(client.get("/complaints", params={"limit": 0}).json()["items"]) == 1  # clamped to 1


def test_unknown_id_404():
    missing = uuid.uuid4()
    assert client.get(f"/complaints/{missing}").status_code == 404
    assert client.patch(f"/complaints/{missing}", json={"status": "open"}).status_code == 404
    assert client.post(f"/complaints/{missing}/notes", json={"text": "hi"}).status_code == 404


def test_status_update_and_bulk_not_swallowed():
    a, b = make("a"), make("b")
    r = client.patch(f"/complaints/{a}", json={"status": "in_progress"})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    r = client.patch("/complaints/bulk-status", json={"ids": [a, b], "status": "resolved"})
    assert r.status_code == 200 and [x["status"] for x in r.json()] == ["resolved", "resolved"]
    assert client.patch("/complaints/bulk-status", json={"ids": [], "status": "resolved"}).status_code == 422


def test_notes():
    a = make("a")
    assert client.post(f"/complaints/{a}/notes", json={"text": ""}).status_code == 422
    assert client.post(f"/complaints/{a}/notes", json={"text": "Crew assigned"}).status_code == 201
    notes = client.get(f"/complaints/{a}").json()["notes"]
    assert [n["text"] for n in notes] == ["Crew assigned"]


def test_analytics_zero_filled_trend():
    make("today")
    make("old", days_ago=3)
    body = client.get("/analytics/summary").json()
    assert set(body) == {"by_category", "by_urgency", "by_status", "trend"}
    assert len(body["trend"]) == 14
    counts = [t["count"] for t in body["trend"]]
    assert sum(counts) == 2 and counts.count(0) == 12
    assert body["by_status"]["open"] == 2


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["db"] is True and body["llm_configured"] is False


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    rate_limit.reset()
    codes = [client.post("/complaints", data={"text": "x"}).status_code for _ in range(4)]
    assert codes == [201, 201, 201, 429]
