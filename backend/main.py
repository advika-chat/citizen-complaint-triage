import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, func, or_, select, text as sql_text
from sqlalchemy.orm import Session

from database import get_db
from llm_classifier import classify_complaint, llm_configured
from models import Category, Complaint, ComplaintNote, LlmCall, Status, Urgency
from rate_limit import check_rate_limit
import agent
import embeddings
from schemas import (
    AnalyticsSummary,
    BulkStatusUpdate,
    ComplaintListResponse,
    ComplaintOut,
    ComplaintStatusUpdate,
    LlmAnalytics,
    NoteCreate,
    NoteOut,
    SearchResult,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("triage.api")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR") or Path(__file__).parent / "uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_TEXT = 4000
MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}

app = FastAPI(title="Citizen Complaint Triage Bot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def embeddings_mode() -> str:
    return embeddings.MODE


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(sql_text("select 1"))
    return {"status": "ok", "db": True, "llm_configured": llm_configured(), "embeddings": embeddings_mode(), "semantic_search": embeddings.embeddings_available()}


@app.post("/complaints", response_model=ComplaintOut, status_code=201, dependencies=[Depends(check_rate_limit)])
def create_complaint(
    text: str = Form(...),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Complaint text must not be blank.")
    if len(text) > MAX_TEXT:
        raise HTTPException(status_code=422, detail=f"Complaint text must be at most {MAX_TEXT} characters.")
    if latitude is not None and not -90 <= latitude <= 90:
        raise HTTPException(status_code=422, detail="latitude must be between -90 and 90.")
    if longitude is not None and not -180 <= longitude <= 180:
        raise HTTPException(status_code=422, detail="longitude must be between -180 and 180.")

    photo_url = None
    photo_bytes = None
    if photo is not None and photo.filename:
        ext = PHOTO_TYPES.get(photo.content_type or "")
        if ext is None:
            raise HTTPException(status_code=422, detail="Photo must be a JPEG, PNG, WebP or GIF image.")
        photo_bytes = photo.file.read(MAX_PHOTO_BYTES + 1)
        if len(photo_bytes) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=422, detail="Photo must be 5MB or smaller.")
        filename = f"{uuid.uuid4()}{ext}"
        photo_url = f"/uploads/{filename}"

    # Agent (tools + duplicate check) when an LLM is configured; any failure falls back to the
    # single-shot classifier, which itself falls back to the static result.
    agent_result = agent.run_agent(db, text, latitude, longitude) if llm_configured() else None
    result = agent_result.classification if agent_result else classify_complaint(text)
    complaint = Complaint(
        raw_text=text,
        category=result.category,
        urgency=result.urgency,
        summary=result.summary,
        suggested_department=result.suggested_department,
        latitude=latitude,
        longitude=longitude,
        photo_url=photo_url,
        model=result.model,
        prompt_version=result.prompt_version,
        used_fallback=result.used_fallback,
        duplicate_of=agent_result.duplicate_of if agent_result else None,
        agent_trace=agent_result.trace if agent_result else None,
        embedding=agent_result.text_vector if agent_result else None,  # reuse: embed each complaint once
    )
    db.add(complaint)
    db.commit()
    if photo_bytes is not None:
        (UPLOAD_DIR / photo_url.rsplit("/", 1)[1]).write_bytes(photo_bytes)
    embeddings.embed_complaint(db, complaint)  # best effort; never fails the submission
    db.refresh(complaint)
    log.info("complaint created id=%s len=%d fallback=%s", complaint.id, len(text), result.used_fallback)
    return complaint


URGENCY_RANK = case(
    (Complaint.urgency == Urgency.high, 3),
    (Complaint.urgency == Urgency.medium, 2),
    else_=1,
)
SORT_COLUMNS = {
    "created_at": Complaint.created_at,
    "urgency": URGENCY_RANK,
    "status": Complaint.status,
    "category": Complaint.category,
}


@app.get("/complaints", response_model=ComplaintListResponse)
def list_complaints(
    category: Category | None = None,
    urgency: Urgency | None = None,
    status: Status | None = None,
    q: str | None = None,
    sort: str = Query("created_at", pattern="^(created_at|urgency|status|category)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    stmt = select(Complaint)
    if category:
        stmt = stmt.where(Complaint.category == category)
    if urgency:
        stmt = stmt.where(Complaint.urgency == urgency)
    if status:
        stmt = stmt.where(Complaint.status == status)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Complaint.raw_text.ilike(like), Complaint.summary.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    col = SORT_COLUMNS[sort]
    primary = col.asc() if order == "asc" else col.desc()
    items = db.scalars(stmt.order_by(primary, Complaint.created_at.desc(), Complaint.id).limit(limit).offset(offset)).all()
    return {"items": items, "total": total}


# Literal routes must be declared before "/complaints/{complaint_id}".
@app.get("/complaints/search", response_model=list[SearchResult])
def semantic_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    if not embeddings.embeddings_available():
        raise HTTPException(status_code=503, detail="Semantic search needs LLM_API_KEY and EMBEDDING_MODEL to be configured.")
    try:
        found = embeddings.search(db, q.strip(), limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("semantic search failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Semantic search is temporarily unavailable.")
    return [SearchResult(**ComplaintOut.model_validate(c).model_dump(), similarity=round(sim, 4)) for c, sim in found]


@app.patch("/complaints/bulk-status", response_model=list[ComplaintOut])
def bulk_status(body: BulkStatusUpdate, db: Session = Depends(get_db)):
    rows = db.scalars(select(Complaint).where(Complaint.id.in_(body.ids))).all()
    for row in rows:
        row.status = body.status
    db.commit()
    return rows


def get_or_404(db: Session, complaint_id: uuid.UUID) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found.")
    return complaint


@app.get("/complaints/{complaint_id}", response_model=ComplaintOut)
def get_complaint(complaint_id: uuid.UUID, db: Session = Depends(get_db)):
    return get_or_404(db, complaint_id)


@app.patch("/complaints/{complaint_id}", response_model=ComplaintOut)
def update_status(complaint_id: uuid.UUID, body: ComplaintStatusUpdate, db: Session = Depends(get_db)):
    complaint = get_or_404(db, complaint_id)
    complaint.status = body.status
    db.commit()
    db.refresh(complaint)
    return complaint


@app.post("/complaints/{complaint_id}/notes", response_model=NoteOut, status_code=201)
def add_note(complaint_id: uuid.UUID, body: NoteCreate, db: Session = Depends(get_db)):
    get_or_404(db, complaint_id)
    note = ComplaintNote(complaint_id=complaint_id, text=body.text)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.get("/analytics/summary", response_model=AnalyticsSummary)
def analytics_summary(db: Session = Depends(get_db)):
    def counts(column, enum_cls):
        found = dict(db.execute(select(column, func.count()).group_by(column)).all())
        return {e.value: found.get(e, 0) for e in enum_cls}

    today = date.today()
    start = today - timedelta(days=13)
    day = func.date(Complaint.created_at)
    per_day = dict(db.execute(select(day, func.count()).where(day >= start).group_by(day)).all())
    trend = [
        {"date": start + timedelta(days=i), "count": per_day.get(start + timedelta(days=i), 0)}
        for i in range(14)
    ]
    return {
        "by_category": counts(Complaint.category, Category),
        "by_urgency": counts(Complaint.urgency, Urgency),
        "by_status": counts(Complaint.status, Status),
        "trend": trend,
    }


def _percentile(values: list[int], p: float):
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))])


