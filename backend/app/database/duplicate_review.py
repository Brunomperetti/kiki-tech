from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class DuplicateReviewDecision(Base):
    """Persistent human resolution for possible duplicate Ecomm product groups."""

    __tablename__ = "duplicate_review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    reconciliation_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str] = mapped_column(String(40), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_identifiers: Mapped[list] = mapped_column(JSON, default=list)
    product_keys: Mapped[list] = mapped_column(JSON, default=list)
    group_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
