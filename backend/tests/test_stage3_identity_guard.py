"""Manufacturer I/O cannot bypass raw variant/parent identity; synthetic only."""

from copy import deepcopy
import base64
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CatalogSnapshot, EcommApiProductEdit
from app.services.documental.explicit_url_intake import import_explicit_url
from app.services.documental.manufacturer_batch_intake import (
    _eligible_unit,
    _identity,
    capture_selected,
)
from app.services.documental.storage import Document, Dossier
from test_documental_complete_draft_flow import IDENT
from test_documental_explicit_url_intake import (
    setup,
    kwargs,
    fake_downloader,
    HTML,
    ALT,
)
from test_documental_manufacturer_batch_intake import (
    FIRST,
    HASH,
    HOST,
    SITEMAP,
    candidate,
    preview,
    parse_source,
)


def _unit(**changes):
    return {
        "ecomm_id": "123",
        "sku": "SYNTHETIC-UNIT",
        "parent_code": "FAMILY",
        "product_name": "Synthetic unit 250 g",
        "variant_description": "250 g",
        "gtin": "7794940000796",
        "gtin_raw": "7794940000796",
        "barcode": None,
        "is_combo": False,
        "parent_is_combo": False,
        "identity_blockers": [],
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"parent_is_combo": True},
        {"parent_is_combo": 0},
        {"is_combo": None},
        {"is_combo": 0},
        {"barcode": "036000291452"},
        {"barcode": 7794940000796},
        {"identity_blockers": ["BARCODE_GTIN_CONFLICT"]},
        {"sku": " "},
    ],
)
def test_unit_eligibility_rejects_pack_parent_and_raw_conflicts(changes):
    assert not _eligible_unit(_unit(**changes))


def test_missing_code_and_unknown_parent_do_not_invent_identity_or_approval():
    assert _eligible_unit(_unit(parent_is_combo=None))
    assert _eligible_unit(_unit(gtin=None, gtin_raw=None, barcode=None))


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("barcode", "7794940000796"),
        ("gtin_raw", None),
        ("parent_is_combo", True),
        ("parent_is_combo", None),
        ("is_combo", 0),
        ("parent_code", "OTHER-FAMILY"),
        ("identity_blockers", ["BARCODE_GTIN_CONFLICT"]),
    ],
)
def test_full_identity_detects_drift_and_survives_json_queue_persistence(
    field, replacement
):
    baseline = _unit()
    stored = json.loads(json.dumps(list(_identity(baseline))))
    assert tuple(stored) == _identity(baseline)
    assert tuple(stored) != _identity({**baseline, field: replacement})


def _change_capture(db, *, parent=None, variant=None):
    snap = db.scalar(
        select(CatalogSnapshot).where(CatalogSnapshot.source == "ECOMM_APP_API_STAGE")
    )
    pages = deepcopy(snap.payload)
    if parent:
        pages[0]["items"][0].update(parent)
    if variant:
        pages[0]["items"][0]["variants"][0].update(variant)
    snap.payload = pages
    db.commit()


@pytest.mark.parametrize("change", ["pack_parent", "code_conflict"])
def test_both_intake_paths_block_before_any_source_requests(
    tmp_path, monkeypatch, change
):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        _change_capture(
            db,
            parent={"is_combo": True} if change == "pack_parent" else {},
            variant={"gtin": "7794940000796", "barcode": "036000291452"}
            if change == "code_conflict"
            else {},
        )
        existing = {doc.id for doc in db.scalars(select(Document))}

        def no_network(*_a, **_k):
            pytest.fail("Rejected identity must not fetch")

        with pytest.raises(ValueError):
            import_explicit_url(
                db, SimpleNamespace(id=1), **kwargs(downloader=no_network)
            )
        db.rollback()
        with pytest.raises(ValueError):
            capture_selected(
                db,
                SimpleNamespace(id=1),
                sitemap_url=SITEMAP,
                sitemap_sha256=HASH,
                items=[{"ecomm_id": IDENT, "url": FIRST}],
                configured_hosts=HOST,
                previewer=no_network,
                downloader=no_network,
            )
        db.rollback()
        assert {doc.id for doc in db.scalars(select(Document))} == existing
        assert db.scalars(select(Dossier)).all() == []
        assert db.scalars(select(EcommApiProductEdit)).all() == []


