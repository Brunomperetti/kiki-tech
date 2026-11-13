"""Offline authorization plan. A valid plan NEVER enables network in this release."""

from datetime import datetime, timezone
import ipaddress
import re
from urllib.parse import urlsplit
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

REAL_NETWORK_ENABLED = False  # release lock: not an environment variable or API setting


def public_host(host):
    if (
        not host.isascii()
        or host != host.lower()
        or len(host) > 253
        or not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host
        )
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError(
            "Dominio exacto inválido; no se admiten comodines ni destinos locales."
        )
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ValueError("Se requiere dominio, no dirección IP.")


def checked_url(value):
    try:
        p = urlsplit(value)
        if (
            len(value) > 1000
            or p.scheme != "https"
            or not p.hostname
            or p.netloc != p.hostname
            or p.username
            or p.password
            or p.query
            or p.fragment
            or "%" in value
            or "\\" in value
            or any(ord(c) < 33 or ord(c) > 126 for c in value)
            or any(part in {".", ".."} for part in p.path.split("/"))
        ):
            raise ValueError
        public_host(p.hostname)
    except (ValueError, TypeError):
        raise ValueError(
            "URL HTTPS exacta inválida; sin credenciales, parámetros ni escapes."
        ) from None
    return p


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PilotProduct(Strict):
    ecomm_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9-]+$")
    name: str = Field(min_length=2, max_length=180)
    brand: str | None = Field(default=None, max_length=120)
    manufacturer: str = Field(min_length=2, max_length=180)
    presentation: str = Field(min_length=1, max_length=100)
    ean: str | None = Field(default=None, pattern=r"^(?:\d{8}|\d{12,14})$")
    authorization_reference: str = Field(min_length=10, max_length=200)


class OfficialSource(Strict):
    domain: str
    urls: tuple[str, ...] = Field(min_length=1, max_length=9)
    ecomm_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    manufacturer: str = Field(min_length=2, max_length=180)
    ownership_evidence: str = Field(min_length=20, max_length=600)
    conditions_review: str = Field(min_length=20, max_length=600)
    automated_access_permitted: Literal[True]
    reviewed_by: str = Field(min_length=2, max_length=100)
    approval_reference: str = Field(min_length=10, max_length=200)
    expires_at: datetime

    @model_validator(mode="after")
    def exact_scope(self):
        public_host(self.domain)
        if self.expires_at.tzinfo is None:
            raise ValueError("Vigencia requiere zona horaria.")
        if any(checked_url(url).hostname != self.domain for url in self.urls):
            raise ValueError("Cada URL debe pertenecer al dominio explícito.")
        if len(set(self.urls)) != len(self.urls) or len(set(self.ecomm_ids)) != len(
            self.ecomm_ids
        ):
            raise ValueError("No se admiten autorizaciones duplicadas.")
        return self


class PilotPlan(Strict):
    schema_version: Literal["kiki-pilot-v1"] = "kiki-pilot-v1"
    network_enabled: Literal[False] = False
    products: tuple[PilotProduct, ...] = Field(default=(), max_length=3)
    sources: tuple[OfficialSource, ...] = Field(default=(), max_length=9)

    @model_validator(mode="after")
    def consistent_products(self):
        products = {p.ecomm_id: p for p in self.products}
        if len(products) != len(self.products) or len(
            {s.domain for s in self.sources}
        ) != len(self.sources):
            raise ValueError("Identidades y dominios deben ser únicos.")
        for source in self.sources:
            for ident in source.ecomm_ids:
                if (
                    ident not in products
                    or products[ident].manufacturer != source.manufacturer
                ):
                    raise ValueError(
                        "Fuente no autorizada para ese fabricante y Ecomm ID."
                    )
        return self

    def source_for(self, ident, url, *, at=None):
        parsed = checked_url(url)
        at = at or datetime.now(timezone.utc)
        source = next(
            (
                s
                for s in self.sources
                if s.domain == parsed.hostname
                and ident in s.ecomm_ids
                and url in s.urls
            ),
            None,
        )
        if not source or source.expires_at <= at:
            raise ValueError("Fuente no autorizada, fuera de alcance o vencida.")
        return source


def pilot_status():
    return {
        "schema_version": "kiki-pilot-v1",
        "network_enabled": False,
        "release_locked": not REAL_NETWORK_ENABLED,
        "authorized_products": [],
        "authorized_domains": [],
        "authentic_documents_included": False,
        "manual_ingestion_available": True,
        "openai_enabled": False,
        "message": "Piloto pendiente de selección y autorización de 1 a 3 productos auténticos. El catálogo actual es sintético.",
    }
