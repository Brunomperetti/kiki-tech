"""Bounded review CSV from the existing Ecomm queue. Never imports or syncs data."""

import csv
import io

from .ecomm_api_work_queue_service import build_queue

MAX_EXPORT_BYTES = 10 * 1024 * 1024
STATES = {
    "all",
    "found",
    "pending",
    "verified",
    "candidates",
    "conflicts",
    "no_match",
    "insufficient",
}


def safe_cell(value):
    text = "" if value is None else str(value)
    if len(text) > 4096:
        raise ValueError(
            "Una celda supera 4.096 caracteres; no se generó una exportación parcial."
        )
    # Spreadsheet formula injection is possible even inside quoted CSV cells.
    if text.lstrip(" \t\r\n\v\f\ufeff").startswith(
        ("=", "+", "-", "@")
    ) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def export_differences(db, channel, state="no_match", query=""):
    if channel not in {"ml", "tn"} or state not in STATES:
        raise ValueError("Canal o lista de revisión inválida.")
    filter_name = (
        "all"
        if state == "all"
        else channel + "_found"
        if state == "found"
        else channel + "_pending_candidates"
        if state == "pending"
        else channel + "_comparison_" + state
    )
    data = build_queue(
        db, query=query, filter_name=filter_name, sort="capture", export_rows=True
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    headers = [
        "ecomm_id",
        "sku",
        "nombre_ecomm",
        "presentacion",
        "marca_referencia",
        "barcode",
        "gtin",
        "combo_variante",
        "canal_revisado",
        "estado_comparacion",
        "ml_ids",
        "ml_titulos",
        "tn_identificadores_url",
        "tn_titulos",
        "cantidad_candidatos",
        "candidatos_por_revisar",
        "candidatos_detallados",
        "detalle_truncado",
        "evidencia",
        "discrepancias",
        "bloqueos_revision",
        "captura_canal",
        "antiguedad_horas",
        "captura_vigente",
        "captura_completa_acreditada",
        "ausencia_publicacion_actual_acreditada",
        "siguiente_paso",
    ]
    writer.writerow(headers)
    size = len(output.getvalue().encode("utf-8")) + 3
    chunks = ["\ufeff" + output.getvalue()]
    for item in data["items"]:
        source, channel_data = item["source"], item["channel_coverage"][channel]
        candidates = channel_data.get("candidates", [])

        def join(channel_key, key):
            return " | ".join(
                str(c.get(key) or "")
                for c in item["channel_coverage"][channel_key].get("candidates", [])
            )

        fields = [
            item["ecomm_id"],
            item["sku"],
            item["product_name"],
            source.get("variant_description"),
            item["proposed_brand"]
            or item["channel_coverage"].get("identity", {}).get("brand"),
            source.get("barcode"),
            source.get("gtin_raw"),
            source.get("is_combo"),
            channel,
            channel_data["comparison_state"],
            join("ml", "id"),
            join("ml", "title"),
            join("tn", "slug"),
            join("tn", "title"),
            channel_data["candidates_total"],
            channel_data["pending_candidates_count"],
            len(candidates),
            channel_data["candidates_truncated"],
            " | ".join(
                sorted({r for c in candidates for r in c.get("match_reasons", [])})
            ),
            " | ".join(
                sorted({r for c in candidates for r in c.get("discrepancies", [])})
            ),
            " | ".join(sorted({r for c in candidates for r in c.get("blockers", [])})),
            channel_data["snapshot_at"],
            channel_data["freshness"]["age_hours"],
            channel_data["freshness"]["fresh"],
            "NO_ACREDITADA",
            "NO_ACREDITADA",
            "No encontrado en esta captura; revisar vigencia, alcance e identidad antes de crear publicaciones."
            if channel_data["comparison_state"] == "no_match"
            else "Revisar candidatos e identidad; no aprobar automáticamente.",
        ]
        output.seek(0)
        output.truncate(0)
        writer.writerow([safe_cell(value) for value in fields])
        chunk = output.getvalue()
        size += len(chunk.encode("utf-8"))
        if size > MAX_EXPORT_BYTES:
            raise ValueError(
                "El CSV supera 10 MiB; acotá la búsqueda. No se generó una exportación parcial."
            )
        chunks.append(chunk)
    return "".join(chunks).encode("utf-8"), data["total"]