@pytest.mark.parametrize("path", ["exact", "sitemap"])
def test_same_variant_sha_under_alternate_url_cannot_duplicate_or_relabel(
    tmp_path,
    monkeypatch,
    path,
):
    from app.services.documental.storage import digest

    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        old = db.scalars(select(Document)).one()
        body = deepcopy(old.body)
        body["source"]["reference_url"] = ALT
        body["original"].update(size=len(HTML), sha256=sha256(HTML).hexdigest())
        body["original_base64"] = base64.b64encode(HTML).decode("ascii")
        old.body, old.digest = body, digest(body)
        old.history = [{"action": "SYNTHETIC_PRIOR_HISTORY"}]
        db.commit()
        previous = deepcopy((old.body, old.history, old.digest, old.version))
        old_id = old.id
        with pytest.raises(ValueError, match="mismo original SHA-256"):
            if path == "exact":
                import_explicit_url(db, SimpleNamespace(id=1), **kwargs())
            else:
                capture_selected(
                    db,
                    SimpleNamespace(id=1),
                    sitemap_url=SITEMAP,
                    sitemap_sha256=HASH,
                    items=[{"ecomm_id": IDENT, "url": FIRST}],
                    configured_hosts=HOST,
                    previewer=lambda *_a, **_k: preview(candidate(IDENT, FIRST)),
                    downloader=fake_downloader,
                    parser=parse_source,
                )
        db.rollback()
        assert db.scalars(select(Document.id)).all() == [old_id]
        restored = db.get(Document, old_id)
        assert (
            restored.body,
            restored.history,
            restored.digest,
            restored.version,
        ) == previous
        assert db.scalars(select(Dossier)).all() == []
        assert db.scalars(select(EcommApiProductEdit)).all() == []


@pytest.mark.parametrize("path", ["exact", "sitemap"])
@pytest.mark.parametrize("change", ["raw_barcode", "parent_pack"])
def test_identity_drift_during_fetch_cannot_archive_or_approve(
    tmp_path,
    monkeypatch,
    path,
    change,
):
    engine = setup(tmp_path, monkeypatch)
    with Session(engine) as db:
        # Adding a concordant raw barcode leaves the old compatibility `gtin`
        # unchanged, but must still invalidate the operator's exact selection.
        _change_capture(db, variant={"gtin": "7794940000796", "barcode": None})
        existing = {doc.id for doc in db.scalars(select(Document))}

        def changing_fetch(url, hosts, *, max_bytes):
            with Session(engine) as other:
                _change_capture(
                    other,
                    parent={"is_combo": True} if change == "parent_pack" else {},
                    variant={"barcode": "7794940000796"}
                    if change == "raw_barcode"
                    else {},
                )
            return fake_downloader(url, hosts, max_bytes=max_bytes)

        with pytest.raises(ValueError, match="cambi"):
            if path == "exact":
                import_explicit_url(
                    db,
                    SimpleNamespace(id=1),
                    **kwargs(downloader=changing_fetch),
                )
            else:
                capture_selected(
                    db,
                    SimpleNamespace(id=1),
                    sitemap_url=SITEMAP,
                    sitemap_sha256=HASH,
                    items=[{"ecomm_id": IDENT, "url": FIRST}],
                    configured_hosts=HOST,
                    previewer=lambda *_a, **_k: preview(candidate(IDENT, FIRST)),
                    downloader=changing_fetch,
                    parser=parse_source,
                )
        db.rollback()
        assert {doc.id for doc in db.scalars(select(Document))} == existing
        assert db.scalars(select(Dossier)).all() == []
        assert db.scalars(select(EcommApiProductEdit)).all() == []
