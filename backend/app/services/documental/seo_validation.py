"""Editor limits and source-cited copy validation; no model or network client."""

from app.services.ecomm_api_product_workspace_service import ARRAY_LIMITS, TEXT_LIMITS


def field_limits(field, value):
    """Use the real editor contract, not an invented SEO completeness score."""
    maximum = TEXT_LIMITS.get(field, ARRAY_LIMITS.get(field))
    if maximum is None:
        raise ValueError("Campo comercial desconocido.")
    text = field in TEXT_LIMITS
    valid_type = isinstance(value, str) if text else isinstance(value, list)
    length = len(value) if valid_type else 0
    reasons = []
    if not valid_type:
        reasons.append("El valor no tiene el formato admitido por el editor.")
    elif length > maximum:
        reasons.append(
            f"Supera el máximo de {maximum} {'caracteres' if text else 'elementos'} del editor."
        )
    if not text and valid_type:
        specs = {
            "attributes": {"name": 90, "value": 450},
            "media": {"url": 1000, "alt": 180, "source_url": 1000, "kind": 5},
            "sources": {"name": 180, "url": 1000, "note": 500, "kind": 20},
        }
        for row in value:
            if not isinstance(row, dict) or any(
                not isinstance(row.get(key, ""), str) or len(row.get(key, "")) > size
                for key, size in specs[field].items()
            ):
                reasons.append(
                    "Un elemento contiene valores inválidos o supera sus límites."
                )
                break
    return {
        "maximum": maximum,
        "length": length,
        "unit": "characters" if text else "items",
        "valid": not reasons,
        "reasons": reasons,
    }


def matches_documented_copy(field, value, generated):
    """Reuse exactly the existing proposal editor's factual-clause rules."""
    from .proposals import Proposals

    if not generated or not generated.get("evidence_ids"):
        return False
    try:
        Proposals.validate_edit(field, value, generated)
    except (ValueError, KeyError, TypeError):
        return False
    return True
