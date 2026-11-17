"""Authenticated read-only research manifest; no source approval or vendor writes.

One row per Ecomm ID/SKU with a unique eligible Excel GTIN lookup hint.
It is a research workload, NOT a manufacturer's evidence or a commercial fiche.
"""
import csv
from io import StringIO

from .ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .ecomm_api_work_queue_service import build_queue
from .ecomm_gtin_export_service import safe_gtin_candidates_for_pages

MAX_ROWS = 5000
HEADER = (
    "ecomm_id", "sku", "nombre_ecomm", "presentacion_ecomm",
    "gtin_excel_solo_busqueda", "busqueda_sugerida",
    "estado_fuente", "url_fabricante", "cita_fuente", "fecha_verificacion",
)


def _cell(value):
    """Prevent CSV formula injection and control-character confusion in Excel."""
    result = " ".join(str(value or "").split())[:500]
    if result.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + result
    return result


def build_research_manifest(db):
    # Both computations validate the *entire* API capture and Excel ID+SKU map.
    pages = EcommApiProductWorkspace(db)._source_pages()
    candidates = safe_gtin_candidates_for_pages(db, pages)
    work = build_queue(db, filter_name="research_gtin_unique", export_rows=True)
    rows = work["items"]
    if len(rows) > MAX_ROWS:
        raise ValueError("Lote superior a 5.000 variantes; se requiere dividirlo antes de exportar.")

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(HEADER)
    for row in sorted(rows, key=lambda r: (r["sku"].casefold(), r["ecomm_id"])):
        ident = row["ecomm_id"]
        gtin = candidates.get(ident)
        source = row["source"]
        if (
            not gtin
            or row["is_combo"]
            or row["identity_issue"]
            or not source.get("product_name")
            or not source.get("variant_description")
        ):
            raise ValueError("La captura de investigación cambió; actualizá el listado antes de exportar.")
        name = _cell(source["product_name"])
        presentation = _cell(source["variant_description"])
        writer.writerow((
            _cell(ident),
            _cell(row["sku"]),
            name,
            presentation,
            gtin,  # A validated lookup hint; never an official API EAN.
            _cell(f'"{name}" "{presentation}" {gtin} fabricante'),
            "PENDIENTE_VERIFICACION_FABRICANTE",
            "", "", "",
        ))
    # UTF-8 BOM for Argentina/Excel. Nothing is written to the database.
    return "\ufeff" + output.getvalue(), len(rows)