@app.get("/analytics/llm", response_model=LlmAnalytics)
def analytics_llm(db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=7)
    calls = db.scalars(select(LlmCall).where(LlmCall.created_at >= since)).all()
    total = len(calls)
    latencies = [c.latency_ms for c in calls]
    # Fallback rate: share of real (non-seed) complaints in the window that used the static fallback.
    recent = select(Complaint).where(Complaint.created_at >= since, Complaint.prompt_version.is_distinct_from("seed"))
    recent_total = db.scalar(select(func.count()).select_from(recent.subquery()))
    recent_fallback = db.scalar(
        select(func.count()).select_from(recent.where(Complaint.used_fallback.is_(True)).subquery())
    )
    by_kind: dict[str, int] = {}
    by_model: dict[str, int] = {}
    for c in calls:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
        by_model[c.model or "unknown"] = by_model.get(c.model or "unknown", 0) + 1
    return {
        "days": 7,
        "total_calls": total,
        "success_rate": (sum(c.success for c in calls) / total) if total else None,
        "fallback_rate": (recent_fallback / recent_total) if recent_total else None,
        "p50_latency_ms": _percentile(latencies, 0.5),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "prompt_tokens": sum(c.prompt_tokens or 0 for c in calls),
        "completion_tokens": sum(c.completion_tokens or 0 for c in calls),
        "est_cost_usd": sum(c.est_cost_usd or 0.0 for c in calls),
        "by_kind": by_kind,
        "by_model": by_model,
    }
