from collections import Counter

from sqlalchemy.orm import Session

from ..database.models import (
    EnrichmentExternalResearch,
    MercadoLibreConnection,
    PrepublicationImageReview,
    PrepublicationMetadataReview,
)
from .catalog_continuity_service import CatalogContinuityService
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
            .filter(
                EnrichmentExternalResearch.status.in_(
                    {"EVIDENCE_ACCEPTED", "GTIN_NOT_APPLICABLE"}
                )
            )
            .all()
        }
        approved_images = {
            row.product_key: row
            for row in self.db.query(PrepublicationImageReview)
            .filter(PrepublicationImageReview.status == "APPROVED")
            .all()
        }
        approved_metadata = {
            row.product_key: row
            for row in self.db.query(PrepublicationMetadataReview)
            .filter(PrepublicationMetadataReview.status == "APPROVED")
            .all()
        }
        ml_connected = self.db.query(MercadoLibreConnection).first() is not None
        readiness_items = list(readiness.get("items") or [])
        effective_core = CatalogContinuityService(self.db).effective_index(
            [dict(item.get("product") or {}) for item in readiness_items]
        )

        items = []
        source_counts = Counter()
        image_passed = 0
        category_passed = 0
        attributes_passed = 0
        ready_for_preview = 0
        for item in readiness_items:
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
            effective = effective_core.get(key) or {}
            if evidence is not None:
                conflicts = effective.get("conflicts") or []
                gtin_exception = bool(effective.get("gtin_exception"))
                verified = {
                    "brand": effective.get("brand"),
                    "ean": effective.get("ean"),
                    "gtin_exception": gtin_exception,
                    "source_name": evidence.source_name,
                    "source_url": evidence.source_url,
                    "confidence": evidence.confidence,
                    "core_conflicts": [
                        {
                            "conflict_key": conflict.get("conflict_key"),
                            "field": conflict.get("field"),
                            "field_label": conflict.get("field_label"),
                            "ecomm_value": conflict.get("ecomm_value"),
                            "kiki_value": conflict.get("kiki_value"),
                            "state": conflict.get("state"),
                        }
                        for conflict in conflicts
                    ],
                }
                if conflicts:
                    source = (
                        "ACCEPTED_GTIN_EXCEPTION"
                        if evidence.status == "GTIN_NOT_APPLICABLE"
                        else "ACCEPTED_EVIDENCE"
                    )
                    source_label = "Requiere resolver conflicto KIKI / Ecomm"
                elif gtin_exception and verified["brand"]:
                    source = "ACCEPTED_GTIN_EXCEPTION"
                    source_label = "Excepción de GTIN documentada"
                elif verified["brand"] and verified["ean"]:
                    source = "ACCEPTED_EVIDENCE"
                    source_label = "Datos efectivos validados por KIKI"
            elif readiness_status == PublicationReadinessService.READY_CORE_DATA:
                verified = {
                    "brand": product.get("brand"),
                    "ean": product.get("ean"),
                    "source_name": "Ecomm-App",
                    "source_url": None,
                    "confidence": "CATALOG",
                    "core_conflicts": [],
                }
                if verified["brand"] and verified["ean"]:
                    source = "ECOMM_CORE"
                    source_label = "Datos centrales validados desde Ecomm-App"

            if not source or not verified:
                continue

            source_counts[source] += 1
            images_status = "PASSED" if key in approved_images else "WAITING_IMAGE_DATA"
            if images_status == "PASSED":
                image_passed += 1
            metadata = approved_metadata.get(key)
            conditional_pending = []
            conditional_required = []
            conditional_validation_status = "NOT_APPLICABLE"
            core_data_status = "PASSED"
            if verified.get("core_conflicts"):
                core_data_status = "BLOCKED"
            elif verified.get("gtin_exception"):
                core_data_status = "READY_TO_VALIDATE"
            if metadata is not None:
                (
                    conditional_validation_status,
                    conditional_required,
                    conditional_pending,
                ) = self._conditional_state(metadata.attributes or [])
                category_status = "PASSED"
                category_passed += 1
                required_ids = {
                    str(attribute.get("id") or "").upper()
                    for attribute in (metadata.required_missing or [])
                }
                conditional_ids = {
                    str(attribute.get("id") or "").upper()
                    for attribute in conditional_pending
                }
                gtin_required = bool(
                    {"GTIN", "EAN", "GTIN14"}.intersection(
                        required_ids | conditional_ids
                    )
                )
                if verified.get("core_conflicts"):
                    core_data_status = "BLOCKED"
                elif verified.get("gtin_exception"):
                    core_data_status = "BLOCKED" if gtin_required else "PASSED"
                if metadata.required_missing or conditional_pending:
                    attributes_status = "READY_TO_VALIDATE"
                else:
                    attributes_status = "PASSED"
                    attributes_passed += 1
            else:
                category_status = "READY_TO_VALIDATE" if ml_connected else "WAITING_ML_CONNECTION"
                attributes_status = "READY_TO_VALIDATE" if ml_connected else "WAITING_ML_CONNECTION"

            preview_status = (
                "READY_TO_VALIDATE"
                if core_data_status == "PASSED"
                and images_status == "PASSED"
                and category_status == "PASSED"
                and attributes_status == "PASSED"
                else "BLOCKED"
            )
            if preview_status == "READY_TO_VALIDATE":
                ready_for_preview += 1
            items.append(
                {
                    "product_key": key,
                    "product": product,
                    "core_source": source,
                    "core_source_label": source_label,
                    "verified_core_data": verified,
                    "status": self.WAITING_EXTERNAL_CONTROLS,
                    "checks": {
                        "core_data": core_data_status,
                        "images": images_status,
                        "category": category_status,
                        "attributes": attributes_status,
                        "preview": preview_status,
                    },
                    "ml_metadata": (
                        {
                            "category_id": metadata.category_id,
                            "category_name": metadata.category_name,
                            "domain_id": metadata.domain_id,
                            "domain_name": metadata.domain_name,
                            "required_missing": metadata.required_missing or [],
                            "conditional_validation_status": conditional_validation_status,
                            "conditional_required": conditional_required,
                            "conditional_pending": conditional_pending,
                        }
                        if metadata is not None
                        else None
                    ),
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
                "from_gtin_exception": source_counts["ACCEPTED_GTIN_EXCEPTION"],
                "approved_images": image_passed,
                "waiting_images": len(items) - image_passed,
                "waiting_ml_connection": 0 if ml_connected else len(items),
                "approved_categories": category_passed,
                "attributes_complete": attributes_passed,
                "ready_for_preview": ready_for_preview,
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
                    "Esta etapa no publica nada. Ingresan productos con marca y EAN/GTIN "
                    "resueltos, o con una excepción de GTIN documentada que luego debe ser "
                    "compatible con los requisitos de la categoría de Mercado Libre. "
                    "Si un nuevo Ecomm contradice un dato ya validado en KIKI, el producto se "
                    "bloquea hasta resolver explícitamente el conflicto. Todavía exige imágenes, "
                    "categoría, atributos, preview y confirmación humana "
                    "antes de cualquier futura escritura en Mercado Libre."
                ),
            },
            "items": items,
        }

    @staticmethod
    def _conditional_state(attributes: list[dict]) -> tuple[str, list[dict], list[dict]]:
        candidates = [
            attribute for attribute in attributes if attribute.get("conditional_required")
        ]
        if not candidates:
            return "NOT_APPLICABLE", [], []
        if not all(attribute.get("conditional_evaluated") for attribute in candidates):
            pending = [
                {"id": attribute.get("id"), "name": attribute.get("name")}
                for attribute in candidates
            ]
            return "PENDING", [], pending
        required = [
            attribute for attribute in candidates if attribute.get("conditional_required_now")
        ]
        pending = [
            {"id": attribute.get("id"), "name": attribute.get("name")}
            for attribute in required
            if attribute.get("verified_value") in {None, ""}
        ]
        return (
            "VALIDATED",
            [{"id": attribute.get("id"), "name": attribute.get("name")} for attribute in required],
            pending,
        )

    @staticmethod
    def _stock_value(value) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0
