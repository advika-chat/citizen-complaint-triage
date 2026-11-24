import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from models import Category, Status, Urgency


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    text: str
    created_at: datetime


class NoteCreate(BaseModel):
    text: str = Field(min_length=1)


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    raw_text: str
    category: Category
    urgency: Urgency
    summary: str
    suggested_department: str
    status: Status
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    used_fallback: bool = False
    duplicate_of: uuid.UUID | None = None
    agent_trace: list | None = None
    created_at: datetime
    updated_at: datetime
    notes: list[NoteOut] = []


class SearchResult(ComplaintOut):
    similarity: float


class ComplaintStatusUpdate(BaseModel):
    status: Status


class BulkStatusUpdate(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)
    status: Status


class ComplaintListResponse(BaseModel):
    items: list[ComplaintOut]
    total: int


class TrendPoint(BaseModel):
    date: date
    count: int


class AnalyticsSummary(BaseModel):
    by_category: dict[str, int]
    by_urgency: dict[str, int]
    by_status: dict[str, int]
    trend: list[TrendPoint]


class LlmAnalytics(BaseModel):
    days: int
    total_calls: int
    success_rate: float | None
    fallback_rate: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    prompt_tokens: int
    completion_tokens: int
    est_cost_usd: float
    by_kind: dict[str, int]
    by_model: dict[str, int]
