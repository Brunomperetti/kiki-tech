"""Conservative, explanatory evidence warnings for generated commercial copy."""
import re
import unicodedata


COMMON_EDITORIAL_WORDS = {
    "de", "del", "la", "las", "el", "los", "y", "con", "para", "por", "en",
    "un", "una", "su", "sus", "producto", "presentacion", "marca",
}


def tokens(value: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    return set(re.findall(r"[a-z0-9]+", folded))


def audit_generated_copy(title: str, description: str, facts: list[dict]) -> dict:
    """Warnings only: word overlap can never certify manufacturer claims."""
    evidence = set()
    for fact in facts:
        evidence |= tokens(str(fact.get("value") or ""))
    output = tokens(" ".join((title, description)))
    unsupported_numbers = sorted(x for x in output if x.isdecimal() and x not in evidence)
    unsupported_words = sorted(x for x in output
                               if x not in evidence and x not in COMMON_EDITORIAL_WORDS
                               and not x.isdecimal())
    warnings = []
    if unsupported_numbers:
        warnings.append("La IA introdujo números no presentes en los datos de origen.")
    if unsupported_words:
        warnings.append("La IA introdujo términos que no figuran en los datos originales; revisalos.")
    if not description.strip():
        warnings.append("Descripción pendiente: faltan datos verificados para generar contenido.")
    return {
        "needs_review": bool(warnings),
        "unsupported_numbers": unsupported_numbers[:20],
        "unsupported_terms": unsupported_words[:20],
        "warnings": warnings,
        "policy": "Control preliminar de texto: no demuestra autenticidad ni autoriza publicar.",
    }
