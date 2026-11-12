# Archivos del cierre funcional

No se modificaron modelos, configuración productiva, integraciones de proveedores, main, credenciales ni Render. No hay migraciones nuevas. Se conservan los artefactos históricos: se agregan sólo las capturas nuevas con prefijo functional-.

## Backend reutilizado y proyecciones de lectura

- [backend/app/api/routes/ecomm_api_channels.py](../backend/app/api/routes/ecomm_api_channels.py)
- [backend/app/api/routes/ecomm_api_workspace.py](../backend/app/api/routes/ecomm_api_workspace.py)
- [backend/app/api/routes/editorial_batches.py](../backend/app/api/routes/editorial_batches.py)
- [backend/app/services/ecomm_api_work_queue_service.py](../backend/app/services/ecomm_api_work_queue_service.py)
- [backend/app/services/ecomm_catalog_quality.py](../backend/app/services/ecomm_catalog_quality.py)
- [backend/app/services/ecomm_channel_coverage_service.py](../backend/app/services/ecomm_channel_coverage_service.py)
- [backend/app/services/ecomm_channel_listings.py](../backend/app/services/ecomm_channel_listings.py)
- [backend/app/services/editorial_batches/queue_projection.py](../backend/app/services/editorial_batches/queue_projection.py)

## Arnés y pruebas aisladas

- [backend/integration_sandbox/catalog_operations_checks.py](../backend/integration_sandbox/catalog_operations_checks.py)
- [backend/integration_sandbox/policy.py](../backend/integration_sandbox/policy.py)
- [backend/integration_sandbox/presentation_fixtures.py](../backend/integration_sandbox/presentation_fixtures.py)
- [backend/integration_sandbox/verify.py](../backend/integration_sandbox/verify.py)
- [integration/browser_tests.py](../integration/browser_tests.py)
- [integration/run.py](../integration/run.py)

## Interfaz compartida

- [frontend/src/components/CommercialBackofficeFields.tsx](../frontend/src/components/CommercialBackofficeFields.tsx)
- [frontend/src/integration/CommercialViews.tsx](../frontend/src/integration/CommercialViews.tsx)
- [frontend/src/integration/IntegrationCatalog.tsx](../frontend/src/integration/IntegrationCatalog.tsx)
- [frontend/src/integration/PersistentWorkspace.tsx](../frontend/src/integration/PersistentWorkspace.tsx)
- [frontend/src/integration/SavedHistory.tsx](../frontend/src/integration/SavedHistory.tsx)
- [frontend/src/integration/catalog-adapter.ts](../frontend/src/integration/catalog-adapter.ts)
- [frontend/src/integration/commercial-views.css](../frontend/src/integration/commercial-views.css)
- [frontend/src/integration/isolation.ts](../frontend/src/integration/isolation.ts)
- [frontend/src/integration/workspace-adapter.ts](../frontend/src/integration/workspace-adapter.ts)
- [frontend/src/prototype/CatalogView.tsx](../frontend/src/prototype/CatalogView.tsx)
- [frontend/src/prototype/Dashboard.tsx](../frontend/src/prototype/Dashboard.tsx)
- [frontend/src/prototype/OperationalPanel.tsx](../frontend/src/prototype/OperationalPanel.tsx)
- [frontend/src/prototype/SettingsDialog.tsx](../frontend/src/prototype/SettingsDialog.tsx)
- [frontend/src/prototype/commercial-demo.ts](../frontend/src/prototype/commercial-demo.ts)
- [frontend/src/prototype/operations-model.ts](../frontend/src/prototype/operations-model.ts)

## Pruebas de navegador

- [frontend/integration-tests/functional-catalog.spec.ts](../frontend/integration-tests/functional-catalog.spec.ts)
- [frontend/integration-tests/presentation-connected.spec.ts](../frontend/integration-tests/presentation-connected.spec.ts)
- [frontend/tests/channel-coverage.spec.ts](../frontend/tests/channel-coverage.spec.ts)
- [frontend/tests/dashboard.spec.ts](../frontend/tests/dashboard.spec.ts)
- [frontend/tests/functional-catalog.spec.ts](../frontend/tests/functional-catalog.spec.ts)
- [frontend/tests/simple-dashboard.spec.ts](../frontend/tests/simple-dashboard.spec.ts)

