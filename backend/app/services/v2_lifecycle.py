"""Attach the EXISTING executor to the existing API only on explicit rollout.

No provider work, no migration, no new queue. The disposable harness already
supervises the same executor and therefore does not start a second one here.
"""
import logging
from threading import Event, Thread
from app.core.config import get_settings


def start_executor(application, factory):
    config = get_settings()
    if getattr(application.state, "local_synthetic", False) or not (
        config.kiki_v2_enabled and config.kiki_editorial_executor_enabled
    ):
        return None
    from app.api.routes.v2 import capabilities
    from app.services.editorial_batches.executor import Executor

    with factory() as db:
        if not capabilities(db)["batches"]:
            raise RuntimeError("Ejecutor bloqueado: esquema y configuración editorial pendientes.")
    stop = Event()
    executor = Executor(factory)

    def run():
        try:
            executor.run(stop)
        except Exception:
            logging.getLogger(__name__).error("Ejecutor editorial detenido; trabajos persistidos, revisar operación.")

    worker = Thread(target=run, name="kiki-editorial-existing", daemon=True)
    application.state.v2_executor = worker
    worker.start()
    return stop, worker


def stop_executor(handle):
    if handle:
        stop, worker = handle
        stop.set()
        worker.join(timeout=35)
