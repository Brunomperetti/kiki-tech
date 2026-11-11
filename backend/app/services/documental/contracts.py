from datetime import datetime, timezone
from typing import Literal
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


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    new_version: int = Field(ge=1)


class Incorporate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["FILE", "URL"]
    expected_version: int = Field(ge=0)
    filename: str = Field(default="", max_length=120)
    content_type: str = Field(default="", max_length=80)
    content_base64: str = Field(default="", max_length=699_052)
    provenance_note: str = Field(min_length=10, max_length=600)
    reference_url: str = Field(default="", max_length=1000)
    declared_official: bool = False
    declared_manufacturer: str = Field(default="", max_length=180)
    declared_consulted_at: datetime | None = None
    authorized_local_processing: Literal[True]
    document_id: str | None = Field(default=None, pattern=r"^local-[a-f0-9]{32}$")
    expected_document_version: int | None = Field(default=None, ge=1)

    @field_validator("declared_consulted_at")
    @classmethod
    def consulted_date(cls, value):
        if value and (value.tzinfo is None or value > datetime.now(timezone.utc)):
            raise ValueError(
                "Fecha de consulta requiere zona horaria y no puede ser futura."
            )
        return value


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
