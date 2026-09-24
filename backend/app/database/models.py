from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
class Base(DeclarativeBase): pass
class CatalogSnapshot(Base):
    __tablename__="catalog_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), unique=True)
    payload: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class ImportJobRecord(Base):
    __tablename__="import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30)); filename: Mapped[str] = mapped_column(String(255))
    records: Mapped[int] = mapped_column(Integer, default=0); processed: Mapped[int] = mapped_column(Integer, default=0); errors: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30)); unknown_columns: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)); finished_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
class ReconciliationRun(Base):
    __tablename__="reconciliation_runs"
    id: Mapped[int] = mapped_column(primary_key=True); results: Mapped[list] = mapped_column(JSON); summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
