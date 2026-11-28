"""Explicit, idempotent TN content dispatch using the existing import-job ledger.

No background executor, DDL, token refresh or implicit retries. A durable RUNNING
receipt is committed before the single external write; lost/uncertain responses
remain UNKNOWN for human reconciliation, including a process crash. Stock,
prices, external categories, media and visibility changes are never sent.
"""
from copy import deepcopy
from html import escape
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from uuid import UUID

from sqlalchemy import select, update, func, or_

from app.database.models import ImportJobRecord
from app.integrations.tiendanube.client import TiendanubeClient, TiendanubeError, _id
from app.services.commercial_channel_export_service import preview_commercial_export
from app.services.tiendanube_catalog_capture import _record, read_catalog
from app.services.tiendanube_publication_preview import normalized_sku
from app.services.tiendanube_assisted_match_service import normalize, variant_conflict
from app.services.ecomm_api_channel_evidence import quantity
from app.services.ecomm_api_product_workspace_service import _gtin_check_digit_valid

SOURCE = "TN_CONTROLLED"
CHECKS = {"brand", "name", "presentation", "quantity", "pack", "barcode"}
OPERATIONS = {"CREATE_HIDDEN", "UPDATE_CONTENT"}
TTL = timedelta(minutes=15)


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc)


def _actor(session):
    if not session or type(getattr(session, "id", None)) is not int or session.id <= 0:
        raise PermissionError("Sesión autenticada requerida")
    return f"session:{session.id}"


def _scope(db, store):
    # Shared across distinct request keys, identities and target product IDs.
    if db.get_bind().dialect.name == "postgresql":
        key = int(sha256((SOURCE + store).encode()).hexdigest()[:15], 16)
        if not db.scalar(select(func.pg_try_advisory_xact_lock(key))):
            raise ValueError("Otro envío está modificando el registro; reintentá la consulta.")


def _read_enabled(settings):
    if not getattr(settings, "kiki_tiendanube_read_enabled", False):
        raise PermissionError("Lectura Tiendanube deshabilitada")
    return _id(settings.tiendanube_store_id)


def _write_enabled(settings):
    _read_enabled(settings)
    if not (getattr(settings, "kiki_tiendanube_writes_enabled", False)
            and getattr(settings, "kiki_v2_writes_enabled", False)):
        raise PermissionError("Envíos Tiendanube deshabilitados; no se realizó ninguna llamada")


def _row(db, ident):
    if type(ident) is not int or ident <= 0:
        raise ValueError("Identificador de envío inválido")
    row = db.scalar(select(ImportJobRecord).where(
        ImportJobRecord.id == ident, ImportJobRecord.source == SOURCE
    ).execution_options(populate_existing=True))
    if not row:
        raise ValueError("Envío no encontrado")
    return row


def public(row):
    audit = row.diagnostics
    return {"id": row.id, "state": row.status, "revision": row.processed,
            "ecomm_id": audit["ecomm_id"], "operation": audit["operation"],
            "store_id": audit["store_id"], "target_product_id": audit.get("target_product_id"),
            "target_variant_id": audit.get("target_variant_id"),
            "preview_fingerprint": audit["preview_fingerprint"],
            "payload_preview": deepcopy(audit["payload"]),
            "review_mode": audit.get("review_mode", "DOCUMENTED"),
            "product_admin_url": (f"https://www.tiendanube.com/admin/v2/products/{audit['target_product_id']}"
                                  if row.status == "SUCCEEDED" and audit.get("target_product_id") else None),
            "optional_fields_notice": "No se envían precios, stock, categorías locales sin equivalencia, imágenes sin permisos, videos ni medidas no disponibles. Se pueden completar después en Tiendanube. La presentación debe estar incluida en el nombre revisado.",
            "blockers": audit.get("blockers", []), "history": audit.get("history", []),
            "created_at": audit["created_at"], "expires_at": audit["expires_at"],
            "error_code": audit.get("error_code"), "provider_calls": audit.get("provider_calls", 0),
            "external_writes_enabled": False,
            "notice": "No se publica. Requiere habilitación y confirmación explícita; un resultado incierto nunca se reintenta automáticamente."}


