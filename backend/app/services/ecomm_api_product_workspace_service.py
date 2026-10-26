"""Durable KIKI-only editor for products identified by the Ecomm-App read API.

The authoritative source is always the complete ECOMM_APP_API_STAGE capture,
never historical XLSX. The proposed commercial fields are an INTERNAL OVERLAY:
no Ecomm-App, Mercado Libre, Tiendanube, stock, or price writes.
"""
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database.models import CatalogSnapshot, EcommApiProductEdit
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status

# Every commercial edit is a separate PostgreSQL JSON overlay. The API catalog
# is never modified and new fields do not require destructive migrations.
TEXT_LIMITS = {
    "brand": 120, "manufacturer": 120, "title": 180, "short_title": 100,
    "short_description": 500, "description": 5000, "details": 5000,
    "presentation": 750, "category": 160, "subcategory": 160,
    "seo_title": 180, "seo_description": 320, "seo_keywords": 1000,
    "proposed_gtin": 14, "note": 1800,
}
ARRAY_LIMITS = {"attributes": 40, "media": 30, "sources": 20}
FIELDS = tuple(TEXT_LIMITS) + tuple(ARRAY_LIMITS)
STATES = ("DRAFT", "READY_FOR_REVIEW", "READY_FOR_CHANNELS")
SOURCE_KINDS = ("FABRICANTE", "ETIQUETA", "DISTRIBUIDOR", "OTRO")
READY_REQUIRED = (
    "brand", "title", "short_title", "short_description", "description",
    "category", "subcategory", "presentation", "seo_title", "seo_description",
)


def _now():
    return datetime.now(timezone.utc)


def blank_fields() -> dict:
    return {**{key: "" for key in TEXT_LIMITS}, **{key: [] for key in ARRAY_LIMITS}}


def _https_url(url: str) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return (
        parsed.scheme == "https" and bool(parsed.hostname)
        and not parsed.username and not parsed.password
        and parsed.hostname not in ("localhost", "127.0.0.1", "::1")
    )


def _canonical_fields(fields: dict) -> dict:
    if not isinstance(fields, dict) or any(key not in FIELDS for key in fields):
        raise ValueError("Los campos de la ficha no son válidos.")
    normalized = blank_fields()
    for key in TEXT_LIMITS:
        value = fields.get(key, "")
        if not isinstance(value, str):
            raise ValueError("El contenido del campo " + key + " no es válido.")
        normalized[key] = value.strip()
    specs = {
        "attributes": {"name": 90, "value": 450},
        "media": {"url": 1000, "alt": 180, "source_url": 1000, "kind": 5},
        "sources": {"name": 180, "url": 1000, "note": 500, "kind": 20},
    }
    for key, max_items in ARRAY_LIMITS.items():
        values = fields.get(key, [])
        if not isinstance(values, list) or len(values) > max_items:
            raise ValueError("Hay demasiados elementos en " + key + ".")
        cleaned = []
        for value in values:
            if not isinstance(value, dict) or set(value) - set(specs[key]):
                raise ValueError("Formato de " + key + " no válido.")
            row = {}
            for name, limit in specs[key].items():
                item = value.get(name, "")
                if not isinstance(item, str) or len(item.strip()) > limit:
                    raise ValueError("Campo no válido de " + key + ": " + name)
                row[name] = item.strip()
            if (
                (key == "media" and not row["url"] and not row["alt"] and not row["source_url"])
                or (key == "sources" and not row["name"] and not row["url"] and not row["note"])
                or (key == "attributes" and not any(row.values()))
            ):
                # An untouched newly-added editor row is not a saved resource.
                continue
            if key == "attributes" and not (row["name"] and row["value"]):
                raise ValueError("Cada característica necesita nombre y valor.")
            if key == "media":
                if row["kind"] not in ("IMAGE", "VIDEO") or not _https_url(row["url"]):
                    raise ValueError("Las imágenes y videos requieren enlaces HTTPS válidos.")
                if row["source_url"] and not _https_url(row["source_url"]):
                    raise ValueError("El origen multimedia debe tener una URL HTTPS válida.")
            if key == "sources":
                if row["kind"] not in SOURCE_KINDS or not row["name"]:
                    raise ValueError("Cada fuente requiere un tipo y nombre.")
                if row["url"] and not _https_url(row["url"]):
                    raise ValueError("El enlace de la fuente debe ser HTTPS válido.")
                if row["kind"] in ("FABRICANTE", "DISTRIBUIDOR") and not row["url"]:
                    raise ValueError("Las fuentes web deben incluir el enlace original.")
                if row["kind"] == "ETIQUETA" and not (row["url"] or row["note"]):
                    raise ValueError("Describí la etiqueta o agregá el enlace a su imagen.")
            cleaned.append(row)
        normalized[key] = cleaned
    return normalized


