from urllib.parse import urlencode

from .oauth import OAuthManager
from .transport import HTTPTransport, MercadoLibreHTTPError


class MercadoLibreClient:
    """Official Mercado Libre read-only client (OAuth POST is the sole POST)."""

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
            data = self._get(
                "/items/bulk", {"ids": ",".join(item_ids[offset : offset + batch_size])}
            )
            for entry in data or []:
                if isinstance(entry, dict) and "body" in entry:
                    if entry.get("code", 200) == 200:
                        items.append(entry["body"])
                elif isinstance(entry, dict):
                    items.append(entry)
        return items

    def refresh_access_token(self, refresh_token: str) -> dict:
        return self.oauth.refresh(refresh_token)
