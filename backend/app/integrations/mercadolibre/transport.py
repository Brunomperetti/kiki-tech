import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass
class Response:
    status_code: int
    data: object


class MercadoLibreHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


class HTTPTransport:
    """Small injectable JSON transport. Commercial writes are deliberately not exposed."""

    def __init__(self, retries: int = 2, sleep=time.sleep):
        self.retries = retries
        self.sleep = sleep

    def request(self, method: str, url: str, *, headers=None, data=None) -> Response:
        if method not in {"GET", "POST"}:
            raise ValueError(
                "Mercado Libre integration only permits GET and controlled POST requests"
            )
        body = data.encode() if isinstance(data, str) else data
        for attempt in range(self.retries + 1):
            try:
                request = Request(url, data=body, headers=headers or {}, method=method)
                with urlopen(request, timeout=30) as response:  # noqa: S310
                    raw = response.read()
                    return Response(response.status, json.loads(raw or b"null"))
            except HTTPError as exc:
                if exc.code == 429 and attempt < self.retries:
                    delay = min(float(exc.headers.get("Retry-After", "1")), 5)
                    self.sleep(delay)
                    continue
                raw = exc.read()
                try:
                    detail = json.loads(raw).get(
                        "message", "Mercado Libre request failed"
                    )
                except (ValueError, AttributeError):
                    detail = "Mercado Libre request failed"
                raise MercadoLibreHTTPError(exc.code, detail) from exc
        raise RuntimeError("unreachable")
