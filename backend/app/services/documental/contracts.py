from datetime import datetime, timezone
from typing import Literal
from document_reader.hileret_brochure import ENCODED_SIZE
from document_reader.parser import MAX_SAVED_HTML_BYTES
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Extract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    document_id: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    document_version: int = Field(ge=1)


class FactReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    expected_fact_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED", "REVOKED"]
    reason: str = Field(min_length=10, max_length=600)


class DocumentIdentityReview(BaseModel):
    """Explicit per-source name/presentation reconciliation; never EAN approval."""
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    document_version: int = Field(ge=1)
    decision: Literal["APPROVED", "REVOKED"]
    reason: str = Field(min_length=20, max_length=600)


class MediaRightsReview(BaseModel):
    """Explicit asset-specific usage permission in a reviewed original."""
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    document_version: int = Field(ge=1)
    media_kind: Literal["IMAGE", "VIDEO"]
    media_url: str = Field(min_length=9, max_length=1000)
    source_url: str = Field(min_length=9, max_length=1000)
    decision: Literal["APPROVED", "REVOKED"]
    licence_basis: Literal["OWNER_AUTHORIZATION", "DOCUMENTED_LICENSE"]
    location: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=30, max_length=1500)
    reason: str = Field(min_length=25, max_length=600)


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    new_version: int = Field(ge=1)


class Incorporate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["FILE", "URL"]
    web_snapshot: Literal[True, False] = False
    expected_version: int = Field(ge=0)
    filename: str = Field(default="", max_length=120)
    content_type: str = Field(default="", max_length=80)
    content_base64: str = Field(default="", max_length=ENCODED_SIZE)
    provenance_note: str = Field(min_length=10, max_length=600)
    reference_url: str = Field(default="", max_length=1000)
    declared_official: bool = False
    declared_manufacturer: str = Field(default="", max_length=180)
    declared_consulted_at: datetime | None = None
    authorized_local_processing: Literal[True]
    document_id: str | None = Field(default=None, pattern=r"^local-[a-f0-9]{32}$")
    expected_document_version: int | None = Field(default=None, ge=1)

    @field_validator("content_base64")
    @classmethod
    def bounded_original(cls, value, info):
        # Only explicitly opt-in, original HTML snapshots may be larger.
        # All normal files still use the 512 KiB / pinned-Hileret validation.
        if cls is Incorporate and len(value) > 699_052:
            is_saved_html = (
                info.data.get("kind") == "FILE"
                and info.data.get("web_snapshot") is True
                and str(info.data.get("filename", "")).lower().endswith(".html")
                and info.data.get("content_type") == "text/html"
            )
            if is_saved_html:
                if len(value) > ((MAX_SAVED_HTML_BYTES + 2) // 3) * 4:
                    raise ValueError("HTML guardado superior a 4 MiB.")
            else:
                from document_reader.hileret_brochure import validate_encoding
                validate_encoding(value)
        return value

    @field_validator("declared_consulted_at")
    @classmethod
    def consulted_date(cls, value):
        if value and (value.tzinfo is None or value > datetime.now(timezone.utc)):
            raise ValueError(
                "Fecha de consulta requiere zona horaria y no puede ser futura."
            )
        return value


class ManufacturerFetch(BaseModel):
    """One explicit operator-initiated manufacturer page, never bulk crawling."""
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    reference_url: str = Field(min_length=16, max_length=1000)
    provenance_note: str = Field(min_length=10, max_length=600)
    authorized_local_processing: Literal[True]


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_document_version: int = Field(ge=1)
    decision: Literal["REVIEWED", "REJECTED", "REVOKED"]
    reason: str = Field(min_length=10, max_length=600)


class Generate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["ACCEPTED", "REJECTED"]
    value: str | list[dict[str, str]]


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    decisions: dict[str, Decision] = Field(max_length=18)
