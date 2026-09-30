import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from .publication_readiness_service import PublicationReadinessService


class EnrichmentService:
    """Build a controlled research queue for missing EAN/GTIN and brand data.

    The service is intentionally read-only. Product nature is inferred conservatively
    and internal catalog evidence is used only to suggest where to research next.
    Nothing inferred here is written back to Ecomm-App or Mercado Libre.
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
    TOKEN_STOPWORDS = {
        "DE",
        "DEL",
        "LA",
        "LAS",
        "EL",
        "LOS",
        "Y",
        "CON",
        "SIN",
        "PARA",
        "POR",
        "EN",
        "UNA",
        "UNO",
        "UN",
        "PACK",
        "COMBO",
        "KIT",
        "GRS",
        "GR",
        "GRAMOS",
        "KG",
        "KGS",
        "ML",
        "CC",
        "CM",
        "UNIDAD",
        "UNIDADES",
    }

    def __init__(self, db: Session):
        self.readiness = PublicationReadinessService(db)

    def report(self, limit: int = 20) -> dict:
        readiness_report = self.readiness.report()
        return self.build_report(readiness_report, limit)

    @classmethod
    def build_report(cls, readiness_report: dict, limit: int = 20) -> dict:
        if limit < 1 or limit > 100:
            raise ValueError("El límite del piloto debe estar entre 1 y 100 productos.")

        raw_items = readiness_report.get("items") or []
        evidence_index = cls._build_internal_evidence_index(raw_items)

        eligible = []
        for item in raw_items:
            enrichment_item = cls._to_enrichment_item(item, evidence_index)
            if enrichment_item:
                eligible.append(enrichment_item)

        eligible.sort(key=cls._priority_key)
        pilot = eligible[:limit]

        missing_ean = sum("EAN/GTIN" in item["missing_fields"] for item in eligible)
        missing_brand = sum("Marca" in item["missing_fields"] for item in eligible)
        missing_both = sum(len(item["missing_fields"]) == 2 for item in eligible)
        nature_counts = Counter(item["nature_code"] for item in eligible)
        evidence_counts = Counter(item["internal_evidence"]["confidence"] for item in eligible)
        internal_brand_candidates = sum(
            bool(item["internal_evidence"].get("brand_candidate")) for item in eligible
        )
        ambiguous_internal_evidence = sum(
            not item["internal_evidence"].get("brand_candidate")
            and len(item["internal_evidence"].get("candidate_brands") or []) > 1
            for item in eligible
        )

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
                "internal_brand_candidates": internal_brand_candidates,
                "internal_evidence_ambiguous": ambiguous_internal_evidence,
                "known_brands_in_catalog": evidence_index["brand_count"],
            },
            "classification_summary": classification_summary,
            "internal_evidence_summary": {
                "high": evidence_counts["HIGH"],
                "medium": evidence_counts["MEDIUM"],
                "none": evidence_counts["NONE"],
                "description": (
                    "La evidencia interna se calcula comparando el producto con marcas y "
                    "productos ya identificados dentro del mismo catálogo. Es una pista para "
                    "investigar, no un dato aprobado."
                ),
            },
            "policy": {
                "mode": "READ_ONLY_RESEARCH_PILOT",
                "description": (
                    "La clasificación y la evidencia interna orientan la investigación pero "
                    "no reemplazan una fuente externa verificable. No modifica Ecomm-App ni "
                    "Mercado Libre y no aprueba datos automáticamente."
                ),
            },
            "items": pilot,
        }

    @classmethod
    def _to_enrichment_item(cls, item: dict, evidence_index: dict | None = None) -> dict | None:
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
        internal_evidence = cls._find_internal_evidence(product, evidence_index or cls._empty_evidence())

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
            "internal_evidence": internal_evidence,
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
    def _build_internal_evidence_index(cls, items: list[dict]) -> dict:
        brand_spellings = defaultdict(Counter)
        references = []

        for item in items:
            product = item.get("product") or {}
            brand = str(product.get("brand") or "").strip()
            name = str(product.get("name") or "").strip()
            if not brand or not name:
                continue

            normalized_brand = cls._normalize(brand)
            if len(normalized_brand) < 4:
                continue

            brand_spellings[normalized_brand][brand] += 1
            tokens = cls._informative_tokens(name)
            if len(tokens) >= 2:
                references.append(
                    {
                        "sku": str(product.get("sku") or ""),
                        "name": name,
                        "brand": brand,
                        "ean": product.get("ean"),
                        "tokens": tokens,
                    }
                )

        brands = {
            normalized: counts.most_common(1)[0][0]
            for normalized, counts in brand_spellings.items()
        }
        return {
            "brands": brands,
            "references": references,
            "brand_count": len(brands),
        }

    @classmethod
    def _find_internal_evidence(cls, product: dict, evidence_index: dict) -> dict:
        name = cls._normalize(product.get("name"))
        sku = str(product.get("sku") or "")
        brands = evidence_index.get("brands") or {}

        direct = []
        for normalized_brand, display_brand in brands.items():
            pattern = rf"(?<![A-Z0-9]){re.escape(normalized_brand)}(?![A-Z0-9])"
            if re.search(pattern, name):
                direct.append(display_brand)

        direct = sorted(set(direct), key=lambda value: (-len(value), value.casefold()))
        if len(direct) == 1:
            return {
                "brand_candidate": direct[0],
                "candidate_brands": direct,
                "confidence": "HIGH",
                "method": "BRAND_IN_TITLE",
                "reason": (
                    f"La marca '{direct[0]}' ya existe en el catálogo y aparece literalmente "
                    "en el título de este producto."
                ),
                "related_sku": None,
                "related_name": None,
                "related_ean": None,
                "similarity": None,
            }
        if len(direct) > 1:
            return {
                "brand_candidate": None,
                "candidate_brands": direct[:3],
                "confidence": "NONE",
                "method": "MULTIPLE_BRANDS_IN_TITLE",
                "reason": (
                    "El título coincide con más de una marca conocida del catálogo; no se "
                    "elige una automáticamente."
                ),
                "related_sku": None,
                "related_name": None,
                "related_ean": None,
                "similarity": None,
            }

        target_tokens = cls._informative_tokens(product.get("name"))
        if len(target_tokens) < 2:
            return cls._empty_internal_evidence_result()

        best_by_brand = {}
        for ref in evidence_index.get("references") or []:
            if sku and ref["sku"] == sku:
                continue

            ref_tokens = ref["tokens"]
            intersection = target_tokens & ref_tokens
            if len(intersection) < 2:
                continue

            union = target_tokens | ref_tokens
            jaccard = len(intersection) / len(union) if union else 0
            coverage = len(intersection) / len(target_tokens)
            score = (jaccard * 0.6) + (coverage * 0.4)
            if score < 0.72:
                continue

            current = best_by_brand.get(ref["brand"])
            if current is None or score > current["score"]:
                best_by_brand[ref["brand"]] = {"score": score, "ref": ref}

        ranked = sorted(
            best_by_brand.items(),
            key=lambda entry: (-entry[1]["score"], entry[0].casefold()),
        )
        if not ranked:
            return cls._empty_internal_evidence_result()

        top_brand, top = ranked[0]
        runner_up_score = ranked[1][1]["score"] if len(ranked) > 1 else 0
        lead = top["score"] - runner_up_score
        candidate_brands = [entry[0] for entry in ranked[:3]]

        if len(ranked) > 1 and lead < 0.12:
            return {
                "brand_candidate": None,
                "candidate_brands": candidate_brands,
                "confidence": "NONE",
                "method": "SIMILAR_PRODUCTS_AMBIGUOUS",
                "reason": (
                    "Hay productos internos similares asociados a más de una marca y la "
                    "diferencia no alcanza para sugerir una sola."
                ),
                "related_sku": top["ref"]["sku"] or None,
                "related_name": top["ref"]["name"],
                "related_ean": top["ref"]["ean"],
                "similarity": round(top["score"], 3),
            }

        confidence = "HIGH" if top["score"] >= 0.9 else "MEDIUM"
        return {
            "brand_candidate": top_brand,
            "candidate_brands": candidate_brands,
            "confidence": confidence,
            "method": "SIMILAR_INTERNAL_PRODUCT",
            "reason": (
                f"Un producto ya identificado en el catálogo tiene una descripción muy similar "
                f"y está asociado a la marca '{top_brand}'. Validar antes de aprobar."
            ),
            "related_sku": top["ref"]["sku"] or None,
            "related_name": top["ref"]["name"],
            "related_ean": top["ref"]["ean"],
            "similarity": round(top["score"], 3),
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

    @classmethod
    def _informative_tokens(cls, value) -> set[str]:
        text = cls._normalize(value)
        tokens = set()
        for token in re.findall(r"[A-Z0-9]+", text):
            if token.isdigit() or len(token) < 3 or token in cls.TOKEN_STOPWORDS:
                continue
            tokens.add(token)
        return tokens

    @staticmethod
    def _empty_evidence() -> dict:
        return {"brands": {}, "references": [], "brand_count": 0}

    @staticmethod
    def _empty_internal_evidence_result() -> dict:
        return {
            "brand_candidate": None,
            "candidate_brands": [],
            "confidence": "NONE",
            "method": "NO_MATCH",
            "reason": "No se encontró evidencia interna suficientemente fuerte.",
            "related_sku": None,
            "related_name": None,
            "related_ean": None,
            "similarity": None,
        }

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
