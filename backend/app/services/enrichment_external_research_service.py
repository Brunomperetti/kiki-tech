from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..database.models import EnrichmentExternalResearch, EnrichmentReviewDecision
from .enrichment_review_service import EnrichmentReviewService


class EnrichmentExternalResearchService:
    """Persist source-backed research without writing to external systems."""

    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    EVIDENCE_ACCEPTED = "EVIDENCE_ACCEPTED"
    REJECTED = "REJECTED"

    VALID_STATUSES = {DRAFT, READY_FOR_REVIEW, EVIDENCE_ACCEPTED, REJECTED}
    VALID_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}

    def __init__(self, db: Session):
        self.db = db
        self.review = EnrichmentReviewService(db)

    def queue(self) -> dict:
        review_queue = self.review.queue()
        active = {
            item["product_key"]: item
            for item in review_queue.get("items") or []
            if item.get("review_status") == EnrichmentReviewService.EXTERNAL_RESEARCH
        }
        records = {
            row.product_key: row
            for row in self.db.query(EnrichmentExternalResearch).all()
        }

        items = []
        for product_key, item in active.items():
            items.append(self._serialize(item, records.get(product_key)))

        items.sort(key=self._sort_key)
        status_counts = {status: 0 for status in self.VALID_STATUSES}
        for item in items:
            status_counts[item["research_status"]] += 1

        return {
            "summary": {
                "total": len(items),
                "DRAFT": status_counts[self.DRAFT],
                "READY_FOR_REVIEW": status_counts[self.READY_FOR_REVIEW],
                "EVIDENCE_ACCEPTED": status_counts[self.EVIDENCE_ACCEPTED],
                "REJECTED": status_counts[self.REJECTED],
            },
            "policy": {
                "mode": "SOURCE_BACKED_INTERNAL_RESEARCH",
                "description": (
                    "La investigación externa se guarda solo dentro de KIKI Tech. "
                    "Aceptar evidencia no actualiza Ecomm-App ni Mercado Libre y no habilita "
                    "publicaciones automáticas."
                ),
            },
            "items": items,
        }

    def save(
        self,
        product_key: str,
        status: str,
        proposed_brand: str | None = None,
        proposed_ean: str | None = None,
        source_name: str | None = None,
        source_url: str | None = None,
        confidence: str | None = None,
        notes: str | None = None,
    ) -> dict:
        status = self._clean(status).upper()
        if status not in self.VALID_STATUSES:
            raise ValueError("Estado de investigación externa no válido.")

        review_decision = (
            self.db.query(EnrichmentReviewDecision)
            .filter(EnrichmentReviewDecision.product_key == product_key)
            .one_or_none()
        )
        if review_decision is None or review_decision.status != EnrichmentReviewService.EXTERNAL_RESEARCH:
            raise ValueError("El producto debe estar marcado como 'Investigar afuera'.")

        review_items = {
            item["product_key"]: item
            for item in self.review.queue().get("items") or []
        }
        item = review_items.get(product_key)
        if item is None:
            raise ValueError("El producto ya no está disponible para investigación externa.")

        proposed_brand = self._nullable(proposed_brand, 255)
        proposed_ean = self._digits_or_none(proposed_ean)
        source_name = self._nullable(source_name, 255)
        source_url = self._nullable(source_url, 2000)
        confidence = self._nullable(confidence, 20)
        confidence = confidence.upper() if confidence else None
        notes = self._nullable(notes, 4000)

        if confidence and confidence not in self.VALID_CONFIDENCE:
            raise ValueError("Confianza no válida.")
        if source_url and not self._valid_http_url(source_url):
            raise ValueError("La URL de la fuente debe comenzar con http:// o https://.")
        if proposed_ean and not self._valid_gtin(proposed_ean):
            raise ValueError("El EAN/GTIN propuesto no supera la validación de dígito verificador.")

        if status in {self.READY_FOR_REVIEW, self.EVIDENCE_ACCEPTED}:
            if not proposed_brand and not proposed_ean:
                raise ValueError("Ingresá al menos una marca o un EAN/GTIN propuesto.")
            if not source_name or not source_url:
                raise ValueError("Para revisar o aceptar evidencia necesitás fuente y URL.")

        if status == self.EVIDENCE_ACCEPTED and confidence not in {"HIGH", "MEDIUM"}:
            raise ValueError("Para aceptar evidencia la confianza debe ser Alta o Media.")

        now = datetime.now(timezone.utc)
        row = (
            self.db.query(EnrichmentExternalResearch)
            .filter(EnrichmentExternalResearch.product_key == product_key)
            .one_or_none()
        )
        if row is None:
            row = EnrichmentExternalResearch(
                product_key=product_key,
                reconciliation_run_id=review_decision.reconciliation_run_id,
                status=status,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)

        row.reconciliation_run_id = review_decision.reconciliation_run_id
        row.status = status
        row.proposed_brand = proposed_brand
        row.proposed_ean = proposed_ean
        row.source_name = source_name
        row.source_url = source_url
        row.confidence = confidence
        row.notes = notes
        row.product_snapshot = dict(item.get("product") or {})
        row.internal_evidence = dict(item.get("internal_evidence") or {})
        row.updated_at = now

        history = list(row.history or [])
        history.append(
            {
                "status": status,
                "at": now.isoformat(),
                "proposed_brand": proposed_brand,
                "proposed_ean": proposed_ean,
                "source_name": source_name,
                "source_url": source_url,
                "confidence": confidence,
                "notes": notes,
            }
        )
        row.history = history[-100:]

        self.db.commit()
        self.db.refresh(row)
        return self._serialize(item, row)

    @classmethod
    def _serialize(cls, item: dict, row: EnrichmentExternalResearch | None) -> dict:
        return {
            "product_key": item["product_key"],
            "product": item.get("product") or {},
            "nature_label": item.get("nature_label"),
            "priority_code": item.get("priority_code"),
            "internal_evidence": item.get("internal_evidence") or {},
            "research_status": row.status if row else cls.DRAFT,
            "proposed_brand": row.proposed_brand if row else None,
            "proposed_ean": row.proposed_ean if row else None,
            "source_name": row.source_name if row else None,
            "source_url": row.source_url if row else None,
            "confidence": row.confidence if row else None,
            "notes": row.notes if row else None,
            "updated_at": row.updated_at.isoformat() if row else None,
            "history_count": len(row.history or []) if row else 0,
        }

    @classmethod
    def _sort_key(cls, item: dict) -> tuple:
        status_rank = {
            cls.READY_FOR_REVIEW: 0,
            cls.DRAFT: 1,
            cls.EVIDENCE_ACCEPTED: 2,
            cls.REJECTED: 3,
        }
        stock = item.get("product", {}).get("stock") or 0
        try:
            stock_value = float(stock)
        except (TypeError, ValueError):
            stock_value = 0
        return (
            status_rank.get(item["research_status"], 99),
            -stock_value,
            str(item.get("product", {}).get("name") or "").casefold(),
        )

    @staticmethod
    def _clean(value: str | None) -> str:
        return str(value or "").strip()

    @classmethod
    def _nullable(cls, value: str | None, max_length: int) -> str | None:
        text = cls._clean(value)
        return text[:max_length] if text else None

    @classmethod
    def _digits_or_none(cls, value: str | None) -> str | None:
        text = cls._clean(value).replace(" ", "").replace("-", "")
        if not text:
            return None
        if not text.isdigit():
            raise ValueError("El EAN/GTIN propuesto debe contener solo números.")
        return text

    @staticmethod
    def _valid_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _valid_gtin(value: str) -> bool:
        if len(value) not in {8, 12, 13, 14} or not value.isdigit():
            return False
        digits = [int(char) for char in value]
        body = digits[:-1]
        check = digits[-1]
        total = 0
        for index, digit in enumerate(reversed(body)):
            total += digit * (3 if index % 2 == 0 else 1)
        expected = (10 - (total % 10)) % 10
        return expected == check
