from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class ReconciliationReviewDecision(Base):
    """Persistent human resolution for ambiguous Ecomm ↔ Mercado Libre matches."""

    __tablename__ = "reconciliation_review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    reconciliation_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str] = mapped_column(String(30), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_listing_ids: Mapped[list] = mapped_column(JSON, default=list)
    product_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    listing_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
