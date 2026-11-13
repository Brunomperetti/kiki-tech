"""Same-origin production contracts, executed ONLY after disposable preflight."""
from copy import deepcopy
import unittest
from .bootstrap import create_sandbox_app

sandbox = create_sandbox_app(production_compat=True)
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from app.main import create_app  # noqa: E402
from app.core.config import get_settings, Settings  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.database.models import Base, CatalogSnapshot  # noqa: E402
from app.api.routes.v2 import capabilities  # noqa: E402
from app.services.v2_schema import statements  # noqa: E402


class V2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed_client = TestClient(sandbox)
        cls.seed_client.__enter__()
        # Normal FastAPI routers: no synthetic authentication or ID allowlists.
        cls.app = create_app()
        cls.app.state.local_synthetic = True
        cls.client = TestClient(cls.app,base_url="https://127.0.0.1:8443")
        cls.client.headers['X-Kiki-UI'] = 'v2'
        auth = cls.client.post('/api/auth/login', json={'username':'operador-prueba','password':'solo-datos-sinteticos'})
        assert auth.status_code == 200
        cls.csrf = auth.json()['csrf_token']
        cls.original_flags = {k:getattr(get_settings(),k) for k in ('kiki_v2_enabled','kiki_v2_writes_enabled','kiki_v2_connections_enabled','kiki_v2_ai_generation_enabled')}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.seed_client.__exit__(None,None,None)

    def tearDown(self):
        for key,value in self.original_flags.items(): setattr(get_settings(),key,value)

    def test_capabilities_authenticated_and_default_off(self):
        c=TestClient(self.app,base_url="https://127.0.0.1:8443")
        c.headers['X-Kiki-UI']='v2'
        self.assertEqual(c.get('/api/ui/v2').status_code,401)
        c.close()
        for key in self.original_flags: self.assertFalse(getattr(Settings(_env_file=None),key))
        response=self.client.get('/api/ui/v2')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['X-Kiki-UI-Contract'],'kiki-same-origin-v2-1')
        self.assertEqual(response.json()['missing_schema'],{'core':[],'documents':[],'batches':[]})
        self.assertFalse(response.json()['external_research'])
        self.assertFalse(response.json()['openai_generation'])
        self.assertTrue(response.json()['synthetic'])

    def test_disable_ui_preserves_classic(self):
        get_settings().kiki_v2_enabled=False
        self.assertEqual(self.client.get('/api/ecomm-app/stage/catalog').status_code,404)
        self.assertEqual(self.client.get('/api/ui/v2').status_code,404)
        self.assertEqual(self.client.get('/api/ecomm-app/stage/catalog',headers={'X-Kiki-UI':'classic'}).status_code,200)

    def test_read_only_blocks_writes_and_provider_actions(self):
        get_settings().kiki_v2_writes_enabled=False
        for path in ['/api/ecomm-app/workspace/900001','/api/ecomm-app/editorial-batches/preview','/api/ecomm-app/stage/manual/start','/api/mercadolibre/sync','/api/tiendanube/import-csv']:
            self.assertEqual(self.client.post(path,json={},headers={'X-CSRF-Token':self.csrf}).status_code,403)
        self.assertEqual(self.client.get('/api/ecomm-app/workspace/900001').status_code,200)

    def test_connections_and_openai_still_denied_when_writes_on(self):
        for path in ['/api/ecomm-app/stage/manual/start','/api/mercadolibre/auth-url','/api/mercadolibre/sync','/api/tiendanube/import-csv','/api/ecomm-app/workspace/ai/900001/suggest']:
            self.assertEqual(self.client.post(path,json={'expected_version':0},headers={'X-CSRF-Token':self.csrf}).status_code,403)
        self.assertFalse(self.client.get('/api/connections/status').json()['actions_enabled'])

    def test_original_editor_csrf_persistence_history_and_conflict(self):
        path='/api/ecomm-app/workspace/900002'
        before=self.client.get(path).json()
        fields=deepcopy(before['fields']);fields['title']='Título sintético compatibilidad V2'
        body={'fields':fields,'status':'DRAFT','expected_version':before['version']}
        self.assertEqual(self.client.post(path,json=body).status_code,403)
        saved=self.client.post(path,json=body,headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.client.post(path,json=body,headers={'X-CSRF-Token':self.csrf}).status_code,409)
        loaded=self.client.get(path).json()
        self.assertEqual(loaded['fields']['title'],fields['title'])
        self.assertEqual(len(loaded['fields']),18)
        self.assertEqual(loaded['version'],before['version']+1)
        self.assertTrue(loaded['history'])

    def test_nonfixture_id_not_translated_or_fused(self):
        with SessionLocal() as db:
            capture=db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source=='ECOMM_APP_API_STAGE'))
            original=deepcopy(capture.payload)
            payload=deepcopy(original)
            payload[0]['items'][0]['variants'][0]['id']='VARIANT-781251'
            capture.payload=payload;db.commit()
        try:
            v=self.client.get('/api/ecomm-app/workspace/VARIANT-781251')
            self.assertEqual(v.status_code,200,v.text)
            self.assertEqual(v.json()['ecomm_id'],'VARIANT-781251')
            self.assertEqual(self.client.get('/api/ecomm-app/workspace/900001').status_code,409)
            self.assertEqual(self.client.get('/api/ecomm-app/workspace/900002').status_code,200)
        finally:
            with SessionLocal() as db:
                c=db.scalar(select(CatalogSnapshot).where(CatalogSnapshot.source=='ECOMM_APP_API_STAGE'))
                c.payload=original;db.commit()

    def test_additive_migrations_on_legacy_structure_copy_preserve_data(self):
        # Author-created fixtures only. No customer snapshot exists locally.
        # Transactional schema copy of existing Base; NEVER production and no secrets copied.
        with engine.connect() as connection:
            transaction=connection.begin()
            try:
                connection.execute(text('CREATE SCHEMA v2_compatibility_copy'))
                connection.execute(text('SET LOCAL search_path TO v2_compatibility_copy'))
                Base.metadata.create_all(connection)
                for table in ('catalog_snapshots','ecomm_api_product_edits'):
                    connection.execute(text(f'INSERT INTO v2_compatibility_copy.{table} SELECT * FROM public.{table}'))
                def snapshot():
                    return {table:connection.execute(text(f'SELECT row_to_json(t) FROM {table} t ORDER BY id')).scalars().all() for table in ('catalog_snapshots','ecomm_api_product_edits')}
                before=snapshot()
                for _ in range(2):
                    for statement in statements():connection.execute(text(statement.replace("public.","v2_compatibility_copy.")))
                self.assertEqual(snapshot(),before)
                with SessionLocal(bind=connection) as db:
                    self.assertEqual(capabilities(db)['missing_schema'],{'core':[],'documents':[],'batches':[]})
                # Existing table names without columns do not pass readiness.
                connection.execute(text('ALTER TABLE kiki_evidence_documents DROP COLUMN digest'))
                with SessionLocal(bind=connection) as db:
                    self.assertIn('kiki_evidence_documents.digest',capabilities(db)['missing_schema']['documents'])
                    self.assertFalse(capabilities(db)['documents'])
            finally:transaction.rollback()

    def test_original_executor_lifecycle_is_opt_in_and_no_new_queue(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.services.v2_lifecycle import start_executor, stop_executor
        config=get_settings()
        original=config.kiki_editorial_executor_enabled
        app=SimpleNamespace(state=SimpleNamespace())
        try:
            config.kiki_editorial_executor_enabled=False
            self.assertIsNone(start_executor(app,SessionLocal))
            config.kiki_editorial_executor_enabled=True
            with patch('app.services.editorial_batches.executor.Executor.run',side_effect=lambda stop: stop.wait(2)) as run:
                handle=start_executor(app,SessionLocal)
                self.assertIsNotNone(handle)
                stop_executor(handle)
                self.assertFalse(handle[1].is_alive())
                run.assert_called_once()
            app.state.local_synthetic=True
            self.assertIsNone(start_executor(app,SessionLocal))
        finally:config.kiki_editorial_executor_enabled=original

    def test_no_automatic_ddl_or_provider_in_readiness(self):
        from unittest.mock import patch
        with patch('socket.getaddrinfo',side_effect=AssertionError('No DNS')), patch('app.database.models.Base.metadata.create_all',side_effect=AssertionError('No DDL')):
            self.assertEqual(self.client.get('/api/ui/v2').status_code,200)
            self.assertEqual(self.client.get('/api/connections/status').status_code,200)
        self.assertEqual(self.client.get('/api/ecomm-app/workspace/PILOT-HILERET-200-UNIT-SYNTHETIC').status_code,409)


if __name__=='__main__':unittest.main(verbosity=2)
