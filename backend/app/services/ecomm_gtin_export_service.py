"""GTIN evidence from an Ecomm-App inventory XLSX export.

Read-only with respect to Ecomm-App, the API catalog master, edits and channels.
Persists only Ecomm ID, exact SKU and GTIN in a dedicated existing snapshot row.
"""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from sqlalchemy import select

from ..database.models import CatalogSnapshot
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE, stage_status
from .ecomm_api_product_workspace_service import _gtin_check_digit_valid

SOURCE = "ECOMM_APP_GTIN_EXPORT"
MAX_BYTES = 3 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 35 * 1024 * 1024
MAX_VARIANTS = 10000
HEADERS = ("id_interno", "descripcion", "descripcion_variante", "sku_madre", "sku")
GTIN_COLUMN = 13  # N, zero-indexed
SCHEMA_VERSION = 1


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        raise ValueError("El Excel contiene un valor booleano en un identificador.")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("El Excel contiene un identificador con decimales.")
        return str(int(value))
    return str(value).strip()


def _read_xlsx(content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError("El Excel está vacío o supera el límite de 3 MB.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("El Excel supera el límite de contenido permitido.")
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except (BadZipFile, OSError, ValueError, KeyError) as exc:
        raise ValueError("El archivo no es un Excel .xlsx válido o supera los límites.") from exc
    try:
        if "Actualización de productos" not in book.sheetnames:
            raise ValueError("Falta la hoja oficial 'Actualización de productos'.")
        sheet = book["Actualización de productos"]
        rows = sheet.iter_rows(min_row=1, max_col=20, values_only=True)
        headers = next(rows, None)
        if not headers or tuple(headers[:5]) != HEADERS or _as_text(headers[GTIN_COLUMN]).lower() != "gtin":
            raise ValueError("La estructura del Excel Ecomm-App cambió: ID, SKU o GTIN no están en las columnas esperadas.")
        next(rows, None)  # Row 2 is the official explanatory row, never a product.
        items = {}
        for row in rows:
            if not row or all(cell is None for cell in row):
                continue
            if len(items) >= MAX_VARIANTS:
                raise ValueError("El archivo supera el máximo de 10.000 variantes.")
            ecomm_id = _as_text(row[0])
            sku = _as_text(row[4])
            if not ecomm_id.isascii() or not ecomm_id.isdecimal() or int(ecomm_id) < 1 or not sku:
                raise ValueError("El Excel contiene un Ecomm ID o SKU inválido.")
            if ecomm_id in items:
                raise ValueError("Hay Ecomm ID duplicados en el Excel. No se importó nada.")
            gtin = _as_text(row[GTIN_COLUMN])
            if len(gtin) > 32:
                raise ValueError("El Excel contiene un código de barras demasiado largo.")
            items[ecomm_id] = {"ecomm_id": ecomm_id, "sku": sku, "gtin": gtin}
        if not items:
            raise ValueError("El Excel no contiene variantes.")
        return items
    finally:
        book.close()


def _stage_variants(db, *, lock=False):
    query = select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
    if lock:
        query = query.with_for_update()
    stage = db.scalar(query)
    pages = stage.payload if stage and isinstance(stage.payload, list) else []
    status = stage_status(pages)
    if not status["complete"] or status["quality"]["duplicate_variant_ids"]:
        raise ValueError("La captura API no está completa; no se admiten GTIN contra un catálogo parcial.")
    variants = {}
    for page in pages:
        for parent in page.get("items") or []:
            for variant in parent.get("variants") or []:
                if not isinstance(variant, dict) or variant.get("invalid"):
                    continue
                ecomm_id = _as_text(variant.get("id"))
                if not ecomm_id or ecomm_id in variants:
                    raise ValueError("La API tiene variantes sin identidad única.")
                variants[ecomm_id] = {
                    "sku": _as_text(variant.get("sku")),
                    "combo": bool(variant.get("is_combo") is True or parent.get("is_combo") is True),
                    "api_gtin": _as_text(variant.get("gtin") or variant.get("barcode")),
                }
    return variants


def _match_export(items, stage):
    if set(items) != set(stage):
        raise ValueError(
            "El Excel no corresponde a la captura API actual: faltan "
            f"{len(set(stage) - set(items))} IDs y sobran {len(set(items) - set(stage))}. "
            "Volvé a descargar productos de Ecomm-App antes de importarlo."
        )
    wrong = [eid for eid, item in items.items() if item["sku"] != stage[eid]["sku"]]
    if wrong:
        raise ValueError(f"Hay {len(wrong)} SKU que difieren de la API. No se importó nada.")


def _prepare(items, stage):
    codes = Counter(
        item["gtin"] for item in items.values()
        if item["gtin"] and _gtin_check_digit_valid(item["gtin"])
    )
    counts = Counter()
    rows = []
    for eid, item in items.items():
        code = item["gtin"]
        if not code:
            state = "MISSING"
        elif not _gtin_check_digit_valid(code):
            state = "INVALID"
        elif codes[code] > 1:
            state = "VALID_REPEATED"
        elif stage[eid]["combo"]:
            state = "PACK_REVIEW"
        else:
            state = "VALID_UNIQUE"
        counts[state] += 1
        rows.append({**item, "status": state, "is_combo": stage[eid]["combo"]})
    return rows, dict(counts)


class EcommExportGtin:
    def __init__(self, db):
        self.db = db

    def import_file(self, content, filename):
        if not filename.lower().endswith(".xlsx"):
            raise ValueError("Seleccioná el Excel .xlsx exportado desde Ecomm-App.")
        items = _read_xlsx(content)
        stage = _stage_variants(self.db, lock=True)
        _match_export(items, stage)
        rows, counts = _prepare(items, stage)
        now = datetime.now(timezone.utc).isoformat()
        payload = [{
            "version": SCHEMA_VERSION,
            "sha256": sha256(content).hexdigest(),
            "imported_at": now,
            "source_filename": filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:150],
            "variants": len(rows),
            "counts": counts,
            "rows": rows,
        }]
        existing = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == SOURCE).with_for_update()
        )
        if existing:
            existing.payload = payload
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self.db.add(CatalogSnapshot(source=SOURCE, payload=payload))
        self.db.commit()
        return self.summary()

    def _snapshot(self):
        record = self.db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == SOURCE))
        content = record.payload[0] if record and isinstance(record.payload, list) and record.payload else None
        if not isinstance(content, dict) or content.get("version") != SCHEMA_VERSION:
            return None
        return content

    def summary(self):
        snap = self._snapshot()
        if snap is None:
            return {"available": False, "source": SOURCE, "external_writes": False}
        stage = _stage_variants(self.db)
        same = len(stage) == snap.get("variants") and all(
            item["ecomm_id"] in stage and item["sku"] == stage[item["ecomm_id"]]["sku"]
            for item in snap["rows"]
        )
        counts = snap["counts"]
        return {
            "available": True,
            "current": same,
            "source": SOURCE,
            "source_filename": snap["source_filename"],
            "imported_at": snap["imported_at"],
            "sha256": snap["sha256"],
            "variants": snap["variants"],
            "api_variants": len(stage),
            "valid_unique": counts.get("VALID_UNIQUE", 0),
            "valid_repeated": counts.get("VALID_REPEATED", 0),
            "pack_review": counts.get("PACK_REVIEW", 0),
            "invalid": counts.get("INVALID", 0),
            "missing": counts.get("MISSING", 0),
            "external_writes": False,
            "note": "GTIN del Excel descargado, no certificado por API. Repetidos y combos requieren revisión. Ninguna publicación se modificó.",
        }

    def evidence(self, ecomm_id):
        snap = self._snapshot()
        if snap is None:
            return {"available": False, "ecomm_id": ecomm_id}
        summary = self.summary()
        if not summary["current"]:
            return {"available": True, "current": False, "ecomm_id": ecomm_id,
                    "note": "El inventario API cambió desde la importación; la evidencia está suspendida."}
        item = next((r for r in snap["rows"] if r["ecomm_id"] == str(ecomm_id)), None)
        if item is None:
            raise ValueError("El producto no figura en el Excel incorporado.")
        return {
            "available": True,
            "current": True,
            "ecomm_id": str(ecomm_id),
            "gtin": item["gtin"] or None,
            "status": item["status"],
            "is_combo": item["is_combo"],
            "source": SOURCE,
            "imported_at": snap["imported_at"],
            "note": "Evidencia de exportación manual Ecomm-App, no confirmación API ni autorización de publicación.",
        }
