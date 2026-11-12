"""Browser -> loopback gateway -> offline FastAPI -> disposable PostgreSQL."""

import ssl
import subprocess
import sys
import time
import http.client

from run import ROOT, clean_environment


def main():
    directory = ROOT / ".integration-runtime/api"
    context = ssl.create_default_context(cafile=str(directory / "tls-cert.pem"))
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "integration/gateway.py"), str(directory)],
        env=clean_environment(),
    )
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("La pasarela local no inició.")
            connection = http.client.HTTPSConnection(
                "127.0.0.1", 8443, context=context, timeout=2
            )
            try:
                connection.request("GET", "/health")
                response = connection.getresponse()
                if response.status == 200:
                    response.read()
                    break
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(0.25)
        else:
            raise RuntimeError("El backend aislado no está disponible.")
        for key in ["VITE_API_URL", "VITE_KIKI_MODE"]:
            invalid = {**clean_environment(), key: "https://production.invalid"}
            result = subprocess.run(
                ["node", "scripts/build-integration.mjs"],
                env=invalid,
                cwd=ROOT / "frontend",
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 or "Configuración ambigua" not in result.stderr:
                raise RuntimeError("El build no rechazó configuración ambigua.")
        subprocess.run(
            ["npm", "run", "test:integration", *(["--", "connections-connected.spec.ts"] if "--connections" in sys.argv[1:] else ["--", "presentation-connected.spec.ts", "functional-catalog.spec.ts"] if "--presentation" in sys.argv[1:] else ["--", "channels-connected.spec.ts"] if "--channels" in sys.argv[1:] else ["--", "batches-connected.spec.ts"] if "--batches" in sys.argv[1:] else ["--", "autonomous-connected.spec.ts"] if "--autonomous" in sys.argv[1:] else [])],
            cwd=ROOT / "frontend",
            env={
                **clean_environment(),
                "NODE_EXTRA_CA_CERTS": str(directory / "tls-cert.pem"),
                **({"KIKI_CONNECTION_SCENARIO": "offline-fixtures"} if "--connections" in sys.argv[1:] else {}),
                **({"KIKI_PRESENTATION_SCENARIO": "local-synthetic"} if "--presentation" in sys.argv[1:] else {}),
                **({"KIKI_AUTONOMOUS_SCENARIO":"5000-synthetic"} if "--autonomous" in sys.argv[1:] else {}),
                **({"KIKI_BATCH_SCENARIO": "synthetic-approvals"} if "--batches" in sys.argv[1:] else {}),
                **({"KIKI_CHANNEL_SCENARIO": "synthetic-captures"} if "--channels" in sys.argv[1:] else {}),
            },
            check=True,
        )
        if not any(flag in sys.argv[1:] for flag in ("--connections", "--channels", "--batches", "--autonomous", "--presentation")):
            subprocess.run(
                ["npm", "run", "test:pilot"],
                cwd=ROOT / "frontend",
                env={
                    **clean_environment(),
                    "NODE_EXTRA_CA_CERTS": str(directory / "tls-cert.pem"),
                },
                check=True,
            )
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    main()
