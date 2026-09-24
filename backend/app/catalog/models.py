from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, Field


class Channel(StrEnum):
    MERCADOLIBRE = "MERCADOLIBRE"


class ReconciliationStatus(StrEnum):
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    CANDIDATE_TO_PUBLISH = "CANDIDATE_TO_PUBLISH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"
    INVALID_SKU = "INVALID_SKU"
    INVALID_EAN = "INVALID_EAN"
    UNMATCHED_ML_LISTING = "UNMATCHED_ML_LISTING"


class MatchMethod(StrEnum):
    SKU = "SKU"
    EAN = "EAN"
    TITLE = "TITLE"
    NONE = "NONE"


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class EcommChannelRow(BaseModel):
    """A row from Ecomm-App, before product canonicalization."""

    ecomm_id: str | None = None
    marketplace: str | None = None
    marketplace_id: str | None = None
    store: str | None = None
    listing_id: str | None = None
    listing_title: str | None = None
    listing_status: str | None = None
    sku: str | None = None
    sku_product: str | None = None
    sku_variant: str | None = None
    sku_effective: str | None = None
    sku_source: str | None = None
    ean: str | None = None
    name: str | None = None
    brand: str | None = None
    marketplace_price: Decimal | None = None
    list_price: Decimal | None = None
    cost: Decimal | None = None
    stock: Decimal | None = None
    inventory_linked: str | None = None


class Product(BaseModel):
    ecomm_id: str | None = None
    sku: str | None = None
    sku_product: str | None = None
    sku_variant: str | None = None
    sku_effective: str | None = None
    sku_source: str | None = None
    sku_aliases: list[str] = Field(default_factory=list)
    ean: str | None = None
    ean_aliases: list[str] = Field(default_factory=list)
    name: str | None = None
    brand: str | None = None
    price: Decimal | None = None
    list_price: Decimal | None = None
    cost: Decimal | None = None
    stock: Decimal | None = None
    image_urls: list[str] = Field(default_factory=list)
    ecomm_rows: list[EcommChannelRow] = Field(default_factory=list)


class ChannelListing(BaseModel):
    channel: Channel = Channel.MERCADOLIBRE
    external_id: str | None = None
    sku: str | None = None
    sku_product: str | None = None
    variant_sku: str | None = None
    sku_effective: str | None = None
    sku_source: str | None = None
    ean: str | None = None
    title: str | None = None
    status: str | None = None
    price: Decimal | None = None
    url: str | None = None
    inventory_linked: str | None = None


class ValidationIssue(BaseModel):
    field: str
    severity: Severity
    code: str
    message: str


class ReconciliationResult(BaseModel):
    product: Product | None = None
    listing: ChannelListing | None = None
    status: ReconciliationStatus
    confidence: float = 0
    reason: str
    match_method: MatchMethod = MatchMethod.NONE
    matched_identifier: str | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
