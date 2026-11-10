"""Disposable offline parser service. Each input gets its own resource-limited child."""

import json
import logging
import os
import resource
import signal
import socketserver
import struct
import sys
from .document_parser import parse
from .hileret_brochure import MAX_REQUEST

SOCKET = "/document-parser/parser.sock"


def read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("Solicitud incompleta.")
    return data


def child_guard(event, args):
    if event in {
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.sendto",
        "socket.sendmsg",
        "subprocess.Popen",
        "os.system",
        "os.exec",
        "os.posix_spawn",
        "os.fork",
        "os.forkpty",
    }:
        raise ValueError("Red y ejecución de procesos prohibidas en el lector.")


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024, 192 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        signal.alarm(8)
        sys.addaudithook(child_guard)
        logging.disable(logging.CRITICAL)
        self.request.settimeout(8)
        try:
            size = struct.unpack("!I", read_exact(self.rfile, 4))[0]
            if not 0 < size <= MAX_REQUEST:
                raise ValueError("Solicitud de lectura demasiado grande.")
            body = json.loads(read_exact(self.rfile, size))
            result = {
                "ok": True,
                "result": parse(
                    body["filename"], body["content_type"], body["content_base64"]
                ),
            }
        except Exception:
            # Parser exceptions can contain document text; never log/echo untrusted contents.
            result = {
                "ok": False,
                "error": "Documento rechazado: tipo, formato, contenido activo o límites de lectura. PDF escaneado sin texto se registra sin extraer hechos.",
            }
        encoded = json.dumps(result, ensure_ascii=False).encode()
        if len(encoded) > 524_288:
            encoded = b'{"ok":false,"error":"Resultado demasiado grande."}'
        self.wfile.write(struct.pack("!I", len(encoded)) + encoded)


class Server(socketserver.ForkingMixIn, socketserver.UnixStreamServer):
    max_children = 2


if __name__ == "__main__":
    # Only server-parent performs fork; children have no process/network capabilities.
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o600)
        server.serve_forever()
