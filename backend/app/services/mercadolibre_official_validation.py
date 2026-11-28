"""Human-confirmed official validation, never publication or token refresh."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import ipaddress
import json
import re

from sqlalchemy import select, update

from app.database.models import ImportJobRecord, MercadoLibreConnection
from app.integrations.mercadolibre.transport import Response, MercadoLibreHTTPError
from app.services.mercadolibre_service import MercadoLibreService
from app.services.commercial_channel_export_service import preview_commercial_export
from app.services.tiendanube_controlled_submission import fingerprint, now, TTL, _actor, _scope
from app.services.documental.source_fetch import DNSResolver, vetted_ip, _PinnedHTTPSConnection
from app.services.documental.storage import Dossier

SOURCE = "ML_VALIDATION"
HOST = "api.mercadolibre.com"
CATEGORY = r"ML[A-Z][1-9][0-9]{0,13}"


class ValidationTransport:
    """Defense in depth around the existing client: four routes, zero retries."""
    def __init__(self, *, resolver=None, connection_factory=None):
        self.resolver = resolver or DNSResolver()
        self.connection_factory = connection_factory or _PinnedHTTPSConnection
        self.calls = 0

    def request(self, method, url, *, headers=None, data=None):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        route = (method == "POST" and parsed.path == "/items/validate") or (
            method == "GET" and (parsed.path == "/users/me" or re.fullmatch(r"/categories/" + CATEGORY + r"(?:/attributes)?", parsed.path)))
        if (not route or parsed.scheme != "https" or parsed.netloc != HOST
                or parsed.query or parsed.fragment or parsed.username or self.calls >= 4):
            raise ValueError("Destino o límite de validación oficial rechazado")
        ip = vetted_ip(HOST, self.resolver)
        conn = self.connection_factory(HOST, ip)
        conn.timeout = 15
        self.calls += 1
        try:
            conn.connect()
            if ipaddress.ip_address(conn.sock.getpeername()[0]) != ipaddress.ip_address(ip):
                raise ValueError("Destino DNS de validación incompatible")
            conn.request(method, parsed.path, body=data, headers={**(headers or {}), "Host": HOST, "Accept": "application/json", "Accept-Encoding": "identity"})
            response = conn.getresponse()
            if 300 <= response.status < 400:
                raise ValueError("Redirección de validación rechazada")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise ValueError("Codificación de respuesta rechazada")
            raw = response.read(524289)
            if len(raw) > 524288:
                raise ValueError("Respuesta oficial fuera de límite")
            if response.status >= 400:
                raise MercadoLibreHTTPError(response.status, "La API oficial rechazó la validación")
            if response.status == 204:
                return Response(204, None)
            if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise ValueError("Respuesta oficial sin JSON verificable")
            return Response(response.status, json.loads(raw))
        finally:
            conn.close()



class ValidationGuard:
    """Apply the same path budget even to an injected test/operational transport."""
    def __init__(self, delegate):
        self.delegate, self.calls = delegate, 0

    def request(self, method, url, *, headers=None, data=None):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        allowed = (method == "POST" and parsed.path == "/items/validate") or (
            method == "GET" and (parsed.path == "/users/me" or re.fullmatch(r"/categories/" + CATEGORY + r"(?:/attributes)?", parsed.path)))
        if (not allowed or parsed.scheme != "https" or parsed.netloc != HOST or parsed.query
                or parsed.fragment or parsed.username or self.calls >= 4
                or data is not None and (not isinstance(data, str) or len(data.encode()) > 64000)):
            raise ValueError("Operación fuera del contrato de validación")
        self.calls += 1
        return self.delegate.request(method, url, headers=headers, data=data)


def _row(db, ident):
    row = db.scalar(select(ImportJobRecord).where(ImportJobRecord.id == ident, ImportJobRecord.source == SOURCE).execution_options(populate_existing=True))
    if not row:
        raise ValueError("Validación no encontrada")
    return row


def public(row):
    data = row.diagnostics
    return {"id": row.id, "ecomm_id": data["ecomm_id"], "state": row.status,
            "revision": row.processed, "preview_fingerprint": data["preview_fingerprint"],
            "payload_preview": deepcopy(data["payload"]), "blockers": data["blockers"],
            "history": data["history"], "provider_calls": data.get("provider_calls", 0),
            "error_code": data.get("error_code"), "official_payload_validated": row.status == "VALIDATED",
            "publication_created": False, "external_writes_enabled": False,
            "validation_scope": "EXACT_REVIEWED_PAYLOAD_AT_RECORDED_TIME_NOT_CURRENT_PUBLICATION",
            "notice": "Validar no publica. No renueva OAuth ni modifica publicaciones, stock o precios."}


def listing(db, ecomm_id):
    return [public(row) for row in db.scalars(select(ImportJobRecord).where(
        ImportJobRecord.source == SOURCE, ImportJobRecord.filename == ecomm_id
    ).order_by(ImportJobRecord.id.desc()).limit(30))]


def _build(db, session, ecomm_id, parameters):
    if not isinstance(parameters, dict) or len(json.dumps(parameters).encode()) > 32000:
        raise ValueError("Parámetros de validación fuera de límite")
    review = preview_commercial_export(db, session, "ml", [ecomm_id])
    item = review["items"][0]
    fields = item["commercial_fields"]
    blockers = list(item["blockers"])
    allowed = {"seller_id", "category_id", "price", "currency_id", "available_quantity", "condition", "buying_mode", "listing_type_id", "attributes"}
    if set(parameters) - allowed:
        raise ValueError("Parámetro no autorizado; no se aceptan payloads arbitrarios")
    seller, category = parameters.get("seller_id"), parameters.get("category_id")
    if not isinstance(seller, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", seller):
        blockers.append("Falta el vendedor auténtico autorizado")
    if not isinstance(category, str) or not re.fullmatch(CATEGORY, category):
        blockers.append("Falta el ID oficial de categoría seleccionado y revisado")
    try:
        price = Decimal(str(parameters.get("price")))
        if not price.is_finite() or price <= 0 or price > Decimal("1000000000"):
            raise InvalidOperation
    except InvalidOperation:
        blockers.append("Falta precio real suministrado para validar; no se inventa")
    quantity = parameters.get("available_quantity")
    if type(quantity) is not int or not 1 <= quantity <= 1000000:
        blockers.append("Falta cantidad real autorizada para la validación")
    if not isinstance(parameters.get("currency_id"), str) or not re.fullmatch(r"[A-Z]{3}", parameters["currency_id"]):
        blockers.append("Falta moneda explícita")
    if parameters.get("condition") not in {"new", "used", "not_specified"} or parameters.get("buying_mode") not in {"buy_it_now", "auction", "classified"}:
        blockers.append("Falta condición o modalidad de venta explícita")
    if not isinstance(parameters.get("listing_type_id"), str) or not re.fullmatch(r"[a-z_]{1,50}", parameters["listing_type_id"]):
        blockers.append("Falta modalidad de publicación oficial seleccionada")
    case = db.get(Dossier, ecomm_id)
    cited = {str(c.get("fact_id")) for values in item.get("field_evidence", {}).values() for c in values}
    facts = {f["id"]: f for f in case.facts if f.get("state") == "APPROVED" and f["id"] in cited} if case else {}
    attributes = parameters.get("attributes")
    attrs, seen = [], set()
    if not isinstance(attributes, list) or len(attributes) > 40:
        blockers.append("Atributos oficiales sin revisión respaldada")
    else:
        for attr in attributes:
            if not isinstance(attr, dict) or set(attr) != {"id", "value_name", "fact_id"}:
                blockers.append("Cada atributo requiere ID oficial, valor y hecho aprobado exacto")
                continue
            key, value = attr["id"], attr["value_name"]
            fact = facts.get(attr["fact_id"])
            if (key not in {"BRAND", "GTIN"} or key in seen
                    or not isinstance(value, str) or len(value) > 250 or not fact or str(fact.get("value")) != value):
                blockers.append("Atributo duplicado o valor sin cita aprobada de esta variante")
                continue
            if key == "BRAND" and fact.get("field") != "brand" or key == "GTIN" and fact.get("field") not in {"ean", "gtin", "barcode"}:
                blockers.append("El tipo de hecho no acredita el atributo oficial indicado")
                continue
            seen.add(key)
            attrs.append({"id": key, "value_name": value})
    pictures = [{"source": value["url"]} for value in fields.get("media", []) if value["kind"] == "IMAGE"]
    if not pictures:
        blockers.append("Faltan imágenes autorizadas para el producto exacto")
    payload = {key: deepcopy(parameters.get(key)) for key in ("category_id", "price", "currency_id", "available_quantity", "condition", "buying_mode", "listing_type_id")}
    payload.update(title=fields["title"], attributes=attrs, pictures=pictures)
    return review, item, payload, blockers


def prepare(db, session, settings, *, request_key, ecomm_id, parameters, reason):
    from uuid import UUID
    actor = _actor(session)
    if not settings.kiki_v2_writes_enabled:
        raise PermissionError("Registro de validaciones deshabilitado")
    try:
        if str(UUID(request_key)) != request_key:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Clave idempotente UUID inválida") from None
    if not isinstance(reason, str) or not 20 <= len(reason.strip()) <= 600:
        raise ValueError("Explicá la autorización de parámetros auténticos (20 a 600 caracteres)")
    _scope(db, "ML_VALIDATION")
    manifest = {"ecomm_id": ecomm_id, "parameters": parameters, "reason": reason.strip()}
    prior = db.scalar(select(ImportJobRecord).where(ImportJobRecord.source == SOURCE, ImportJobRecord.unknown_columns["request_key"].as_string() == request_key))
    if prior:
        if prior.diagnostics["manifest"] != manifest:
            raise ValueError("La clave ya corresponde a otra autorización")
        return public(prior)
    review, item, payload, blockers = _build(db, session, ecomm_id, parameters)
    data = {"request_key": request_key, "manifest": manifest, "ecomm_id": ecomm_id,
            "commercial_fingerprint": review["preview_fingerprint"], "payload": payload,
            "target_taxonomy": item["channel_taxonomy"]["target_pair"], "blockers": blockers,
            "expires_at": (now() + TTL).isoformat(), "history": [{"action": "PREVIEW", "by": actor, "at": now().isoformat()}]}
    data["preview_fingerprint"] = fingerprint(data)
    row = ImportJobRecord(source=SOURCE, filename=ecomm_id, records=1, processed=1, errors=0,
                          status="BLOCKED" if blockers else "PREVIEW", unknown_columns=data)
    db.add(row)
    db.commit()
    return public(row)


def validate(db, session, settings, ident, *, expected_revision, expected_preview_fingerprint, confirm, service_factory=MercadoLibreService, transport=None):
    actor = _actor(session)
    if not (getattr(settings, "kiki_ml_official_validation_enabled", False) and settings.kiki_v2_writes_enabled):
        raise PermissionError("Validación oficial Mercado Libre deshabilitada; no se consultó al proveedor")
    if settings.ml_api_url != "https://" + HOST or confirm is not True:
        raise ValueError("Origen oficial y confirmación explícita requeridos")
    _scope(db, "ML_VALIDATION")
    row = _row(db, ident)
    if row.status in {"VALIDATED", "REJECTED", "UNKNOWN", "RUNNING"}:
        return public(row)
    data = deepcopy(row.diagnostics)
    if (row.status != "PREVIEW" or row.processed != expected_revision
            or data["preview_fingerprint"] != expected_preview_fingerprint
            or now() > datetime.fromisoformat(data["expires_at"])):
        raise ValueError("Previsualización vencida o modificada; recuperá su estado")
    review, _, payload, blockers = _build(db, session, data["ecomm_id"], data["manifest"]["parameters"])
    if blockers or review["preview_fingerprint"] != data["commercial_fingerprint"] or payload != data["payload"]:
        raise ValueError("La ficha, evidencias o permisos cambiaron; no se validó")
    connections = list(db.scalars(select(MercadoLibreConnection).limit(2)))
    if len(connections) != 1:
        raise ValueError("Falta una cuenta Mercado Libre inequívoca ya conectada")
    connection = connections[0]
    expires = connection.expires_at.replace(tzinfo=timezone.utc) if connection.expires_at.tzinfo is None else connection.expires_at
    if expires <= now() or connection.user_id != data["manifest"]["parameters"]["seller_id"]:
        raise ValueError("Token vencido o vendedor distinto; no se renovó OAuth ni se leyó la credencial")
    boundary = ValidationGuard(transport or ValidationTransport())
    service = service_factory(db)
    client = service._client(connection)  # Existing decrypt/client path; NEVER _run/_refresh.
    client.transport = boundary
    data["history"].append({"action": "RUNNING", "by": actor, "at": now().isoformat()})
    changed = db.execute(update(ImportJobRecord).where(ImportJobRecord.id == ident, ImportJobRecord.status == "PREVIEW", ImportJobRecord.processed == expected_revision).values(status="RUNNING", processed=expected_revision + 1, unknown_columns=data))
    if changed.rowcount != 1:
        db.rollback()
        raise ValueError("Otra sesión inició esta validación")
    db.commit()
    state, code = "UNKNOWN", "OFFICIAL_VALIDATION_UNCERTAIN"
    try:
        owner = client.get_current_user()
        if not isinstance(owner, dict) or str(owner.get("id")) != connection.user_id:
            raise ValueError("Vendedor no acreditado")
        category = client._get("/categories/" + payload["category_id"])
        pair = data["target_taxonomy"] or {}
        names = [node.get("name") for node in category.get("path_from_root", [])]
        if str(category.get("id")) != payload["category_id"] or not names or pair.get("category") not in names or pair.get("subcategory") != names[-1]:
            raise ValueError("La categoría oficial no coincide con la equivalencia aprobada")
        attrs = client.get_category_attributes(payload["category_id"])
        allowed = {attr["id"] for attr in attrs if isinstance(attr.get("id"), str)}
        required = {attr["id"] for attr in attrs if (attr.get("tags") or {}).get("required") is True}
        selected = {attr["id"] for attr in payload["attributes"]}
        if not selected <= allowed or not required <= selected:
            raise ValueError("Faltan atributos oficiales respaldados")
        db.expire_all()
        current, _, current_payload, current_blockers = _build(db, session, data["ecomm_id"], data["manifest"]["parameters"])
        if current_blockers or current["preview_fingerprint"] != data["commercial_fingerprint"] or current_payload != payload:
            raise ValueError("Ficha cambiada durante comprobaciones oficiales")
        db.rollback()
        result = client.validate_item(payload)
        if result != {"validated": True, "status_code": 204, "publication_created": False}:
            raise ValueError("Validación sin HTTP204 limpio")
        db.expire_all()
        final, _, final_payload, final_blockers = _build(db, session, data["ecomm_id"], data["manifest"]["parameters"])
        if final_blockers or final["preview_fingerprint"] != data["commercial_fingerprint"] or final_payload != payload:
            state, code = "BLOCKED", "LOCAL_CHANGED_AFTER_OFFICIAL_VALIDATION"
        else:
            state, code = "VALIDATED", None
    except MercadoLibreHTTPError:
        state, code = "REJECTED", "OFFICIAL_PROVIDER_REJECTED"
    except ValueError:
        state, code = "BLOCKED", "OFFICIAL_REQUIREMENTS_UNVERIFIED"
    except Exception:
        pass
    db.rollback()
    row = _row(db, ident)
    data = deepcopy(row.diagnostics)
    data.update(error_code=code, provider_calls=getattr(boundary, "calls", None))
    data["history"].append({"action": state, "at": now().isoformat(), "error_code": code})
    done = db.execute(update(ImportJobRecord).where(ImportJobRecord.id == ident, ImportJobRecord.status == "RUNNING").values(status=state, processed=row.processed + 1, unknown_columns=data, finished_at=now(), errors=int(state != "VALIDATED")))
    if done.rowcount != 1:
        db.rollback()
        raise ValueError("Cambió el registro; no repetir la validación")
    db.commit()
    return public(_row(db, ident))
