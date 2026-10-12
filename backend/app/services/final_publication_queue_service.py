from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..database.models import (
    PrepublicationFinalApproval,
    PrepublicationImageReview,
    PrepublicationMetadataReview,
)
from .prepublication_service import PrepublicationService


class FinalPublicationQueueService:
    """Final internal gate before any future Mercado Libre write flow."""

    BLOCKED = "BLOCKED"
    READY_FOR_FINAL_REVIEW = "READY_FOR_FINAL_REVIEW"
    APPROVED_FOR_PUBLICATION = "APPROVED_FOR_PUBLICATION"
    STALE_APPROVAL = "STALE_APPROVAL"

    def __init__(self, db: Session):
        self.db = db
        self.prepublication = PrepublicationService(db)

    def queue(self) -> dict:
        report = self.prepublication.report()
        images = {
            row.product_key: row
            for row in self.db.query(PrepublicationImageReview).all()
        }
        metadata = {
            row.product_key: row
            for row in self.db.query(PrepublicationMetadataReview).all()
        }
        approvals = {
            row.product_key: row
            for row in self.db.query(PrepublicationFinalApproval).all()
        }

        items = []
        summary = {
            "total": 0,
            self.BLOCKED: 0,
            self.READY_FOR_FINAL_REVIEW: 0,
            self.APPROVED_FOR_PUBLICATION: 0,
            self.STALE_APPROVAL: 0,
        }

        for base in report.get("items") or []:
            key = base["product_key"]
            image = images.get(key)
            meta = metadata.get(key)
            approval = approvals.get(key)
            snapshot = self._snapshot(base, image, meta)
            all_checks_passed = (
                base.get("checks", {}).get("core_data") == "PASSED"
                and base.get("checks", {}).get("images") == "PASSED"
                and base.get("checks", {}).get("category") == "PASSED"
                and base.get("checks", {}).get("attributes") == "PASSED"
                and base.get("checks", {}).get("preview") == "READY_TO_VALIDATE"
            )

            if not all_checks_passed:
                status = self.BLOCKED
            elif approval and approval.status == "APPROVED":
                status = (
                    self.APPROVED_FOR_PUBLICATION
                    if approval.source_snapshot == snapshot
                    else self.STALE_APPROVAL
                )
            else:
                status = self.READY_FOR_FINAL_REVIEW

            blockers = self._blockers(base)
            preview = self._preview(base, image, meta)
            summary["total"] += 1
            summary[status] += 1
            items.append(
                {
                    "product_key": key,
                    "product": base.get("product") or {},
                    "verified_core_data": base.get("verified_core_data") or {},
                    "checks": base.get("checks") or {},
                    "queue_status": status,
                    "preview": preview,
                    "blockers": blockers,
                    "approved_at": (
                        approval.updated_at.isoformat()
                        if approval and approval.status == "APPROVED"
                        else None
                    ),
                    "approval_note": approval.note if approval else None,
                    "history_count": len(approval.history or []) if approval else 0,
                }
            )

        items.sort(
            key=lambda item: (
                {
                    self.READY_FOR_FINAL_REVIEW: 0,
                    self.STALE_APPROVAL: 1,
                    self.APPROVED_FOR_PUBLICATION: 2,
                    self.BLOCKED: 3,
                }.get(item["queue_status"], 9),
                str(item.get("product", {}).get("name") or "").casefold(),
            )
        )

        return {
            "summary": summary,
            "policy": {
                "mode": "FINAL_QUEUE_READ_ONLY",
                "description": (
                    "Aprobar un producto lo agrega a la cola interna de publicación. "
                    "Todavía no crea ni modifica publicaciones en Mercado Libre."
                ),
                "required_checks": [
                    "Datos centrales",
                    "Imágenes aprobadas",
                    "Categoría Mercado Libre aprobada",
                    "Atributos obligatorios completos",
                    "Preview completo",
                    "Confirmación humana final",
                ],
            },
            "items": items,
        }

    def save_approval(
        self,
        product_key: str,
        action: str,
        note: str | None = None,
    ) -> dict:
        action = str(action or "").strip().upper()
        if action not in {"APPROVE", "REVOKE"}:
            raise ValueError("La acción final debe ser APPROVE o REVOKE.")

        queue = self.queue()
        item = next(
            (
                candidate
                for candidate in queue.get("items") or []
                if candidate.get("product_key") == product_key
            ),
            None,
        )
        if not item:
            raise ValueError("El producto ya no está disponible en pre-publicación.")
        if action == "APPROVE" and item["queue_status"] not in {
            self.READY_FOR_FINAL_REVIEW,
            self.STALE_APPROVAL,
        }:
            raise ValueError(
                "El producto todavía no pasó todos los controles necesarios para aprobarlo."
            )

        report_item = next(
            candidate
            for candidate in self.prepublication.report().get("items") or []
            if candidate["product_key"] == product_key
        )
        image = (
            self.db.query(PrepublicationImageReview)
            .filter(PrepublicationImageReview.product_key == product_key)
            .one_or_none()
        )
        meta = (
            self.db.query(PrepublicationMetadataReview)
            .filter(PrepublicationMetadataReview.product_key == product_key)
            .one_or_none()
        )
        snapshot = self._snapshot(report_item, image, meta)

        now = datetime.now(timezone.utc)
        row = (
            self.db.query(PrepublicationFinalApproval)
            .filter(PrepublicationFinalApproval.product_key == product_key)
            .one_or_none()
        )
        history = list(row.history or []) if row else []
        history.append(
            {
                "at": now.isoformat(),
                "action": action,
                "note": (note or "").strip() or None,
                "source_snapshot": snapshot,
            }
        )
        values = {
            "status": "APPROVED" if action == "APPROVE" else "REVOKED",
            "source_snapshot": snapshot,
            "note": (note or "").strip() or None,
            "history": history[-100:],
            "updated_at": now,
        }
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            row = PrepublicationFinalApproval(
                product_key=product_key,
                created_at=now,
                **values,
            )
            self.db.add(row)

        self.db.commit()
        self.db.refresh(row)

        refreshed = self.queue()
        return next(
            candidate
            for candidate in refreshed["items"]
            if candidate["product_key"] == product_key
        )

    @staticmethod
    def _blockers(base: dict) -> list[str]:
        checks = base.get("checks") or {}
        labels = {
            "core_data": "Datos centrales",
            "images": "Imágenes",
            "category": "Categoría ML",
            "attributes": "Atributos",
            "preview": "Preview",
        }
        expected = {
            "core_data": "PASSED",
            "images": "PASSED",
            "category": "PASSED",
            "attributes": "PASSED",
            "preview": "READY_TO_VALIDATE",
        }
        return [
            labels[key]
            for key, value in expected.items()
            if checks.get(key) != value
        ]

    @staticmethod
    def _snapshot(base: dict, image, meta) -> dict:
        product = base.get("product") or {}
        attributes = []
        if meta:
            attributes = [
                {
                    "id": attribute.get("id"),
                    "value": attribute.get("verified_value"),
                    "required": bool(attribute.get("required")),
                    "conditional_required_now": bool(
                        attribute.get("conditional_required_now")
                    ),
                }
                for attribute in (meta.attributes or [])
            ]
        return {
            "product": {
                "ecomm_id": product.get("ecomm_id"),
                "sku": product.get("sku_effective") or product.get("sku"),
                "name": product.get("name"),
                "brand": (base.get("verified_core_data") or {}).get("brand"),
                "ean": (base.get("verified_core_data") or {}).get("ean"),
                "gtin_exception": bool(
                    (base.get("verified_core_data") or {}).get("gtin_exception")
                ),
                "price": product.get("price"),
                "stock": product.get("stock"),
            },
            "images": list(image.image_urls or []) if image else [],
            "category": {
                "id": meta.category_id if meta else None,
                "name": meta.category_name if meta else None,
            },
            "attributes": attributes,
            "required_missing": list(meta.required_missing or []) if meta else [],
        }

    @staticmethod
    def _preview(base: dict, image, meta) -> dict:
        product = base.get("product") or {}
        verified = base.get("verified_core_data") or {}
        attributes = []
        if meta:
            attributes = [
                {
                    "id": attribute.get("id"),
                    "name": attribute.get("name"),
                    "value": attribute.get("verified_value"),
                }
                for attribute in (meta.attributes or [])
                if attribute.get("verified_value") not in {None, ""}
            ]
        return {
            "title": product.get("name"),
            "sku": product.get("sku_effective") or product.get("sku"),
            "brand": verified.get("brand"),
            "gtin": verified.get("ean"),
            "gtin_exception": bool(verified.get("gtin_exception")),
            "price": product.get("price"),
            "stock": product.get("stock"),
            "category_id": meta.category_id if meta else None,
            "category_name": meta.category_name if meta else None,
            "image_urls": list(image.image_urls or []) if image else [],
            "attributes": attributes,
        }
