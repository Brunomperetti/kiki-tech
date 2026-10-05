from collections import Counter

from sqlalchemy.orm import Session

from ..database.models import (
    EnrichmentExternalResearch,
    MercadoLibreConnection,
    PrepublicationImageReview,
)
from .enrichment_review_service import EnrichmentReviewService
from .publication_readiness_service import PublicationReadinessService


class PrepublicationService:
    """Build the bridge between validated core data and future Mercado Libre publishing.

    This service is deliberately read-only. It does not publish, edit Ecomm-App, or
    write to Mercado Libre. It only shows which controls are already satisfied and
    which still depend on images or Mercado Libre metadata.
    """

    WAITING_EXTERNAL_CONTROLS = "WAITING_EXTERNAL_CONTROLS"

    def __init__(self, db: Session):
        self.db = db
        self.readiness = PublicationReadinessService(db)

    def report(self) -> dict:
        readiness = self.readiness.report()
        accepted = {
            row.product_key: row
            for row in self.db.query(EnrichmentExternalResearch)
            .filter(EnrichmentExternalResearch.status == "EVIDENCE_ACCEPTED")
            .all()
        }
        approved_images = {
            row.product_key: row
            for row in self.db.query(PrepublicationImageReview)
            .filter(PrepublicationImageReview.status == "APPROVED")
            .all()
        }
        ml_connected = self.db.query(MercadoLibreConnection).first() is not None

        items = []
        source_counts = Counter()
        image_passed = 0
        for item in readiness.get("items") or []:
            product = dict(item.get("product") or {})
            key = EnrichmentReviewService.product_key(product)
            readiness_status = item.get("readiness_status")
            evidence = accepted.get(key)

            if readiness_status in {
                PublicationReadinessService.ALREADY_PUBLISHED,
                PublicationReadinessService.NO_STOCK,
                PublicationReadinessService.EXCLUDED_BULK,
            }:
                continue

            source = None
            source_label = None
            verified = None
            if readiness_status == PublicationReadinessService.READY_CORE_DATA:
                verified = {
                    "brand": product.get("brand"),
                    "ean": product.get("ean"),
                    "source_name": "Ecomm-App",
                    "source_url": None,
                    "confidence": "CATALOG",
                }
                if verified["brand"] and verified["ean"]:
                    source = "ECOMM_CORE"
                    source_label = "Datos centrales validados desde Ecomm-App"
            elif evidence is not None:
                verified = {
                    "brand": product.get("brand") or evidence.proposed_brand,
                    "ean": product.get("ean") or evidence.proposed_ean,
                    "source_name": evidence.source_name,
                    "source_url": evidence.source_url,
                    "confidence": evidence.confidence,
                }
                if verified["brand"] and verified["ean"]:
                    source = "ACCEPTED_EVIDENCE"
                    source_label = "Evidencia externa aceptada"

            if not source or not verified:
                continue

            source_counts[source] += 1
            images_status = "PASSED" if key in approved_images else "WAITING_IMAGE_DATA"
            if images_status == "PASSED":
                image_passed += 1
            category_status = "READY_TO_VALIDATE" if ml_connected else "WAITING_ML_CONNECTION"
            attributes_status = "READY_TO_VALIDATE" if ml_connected else "WAITING_ML_CONNECTION"
            items.append(
                {
                    "product_key": key,
                    "product": product,
                    "core_source": source,
                    "core_source_label": source_label,
                    "verified_core_data": verified,
                    "status": self.WAITING_EXTERNAL_CONTROLS,
                    "checks": {
                        "core_data": "PASSED",
                        "images": images_status,
                        "category": category_status,
                        "attributes": attributes_status,
                        "preview": "BLOCKED",
                    },
                }
            )

        items.sort(
            key=lambda item: (
                0 if item["core_source"] == "ACCEPTED_EVIDENCE" else 1,
                -self._stock_value(item.get("product", {}).get("stock")),
                str(item.get("product", {}).get("name") or "").casefold(),
            )
        )

        return {
            "summary": {
                "total": len(items),
                "from_ecomm_core": source_counts["ECOMM_CORE"],
                "from_accepted_evidence": source_counts["ACCEPTED_EVIDENCE"],
                "approved_images": image_passed,
                "waiting_images": len(items) - image_passed,
                "waiting_ml_connection": 0 if ml_connected else len(items),
                "ready_for_preview": 0,
            },
            "mercadolibre_connected": ml_connected,
            "pending_controls": [
                "Imágenes disponibles y aptas para Mercado Libre",
                "Categoría de Mercado Libre",
                "Atributos obligatorios de la categoría",
                "Preview de la publicación",
            ],
            "policy": {
                "mode": "READ_ONLY_PREPUBLICATION",
                "description": (
                    "Esta etapa no publica nada. Solo ingresan productos con marca y EAN/GTIN "
                    "resueltos que además no estén excluidos por las reglas vigentes del masivo. "
                    "Todavía exige imágenes, categoría, atributos, preview y confirmación humana "
                    "antes de cualquier futura escritura en Mercado Libre."
                ),
            },
            "items": items,
        }

    @staticmethod
    def _stock_value(value) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0
