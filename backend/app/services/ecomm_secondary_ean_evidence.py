"""Isolated historic EAN evidence for API-identified Ecomm variants.

The historical Ecomm spreadsheet is NEVER a catalog, price or stock source.
It may only provide a *candidate* barcode for a unique API variant, never an
approved product GTIN. Every response explicitly distinguishes provenance.
"""
from collections import Counter, defaultdict

from sqlalchemy import select

from ..database.models import CatalogSnapshot, EcommApiProductEdit
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status
from .ecomm_api_product_workspace_service import _gtin_check_digit_valid


def _str(raw):
    return str(raw).strip() if raw is not None else ""


def _sku(raw):
    return _str(raw).casefold()


def _candidate(raw):
    value = _str(raw)
    if not value or not value.isascii() or not value.isdecimal():
        return ""
    return value if _gtin_check_digit_valid(value) else ""


class EcommLegacyEanEvidence:
    def __init__(self, db):
        self.db = db

    def _load(self):
        api = self.db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == STAGE_SOURCE
        ))
        pages = api.payload if api and isinstance(api.payload, list) else []
        status = stage_status(pages)
        if not status["complete"] or status["quality"]["duplicate_variant_ids"]:
            raise ValueError("El catálogo Ecomm-App API no está completo o tiene IDs duplicados.")

        raw = self.db.scalar(select(CatalogSnapshot).where(
            CatalogSnapshot.source == "ECOMM_APP_RAW"
        ))
        rows = raw.payload if raw and isinstance(raw.payload, list) else []
        by_id = {}
        by_sku = defaultdict(list)
        for page in pages:
            for parent in page.get("items") or []:
                if not isinstance(parent, dict):
                    continue
                variants = parent.get("variants") or []
                valid = [v for v in variants if isinstance(v, dict) and not v.get("invalid")]
                for variant in valid:
                    ident, sku = _str(variant.get("id")), _str(variant.get("sku"))
                    if not ident:
                        continue
                    record = {
                        "ecomm_id": ident, "sku": sku,
                        "name": _str(parent.get("description")),
                        "combo": variant.get("is_combo") is True or parent.get("is_combo") is True,
                        "siblings": len(valid),
                        "api_gtin": _str(variant.get("gtin") or variant.get("barcode")),
                        "captured_at": page.get("captured_at"),
                    }
                    by_id[ident] = record
                    if sku:
                        by_sku[_sku(sku)].append(record)
        legacy_by_sku = defaultdict(list)
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _sku(row.get("sku_effective") or row.get("sku_variant") or row.get("sku"))
            if key:
                legacy_by_sku[key].append(row)
        return by_id, by_sku, legacy_by_sku, raw

    def _evaluate(self, record, api_by_sku, legacy_by_sku, raw):
        base = {
            "ecomm_id": record["ecomm_id"], "sku": record["sku"],
            "api_source": STAGE_SOURCE, "evidence_source": "ECOMM_APP_RAW_XLSX_HISTORICAL",
            "legacy_snapshot_at": raw.updated_at.isoformat() if raw else None,
            "candidate_ean": None, "status": "NO_EVIDENCE", "can_use": False,
            "confidence": "NOT_VERIFIED", "matches": 0, "reason": "",
            "external_writes_enabled": False,
        }
        if record["api_gtin"]:
            return {**base, "status": "API_HAS_GTIN",
                    "reason": "La API ya informa un GTIN para esta variante."}
        if record["combo"]:
            return {**base, "status": "PACK_REVIEW_REQUIRED",
                    "reason": "Los packs o combos no heredan el EAN del producto integrante."}
        key = _sku(record["sku"])
        if not key or len(api_by_sku.get(key, [])) != 1:
            return {**base, "status": "AMBIGUOUS_API_SKU",
                    "reason": "SKU ausente o repetido en variantes API. No asignar EAN."}
        if not raw:
            return {**base, "status": "NO_LEGACY_SOURCE",
                    "reason": "No hay registros históricos con EAN para contrastar."}
        possible = legacy_by_sku.get(key, [])
        if not possible:
            return {**base, "status": "NO_EVIDENCE",
                    "reason": "No se encontró el SKU exacto en las filas históricas."}
        # An inherited product SKU is permitted only for a true single-variant
        # non-pack parent; otherwise require an explicit matching variant SKU.
        eligible = []
        for row in possible:
            variant_sku = _str(row.get("sku_variant"))
            if variant_sku:
                if _sku(variant_sku) != key:
                    continue
            elif record["siblings"] != 1 or _sku(row.get("sku_product")) != key:
                continue
            eligible.append(row)
        if not eligible or len(eligible) != len(possible):
            return {**base, "status": "AMBIGUOUS_LEGACY_SKU",
                    "matches": len(possible),
                    "reason": "El SKU histórico puede pertenecer a un producto o familia diferente."}
        codes = {_str(row.get("ean")) for row in eligible if _str(row.get("ean"))}
        if len(codes) != 1:
            return {**base, "status": "CONFLICTING_OR_MISSING_EAN",
                    "matches": len(eligible),
                    "reason": "El archivo no proporciona un único EAN inequívoco para este SKU."}
        ean = codes.pop()
        if not _candidate(ean):
            return {**base, "status": "INVALID_EAN",
                    "matches": len(eligible),
                    "reason": "El código no cumple el formato o el dígito de control GTIN."}
        # Multiple legacy records can refer to different publications; require
        # a common original product label when they share the same SKU.
        names = {_sku(row.get("name")) for row in eligible if _str(row.get("name"))}
        if len(names) > 1:
            return {**base, "status": "AMBIGUOUS_LEGACY_SKU",
                    "matches": len(eligible),
                    "reason": "El SKU aparece con nombres distintos en el archivo anterior."}
        return {
            **base, "status": "CANDIDATE", "can_use": True,
            "candidate_ean": ean, "matches": len(eligible),
            "reason": (
                "Coincide SKU exacto y único y el GTIN tiene dígito de control válido. "
                "Es evidencia histórica, NO un EAN certificado por API ni fabricante. "
                "Confirmar envase y presentación antes de guardar y publicar."
            ),
        }

    def get(self, ecomm_id: str):
        by_id, by_sku, rows, raw = self._load()
        record = by_id.get(str(ecomm_id))
        if not record:
            raise ValueError("La variante no figura con un ID único en la copia API.")
        result = self._evaluate(record, by_sku, rows, raw)
        edit = self.db.scalar(select(EcommApiProductEdit).where(
            EcommApiProductEdit.ecomm_id == str(ecomm_id)
        ))
        result["kiki_saved_gtin"] = _str((edit.fields or {}).get("proposed_gtin")) if edit else ""
        return result

    def summary(self):
        by_id, by_sku, rows, raw = self._load()
        counts = Counter()
        for record in by_id.values():
            result = self._evaluate(record, by_sku, rows, raw)
            counts[result["status"]] += 1
        return {
            "source": STAGE_SOURCE, "ean_evidence_source": "ECOMM_APP_RAW_XLSX_HISTORICAL",
            "legacy_available": bool(raw), "legacy_snapshot_at": raw.updated_at.isoformat() if raw else None,
            "api_variants": len(by_id),
            "possible_candidates": counts["CANDIDATE"],
            "pack_review_required": counts["PACK_REVIEW_REQUIRED"],
            "ambiguities": sum(counts[k] for k in (
                "AMBIGUOUS_API_SKU", "AMBIGUOUS_LEGACY_SKU",
                "CONFLICTING_OR_MISSING_EAN", "INVALID_EAN"
            )),
            "status_counts": dict(counts),
            "external_writes_enabled": False,
            "policy": (
                "El catálogo sigue siendo API. Los GTIN propuestos son indicios "
                "de un Excel histórico, no valores API ni certificados. Nunca se "
                "asignan a packs, SKU duplicados o discrepantes. Ningún candidato "
                "se guarda ni se publica automáticamente."
            ),
        }
