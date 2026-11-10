"""Credential-free synthetic collector. No application imports and no network client."""

import base64
import json
import os
import socketserver
import struct
from .document_worker import child_guard, read_exact
from .discovery_http import Response, SimulatedHTTP, SyntheticDNS, retrieve
from .discovery_fixtures import catalogue

SOCKET = "/discovery-collector/collector.sock"


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(6)
        try:
            length = struct.unpack("!I", read_exact(self.rfile, 4))[0]
            if not 0 < length <= 16384:
                raise ValueError("Consulta fuera de límite.")
            body = json.loads(read_exact(self.rfile, length))
            entries, responses = catalogue()
            if body.get("operation") == "discover":
                query = body["query"]
                name = str(query.get("name") or "").casefold()
                ean = query.get("ean")
                entries = [
                    e
                    for e in entries
                    if (name and e["identity_hint"]["name"].casefold() == name)
                    or (ean and e["identity_hint"]["ean"] == ean)
                    or (
                        not name
                        and not ean
                        and query.get("brand")
                        and query.get("manufacturer")
                        and e["identity_hint"]["brand"] == query["brand"]
                        and e["identity_hint"]["manufacturer"] == query["manufacturer"]
                    )
                ]
                entries = sorted(entries, key=lambda e: e["priority"])[:20]
                # Search index response is simulated HTTP too, checked by the same policy.
                url = "https://fabricante-prueba.invalid/indice"
                responses[url] = Response(
                    200,
                    json.dumps(entries, ensure_ascii=False).encode(),
                    "application/json",
                )
                raw, trace = retrieve(url, SimulatedHTTP(responses), SyntheticDNS())
                result = {"candidates": json.loads(raw), "trace": trace}
            elif body.get("operation") == "retrieve":
                entry = next(
                    (e for e in entries if e["source_id"] == body.get("source_id")),
                    None,
                )
                if not entry:
                    raise ValueError("Fuente fuera del catálogo simulado.")
                raw, trace = retrieve(
                    entry["url"], SimulatedHTTP(responses), SyntheticDNS()
                )
                extension = {
                    "application/pdf": "pdf",
                    "text/plain": "txt",
                    "text/html": "html",
                    "application/json": "json",
                }[trace["content_type"]]
                result = {
                    "content_base64": base64.b64encode(raw).decode(),
                    "filename": entry["source_id"] + "." + extension,
                    "trace": trace,
                }
            else:
                raise ValueError("Operación no permitida.")
            response = {
                "ok": True,
                "result": result,
                "simulated": True,
                "network_enabled": False,
            }
        except Exception:
            response = {
                "ok": False,
                "error": "Investigación simulada rechazada o fuera de límites.",
            }
        encoded = json.dumps(response, ensure_ascii=False).encode()
        if len(encoded) > 750000:
            encoded = b'{"ok":false,"error":"Resultado excesivo."}'
        self.wfile.write(struct.pack("!I", len(encoded)) + encoded)


if __name__ == "__main__":
    import sys

    sys.addaudithook(
        child_guard
    )  # blocks DNS, connections and processes even in this collector
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o600)
        server.serve_forever()
