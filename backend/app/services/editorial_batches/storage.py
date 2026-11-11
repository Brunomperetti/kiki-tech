"""Additive coordination only. Never part of production Base startup metadata."""

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class EditorialBase(DeclarativeBase):
    pass


class Batch(EditorialBase):
    __tablename__ = "kiki_editorial_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(80), unique=True)
    operation: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(20))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creator: Mapped[str] = mapped_column(String(240))
    authorized_by: Mapped[str | None] = mapped_column(String(240), nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    selection: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    preview_hash: Mapped[str] = mapped_column(String(64))
    total: Mapped[int] = mapped_column(Integer)
    owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    history: Mapped[list] = mapped_column(JSON, default=list)


class Item(EditorialBase):
    __tablename__ = "kiki_editorial_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "ecomm_id"),
        UniqueConstraint("batch_id", "position"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("kiki_editorial_batches.id", ondelete="CASCADE"), index=True
    )
    ecomm_id: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expected: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