def _readiness(fields: dict) -> dict:
    missing = [name for name in READY_REQUIRED if not str(fields.get(name) or "").strip()]
    if not fields.get("attributes"):
        missing.append("attributes")
    if not any(m.get("kind") == "IMAGE" for m in fields.get("media") or []):
        missing.append("images")
    sources = fields.get("sources") or []
    if not any(s.get("kind") in ("FABRICANTE", "ETIQUETA") for s in sources):
        missing.append("primary_source")
    if fields.get("category") and not fields.get("subcategory"):
        # Covered above but make category hierarchy explicit.
        pass
    if not fields.get("seo_keywords"):
        missing.append("seo_keywords")
    total = len(READY_REQUIRED) + 4
    return {
        "missing": missing,
        "ready": not missing,
        "completed": total - len(missing),
        "total": total,
        "percent": round(100 * (total - len(missing)) / total),
        "policy": (
            "Listo para canales significa ficha completa y fuente primaria registrada "
            "por el operador; NO confirma automáticamente la autenticidad ni publica."
        ),
    }


def _gtin_check_digit_valid(digits: str) -> bool:
    if not digits:
        return True
    if not digits.isascii() or not digits.isdecimal() or len(digits) not in (8, 12, 13, 14):
        return False
    nums = [int(x) for x in digits]
    weighted_sum = sum(
        digit * (3 if i % 2 == 0 else 1)
        for i, digit in enumerate(reversed(nums[:-1]))
    )
    return (10 - weighted_sum % 10) % 10 == nums[-1]


def _validate(fields: dict, status: str):
    if status not in STATES:
        raise ValueError("Estado de revisión no permitido.")
    if not any(fields.values()):
        raise ValueError("Completá al menos un dato o una observación antes de guardar.")
    for field, max_length in TEXT_LIMITS.items():
        if len(fields[field]) > max_length:
            raise ValueError(f"El campo {field} supera el máximo permitido.")
    if fields["proposed_gtin"] and not _gtin_check_digit_valid(fields["proposed_gtin"]):
        raise ValueError("El GTIN propuesto debe tener 8, 12, 13 o 14 dígitos y un verificador válido.")
    if status == "READY_FOR_REVIEW" and not (fields["title"] or fields["brand"] or fields["description"]):
        raise ValueError("Para enviar a revisión, completá título, marca o descripción.")
    if status == "READY_FOR_CHANNELS":
        readiness = _readiness(fields)
        if not readiness["ready"]:
            raise ValueError(
                "Para dejarla lista para canales faltan: " + ", ".join(readiness["missing"])
            )


