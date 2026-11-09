"""Invented dietetics catalog. No client exports, credentials or captured real data."""

from sqlalchemy import select


def seed(factory):
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
