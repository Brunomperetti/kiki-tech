from datetime import datetime, timezone
import re
import unicodedata

from sqlalchemy.orm import Session

from ..database.models import (
    CatalogCoreConflictDecision,
    EnrichmentExternalResearch,
)
from ..repositories.catalog_repository import CatalogRepository
from .enrichment_review_service import EnrichmentReviewService


class CatalogContinuityService:
    """Keep validated KIKI core data stable across newer Ecomm snapshots.

    Ecomm remains the source feed. Accepted KIKI evidence remains persisted. When a
    newer Ecomm value disagrees with a previously validated KIKI value, this service
    creates an explicit human-review conflict instead of silently replacing either
    side.
    """

    USE_KIKI = "USE_KIKI"
    USE_ECOMM = "USE_ECOMM"
    VALID_DECISIONS = {USE_KIKI, USE_ECOMM}

    ACCEPTED_STATUSES = {"EVIDENCE_ACCEPTED", "GTIN_NOT_APPLICABLE"}

    FIELD_LABELS = {
        "brand": "Marca",
        "ean": "EAN / GTIN",
    }

    def __init__(self, db: Session):
        self.db = db
        self.repo = CatalogRepository(db)

    def report(self) -> dict:
        products = list(self.repo.snapshot("ECOMM_APP"))
        product_index = {
            EnrichmentReviewService.product_key(product): product
            for product in products
        }
        evidence_rows = (
            self.db.query(EnrichmentExternalResearch)
            .filter(EnrichmentExternalResearch.status.in_(self.ACCEPTED_STATUSES))
            .all()
        )
        decisions = {
            row.conflict_key: row
            for row in self.db.query(CatalogCoreConflictDecision).all()
        }

        items = []
        validated_products = set()
        missing_products = set()

        for evidence in evidence_rows:
            product_key = evidence.product_key
            validated_products.add(product_key)
            product = product_index.get(product_key)
            if product is None:
                missing_products.add(product_key)
                items.append(
                    {
                        "conflict_key": f"{product_key}:product",
                        "product_key": product_key,
                        "product": self._product_view(evidence.product_snapshot or {}),
                        "field": "product",
                        "field_label": "Producto",
                        "state": "MISSING_FROM_CURRENT_ECOMM",
                        "ecomm_value": None,
                        "kiki_value": "Datos validados conservados",
                        "effective_value": "Datos validados conservados",
                        "source_name": evidence.source_name,
                        "source_url": evidence.source_url,
                        "confidence": evidence.confidence,
                        "updated_at": evidence.updated_at.isoformat()
                        if evidence.updated_at
                        else None,
                        "decision": None,
                    }
                )
                continue

            for field, kiki_value, is_exception in self._validated_fields(evidence):
                item = self._field_item(
                    product_key=product_key,
                    product=product,
                    field=field,
                    kiki_value=kiki_value,
                    is_exception=is_exception,
                    evidence=evidence,
                    decision=decisions.get(f"{product_key}:{field}"),
                )
                items.append(item)

        summary = {
            "validated_products": len(validated_products),
            "validated_fields": sum(item["field"] != "product" for item in items),
            "kiki_only": sum(item["state"] == "KIKI_ONLY" for item in items),
            "aligned": sum(item["state"] == "ALIGNED" for item in items),
            "conflicts": sum(item["state"] == "CONFLICT" for item in items),
            "resolved_use_kiki": sum(
                item["state"] == "RESOLVED_USE_KIKI" for item in items
            ),
            "resolved_use_ecomm": sum(
                item["state"] == "RESOLVED_USE_ECOMM" for item in items
            ),
            "stale_decisions": sum(
                item["state"] == "STALE_DECISION" for item in items
            ),
            "missing_from_current_ecomm": len(missing_products),
        }

        items.sort(key=self._sort_key)
        return {
            "summary": summary,
            "policy": {
                "mode": "KIKI_EFFECTIVE_CORE_DATA",
                "description": (
                    "Un nuevo reporte de Ecomm actualiza datos operativos, pero no borra "
                    "evidencia validada en KIKI. Si Ecomm y KIKI difieren en marca o GTIN, "
                    "KIKI exige una decisión humana antes de usar ese campo para publicar."
                ),
            },
            "items": items,
        }

    def effective_index(self, products: list[dict] | None = None) -> dict[str, dict]:
        products = list(products if products is not None else self.repo.snapshot("ECOMM_APP"))
        report = self.report()
        item_index: dict[str, list[dict]] = {}
        for item in report["items"]:
            if item["field"] == "product":
                continue
            item_index.setdefault(item["product_key"], []).append(item)

        result = {}
        for product in products:
            key = EnrichmentReviewService.product_key(product)
            fields = item_index.get(key, [])
            brand = product.get("brand")
            ean = product.get("ean")
            gtin_exception = False
            conflicts = []
            sources = []

            for item in fields:
                if item["state"] in {"CONFLICT", "STALE_DECISION"}:
                    conflicts.append(item)
                    continue
                if item["field"] == "brand":
                    brand = item["effective_value"]
                elif item["field"] == "ean":
                    if item.get("kiki_exception") and item["state"] != "RESOLVED_USE_ECOMM":
                        ean = None
                        gtin_exception = True
                    else:
                        ean = item["effective_value"]
                        gtin_exception = False
                sources.append(
                    {
                        "field": item["field"],
                        "source_name": item.get("source_name"),
                        "source_url": item.get("source_url"),
                        "confidence": item.get("confidence"),
                        "state": item["state"],
                    }
                )

            result[key] = {
                "brand": brand,
                "ean": ean,
                "gtin_exception": gtin_exception,
                "conflicts": conflicts,
                "sources": sources,
                "has_kiki_validation": bool(fields),
            }
        return result

    def save_decision(
        self,
        conflict_key: str,
        decision_value: str,
        note: str | None = None,
    ) -> dict:
        decision_value = str(decision_value or "").strip().upper()
        if decision_value not in self.VALID_DECISIONS:
            raise ValueError("La decisión debe ser USE_KIKI o USE_ECOMM.")

        current = next(
            (
                item
                for item in self.report()["items"]
                if item["conflict_key"] == conflict_key
            ),
            None,
        )
        if current is None or current["field"] == "product":
            raise ValueError("El conflicto ya no está disponible.")
        if current["state"] not in {"CONFLICT", "STALE_DECISION", "RESOLVED_USE_KIKI", "RESOLVED_USE_ECOMM"}:
            raise ValueError("Ese dato ya no presenta un conflicto entre KIKI y Ecomm.")

        now = datetime.now(timezone.utc)
        snapshot = self._decision_snapshot(current)
        row = (
            self.db.query(CatalogCoreConflictDecision)
            .filter(CatalogCoreConflictDecision.conflict_key == conflict_key)
            .one_or_none()
        )
        history = list(row.history or []) if row else []
        history.append(
            {
                "at": now.isoformat(),
                "decision": decision_value,
                "note": (note or "").strip() or None,
                "source_snapshot": snapshot,
            }
        )
        if row is None:
            row = CatalogCoreConflictDecision(
                conflict_key=conflict_key,
                product_key=current["product_key"],
                field=current["field"],
                decision=decision_value,
                source_snapshot=snapshot,
                note=(note or "").strip() or None,
                history=history[-100:],
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.product_key = current["product_key"]
            row.field = current["field"]
            row.decision = decision_value
            row.source_snapshot = snapshot
            row.note = (note or "").strip() or None
            row.history = history[-100:]
            row.updated_at = now

        self.db.commit()
        refreshed = next(
            item
            for item in self.report()["items"]
            if item["conflict_key"] == conflict_key
        )
        return refreshed

    def _field_item(
        self,
        *,
        product_key: str,
        product: dict,
        field: str,
        kiki_value,
        is_exception: bool,
        evidence: EnrichmentExternalResearch,
        decision: CatalogCoreConflictDecision | None,
    ) -> dict:
        ecomm_value = product.get(field)
        conflict_key = f"{product_key}:{field}"
        same = self._same_value(field, ecomm_value, kiki_value, is_exception)

        if self._empty(ecomm_value):
            state = "KIKI_ONLY"
            effective_value = None if is_exception else kiki_value
        elif same:
            state = "ALIGNED"
            effective_value = ecomm_value
        else:
            current_snapshot = {
                "product_key": product_key,
                "field": field,
                "ecomm_value": self._normalized_snapshot_value(ecomm_value),
                "kiki_value": self._normalized_snapshot_value(kiki_value),
                "kiki_exception": bool(is_exception),
            }
            if decision and decision.source_snapshot == current_snapshot:
                if decision.decision == self.USE_KIKI:
                    state = "RESOLVED_USE_KIKI"
                    effective_value = None if is_exception else kiki_value
                else:
                    state = "RESOLVED_USE_ECOMM"
                    effective_value = ecomm_value
            elif decision:
                state = "STALE_DECISION"
                effective_value = None
            else:
                state = "CONFLICT"
                effective_value = None

        return {
            "conflict_key": conflict_key,
            "product_key": product_key,
            "product": self._product_view(product),
            "field": field,
            "field_label": self.FIELD_LABELS[field],
            "state": state,
            "ecomm_value": ecomm_value,
            "kiki_value": "No aplica / sin GTIN" if is_exception else kiki_value,
            "kiki_exception": bool(is_exception),
            "effective_value": effective_value,
            "source_name": evidence.source_name,
            "source_url": evidence.source_url,
            "confidence": evidence.confidence,
            "updated_at": evidence.updated_at.isoformat()
            if evidence.updated_at
            else None,
            "decision": decision.decision if decision else None,
        }

    @staticmethod
    def _validated_fields(evidence: EnrichmentExternalResearch):
        fields = []
        if evidence.proposed_brand:
            fields.append(("brand", evidence.proposed_brand, False))
        if evidence.status == "GTIN_NOT_APPLICABLE":
            fields.append(("ean", None, True))
        elif evidence.proposed_ean:
            fields.append(("ean", evidence.proposed_ean, False))
        return fields

    @classmethod
    def _same_value(cls, field: str, ecomm_value, kiki_value, is_exception: bool) -> bool:
        if is_exception:
            return cls._empty(ecomm_value)
        if cls._empty(ecomm_value) or cls._empty(kiki_value):
            return False
        if field == "ean":
            return cls._digits(ecomm_value) == cls._digits(kiki_value)
        return cls._text(ecomm_value) == cls._text(kiki_value)

    @staticmethod
    def _empty(value) -> bool:
        return value is None or str(value).strip() == ""

    @staticmethod
    def _digits(value) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    def _text(value) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return " ".join(text.casefold().split())

    @staticmethod
    def _normalized_snapshot_value(value):
        if value is None:
            return None
        return str(value).strip()

    @staticmethod
    def _product_view(product: dict) -> dict:
        return {
            "ecomm_id": product.get("ecomm_id"),
            "sku": product.get("sku_effective")
            or product.get("sku_variant")
            or product.get("sku"),
            "name": product.get("name"),
            "brand": product.get("brand"),
            "ean": product.get("ean"),
            "stock": product.get("stock"),
            "price": product.get("price"),
        }

    @staticmethod
    def _decision_snapshot(item: dict) -> dict:
        return {
            "product_key": item["product_key"],
            "field": item["field"],
            "ecomm_value": CatalogContinuityService._normalized_snapshot_value(
                item.get("ecomm_value")
            ),
            "kiki_value": (
                None
                if item.get("kiki_exception")
                else CatalogContinuityService._normalized_snapshot_value(
                    item.get("kiki_value")
                )
            ),
            "kiki_exception": bool(item.get("kiki_exception")),
        }

    @staticmethod
    def _sort_key(item: dict) -> tuple:
        rank = {
            "CONFLICT": 0,
            "STALE_DECISION": 1,
            "KIKI_ONLY": 2,
            "MISSING_FROM_CURRENT_ECOMM": 3,
            "RESOLVED_USE_KIKI": 4,
            "RESOLVED_USE_ECOMM": 5,
            "ALIGNED": 6,
        }
        return (
            rank.get(item["state"], 99),
            str(item.get("product", {}).get("name") or "").casefold(),
            item.get("field") or "",
        )
