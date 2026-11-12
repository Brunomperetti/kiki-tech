"""External lifecycle acceptance. Only the fixed disposable test catalog is used."""

import json
import os
from pathlib import Path
import signal
import sys
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4
from .bootstrap import create_sandbox_app

create_sandbox_app(autonomous=True)
from sqlalchemy import select, func  # noqa:E402
from app.database.session import SessionLocal  # noqa:E402
from app.database.models import EcommApiProductEdit  # noqa:E402
from app.services.editorial_batches.service import Batches  # noqa:E402
from app.services.editorial_batches.storage import Item  # noqa:E402
from .editorial_fixtures import catalogue  # noqa:E402

ACTOR = SimpleNamespace(id="SYNTHETIC-2R-LIFECYCLE-AUTHORIZER")
STATE = Path("/runtime/editorial-test-state.json")
GATE = Path("/runtime/editorial-test-pause-after-claim")
CLAIM = Path("/runtime/editorial-test-claimed.json")


def wait(fn, timeout=60):
    end = monotonic() + timeout
    while monotonic() < end:
        result = fn()
        if result:
            return result
        sleep(0.1)
    raise RuntimeError("Venció el tiempo de la comprobación autónoma aislada.")


def read():
    ident = json.loads(STATE.read_text())["batch_id"]
    with SessionLocal() as db:
        return Batches(db, ACTOR).detail(ident)


def main():
    phase = sys.argv[1]
    if phase == "prepare":
        with SessionLocal() as db:
            catalogue(db, 1000)
            before = db.scalar(select(func.count()).select_from(EcommApiProductEdit))
            batch = Batches(db, ACTOR).preview(
                {
                    "request_key": str(uuid4()),
                    "operation": "REVIEW_TASKS",
                    "selection": {
                        "kind": "FILTER",
                        "ids": [],
                        "query": "",
                        "filter": "all",
                    },
                }
            )
        STATE.write_text(
            json.dumps({"batch_id": batch["id"], "commercial_records_before": before})
        )
        ready = wait(lambda: (r if (r := read())["state"] == "PREVIEW" else None))
        GATE.write_text(batch["id"])
        CLAIM.unlink(missing_ok=True)
        with SessionLocal() as db:
            Batches(db, ACTOR).start(
                batch["id"],
                {
                    "confirm": True,
                    "expected_revision": ready["revision"],
                    "preview_hash": ready["preview_hash"],
                    "idempotency_key": str(uuid4()),
                },
            )
        wait(lambda: CLAIM.exists())
        assert read()["counts"].get("RUNNING", 0) > 0
        print("2R durable claim before worker death: PASS", flush=True)
    elif phase == "kill":
        marker = json.loads(CLAIM.read_text())
        pid = marker["pid"]
        command = Path(f"/proc/{pid}/cmdline").read_bytes()
        if pid <= 1 or b"integration_sandbox.editorial_executor" not in command:
            raise RuntimeError("PID no autorizado para la prueba.")
        os.kill(pid, signal.SIGKILL)
        GATE.unlink(missing_ok=True)
        resumed = wait(
            lambda: (r if (r := read())["progress"]["completed"] >= 5 else None)
        )
        assert resumed["progress"]["completed"] < 1000
        with SessionLocal() as db:
            assert (
                db.scalar(
                    select(func.max(Item.attempts)).where(
                        Item.batch_id == resumed["id"]
                    )
                )
                >= 2
            )
        print(
            "2R independent worker killed/restarted; lease recovered with two executors: PASS",
            flush=True,
        )
    elif phase == "verify":
        result = wait(
            lambda: (r if (r := read())["state"] == "COMPLETED" else None), 120
        )
        assert result["counts"] == {"COMPLETED": 1000}
        with SessionLocal() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Item)
                    .where(Item.batch_id == result["id"])
                )
                == 1000
            )
            assert (
                db.scalar(select(func.count()).select_from(EcommApiProductEdit))
                == json.loads(STATE.read_text())["commercial_records_before"]
            )
            assert not db.scalar(
                select(func.count())
                .select_from(Item)
                .where(Item.batch_id == result["id"], Item.attempts > 3)
            )
        print(
            "2R backend restart: 1000 unique tasks recovered, no commercial writes: PASS",
            flush=True,
        )
    else:
        raise RuntimeError("Fase no autorizada.")


if __name__ == "__main__":
    main()
