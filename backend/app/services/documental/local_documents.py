"""Authorized local documents in existing research test tables; no vendor writes."""

import base64
from copy import deepcopy
import hashlib
import json
import socket
import struct
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4
from .research import Research, now
from .storage import Document, digest

MAX_REQUEST = 750_000

PARSER_SOCKET = "/document-parser/parser.sock"


def parse_local(body, *, max_request=MAX_REQUEST):
    if body.web_snapshot and (
        body.kind != "FILE" or not body.filename.lower().endswith(".html")
        or body.content_type != "text/html"
    ):
        raise ValueError("La captura web debe ser un archivo HTML auténtico guardado localmente.")
    request = json.dumps(
        {
            key: getattr(body, key)
            for key in ("filename", "content_type", "content_base64", "web_snapshot")
        }
    ).encode()
    if len(body.content_base64) > 699_052:
        from document_reader.hileret_brochure import validate_encoding, MAX_REQUEST as PINNED_MAX
        if body.web_snapshot and body.kind == "FILE" and body.filename.lower().endswith(".html"):
            from document_reader.parser import MAX_SAVED_HTML_BYTES
            if len(body.content_base64) > ((MAX_SAVED_HTML_BYTES + 2) // 3) * 4:
                raise ValueError("HTML guardado superior a 4 MiB.")
            # The isolated parser validates exact base64 encoding, MIME,
            # original byte size, complexity and non-executing HTML.
        else:
            validate_encoding(body.content_base64)
        max_request = PINNED_MAX
    if len(request) > max_request:
        raise ValueError("Archivo superior al límite de lectura.")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(10)
            from app.core.config import get_settings
            connection.connect(get_settings().kiki_document_parser_socket)
            connection.sendall(struct.pack("!I", len(request)) + request)
            with connection.makefile("rb") as stream:
                header = stream.read(4)
                size = struct.unpack("!I", header)[0]
                if not 0 < size <= 524_288:
                    raise ValueError("Resultado fuera de límite.")
                result = json.loads(stream.read(size))
    except (OSError, ValueError, struct.error):
        raise ValueError(
            "Lector aislado no disponible o límite de tiempo/memoria excedido. No se importó el documento. Código: READER_LIMIT_OR_UNAVAILABLE."
        ) from None
    if not result.get("ok"):
        raise ValueError(result.get("error", "Documento rechazado."))
    return result["result"]


def valid_url(value):
    if not value:
        return
    try:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or any(ord(c) < 33 for c in value)
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "La referencia debe ser HTTPS y no incluir credenciales. No se descargará."
        ) from None


def public_body(body):
    result = deepcopy(body)
    result.pop("original_base64", None)
    return result


