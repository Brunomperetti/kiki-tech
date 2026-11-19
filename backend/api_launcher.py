"""Launch FastAPI under UID 10000 with cooperative PID-1 shutdown.

On Render, PID 1 has no CAP_KILL and cannot signal differently-owned
children. An inherited anonymous pipe lets this process signal ITSELF
before PID 1 exits, preserving Uvicorn's normal lifespan shutdown.
PR_SET_PDEATHSIG handles unexpected parent death as a separate fallback.
"""
import ctypes
import os
import signal
import sys
from threading import Thread


PR_SET_PDEATHSIG = 1


def arm_parent_death_signal():
    try:
        expected_parent = int(os.environ.pop("KIKI_SUPERVISOR_PID"))
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("Supervisor de API no identificado.") from exc
    if expected_parent <= 0:
        raise SystemExit("Supervisor de API no válido.")

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "No se pudo armar protección de proceso API")
    if os.getppid() != expected_parent:
        raise SystemExit("El supervisor terminó antes de iniciar la API.")


def start_shutdown_watch():
    try:
        fd = int(os.environ.pop("KIKI_SHUTDOWN_READ_FD"))
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("Canal de apagado de API no identificado.") from exc
    if fd < 3:
        raise SystemExit("Canal de apagado de API inválido.")

    def watch():
        try:
            while os.read(fd, 1):
                pass
        finally:
            os.close(fd)
        os.kill(os.getpid(), signal.SIGTERM)

    Thread(target=watch, name="kiki-api-shutdown", daemon=True).start()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Puerto requerido.")
    port = int(sys.argv[1])
    if not 1024 <= port <= 65535:
        raise SystemExit("Puerto API inválido.")
    arm_parent_death_signal()
    start_shutdown_watch()
    # Run in-process: os.execv would destroy the shutdown watcher thread.
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
