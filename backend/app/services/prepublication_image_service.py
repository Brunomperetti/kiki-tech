from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..database.models import PrepublicationImageReview
from .prepublication_service import PrepublicationService


class PrepublicationImageService:
    """Review candidate image sources without copying or publishing anything."""

    DRAFT = "DRAFT"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    VALID_STATUSES = {DRAFT, READY_FOR_REVIEW, APPROVED, REJECTED}

    OWN_ML = "OWN_ML"
    ML_CATALOG = "ML_CATALOG"
    MANUFACTURER = "MANUFACTURER"
    OTHER_SELLER = "OTHER_SELLER"
    OTHER = "OTHER"
    VALID_SOURCE_TYPES = {OWN_ML, ML_CATALOG, MANUFACTURER, OTHER_SELLER, OTHER}

    VALID_MATCH_BASIS = {"GTIN_EXACT", "OWN_LISTING", "MANUAL_EXACT"}

    SOURCE_LABELS = {
        OWN_ML: "Publicación propia de KIKI",
        ML_CATALOG: "Catálogo de Mercado Libre",
        MANUFACTURER: "Fabricante / marca oficial",
        OTHER_SELLER: "Otro vendedor de Mercado Libre",
        OTHER: "Otra fuente autorizada",
    }

    def __init__(self, db: Session):
        self.db = db
        self.prepublication = PrepublicationService(db)

    def queue(self) -> dict:
        report = self.prepublication.report()
        reviews = {
            row.product_key: row
            for row in self.db.query(PrepublicationImageReview).all()
        }
        items = [
            self._serialize(item, reviews.get(item["product_key"]))
            for item in report.get("items") or []
        ]
        items.sort(key=self._sort_key)

        summary = {status: 0 for status in self.VALID_STATUSES}
        for item in items:
            summary[item["image_status"]] += 1

        return {
            "summary": {
                "total": len(items),
                **summary,
                "approved": summary[self.APPROVED],
                "pending": len(items) - summary[self.APPROVED] - summary[self.REJECTED],
            },
            "mercadolibre_connected": report.get("mercadolibre_connected", False),
            "source_policy": [
                {"code": code, "label": label, "approvable": code != self.OTHER_SELLER}
                for code, label in self.SOURCE_LABELS.items()
            ],
            "policy": {
                "mode": "IMAGE_SOURCE_REVIEW",
                "description": (
                    "KIKI Tech registra y aprueba fuentes de imágenes, pero no copia ni publica "
                    "imágenes automáticamente. Otro vendedor puede servir como referencia, nunca "
                    "como fuente aprobada de uso."
                ),
                "automatic_ml_search": (
                    "PENDING_IMPLEMENTATION" if report.get("mercadolibre_connected") else "WAITING_CONNECTION"
                ),
            },
            "items": items,
        }

    def save(
        self,
        product_key: str,
        status: str,
        source_type: str | None = None,
        source_name: str | None = None,
        source_url: str | None = None,
        image_urls: list[str] | None = None,
        match_basis: str | None = None,
        exact_match: bool = False,
        authorized_for_use: bool = False,
        notes: str | None = None,
    ) -> dict:
        status = self._clean(status).upper()
        if status not in self.VALID_STATUSES:
            raise ValueError("Estado de revisión de imágenes no válido.")

        report_items = {
            item["product_key"]: item
            for item in self.prepublication.report().get("items") or []
        }
        item = report_items.get(product_key)
        if item is None:
            raise ValueError("El producto no está disponible en pre-publicación.")

        source_type = self._nullable(source_type, 30)
        source_type = source_type.upper() if source_type else None
        if source_type and source_type not in self.VALID_SOURCE_TYPES:
            raise ValueError("Tipo de fuente de imagen no válido.")

        source_name = self._nullable(source_name, 255)
        source_url = self._nullable(source_url, 2000)
        match_basis = self._nullable(match_basis, 30)
        match_basis = match_basis.upper() if match_basis else None
        notes = self._nullable(notes, 4000)
        image_urls = self._clean_urls(image_urls or [])

        if source_url and not self._valid_http_url(source_url):
            raise ValueError("La URL de la fuente debe comenzar con http:// o https://.")
        if match_basis and match_basis not in self.VALID_MATCH_BASIS:
            raise ValueError("Criterio de coincidencia de imagen no válido.")

        if status in {self.READY_FOR_REVIEW, self.APPROVED}:
            if not source_type or not source_name or not source_url:
                raise ValueError("Para revisar o aprobar imágenes necesitás tipo, nombre y URL de fuente.")
            if not image_urls:
                raise ValueError("Agregá al menos una URL de imagen candidata.")
            if not match_basis:
                raise ValueError("Indicá cómo verificaste que corresponde a la presentación exacta.")

        if status == self.APPROVED:
            if source_type == self.OTHER_SELLER:
                raise ValueError("Una publicación de otro vendedor no puede aprobarse como fuente de imágenes.")
            if not exact_match:
                raise ValueError("Confirmá que las imágenes corresponden exactamente al producto y presentación.")
            if source_type not in {self.OWN_ML, self.ML_CATALOG} and not authorized_for_use:
                raise ValueError("Confirmá que la fuente autoriza el uso de estas imágenes.")

        now = datetime.now(timezone.utc)
        row = (
            self.db.query(PrepublicationImageReview)
            .filter(PrepublicationImageReview.product_key == product_key)
            .one_or_none()
        )
        if row is None:
            row = PrepublicationImageReview(
                product_key=product_key,
                status=status,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)

        row.status = status
        row.source_type = source_type
        row.source_name = source_name
        row.source_url = source_url
        row.image_urls = image_urls
        row.match_basis = match_basis
        row.exact_match = bool(exact_match)
        row.authorized_for_use = bool(authorized_for_use)
        row.notes = notes
        row.product_snapshot = dict(item.get("product") or {})
        row.updated_at = now

        history = list(row.history or [])
        history.append(
            {
                "status": status,
                "at": now.isoformat(),
                "source_type": source_type,
                "source_name": source_name,
                "source_url": source_url,
                "image_count": len(image_urls),
                "match_basis": match_basis,
                "exact_match": bool(exact_match),
                "authorized_for_use": bool(authorized_for_use),
                "notes": notes,
            }
        )
        row.history = history[-100:]

        self.db.commit()
        self.db.refresh(row)
        return self._serialize(item, row)

    @classmethod
    def _serialize(cls, item: dict, row: PrepublicationImageReview | None) -> dict:
        source_type = row.source_type if row else None
        return {
            "product_key": item["product_key"],
            "product": item.get("product") or {},
            "verified_core_data": item.get("verified_core_data") or {},
            "image_status": row.status if row else cls.DRAFT,
            "source_type": source_type,
            "source_label": cls.SOURCE_LABELS.get(source_type) if source_type else None,
            "source_name": row.source_name if row else None,
            "source_url": row.source_url if row else None,
            "image_urls": list(row.image_urls or []) if row else [],
            "match_basis": row.match_basis if row else None,
            "exact_match": bool(row.exact_match) if row else False,
            "authorized_for_use": bool(row.authorized_for_use) if row else False,
            "notes": row.notes if row else None,
            "updated_at": row.updated_at.isoformat() if row else None,
            "history_count": len(row.history or []) if row else 0,
        }

    @classmethod
    def _sort_key(cls, item: dict) -> tuple:
        rank = {cls.READY_FOR_REVIEW: 0, cls.DRAFT: 1, cls.APPROVED: 2, cls.REJECTED: 3}
        try:
            stock = float(item.get("product", {}).get("stock") or 0)
        except (TypeError, ValueError):
            stock = 0
        return (
            rank.get(item["image_status"], 99),
            -stock,
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
    def _clean_urls(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values[:12]:
            url = cls._clean(value)
            if not url:
                continue
            if not cls._valid_http_url(url):
                raise ValueError("Cada imagen debe tener una URL http:// o https:// válida.")
            if url not in cleaned:
                cleaned.append(url)
        return cleaned

    @staticmethod
    def _valid_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
