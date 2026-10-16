from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthLoginThrottle(Base):
    __tablename__ = "auth_login_throttles"
    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalogSnapshot(Base):
    __tablename__ = "catalog_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), unique=True)
    payload: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ImportJobRecord(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(255))
    records: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30))
    unknown_columns: Mapped[list | dict] = mapped_column(JSON, default=list)

    @property
    def diagnostics(self) -> dict:
        # Diagnostics live in the existing JSON audit column so this hardening
        # remains deployable without a destructive schema change.
        return (
            self.unknown_columns
            if isinstance(self.unknown_columns, dict)
            else {"ignored_columns": self.unknown_columns or [], "warnings": []}
        )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    results: Mapped[list] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class InventoryLinkageDecision(Base):
    """Human confirmation for an EDIMA linkage suggestion; never writes externally."""

    __tablename__ = "inventory_linkage_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    decision: Mapped[str] = mapped_column(String(30), index=True)
    ecomm_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    product_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class EnrichmentReviewDecision(Base):
    """Persistent internal review state; never writes to Ecomm-App or Mercado Libre."""

    __tablename__ = "enrichment_review_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    reconciliation_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    proposed_brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_ean: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    product_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class EnrichmentExternalResearch(Base):
    """Source-backed research prepared inside KIKI Tech; never writes externally."""

    __tablename__ = "enrichment_external_research"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    reconciliation_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    proposed_brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposed_ean: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    internal_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CatalogCoreConflictDecision(Base):
    """Human resolution when current Ecomm data conflicts with validated KIKI data."""

    __tablename__ = "catalog_core_conflict_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    conflict_key: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    product_key: Mapped[str] = mapped_column(String(255), index=True)
    field: Mapped[str] = mapped_column(String(40), index=True)
    decision: Mapped[str] = mapped_column(String(30), index=True)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PrepublicationImageReview(Base):
    """Persistent image-source review. It never copies or publishes an image by itself."""

    __tablename__ = "prepublication_image_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_urls: Mapped[list] = mapped_column(JSON, default=list)
    match_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    exact_match: Mapped[bool] = mapped_column(Boolean, default=False)
    authorized_for_use: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PrepublicationMetadataReview(Base):
    """Persistent ML category/attribute review; reads ML but never publishes."""

    __tablename__ = "prepublication_metadata_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    category_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    domain_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    attributes: Mapped[list] = mapped_column(JSON, default=list)
    required_missing: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

class PrepublicationFinalApproval(Base):
    """Human approval for the final Mercado Libre publication queue.

    This is internal state only. It never writes to Mercado Libre by itself.
    """

    __tablename__ = "prepublication_final_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MercadoLibreConnection(Base):
    __tablename__ = "mercadolibre_connections"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    user_id: Mapped[str] = mapped_column(String(80), unique=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MercadoLibreOAuthState(Base):
    __tablename__ = "mercadolibre_oauth_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MercadoLibreSync(Base):
    """Immutable synchronization audit; catalog_snapshots keeps the current view."""

    __tablename__ = "mercadolibre_syncs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80))
    listing_count: Mapped[int] = mapped_column(Integer)
    payload: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TiendanubeMatchDecision(Base):
    """Auditable human decision; never performs external writes."""
    __tablename__ = "tiendanube_match_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    target_ecomm_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    target_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text)
    history: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class KikiAiDailyPilotAttempt(Base):
    """One durable reservation per UTC day. Failed attempts still consume the pilot slot."""
    __tablename__ = "kiki_ai_daily_pilot_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    day_utc: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