def list_submissions(db, ecomm_id):
    return [public(row) for row in db.scalars(select(ImportJobRecord).where(
        ImportJobRecord.source == SOURCE,
        ImportJobRecord.unknown_columns["ecomm_id"].as_string() == ecomm_id,
    ).order_by(ImportJobRecord.id.desc()).limit(50))]


def get_submission(db, ident):
    return public(_row(db, ident))


def _capture(db, store):
    record = _record(db)
    capture = record.payload[0] if record and record.payload else None
    if not capture or str(capture.get("store_id")) != store:
        raise ValueError("Falta una captura API Tiendanube de esta tienda; el CSV no autoriza envíos")
    try:
        at = datetime.fromisoformat(capture["captured_at"])
        if at.tzinfo is None or not timedelta(0) <= now() - at <= timedelta(hours=24):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise ValueError("Captura Tiendanube vencida o sin fecha verificable") from None
    return capture


def _remote_identity(rows, product_id):
    return sorted([
        {key: row.get(key) for key in ("product_id", "variant_id", "sku", "barcode", "name", "brand")}
        for row in rows if str(row.get("product_id")) == str(product_id)
    ], key=lambda row: str(row["variant_id"]))


def _matches(rows, sku, code, name=None):
    # Matching creates blockers/candidates; it never establishes a link.
    return [row for row in rows if normalized_sku(row.get("sku")) == normalized_sku(sku)
            or (code and row.get("barcode") and str(row["barcode"]).zfill(14) == str(code).zfill(14))
            or (name and normalize(row.get("name")) == normalize(name))]



def _target_conflicts(item, target):
    fields = item["commercial_fields"]
    reasons = []
    code = item.get("gtin_original") or item.get("barcode_original")
    remote_code = target.get("barcode")
    if remote_code and (not isinstance(remote_code, str) or not _gtin_check_digit_valid(remote_code)):
        reasons.append("Código remoto inválido; no se puede confirmar la identidad")
    elif code and remote_code and str(code).zfill(14) != remote_code.zfill(14):
        reasons.append("Conflicto entre el GTIN de Ecomm-App y el código Tiendanube")
    brand = fields.get("brand")
    if brand and target.get("brand") and normalize(brand) != normalize(target["brand"]):
        reasons.append("Marca remota distinta; requiere resolver la identidad antes de actualizar")
    name = fields.get("title", "") + " " + fields.get("presentation", "")
    if variant_conflict(name, item["sku"], target.get("name"), target.get("sku")):
        reasons.append("Presentación o variante remota incompatible con la ficha")
    if re.search(r"\b(?:pack|combo)\b", str(target.get("name") or ""), re.IGNORECASE) or (quantity(target.get("name")) or 1) != 1:
        reasons.append("La presentación remota es un pack; no actualizar como unidad")
    return reasons


def _payload(item, operation):
    fields = item["commercial_fields"]
    value = {"name": {"es": fields["title"].strip()},
             "description": {"es": fields["description"].strip()}}
    if fields.get("brand", "").strip():
        value["brand"] = fields["brand"].strip()
    if operation == "CREATE_HIDDEN":
        value.update({"visibility": "hidden", "variants": [{"sku": item["sku"].strip()}]})
    return value


