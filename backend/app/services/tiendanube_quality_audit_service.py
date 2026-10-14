"""Conservative catalog completeness audit for imported Tiendanube snapshots."""
from collections import Counter
from html import unescape
import re

from .tiendanube_csv_service import TiendanubeCsvService


def gtin_status(raw):
    text = str(raw or "").strip()
    if not text:
        return "MISSING"
    # An Excel-like suffix must be investigated, never silently repaired.
    if not text.isdigit() or len(text) not in {8, 12, 13, 14}:
        return "UNVERIFIED_FORMAT"
    digits = [int(x) for x in text]
    expected = (10 - sum(digit * (3 if index % 2 == 0 else 1)
                         for index, digit in enumerate(reversed(digits[:-1]))) % 10) % 10
    return "VALID_CHECK_DIGIT" if expected == digits[-1] else "INVALID_CHECK_DIGIT"


class TiendanubeQualityAuditService:
    def __init__(self, db):
        self.catalog = TiendanubeCsvService(db)

    def report(self):
        rows = self.catalog.repo.snapshot("TIENDANUBE")
        if not rows:
            return {"available": False, "summary": {}, "items": []}
        raw_counts = Counter(str(row.get("ean_raw") or "").strip() for row in rows
                             if str(row.get("ean_raw") or "").strip())
        grouped = {}
        for row in rows:
            identity = str(row.get("slug") or "").strip() or "SKU:" + str(row.get("sku") or "")
            grouped.setdefault(identity, []).append(row)
        items = []
        for identity, members in grouped.items():
            first = members[0]
            issues = []
            if not any(str(x.get("brand") or "").strip() for x in members):
                issues.append("BRAND_MISSING")
            if not any(str(x.get("category") or "").strip() for x in members):
                issues.append("CATEGORY_MISSING")
            if not any(x.get("description_present") for x in members):
                issues.append("DESCRIPTION_MISSING")
            if not any(str(x.get("sku") or "").strip() for x in members):
                issues.append("SKU_MISSING")
            gtin_states = [gtin_status(x.get("ean_raw")) for x in members]
            if all(x == "MISSING" for x in gtin_states):
                issues.append("GTIN_MISSING")
            elif any(x in {"UNVERIFIED_FORMAT", "INVALID_CHECK_DIGIT"} for x in gtin_states):
                issues.append("GTIN_NEEDS_REVIEW")
            if any(raw_counts[str(x.get("ean_raw") or "").strip()] > 1
                   for x in members if str(x.get("ean_raw") or "").strip()):
                issues.append("GTIN_REPEATED")
            # Image file is exported separately; do not call images missing.
            items.append({"key": identity, "name": first.get("name") or "",
                          "sku": first.get("sku") or "", "variant_rows": len(members),
                          "issues": issues, "priority": "HIGH" if any(
                              x in issues for x in ("SKU_MISSING", "GTIN_NEEDS_REVIEW", "GTIN_REPEATED")
                          ) else "REVIEW" if issues else "NO_ISSUES_DETECTED",
                          "image_status": "NOT_EVALUATED",
                          "gtin_validation": "El dígito verificador no confirma autenticidad, identidad ni titularidad."})
        counts = Counter(issue for item in items for issue in item["issues"])
        return {"available": True, "summary": {"products": len(items),
                "requiring_review": sum(bool(x["issues"]) for x in items),
                "no_issues_detected": sum(not x["issues"] for x in items),
                **dict(counts)}, "items": items,
                "policy": "Diagnóstico solo lectura. Imágenes no evaluadas sin importar el CSV de imágenes. GTIN con formato correcto requiere fuente verificable. Las excepciones de marca deben resolverse por separado."}
