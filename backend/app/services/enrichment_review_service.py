from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy.orm import Session

from ..database.models import EnrichmentReviewDecision
from .enrichment_service import EnrichmentService
from .publication_readiness_service import PublicationReadinessService


class EnrichmentReviewService:
    """Persist human decisions about internal enrichment evidence.

    This workflow only changes KIKI Tech's own database. It never writes to Ecomm-App
    or Mercado Libre and an approved proposal is not treated as verified source data.
    """

    PENDING = "PENDING"
    APPROVED_PROPOSAL = "APPROVED_PROPOSAL"
    REJECTED = "REJECTED"
    EXTERNAL_RESEARCH = "EXTERNAL_RESEARCH"

    VALID_STATUSES = {
        PENDING,
        APPROVED_PROPOSAL,
        REJECTED,
        EXTERNAL_RESEARCH,
    }

    PRIORITY_LABELS = {
        "P1_HIGH": "Prioridad 1 · evidencia alta",
        "P2_MEDIUM": "Prioridad 2 · evidencia media",
        "P3_AMBIGUOUS": "Prioridad 3 · evidencia ambigua",
        "P4_EXTERNAL": "Prioridad 4 · sin evidencia interna",
    }

    def __init__(self, db: Session):
        self.db = db
        self.readiness = PublicationReadinessService(db)

    def queue(self) -> dict:
        readiness_report = self.readiness.report()
        eligible = self._eligible_items(readiness_report)
        decisions = {
            row.product_key: row
            for row in self.db.query(EnrichmentReviewDecision).all()
        }

        queue_items = []
        candidate_count = 0
        ambiguous_count = 0
        no_evidence_count = 0

        for item in eligible:
            evidence = item["internal_evidence"]
            has_candidate = bool(evidence.get("brand_candidate"))
            is_ambiguous = (
                not has_candidate
                and len(evidence.get("candidate_brands") or []) > 1
            )
            if has_candidate:
                candidate_count += 1
            elif is_ambiguous:
                ambiguous_count += 1
            else:
                no_evidence_count += 1

            decision = decisions.get(item["product_key"])
            # MVP3.5 focuses the human queue on cases where KIKI already has some
            # internal signal. Previously reviewed cases remain visible even if a
            # later catalog snapshot changes the signal.
            if not has_candidate and not is_ambiguous and decision is None:
                continue

            queue_items.append(self._serialize_queue_item(item, decision))

        status_counts = {status: 0 for status in self.VALID_STATUSES}
        priority_counts = {code: 0 for code in self.PRIORITY_LABELS}
        for item in queue_items:
            status_counts[item["review_status"]] += 1
            priority_counts[item["priority_code"]] += 1

        queue_items.sort(key=self._queue_sort_key)

        return {
            "reconciliation_run_id": readiness_report.get("reconciliation_run_id"),
            "summary": {
                "total_eligible": len(eligible),
                "queue_total": len(queue_items),
                "internal_brand_candidates": candidate_count,
                "internal_ambiguous": ambiguous_count,
                "without_internal_evidence": no_evidence_count,
                "PENDING": status_counts[self.PENDING],
                "APPROVED_PROPOSAL": status_counts[self.APPROVED_PROPOSAL],
                "REJECTED": status_counts[self.REJECTED],
                "EXTERNAL_RESEARCH": status_counts[self.EXTERNAL_RESEARCH],
            },
            "priority_summary": [
                {
                    "code": code,
                    "label": label,
                    "count": priority_counts[code],
                }
                for code, label in self.PRIORITY_LABELS.items()
                if priority_counts[code]
            ],
            "policy": {
                "mode": "INTERNAL_REVIEW_ONLY",
                "description": (
                    "Aprobar una propuesta solo guarda una decisión interna en KIKI Tech. "
                    "No actualiza Ecomm-App ni Mercado Libre y no convierte la evidencia "
                    "interna en una fuente verificada."
                ),
            },
            "items": queue_items,
        }

    def save_decision(self, product_key: str, status: str, note: str | None = None) -> dict:
        status = str(status or "").upper().strip()
        if status not in self.VALID_STATUSES:
            raise ValueError("Estado de revisión no válido.")

        readiness_report = self.readiness.report()
        current_items = {
            item["product_key"]: item
            for item in self._eligible_items(readiness_report)
        }
        item = current_items.get(product_key)
        if item is None:
            raise ValueError("El producto ya no está disponible en la cola de enriquecimiento.")

        evidence = item["internal_evidence"]
        has_candidate = bool(evidence.get("brand_candidate"))
        is_ambiguous = (
            not has_candidate
            and len(evidence.get("candidate_brands") or []) > 1
        )
        if not has_candidate and not is_ambiguous:
            raise ValueError(
                "Este producto todavía no tiene evidencia interna suficiente para esta cola."
            )
        if status == self.APPROVED_PROPOSAL and not has_candidate:
            raise ValueError("No hay una marca candidata única para aprobar como propuesta.")

        now = datetime.now(timezone.utc)
        row = (
            self.db.query(EnrichmentReviewDecision)
            .filter(EnrichmentReviewDecision.product_key == product_key)
            .one_or_none()
        )
        if row is None:
            row = EnrichmentReviewDecision(
                product_key=product_key,
                reconciliation_run_id=readiness_report.get("reconciliation_run_id"),
                status=status,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)

        row.reconciliation_run_id = readiness_report.get("reconciliation_run_id")
        row.status = status
        row.proposed_brand = (
            evidence.get("brand_candidate")
            if status == self.APPROVED_PROPOSAL
            else None
        )
        row.proposed_ean = None
        row.evidence = dict(evidence)
        row.product_snapshot = self._slim_product(item.get("product") or {})
        row.note = note.strip()[:2000] if note and note.strip() else None
        row.updated_at = now

        history = list(row.history or [])
        history.append(
            {
                "status": status,
                "at": now.isoformat(),
                "note": row.note,
                "brand_candidate": evidence.get("brand_candidate"),
                "confidence": evidence.get("confidence"),
            }
        )
        row.history = history[-100:]

        self.db.commit()
        self.db.refresh(row)
        return self._serialize_queue_item(item, row)

    def _eligible_items(self, readiness_report: dict) -> list[dict]:
        raw_items = readiness_report.get("items") or []
        evidence_index = EnrichmentService._build_internal_evidence_index(raw_items)
        eligible = []
        for raw_item in raw_items:
            item = EnrichmentService._to_enrichment_item(raw_item, evidence_index)
            if not item:
                continue
            item["product_key"] = self.product_key(item.get("product") or {})
            eligible.append(item)
        return eligible

    @classmethod
    def product_key(cls, product: dict) -> str:
        ecomm_id = str(product.get("ecomm_id") or "").strip()
        if ecomm_id:
            return f"ECOMM:{ecomm_id}"

        for field in ("sku_variant", "sku_effective", "sku"):
            value = str(product.get(field) or "").strip()
            if value:
                return f"SKU:{value}"

        ean = str(product.get("ean") or "").strip()
        if ean:
            return f"EAN:{ean}"

        normalized_name = EnrichmentService._normalize(product.get("name"))
        if normalized_name:
            digest = sha256(normalized_name.encode("utf-8")).hexdigest()[:24]
            return f"NAME:{digest}"
        raise ValueError("No se pudo construir una identidad estable para el producto.")

    def _serialize_queue_item(
        self,
        item: dict,
        decision: EnrichmentReviewDecision | None,
    ) -> dict:
        evidence = item["internal_evidence"]
        priority_code = self._priority_code(evidence)
        status = decision.status if decision else self.PENDING
        return {
            "product_key": item["product_key"],
            "product": self._slim_product(item.get("product") or {}),
            "missing_fields": item.get("missing_fields") or [],
            "nature_code": item.get("nature_code"),
            "nature_label": item.get("nature_label"),
            "internal_evidence": evidence,
            "priority_code": priority_code,
            "priority_label": self.PRIORITY_LABELS[priority_code],
            "review_status": status,
            "proposed_brand": decision.proposed_brand if decision else None,
            "proposed_ean": decision.proposed_ean if decision else None,
            "note": decision.note if decision else None,
            "updated_at": decision.updated_at.isoformat() if decision else None,
            "history_count": len(decision.history or []) if decision else 0,
        }

    @classmethod
    def _priority_code(cls, evidence: dict) -> str:
        if evidence.get("brand_candidate") and evidence.get("confidence") == "HIGH":
            return "P1_HIGH"
        if evidence.get("brand_candidate"):
            return "P2_MEDIUM"
        if len(evidence.get("candidate_brands") or []) > 1:
            return "P3_AMBIGUOUS"
        return "P4_EXTERNAL"

    @classmethod
    def _queue_sort_key(cls, item: dict) -> tuple:
        status_rank = {
            cls.PENDING: 0,
            cls.EXTERNAL_RESEARCH: 1,
            cls.APPROVED_PROPOSAL: 2,
            cls.REJECTED: 3,
        }
        priority_rank = {
            "P1_HIGH": 0,
            "P2_MEDIUM": 1,
            "P3_AMBIGUOUS": 2,
            "P4_EXTERNAL": 3,
        }
        stock = item.get("product", {}).get("stock") or 0
        try:
            stock_value = float(stock)
        except (TypeError, ValueError):
            stock_value = 0
        return (
            status_rank.get(item["review_status"], 99),
            priority_rank.get(item["priority_code"], 99),
            -stock_value,
            str(item.get("product", {}).get("name") or "").casefold(),
        )

    @staticmethod
    def _slim_product(product: dict) -> dict:
        fields = (
            "ecomm_id",
            "sku",
            "sku_product",
            "sku_variant",
            "sku_effective",
            "ean",
            "brand",
            "name",
            "stock",
            "price",
        )
        return {field: product.get(field) for field in fields}
