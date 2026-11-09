"""Loopback HTTPS -> exactly one local Unix socket, with no upstream configuration."""

import http.client
import os
import socket
import socketserver
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from integration_sandbox.policy import ALLOWED_ROUTES, CSP, install_network_guard  # noqa: E402


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(str(SOCKET))


class LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer's default calls getfqdn; even DNS is unnecessary here.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    # Only this origin and these methods/paths; never a general forward proxy.
    def handle_request(self):
        path = urlsplit(self.path)
        origin = self.headers.get("Origin")
        if (
            self.headers.get("Host") not in {"127.0.0.1:8443", "localhost:8443"}
            or path.scheme
            or path.netloc
            or origin not in {None, "https://127.0.0.1:8443", "https://localhost:8443"}
            or (self.command, path.path) not in ALLOWED_ROUTES
            or self.headers.get("Transfer-Encoding")
        ):
            self.deny(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 16_384:
                self.deny(413)
                return
        except ValueError:
            self.deny(400)
            return
        data = self.rfile.read(length)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() in {"content-type", "cookie", "x-csrf-token"}
        }
        headers["Host"] = "localhost"
        connection = UnixHTTPConnection("localhost", timeout=10)
        try:
            connection.request(self.command, self.path, body=data, headers=headers)
            upstream = connection.getresponse()
            body = upstream.read(2_000_001)
            if len(body) > 2_000_000:
                raise OSError("Response too large")
            self.send_response(upstream.status)
            for key, value in upstream.getheaders():
                if key.lower() in {
                    "content-type",
                    "set-cookie",
                    "content-security-policy",
                    "cache-control",
                    "x-kiki-environment",
                    "x-content-type-options",
                }:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (OSError, http.client.HTTPException):
            self.deny(502)
        finally:
            connection.close()

    def deny(self, status):
        self.send_response(status)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = handle_request
    do_POST = handle_request
    do_OPTIONS = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request
    do_HEAD = handle_request

    def log_message(self, *_args):
        pass  # Do not log query strings, cookies or request bodies.


if __name__ == "__main__":
    directory = Path(sys.argv[1]).resolve(strict=True)
    SOCKET = directory / "api.sock"
    os.umask(0o077)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(directory / "tls-cert.pem", directory / "tls-key.pem")
    install_network_guard(unix_socket=str(SOCKET))
    server = LocalServer(("127.0.0.1", 8443), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print("Integración sintética: https://127.0.0.1:8443/health", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
