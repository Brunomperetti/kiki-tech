"""Activation gates: real PG only after existing disposable preflight."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import patch
from .v2_checks import sandbox
from fastapi.testclient import TestClient
from sqlalchemy import text,select
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet
from app.database.session import engine,get_db
from app.database.models import Base,MercadoLibreConnection,InventoryLinkageDecision,AdminSession
from app.main import create_app
from app.core.config import get_settings
from app.services.v2_preflight import audit,connect_readonly,inspect_schema
from app.services.v2_schema import statements
from .policy import DATABASE_URL


class Activation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.life=TestClient(sandbox,base_url='https://127.0.0.1:8443');cls.life.__enter__()
        cls.app=create_app();cls.app.state.local_synthetic=True
        cls.client=TestClient(cls.app,base_url='https://127.0.0.1:8443')
        r=cls.client.post('/api/auth/login',json={'username':'operador-prueba','password':'solo-datos-sinteticos'})
        assert r.status_code==200
        cls.csrf=r.json()['csrf_token']

    @classmethod
    def tearDownClass(cls):
        cls.client.close();cls.life.__exit__(None,None,None)

    def test_readonly_schema_matches_and_never_imports_another_engine(self):
        dbengine=connect_readonly(DATABASE_URL,'kiki_integration','kiki_integration','/var/run/postgresql')
        try:
            result=audit(dbengine,'kiki_integration','kiki_integration')
            self.assertTrue(result['transaction_read_only'])
            self.assertFalse(result['reads_user_rows'])
            self.assertEqual(result['groups'],{'core':[],'documents':[],'batches':[]})
            from sqlalchemy.exc import DBAPIError
            with dbengine.connect() as c:
                with self.assertRaises(DBAPIError) as raised:
                    c.exec_driver_sql('UPDATE catalog_snapshots SET source=source')
                self.assertEqual(raised.exception.orig.sqlstate,'25006')
        finally:dbengine.dispose()

    def test_mismatched_or_remote_target_is_rejected_before_connect(self):
        with patch('sqlalchemy.create_engine',side_effect=AssertionError('No engine for invalid target')):
            with self.assertRaises(ValueError):connect_readonly(DATABASE_URL,'wrong','kiki_integration','/var/run/postgresql')
            with self.assertRaises(ValueError):connect_readonly('postgresql://reader@production.invalid/catalog','catalog','reader','production.invalid')

    def test_all_legacy_records_ciphertext_sessions_and_versions_survive_migration_and_rollback(self):
        path='/api/ecomm-app/workspace/900002'
        before=self.client.get(path).json()
        fields=deepcopy(before['fields']);fields['title']='Ficha sintética anterior a migración'
        saved=self.client.post(path,json={'expected_version':before['version'],'fields':fields,'status':'DRAFT'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(saved.status_code,200)
        key=Fernet(Fernet.generate_key());cipher=key.encrypt(b'SYNTHETIC-TOKEN-NOT-A-CREDENTIAL').decode()
        with engine.connect() as connection:
            transaction=connection.begin()
            try:
                connection.exec_driver_sql('CREATE SCHEMA kiki_protected_copy')
                connection.exec_driver_sql('SET LOCAL search_path TO kiki_protected_copy')
                Base.metadata.create_all(connection)
                for table in Base.metadata.sorted_tables:
                    connection.exec_driver_sql(f'INSERT INTO kiki_protected_copy.{table.name} SELECT * FROM public.{table.name}')
                with Session(bind=connection) as db:
                    now=datetime.now(timezone.utc)
                    db.add(MercadoLibreConnection(user_id='SYNTHETIC-ACCOUNT',access_token=cipher,refresh_token=cipher,expires_at=now+timedelta(hours=1),connected_at=now,updated_at=now))
                    db.add(InventoryLinkageDecision(external_id='SYNTHETIC-LINK',decision='CONFIRMED',ecomm_id='900002',source_snapshot={'synthetic':True},product_snapshot={'synthetic':True},history=[{'synthetic':'before migration'}]))
                    db.commit()
                def frozen():
                    return {t.name:connection.exec_driver_sql(f'SELECT row_to_json(t)::text FROM {t.name} t ORDER BY row_to_json(t)::text').scalars().all() for t in Base.metadata.sorted_tables}
                legacy=frozen()
                for _ in range(2):
                    for statement in statements():connection.execute(text(statement.replace('public.','kiki_protected_copy.')))
                self.assertEqual(frozen(),legacy)
                self.assertEqual(inspect_schema(connection,schema='kiki_protected_copy')['groups'],{'core':[],'documents':[],'batches':[]})
                self.assertEqual(frozen(),legacy)  # preflight itself did not touch last_seen or anything else
                def db_override():
                    with Session(bind=connection) as db:yield db
                self.app.dependency_overrides[get_db]=db_override
                prior=get_settings().kiki_v2_enabled
                try:
                    get_settings().kiki_v2_enabled=False
                    self.assertEqual(self.client.get('/api/auth/me').status_code,200)
                    self.assertEqual(self.client.get(path).json()['fields'],fields)
                    self.assertEqual(self.client.get(path).json()['version'],saved.json()['version'])
                    self.assertEqual(self.client.get('/api/ui/v2',headers={'X-Kiki-UI':'v2'}).status_code,404)
                    with Session(bind=connection) as db:
                        stored=db.scalar(select(MercadoLibreConnection))
                        self.assertEqual(stored.access_token,cipher)
                        self.assertEqual(key.decrypt(stored.access_token.encode()),b'SYNTHETIC-TOKEN-NOT-A-CREDENTIAL')
                        self.assertTrue(db.scalar(select(AdminSession)))
                        self.assertEqual(db.scalar(select(InventoryLinkageDecision).where(InventoryLinkageDecision.external_id=='SYNTHETIC-LINK')).ecomm_id,'900002')
                finally:
                    get_settings().kiki_v2_enabled=prior;self.app.dependency_overrides.clear()
            finally:transaction.rollback()

    def test_v2_off_and_auto_schema_off_preserve_existing_api_without_ddl(self):
        config=get_settings();prior=(config.kiki_v2_enabled,config.kiki_auto_create_schema)
        config.kiki_v2_enabled=False;config.kiki_auto_create_schema=False
        try:
            with patch('app.database.models.Base.metadata.create_all',side_effect=AssertionError('No startup DDL')):
                with TestClient(create_app(),base_url='https://127.0.0.1:8443') as client:
                    client.cookies.update(self.client.cookies)
                    self.assertEqual(client.get('/api/auth/me').status_code,200)
                    self.assertEqual(client.get('/api/ecomm-app/stage/catalog').status_code,200)
                    self.assertEqual(client.get('/api/ui/v2',headers={'X-Kiki-UI':'v2'}).status_code,404)
        finally:config.kiki_v2_enabled,config.kiki_auto_create_schema=prior

    def test_normal_document_contract_reuses_exact_authentic_pdf_profile(self):
        import base64
        from pathlib import Path
        from pydantic import ValidationError
        from app.services.documental.contracts import Incorporate
        from app.services.documental.local_documents import parse_local
        raw=Path('/pilot-inputs/hileret-original.pdf').read_bytes()
        payload={'kind':'FILE','expected_version':0,'filename':'hileret-original.pdf','content_type':'application/pdf','content_base64':base64.b64encode(raw).decode(),'provenance_note':'PDF auténtico adjunto; sólo prueba de contrato, sin asignación de identidad real.','authorized_local_processing':True}
        body=Incorporate(**payload)
        parsed=parse_local(body)
        claims={c['field']:c for c in parsed['claims']}
        self.assertEqual(claims['ean']['value'],'7794940000796')
        self.assertEqual(claims['logistic_dun']['value'],'97794940000799')
        self.assertTrue(all('pagina/2/tabla/stevia/' in c['location'] for c in parsed['claims']))
        with self.assertRaises(ValidationError):Incorporate(**{**payload,'content_base64':base64.b64encode(raw[:-1]+b'X').decode()})
        with self.assertRaises(ValidationError):Incorporate(**{**payload,'content_base64':'A'*699056})

    def test_reader_normal_route_preserves_rejection_and_previous_dossier(self):
        import base64
        root='/api/ecomm-app/workspace/900003'
        dossier=self.client.get(root+'/evidence',headers={'X-Kiki-UI':'v2'}).json()
        result=self.client.post(root+'/documents/import',headers={'X-Kiki-UI':'v2','X-CSRF-Token':self.csrf},json={'kind':'FILE','expected_version':dossier['version'],'filename':'bad.pdf','content_type':'application/pdf','content_base64':base64.b64encode(b'not a pdf').decode(),'provenance_note':'Rechazo explícito de documento de prueba inválido.','authorized_local_processing':True})
        self.assertEqual(result.status_code,409)
        self.assertEqual(self.client.get(root+'/evidence',headers={'X-Kiki-UI':'v2'}).json()['documents'],dossier['documents'])


if __name__=='__main__':unittest.main(verbosity=2)
