"""Explicit additive schema for controlled channel dispatch.

No startup migration, provider calls or credential storage.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ChannelDispatchBase(DeclarativeBase):
    pass


class ChannelDispatch(ChannelDispatchBase):
    __tablename__ = "kiki_channel_dispatch"
    __table_args__ = (
        UniqueConstraint("channel", "store_id", "sku_key", name="uq_dispatch_sku"),
        UniqueConstraint("channel", "store_id", "ecomm_id", name="uq_dispatch_identity"),
        CheckConstraint("channel IN ('tn', 'ml')", name="ck_dispatch_channel"),
        CheckConstraint("state IN ('RESERVED', 'IN_FLIGHT', 'CONFIRMED', 'UNKNOWN')",
                        name="ck_dispatch_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(2), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ecomm_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sku_key: Mapped[str] = mapped_column(String(256), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(240), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    remote_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
