from decimal import Decimal

from sqlalchemy.orm import Session

from .publication_readiness_service import PublicationReadinessService


class EnrichmentService:
    """Build a small, controlled research queue for missing EAN/GTIN and brand data.

    This service is intentionally read-only. It does not call external systems and does
    not persist proposed values. The pilot CSV is meant to be researched and validated
    before any future import or write workflow is introduced.
    """

    PENDING_RESEARCH = "PENDING_RESEARCH"

    def __init__(self, db: Session):
        self.readiness = PublicationReadinessService(db)

    def report(self, limit: int = 20) -> dict:
        readiness_report = self.readiness.report()
        return self.build_report(readiness_report, limit)

    @classmethod
    def build_report(cls, readiness_report: dict, limit: int = 20) -> dict:
        if limit < 1 or limit > 100:
            raise ValueError("El límite del piloto debe estar entre 1 y 100 productos.")

        eligible = []
        for item in readiness_report.get("items") or []:
            enrichment_item = cls._to_enrichment_item(item)
            if enrichment_item:
                eligible.append(enrichment_item)

        eligible.sort(key=cls._priority_key)
        pilot = eligible[:limit]

        missing_ean = sum("EAN/GTIN" in item["missing_fields"] for item in eligible)
        missing_brand = sum("Marca" in item["missing_fields"] for item in eligible)
        missing_both = sum(len(item["missing_fields"]) == 2 for item in eligible)

        return {
            "reconciliation_run_id": readiness_report.get("reconciliation_run_id"),
            "mercadolibre_source": readiness_report.get("mercadolibre_source"),
            "summary": {
                "total_eligible": len(eligible),
                "missing_ean": missing_ean,
                "missing_brand": missing_brand,
                "missing_both": missing_both,
                "pilot_size": len(pilot),
                "pilot_limit": limit,
            },
            "policy": {
                "mode": "READ_ONLY_RESEARCH_PILOT",
                "description": (
                    "El piloto solo arma una cola de investigación. No modifica Ecomm-App "
                    "ni Mercado Libre y no acepta datos sin fuente verificable."
                ),
            },
            "items": pilot,
        }

    @classmethod
    def _to_enrichment_item(cls, item: dict) -> dict | None:
        if item.get("readiness_status") != PublicationReadinessService.REVIEW_REQUIRED:
            return None

        product = item.get("product") or {}
        stock = cls._decimal(product.get("stock"))
        if stock is None or stock <= 0:
            return None

        missing_fields = []
        if not product.get("ean"):
            missing_fields.append("EAN/GTIN")
        if not product.get("brand"):
            missing_fields.append("Marca")
        if not missing_fields:
            return None

        return {
            "product": product,
            "readiness_status": item.get("readiness_status"),
            "reason_codes": item.get("reason_codes") or [],
            "missing_fields": missing_fields,
            "research_status": cls.PENDING_RESEARCH,
            "proposal": {
                "ean": None,
                "brand": None,
                "source_name": None,
                "source_url": None,
                "confidence": None,
                "notes": None,
            },
        }

    @classmethod
    def _priority_key(cls, item: dict) -> tuple:
        product = item.get("product") or {}
        stock = cls._decimal(product.get("stock")) or Decimal("0")
        missing_count = len(item.get("missing_fields") or [])
        return (
            -missing_count,
            -stock,
            str(product.get("name") or "").casefold(),
            str(product.get("sku") or ""),
        )

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