class LocalDocuments:
    research_type = Research
    Document = Document

    def __init__(self, db, session):
        self.db = db
        self.research = self.research_type(db, session)

    def document(self, ident, doc_id):
        doc = self.db.get(self.Document, doc_id)
        if not doc or doc.body.get("associated_ecomm_id") != ident:
            raise ValueError("Documento local no asociado a este Ecomm ID.")
        return doc

    def store_revision(self, doc, body, action):
        if doc.version >= 8:
            raise ValueError(
                "Límite de 8 versiones del documento en este entorno de pruebas."
            )
        doc.history = doc.history + [
            {
                "at": now(),
                "actor": self.research.actor,
                "action": action,
                "version": doc.version,
                "hash": doc.digest,
                "body": doc.body,
            }
        ]
        doc.version += 1
        body["version"] = doc.version
        doc.body, doc.digest = body, digest(body)
        self.db.flush()

    def incorporate(self, ident, body, parsed, *, acquisition=None, source_retrieval=None):
        case = self.research.dossier(ident)
        self.research.expect(case, body.expected_version)
        valid_url(body.reference_url)
        if body.web_snapshot and (
            body.kind != "FILE" or not body.filename.lower().endswith(".html")
            or body.content_type != "text/html"
            or not body.reference_url or body.declared_consulted_at is None
        ):
            raise ValueError("La captura web requiere HTML original, URL HTTPS y fecha de consulta.")
        if not body.authorized_local_processing:
            raise ValueError(
                "Se requiere autorización expresa para procesar este documento localmente."
            )
        if len(body.provenance_note.strip()) < 10:
            raise ValueError(
                "Registrá cómo obtuviste el documento. Una URL o nombre no prueba su procedencia."
            )
        if body.document_id:
            doc = self.document(ident, body.document_id)
            if body.expected_document_version != doc.version:
                raise ValueError("El documento cambió en otra sesión; no se reemplazó.")
            key, version = doc.id, doc.version + 1
        else:
            if (
                len(
                    [
                        d
                        for d in self.research.documents(ident)
                        if d.body.get("associated_ecomm_id")
                    ]
                )
                >= 10
            ):
                raise ValueError(
                    "Máximo 10 documentos locales por variante en pruebas."
                )
            doc, key, version = None, "local-" + uuid4().hex, 1
        if body.kind == "URL":
            if (
                not body.reference_url
                or body.content_base64
                or body.filename
                or body.content_type
            ):
                raise ValueError(
                    "Una referencia URL no contiene archivo ni texto descargado."
                )
            content = {
                "identity": {},
                "sections": {},
                "claims": [],
                "parse_status": "REFERENCE_ONLY",
                "parser_warnings": [],
                "parser_blockers": [],
            }
            original = {
                "filename": None,
                "content_type": None,
                "size": 0,
                "sha256": hashlib.sha256(body.reference_url.encode()).hexdigest(),
            }
        else:
            content = parsed
            raw = base64.b64decode(body.content_base64, validate=True)
            original = {
                "filename": body.filename,
                "content_type": body.content_type,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        content = {
            **content,
            "id": key,
            "version": version,
            "synthetic": False,
            "origin_kind": body.kind,
            "associated_ecomm_id": ident,
            "title": body.filename
            if body.kind == "FILE"
            else "Referencia URL · Sin descargar",
            "kind": "Documento local" if body.kind == "FILE" else "Referencia URL",
            "provenance": "local://sha256/" + original["sha256"],
            "original": original,
            "original_base64": body.content_base64,
            "source": {
                "declared_official": body.declared_official,
                "declared_manufacturer": body.declared_manufacturer.strip() or None,
                "declared_consulted_at": body.declared_consulted_at.isoformat()
                if body.declared_consulted_at
                else None,
                "note": body.provenance_note.strip(),
                "reference_url": body.reference_url,
                "registered_at": now(),
                "registered_by": self.research.actor,
                "capture_mode": (
                    "ALLOWLISTED_HTTPS_FETCH" if source_retrieval
                    else "USER_SAVED_WEB_HTML" if body.web_snapshot
                    else "LOCAL_REFERENCE_OR_FILE"
                ),
                "review_state": "PENDING",
                "reviewer": None,
                "reviewed_at": None,
                "review_reason": None,
            },
        }
        if source_retrieval:
            # Network receipt is evidence of a TLS retrieval, *not* a
            # manufacturer identity decision or claim approval.
            if body.kind != "FILE" or not body.web_snapshot:
                raise ValueError("La obtención solo permite original HTML archivado.")
            if source_retrieval["sha256"] != original["sha256"]:
                raise ValueError("El documento obtenido no coincide con el SHA-256 recibido.")
            content["retrieval"] = source_retrieval
        if acquisition:
            content["retrieval"] = {
                **acquisition["trace"],
                "run_id": acquisition["run_snapshot"]["run_id"],
                "candidate_id": acquisition["candidate_id"],
                "acquired_at": now(),
            }
        if doc:
            self.store_revision(doc, content, "REPLACE_DOCUMENT")
        else:
            doc = self.Document(
                id=key, version=1, body=content, digest=digest(content), history=[]
            )
            self.db.add(doc)
            self.db.flush()
        self.research.commit_change(
            case,
            deepcopy(case.facts),
            "DOCUMENT_INCORPORATED",
            {"document_id": key, "version": doc.version,
             "source_fetched": source_retrieval is not None},
        )
        if acquisition:
            run = deepcopy(acquisition["run_snapshot"])
            candidate = next(
                c for c in run["candidates"] if c["id"] == acquisition["candidate_id"]
            )
            candidate.update(
                document_id=key,
                decision="TRANSFERRED",
                version=candidate["version"] + 1,
            )
            candidate["history"].append(
                {
                    "at": now(),
                    "actor": self.research.actor,
                    "decision": "TRANSFERRED",
                    "document_id": key,
                    "version": candidate["version"],
                }
            )
            self.research.commit_change(
                case, deepcopy(case.facts), "ASSISTED_TRANSFER", run
            )
        self.research.refresh(case)
        result = self.research.serialize(case)
        result["incorporated_document_id"] = key
        return result

    def reparse_saved_html(self, ident, doc_id, expected_version, document_version):
        """Re-read an original missing identity, never fetching or approving anything."""
        case = self.research.dossier(ident)
        self.research.expect(case, expected_version)
        doc = self.document(ident, doc_id)
        if doc.version != document_version:
            raise ValueError("El documento cambió; actualizá las evidencias.")
        stored = doc.body
        original = stored.get("original") or {}
        source = stored.get("source") or {}
        identity = stored.get("identity") or {}
        if (
            stored.get("synthetic") is not False
            or stored.get("origin_kind") != "FILE"
            or source.get("capture_mode") != "USER_SAVED_WEB_HTML"
            or source.get("review_state") != "PENDING"
            or stored.get("parse_status") not in {"INSUFFICIENT_DATA", "TEXT_EXTRACTED"}
            or (identity.get("name") and identity.get("presentation"))
            or any(f.get("document_id") == doc_id for f in case.facts)
            or original.get("content_type") != "text/html"
        ):
            raise ValueError("Solo se releen HTML originales pendientes sin hechos extraídos.")
        encoded = stored.get("original_base64") or ""
        from document_reader.parser import MAX_SAVED_HTML_BYTES
        if not encoded or len(encoded) > ((MAX_SAVED_HTML_BYTES + 2) // 3) * 4:
            raise ValueError("El original no está disponible dentro de los límites.")
        raw = base64.b64decode(encoded, validate=True)
        if (
            len(raw) != original.get("size")
            or hashlib.sha256(raw).hexdigest() != original.get("sha256")
        ):
            raise ValueError("El SHA-256 del original no coincide.")
        parsed = parse_local(SimpleNamespace(
            kind="FILE", web_snapshot=True, filename=original["filename"],
            content_type=original["content_type"], content_base64=encoded,
        ))
        new_identity = parsed.get("identity") or {}
        if (
            parsed.get("parse_status") != "TEXT_EXTRACTED"
            or not new_identity.get("name")
            or not new_identity.get("presentation")
        ):
            raise ValueError("El lector sigue sin nombre y presentación completos; se conservó el original.")
        updated = deepcopy(stored)
        for key in ("sections", "identity", "identity_evidence", "claims",
                    "parser_warnings", "parser_blockers", "parse_status"):
            updated[key] = parsed[key]
        self.store_revision(doc, updated, "REPARSE_SAVED_HTML")
        self.research.commit_change(
            case, deepcopy(case.facts), "DOCUMENT_REPARSED",
            {"document_id": doc.id, "version": doc.version,
             "original_sha256": original["sha256"]},
        )
        self.research.refresh(case)
        return self.research.serialize(case)

    def provenance(self, ident, doc_id, body):
        case = self.research.dossier(ident)
        doc = self.document(ident, doc_id)
        if doc.version != body.expected_document_version:
            raise ValueError(
                "La procedencia cambió en otra sesión; recuperá su versión nueva."
            )
        if len(body.reason.strip()) < 10:
            raise ValueError("Registrá un motivo concreto de revisión de procedencia.")
        if (
            body.decision == "REVIEWED"
            and doc.body.get("source", {}).get("review_state") == "REVIEWED"
        ):
            # Reconfirming an unchanged reviewed original is an audit event, not
            # a new document version: changing its metadata digest needlessly
            # invalidates valid per-field approvals and identity reconciliation.
            # Revoking/rejecting a source still takes the revision path below,
            # which blocks facts as before.
            self.research.commit_change(
                case,
                deepcopy(case.facts),
                "PROVENANCE_RECONFIRMED",
                {
                    "document_id": doc_id,
                    "document_version": doc.version,
                    "document_hash": doc.digest,
                    "decision": body.decision,
                    "reason": body.reason.strip(),
                },
            )
            return self.research.serialize(case)
        updated = deepcopy(doc.body)
        updated["source"].update(
            review_state=body.decision,
            reviewer=self.research.actor,
            reviewed_at=now(),
            review_reason=body.reason.strip(),
        )
        self.store_revision(doc, updated, "PROVENANCE_" + body.decision)
        self.research.commit_change(
            case,
            deepcopy(case.facts),
            "PROVENANCE_REVIEWED",
            {"document_id": doc_id, "decision": body.decision},
        )
        self.research.refresh(case)
        return self.research.serialize(case)

    def original(self, ident, doc_id, version):
        self.research.dossier(ident)
        doc = self.document(ident, doc_id)
        stored = (
            doc.body
            if version == doc.version
            else next((h["body"] for h in doc.history if h["version"] == version), None)
        )
        if not stored:
            raise ValueError("Versión original no disponible.")
        result = {
            "document_id": doc.id,
            "version": version,
            "ecomm_id": ident,
            "original": stored["original"],
            "content_base64": stored["original_base64"],
            "reference_url": stored["source"]["reference_url"],
            "isolated_only": self.research.isolated_only,
            "internal_only": True,
            "external_writes_enabled": False,
        }
        self.db.commit()
        return result


def reader_available():
    """Local UDS health only; never probes a provider or reads a document."""
    from app.core.config import get_settings
    config = get_settings()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(1)
            connection.connect(config.kiki_document_parser_socket)
            body = b'{"operation":"health"}'
            connection.sendall(struct.pack("!I", len(body)) + body)
            with connection.makefile("rb") as stream:
                size = struct.unpack("!I", stream.read(4))[0]
                if not 0 < size < 4096: return False
                result = json.loads(stream.read(size))
        details = result.get("result", {})
        return result.get("ok") is True and details.get("version") == "7.0.0" and (not config.kiki_document_parser_kernel_required or (details.get("kernel_guard") is True and details.get("native_network_denied") is True and details.get("backend_visible") is False and details.get("proc_visible") is False and details.get("secret_environment_present") is False))
    except (OSError, ValueError, struct.error, TypeError):
        return False