def _manual_review(db, session, ecomm_id):
    """Saved editor + explicit operator attestation; not documentary approval.

    Reuses the API master and editor. Optional editorial coverage, AI and a
    READY state are deliberately not requirements for an unpublished draft.
    """
    from app.services.editorial_batches.context import sources
    from app.services.ecomm_api_product_workspace_service import EcommApiProductWorkspace
    catalog = sources(db)
    workspace = EcommApiProductWorkspace(db).get(ecomm_id, session=session)
    source, fields = workspace["source"], workspace["fields"]
    blockers = []
    sku = source["sku"]
    if not workspace["available"] or not fields.get("title", "").strip():
        blockers.append("Guardá la ficha con un nombre de producto antes de enviarla.")
    if workspace["source_sku_changed"] or source.get("identity_blockers"):
        blockers.append("La identidad Ecomm-App cambió o presenta códigos contradictorios.")
    if sum(normalized_sku(row.get("sku")) == normalized_sku(sku) for row in catalog.values()) != 1:
        blockers.append("SKU repetido en Ecomm-App; revisá la variante antes de crear un producto.")
    source_name = str(source.get("product_name") or "") + " " + str(source.get("variant_description") or "")
    title = fields.get("title", "") + " " + fields.get("presentation", "")
    if variant_conflict(source_name, sku, title, sku) or (quantity(title) or 1) != (quantity(source_name) or 1):
        blockers.append("La presentación o cantidad de la ficha difiere de la variante Ecomm-App.")
    if re.search(r"\b(?:pack|combo)\b", title + " " + source_name, re.IGNORECASE) or (quantity(title) or 1) != 1:
        blockers.append("Un pack o combo necesita validación específica; no se creará como unidad individual.")
    codes = [source.get("gtin_raw"), source.get("barcode")]
    codes = [code for code in codes if code]
    if any(not isinstance(code, str) or not _gtin_check_digit_valid(code) for code in codes):
        blockers.append("El código original Ecomm-App no es un GTIN válido.")
    code = codes[0] if codes else None
    if code and any(row["ecomm_id"] != ecomm_id and any(
        isinstance(other, str) and other.zfill(14) == code.zfill(14)
        for other in (row.get("gtin_raw"), row.get("barcode"))
    ) for row in catalog.values()):
        blockers.append("El código también identifica otra variante: no crear hasta resolver unidad y pack.")
    if fields.get("proposed_gtin") and fields["proposed_gtin"] != code:
        blockers.append("El EAN editado difiere del original; requiere resolver su procedencia antes del envío.")
    item = {"ecomm_id": ecomm_id, "sku": sku, "workspace_version": workspace["version"],
            "source_is_combo": source.get("is_combo"), "source_parent_is_combo": source.get("parent_is_combo"),
            "gtin_original": code, "commercial_fields": deepcopy(fields), "blockers": blockers}
    # Include ALL source identity and saved fields, not just the outbound subset.
    pin = fingerprint({"source": source, "fields": fields, "version": workspace["version"]})
    return {"items": [item], "blocked": bool(blockers), "preview_fingerprint": pin}


def _review(db, session, ecomm_id, mode):
    if mode == "MANUAL":
        return _manual_review(db, session, ecomm_id)
    return preview_commercial_export(db, session, "tn", [ecomm_id])


def _manual_payload(item):
    fields = item["commercial_fields"]
    variant = {"sku": item["sku"].strip()}
    if item.get("gtin_original"):
        variant["barcode"] = item["gtin_original"]
    # The editor stores plain text; the provider renders HTML. Never execute
    # arbitrary operator HTML, remote scripts or unapproved embedded images.
    payload = {"name": {"es": fields["title"].strip()}, "published": False,
               "variants": [variant]}
    for local, remote in (("description", "description"), ("seo_title", "seo_title"),
                          ("seo_description", "seo_description")):
        value = fields.get(local, "").strip()
        if value:
            payload[remote] = {"es": escape(value).replace("\n", "<br>") if local == "description" else value}
    if fields.get("brand", "").strip():
        payload["brand"] = fields["brand"].strip()
    return payload


def _capture_pin(db, store, mode):
    if mode != "MANUAL":
        return fingerprint(_capture(db, store))
    # A cached capture is informative, not an authorization prerequisite. A
    # complete live duplicate check is still mandatory immediately before POST.
    row = _record(db)
    capture = row.payload[0] if row and row.payload else None
    return fingerprint(capture) if capture and str(capture.get("store_id")) == store else None


