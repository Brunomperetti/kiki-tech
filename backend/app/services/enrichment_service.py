import re
import unicodedata
from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import Session

from .publication_readiness_service import PublicationReadinessService


class EnrichmentService:
    """Build a controlled research queue for missing EAN/GTIN and brand data.

    The service is intentionally read-only. Product nature is inferred conservatively
    from existing catalog data to choose a research strategy before looking for GTINs.
    No inferred classification is written back to Ecomm-App or Mercado Libre.
    """

    PENDING_RESEARCH = "PENDING_RESEARCH"

    PACK_OR_KIT = "PACK_OR_KIT"
    BULK_OR_FRACTIONED = "BULK_OR_FRACTIONED"
    ARTISANAL = "ARTISANAL"
    STANDARD_UNIT = "STANDARD_UNIT"
    AMBIGUOUS_GENERIC = "AMBIGUOUS_GENERIC"

    NATURES = {
        PACK_OR_KIT: {
            "label": "Pack / kit / combo",
            "strategy": (
                "Investigar los componentes y la presentación comercial. No copiar el EAN "
                "de una unidad como si identificara al pack."
            ),
        },
        BULK_OR_FRACTIONED: {
            "label": "Granel / fraccionado",
            "strategy": (
                "Verificar proveedor y presentación. Evaluar si corresponde informar una "
                "excepción de GTIN según la categoría en lugar de inventar un código."
            ),
        },
        ARTISANAL: {
            "label": "Artesanal / casero",
            "strategy": (
                "Confirmar origen, marca real y condición artesanal. No forzar EAN ni marca "
                "si el producto no los tiene."
            ),
        },
        STANDARD_UNIT: {
            "label": "Unidad envasada",
            "strategy": (
                "Buscar fabricante, marca y GTIN de la presentación exacta usando fuentes "
                "verificables."
            ),
        },
        AMBIGUOUS_GENERIC: {
            "label": "Genérico / ambiguo",
            "strategy": (
                "Pedir etiqueta, proveedor o ficha original antes de proponer marca o GTIN. "
                "La coincidencia por nombre sola no alcanza."
            ),
        },
    }

    PACK_PATTERNS = (
        r"\bPACK\s*X\s*\d+\b",
        r"\bCOMBO\b",
        r"\bKIT\b",
    )
    BULK_WORDS = ("GRANEL", "SUELTA", "SUELTO", "FRACCIONADO", "FRACCIONADA")
    ARTISANAL_WORDS = ("ARTESANAL", "ARTESANALES", "CASERO", "CASERA", "CASEROS", "CASERAS")
    UNIT_WORDS = (
        "CAPSULA",
        "CAPSULAS",
        "COMPRIMIDO",
        "COMPRIMIDOS",
        "BARRITA",
        "ALFAJOR",
        "TOFU",
        "PREPIZZA",
        "FRASCO",
        "BOTELLA",
        "LATA",
        "SOBRE",
        "SOBRES",
        "CAJA",
    )

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
        nature_counts = Counter(item["nature_code"] for item in eligible)

        classification_summary = [
            {
                "code": code,
                "label": config["label"],
                "count": nature_counts[code],
                "strategy": config["strategy"],
            }
            for code, config in cls.NATURES.items()
            if nature_counts[code]
        ]

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
            "classification_summary": classification_summary,
            "policy": {
                "mode": "READ_ONLY_RESEARCH_PILOT",
                "description": (
                    "La clasificación orienta la investigación pero no reemplaza una fuente. "
                    "No modifica Ecomm-App ni Mercado Libre y no acepta datos sin evidencia "
                    "verificable."
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

        nature_code, basis = cls.classify_nature(product)
        nature = cls.NATURES[nature_code]

        return {
            "product": product,
            "readiness_status": item.get("readiness_status"),
            "reason_codes": item.get("reason_codes") or [],
            "missing_fields": missing_fields,
            "research_status": cls.PENDING_RESEARCH,
            "nature_code": nature_code,
            "nature_label": nature["label"],
            "nature_basis": basis,
            "research_strategy": nature["strategy"],
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
    def classify_nature(cls, product: dict) -> tuple[str, str]:
        name = cls._normalize(product.get("name"))

        if any(re.search(pattern, name) for pattern in cls.PACK_PATTERNS):
            return cls.PACK_OR_KIT, "El título indica pack, kit o combo."

        bulk_match = next((word for word in cls.BULK_WORDS if word in name), None)
        if bulk_match:
            return cls.BULK_OR_FRACTIONED, f"El título contiene '{bulk_match.lower()}'."

        artisan_match = next((word for word in cls.ARTISANAL_WORDS if word in name), None)
        if artisan_match:
            return cls.ARTISANAL, f"El título contiene '{artisan_match.lower()}'."

        if product.get("brand") or product.get("ean"):
            return cls.STANDARD_UNIT, "El catálogo ya contiene marca o EAN para la presentación."

        unit_match = next((word for word in cls.UNIT_WORDS if word in name), None)
        if unit_match:
            return cls.STANDARD_UNIT, (
                f"El título contiene una presentación de unidad reconocible: '{unit_match.lower()}'."
            )

        return cls.AMBIGUOUS_GENERIC, (
            "El título no alcanza para distinguir una unidad envasada de un producto genérico "
            "o fraccionado."
        )

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
    def _normalize(value) -> str:
        text = str(value or "").upper().strip()
        return "".join(
            char
            for char in unicodedata.normalize("NFD", text)
            if unicodedata.category(char) != "Mn"
        )

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
