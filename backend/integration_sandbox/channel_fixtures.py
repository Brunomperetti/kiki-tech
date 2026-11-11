"""Opt-in authored channel fixtures; invoked only after disposable DB preflight."""

from .policy import preflight


def install(factory):
    from copy import deepcopy
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from app.database.models import (
        CatalogSnapshot,
        EcommApiProductEdit,
        InventoryLinkageDecision,
        TiendanubeMatchDecision,
    )
    from app.integrations.ecomm_app.catalog_stage import STAGE_SOURCE
    from app.integrations.mercadolibre.transformer import transform_item
    from app.services.tiendanube_csv_service import TiendanubeCsvService
    from app.services.ecomm_api_product_workspace_service import (
        EcommApiProductWorkspace,
        blank_fields,
    )

    with factory() as db:
        capture = db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == STAGE_SOURCE)
        )
        if (
            not capture
            or db.scalar(
                select(CatalogSnapshot).where(
                    CatalogSnapshot.source != "ECOMM_APP_API_STAGE"
                )
            )
            or db.scalar(select(EcommApiProductEdit))
        ):
            raise RuntimeError(
                "El escenario Canales requiere una base sintética nueva, sin otras capturas ni fichas."
            )
        pages = deepcopy(capture.payload)
        if [
            v["id"] for p in pages for parent in p["items"] for v in parent["variants"]
        ] != list(range(900001, 900007)):
            raise RuntimeError(
                "Identidades ajenas al fixture sintético; no se reemplaza el catálogo."
            )
        for i, qty in [(0, 2), (1, 6)]:
            parent = pages[0]["items"][i]
            parent["is_combo"] = True
            parent["variants"][0].update(
                description=f"Pack x{qty} de 250 g", is_combo=True
            )
        for i in [2, 3]:
            pages[0]["items"][i]["variants"][0]["gtin"] = "12345670"
        pages[0]["items"][5]["variants"][0].update(barcode="12345670", gtin="12345685")
        capture.payload = pages
        brand = "Marca sintética KIKI"
        ml = []
        for key, sku, title in [
            ("MLA900000001", "DEMO-ALM", "Almendras sintéticas Pack x2 de 250 g"),
            ("MLA900000002", "DEMO-ALM", "Almendras sintéticas Pack x6 de 250 g"),
            ("MLA900000003", "DEMO-CHIA", "Semillas de chía sintéticas 250 g"),
            ("MLA900000004", "DEMO-HAR", "Harina integral sintética 1 kg"),
            ("MLA900000006", "DEMO-LEN", "Lentejas sintéticas 1 kg"),
        ]:
            item = {
                "id": key,
                "title": title,
                "status": "active",
                "attributes": [
                    {"id": "SELLER_SKU", "value_name": sku},
                    {"id": "BRAND", "value_name": brand},
                ],
            }
            ml.extend(row.model_dump(mode="json") for row in transform_item(item))
        db.add(
            CatalogSnapshot(
                source="MERCADOLIBRE_API",
                payload=ml,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        # Exercise the existing CSV parser/import service, no new importer or TN HTTP.
        csv = (
            "Identificador de URL;Nombre;SKU;Precio;Stock;Marca;Código de barras\n"
            + "\n".join(
                [
                    f"chia-sintetica;Semillas de chía sintéticas 250 g;DEMO-CHIA;100;3;{brand};12345670",
                    f"harina-sintetica;Harina integral sintética 1 kg;DEMO-HAR;200;4;{brand};12345670",
                    f"alm-pack2;Almendras sintéticas Pack x2 de 250 g;DEMO-ALM;300;5;{brand};",
                    f"alm-pack6;Almendras sintéticas Pack x6 de 250 g;DEMO-ALM;600;6;{brand};",
                ]
            )
        )
        TiendanubeCsvService(db).import_csv(
            "canales-exclusivamente-sinteticos.csv", csv.encode()
        )
        tn = db.scalar(
            select(CatalogSnapshot).where(CatalogSnapshot.source == "TIENDANUBE")
        )
        tn.updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
        db.add(
            InventoryLinkageDecision(
                external_id="MLA900000003",
                decision="CONFIRMED",
                ecomm_id="900003",
                source_snapshot={"source": "ECOMM_APP_XLSX_HISTORICAL"},
                product_snapshot={"ecomm_id": "900003"},
                note="Decisión antigua de prueba; no valida identidad API.",
                history=[],
            )
        )
        db.add(
            TiendanubeMatchDecision(
                source_key="old-excel-chia",
                status="APPROVED",
                target_ecomm_id="900003",
                source_snapshot={"source": "ECOMM_APP_XLSX_HISTORICAL"},
                target_snapshot={},
                note="Decisión antigua de prueba no transferible.",
                history=[],
            )
        )
        db.commit()
        for ident in ["900001", "900002", "900003", "900004"]:
            EcommApiProductWorkspace(db).save(
                ident, {**blank_fields(), "brand": brand}, "DRAFT", 0
            )


if __name__ == "__main__":
    preflight()
    from .bootstrap import create_sandbox_app

    create_sandbox_app()
    from app.database.session import SessionLocal

    install(SessionLocal)
    print(
        "Escenario Canales exclusivamente sintético instalado en PostgreSQL descartable."
    )
