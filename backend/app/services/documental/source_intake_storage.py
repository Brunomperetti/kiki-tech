"""Explicit additive state for resumable, manual manufacturer-source intake.

Separate from the existing editorial batch operation codes. Requires an
explicitly applied migration; no create_all or startup DDL in production.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SourceIntakeBase(DeclarativeBase):
    pass


class SourceIntakeJob(SourceIntakeBase):
    __tablename__ = "kiki_source_intake_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creator: Mapped[str] = mapped_column(String(240), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    sitemap_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    sitemap_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_host: Mapped[str] = mapped_column(String(253), nullable=False)
    # Max 20 bounded items; never contains HTML, tokens, or supplier secrets.
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    # Explicit operator actions only. Compact; no document originals.
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
