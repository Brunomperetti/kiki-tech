from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy.orm import Session

from ..database.duplicate_review import DuplicateReviewDecision
from ..repositories.catalog_repository import CatalogRepository
from .reconciliation_review_service import ReconciliationReviewService


class DuplicateReviewService:
    """Persist human decisions about possible duplicate Ecomm products.

    Decisions only affect KIKI Tech's internal interpretation. They never write to
    Ecomm-App or Mercado Libre.
    """

    PENDING = "PENDING"
    DUPLICATE_CONFIRMED = "DUPLICATE_CONFIRMED"
    DISTINCT_PRODUCTS = "DISTINCT_PRODUCTS"
    VARIANTS = "VARIANTS"
    VALID_DECISIONS = {
        PENDING,
        DUPLICATE_CONFIRMED,
        DISTINCT_PRODUCTS,
        VARIANTS,
    }

    def __init__(self, db: Session):
        self.db = db
        self.repo = CatalogRepository(db)

    def queue(self) -> dict:
        run = self.repo.latest_run()
        if not run:
            raise ValueError("Primero ejecutá una reconciliación para revisar duplicados.")

        groups = self._groups(run.results or [])
        decisions = {
            row.group_key: row for row in self.db.query(DuplicateReviewDecision).all()
        }
        items = [
            self._serialize_group(group, decisions.get(group["group_key"]))
            for group in groups
        ]
        rank = {
            self.PENDING: 0,
            self.DUPLICATE_CONFIRMED: 1,
            self.DISTINCT_PRODUCTS: 2,
            self.VARIANTS: 3,
        }
        items.sort(
            key=lambda item: (
                rank.get(item["review_decision"], 99),
                item["shared_identifiers"],
            )
        )
        counts = {decision: 0 for decision in self.VALID_DECISIONS}
        for item in items:
            counts[item["review_decision"]] += 1

        return {
            "reconciliation_run_id": run.id,
            "summary": {
                "groups_total": len(items),
                "products_affected": sum(len(item["products"]) for item in items),
                "PENDING": counts[self.PENDING],
                "DUPLICATE_CONFIRMED": counts[self.DUPLICATE_CONFIRMED],
                "DISTINCT_PRODUCTS": counts[self.DISTINCT_PRODUCTS],
                "VARIANTS": counts[self.VARIANTS],
            },
            "policy": {
                "mode": "INTERNAL_DUPLICATE_REVIEW",
                "description": (
                    "La decisión solo se guarda dentro de KIKI Tech. No modifica Ecomm-App "
                    "ni Mercado Libre. Un duplicado confirmado permanece bloqueado hasta que "
                    "el catálogo de origen se corrija; productos distintos o variantes dejan de "
                    "bloquearse por este conflicto."
                ),
            },
            "items": items,
        }

    def save_decision(
        self,
        group_key: str,
        decision: str,
        note: str | None = None,
    ) -> dict:
        decision = str(decision or "").upper().strip()
        if decision not in self.VALID_DECISIONS:
            raise ValueError("Decisión de duplicado no válida.")

        run = self.repo.latest_run()
        if not run:
            raise ValueError("Primero ejecutá una reconciliación.")
        current = {group["group_key"]: group for group in self._groups(run.results or [])}
        group = current.get(group_key)
        if group is None:
            raise ValueError("El grupo ya no está disponible en la revisión de duplicados.")

        now = datetime.now(timezone.utc)
        row = (
            self.db.query(DuplicateReviewDecision)
            .filter(DuplicateReviewDecision.group_key == group_key)
            .one_or_none()
        )
        if row is None:
            row = DuplicateReviewDecision(
                group_key=group_key,
                reconciliation_run_id=run.id,
                decision=decision,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)

        clean_note = note.strip()[:2000] if note and note.strip() else None
        row.reconciliation_run_id = run.id
        row.decision = decision
        row.note = clean_note
        row.shared_identifiers = list(group["shared_identifiers"])
        row.product_keys = list(group["product_keys"])
        row.group_snapshot = [self._snapshot_result(item) for item in group["results"]]
        row.updated_at = now
        history = list(row.history or [])
        history.append(
            {
                "decision": decision,
                "at": now.isoformat(),
                "note": clean_note,
                "shared_identifiers": list(group["shared_identifiers"]),
                "product_keys": list(group["product_keys"]),
            }
        )
        row.history = history[-100:]

        self.db.commit()
        self.db.refresh(row)
        return self._serialize_group(group, row)

    @classmethod
    def product_decision_index(
        cls,
        rows: list[DuplicateReviewDecision],
    ) -> dict[str, DuplicateReviewDecision]:
        index: dict[str, DuplicateReviewDecision] = {}
        for row in rows:
            if row.decision == cls.PENDING:
                continue
            for product_key in row.product_keys or []:
                index[str(product_key)] = row
        return index

    @classmethod
    def reclassify_resolved_duplicate(cls, result: dict) -> dict:
        """Remove only the duplicate conflict and recover the underlying reconciliation state."""
        updated = dict(result)
        remaining_issues = [
            issue
            for issue in result.get("issues") or []
            if issue.get("code") != "SKU_DUPLICATE"
        ]
        updated["issues"] = remaining_issues
        codes = {issue.get("code") for issue in remaining_issues}

        if "SKU_MISSING" in codes or "SKU_INVALID" in codes:
            updated["status"] = "INVALID_SKU"
            updated["reason"] = "El SKU está ausente o tiene formato inválido."
            return updated
        if "EAN_INVALID" in codes:
            updated["status"] = "INVALID_EAN"
            updated["reason"] = "El EAN/GTIN tiene formato inválido."
            return updated
        if codes.intersection({"NAME_MISSING", "PRICE_INVALID", "STOCK_INVALID"}):
            updated["status"] = "INCOMPLETE_DATA"
            updated["reason"] = "Faltan datos obligatorios o contienen valores inválidos."
            return updated
        if str(result.get("match_method") or "").upper() == "TITLE":
            updated["status"] = "REVIEW_REQUIRED"
            updated["reason"] = "Coincidencia aproximada por título; requiere confirmación humana."
            return updated
        if int(result.get("matched_listing_count") or 0) > 0:
            updated["status"] = "ALREADY_PUBLISHED"
            updated["reason"] = "Conflicto de duplicado resuelto; conserva su coincidencia con Mercado Libre."
            return updated
        updated["status"] = "CANDIDATE_TO_PUBLISH"
        updated["reason"] = "Conflicto de duplicado resuelto; no se encontró publicación asociada."
        return updated

    @classmethod
    def product_key(cls, product: dict) -> str:
        return ReconciliationReviewService.product_key(product)

    @classmethod
    def _groups(cls, results: list[dict]) -> list[dict]:
        candidates = [
            result
            for result in results
            if result.get("product") and result.get("status") == "POSSIBLE_DUPLICATE"
        ]
        if not candidates:
            return []

        product_keys = [cls.product_key(result.get("product") or {}) for result in candidates]
        aliases_by_index: list[set[str]] = []
        alias_to_indexes: dict[str, list[int]] = defaultdict(list)
        for index, result in enumerate(candidates):
            product = result.get("product") or {}
            aliases = {
                str(value).strip()
                for value in (product.get("sku_aliases") or [])
                if str(value).strip()
            }
            if not aliases:
                for field in ("sku_variant", "sku_effective", "sku"):
                    value = str(product.get(field) or "").strip()
                    if value:
                        aliases.add(value)
            aliases_by_index.append(aliases)
            for alias in aliases:
                alias_to_indexes[alias].append(index)

        parent = list(range(len(candidates)))

        def find(value: int) -> int:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for indexes in alias_to_indexes.values():
            unique = sorted(set(indexes))
            if len(unique) < 2:
                continue
            first = unique[0]
            for other in unique[1:]:
                union(first, other)

        components: dict[int, list[int]] = defaultdict(list)
        for index in range(len(candidates)):
            components[find(index)].append(index)

        groups = []
        for indexes in components.values():
            if len(indexes) < 2:
                continue
            member_keys = sorted({product_keys[index] for index in indexes})
            shared = sorted(
                alias
                for alias, alias_indexes in alias_to_indexes.items()
                if len(set(alias_indexes).intersection(indexes)) >= 2
            )
            digest = sha256("|".join(member_keys).encode("utf-8")).hexdigest()[:24]
            groups.append(
                {
                    "group_key": f"DUP:{digest}",
                    "product_keys": member_keys,
                    "shared_identifiers": shared,
                    "results": [candidates[index] for index in indexes],
                }
            )
        return groups

    def _serialize_group(
        self,
        group: dict,
        decision: DuplicateReviewDecision | None,
    ) -> dict:
        return {
            "group_key": group["group_key"],
            "shared_identifiers": list(group["shared_identifiers"]),
            "product_keys": list(group["product_keys"]),
            "products": [self._serialize_result(item) for item in group["results"]],
            "review_decision": decision.decision if decision else self.PENDING,
            "note": decision.note if decision else None,
            "updated_at": decision.updated_at.isoformat() if decision else None,
            "history": list(decision.history or []) if decision else [],
            "history_count": len(decision.history or []) if decision else 0,
        }

    @classmethod
    def _serialize_result(cls, result: dict) -> dict:
        return {
            "product_key": cls.product_key(result.get("product") or {}),
            "product": cls._slim_product(result.get("product") or {}),
            "listing": cls._slim_listing(result.get("listing") or {}),
            "matched_listing_count": result.get("matched_listing_count") or 0,
            "matched_listing_ids": list(result.get("matched_listing_ids") or []),
            "match_method": result.get("match_method"),
            "reason": result.get("reason"),
        }

    @classmethod
    def _snapshot_result(cls, result: dict) -> dict:
        return cls._serialize_result(result)

    @staticmethod
    def _slim_product(product: dict) -> dict:
        fields = (
            "ecomm_id",
            "sku",
            "sku_product",
            "sku_variant",
            "sku_effective",
            "sku_aliases",
            "ean",
            "ean_aliases",
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
        return {field: listing.get(field) for field in fields}
