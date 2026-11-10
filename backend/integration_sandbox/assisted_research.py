"""Discovery orchestration reusing Dossier history, 2G ingester, 2F and 2D."""

import base64
from copy import deepcopy
import hashlib
import json
import socket
import struct
from sqlalchemy import select
from app.database.models import EcommApiProductEdit
from uuid import uuid4
from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
from .research.service import Research, now, fact_digest
from .research.storage import digest
from .local_documents import LocalDocuments, parse_local
from .document_routes import Incorporate

SOCKET = "/discovery-collector/collector.sock"
EVENTS = {
    "ASSISTED_DISCOVERY",
    "ASSISTED_DECISION",
    "ASSISTED_TRANSFER",
    "ASSISTED_STALE",
}


def collector(operation, **payload):
    request = json.dumps(
        {"operation": operation, **payload}, ensure_ascii=False
    ).encode()
    if len(request) > 16384:
        raise ValueError("Consulta de investigación demasiado grande.")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(8)
            connection.connect(SOCKET)
            connection.sendall(struct.pack("!I", len(request)) + request)
            with connection.makefile("rb") as stream:
                size = struct.unpack("!I", stream.read(4))[0]
                if not 0 < size <= 750000:
                    raise ValueError
                response = json.loads(stream.read(size))
    except (OSError, ValueError, struct.error):
        raise ValueError(
            "Recolector simulado no disponible; no se utilizó Internet ni otro destino."
        ) from None
    if (
        not response.get("ok")
        or response.get("simulated") is not True
        or response.get("network_enabled") is not False
    ):
        raise ValueError(
            "El recolector no acredita un resultado exclusivamente simulado."
        )
    return response["result"]


def query_context(research, item):
    workspace = EcommApiProductWorkspace(research.db).get(item.ecomm_id)
    source, fields = workspace["source"], workspace["fields"]
    facts = [
        f
        for f in item.facts
        if f["ecomm_id"] == item.ecomm_id
        and f["state"] == "APPROVED"
        and not research.blockers(item, f)
    ]
    provenance = {}
    query = {
        "ecomm_id": item.ecomm_id,
        "name": source["product_name"] or None,
        "presentation": source["variant_description"] or None,
        "is_combo": source["is_combo"],
        "ean": source["gtin"] or fields.get("proposed_gtin") or None,
    }
    provenance.update(
        name="Captura Ecomm-App de pruebas",
        presentation="Captura Ecomm-App de pruebas",
        is_combo="Captura Ecomm-App de pruebas",
        ean="Captura Ecomm-App de pruebas"
        if source["gtin"]
        else "Propuesta KIKI no verificada"
        if fields.get("proposed_gtin")
        else "No disponible",
    )
    for key in ("brand", "manufacturer", "net_weight"):
        fact = next((f for f in facts if f["field"] == key), None)
        manual = (
            fields.get(key)
            if key != "net_weight"
            else next(
                (
                    a["value"]
                    for a in fields["attributes"]
                    if a["name"].casefold() == "contenido neto"
                ),
                None,
            )
        )
        query[key] = (
            (fact["value"] + (" " + fact["unit"] if fact["unit"] else ""))
            if fact
            else manual or None
        )
        provenance[key] = (
            "Evidencia aprobada vigente"
            if fact
            else "Edición KIKI no verificada"
            if manual
            else "No disponible en captura ni ficha"
        )
    snapshot = {
        "query": query,
        "workspace_version": workspace["version"],
        "identity_hash": item.identity_digest,
        "approved_versions": sorted(
            (f["id"], f["version"], fact_digest(f)) for f in facts
        ),
    }
    return {
        **snapshot,
        "provenance": provenance,
        "hash": digest(snapshot),
        "missing": [k for k, v in query.items() if v is None],
    }


def evaluate(query, hint):
    comparisons = {}
    for key in (
        "ean",
        "brand",
        "manufacturer",
        "name",
        "presentation",
        "net_weight",
        "is_combo",
    ):
        expected, actual = query.get(key), hint.get(key)
        status = (
            "UNKNOWN"
            if expected is None or actual is None
            else "MATCH"
            if str(expected).strip().casefold() == str(actual).strip().casefold()
            else "MISMATCH"
        )
        comparisons[key] = {"expected": expected, "found": actual, "status": status}
    return comparisons


def latest_run(item):
    return next(
        (
            deepcopy(event["detail"])
            for event in reversed(item.history)
            if event["action"] in EVENTS
        ),
        None,
    )


def assisted_view(research, item):
    run = latest_run(item)
    if not run:
        return None
    context = query_context(research, item)
    current = (
        context["hash"] == run["query_context"]["hash"] and run["state"] != "STALE"
    )
    if not current and run["state"] != "STALE":
        run["state"] = "STALE"
        run["stale_reason"] = (
            "La ficha, identidad o evidencias aprobadas cambiaron; iniciá otra investigación antes de incorporar fuentes."
        )
        research.commit_change(item, deepcopy(item.facts), "ASSISTED_STALE", run)
    return {
        **run,
        "current": current,
        "simulated_only": True,
        "network_enabled": False,
        "current_query": context,
    }


