"""Embeddings and similarity search.

pgvector is not installed in the development database, so embeddings are stored as a
double precision[] column and cosine similarity is computed in Python (fine for demo-sized data).
MODE is reported by GET /health.
"""
import logging
import os
import time
import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from llm_classifier import call_with_backoff, get_client, llm_configured
from llm_logging import log_llm_call
from models import Complaint

MODE = "python-fallback"
log = logging.getLogger("triage.embeddings")


def embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "").strip()


def embeddings_available() -> bool:
    return llm_configured() and bool(embedding_model())


def embed_text(text: str, complaint_id: uuid.UUID | None = None) -> list[float]:
    """Embed one text. Raises on any failure; callers decide how to degrade."""
    client = get_client()
    model = embedding_model()
    if client is None or not model:
        raise RuntimeError("embeddings are not configured")
    start = time.perf_counter()
    try:
        resp = call_with_backoff(lambda: client.embeddings.create(model=model, input=text))
    except Exception as exc:  # noqa: BLE001
        log_llm_call(kind="embed", model=model, latency_ms=int((time.perf_counter() - start) * 1000),
                     success=False, error=exc.__class__.__name__, complaint_id=complaint_id)
        raise
    log_llm_call(kind="embed", model=model, latency_ms=int((time.perf_counter() - start) * 1000),
                 success=True, usage=getattr(resp, "usage", None), complaint_id=complaint_id)
    return list(resp.data[0].embedding)


def cosine(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / denom) if denom else 0.0


def embed_complaint(db: Session, complaint: Complaint) -> bool:
    """Best effort: a failed embedding never fails a submission."""
    if complaint.embedding is not None or not embeddings_available():
        return False
    try:
        complaint.embedding = embed_text(complaint.raw_text, complaint.id)
        db.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.warning("embedding failed for %s (%s)", complaint.id, exc.__class__.__name__)
        return False


def search(db: Session, query: str, limit: int = 10, exclude: uuid.UUID | None = None, vector=None):
    """Return [(complaint, similarity)] ordered by cosine similarity, best first."""
    vector = vector if vector is not None else embed_text(query)
    rows = db.scalars(select(Complaint).where(Complaint.embedding.is_not(None))).all()
    scored = [(c, cosine(vector, c.embedding)) for c in rows if c.id != exclude]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def backfill() -> int:
    """Embed every complaint that has no embedding yet (one call each, never re-embeds)."""
    from database import SessionLocal

    done = 0
    with SessionLocal() as db:
        for c in db.scalars(select(Complaint).where(Complaint.embedding.is_(None))).all():
            if embed_complaint(db, c):
                done += 1
            time.sleep(0.5)  # free-tier friendly
    return done
