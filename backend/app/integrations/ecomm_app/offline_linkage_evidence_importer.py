from ..common.excel import ExcelImporter
from ...catalog.models import OfflineLinkageEvidenceRow
from ...catalog.normalizer import normalize_ean, normalize_sku


class OfflineLinkageEvidenceExcelImporter(ExcelImporter):
    """Import a compact offline evidence sheet for EDIMA linkage review."""

    source_label = "Evidencia offline EDIMA"
    required_any = {"external_id", "candidate_ecomm_id", "evidence_type"}
    aliases = {
        "external_id": {"ML ID", "Publicación ML", "Publicacion ML", "MLA"},
        "gtin": {"GTIN EDIMA", "GTIN", "EAN"},
        "title": {"Título EDIMA", "Titulo EDIMA", "Título", "Titulo"},
        "brand": {"Marca EDIMA", "Marca"},
        "historical_status": {"Estado histórico", "Estado historico"},
        "candidate_ecomm_id": {"ID interno candidato", "ID interno", "Ecomm ID candidato"},
        "candidate_product": {"Producto candidato", "Producto inventario relacionado"},
        "candidate_sku_product": {"SKU producto candidato", "SKU producto"},
        "candidate_sku_variant": {"SKU variante candidato", "SKU variante"},
        "evidence_type": {"Tipo evidencia", "Tipo de evidencia"},
        "recommendation": {"Recomendación", "Recomendacion"},
        "note": {"Observación", "Observacion", "Nota"},
    }

    def to_model(self, row, mapping):
        def get(key):
            return row[mapping[key]] if key in mapping else None

        def clean(value):
            if value is None:
                return None
            text = str(value).strip()
            return text if text and text.casefold() != "nan" else None

        external_id = normalize_sku(get("external_id"))
        return OfflineLinkageEvidenceRow(
            external_id=external_id or "",
            gtin=normalize_ean(get("gtin")),
            title=clean(get("title")),
            brand=clean(get("brand")),
            historical_status=clean(get("historical_status")),
            candidate_ecomm_id=normalize_sku(get("candidate_ecomm_id")),
            candidate_product=clean(get("candidate_product")),
            candidate_sku_product=normalize_sku(get("candidate_sku_product")),
            candidate_sku_variant=normalize_sku(get("candidate_sku_variant")),
            evidence_type=clean(get("evidence_type")),
            recommendation=clean(get("recommendation")),
            note=clean(get("note")),
        )

    def accept(self, model) -> bool:
        return bool(model.external_id)

    def report_warnings(self, records):
        candidates = sum(bool(record.candidate_ecomm_id) for record in records)
        unresolved = len(records) - candidates
        return [
            f"Evidencia offline: {candidates} filas con candidato Ecomm y {unresolved} sin candidato."
        ]
