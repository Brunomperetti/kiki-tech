"""Restart only the fixed, verified network:none disposable project. No provider IO."""

import re
from run import compose, verify_containers


def main():
    verify_containers()
    result = compose(
        "exec",
        "-T",
        "backend",
        "python",
        "-m",
        "integration_sandbox.editorial_restart",
        "prepare",
        capture=True,
    )
    found = re.search(r"^RESTART_BATCH_ID=([a-f0-9-]{36})$", result.stdout, re.M)
    if not found:
        raise RuntimeError("El control aislado no devolvió un lote verificable.")
    compose("restart", "backend")
    compose("up", "--detach", "--no-build", "--wait", "--wait-timeout", "90")
    verify_containers()
    compose(
        "exec",
        "-T",
        "backend",
        "python",
        "-m",
        "integration_sandbox.editorial_restart",
        "verify",
        found[1],
    )


if __name__ == "__main__":
    main()