class AssistedResearch:
    def __init__(self, db, session):
        self.db, self.session = db, session
        self.research = Research(db, session)

    def case(self, ident, expected):
        item = self.research.dossier(ident)
        self.research.expect(item, expected)
        return item

    def run(self, item, run_id):
        run = latest_run(item)
        if (
            not run
            or run["run_id"] != run_id
            or run["state"] == "STALE"
            or query_context(self.research, item)["hash"]
            != run["query_context"]["hash"]
        ):
            raise ValueError(
                "Investigación desactualizada o de otra variante; no se aplicó una decisión antigua."
            )
        return run

    def start(self, ident, expected, workspace_version):
        item = self.case(ident, expected)
        context = query_context(self.research, item)
        if context["workspace_version"] != workspace_version:
            raise ValueError(
                "La ficha cambió; recuperá su versión actual antes de investigar."
            )
        if len([e for e in item.history if e["action"] == "ASSISTED_DISCOVERY"]) >= 10:
            raise ValueError(
                "Límite de diez investigaciones por variante en este entorno descartable."
            )
        # No live HTTP: the separate worker only interprets authored HTTP fixtures.
        result = collector("discover", query=context["query"])
        run_id = uuid4().hex[:24]
        candidates = []
        for source in result["candidates"]:
            comparisons = evaluate(context["query"], source["identity_hint"])
            candidates.append(
                {
                    **source,
                    "id": digest({"run": run_id, "source": source["source_id"]})[:24],
                    "version": 1,
                    "decision": "PENDING",
                    "comparisons": comparisons,
                    "identity_state": "MISMATCH"
                    if any(x["status"] == "MISMATCH" for x in comparisons.values())
                    else "INCOMPLETE"
                    if any(x["status"] == "UNKNOWN" for x in comparisons.values())
                    else "COMPATIBLE_PENDING_REVIEW",
                    "provenance_state": "SIMULATED_UNCHECKED",
                    "history": [],
                    "document_id": None,
                }
            )
        run = {
            "run_id": run_id,
            "ecomm_id": ident,
            "state": "CANDIDATES",
            "created_at": now(),
            "actor": self.research.actor,
            "query_context": context,
            "candidates": sorted(candidates, key=lambda c: (c["priority"], c["id"])),
            "search_trace": result["trace"],
        }
        self.research.commit_change(
            item, deepcopy(item.facts), "ASSISTED_DISCOVERY", run
        )
        return self.research.serialize(item)

    def decision(self, ident, body, candidate_id):
        item = self.case(ident, body.expected_version)
        run = self.run(item, body.run_id)
        candidate = next(
            (c for c in run["candidates"] if c["id"] == candidate_id), None
        )
        if (
            not candidate
            or candidate["version"] != body.expected_candidate_version
            or candidate["document_id"]
        ):
            raise ValueError("La fuente candidata cambió o ya fue incorporada.")
        if len(body.reason.strip()) < 10:
            raise ValueError("Registrá un motivo de selección o rechazo.")
        candidate["decision"] = body.decision
        candidate["version"] += 1
        candidate["history"].append(
            {
                "at": now(),
                "actor": self.research.actor,
                "decision": body.decision,
                "reason": body.reason.strip(),
                "version": candidate["version"],
            }
        )
        self.research.commit_change(
            item, deepcopy(item.facts), "ASSISTED_DECISION", run
        )
        return self.research.serialize(item)

    def acquire(self, ident, body, candidate_id):
        item = self.case(ident, body.expected_version)
        run = self.run(item, body.run_id)
        candidate = next(
            (c for c in run["candidates"] if c["id"] == candidate_id), None
        )
        if (
            not candidate
            or candidate["version"] != body.expected_candidate_version
            or candidate["decision"] != "SELECTED"
            or candidate["document_id"]
        ):
            raise ValueError(
                "Seleccioná una fuente vigente antes de incorporar su documento."
            )
        self.db.commit()  # release DB locks during the bounded collector/parser RPCs
        artifact = collector("retrieve", source_id=candidate["source_id"])
        trace = artifact["trace"]
        raw = base64.b64decode(artifact["content_base64"], validate=True)
        if (
            trace["simulated"] is not True
            or trace["network_enabled"] is not False
            or hashlib.sha256(raw).hexdigest() != trace["sha256"]
        ):
            raise ValueError("Transferencia documental no íntegra o no simulada.")
        imported = Incorporate(
            kind="FILE",
            expected_version=body.expected_version,
            filename=artifact["filename"],
            content_type=trace["content_type"],
            content_base64=artifact["content_base64"],
            provenance_note="Transferencia controlada de fuente HTTP simulada. No es documentación auténtica de fabricante.",
            reference_url=trace["final_url"],
            declared_official=candidate["declared_official"],
            authorized_local_processing=True,
        )
        parsed = parse_local(imported)
        self.db.expire_all()
        final = AssistedResearch(self.db, self.session)
        refreshed = final.case(ident, body.expected_version)
        self.db.scalar(
            select(EcommApiProductEdit)
            .where(EcommApiProductEdit.ecomm_id == ident)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        latest = final.run(refreshed, body.run_id)
        fresh = next(c for c in latest["candidates"] if c["id"] == candidate_id)
        if fresh["version"] != body.expected_candidate_version:
            raise ValueError("La selección cambió durante la lectura.")
        return LocalDocuments(self.db, self.session).incorporate(
            ident,
            imported,
            parsed,
            acquisition={
                "trace": trace,
                "run_snapshot": latest,
                "candidate_id": candidate_id,
            },
        )
