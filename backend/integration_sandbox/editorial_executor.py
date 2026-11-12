"""Standalone disposable worker; preflight BEFORE all application/engine imports."""

import json
import os
from pathlib import Path
import signal
from threading import Event


def main():
    from .bootstrap import create_sandbox_app

    create_sandbox_app(autonomous=True)
    from app.database.session import SessionLocal
    from app.services.editorial_batches.executor import Executor

    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    class InstrumentedExecutor(Executor):
        def after_claim(self, claim):
            gate = Path("/runtime/editorial-test-pause-after-claim")
            if (
                gate.exists()
                and gate.read_text().strip() == claim[0]
                and claim[3] == "PROCESS"
            ):
                marker = Path("/runtime/editorial-test-claimed.json")
                marker.write_text(
                    json.dumps(
                        {
                            "batch_id": claim[0],
                            "pid": os.getpid(),
                            "executor_id": self.ident,
                        }
                    )
                )
                while gate.exists() and not stop.is_set():
                    stop.wait(0.05)
                if stop.is_set():
                    raise SystemExit(0)

    executor = InstrumentedExecutor(SessionLocal)
    path = Path(f"/runtime/editorial-worker-{os.getpid()}.json")
    path.write_text(json.dumps({"pid": os.getpid(), "executor_id": executor.ident}))
    try:
        executor.run(stop)
    finally:
        path.unlink(missing_ok=True)
        from app.database.session import engine

        engine.dispose()


if __name__ == "__main__":
    main()
