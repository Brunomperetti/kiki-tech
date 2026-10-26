"""Conservative, read-only candidate discovery for Tiendanube SKU mismatches."""
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone
from sqlalchemy import select

from ..database.models import TiendanubeMatchDecision

from .tiendanube_api_catalog_service import TiendanubeApiCatalogService
from ..integrations.ecomm_app.catalog_stage import STAGE_SOURCE


def normalize(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def numbers(value):
    return set(re.findall(r"\d+(?:[.,]\d+)?", normalize(value)))


# Only explicit, recognizable product attributes can rule out a candidate.
# Unknown attributes are not assumed to match.
FLAVOR_TERMS = {
    "vainilla": ("vainilla", "vanilla"),
    "chocolate": ("chocolate", "choco"),
    "frutilla": ("frutilla", "fresa", "strawberry"),
    "limon": ("limon", "lemon"),
    "naranja": ("naranja", "orange"),
    "menta": ("menta", "mint"),
    "coco": ("coco", "coconut"),
    "manzana": ("manzana", "apple"),
    "durazno": ("durazno", "peach"),
}
UNITS = {"g", "gr", "grs", "gramos", "kg", "ml", "cc", "l", "litros",
         "capsula", "capsulas", "caps", "cap",
         "comprimido", "comprimidos", "tableta", "tabletas"}

def product_flavors(*values):
    words = set(normalize(" ".join(str(v or "") for v in values)).split())
    # For SKU strings without separators, only detect well-known flavor
    # words when they occur as a suffix; do not match arbitrary substrings.
    sku_compact = normalize(str(values[-1] or "")).replace(" ", "") if values else ""
    return {flavor for flavor, aliases in FLAVOR_TERMS.items()
            if any(alias in words or sku_compact.endswith(alias) for alias in aliases)}

def pack_units(value):
    normalized = normalize(value)
    # Some supplier titles write amounts without spaces: "485g", "180caps".
    normalized = re.sub(
        r"(\d+)(g|gr|grs|gramos|kg|ml|cc|l|litros|capsula|capsulas|caps|cap|comprimido|comprimidos|tableta|tabletas)\b",
        r"\1 \2",
        normalized,
    )
    tokens = re.sub(r"\bx(?=\d)", "x ", normalized).split()
    units = []
    for i, token in enumerate(tokens[1:], start=1):
        if token in UNITS and re.fullmatch(r"\d+", tokens[i-1]):
            unit = ("g" if token in {"gr", "grs", "gramos"} else
                    "ml" if token == "cc" else "l" if token == "litros" else
                    "capsulas" if token in {"capsula", "capsulas", "caps", "cap"} else
                    "comprimidos" if token in {"comprimido", "comprimidos"} else
                    "tabletas" if token in {"tableta", "tabletas"} else token)
            units.append((int(tokens[i-1]), unit))
    return set(units)

def variant_conflict(source_name, source_sku, target_name, target_sku):
    source_flavors = product_flavors(source_name, source_sku)
    target_flavors = product_flavors(target_name, target_sku)
    if source_flavors and target_flavors and source_flavors.isdisjoint(target_flavors):
        return True
    source_units, target_units = pack_units(source_name), pack_units(target_name)
    if source_units and target_units and source_units != target_units:
        return True
    return False


class TiendanubeAssistedMatchService:
    def __init__(self, db):
        self.catalog = TiendanubeApiCatalogService(db)

    def report(self):
        existing = self.catalog.report()
        if not existing["available"]:
            return {"available": False, "items": [], "summary": {}}
        # Only use variants of the completed API capture. No historical
        # Ecomm Excel brands, aliases or parent SKU families are candidates.
        api_pages = self.catalog.repo.snapshot(STAGE_SOURCE)
        ecomm = []
        used_skus = {}
        for page in api_pages:
            for parent in page.get("items") or []:
                for variant in parent.get("variants") or []:
                    if not isinstance(variant, dict) or variant.get("invalid"):
                        continue
                    if variant.get("is_combo") is True or parent.get("is_combo") is True:
                        continue
                    ident, sku = variant.get("id"), variant.get("sku")
                    if ident is None or not isinstance(sku, str) or not sku.strip():
                        continue
                    name = str(parent.get("description") or variant.get("description") or "").strip()
                    if not name:
                        continue
                    item = {"ecomm_id": str(ident), "sku": sku, "name": name,
                            "brand": "", "source": STAGE_SOURCE}
                    ecomm.append(item)
                    used_skus[sku.casefold()] = used_skus.get(sku.casefold(), 0) + 1
        # Ambiguous Ecomm SKUs cannot support recommendations.
        ecomm = [item for item in ecomm
                 if used_skus[item["sku"].casefold()] == 1]
        decisions = {row.source_key: row for row in self.catalog.repo.db.scalars(select(TiendanubeMatchDecision)).all()}
        candidates = []
        for item in existing["items"]:
            if item["status"] != "UNMATCHED_SKU":
                continue
            source_name = normalize(item["name"])
            source_brand = normalize(item["brand"])
            if not source_name or len(source_name) < 9:
                continue
            proposed = []
            for target in ecomm:
                target_name = normalize(target.get("name"))
                if not target_name:
                    continue
                target_brand = normalize(target.get("brand"))
                if source_brand and target_brand and source_brand != target_brand:
                    continue
                if variant_conflict(item["name"], item["sku"], target.get("name"),
                                    target.get("sku_effective") or target.get("sku")):
                    continue
                # Different quantities/packs never become a high-confidence match.
                if numbers(item["name"]) != numbers(target.get("name")):
                    continue
                score = SequenceMatcher(None, source_name, target_name).ratio()
                if score < 0.85:
                    continue
                proposed.append({
                    "ecomm_id": str(target.get("ecomm_id") or ""),
                    "sku": str(target.get("sku_effective") or target.get("sku") or ""),
                    "name": target.get("name") or "",
                    "brand": target.get("brand") or "",
                    "similarity": round(score, 3),
                    "confidence": "HIGH" if score >= 0.96 and source_brand and target_brand == source_brand else "MEDIUM",
                    "evidence": "Similitud de nombre; marca compatible; números de presentación coincidentes. Requiere verificación humana.",
                })
            proposed.sort(key=lambda x: (-x["similarity"], x["ecomm_id"]))
            key = f"{item['slug']}|{item['sku']}"
            decision = decisions.get(key)
            candidates.append({
                "source_key": key,
                "decision": {"status": decision.status, "target_ecomm_id": decision.target_ecomm_id, "note": decision.note, "history": decision.history} if decision else None,
                "tiendanube_sku": item["sku"],
                "tiendanube_name": item["name"],
                "tiendanube_brand": item["brand"],
                "tiendanube_slug": item["slug"],
                "candidates": proposed[:3],
                "status": "REVIEW_REQUIRED" if proposed else "NO_SAFE_CANDIDATE",
            })
        return {
            "available": True,
            "summary": {
                "sku_unmatched": existing["summary"].get("UNMATCHED_SKU", 0),
                "with_proposals": sum(bool(x["candidates"]) for x in candidates),
                "without_proposals": sum(not x["candidates"] for x in candidates),
            },
            "items": candidates,
            "policy": "Candidatos desde captura Ecomm-App API completa y Tiendanube CSV. Sin Excel Ecomm, sin marca inferida y sin aprobación automática. No se infiere EAN ni se publica.",
        }

    def decide(self, source_key: str, target_ecomm_id: str | None, status: str, note: str):
        if status not in {"APPROVED", "REJECTED"}:
            raise ValueError("Decisión inválida.")
        if len((note or "").strip()) < 10:
            raise ValueError("El motivo debe contener al menos 10 caracteres.")
        report = self.report()
        item = next((entry for entry in report["items"] if entry["source_key"] == source_key), None)
        if item is None:
            raise ValueError("El producto ya no pertenece a los pendientes de conciliación.")
        candidate = next(
            (c for c in item["candidates"] if c["ecomm_id"] == target_ecomm_id), None
        ) if target_ecomm_id else None
        if status == "APPROVED" and (not candidate or not target_ecomm_id):
            raise ValueError("Solo se puede aprobar una propuesta vigente con ID Ecomm válido.")
        if status == "REJECTED" and target_ecomm_id:
            raise ValueError("El rechazo no debe asignar un producto de Ecomm.")
        now = datetime.now(timezone.utc)
        db = self.catalog.repo.db
        record = db.scalar(select(TiendanubeMatchDecision).where(
            TiendanubeMatchDecision.source_key == source_key
        ))
        if record is None:
            record = TiendanubeMatchDecision(source_key=source_key, history=[])
            db.add(record)
        source_snapshot = {
            "sku": item["tiendanube_sku"],
            "slug": item["tiendanube_slug"],
            "name": item["tiendanube_name"],
            "brand": item["tiendanube_brand"],
        }
        event = {
            "at": now.isoformat(), "status": status,
            "target_ecomm_id": target_ecomm_id, "note": note.strip(),
            "source": source_snapshot, "target": candidate or {},
        }
        record.status = status
        record.target_ecomm_id = target_ecomm_id if status == "APPROVED" else None
        record.source_snapshot = source_snapshot
        record.target_snapshot = candidate or {}
        record.note = note.strip()
        record.history = [*(record.history or []), event][-100:]
        record.updated_at = now
        db.commit()
        return {"status": status, "source_key": source_key, "history_count": len(record.history)}
    def bulk_preview(self, source_keys: list[str]):
        if not source_keys or len(source_keys) > 50 or len(set(source_keys)) != len(source_keys):
            raise ValueError("Seleccioná entre 1 y 50 productos diferentes.")
        by_key = {x["source_key"]: x for x in self.report()["items"]}
        selection = []
        for key in source_keys:
            item = by_key.get(key)
            if not item:
                raise ValueError("Hay productos que ya no están pendientes. Actualizá la revisión.")
            if item["decision"] is not None:
                raise ValueError("Hay decisiones previas. Revisalas individualmente antes de cambiarlas.")
            selection.append(item)
        return {"count": len(selection), "items": [
            {"source_key": x["source_key"], "name": x["tiendanube_name"],
             "sku": x["tiendanube_sku"], "candidate_count": len(x["candidates"])}
            for x in selection
        ], "action": "REJECTED", "policy": "No se crea vínculo ni se modifica ningún catálogo externo."}

    def bulk_reject(self, source_keys: list[str], note: str):
        if len((note or "").strip()) < 10:
            raise ValueError("Ingresá un motivo de al menos 10 caracteres.")
        preview = self.bulk_preview(source_keys)
        db = self.catalog.repo.db
        current = {x["source_key"]: x for x in self.report()["items"]}
        existing = set(db.scalars(select(TiendanubeMatchDecision.source_key).where(
            TiendanubeMatchDecision.source_key.in_(source_keys))).all())
        if existing:
            raise ValueError("Hay decisiones anteriores para estos productos. Actualizá la revisión.")
        now = datetime.now(timezone.utc)
        for key in source_keys:
            item = current[key]
            source = {"sku": item["tiendanube_sku"], "slug": item["tiendanube_slug"],
                      "name": item["tiendanube_name"], "brand": item["tiendanube_brand"]}
            event = {"at": now.isoformat(), "status": "REJECTED", "target_ecomm_id": None,
                     "note": note.strip(), "source": source, "target": {}}
            db.add(TiendanubeMatchDecision(
                source_key=key, status="REJECTED", target_ecomm_id=None,
                source_snapshot=source, target_snapshot={}, note=note.strip(),
                history=[event], updated_at=now,
            ))
        db.commit()
        return {"updated": preview["count"], "status": "REJECTED",
                "policy": "Solo decisiones internas; sin cambios en Tiendanube, Ecomm o ML."}
