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

FIELDS = ("brand", "title", "description", "proposed_gtin", "note")
STATES = ("DRAFT", "READY_FOR_REVIEW")


def _now():
    return datetime.now(timezone.utc)


def _canonical_fields(fields: dict) -> dict:
    if not isinstance(fields, dict) or any(key not in FIELDS for key in fields):
        raise ValueError("Los campos de la ficha no son válidos.")
    return {name: str(fields.get(name) or "").strip() for name in FIELDS}


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
    bounds = {"brand": 120, "title": 180, "description": 3000,
              "proposed_gtin": 14, "note": 1200}
    for field, max_length in bounds.items():
        if len(fields[field]) > max_length:
            raise ValueError(f"El campo {field} supera el máximo permitido.")
    if fields["proposed_gtin"] and not _gtin_check_digit_valid(fields["proposed_gtin"]):
        raise ValueError("El GTIN propuesto debe tener 8, 12, 13 o 14 dígitos y un verificador válido.")
    if status == "READY_FOR_REVIEW" and not (fields["title"] or fields["brand"] or fields["description"]):
        raise ValueError("Para enviar a revisión, completá título, marca o descripción.")


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
            "fields": dict(edit.fields or {}) if edit else {k: "" for k in FIELDS},
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
                        "ready_for_review": totals["READY_FOR_REVIEW"]},
            "items": [{
                "ecomm_id": x.ecomm_id,
                "sku": x.source_sku,
                "product_name": (x.source_snapshot or {}).get("product_name"),
                "title": (x.fields or {}).get("title") or "",
                "brand": (x.fields or {}).get("brand") or "",
                "status": x.status, "version": x.version,
                "updated_at": x.updated_at.isoformat(),
            } for x in filtered[offset:offset + limit]],
            "saved_in": "KIKI_POSTGRESQL_INTERNAL_ONLY",
            "external_writes_enabled": False,
        }
