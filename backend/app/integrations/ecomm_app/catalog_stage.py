"""Resumable read-only Ecomm-App catalog COPY in a separate staging snapshot.

Never writes to ECOMM_APP, ECOMM_APP_RAW, ML/TN or reconciliation decisions.
A stage is deliberately NOT a trustworthy production inventory source.
"""
from collections import Counter
from datetime import datetime, timezone
from math import ceil

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...database.models import CatalogSnapshot
from .public_api import API_PREFIX, EcommAppApiError

STAGE_SOURCE = "ECOMM_APP_API_STAGE"
REFRESH_SOURCE = "ECOMM_APP_API_REFRESH"
PAGE_SIZE = 50
PAGES_PER_BATCH = 3
STAGE_VERSION = 1


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _source_page(raw: object, expected_page: int, baseline: dict | None) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise EcommAppApiError(
            502, "FORMATO_CATALOGO", "La API no devolvió una lista de productos en data.items."
        )
    pagination = raw.get("paginacion")
    if not isinstance(pagination, dict):
        pagination = raw.get("pagination")
    if not isinstance(pagination, dict):
        raise EcommAppApiError(
            502, "SIN_PAGINACION", "La API no informó paginación; se conservó la copia anterior."
        )
    page = pagination.get("page")
    total = pagination.get("total")
    per_page = pagination.get("per_page")
    total_pages = pagination.get("total_pages")
    if not all(_integer(v) for v in (page, total, per_page, total_pages)):
        raise EcommAppApiError(
            502, "PAGINACION_INCOMPLETA",
            "Faltan datos numéricos de página, tamaño, total o cantidad de páginas."
        )
    if (page != expected_page or per_page != PAGE_SIZE or total < 1 or
            total_pages != ceil(total / PAGE_SIZE)):
        raise EcommAppApiError(
            409, "PAGINACION_INCONSISTENTE",
            "Los números de paginación no coinciden. No se incorporó este bloque a la copia.",
        )
    if baseline is not None and (
        total != baseline["total"] or total_pages != baseline["total_pages"]
    ):
        raise EcommAppApiError(
            409, "CATALOGO_CAMBIO",
            "La cantidad del catálogo cambió durante la copia. Se conservó el avance anterior.",
        )
    expected_count = min(PAGE_SIZE, total - (page - 1) * PAGE_SIZE)
    source_items = raw["items"]
    if len(source_items) != expected_count or any(
        not isinstance(x, dict) for x in source_items
    ):
        raise EcommAppApiError(
            409, "PAGINA_INCOMPLETA",
            "La página no contiene la cantidad esperada de productos. No se guardó este bloque.",
        )
    items = []
    for parent in source_items:
        variants = parent.get("variants")
        if not isinstance(variants, list):
            variants = None
        compact_variants = None if variants is None else []
        for variant in variants or []:
            if not isinstance(variant, dict):
                # Preserve that structural defect explicitly for quality review.
                compact_variants.append({"invalid": True})
                continue
            warehouses = variant.get("warehouses")
            compact_variants.append({
                "id": variant.get("id"),
                "sku": variant.get("sku"),
                "description": variant.get("description"),
                "variant_description": variant.get("variant_description"),
                "is_combo": variant.get("is_combo")
                if isinstance(variant.get("is_combo"), bool) else None,
                "total_stock": variant.get("total_stock"),
                "barcode": variant.get("barcode"),
                "gtin": variant.get("gtin"),
                "warehouses": [
                    {
                        "id": warehouse.get("id") or warehouse.get("warehouse_id"),
                        "stock": warehouse.get("stock"),
                    }
                    for warehouse in warehouses
                    if isinstance(warehouse, dict)
                ] if isinstance(warehouses, list) else None,
            })
        items.append({
            "code": parent.get("code"),
            "description": parent.get("description"),
            "is_combo": parent.get("is_combo")
            if isinstance(parent.get("is_combo"), bool) else None,
            "total_stock": parent.get("total_stock"),
            "variants": compact_variants,
        })
    return {
        "version": STAGE_VERSION,
        "page": page,
        "total": total,
        "total_pages": total_pages,
        "per_page": PAGE_SIZE,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def _quality(pages: list[dict]) -> dict:
    totals = Counter()
    all_ids = set()
    all_skus = set()
    duplicate_ids = set()
    duplicate_skus = set()
    for page in pages:
        totals["parents"] += len(page["items"])
        for parent in page["items"]:
            if parent.get("is_combo") is True:
                totals["combo_parents"] += 1
            variants = parent.get("variants")
            if variants is None:
                totals["parents_without_variants"] += 1
                continue
            for variant in variants:
                totals["variants"] += 1
                if variant.get("invalid"):
                    totals["invalid_variants"] += 1
                    continue
                if variant.get("is_combo") is True:
                    totals["combo_variants"] += 1
                vid = variant.get("id")
                if vid is None or vid == "":
                    totals["without_variant_id"] += 1
                else:
                    vkey = str(vid)
                    if vkey in all_ids:
                        duplicate_ids.add(vkey)
                    all_ids.add(vkey)
                sku = variant.get("sku")
                if not isinstance(sku, str) or not sku.strip():
                    totals["without_sku"] += 1
                else:
                    if sku in all_skus:
                        duplicate_skus.add(sku)
                    all_skus.add(sku)
                if variant.get("total_stock") is None:
                    totals["without_total_stock"] += 1
    return {
        "parents": totals["parents"], "variants": totals["variants"],
        "combo_parents": totals["combo_parents"],
        "combo_variants": totals["combo_variants"],
        "parents_without_variants": totals["parents_without_variants"],
        "invalid_variants": totals["invalid_variants"],
        "without_variant_id": totals["without_variant_id"],
        "without_sku": totals["without_sku"],
        "without_total_stock": totals["without_total_stock"],
        "duplicate_variant_ids": len(duplicate_ids),
        "duplicate_skus": len(duplicate_skus),
    }


def stage_status(pages: list[dict] | None) -> dict:
    pages = pages or []
    expected = pages[0]["total"] if pages else None
    total_pages = pages[0]["total_pages"] if pages else None
    next_page = len(pages) + 1
    complete = bool(pages) and len(pages) == total_pages
    quality = _quality(pages)
    problems = sum(quality[key] for key in (
        "parents_without_variants", "invalid_variants", "without_variant_id",
        "without_sku", "without_total_stock", "duplicate_variant_ids",
    ))
    return {
        "mode": "READ_ONLY_STAGE",
        "source": STAGE_SOURCE,
        "exists": bool(pages),
        "complete": complete,
        "can_continue": bool(total_pages is None or next_page <= total_pages),
        "expected_parents": expected,
        "expected_pages": total_pages,
        "pages_saved": len(pages),
        "next_page": next_page if not complete else None,
        "first_page_at": pages[0]["captured_at"] if pages else None,
        "last_page_at": pages[-1]["captured_at"] if pages else None,
        "quality": quality,
        "has_quality_warnings": problems > 0,
        "warning": (
            "Se completó una copia de prueba, NO se actualizó el catálogo usado por KIKI. "
            "La paginación puede variar si Ecomm-App cambia productos durante el barrido; "
            "requiere revisión antes de usarla como fuente."
            if complete else
            "Esta copia es parcial; nunca usarla para precios, stock ni conciliación."
        ),
    }


def _extend(pages: list[dict], raw_pages: list[object]) -> list[dict]:
    new_pages = list(pages)
    baseline = new_pages[0] if new_pages else None
    expected_page = len(new_pages) + 1
    for raw in raw_pages:
        page = _source_page(raw, expected_page, baseline)
        new_pages.append(page)
        if baseline is None:
            baseline = page
        expected_page += 1
    quality = _quality(new_pages)
    if quality["duplicate_variant_ids"]:
        raise EcommAppApiError(
            409, "ID_VARIANTE_REPETIDO",
            "Aparecieron IDs de variante duplicados entre páginas. "
            "Se conservó la copia anterior sin incorporar el bloque.",
        )
    return new_pages


class EcommAppStageService:
    def __init__(self, db, client, source: str = STAGE_SOURCE):
        if source not in (STAGE_SOURCE, REFRESH_SOURCE):
            raise ValueError("Fuente de captura Ecomm-App no permitida.")
        self.db = db
        self.client = client
        self.source = source

    def status(self) -> dict:
        item = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == self.source)
        )
        return stage_status(item.payload if item else [])

    def next_batch(self) -> dict:
        current = self.db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == self.source)
        )
        original_pages = current.payload if current else []
        state = stage_status(original_pages)
        if state["complete"]:
            return state
        first = state["next_page"]
        final = min(
            first + PAGES_PER_BATCH - 1,
            state["expected_pages"] or first + PAGES_PER_BATCH - 1,
        )
        raw_pages = []
        expected_total = state["expected_parents"]
        expected_pages = state["expected_pages"]
        for page in range(first, final + 1):
            raw = self.client._call(
                "GET", f"{API_PREFIX}/productos",
                params={"page": page, "limit": PAGE_SIZE, "sort": "sku_asc"},
            )
            # Validate each response immediately. Never request a page past
            # the actual last page when starting from a new empty stage.
            normalized = _source_page(
                raw, page,
                {"total": expected_total, "total_pages": expected_pages}
                if expected_total is not None else None,
            )
            if expected_total is None:
                expected_total = normalized["total"]
                expected_pages = normalized["total_pages"]
            raw_pages.append(raw)
            if page == expected_pages:
                break

        # Lock and recheck so two sessions can't both append the same pages.
        locked = self.db.scalar(
            select(CatalogSnapshot)
            .where(CatalogSnapshot.source == self.source)
            .with_for_update()
        )
        latest = locked.payload if locked else []
        if len(latest) != len(original_pages):
            self.db.rollback()
            raise EcommAppApiError(
                409, "COPIA_AVANZO", "Otra solicitud avanzó la copia. Consultá el estado actualizado."
            )
        staged = _extend(latest, raw_pages)
        # Complete refreshes are promoted atomically: never expose a
        # partially updated catalog to browsers, AI or editorial saves.
        if self.source == REFRESH_SOURCE and stage_status(staged)["complete"]:
            quality = stage_status(staged)["quality"]
            if any(quality[key] for key in (
                "invalid_variants", "without_variant_id", "duplicate_variant_ids"
            )):
                self.db.rollback()
                raise EcommAppApiError(
                    409, "CALIDAD_INVENTARIO",
                    "La copia nueva tiene variantes sin identidad segura. Se conservó la última copia completa.",
                )
            live = self.db.scalar(
                select(CatalogSnapshot)
                .where(CatalogSnapshot.source == STAGE_SOURCE)
                .with_for_update()
            )
            if live:
                live.payload = staged
                live.updated_at = datetime.now(timezone.utc)
            else:
                self.db.add(CatalogSnapshot(source=STAGE_SOURCE, payload=staged))
        if locked:
            locked.payload = staged
            locked.updated_at = datetime.now(timezone.utc)
        else:
            self.db.add(CatalogSnapshot(source=self.source, payload=staged))
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise EcommAppApiError(
                409, "COPIA_AVANZO", "La copia avanzó en otra sesión. Revisá su estado."
            ) from None
        return stage_status(staged)
