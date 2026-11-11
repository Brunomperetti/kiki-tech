"""Two separate offline processes around an actual disposable FastAPI restart."""

import sys
from types import SimpleNamespace
from uuid import uuid4
from .editor_checks import application
from fastapi.testclient import TestClient
from app.database.session import SessionLocal
from app.services.editorial_batches.service import Batches

if __name__ == "__main__":
    with TestClient(application, base_url="https://127.0.0.1:8443"):
        with SessionLocal() as db:
            service = Batches(db, SimpleNamespace(id="SYNTHETIC-RESTART-CHECK"))
            if sys.argv[1] == "prepare":
                batch = service.preview(
                    {
                        "request_key": str(uuid4()),
                        "operation": "REVIEW_TASKS",
                        "selection": {
                            "kind": "IDS",
                            "ids": ["900001"],
                            "query": "",
                            "filter": "all",
                        },
                    }
                )
                service.start(
                    batch["id"],
                    {
                        "confirm": True,
                        "expected_revision": batch["revision"],
                        "preview_hash": batch["preview_hash"],
                        "idempotency_key": str(uuid4()),
                    },
                )
                service.claim(batch["id"])
                print("RESTART_BATCH_ID=" + batch["id"], flush=True)
            elif sys.argv[1] == "verify":
                ident = str(__import__("uuid").UUID(sys.argv[2]))
                assert service.detail(ident)["counts"] == {"RUNNING": 1}
                assert service.step(ident, True)["state"] == "COMPLETED"
                first = service.detail(ident)
                assert first["items"][0]["attempts"] == 2
                try:
                    service.step(ident, True)
                except ValueError:
                    db.rollback()
                else:
                    raise AssertionError(
                        "Un lote terminado no puede ejecutarse otra vez."
                    )
                assert service.detail(ident)["counts"] == {"COMPLETED": 1}
                print(
                    "Actual disposable backend restart: PASS; no duplicate action.",
                    flush=True,
                )
