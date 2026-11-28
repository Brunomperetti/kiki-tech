"""Manual read-only catalog capture. CSV and legacy approvals are not replaced.

A consistent reported total and unique IDs are necessary, not proof of an
atomic remote snapshot. Never use this report to authorize an external write.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from time import monotonic

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import CatalogSnapshot
from app.integrations.tiendanube.client import TiendanubeClient
from app.services.editorial_batches.context import sources
from app.services.tiendanube_publication_preview import normalized_sku

SOURCE = "TIENDANUBE_API"
PAGE_SIZE = 100
MAX_PAGES = 100
MAX_VARIANTS = 50000


def _positive_id(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Identificador remoto inválido.")
    return value


def _text(value):
    return value.strip()[:500] if isinstance(value, str) else ""


def read_catalog(client, *, deadline_seconds=45):
    started = monotonic()
    seen_products, seen_variants, rows = set(), set(), []
    expected = None
    for page in range(1, MAX_PAGES + 1):
        if monotonic() - started >= deadline_seconds:
            raise ValueError("Tiempo de captura agotado; se conserva la captura anterior.")
        products, total = client.catalog_page(page)
        if monotonic() - started >= deadline_seconds:
            raise ValueError("Tiempo de captura agotado; se conserva la captura anterior.")
        if type(total) is not int or not 0 <= total <= PAGE_SIZE * MAX_PAGES:
            raise ValueError("Total remoto fuera del límite de captura.")
        if expected is None:
            expected = total
        remaining = expected - len(seen_products)
        if total != expected or len(products) != min(PAGE_SIZE, remaining):
            raise ValueError("El catálogo cambió o la página está incompleta.")
        for product in products:
            if not isinstance(product, dict):
                raise ValueError("Producto remoto inválido.")
            pid = _positive_id(product.get("id"))
            if pid in seen_products:
                raise ValueError("Producto repetido entre páginas.")
            seen_products.add(pid)
            name = product.get("name")
            name = _text(name.get("es")) if isinstance(name, dict) else _text(name)
            variants = product.get("variants")
            if not isinstance(variants, list) or not variants:
                raise ValueError("Producto sin variantes en la respuesta.")
            for variant in variants:
                if not isinstance(variant, dict):
                    raise ValueError("Variante remota inválida.")
                vid = _positive_id(variant.get("id"))
                if vid in seen_variants:
                    raise ValueError("Variante remota repetida.")
                seen_variants.add(vid)
                sku = variant.get("sku")
                if sku is not None and (not isinstance(sku, str) or len(sku) > 256):
                    raise ValueError("SKU remoto inválido.")
                if "sku" not in variant:
                    raise ValueError("Respuesta sin campo SKU.")
                visibility = product.get("visibility")
                rows.append({
                    "product_id": pid, "variant_id": vid,
                    "sku": sku.strip() if sku else "",
                    "name": name, "brand": _text(product.get("brand")),
                    "barcode": _text(variant.get("barcode")),
                    "visibility": visibility if visibility in ("visible", "hidden", "unlisted") else None,
                    "published": product.get("published") if type(product.get("published")) is bool else None,
                })
                if len(rows) > MAX_VARIANTS:
                    raise ValueError("Límite de variantes superado.")
        if len(seen_products) == expected:
            return {"products": expected, "rows": rows, "pages": page}
    raise ValueError("Captura incompleta; se conserva la copia anterior.")


def _record(db, *, lock=False):
    stmt = select(CatalogSnapshot).where(CatalogSnapshot.source == SOURCE)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt.execution_options(populate_existing=True))


def _revision(record):
    return record.updated_at.isoformat() if record else None


def refresh_catalog(db, settings, *, transport=None):
    if not settings.kiki_tiendanube_read_enabled:
        raise ValueError("Lectura de Tiendanube deshabilitada.")
    client = TiendanubeClient(
        settings.tiendanube_store_id, settings.tiendanube_access_token.get_secret_value(),
        user_agent=settings.tiendanube_user_agent, writes_enabled=False, transport=transport,
    )
    initial_revision = _revision(_record(db))
    # No DB transaction or lock while waiting for the remote provider.
    db.rollback()
    capture = read_catalog(client)
    capture["store_id"] = settings.tiendanube_store_id
    capture["captured_at"] = datetime.now(timezone.utc).isoformat()
    current = _record(db, lock=True)
    if _revision(current) != initial_revision:
        db.rollback()
        raise ValueError("Otra captura fue guardada; volvé a consultar.")
    if current:
        current.payload = [capture]
        current.updated_at = datetime.now(timezone.utc)
    else:
        db.add(CatalogSnapshot(source=SOURCE, payload=[capture]))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Otra captura fue guardada; volvé a consultar.") from None
    return capture


def compare_capture(capture, source_map, ecomm_id):
    """Only unique exact SKU candidates; never commercial identity approval."""
    if ecomm_id not in source_map:
        raise ValueError("Variante Ecomm-App no disponible en la captura API.")
    counts_ecomm = Counter(normalized_sku(r.get("sku")) for r in source_map.values())
    counts_tn = Counter(normalized_sku(r["sku"]) for r in capture["rows"])
    counts = Counter()
    for row in capture["rows"]:
        key = normalized_sku(row["sku"])
        state = (
            "MISSING_SKU" if not key else
            "DUPLICATE_TN" if counts_tn[key] > 1 else
            "AMBIGUOUS_ECOMM" if counts_ecomm[key] > 1 else
            "UNIQUE_SKU_CANDIDATE" if counts_ecomm[key] == 1 else
            "NO_ECOMM_SKU_MATCH"
        )
        counts[state] += 1
    target = normalized_sku(source_map[ecomm_id].get("sku"))
    matches = [r for r in capture["rows"] if target and normalized_sku(r["sku"]) == target]
    state = (
        "MISSING_SKU" if not target else
        "AMBIGUOUS_ECOMM" if counts_ecomm[target] != 1 else
        "DUPLICATE_TN" if len(matches) > 1 else
        "UNIQUE_SKU_CANDIDATE" if matches else "NO_SKU_MATCH_IN_CAPTURE"
    )
    return {"summary": dict(counts), "match_state": state, "matches_total": len(matches),
            "matches": matches[:10]}


def catalog_report(db, settings, ecomm_id):
    base = {"source": SOURCE, "ecomm_id": ecomm_id, "external_writes_enabled": False,
            "identity_verified": False}
    if not settings.kiki_tiendanube_read_enabled:
        return {**base, "state": "DISABLED"}
    record = _record(db)
    capture = record.payload[0] if record and record.payload else None
    if not capture or capture.get("store_id") != settings.tiendanube_store_id:
        return {**base, "state": "NOT_CAPTURED"}
    comparison = compare_capture(capture, sources(db), ecomm_id)
    at = datetime.fromisoformat(capture["captured_at"])
    age = datetime.now(timezone.utc) - at
    return {
        **base, **comparison, "state": "CAPTURED",
        "captured_at": capture["captured_at"], "store_id": capture["store_id"],
        "products": capture["products"], "variants": len(capture["rows"]),
        "fresh": timedelta(0) <= age <= timedelta(hours=24),
    }
