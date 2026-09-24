from io import BytesIO
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.models import Base
from app.services.reconciliation_service import ReconciliationService


def xlsx(rows, header=True):
    stream = BytesIO()
    pd.DataFrame(rows).to_excel(stream, index=False, header=header, engine="openpyxl")
    return stream.getvalue()


def test_real_exports_import_normalize_reconcile_and_generate_metrics():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    ecomm = [
        ["No Modificar", "Obligatorio", None, None, None, None, None],
        [
            "Descripción del producto",
            "SKU del Producto",
            "SKU de la variante",
            "Código de barra",
            "Precio Marketplace",
            "Marca",
            "General",
        ],
        ["Café rojo", "001", "001-R", None, 100, "KIKI", 2],
        ["Té", "002", None, "0779123456789", 80, "KIKI", 3],
        ["Té duplicado", "002", None, None, 85, "KIKI", 1],
    ]
    ml = [
        {
            "Título de la publicación": "Café rojo",
            "Nro. de la publicación": "MLA1",
            "SKU": "001",
            "SKU de la Variante": "001-R",
            "Status": "active",
            "Precio": 100,
            "Publicacion Vinculada con Inventario": "Sí",
        },
        {
            "Título de la publicación": "Publicación suelta",
            "Nro. de la publicación": "MLA2",
            "SKU": "999",
            "SKU de la Variante": None,
            "Status": "paused",
            "Precio": 50,
            "Publicacion Vinculada con Inventario": "No",
        },
    ]
    with Session(engine) as db:
        service = ReconciliationService(db)
        ecomm_job = service.import_file("ECOMM_APP", "ecomm.xlsx", xlsx(ecomm, False))
        ml_job = service.import_file("MERCADOLIBRE", "ml.xlsx", xlsx(ml))
        run = service.analyze()
        assert (
            ecomm_job.diagnostics["header_row"] == 2
            and ecomm_job.diagnostics["rows_accepted"] == 3
        )
        assert ml_job.diagnostics["rows_accepted"] == 2
        assert run.summary["total_products"] == 3 and run.summary["total_listings"] == 2
        assert (
            run.summary["ALREADY_PUBLISHED"] == 1
            and run.summary["POSSIBLE_DUPLICATE"] == 2
            and run.summary["UNMATCHED_ML_LISTING"] == 1
        )
