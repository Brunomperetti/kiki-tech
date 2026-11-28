from app.integrations.tiendanube.client import TiendanubeClient, TiendanubeError


def check_connection(settings, *, transport=None):
    result = {"external_writes_enabled": False, "provider_calls": 0}
    if not settings.kiki_tiendanube_read_enabled:
        return {**result, "state": "DISABLED"}
    token = settings.tiendanube_access_token.get_secret_value()
    if not settings.tiendanube_store_id or not token:
        return {**result, "state": "NOT_CONFIGURED"}
    try:
        client = TiendanubeClient(
            settings.tiendanube_store_id, token,
            user_agent=settings.tiendanube_user_agent,
            writes_enabled=False, transport=transport,
        )
    except ValueError:
        return {**result, "state": "INVALID_CONFIG"}
    result["provider_calls"] = 1
    try:
        rows = client.list_products(page=1, per_page=1)
    except TiendanubeError as exc:
        return {**result, "state": "PROVIDER_ERROR", "http_status": exc.status_code}
    return {
        **result, "state": "CONNECTED_READ_ONLY",
        "store_id": settings.tiendanube_store_id,
        "sample_count": len(rows),
    }
