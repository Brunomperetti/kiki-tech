"""Synthetic PG18 only; never connects to a production database."""
import os

if (os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("KIKI_CI_SYNTHETIC_ONLY") != "1"):
    raise SystemExit("Only CI disposable PostgreSQL may run this smoke.")

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from threading import Barrier  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.services.channel_dispatch import (  # noqa: E402
    DispatchConflict, reserve, begin, confirm, read_receipt,
)
from app.services.channel_dispatch_migration import UP, DOWN  # noqa: E402
from app.services.channel_dispatch_storage import ChannelDispatch  # noqa: E402


def main():
    engine = create_engine(
        "postgresql+psycopg://kiki_ci:synthetic_ci_only@127.0.0.1:5432/kiki_ci_synthetic",
        connect_args={"connect_timeout": 5, "options": "-c lock_timeout=5000 -c statement_timeout=15000"},
    )
    with engine.begin() as db:
        assert tuple(db.execute(text("SELECT current_database(), current_user")).one()) == (
            "kiki_ci_synthetic", "kiki_ci",
        )
        assert int(db.execute(text("SHOW server_version_num")).scalar_one()) // 10000 == 18
        for sql in UP:
            db.exec_driver_sql(sql)
        cols = set(db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='kiki_channel_dispatch'"
        )).scalars())
        assert cols == {col.name for col in ChannelDispatch.__table__.columns}
    barrier = Barrier(2, timeout=10)

    def contender(ecomm_id):
        with Session(engine) as db:
            barrier.wait()
            try:
                return reserve(db, channel="tn", store_id="123", ecomm_id=ecomm_id,
                               sku="TEST", fingerprint="a" * 64, actor="synthetic")
            except DispatchConflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(contender, ("456", "789")))
    winners = [result for result in results if result]
    assert len(winners) == 1, results
    ident = winners[0]
    with Session(engine) as db:
        assert begin(db, ident, 1) == 2
    with Session(engine) as db:
        assert read_receipt(db, ident)["state"] == "IN_FLIGHT"
        try:
            begin(db, ident, 1)
        except DispatchConflict:
            pass
        else:
            raise AssertionError("Stale revision accepted")
        assert confirm(db, ident, 2, "987") == 3
    with engine.begin() as db:
        try:
            with db.begin_nested():
                for sql in DOWN:
                    db.exec_driver_sql(sql)
        except DBAPIError as exc:
            assert "KIKI_DISPATCH_DOWN_BLOCKED_NONEMPTY" in str(exc)
        else:
            raise AssertionError("Nonempty dispatch table dropped")
        assert db.execute(text("SELECT count(*) FROM public.kiki_channel_dispatch")).scalar_one() == 1
        # Synthetic fixture cleanup only; never a production procedure.
        db.execute(text("DELETE FROM public.kiki_channel_dispatch"))
        for sql in DOWN:
            db.exec_driver_sql(sql)
        assert db.execute(text("SELECT to_regclass('public.kiki_channel_dispatch')")).scalar_one() is None
    engine.dispose()
    print("PG18 dispatch: unique concurrent reservation, durable receipt and empty-only rollback PASS")


if __name__ == "__main__":
    main()
