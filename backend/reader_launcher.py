"""Root-only reader boundary with cooperative supervisor shutdown.

The reader receives no database credentials, network permission or backend
modules. It requests Linux SIGTERM on parent death *after* UID change, and
also listens for EOF on a private inherited pipe to finish gracefully
before PID 1 exits, even when CAP_KILL is absent.
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
        raise SystemExit("Supervisor del lector no identificado.") from exc
    if expected_parent <= 0:
        raise SystemExit("Supervisor del lector no válido.")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "No se pudo armar protección del lector")
    if os.getppid() != expected_parent:
        raise SystemExit("El supervisor terminó antes de iniciar el lector.")


def start_shutdown_watch():
    try:
        fd = int(os.environ.pop("KIKI_SHUTDOWN_READ_FD"))
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("Canal de apagado del lector no identificado.") from exc
    if fd < 3:
        raise SystemExit("Canal de apagado del lector inválido.")

    def watch():
        try:
            while os.read(fd, 1):
                pass
        finally:
            os.close(fd)
        os.kill(os.getpid(), signal.SIGTERM)

    Thread(target=watch, name="kiki-reader-shutdown", daemon=True).start()


def main():
    if os.getuid() != 0:
        raise SystemExit("El lector requiere la frontera chroot; no hay fallback inseguro.")
    os.chroot("/opt/kiki-reader")
    os.chdir("/")
    os.setgroups([])
    os.setgid(10000)
    os.setuid(10001)
    arm_parent_death_signal()
    start_shutdown_watch()

    sys.path = [
        "/usr/local/lib/python3.12/site-packages",
        "/usr/local/lib/python3.12",
        "/usr/local/lib/python3.12/lib-dynload",
    ]
    from document_reader import worker
    worker.SOCKET = "/run/parser.sock"
    try:
        worker.serve(kernel_guard=True)
    finally:
        print("KIKI_READER_SHUTDOWN_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
