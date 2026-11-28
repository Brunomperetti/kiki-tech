"""Internal, human-reviewed taxonomy versions in existing snapshot persistence.

This vocabulary contains no products and is not an external category registry.
Changing a version invalidates dependent suggestions; no fiche/provider writes.
"""

from copy import deepcopy
import json
import re

from sqlalchemy import select

from app.core.config import get_settings
from app.database.models import CatalogSnapshot
from .storage import Control, digest

SOURCE = "KIKI_TAXONOMY"
MAX_ITEMS = 1000
MAX_BYTES = 5 * 1024 * 1024
CHANNELS = {"ECOMM", "ML", "TN"}


def _label(value, limit=160):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise ValueError("Nombre o versión de clasificación inválido.")
    return " ".join(value.split())


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("Identificador de clasificación inválido.")
    return value


def normalize_catalog(entries, mappings):
    if (
        not isinstance(entries, list)
        or not 1 <= len(entries) <= MAX_ITEMS
        or not isinstance(mappings, list)
        or len(mappings) > MAX_ITEMS
    ):
        raise ValueError(
            "El vocabulario admite entre 1 y 1.000 pares y hasta 1.000 equivalencias."
        )
    pairs, seen_labels = {}, set()
    for row in entries:
        if not isinstance(row, dict) or set(row) != {
            "id",
            "category",
            "subcategory",
            "state",
        }:
            raise ValueError("Par de clasificación incompleto.")
        ident = _id(row["id"])
        category, subcategory = _label(row["category"]), _label(row["subcategory"])
        key = (category.casefold(), subcategory.casefold())
        if (
            ident in pairs
            or key in seen_labels
            or row["state"] not in {"ACTIVE", "RETIRED"}
        ):
            raise ValueError("Par repetido o estado de clasificación inválido.")
        pairs[ident] = {
            "id": ident,
            "category": category,
            "subcategory": subcategory,
            "state": row["state"],
        }
        seen_labels.add(key)
    links, seen_links = {}, set()
    for row in mappings:
        if not isinstance(row, dict) or set(row) != {
            "id",
            "pair_id",
            "channel",
            "category",
            "subcategory",
            "state",
        }:
            raise ValueError(
                "Equivalencia de canal incompleta; no se admiten IDs externos inventados."
            )
        ident, pair_id = _id(row["id"]), _id(row["pair_id"])
        key = (pair_id, row["channel"])
        if (
            ident in links
            or pair_id not in pairs
            or key in seen_links
            or row["channel"] not in CHANNELS
            or row["state"] not in {"ACTIVE", "RETIRED"}
            or (row["state"] == "ACTIVE" and pairs[pair_id]["state"] != "ACTIVE")
        ):
            raise ValueError(
                "Equivalencia duplicada, ambigua o sin par interno activo."
            )
        links[ident] = {
            "id": ident,
            "pair_id": pair_id,
            "channel": row["channel"],
            "category": _label(row["category"]),
            "subcategory": _label(row["subcategory"]),
            "state": row["state"],
        }
        seen_links.add(key)
    return sorted(pairs.values(), key=lambda r: r["id"]), sorted(
        links.values(), key=lambda r: r["id"]
    )


def catalog_state(db):
    row = db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source == SOURCE))
    if row is None:
        return {
            "version": 0,
            "revision": "",
            "entries": [],
            "mappings": [],
            "fingerprint": digest({"version": 0, "entries": [], "mappings": []}),
            "history": [],
            "external_category_ids_verified": False,
            "external_writes_enabled": False,
        }
    if (
        not isinstance(row.payload, list)
        or len(row.payload) != 1
        or not isinstance(row.payload[0], dict)
    ):
        raise ValueError(
            "Vocabulario interno inválido; no se reemplaza silenciosamente."
        )
    result = deepcopy(row.payload[0])
    core = {key: result[key] for key in ("version", "revision", "entries", "mappings")}
    if result.get("fingerprint") != digest(core):
        raise ValueError("La integridad del vocabulario interno requiere revisión.")
    result.update(external_category_ids_verified=False, external_writes_enabled=False)
    return result


def selected_pair(catalog, pair_id, channel="KIKI", mapping_id=None):
    pair = next(
        (
            p
            for p in catalog["entries"]
            if p["id"] == pair_id and p["state"] == "ACTIVE"
        ),
        None,
    )
    if pair is None:
        raise ValueError("El par interno no existe o fue retirado; requiere revisión.")
    target = pair
    if channel != "KIKI":
        target = next(
            (
                m
                for m in catalog["mappings"]
                if m["id"] == mapping_id
                and m["pair_id"] == pair_id
                and m["channel"] == channel
                and m["state"] == "ACTIVE"
            ),
            None,
        )
        if target is None:
            raise ValueError(
                "No existe equivalencia explícita y activa para este canal."
            )
    return {"category": pair["category"], "subcategory": pair["subcategory"]}, {
        "category": target["category"],
        "subcategory": target["subcategory"],
    }


class TaxonomyCatalog:
    def __init__(self, db, session):
        self.db, self.session = db, session

    def get(self):
        return catalog_state(self.db)

    def save(self, *, expected_version, revision, entries, mappings, reason):
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Versión de vocabulario inválida.")
        revision, reason = _label(revision, 100), _label(reason, 600)
        if len(reason) < 20:
            raise ValueError("Documentá la revisión humana con al menos 20 caracteres.")
        entries, mappings = normalize_catalog(entries, mappings)
        if (
            self.db.scalar(select(Control).where(Control.id == 1).with_for_update())
            is None
        ):
            raise ValueError("Falta el control documental; clasificación bloqueada.")
        row = self.db.scalar(
            select(CatalogSnapshot)
            .where(CatalogSnapshot.source == SOURCE)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        previous = catalog_state(self.db)
        if previous["version"] != expected_version:
            raise ValueError(
                "El vocabulario cambió en otra sesión; recuperá la versión nueva."
            )
        if previous["version"] and previous["revision"] == revision:
            raise ValueError("Un cambio requiere un identificador de revisión nuevo.")
        current = {
            "version": expected_version + 1,
            "revision": revision,
            "entries": entries,
            "mappings": mappings,
        }
        current["fingerprint"] = digest(current)
        from .research import now

        current["history"] = previous.get("history", []) + [
            {
                "at": now(),
                "actor": f"{get_settings().kiki_admin_username} · sesión {self.session.id}",
                "reason": reason,
                "version": current["version"],
                "revision": revision,
                "previous_fingerprint": previous["fingerprint"],
                "fingerprint": current["fingerprint"],
                "entries": deepcopy(entries),
                "mappings": deepcopy(mappings),
                "review_kind": "HUMAN_EXPLICIT",
            }
        ]
        if len(json.dumps(current, ensure_ascii=False).encode()) > MAX_BYTES:
            raise ValueError(
                "El vocabulario y su historial superan 5 MiB; no se guardó parcialmente."
            )
        if row is None:
            row = CatalogSnapshot(source=SOURCE, payload=[current])
            self.db.add(row)
        else:
            row.payload = [current]
        self.db.commit()
        return catalog_state(self.db)
