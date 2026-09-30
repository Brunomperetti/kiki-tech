from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import Session

from ..repositories.catalog_repository import CatalogRepository


class PublicationReadinessService:
    """Classify reconciled Ecomm products before any future Mercado Libre write flow.

    READY_CORE_DATA means the product passed the checks that can be performed with the
    current Ecomm/XLSX + reconciliation data. It is intentionally not equivalent to
    "ready to publish": images, Mercado Libre category and category attributes still
    require validation later.
    """

    READY_CORE_DATA = "READY_CORE_DATA"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    NO_STOCK = "NO_STOCK"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"

    REASON_LABELS = {
        "EAN_MISSING": "Falta EAN/GTIN",
        "STOCK_MISSING": "Falta stock informado",
        "SKU_DUPLICATE": "SKU duplicado",
        "SKU_MISSING": "Falta SKU",
        "SKU_INVALID": "SKU inválido",
        "EAN_INVALID": "EAN inválido",
        "NAME_MISSING": "Falta nombre",
        "PRICE_INVALID": "Precio inválido",
        "STOCK_INVALID": "Stock inválido",
        "RECONCILIATION_REVIEW": "Conciliación requiere revisión",
        "DATA_ERROR": "Datos inconsistentes",
        "NO_STOCK": "Sin stock",
        "ALREADY_PUBLISHED": "Ya publicado",
        "CORE_DATA_OK": "Datos centrales OK",
    }

    def __init__(self, db: Session):
        self.repo = CatalogRepository(db)

    def report(self) -> dict:
        run = self.repo.latest_run()
        if not run:
            raise ValueError(
                "Primero ejecutá una reconciliación para preparar los candidatos de publicación."
            )

        items = []
        counts: Counter[str] = Counter()
        attention_reasons: Counter[str] = Counter()
        for result in run.results or []:
            product = result.get("product")
            if not product:
                continue
            readiness_status, reasons = self.classify(result)
            reason_codes = self.reason_codes(result, readiness_status)
            counts[readiness_status] += 1
            if readiness_status in {self.REVIEW_REQUIRED, self.BLOCKED}:
                attention_reasons.update(reason_codes)
            items.append(
                {
                    "product": product,
                    "reconciliation_status": result.get("status"),
                    "readiness_status": readiness_status,
                    "reason_codes": reason_codes,
                    "reasons": reasons,
                    "issues": result.get("issues") or [],
                    "matched_listing_ids": result.get("matched_listing_ids") or [],
                }
            )

        actionable = (
            counts[self.READY_CORE_DATA]
            + counts[self.REVIEW_REQUIRED]
            + counts[self.BLOCKED]
        )
        reason_summary = [
            {
                "code": code,
                "label": self.REASON_LABELS.get(code, code.replace("_", " ").title()),
                "count": count,
            }
            for code, count in attention_reasons.most_common()
        ]
        return {
            "reconciliation_run_id": run.id,
            "mercadolibre_source": (run.summary or {}).get("mercadolibre_source"),
            "summary": {
                "total_products": len(items),
                "actionable_with_stock": actionable,
                self.READY_CORE_DATA: counts[self.READY_CORE_DATA],
                self.REVIEW_REQUIRED: counts[self.REVIEW_REQUIRED],
                self.BLOCKED: counts[self.BLOCKED],
                self.NO_STOCK: counts[self.NO_STOCK],
                self.ALREADY_PUBLISHED: counts[self.ALREADY_PUBLISHED],
            },
            "reason_summary": reason_summary,
            "pending_external_checks": [
                "Imágenes disponibles y aptas para Mercado Libre",
                "Categoría de Mercado Libre",
                "Atributos obligatorios de la categoría",
            ],
            "items": items,
        }

    @classmethod
    def reason_codes(cls, result: dict, readiness_status: str) -> list[str]:
        if readiness_status == cls.ALREADY_PUBLISHED:
            return ["ALREADY_PUBLISHED"]
        if readiness_status == cls.NO_STOCK:
            return ["NO_STOCK"]
        if readiness_status == cls.READY_CORE_DATA:
            return ["CORE_DATA_OK"]

        issue_codes = [
            issue.get("code")
            for issue in result.get("issues") or []
            if issue.get("code")
        ]
        if issue_codes:
            return list(dict.fromkeys(issue_codes))
        if readiness_status == cls.REVIEW_REQUIRED:
            return ["RECONCILIATION_REVIEW"]
        return ["DATA_ERROR"]

    @classmethod
    def classify(cls, result: dict) -> tuple[str, list[str]]:
        status = result.get("status")
        product = result.get("product") or {}
        issues = result.get("issues") or []
        issue_codes = {issue.get("code") for issue in issues}
        issue_messages = [
            issue.get("message") for issue in issues if issue.get("message")
        ]

        if status == "ALREADY_PUBLISHED":
            return cls.ALREADY_PUBLISHED, ["Ya tiene una publicación asociada."]

        stock = cls._decimal(product.get("stock"))
        if stock is not None and stock <= 0:
            return cls.NO_STOCK, ["El producto no tiene stock disponible."]

        if status in {
            "POSSIBLE_DUPLICATE",
            "INVALID_SKU",
            "INVALID_EAN",
            "INCOMPLETE_DATA",
        }:
            return cls.BLOCKED, issue_messages or [
                "Tiene un error de datos que bloquea la preparación."
            ]

        if status == "REVIEW_REQUIRED":
            reason = result.get("reason")
            return cls.REVIEW_REQUIRED, [reason] if reason else issue_messages

        if status != "CANDIDATE_TO_PUBLISH":
            return cls.REVIEW_REQUIRED, [
                "El estado de conciliación requiere revisión antes de continuar."
            ]

        reasons: list[str] = []
        if stock is None:
            reasons.append("Falta stock informado.")
        if not product.get("ean") or "EAN_MISSING" in issue_codes:
            reasons.append("Falta EAN/GTIN; requiere revisión antes de publicar.")
        if reasons:
            return cls.REVIEW_REQUIRED, reasons

        return cls.READY_CORE_DATA, [
            "Datos centrales de Ecomm validados; faltan controles externos de imágenes, categoría y atributos."
        ]

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
