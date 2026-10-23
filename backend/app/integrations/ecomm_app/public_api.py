"""Ecomm-App Public API v1.0: bounded read-only inventory diagnostics.

Official vendor contract (supplied by account owner):
    GET  /api/v3/public/inventario/depositos
    GET  /api/v3/public/inventario/productos?limit=...
    POST /api/v3/public/inventario/productos/consulta  {"skus": [...]}

The POST above is a *read-only stock lookup*, NOT a mutation. Never
send credentials to clients/logs or modify existing ECOMM_APP snapshots.
"""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://admin.ecomm-app.com"
API_PREFIX = "/api/v3/public/inventario"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class EcommAppApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def _safe_error(status: int, payload: object) -> EcommAppApiError:
    error = payload.get("error") if isinstance(payload, dict) else None
    code = str(error.get("code") or "ERROR_REMOTO") if isinstance(error, dict) else "ERROR_REMOTO"
    known = {
        "SCOPE_INSUFICIENTE": "A la clave le falta el permiso inventario:leer.",
        "API_PUBLICA_NO_HABILITADA": "La cuenta no tiene habilitada la API pública.",
        "PLAN_NO_HABILITADO": "El plan no incluye la API pública.",
        "PLAN_SIN_STOCK": "El plan no incluye la API de stock.",
        "CUENTA_DUMMY": "Una cuenta de prueba no puede utilizar esta API.",
        "SUSCRIPCION_VENCIDA": "La suscripción de Ecomm-App está vencida.",
        "DEPOSITO_INEXISTENTE": "Ese depósito no existe o no está activo.",
    }
    # Never return arbitrary upstream error messages: some vendors echo
    # credentials, request headers or internal exception details.
    message = known.get(code) or {
        401: "Ecomm-App rechazó la clave. Revisá el token en Render.",
        402: "La suscripción de Ecomm-App requiere revisión.",
        403: "Ecomm-App rechazó el acceso o los permisos.",
        404: "El recurso solicitado no está disponible.",
        429: "Ecomm-App alcanzó el límite de consultas. Probá más tarde.",
    }.get(status, "Ecomm-App no pudo completar la consulta.")
    return EcommAppApiError(status, code[:80], message)


def _fetch(method: str, path: str, token: str, *, params: dict | None = None,
           body: dict | None = None) -> object:
    if method not in {"GET", "POST"} or path not in {
        f"{API_PREFIX}/depositos",
        f"{API_PREFIX}/productos",
        f"{API_PREFIX}/productos/consulta",
    }:
        raise ValueError("Operación no admitida por la integración de inventario.")
    if method == "POST" and (path != f"{API_PREFIX}/productos/consulta" or not body):
        raise ValueError("Solo se permite el POST de consulta de stock.")
    url = BASE_URL + path
    if params:
        url += "?" + urlencode(params)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=12) as response:  # noqa: S310
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        try:
            error_body = json.loads(exc.read(32_768))
        except (ValueError, OSError):
            error_body = None
        raise _safe_error(exc.code, error_body) from None
    except (URLError, TimeoutError, OSError):
        raise EcommAppApiError(
            503, "SIN_CONEXION", "No pudimos conectarnos con Ecomm-App."
        ) from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise EcommAppApiError(
            502, "RESPUESTA_GRANDE", "La respuesta excede el máximo seguro de lectura."
        )
    try:
        envelope = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise EcommAppApiError(
            502, "JSON_INVALIDO", "Ecomm-App devolvió una respuesta no válida."
        ) from None
    if not isinstance(envelope, dict):
        raise EcommAppApiError(502, "FORMATO_INESPERADO", "Respuesta API sin objeto JSON.")
    if "error" in envelope:
        raise _safe_error(502, envelope)
    if "data" not in envelope:
        raise EcommAppApiError(502, "SIN_DATA", "La API no devolvió el campo data esperado.")
    return envelope["data"]


def _items(value: object) -> tuple[list[dict] | None, list[str]]:
    """Tolerate envelope shapes while exposing mismatches for mapping review.

    Product/warehouse DTO shapes have not yet been confirmed from a live
    response; never silently assume a missing collection means zero records.
    """
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)], []
    if not isinstance(value, dict):
        return None, []
    for key in ("items", "products", "productos", "results", "rows", "warehouses", "depositos", "data"):
        container = value.get(key)
        if isinstance(container, list):
            return [x for x in container if isinstance(x, dict)], sorted(value.keys())
        if isinstance(container, dict):
            nested, _ = _items(container)
            if nested is not None:
                return nested, sorted(value.keys())
    # Single product objects can be returned by the SKU lookup API.
    if any(key in value for key in ("variants", "code", "sku_madre")):
        return [value], sorted(value.keys())
    return None, sorted(value.keys())


