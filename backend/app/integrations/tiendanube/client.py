"""Official Tiendanube API boundary; no automatic writes or retries."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class TiendanubeError(RuntimeError):
    def __init__(self, status_code: int, *, outcome_unknown: bool = False):
        self.status_code = status_code
        self.outcome_unknown = outcome_unknown
        super().__init__(f"Tiendanube: HTTP {status_code}; "
                         + ("resultado incierto; reconciliar antes de repetir"
                            if outcome_unknown else "solicitud no confirmada"))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport(method, url, *, headers, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("Respuesta demasiado grande")
            return json.loads(raw)
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise TiendanubeError(
            code, outcome_unknown=method != "GET" and code >= 500
        ) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise TiendanubeError(502, outcome_unknown=method != "GET") from None


def _id(value):
    if not re.fullmatch(r"[1-9][0-9]{0,19}", str(value)):
        raise ValueError("Identificador de Tiendanube inválido")
    return str(value)


class TiendanubeClient:
    """One store, fixed HTTPS host, explicit opt-in for hidden creation.

    Creation is a low-level primitive, not a publication workflow.
    The caller must first implement persisted identity and duplicate guards.
    """

    def __init__(self, store_id, access_token, *, user_agent, writes_enabled=False,
                 transport=None):
        self._base = f"https://api.tiendanube.com/2025-03/{_id(store_id)}"
        if not isinstance(access_token, str) or not access_token.strip() or any(
            c.isspace() for c in access_token
        ):
            raise ValueError("Token de Tiendanube inválido o ausente")
        if not isinstance(user_agent, str) or not user_agent.strip() or any(
            c in user_agent for c in "\r\n"
        ):
            raise ValueError("Identificación de aplicación inválida")
        self._headers = {"Authorization": f"Bearer {access_token}",
                         "User-Agent": user_agent,
                         "Content-Type": "application/json",
                         "Accept": "application/json"}
        self._writes_enabled = writes_enabled is True
        self._transport = transport or _transport

    def _get(self, path, params=None):
        url = self._base + path
        if params:
            url += "?" + urlencode(params)
        return self._transport("GET", url, headers=self._headers.copy())

    def list_products(self, *, page=1, per_page=30, query=""):
        if type(page) is not int or page < 1 or type(per_page) is not int or not 1 <= per_page <= 100:
            raise ValueError("Paginación inválida")
        params = {"page": page, "per_page": per_page}
        if query:
            params["q"] = query
        result = self._get("/products", params)
        if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
            raise TiendanubeError(502)
        return result

    def get_product(self, product_id):
        result = self._get("/products/" + _id(product_id))
        if not isinstance(result, dict) or str(result.get("id")) != str(product_id):
            raise TiendanubeError(502)
        return result

    def create_hidden_product(self, *, name, description, sku, brand=""):
        """Never sends prices, stock, media or categories; no live exposure."""
        if not self._writes_enabled:
            raise PermissionError("Escritura Tiendanube deshabilitada")
        if not all(isinstance(value, str) for value in (name, description, sku, brand)):
            raise ValueError("Campos comerciales inválidos")
        if not name.strip() or not description.strip() or not sku.strip():
            raise ValueError("Nombre, descripción y SKU son obligatorios")
        payload = {
            "name": {"es": name.strip()},
            "description": {"es": description.strip()},
            "visibility": "hidden",
            "variants": [{"sku": sku.strip()}],
        }
        if brand.strip():
            payload["brand"] = brand.strip()
        result = self._transport("POST", self._base + "/products",
                                 headers=self._headers.copy(), payload=payload)
        if not isinstance(result, dict):
            raise TiendanubeError(502, outcome_unknown=True)
        try:
            _id(result.get("id"))
        except ValueError:
            raise TiendanubeError(502, outcome_unknown=True) from None
        if result.get("visibility") != "hidden" or result.get("published") is True:
            raise TiendanubeError(502, outcome_unknown=True)
        return result
