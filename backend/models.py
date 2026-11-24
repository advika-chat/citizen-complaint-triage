import enum
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Category(str, enum.Enum):
    streetlight = "streetlight"
    pollution = "pollution"
    water = "water"
    waste = "waste"
    energy = "energy"
    crowd_monitoring = "crowd_monitoring"
    other = "other"


class Urgency(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Status(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Category] = mapped_column(Enum(Category, name="category"), nullable=False)
    urgency: Mapped[Urgency] = mapped_column(Enum(Urgency, name="urgency"), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_department: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[Status] = mapped_column(
        Enum(Status, name="status"), nullable=False, default=Status.open, server_default="open"
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # pgvector is unavailable here: embeddings are a double precision[] and similarity is computed in Python.
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True, deferred=True)
    # Set by the agent when it finds an existing report of the same problem; staff decide what to do.
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="SET NULL", name="fk_complaints_duplicate_of"),
        nullable=True
    )
    agent_trace: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    notes: Mapped[list["ComplaintNote"]] = relationship(
        back_populates="complaint",
        order_by="ComplaintNote.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ComplaintNote(Base):
    __tablename__ = "complaint_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    complaint: Mapped[Complaint] = relationship(back_populates="notes")


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaints.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # classify | agent | embed | eval
    model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Estimate only; free-tier calls record 0.0.
    est_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