def prepare_submission(db, session, settings, *, request_key, ecomm_id, operation,
                       identity_checks, reason, target_product_id=None, target_variant_id=None,
                       review_mode="DOCUMENTED"):
    actor = _actor(session)
    store = _read_enabled(settings)
    if not getattr(settings, "kiki_v2_writes_enabled", False):
        raise PermissionError("Registro interno de envíos deshabilitado")
    try:
        if str(UUID(request_key)) != request_key:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Clave idempotente UUID inválida") from None
    if operation not in OPERATIONS or set(identity_checks) != CHECKS or len(identity_checks) != len(CHECKS):
        raise ValueError("Revisá explícitamente marca, nombre, presentación, cantidad, pack y código")
    if not isinstance(reason, str) or not 20 <= len(reason.strip()) <= 600:
        raise ValueError("Explicá la revisión humana de identidad (20 a 600 caracteres)")
    if operation == "UPDATE_CONTENT":
        target_product_id, target_variant_id = _id(target_product_id), _id(target_variant_id)
    elif target_product_id is not None or target_variant_id is not None:
        raise ValueError("Una creación no admite identificadores externos inventados")
    if review_mode not in {"DOCUMENTED", "MANUAL"} or (review_mode == "MANUAL" and operation != "CREATE_HIDDEN"):
        raise ValueError("La revisión manual simplificada sólo permite crear un producto oculto")
    manifest = {"review_mode": review_mode, "store_id": store, "ecomm_id": ecomm_id, "operation": operation,
                "target_product_id": target_product_id, "target_variant_id": target_variant_id,
                "identity_checks": sorted(identity_checks), "reason": reason.strip()}
    _scope(db, store)
    previous = db.scalar(select(ImportJobRecord).where(
        ImportJobRecord.source == SOURCE,
        ImportJobRecord.unknown_columns["request_key"].as_string() == request_key))
    if previous:
        if previous.diagnostics["manifest"] != manifest:
            raise ValueError("La clave idempotente ya pertenece a otra selección")
        return public(previous)
    review = _review(db, session, ecomm_id, review_mode)
    item = review["items"][0]
    capture_pin = _capture_pin(db, store, review_mode)
    record = _record(db)
    capture = record.payload[0] if record and record.payload and str(record.payload[0].get("store_id")) == store else {"rows": []}
    blockers = list(item["blockers"])
    if item.get("source_is_combo") is not False or item.get("source_parent_is_combo") is not False:
        blockers.append("Este envío controlado requiere una unidad individual con identidad explícita; packs pendientes de validación específica")
    remote = []
    if operation == "UPDATE_CONTENT":
        remote = _remote_identity(capture["rows"], target_product_id)
        if len(remote) != 1 or str(remote[0].get("variant_id")) != target_variant_id:
            blockers.append("La selección debe identificar un producto de una sola variante y sus IDs exactos")
        elif normalized_sku(remote[0].get("sku")) != normalized_sku(item["sku"]):
            blockers.append("SKU remoto distinto: la revisión de identidad requiere resolver el conflicto primero")
        else:
            blockers.extend(_target_conflicts(item, remote[0]))
    elif _matches(capture["rows"], item["sku"], item.get("gtin_original") or item.get("barcode_original")):
        blockers.append("Existen candidatos en la captura; no crear un duplicado ni vincular automáticamente")
    payload = _manual_payload(item) if review_mode == "MANUAL" else _payload(item, operation)
    created = now()
    audit = {**manifest, "manifest": manifest, "request_key": request_key,
             "commercial_fingerprint": review["preview_fingerprint"],
             "capture_fingerprint": capture_pin, "remote_identity": remote,
             "workspace_version": item["workspace_version"],
             "code": item.get("gtin_original") or item.get("barcode_original"),
             "payload": payload, "created_at": created.isoformat(),
             "expires_at": (created + TTL).isoformat(), "blockers": blockers,
             "history": [{"action": "PREVIEW", "at": created.isoformat(), "actor": actor}],
             "provider_calls": 0}
    audit["preview_fingerprint"] = fingerprint(audit)
    row = ImportJobRecord(source=SOURCE, filename=f"{store}:{ecomm_id}", records=1,
                          processed=1, errors=0, status="BLOCKED" if blockers else "PREVIEW",
                          unknown_columns=audit)
    db.add(row)
    db.commit()
    return public(row)


