"""Restart only validated network:none test containers, never a deployment."""

from run import ROOT, compose, verify_containers


def main():
    verify_containers()
    directory = ROOT / ".integration-runtime/api"
    (directory / "editorial-mode").write_text("backend")
    (directory / "editorial-workers").write_text("2")
    try:
        compose("restart", "backend")
        compose("up", "--detach", "--no-build", "--wait", "--wait-timeout", "90")
        verify_containers()
        compose(
            "exec",
            "-T",
            "backend",
            "python",
            "-m",
            "integration_sandbox.autonomous_restart",
            "prepare",
        )
        compose(
            "exec",
            "-T",
            "backend",
            "python",
            "-m",
            "integration_sandbox.autonomous_restart",
            "kill",
        )
        compose("restart", "backend")
        compose("up", "--detach", "--no-build", "--wait", "--wait-timeout", "90")
        verify_containers()
        compose(
            "exec",
            "-T",
            "backend",
            "python",
            "-m",
            "integration_sandbox.autonomous_restart",
            "verify",
        )
    finally:
        # Restore the exact six-variant fixture before restarting manual regression mode.
        compose(
            "exec",
            "-T",
            "backend",
            "python",
            "-c",
            "from integration_sandbox.bootstrap import create_sandbox_app; create_sandbox_app(); from app.database.session import SessionLocal; from app.database.models import CatalogSnapshot; from sqlalchemy import delete; from integration_sandbox.fixtures import seed; db=SessionLocal(); db.execute(delete(CatalogSnapshot)); db.commit(); seed(SessionLocal); db.close()",
        )
        (directory / "editorial-mode").write_text("manual")
        (directory / "editorial-workers").write_text("1")
        compose("restart", "backend")
        compose("up", "--detach", "--no-build", "--wait", "--wait-timeout", "90")


if __name__ == "__main__":
    main()
