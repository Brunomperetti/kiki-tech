"""Test-only PID 1: fixed children, validated clean env; no app/engine imports.

All SQL/provider safeguards remain inside each child, and Docker has network:none.
This launcher is never imported by the production application.
"""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from .policy import validate_environment


def mode():
    path = Path("/runtime/editorial-mode")
    value = path.read_text().strip() if path.exists() else "manual"
    if value not in {"manual", "backend"}:
        raise RuntimeError("Modo de ejecución local inválido.")
    return value


def main():
    validate_environment(os.environ)
    autonomous = mode() == "backend"
    server = subprocess.Popen([sys.executable, "-m", "integration_sandbox.server"])
    stop = False

    def ending(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, ending)
    signal.signal(signal.SIGINT, ending)
    workers = []
    try:
        # API health/migrations precede any consumption. Never create DB schema here.
        for _ in range(240):
            if server.poll() is not None:
                raise RuntimeError("FastAPI aislado no inició.")
            import socket

            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    sock.connect("/runtime/api.sock")
                    sock.sendall(b"GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n")
                    ready = b"200 OK" in sock.recv(1024)
            except OSError:
                ready = False
            if ready:
                break
            if stop:
                return
            time.sleep(0.25)
        else:
            raise RuntimeError("No se pudo comprobar el backend de pruebas.")
        count_path = Path("/runtime/editorial-workers")
        count = int(count_path.read_text()) if count_path.exists() else 1
        if count not in (1, 2):
            raise RuntimeError("Cantidad de ejecutores de pruebas inválida.")
        failures = [0] * count

        def launch():
            return subprocess.Popen(
                [sys.executable, "-m", "integration_sandbox.editorial_executor"]
            )

        if autonomous:
            workers = [launch() for _ in range(count)]
        while not stop:
            if server.poll() is not None:
                raise RuntimeError("FastAPI detenido; ejecutores retirados.")
            for index, worker in enumerate(workers):
                if worker.poll() is not None:
                    failures[index] += 1
                    if failures[index] > 3:
                        raise RuntimeError(
                            "Ejecutor inestable; supervisor detenido sin ignorar errores."
                        )
                    print(
                        "Ejecutor de pruebas reiniciado; estado conservado en PostgreSQL.",
                        flush=True,
                    )
                    time.sleep(min(2 ** (failures[index] - 1), 4))
                    workers[index] = launch()
            time.sleep(0.2)
    finally:
        for child in [*workers, server]:
            if child.poll() is None:
                child.terminate()
        for child in [*workers, server]:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