def _finish(db, ident, status, *, error_code=None, response=None, calls=0):
    row = _row(db, ident)
    audit = deepcopy(row.diagnostics)
    audit["error_code"] = error_code
    audit["provider_calls"] = calls
    if response:
        audit["target_product_id"] = str(response["id"])
        variants = response.get("variants")
        if isinstance(variants, list) and len(variants) == 1:
            audit["target_variant_id"] = str(variants[0].get("id"))
    audit["history"].append({"action": status, "at": now().isoformat(), "error_code": error_code})
    result = db.execute(update(ImportJobRecord).where(
        ImportJobRecord.id == ident, ImportJobRecord.status == "RUNNING"
    ).values(status=status, processed=row.processed + 1, unknown_columns=audit,
             finished_at=now(), errors=0 if status == "SUCCEEDED" else 1))
    if result.rowcount != 1:
        db.rollback()
        raise ValueError("El estado del envío cambió; no repetir la escritura")
    db.commit()
    return get_submission(db, ident)


def send_submission(db, session, settings, ident, *, expected_revision,
                    expected_preview_fingerprint, confirm, transport=None):
    actor = _actor(session)
    _write_enabled(settings)  # Before any source/provider access.
    if confirm is not True:
        raise ValueError("Confirmación explícita requerida")
    store = _id(settings.tiendanube_store_id)
    _scope(db, store)
    row = _row(db, ident)
    audit = deepcopy(row.diagnostics)
    if audit["store_id"] != store:
        raise ValueError("El envío pertenece a otra tienda")
    # Replayed execution is local-only. Never issue the provider call twice.
    if row.status in {"SUCCEEDED", "UNKNOWN", "RUNNING"}:
        return public(row)
    if row.status != "PREVIEW" or row.processed != expected_revision or audit["preview_fingerprint"] != expected_preview_fingerprint:
        raise ValueError("Previsualización cambiada o bloqueada; revisá la versión actual")
    if now() > datetime.fromisoformat(audit["expires_at"]):
        raise ValueError("La autorización de envío venció; generá otra previsualización")
    fresh = _review(db, session, audit["ecomm_id"], audit.get("review_mode", "DOCUMENTED"))
    if fresh["blocked"] or fresh["preview_fingerprint"] != audit["commercial_fingerprint"]:
        raise ValueError("La ficha, identidad, evidencia o permisos cambiaron; envío bloqueado")
    if _capture_pin(db, store, audit.get("review_mode", "DOCUMENTED")) != audit["capture_fingerprint"]:
        raise ValueError("Cambió la captura del canal; compará nuevamente antes del envío")
    conflicts = list(db.scalars(select(ImportJobRecord).where(
        ImportJobRecord.source == SOURCE, ImportJobRecord.id != ident,
        ImportJobRecord.status.in_(["RUNNING", "UNKNOWN", "SUCCEEDED"]),
        ImportJobRecord.unknown_columns["store_id"].as_string() == store,
        or_(ImportJobRecord.unknown_columns["ecomm_id"].as_string() == audit["ecomm_id"],
            ImportJobRecord.unknown_columns["target_product_id"].as_string() == (audit.get("target_product_id") or "")),
    )))
    for previous in conflicts:
        data = previous.diagnostics
        same_variant = data["ecomm_id"] == audit["ecomm_id"]
        same_target = audit.get("target_product_id") and data.get("target_product_id") == audit["target_product_id"]
        if (same_variant or same_target) and (previous.status != "SUCCEEDED"
                or audit["operation"] == "CREATE_HIDDEN"
                or data["ecomm_id"] != audit["ecomm_id"]
                or data["payload"] == audit["payload"]):
            raise ValueError("Existe un envío previo para esta identidad o destino; reconciliá su resultado sin repetirlo")
    client = TiendanubeClient(store, settings.tiendanube_access_token.get_secret_value(),
                             user_agent=settings.tiendanube_user_agent, writes_enabled=True,
                             transport=transport)
    audit["authorized_by"] = actor
    audit["history"].append({"action": "RUNNING", "at": now().isoformat(), "actor": actor})
    changed = db.execute(update(ImportJobRecord).where(
        ImportJobRecord.id == ident, ImportJobRecord.status == "PREVIEW", ImportJobRecord.processed == expected_revision
    ).values(status="RUNNING", processed=expected_revision + 1, unknown_columns=audit))
    if changed.rowcount != 1:
        db.rollback()
        raise ValueError("Otro operador inició el envío; no se duplicó")
    db.commit()  # Durable receipt before any provider request; no DB lock during I/O.
    calls = 0
    dispatched = False
    try:
        # A complete live read is a precondition, never an implicit import/capture.
        def counted_transport(*args, **kwargs):
            nonlocal calls
            calls += 1
            return client_transport(*args, **kwargs)
        client_transport = client._transport
        client._transport = counted_transport
        remote = read_catalog(client)
        item = fresh["items"][0]
        matches = _matches(remote["rows"], item["sku"], audit.get("code"),
                           item["commercial_fields"].get("title") if audit.get("review_mode") == "MANUAL" else None)
        if audit["operation"] == "CREATE_HIDDEN":
            if matches or any(not r.get("sku") and (audit.get("review_mode") != "MANUAL" or
                             not (r.get("barcode") or r.get("name"))) for r in remote["rows"]):
                return _finish(db, ident, "BLOCKED", error_code="REMOTE_DUPLICATE_OR_INCOMPLETE_IDENTITY", calls=calls)
        elif _remote_identity(remote["rows"], audit["target_product_id"]) != audit["remote_identity"]:
            return _finish(db, ident, "BLOCKED", error_code="REMOTE_IDENTITY_CHANGED", calls=calls)
        else:
            if any(str(r["product_id"]) != audit["target_product_id"] for r in matches):
                return _finish(db, ident, "BLOCKED", error_code="REMOTE_AMBIGUOUS_IDENTITY", calls=calls)
        # Re-check all local pins after the remote wait, immediately before dispatch.
        db.expire_all()
        latest = _review(db, session, audit["ecomm_id"], audit.get("review_mode", "DOCUMENTED"))
        if latest["blocked"] or latest["preview_fingerprint"] != audit["commercial_fingerprint"]:
            return _finish(db, ident, "BLOCKED", error_code="LOCAL_EVIDENCE_CHANGED", calls=calls)
        if _capture_pin(db, store, audit.get("review_mode", "DOCUMENTED")) != audit["capture_fingerprint"]:
            return _finish(db, ident, "BLOCKED", error_code="LOCAL_CAPTURE_CHANGED", calls=calls)
        db.rollback()
        fields = item["commercial_fields"]
        dispatched = True
        if audit["operation"] == "CREATE_HIDDEN":
            if audit.get("review_mode") == "MANUAL":
                response = client.create_hidden_product_payload(audit["payload"])
            else:
                response = client.create_hidden_product(name=fields["title"], description=fields["description"],
                                                        sku=item["sku"], brand=fields.get("brand", ""))
            variants = response.get("variants")
            if not isinstance(variants, list) or len(variants) != 1 or normalized_sku(variants[0].get("sku")) != normalized_sku(item["sku"]):
                raise TiendanubeError(502, outcome_unknown=True)
            _id(variants[0].get("id"))
        else:
            response = client.update_product_content(audit["target_product_id"], name=fields["title"],
                                                      description=fields["description"], brand=fields.get("brand", ""))
        return _finish(db, ident, "SUCCEEDED", response=response, calls=calls)
    except TiendanubeError as exc:
        db.rollback()
        uncertain = dispatched and exc.outcome_unknown
        return _finish(db, ident, "UNKNOWN" if uncertain else "FAILED" if dispatched else "BLOCKED",
                       error_code="PROVIDER_OUTCOME_UNKNOWN" if uncertain else f"PROVIDER_HTTP_{exc.status_code}", calls=calls)
    except Exception:
        # Do not retain exception text, response body, token or credentials.
        db.rollback()
        return _finish(db, ident, "UNKNOWN" if dispatched else "BLOCKED",
                       error_code="PROVIDER_OUTCOME_UNKNOWN" if dispatched else "REMOTE_PREFLIGHT_FAILED", calls=calls)
