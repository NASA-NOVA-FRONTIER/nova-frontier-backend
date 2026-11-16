from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonColumn = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class ExplorationRecord(Base):
    __tablename__ = "explorations"
    __table_args__ = (Index("ix_explorations_client_key_created_at", "client_key", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    stage: Mapped[str] = mapped_column(String(16))
    lens: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(1))
    optical_evidence: Mapped[bool] = mapped_column(Boolean)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    area_bucket: Mapped[str] = mapped_column(String(16))
    scenes_total: Mapped[int] = mapped_column(Integer)
    plan_seconds: Mapped[float] = mapped_column(Float)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    runner_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonColumn, nullable=True)
    layer_urls: Mapped[dict[str, Any]] = mapped_column(JsonColumn)
    timings: Mapped[dict[str, Any]] = mapped_column(JsonColumn)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    client_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    counts_toward_limits: Mapped[bool] = mapped_column(Boolean, server_default=true())