def _preview_items(data: object, *, kind: str) -> dict:
    items, envelope_keys = _items(data)
    if items is None:
        return {
            "shape_recognized": False, "count": None, "envelope_keys": envelope_keys,
            "samples": [], "warning": "Falta confirmar la estructura real de la respuesta de Ecomm-App.",
        }
    samples = []
    for item in items[:5]:
        if kind == "warehouses":
            samples.append({
                "id": item.get("id"), "name": item.get("name") or item.get("nombre"),
                "available_fields": sorted(item.keys())[:25],
            })
            continue
        variants = item.get("variants")
        if not isinstance(variants, list):
            variants = []
        shown = []
        for variant in variants[:5]:
            if not isinstance(variant, dict):
                continue
            warehouses = variant.get("warehouses")
            shown.append({
                "sku": variant.get("sku") or variant.get("code"),
                "id": variant.get("id"),
                "description": variant.get("description"),
                "variant_description": variant.get("variant_description"),
                "is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
                "barcode": variant.get("barcode") or variant.get("gtin"),
                "total_stock": variant.get("total_stock"),
                "available_fields": sorted(variant.keys())[:25],
                "warehouse_sample": [
                    {"id": w.get("id") or w.get("warehouse_id"),
                     "stock": w.get("stock") or (0 if w.get("stock") == 0 else None)}
                    for w in warehouses[:5] if isinstance(w, dict)
                ] if isinstance(warehouses, list) else [],
            })
        samples.append({
            "code": item.get("code") or item.get("sku_madre"),
            "description": item.get("description") or item.get("name"),
            "is_combo": item.get("is_combo") if isinstance(item.get("is_combo"), bool) else None,
            "total_stock": item.get("total_stock"),
            "variant_count": len(variants),
            "variants": shown,
            "available_fields": sorted(item.keys())[:25],
        })
    return {
        "shape_recognized": True, "count": len(items),
        "envelope_keys": envelope_keys,
        "samples": samples, "warning": None,
    }


def _requested_sku_diagnosis(data: object, requested: list[str]) -> dict:
    """Distinguish requested exact variants from extra sibling variants.

    Ecomm returns parent products WITH their sibling variants. The number of
    parent records is not the number of matched SKUs. Never identify a
    requested SKU using an alias, title, prefix, or cosmetic normalization.
    """
    parents, envelope_keys = _items(data)
    if parents is None:
        return {
            "shape_recognized": False, "parent_count": None,
            "variant_count": None, "sibling_variant_count": None,
            "envelope_keys": envelope_keys,
            "requested": [
                {"sku": sku, "status": "UNKNOWN_SHAPE", "matches": []}
                for sku in requested
            ],
            "warning": "Ecomm-App respondió, pero aún no se reconoce el formato de consulta.",
        }

    exact_matches = {sku: [] for sku in requested}
    total_variants = 0
    sibling_variants = 0
    for parent in parents:
        variants = parent.get("variants")
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            total_variants += 1
            variant_sku = variant.get("sku")
            if isinstance(variant_sku, str) and variant_sku in exact_matches:
                exact_matches[variant_sku].append({
                    "parent_code": parent.get("code"),
                    "parent_description": parent.get("description"),
                    "parent_is_combo": parent.get("is_combo") if isinstance(parent.get("is_combo"), bool) else None,
                    "variant_id": variant.get("id"),
                    "variant_sku": variant_sku,
                    "variant_is_combo": variant.get("is_combo") if isinstance(variant.get("is_combo"), bool) else None,
                    "total_stock": variant.get("total_stock"),
                    "variant_description": variant.get("variant_description"),
                })
            else:
                sibling_variants += 1
    results = []
    for sku in requested:
        matches = exact_matches[sku]
        if len(matches) > 1:
            status = "MULTIPLE_EXACT"
        elif len(matches) == 1:
            status = "EXACT_SINGLE"
        else:
            status = "NO_EXACT"
        results.append({
            "sku": sku, "status": status, "matches": matches,
        })
    return {
        "shape_recognized": True,
        "parent_count": len(parents),
        "variant_count": total_variants,
        "sibling_variant_count": sibling_variants,
        "envelope_keys": envelope_keys,
        "requested": results,
        "warning": None,
    }


class EcommAppInventoryClient:
    def __init__(self, token: str, requester=_fetch):
        if not token.strip():
            raise ValueError("ECOMM_APP_API_TOKEN no está configurado en Render.")
        self._token = token.strip()
        self._requester = requester

    def _call(self, method: str, path: str, *, params=None, body=None) -> object:
        return self._requester(method, path, self._token, params=params, body=body)

    def preview(self) -> dict:
        warehouses = self._call("GET", f"{API_PREFIX}/depositos")
        products = self._call(
            "GET", f"{API_PREFIX}/productos", params={"page": 1, "limit": 3}
        )
        return {
            "connected": True,
            "mode": "READ_ONLY_PREVIEW",
            "warehouse_preview": _preview_items(warehouses, kind="warehouses"),
            "product_preview": _preview_items(products, kind="products"),
            "note": (
                "Lectura limitada a la primera página de 3 productos; no se "
                "importó nada ni se modificaron snapshots, decisiones o stock."
            ),
        }

    def catalog_audit(self, start_page: int = 1) -> dict:
        # Kept separate from the normal catalog and persisted snapshots.
        from .catalog_audit import audit_catalog_pages
        return audit_catalog_pages(
            lambda page: self._call(
                "GET", f"{API_PREFIX}/productos",
                params={"page": page, "limit": 50, "sort": "sku_asc"},
            ),
            start_page=start_page,
        )

    def lookup(self, skus: list[str]) -> dict:
        if not 1 <= len(skus) <= 3 or any(
            not isinstance(sku, str) or not 1 <= len(sku.strip()) <= 128
            for sku in skus
        ):
            raise ValueError("Ingresá entre 1 y 3 SKU, de hasta 128 caracteres.")
        if len(set(skus)) != len(skus):
            raise ValueError("Los SKU de la consulta no pueden repetirse.")
        products = self._call(
            "POST", f"{API_PREFIX}/productos/consulta", body={"skus": skus},
        )
        return {
            "mode": "READ_ONLY_SKU_LOOKUP",
            "requested_skus": skus,
            "sku_diagnosis": _requested_sku_diagnosis(products, skus),
            "product_preview": _preview_items(products, kind="products"),
            "note": (
                "El POST de consulta es de solo lectura y no modifica stock. "
                "Ecomm puede devolver variantes hermanas del mismo producto. "
                "Solo las coincidencias literales del SKU pedido se presentan "
                "como exactas; ninguna autoriza cambios en inventario."
            ),
        }
