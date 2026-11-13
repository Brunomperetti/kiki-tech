"""Disposable offline parser service. Each input gets its own resource-limited child."""

import json
import logging
import os
import resource
import signal
import ctypes
import errno
import platform
import socketserver
import struct
import sys
from .parser import parse
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


def read_fd(fd, size):
    chunks = bytearray()
    while len(chunks) < size:
        block = os.read(fd, size - len(chunks))
        if not block:
            raise ValueError("Solicitud incompleta.")
        chunks.extend(block)
    return bytes(chunks)


KERNEL_GUARD = False


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024, 192 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        signal.alarm(8)
        if KERNEL_GUARD:
            from .security import restrict
            restrict()
        sys.addaudithook(child_guard)
        logging.disable(logging.CRITICAL)
        self.request.settimeout(None)  # SIGALRM bounds the complete child, including UDS I/O
        try:
            size = struct.unpack("!I", read_fd(self.request.fileno(), 4))[0]
            if not 0 < size <= MAX_REQUEST:
                raise ValueError("Solicitud de lectura demasiado grande.")
            body = json.loads(read_fd(self.request.fileno(), size))
            if body == {"operation": "health"}:
                import pypdf
                native_denied = False
                if KERNEL_GUARD:
                    libc = ctypes.CDLL(None, use_errno=True)
                    nr = 41 if platform.machine() == "x86_64" else 198
                    fd = libc.syscall(nr, 2, 1, 0)
                    native_denied = fd == -1 and ctypes.get_errno() == errno.EPERM
                    if fd >= 0: os.close(fd)
                result = {"ok": True, "result": {
                    "version": pypdf.__version__, "kernel_guard": KERNEL_GUARD,
                    "native_network_denied": native_denied,
                    "backend_visible": os.path.exists("/app"),
                    "proc_visible": os.path.exists("/proc"),
                    "secret_environment_present": any(k in os.environ for k in ("DATABASE_URL", "KIKI_AI_API_KEY", "APP_SESSION_SECRET", "ECOMM_APP_API_TOKEN", "ML_CLIENT_SECRET")),
                }}
            else:
                result = {"ok": True, "result": parse(body["filename"], body["content_type"], body["content_base64"])}
        except Exception:
            # Parser exceptions can contain document text; never log/echo untrusted contents.
            result = {
                "ok": False,
                "error_code": "DOCUMENT_REJECTED",
                "error": "Documento rechazado: tipo, formato, contenido activo o límites de lectura. PDF escaneado sin texto se registra sin extraer hechos.",
            }
        encoded = json.dumps(result, ensure_ascii=False).encode()
        if len(encoded) > 524_288:
            encoded = b'{"ok":false,"error":"Resultado demasiado grande."}'
        packet = memoryview(struct.pack("!I", len(encoded)) + encoded)
        while packet:
            sent = os.write(self.request.fileno(), packet)
            packet = packet[sent:]


class Server(socketserver.ForkingMixIn, socketserver.UnixStreamServer):
    max_children = 2


def serve(*, kernel_guard=False):
    global KERNEL_GUARD
    KERNEL_GUARD = kernel_guard
    Server.max_children = 1 if kernel_guard else 2
    # Only server-parent performs fork; children have no process/network capabilities.
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    try:
        with Server(SOCKET, Handler) as server:
            os.chmod(SOCKET, 0o660 if kernel_guard else 0o600)
            server.serve_forever()
    finally:
        if os.path.exists(SOCKET): os.unlink(SOCKET)


if __name__ == "__main__":
    serve()
