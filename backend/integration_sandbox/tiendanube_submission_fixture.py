"""Explicit offline TN double for the existing private PG18 browser profile."""
from copy import deepcopy
from urllib.parse import urlsplit


def install(application, settings):
    from .stage4_fixtures import _guard
    from app.api.routes import tiendanube_controlled_submission as routes
    from app.services import tiendanube_controlled_submission as service
    from app.integrations.tiendanube.client import TiendanubeClient
    from app.database.session import SessionLocal
    with SessionLocal() as db:
        _guard(db)
    # Only these routes receive fake credentials/opt-ins; production config is
    # unchanged. Network:none + socket guard make provider fallback impossible.
    cfg = settings.model_copy(update={
        "kiki_tiendanube_read_enabled": True, "kiki_tiendanube_writes_enabled": True,
        "tiendanube_store_id": "123",
    })
    from pydantic import SecretStr
    cfg.tiendanube_access_token = SecretStr("SYNTHETIC-TN-NOT-A-CREDENTIAL")
    routes.get_settings = lambda: cfg
    products = []
    calls = []
    def transport(method, url, **kwargs):
        path = urlsplit(url).path
        if not path.endswith("/123/products"):
            raise AssertionError("Only fixed synthetic store products are allowed")
        calls.append(method)
        if method == "GET":
            duplicate = [{"id": 990, "name": {"es": "Producto sintético ya existente"},
                          "variants": [{"id": 9901, "sku": "E4-SYNTHETIC-9104009"},
                                       {"id": 9902, "sku": "E4-SYNTHETIC-9104010"}]}]
            result = deepcopy(products + duplicate)
            return result, str(len(result))
        if method != "POST" or kwargs["payload"].get("published") is not False:
            raise AssertionError("Only hidden creation is allowed")
        payload = kwargs["payload"]
        if payload["variants"][0]["sku"] in {"E4-SYNTHETIC-9104011", "E4-SYNTHETIC-9104012"}:
            raise TimeoutError("Synthetic uncertain outcome")
        ident = 5000 + len(products)
        product = {**deepcopy(payload), "id": ident,
                   "variants": [{**payload["variants"][0], "id": ident * 10}]}
        products.append(product)
        return deepcopy(product)
    def client(*args, **kwargs):
        kwargs["transport"] = transport
        return TiendanubeClient(*args, **kwargs)
    service.TiendanubeClient = client
    application.state.synthetic_tn_calls = calls
