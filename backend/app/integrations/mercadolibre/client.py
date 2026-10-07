import json
from urllib.parse import urlencode

from .oauth import OAuthManager
from .transport import HTTPTransport, MercadoLibreHTTPError


class MercadoLibreClient:
    """Official Mercado Libre client limited to reads and non-mutating validations."""

    def __init__(self, settings, access_token: str = "", transport=None):
        self.settings = settings
        self.access_token = access_token
        self.transport = transport or HTTPTransport()
        self.oauth = OAuthManager(settings, self.transport)

    def _get(self, path: str, params: dict | None = None):
        url = f"{self.settings.ml_api_url}{path}"
        if params:
            url += f"?{urlencode(params)}"
        response = self.transport.request(
            "GET", url, headers={"Authorization": f"Bearer {self.access_token}"}
        )
        if response.status_code >= 400:
            raise MercadoLibreHTTPError(
                response.status_code, "Mercado Libre request failed"
            )
        return response.data

    def _post_json(self, path: str, payload: dict):
        url = f"{self.settings.ml_api_url}{path}"
        response = self.transport.request(
            "POST",
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload, ensure_ascii=False),
        )
        if response.status_code >= 400:
            raise MercadoLibreHTTPError(
                response.status_code, "Mercado Libre request failed"
            )
        return response.data

    def get_current_user(self) -> dict:
        return self._get("/users/me")

    def list_item_ids(self, user_id: str) -> list[str]:
        """Use scan/scroll so the result is not capped at 1,000 listings."""
        item_ids: list[str] = []
        params = {"search_type": "scan", "limit": 100}
        while True:
            data = self._get(f"/users/{user_id}/items/search", params)
            results = data.get("results") or []
            item_ids.extend(str(item_id) for item_id in results)
            scroll_id = data.get("scroll_id")
            if not results or not scroll_id:
                break
            params = {"search_type": "scan", "limit": 100, "scroll_id": scroll_id}
        return item_ids

    def get_items_bulk(self, item_ids: list[str], batch_size: int = 20) -> list[dict]:
        items = []
        for offset in range(0, len(item_ids), batch_size):
            batch = item_ids[offset : offset + batch_size]
            data = self._get("/items/bulk", {"ids": ",".join(batch)})
            if not isinstance(data, list) or len(data) != len(batch):
                raise MercadoLibreHTTPError(
                    502, "Mercado Libre returned an incomplete bulk batch"
                )
            for entry in data or []:
                if not isinstance(entry, dict):
                    raise MercadoLibreHTTPError(
                        502, "Mercado Libre returned an invalid bulk item"
                    )
                status = entry.get("status_code", entry.get("code"))
                if status != 200:
                    raise MercadoLibreHTTPError(
                        status if isinstance(status, int) else 502,
                        "Mercado Libre bulk item failed",
                    )
                if "body" not in entry or not isinstance(entry["body"], dict):
                    raise MercadoLibreHTTPError(
                        502, "Mercado Libre returned an invalid bulk item body"
                    )
                items.append(entry["body"])
        return items

    def predict_categories(
        self, title: str, *, site_id: str = "MLA", limit: int = 3
    ) -> list[dict]:
        """Read Mercado Libre's category predictor for the supplied local title."""
        if not title.strip():
            raise ValueError("El título es obligatorio para predecir categoría.")
        safe_limit = max(1, min(int(limit), 8))
        data = self._get(
            f"/sites/{site_id}/domain_discovery/search",
            {"q": title.strip(), "limit": safe_limit},
        )
        if not isinstance(data, list):
            raise MercadoLibreHTTPError(
                502, "Mercado Libre returned an invalid category prediction"
            )
        return [candidate for candidate in data if isinstance(candidate, dict)]

    def get_category_attributes(self, category_id: str) -> list[dict]:
        """Read the attributes declared by Mercado Libre for one category."""
        if not category_id.strip():
            raise ValueError("La categoría es obligatoria.")
        data = self._get(f"/categories/{category_id.strip()}/attributes")
        if not isinstance(data, list):
            raise MercadoLibreHTTPError(
                502, "Mercado Libre returned invalid category attributes"
            )
        return [attribute for attribute in data if isinstance(attribute, dict)]

    def get_conditional_required_attributes(
        self, category_id: str, item_payload: dict
    ) -> list[dict]:
        """Evaluate conditional_required attributes without creating an item."""
        category_id = category_id.strip()
        if not category_id:
            raise ValueError("La categoría es obligatoria.")
        if not isinstance(item_payload, dict) or not item_payload:
            raise ValueError("El payload del producto es obligatorio.")
        data = self._post_json(
            f"/categories/{category_id}/attributes/conditional", item_payload
        )
        if not isinstance(data, dict):
            raise MercadoLibreHTTPError(
                502, "Mercado Libre returned invalid conditional attributes"
            )
        required = data.get("required_attributes") or []
        if not isinstance(required, list):
            raise MercadoLibreHTTPError(
                502, "Mercado Libre returned invalid conditional attributes"
            )
        return [attribute for attribute in required if isinstance(attribute, dict)]

    def refresh_access_token(self, refresh_token: str) -> dict:
        return self.oauth.refresh(refresh_token)
