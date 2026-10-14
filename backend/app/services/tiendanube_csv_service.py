"""Read-only Tiendanube catalog import and conservative SKU reconciliation."""
import csv
import io
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from ..database.models import ImportJobRecord
from ..repositories.catalog_repository import CatalogRepository


REQUIRED = {"Identificador de URL", "Nombre", "SKU", "Precio", "Stock"}
MAX_ROWS = 100000


def parse_tiendanube_csv(content: bytes) -> list[dict]:
    if not content or len(content) > 20 * 1024 * 1024:
        raise ValueError("El CSV está vacío o supera 20 MB.")
    decoded = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    if decoded is None:
        raise ValueError("Codificación CSV no reconocida.")
    reader = csv.DictReader(io.StringIO(decoded, newline=""), delimiter=";")
    if not REQUIRED.issubset(set(reader.fieldnames or [])):
        raise ValueError("No es una exportación de catálogo Tiendanube válida.")
    records = []
    for index, row in enumerate(reader, start=2):
        if index > MAX_ROWS + 1:
            raise ValueError("El CSV supera el máximo de filas admitido.")
        if None in row:
            raise ValueError(f"Fila {index}: columnas adicionales inesperadas.")
        if not any((v or "").strip() for v in row.values()):
            continue
        def number(value):
            value = (value or "").strip().replace(",", "")
            if not value:
                return None
            try:
                return str(Decimal(value))
            except InvalidOperation:
                return None
        sku = (row.get("SKU") or "").strip()
        # Never truncate or normalize .0 in SKU without independently verifying it.
        records.append({
            "slug": (row.get("Identificador de URL") or "").strip(),
            "name": (row.get("Nombre") or "").strip(),
            "sku": sku,
            "ean_raw": (row.get("Código de barras") or "").strip(),
            "brand": (row.get("Marca") or "").strip(),
            "category": (row.get("Categorías") or "").strip(),
            "price_raw": (row.get("Precio") or "").strip(),
            "price": number(row.get("Precio")),
            "stock": number(row.get("Stock")),
            "description_present": bool((row.get("Descripción") or "").strip()),
            "variant": [
                {"property": row.get(f"Nombre de propiedad {j}") or "",
                 "value": row.get(f"Valor de propiedad {j}") or ""}
                for j in (1, 2, 3) if (row.get(f"Nombre de propiedad {j}") or "").strip()
            ],
        })
    if not records:
        raise ValueError("No se encontraron productos en el CSV.")
    return records


class TiendanubeCsvService:
    def __init__(self, db):
        self.repo = CatalogRepository(db)

    def import_csv(self, filename, content):
        records = parse_tiendanube_csv(content)
        self.repo.save_snapshot("TIENDANUBE", records)
        job = self.repo.add_job(ImportJobRecord(
            source="TIENDANUBE", filename=filename[:255],
            records=len(records), processed=len(records), errors=0,
            status="COMPLETED",
            unknown_columns={"rows_read": len(records), "rows_accepted": len(records),
                             "warnings": ["Importación de solo lectura; no modifica canales externos."]},
            finished_at=datetime.now(timezone.utc),
        ))
        return {"id": job.id, "records": len(records),
                "products": len({r["slug"] for r in records if r["slug"]}),
                "status": "COMPLETED"}

    def report(self):
        tn = self.repo.snapshot("TIENDANUBE")
        ecomm = self.repo.snapshot("ECOMM_APP")
        if not tn:
            return {"available": False, "summary": {}, "items": []}
        sku_index = {}
        for item in ecomm:
            aliases = [item.get(field) for field in ("sku", "sku_effective", "sku_product", "sku_variant")]
            aliases += item.get("sku_aliases") or []
            for alias in aliases:
                if str(alias or "").strip():
                    sku_index.setdefault(str(alias).strip().casefold(), set()).add(
                        str(item.get("ecomm_id") or item.get("sku") or "")
                    )
        tn_counts = Counter(item["sku"].casefold() for item in tn if item["sku"])
        results = []
        for item in tn:
            sku = item["sku"].casefold()
            matched = sku_index.get(sku, set()) if sku else set()
            status = ("SKU_MISSING" if not sku else
                      "SKU_DUPLICATE_TN" if tn_counts[sku] > 1 else
                      "SKU_AMBIGUOUS_ECOMM" if len(matched) > 1 else
                      "MATCHED_SKU" if len(matched) == 1 else
                      "UNMATCHED_SKU")
            results.append({**item, "status": status,
                            "matched_ecomm_id": next(iter(matched)) if len(matched) == 1 else None})
        counts = Counter(item["status"] for item in results)
        return {
            "available": True,
            "summary": {"rows": len(tn), "products": len({r["slug"] for r in tn if r["slug"]}),
                        "ecomm_products": len(ecomm), **dict(counts)},
            "items": results,
            "policy": "Comparación conservadora por SKU exacto; no hace cambios externos. Códigos de barras conservados sin validar.",
        }