## Documentación

- [integration/FUNCTIONAL-CLOSE.md](../integration/FUNCTIONAL-CLOSE.md)
- [integration/FUNCTIONAL-FILES.md](../integration/FUNCTIONAL-FILES.md)
- [integration/FUNCTIONAL-PARITY.md](../integration/FUNCTIONAL-PARITY.md)
- [integration/FUNCTIONAL-VALIDATION.md](../integration/FUNCTIONAL-VALIDATION.md)
- [integration/ONLINE-PRESENTATION-PLAN.md](../integration/ONLINE-PRESENTATION-PLAN.md)
- [integration/README.md](../integration/README.md)

## Capturas y resultados

- [frontend/artifacts/functional-authentic-antes-desktop.png](../frontend/artifacts/functional-authentic-antes-desktop.png)
- [frontend/artifacts/functional-authentic-antes-mobile.png](../frontend/artifacts/functional-authentic-antes-mobile.png)
- [frontend/artifacts/functional-authentic-guardado-desktop.png](../frontend/artifacts/functional-authentic-guardado-desktop.png)
- [frontend/artifacts/functional-authentic-guardado-mobile.png](../frontend/artifacts/functional-authentic-guardado-mobile.png)
- [frontend/artifacts/functional-catalog-dashboard-desktop.png](../frontend/artifacts/functional-catalog-dashboard-desktop.png)
- [frontend/artifacts/functional-catalog-dashboard-mobile.png](../frontend/artifacts/functional-catalog-dashboard-mobile.png)
- [frontend/artifacts/functional-catalog-editor-desktop.png](../frontend/artifacts/functional-catalog-editor-desktop.png)
- [frontend/artifacts/functional-catalog-editor-mobile.png](../frontend/artifacts/functional-catalog-editor-mobile.png)
- [frontend/artifacts/functional-catalog-ml-desktop.png](../frontend/artifacts/functional-catalog-ml-desktop.png)
- [frontend/artifacts/functional-catalog-ml-mobile.png](../frontend/artifacts/functional-catalog-ml-mobile.png)
- [frontend/artifacts/functional-catalog-quality-desktop.png](../frontend/artifacts/functional-catalog-quality-desktop.png)
- [frontend/artifacts/functional-catalog-quality-mobile.png](../frontend/artifacts/functional-catalog-quality-mobile.png)
- [frontend/artifacts/functional-demo-dashboard-desktop.png](../frontend/artifacts/functional-demo-dashboard-desktop.png)
- [frontend/artifacts/functional-demo-dashboard-mobile.png](../frontend/artifacts/functional-demo-dashboard-mobile.png)
- [frontend/artifacts/functional-demo-editor-desktop.png](../frontend/artifacts/functional-demo-editor-desktop.png)
- [frontend/artifacts/functional-demo-editor-mobile.png](../frontend/artifacts/functional-demo-editor-mobile.png)
- [frontend/artifacts/functional-flow-hileret-desktop.png](../frontend/artifacts/functional-flow-hileret-desktop.png)
- [frontend/artifacts/functional-flow-hileret-mobile.png](../frontend/artifacts/functional-flow-hileret-mobile.png)
- [frontend/artifacts/functional-flow-lote-desktop.png](../frontend/artifacts/functional-flow-lote-desktop.png)
- [frontend/artifacts/functional-flow-lote-mobile.png](../frontend/artifacts/functional-flow-lote-mobile.png)
- [frontend/artifacts/functional-flow-propuesta-desktop.png](../frontend/artifacts/functional-flow-propuesta-desktop.png)
- [frontend/artifacts/functional-flow-propuesta-mobile.png](../frontend/artifacts/functional-flow-propuesta-mobile.png)
- [frontend/artifacts/functional-validation.json](../frontend/artifacts/functional-validation.json)

Total: 64 archivos modificados o agregados. Inventario contrastado con el commit local antes de entregar.
