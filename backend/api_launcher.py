"""Launch the existing FastAPI service with Linux parent-death SIGTERM.

Popen sets UID 10000 before this module starts. We must arm the signal
after that credential change: Linux clears PR_SET_PDEATHSIG on setuid.
No access to the document reader or third-party services is added here.
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
        raise SystemExit("Supervisor de API no identificado.") from exc
    if expected_parent <= 0:
        raise SystemExit("Supervisor de API no válido.")

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "No se pudo armar protección de proceso API")
    if os.getppid() != expected_parent:
        raise SystemExit("El supervisor terminó antes de iniciar la API.")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Puerto requerido.")
    port = int(sys.argv[1])
    if not 1024 <= port <= 65535:
        raise SystemExit("Puerto API inválido.")
    arm_parent_death_signal()
    os.execv(
        sys.executable,
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0", "--port", str(port),
        ],
    )


if __name__ == "__main__":
    main()
