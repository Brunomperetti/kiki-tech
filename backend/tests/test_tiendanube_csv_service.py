import pytest
from app.services.tiendanube_csv_service import parse_tiendanube_csv, TiendanubeCsvService
from app.database.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def sample_csv():
    return ('Identificador de URL;Nombre;SKU;Precio;Stock;Marca;Código de barras;Descripción\n'
            'item-1;Producto 1;00012;1,200.50;4;Marca;7798010000000.0;Texto\n'
            'item-2;Producto 2;00013;350.00;0;Marca;7798010000000.0;Texto\n').encode('utf-8')


def test_parser_keeps_sku_and_barcode_original():
    items = parse_tiendanube_csv(sample_csv())
    assert len(items) == 2
    assert items[0]['sku'] == '00012'
    assert items[0]['ean_raw'] == '7798010000000.0'
    assert items[0]['price'] == '1200.50'


def test_import_is_separate_snapshot_and_matching_is_conservative():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = TiendanubeCsvService(db)
        svc.repo.save_snapshot('ECOMM_APP', [{'ecomm_id': 'X', 'sku': '00012'}])
        result = svc.import_csv('products.csv', sample_csv())
        report = svc.report()
        assert result['products'] == 2
        assert report['summary']['MATCHED_SKU'] == 1
        assert report['summary']['UNMATCHED_SKU'] == 1
        assert svc.repo.snapshot('ECOMM_APP') == [{'ecomm_id': 'X', 'sku': '00012'}]


def test_invalid_csv_fails_without_import():
    with pytest.raises(ValueError):
        parse_tiendanube_csv(b'wrong;headers\nA;B\n')
