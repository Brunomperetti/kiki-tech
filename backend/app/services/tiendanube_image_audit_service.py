"""Conservative Tiendanube image CSV import and SKU-based evidence review."""
import csv
import io
from collections import Counter, defaultdict
from urllib.parse import urlparse

from ..repositories.catalog_repository import CatalogRepository


COLUMNS = {"store_id", "product_id", "product_name", "image_url", "sku"}


class TiendanubeImageAuditService:
    def __init__(self, db):
        self.repo = CatalogRepository(db)

    def import_csv(self, content: bytes):
        if not content or len(content) > 20 * 1024 * 1024:
            raise ValueError("El CSV está vacío o supera 20 MB.")
        decoded = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                decoded = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("No se pudo leer la codificación del CSV.")
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        if not COLUMNS.issubset(set(reader.fieldnames or [])):
            raise ValueError("CSV de imágenes inválido: faltan las columnas esperadas.")
        data = []
        for i, row in enumerate(reader):
            if i >= 50000:
                raise ValueError("El CSV supera 50.000 imágenes.")
            if None in row:
                raise ValueError("El CSV contiene columnas inesperadas.")
            url = (row.get("image_url") or "").strip()
            parsed = urlparse(url)
            if not url or parsed.scheme != "https" or not parsed.hostname:
                raise ValueError(f"Fila {i + 2}: URL de imagen inválida o no HTTPS.")
            data.append({key: (row.get(key) or "").strip() for key in COLUMNS})
        if not data:
            raise ValueError("No hay imágenes en el CSV.")
        self.repo.save_snapshot("TIENDANUBE_IMAGES", data)
        return {"images": len(data), "product_ids": len({x["product_id"] for x in data}),
                "policy": "Solo importa URLs y evidencias. No descarga ni publica imágenes."}

    def report(self):
        rows = self.repo.snapshot("TIENDANUBE_IMAGES")
        tn = self.repo.snapshot("TIENDANUBE")
        if not rows:
            return {"available": False, "summary": {}, "items": []}
        sku_counts = Counter(str(x.get("sku") or "").strip().casefold() for x in tn if x.get("sku"))
        by_sku = defaultdict(list)
        for item in tn:
            sku = str(item.get("sku") or "").strip().casefold()
            if sku:
                by_sku[sku].append(item)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["product_id"]].append(row)
        results = []
        for product_id, images in grouped.items():
            values = {x["sku"].casefold() for x in images if x["sku"]}
            sku = images[0]["sku"]
            candidates = by_sku.get(sku.casefold(), []) if len(values) == 1 else []
            if len(values) != 1 or not sku:
                status = "REVIEW_SKU"
            elif sku_counts[sku.casefold()] != 1:
                status = "AMBIGUOUS_SKU" if candidates else "UNMATCHED_SKU"
            else:
                status = "MATCHED_SKU"
            results.append({"product_id": product_id, "name": images[0]["product_name"],
                            "sku": sku, "status": status, "image_count": len(images),
                            "image_urls": list(dict.fromkeys(x["image_url"] for x in images)),
                            "tiendanube_slug": candidates[0].get("slug") if status == "MATCHED_SKU" else None})
        counts = Counter(x["status"] for x in results)
        return {"available": True,
                "summary": {"image_rows": len(rows), "image_products": len(results), **dict(counts)},
                "items": results, "policy": "Solo coincidencias SKU exactas y únicas. product_id no se equipara a slug. Sin reparación automática de .0 ni escritura externa."}
