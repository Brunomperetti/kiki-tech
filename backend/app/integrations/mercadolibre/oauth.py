from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .transport import HTTPTransport, MercadoLibreHTTPError


class OAuthManager:
    def __init__(self, settings, transport: HTTPTransport):
        self.settings = settings
        self.transport = transport

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.ml_client_id,
                "redirect_uri": self.settings.ml_redirect_uri,
                "state": state,
            }
        )
        return f"{self.settings.ml_authorization_url}?{query}"

    def exchange_code(self, code: str) -> dict:
        return self._token(
            {
                "grant_type": "authorization_code",
                "client_id": self.settings.ml_client_id,
                "client_secret": self.settings.ml_client_secret,
                "code": code,
                "redirect_uri": self.settings.ml_redirect_uri,
            }
        )

    def refresh(self, refresh_token: str) -> dict:
        return self._token(
            {
                "grant_type": "refresh_token",
                "client_id": self.settings.ml_client_id,
                "client_secret": self.settings.ml_client_secret,
                "refresh_token": refresh_token,
            }
        )

    def _token(self, values: dict) -> dict:
        response = self.transport.request(
            "POST",
            f"{self.settings.ml_api_url}/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urlencode(values),
        )
        if response.status_code >= 400 or not isinstance(response.data, dict):
            raise MercadoLibreHTTPError(
                response.status_code, "OAuth token request failed"
            )
        return response.data

    @staticmethod
    def expires_at(token: dict) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
