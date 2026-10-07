from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..database.models import PrepublicationMetadataReview
from .mercadolibre_service import MercadoLibreService
from .prepublication_service import PrepublicationService


class PrepublicationMetadataService:
    """Read ML category metadata and persist only KIKI's internal human decisions."""

    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ALLOWED_STATUSES = {DRAFT, READY_FOR_REVIEW, APPROVED, REJECTED}

    def __init__(
        self,
        db: Session,
        ml_service: MercadoLibreService | None = None,
    ):
        self.db = db
        self.prepublication = PrepublicationService(db)
        self.ml = ml_service or MercadoLibreService(db)

    def queue(self) -> dict:
        report = self.prepublication.report()
        saved = {
            row.product_key: row
            for row in self.db.query(PrepublicationMetadataReview).all()
        }
        items = [
            self._serialize(item, saved.get(item["product_key"]))
            for item in report.get("items") or []
        ]
        summary = {
            "total": len(items),
            self.DRAFT: 0,
            self.READY_FOR_REVIEW: 0,
            self.APPROVED: 0,
            self.REJECTED: 0,
            "attributes_complete": 0,
            "attributes_pending": 0,
        }
        for item in items:
            summary[item["metadata_status"]] += 1
            if item["metadata_status"] == self.APPROVED:
                if item["required_missing"]:
                    summary["attributes_pending"] += 1
                else:
                    summary["attributes_complete"] += 1

        return {
            "summary": summary,
            "mercadolibre_connected": report.get("mercadolibre_connected", False),
            "policy": {
                "mode": "READ_ONLY_ML_METADATA",
                "description": (
                    "KIKI Tech consulta el predictor de categorías y los atributos de Mercado "
                    "Libre en modo lectura. La categoría propuesta requiere confirmación humana. "
                    "No crea ni modifica publicaciones."
                ),
                "conditional_attributes": (
                    "Los atributos condicionalmente obligatorios todavía no se evalúan en esta "
                    "etapa; se muestran como pendientes de una validación posterior."
                ),
            },
            "items": items,
        }

    def analyze(self, product_key: str) -> dict:
        item = self._find_item(product_key)
        product = item.get("product") or {}
        title = str(product.get("name") or "").strip()
        if not title:
            raise ValueError("El producto no tiene título para predecir una categoría.")

        candidates = self._candidate_snapshot(self.ml.predict_categories(title, limit=3))
        if not candidates:
            raise ValueError("Mercado Libre no devolvió categorías candidatas para este producto.")

        selected = candidates[0]
        raw_attributes = self.ml.category_attributes(selected["category_id"])
        attributes, required_missing = self._attribute_snapshot(
            raw_attributes,
            item,
            selected.get("suggested_attributes") or [],
        )

        row = self._row(product_key)
        now = datetime.now(timezone.utc)
        history = list(row.history or []) if row else []
        history.append(
            {
                "at": now.isoformat(),
                "action": "ANALYZE",
                "category_id": selected["category_id"],
                "category_name": selected["category_name"],
            }
        )
        values = {
            "status": self.READY_FOR_REVIEW,
            "category_id": selected["category_id"],
            "category_name": selected["category_name"],
            "domain_id": selected.get("domain_id"),
            "domain_name": selected.get("domain_name"),
            "candidates": candidates,
            "attributes": attributes,
            "required_missing": required_missing,
            "product_snapshot": product,
            "history": history[-100:],
            "updated_at": now,
        }
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            row = PrepublicationMetadataReview(
                product_key=product_key,
                notes=None,
                created_at=now,
                **values,
            )
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._serialize(item, row)

    def analyze_pending(self, limit: int = 10) -> dict:
        if limit < 1 or limit > 20:
            raise ValueError("El lote de análisis debe estar entre 1 y 20 productos.")
        queue = self.queue()
        pending = [
            item
            for item in queue["items"]
            if item["metadata_status"] in {self.DRAFT, self.REJECTED}
        ][:limit]
        analyzed = []
        errors = []
        for item in pending:
            try:
                analyzed.append(self.analyze(item["product_key"]))
            except Exception as exc:
                errors.append(
                    {
                        "product_key": item["product_key"],
                        "message": str(exc) or "No se pudo analizar el producto.",
                    }
                )
        return {
            "requested": len(pending),
            "analyzed": len(analyzed),
            "errors": errors,
        }

    def save(
        self,
        product_key: str,
        status: str,
        category_id: str | None = None,
        notes: str | None = None,
    ) -> dict:
        if status not in self.ALLOWED_STATUSES:
            raise ValueError("Estado de revisión de categoría inválido.")
        item = self._find_item(product_key)
        row = self._row(product_key)
        if not row:
            raise ValueError("Primero analizá la categoría del producto con Mercado Libre.")

        selected_id = (category_id or row.category_id or "").strip()
        candidate = next(
            (
                candidate
                for candidate in row.candidates or []
                if candidate.get("category_id") == selected_id
            ),
            None,
        )
        if status in {self.READY_FOR_REVIEW, self.APPROVED} and not candidate:
            raise ValueError("Elegí una de las categorías propuestas por Mercado Libre.")

        attributes = list(row.attributes or [])
        required_missing = list(row.required_missing or [])
        if candidate and selected_id != row.category_id:
            raw_attributes = self.ml.category_attributes(selected_id)
            attributes, required_missing = self._attribute_snapshot(
                raw_attributes,
                item,
                candidate.get("suggested_attributes") or [],
            )

        now = datetime.now(timezone.utc)
        history = list(row.history or [])
        history.append(
            {
                "at": now.isoformat(),
                "action": status,
                "category_id": candidate.get("category_id") if candidate else None,
                "category_name": candidate.get("category_name") if candidate else None,
                "notes": (notes or "").strip() or None,
            }
        )
        row.status = status
        if candidate:
            row.category_id = candidate["category_id"]
            row.category_name = candidate["category_name"]
            row.domain_id = candidate.get("domain_id")
            row.domain_name = candidate.get("domain_name")
        row.attributes = attributes
        row.required_missing = required_missing
        row.notes = (notes or "").strip() or None
        row.product_snapshot = item.get("product") or {}
        row.history = history[-100:]
        row.updated_at = now
        self.db.commit()
        self.db.refresh(row)
        return self._serialize(item, row)

    def _find_item(self, product_key: str) -> dict:
        report = self.prepublication.report()
        item = next(
            (
                candidate
                for candidate in report.get("items") or []
                if candidate.get("product_key") == product_key
            ),
            None,
        )
        if not item:
            raise ValueError("El producto ya no está disponible en Pre-publicación.")
        if not report.get("mercadolibre_connected"):
            raise ValueError("Mercado Libre no está conectado.")
        return item

    def _row(self, product_key: str) -> PrepublicationMetadataReview | None:
        return (
            self.db.query(PrepublicationMetadataReview)
            .filter(PrepublicationMetadataReview.product_key == product_key)
            .one_or_none()
        )

    @staticmethod
    def _candidate_snapshot(candidates: list[dict]) -> list[dict]:
        result = []
        for candidate in candidates[:3]:
            category_id = str(candidate.get("category_id") or "").strip()
            if not category_id:
                continue
            result.append(
                {
                    "category_id": category_id,
                    "category_name": str(candidate.get("category_name") or category_id),
                    "domain_id": candidate.get("domain_id"),
                    "domain_name": candidate.get("domain_name"),
                    "suggested_attributes": [
                        {
                            "id": attribute.get("id"),
                            "name": attribute.get("name"),
                            "value_id": attribute.get("value_id"),
                            "value_name": attribute.get("value_name"),
                        }
                        for attribute in candidate.get("attributes") or []
                        if isinstance(attribute, dict) and attribute.get("id")
                    ],
                }
            )
        return result

    @classmethod
    def _attribute_snapshot(
        cls,
        attributes: list[dict],
        item: dict,
        suggestions: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        product = item.get("product") or {}
        verified = item.get("verified_core_data") or {}
        suggestion_index = {
            str(suggestion.get("id")): suggestion
            for suggestion in suggestions
            if suggestion.get("id")
        }
        snapshot = []
        missing = []
        for attribute in attributes:
            attribute_id = str(attribute.get("id") or "").strip()
            if not attribute_id:
                continue
            tags = attribute.get("tags")
            tags = tags if isinstance(tags, dict) else {}
            required = bool(tags.get("required"))
            conditional = bool(tags.get("conditional_required"))
            verified_value = cls._verified_value(attribute_id, product, verified)
            suggestion = suggestion_index.get(attribute_id) or {}
            record = {
                "id": attribute_id,
                "name": attribute.get("name") or attribute_id,
                "value_type": attribute.get("value_type"),
                "required": required,
                "conditional_required": conditional,
                "catalog_required": bool(tags.get("catalog_required")),
                "verified_value": verified_value,
                "suggested_value_id": suggestion.get("value_id"),
                "suggested_value": suggestion.get("value_name"),
            }
            snapshot.append(record)
            if required and not verified_value:
                missing.append({"id": attribute_id, "name": record["name"]})
        return snapshot, missing

    @staticmethod
    def _verified_value(attribute_id: str, product: dict, verified: dict):
        code = attribute_id.upper()
        if code == "BRAND":
            return verified.get("brand") or product.get("brand")
        if code in {"GTIN", "EAN", "GTIN14"}:
            return verified.get("ean") or product.get("ean")
        if code == "SELLER_SKU":
            return product.get("sku_effective") or product.get("sku")
        return None

    @staticmethod
    def _serialize(item: dict, row: PrepublicationMetadataReview | None) -> dict:
        product = item.get("product") or {}
        if not row:
            return {
                "product_key": item["product_key"],
                "product": product,
                "verified_core_data": item.get("verified_core_data") or {},
                "image_status": item.get("checks", {}).get("images"),
                "metadata_status": PrepublicationMetadataService.DRAFT,
                "category_id": None,
                "category_name": None,
                "domain_id": None,
                "domain_name": None,
                "candidates": [],
                "attributes": [],
                "required_missing": [],
                "notes": None,
                "updated_at": None,
                "history_count": 0,
            }
        return {
            "product_key": item["product_key"],
            "product": product,
            "verified_core_data": item.get("verified_core_data") or {},
            "image_status": item.get("checks", {}).get("images"),
            "metadata_status": row.status,
            "category_id": row.category_id,
            "category_name": row.category_name,
            "domain_id": row.domain_id,
            "domain_name": row.domain_name,
            "candidates": row.candidates or [],
            "attributes": row.attributes or [],
            "required_missing": row.required_missing or [],
            "notes": row.notes,
            "updated_at": row.updated_at,
            "history_count": len(row.history or []),
        }
