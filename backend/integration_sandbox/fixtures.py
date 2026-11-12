"""Invented dietetics catalog. No client exports, credentials or captured real data."""

from sqlalchemy import select


def seed(factory, *, allow_scaled=False):
    from app.database.models import CatalogSnapshot, MercadoLibreConnection
    from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE

    items = []
    for index, (name, presentation, sku) in enumerate(
        [
            ("Almendras sintéticas", "250 g", "DEMO-ALM"),
            ("Almendras sintéticas", "1 kg", "DEMO-ALM"),
            ("Semillas de chía sintéticas", "250 g", "DEMO-CHIA"),
            ("Harina integral sintética", "1 kg", "DEMO-HAR"),
            ("Avena sintética", "500 g", "DEMO-AVE"),
            ("Lentejas sintéticas", "1 kg", "DEMO-LEN"),
        ],
        start=1,
    ):
        items.append(
            {
                "code": f"SYNTHETIC-{index}",
                "description": name,
                "is_combo": False,
                "variants": [
                    {
                        "id": 900000 + index,
                        "sku": sku,
                        "description": presentation,
                        "is_combo": False,
                        "gtin": None,
                        "total_stock": index * 3,
                        "warehouses": [],
                    }
                ],
            }
        )
    payload = [
        {
            "page": 1,
            "total": len(items),
            "total_pages": 1,
            "per_page": 50,
            "captured_at": "2026-11-01T12:00:00+00:00",
            "items": items,
        }
    ]
    with factory() as db:
        if db.scalar(select(MercadoLibreConnection)):
            raise RuntimeError(
                "Una conexión de proveedor no pertenece a este entorno sintético."
            )
        records = db.scalars(select(CatalogSnapshot)).all()
        if records:
            if allow_scaled and len(records) == 1 and records[0].source == STAGE_SOURCE:
                candidate = records[0].payload
                size = (
                    candidate[0].get("total")
                    if candidate and isinstance(candidate[0], dict)
                    else None
                )
                if (
                    isinstance(size, int)
                    and 1 <= size <= 10000
                    and candidate == scaled_capture(size)
                ):
                    return
            if (
                len(records) != 1
                or records[0].source != STAGE_SOURCE
                or records[0].payload != payload
            ):
                raise RuntimeError(
                    "La base contiene datos ajenos al fixture; inicio cancelado."
                )
            return
        db.add(CatalogSnapshot(source=STAGE_SOURCE, payload=payload))
        db.commit()


def scaled_capture(size):
    """Exact authored fixture accepted on isolated restarts; never authentic data."""
    if not isinstance(size, int) or not 1 <= size <= 10000:
        raise ValueError("Tamaño de catálogo sintético inválido.")
    items = [
        {
            "code": f"BATCH-SYNTHETIC-{i}",
            "description": "Almendras sintéticas",
            "is_combo": False,
            "variants": [
                {
                    "id": 900001 + i,
                    "sku": f"BATCH-SYNTHETIC-{i}",
                    "description": "250 g",
                    "is_combo": False,
                    "gtin": None,
                    "total_stock": 3,
                    "warehouses": [],
                }
            ],
        }
        for i in range(size)
    ]
    return [
        {
            "page": i // 50 + 1,
            "total": size,
            "total_pages": (size + 49) // 50,
            "per_page": 50,
            "captured_at": "2026-11-01T12:00:00+00:00",
            "items": items[i : i + 50],
        }
        for i in range(0, size, 50)
    ]
