from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy.orm import Session

from ..database.reconciliation_review import ReconciliationReviewDecision
from ..repositories.catalog_repository import CatalogRepository


class ReconciliationReviewService:
    """Persist human decisions for ambiguous reconciliation matches.

    Decisions only affect KIKI Tech's internal interpretation. They never write to
    Ecomm-App or Mercado Libre.
    """

    PENDING = "PENDING"
    CONFIRMED_MATCH = "CONFIRMED_MATCH"
    NOT_MATCH = "NOT_MATCH"
    VALID_DECISIONS = {PENDING, CONFIRMED_MATCH, NOT_MATCH}

    def __init__(self, db: Session):
        self.db = db
        self.repo = CatalogRepository(db)

    def queue(self) -> dict:
        run = self.repo.latest_run()
        if not run:
            raise ValueError("Primero ejecutá una reconciliación para revisar coincidencias.")

        decisions = {
            row.product_key: row
            for row in self.db.query(ReconciliationReviewDecision).all()
        }
        items = []
        for result in run.results or []:
            product = result.get("product") or {}
            if not product or result.get("status") != "REVIEW_REQUIRED":
                continue
            key = self.product_key(product)
            items.append(self._serialize_item(result, decisions.get(key)))

        rank = {self.PENDING: 0, self.CONFIRMED_MATCH: 1, self.NOT_MATCH: 2}
        items.sort(
            key=lambda item: (
                rank.get(item["review_decision"], 99),
                str(item.get("product", {}).get("name") or "").casefold(),
            )
        )
        counts = {decision: 0 for decision in self.VALID_DECISIONS}
        for item in items:
            counts[item["review_decision"]] += 1

        return {
            "reconciliation_run_id": run.id,
            "summary": {
                "total": len(items),
                "PENDING": counts[self.PENDING],
                "CONFIRMED_MATCH": counts[self.CONFIRMED_MATCH],
                "NOT_MATCH": counts[self.NOT_MATCH],
            },
            "policy": {
                "mode": "INTERNAL_RECONCILIATION_REVIEW",
                "description": (
                    "Confirmar o descartar una coincidencia solo guarda una decisión dentro de KIKI Tech. "
                    "No modifica Ecomm-App ni Mercado Libre."
                ),
            },
            "items": items,
        }

    def save_decision(
        self,
        product_key: str,
        decision: str,
        note: str | None = None,
    ) -> dict:
        decision = str(decision or "").upper().strip()
        if decision not in self.VALID_DECISIONS:
            raise ValueError("Decisión de conciliación no válida.")

        run = self.repo.latest_run()
        if not run:
            raise ValueError("Primero ejecutá una reconciliación.")

        result = None
        for candidate in run.results or []:
            product = candidate.get("product") or {}
            if (
                product
                and candidate.get("status") == "REVIEW_REQUIRED"
                and self.product_key(product) == product_key
            ):
                result = candidate
                break
        if result is None:
            raise ValueError("El producto ya no está disponible en la cola de revisión.")

        now = datetime.now(timezone.utc)
        row = (
            self.db.query(ReconciliationReviewDecision)
            .filter(ReconciliationReviewDecision.product_key == product_key)
            .one_or_none()
        )
        if row is None:
            row = ReconciliationReviewDecision(
                product_key=product_key,
                reconciliation_run_id=run.id,
                decision=decision,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)

        clean_note = note.strip()[:2000] if note and note.strip() else None
        product = result.get("product") or {}
        listing = result.get("listing") or {}

        row.reconciliation_run_id = run.id
        row.decision = decision
        row.reason = result.get("reason")
        row.note = clean_note
        row.matched_listing_ids = list(result.get("matched_listing_ids") or [])
        row.product_snapshot = self._slim_product(product)
        row.listing_snapshot = self._slim_listing(listing)
        row.updated_at = now

        history = list(row.history or [])
        history.append(
            {
                "decision": decision,
                "at": now.isoformat(),
                "note": clean_note,
                "reason": result.get("reason"),
                "matched_listing_ids": list(result.get("matched_listing_ids") or []),
            }
        )
        row.history = history[-100:]

        self.db.commit()
        self.db.refresh(row)
        return self._serialize_item(result, row)

    def decision_for_product(self, product: dict) -> ReconciliationReviewDecision | None:
        key = self.product_key(product)
        return (
            self.db.query(ReconciliationReviewDecision)
            .filter(ReconciliationReviewDecision.product_key == key)
            .one_or_none()
        )

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

        name = " ".join(str(product.get("name") or "").casefold().split())
        if name:
            digest = sha256(name.encode("utf-8")).hexdigest()[:24]
            return f"NAME:{digest}"
        raise ValueError("No se pudo construir una identidad estable para el producto.")

    def _serialize_item(
        self,
        result: dict,
        decision: ReconciliationReviewDecision | None,
    ) -> dict:
        product = result.get("product") or {}
        listing = result.get("listing") or {}
        return {
            "product_key": self.product_key(product),
            "product": self._slim_product(product),
            "listing": self._slim_listing(listing),
            "matched_listing_count": result.get("matched_listing_count") or 0,
            "matched_listing_ids": list(result.get("matched_listing_ids") or []),
            "match_method": result.get("match_method"),
            "confidence": result.get("confidence"),
            "reason": result.get("reason"),
            "review_decision": decision.decision if decision else self.PENDING,
            "note": decision.note if decision else None,
            "updated_at": decision.updated_at.isoformat() if decision else None,
            "history": list(decision.history or []) if decision else [],
            "history_count": len(decision.history or []) if decision else 0,
        }

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

    @staticmethod
    def _slim_listing(listing: dict) -> dict:
        fields = (
            "external_id",
            "status",
            "sku",
            "ean",
            "title",
            "price",
            "url",
            "inventory_linked",
        )
        return {field: listing.get(field) for field in fields if listing.get(field) is not None}
