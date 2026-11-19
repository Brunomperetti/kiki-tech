"""Root-only reader launch boundary; no backend imports or secrets.

The supervisor may lack CAP_KILL. The isolated reader therefore requests a
kernel SIGTERM if its supervisor exits. Arm it AFTER setuid: Linux resets this
setting whenever process credentials change.
"""
import ctypes
import os
import signal
import sys


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


def main():
    if os.getuid() != 0:
        raise SystemExit("El lector requiere la frontera chroot; no hay fallback inseguro.")
    os.chroot("/opt/kiki-reader")
    os.chdir("/")
    os.setgroups([])
    os.setgid(10000)
    os.setuid(10001)
    arm_parent_death_signal()

    sys.path = [
        "/usr/local/lib/python3.12/site-packages",
        "/usr/local/lib/python3.12",
        "/usr/local/lib/python3.12/lib-dynload",
    ]
    from document_reader import worker

    worker.SOCKET = "/run/parser.sock"
    worker.serve(kernel_guard=True)


if __name__ == "__main__":
    main()