class EcommApiProductWorkspace:
    def __init__(self, db: Session):
        self.db = db

    def _source_pages(self) -> list[dict]:
        snapshot = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
        )
        pages = snapshot.payload if snapshot else []
        status = stage_status(pages)
        if not status["complete"] or status["quality"]["duplicate_variant_ids"]:
            raise ValueError("La copia API Ecomm no está completa o tiene IDs duplicados.")
        return pages

    def _source(self, ecomm_id: str) -> dict:
        if not ecomm_id or len(ecomm_id) > 120:
            raise ValueError("ID de variante Ecomm inválido.")
        matches = []
        for page in self._source_pages():
            for parent in page.get("items") or []:
                for variant in parent.get("variants") or []:
                    if not isinstance(variant, dict) or variant.get("invalid"):
                        continue
                    if str(variant.get("id")) == ecomm_id:
                        matches.append({
                            "ecomm_id": ecomm_id,
                            "sku": str(variant.get("sku") or "").strip(),
                            "product_name": str(parent.get("description") or "").strip(),
                            "variant_description": (
                                variant.get("variant_description") or variant.get("description")
                            ),
                            "is_combo": variant.get("is_combo"),
                            "gtin": variant.get("gtin") or variant.get("barcode"),
                            "stock_at_capture": variant.get("total_stock"),
                            "captured_at": page.get("captured_at"),
                        })
        if len(matches) != 1 or not matches[0]["sku"]:
            raise ValueError("El ID de Ecomm no corresponde a una única variante API verificable.")
        return matches[0]

    @staticmethod
    def _serialize(edit: EcommApiProductEdit | None, source: dict) -> dict:
        changed = bool(edit and edit.source_sku != source["sku"])
        return {
            "available": edit is not None,
            "ecomm_id": source["ecomm_id"],
            "source": source,
            "source_sku_changed": changed,
            "status": edit.status if edit else "NOT_STARTED",
            "version": edit.version if edit else 0,
            "fields": {**blank_fields(), **dict(edit.fields or {})} if edit else blank_fields(),
            "readiness": _readiness({**blank_fields(), **dict(edit.fields or {})} if edit else blank_fields()),
            "history": list(edit.history or []) if edit else [],
            "created_at": edit.created_at.isoformat() if edit else None,
            "updated_at": edit.updated_at.isoformat() if edit else None,
            "saved_in": "KIKI_POSTGRESQL_INTERNAL_ONLY",
            "external_writes_enabled": False,
        }

    def get(self, ecomm_id: str) -> dict:
        source = self._source(ecomm_id)
        edit = self.db.scalar(
            select(EcommApiProductEdit).where(EcommApiProductEdit.ecomm_id == ecomm_id)
        )
        return self._serialize(edit, source)

    def save(self, ecomm_id: str, fields: dict, status: str, expected_version: int) -> dict:
        if expected_version < 0:
            raise ValueError("Número de versión inválido.")
        normalized = _canonical_fields(fields)
        _validate(normalized, status)
        source = self._source(ecomm_id)
        edit = self.db.scalar(
            select(EcommApiProductEdit)
            .where(EcommApiProductEdit.ecomm_id == ecomm_id)
            .with_for_update()
        )
        actual = edit.version if edit else 0
        if expected_version != actual:
            raise ValueError(
                "La ficha fue actualizada en otra sesión. Volvé a abrirla antes de guardar."
            )
        if edit and edit.source_sku != source["sku"]:
            raise ValueError(
                "El SKU del ID Ecomm cambió desde que se guardó esta ficha. "
                "Revisá la identidad antes de seguir editando."
            )
        if edit and edit.fields == normalized and edit.status == status:
            return self._serialize(edit, source)

        now = _now()
        previous = dict(edit.fields or {}) if edit else {}
        previous_status = edit.status if edit else "NOT_STARTED"
        event = {
            "at": now.isoformat(),
            "version": actual + 1,
            "previous_status": previous_status,
            "new_status": status,
            "changes": {
                key: {"before": previous.get(key, ""), "after": normalized[key]}
                for key in FIELDS if previous.get(key, "") != normalized[key]
            },
            "source": STAGE_SOURCE,
            "external_writes": False,
        }
        if not edit:
            edit = EcommApiProductEdit(
                ecomm_id=ecomm_id, source_sku=source["sku"],
                source_snapshot=source, created_at=now,
                fields=normalized, status=status, version=1, history=[event],
                updated_at=now,
            )
            self.db.add(edit)
        else:
            edit.fields = normalized
            edit.status = status
            edit.version = actual + 1
            edit.updated_at = now
            edit.history = list(edit.history or []) + [event]
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError(
                "Otro operador guardó esta ficha al mismo tiempo. Volvé a abrirla."
            ) from exc
        self.db.refresh(edit)
        return self._serialize(edit, source)

    def list_saved(self, query: str = "", status: str = "", page: int = 1,
                   limit: int = 25) -> dict:
        if page < 1 or page > 100000 or limit < 1 or limit > 50 or len(query) > 80:
            raise ValueError("Filtro o paginación inválidos.")
        if status and status not in STATES:
            raise ValueError("Estado no válido.")
        # Verify Ecomm API capture exists before presenting saved items as API-linked.
        self._source_pages()
        all_edits = self.db.scalars(
            select(EcommApiProductEdit).order_by(EcommApiProductEdit.updated_at.desc())
        ).all()
        totals = Counter(x.status for x in all_edits)
        term = query.casefold().strip()
        filtered = [
            x for x in all_edits
            if (not status or x.status == status)
            and (not term or any(term in str(value or "").casefold()
                for value in (
                    x.ecomm_id, x.source_sku,
                    (x.source_snapshot or {}).get("product_name"),
                    (x.fields or {}).get("brand"),
                    (x.fields or {}).get("title"),
                )))
        ]
        offset = (page - 1) * limit
        return {
            "total": len(filtered), "page": page, "limit": limit,
            "summary": {"total_saved": len(all_edits),
                        "drafts": totals["DRAFT"],
                        "ready_for_review": totals["READY_FOR_REVIEW"],
                        "ready_for_channels": totals["READY_FOR_CHANNELS"]},
            "items": [{
                "ecomm_id": x.ecomm_id,
                "sku": x.source_sku,
                "product_name": (x.source_snapshot or {}).get("product_name"),
                "title": (x.fields or {}).get("title") or "",
                "brand": (x.fields or {}).get("brand") or "",
                "status": x.status, "version": x.version,
                "category": (x.fields or {}).get("category") or "",
                "subcategory": (x.fields or {}).get("subcategory") or "",
                "updated_at": x.updated_at.isoformat(),
            } for x in filtered[offset:offset + limit]],
            "saved_in": "KIKI_POSTGRESQL_INTERNAL_ONLY",
            "external_writes_enabled": False,
        }
