# Integración productiva de KIKI Tech 2.0: preparación y activación controlada

> Informe histórico de la preparación `3500c4b`. El empaquetado del lector y el cierre técnico posterior se describen en [ACTIVATION-CHECKLIST.md](ACTIVATION-CHECKLIST.md); sus resultados y gates de despliegue tienen precedencia sobre las limitaciones históricas de este documento.

Base: `235b4f0fb5daf7399f2142b962841760a6d7934b`, rama `feature/kiki-tech-2-dashboard`, árbol inicialmente limpio. Preparado el 12/11/2026 para revisión. **No hubo consultas a producción, sincronizaciones, OpenAI real, cambios en Render, push, PR, merge ni despliegue.**

## Qué implementa esta entrega

Un build productivo explícito, separado del build demo y del de integración: `npm run build:production` produce `frontend/.production-dist`. La misma aplicación sirve la interfaz anterior y `/v2/`; no hay un segundo catálogo, servicio de fichas, base comercial o integración. El controlador del dashboard, editor, evidencias, propuestas, canales, lotes y conexiones es el ya existente. Se extrajo la entrada anterior a `LegacyApp.tsx` para poder usarla sin instalar las restricciones de la demo. La demo conserva `npm run build`, su aislamiento, fixtures y rutas antiguas.

El build productivo rechaza variables `VITE_*`, ignora `.env`, usa exclusivamente `/api/` del mismo origen y rechaza incluir controladores o módulos de datos demo. No permite seleccionar un upstream, usar endpoints `test-*`, seguir redirecciones de API ni reemplazar errores por fixtures. CSP restringe conexiones a `self`; fuentes, imágenes y videos externos no se descargan automáticamente. Sus URLs se conservan como texto.

`/v2/` muestra el acceso habitual. `/api/auth/me`, login/logout, cookie Secure/HttpOnly, CSRF y sesión existentes se reutilizan. El HTML estático no contiene datos privados; todas las lecturas y operaciones requieren la autenticación original. No se inventó un sistema de roles: se conservan los permisos administrativos que ya tiene KIKI. El contrato autenticado `GET /api/ui/v2` valida disponibilidad y estructura; no consulta proveedores, crea tablas, renueva tokens ni hace migraciones. Las solicitudes del dashboard llevan `X-Kiki-UI: v2`; FastAPI aplica sus controles de activación adicionales. Esto no cambia los permisos de la interfaz anterior ni convierte PostgreSQL completo en una base de sólo lectura.

La tabla utiliza la captura API completa existente y la cola editorial original. Conserva Ecomm ID, SKU, barcode, GTIN, presentación, combo, stock y fecha. Las cinco vistas, calidad, filtros, URL y publicaciones sin vínculo utilizan los mismos endpoints ya desarrollados. No se eliminan ni convierten registros de Excel. Las evidencias se consultan por Ecomm ID exacto; los pilotos sintéticos MAMA/Hileret no aparecen en el modo productivo ni transfieren sus aprobaciones. Hileret real sigue pendiente de identidad.

Las cinco pestañas reutilizan el editor de 18 campos y sus versiones, 409 e historial. Los controles de escritura quedan deshabilitados cuando la activación es de sólo lectura. Evidencias, Canales y Lotes muestran su falta de habilitación sin aparentar funcionamiento. La evidencia persistida y las fuentes de la ficha no se sustituyen. Los estados de publicación, candidatura, preparación, conflicto y error de captura conservan sus reglas anteriores.

El Centro de conexiones muestra las capturas y autorizaciones guardadas, sin sondas al proveedor. Sus actualizaciones sólo se ejecutan tras habilitación y confirmación humana; el modo inicial no las permite. Reutiliza el bloqueo manual/programado de Ecomm-App y la conservación de capturas/fichas. No se añade ningún cron: siguen 08:25 y 16:25 de Argentina, sujetos a la activación efectiva de GitHub Actions. ML conserva su token y no obliga a repetir OAuth; su callback histórico vuelve a `/channels`. Desde allí se puede volver a `/v2/`. TN sigue siendo CSV, sin afirmación de publicación actual.

## Controles de activación

Todos los controles nuevos son **false por defecto**. No se cambiaron credenciales ni el presupuesto existente.

| Configuración | Alcance |
|---|---|
| `KIKI_V2_ENABLED` | Acceso al contrato y datos del dashboard. Con false, la interfaz anterior conserva sus contratos. Con true, el arranque ya no ejecuta el `Base.metadata.create_all` histórico. |
| `KIKI_V2_WRITES_ENABLED` | Autoriza operaciones internas de `/v2/`; no saltea CSRF, validación, versión o confirmación. Inicialmente false. |
| `KIKI_V2_CONNECTIONS_ENABLED` | Permite las cuatro acciones existentes del Centro, junto con escritura habilitada. Inicialmente false. |
| `KIKI_V2_AI_GENERATION_ENABLED` | Permite solicitar el generador OpenAI histórico; también requiere `KIKI_AI_ENABLED`, clave existente, escritura y cuota. Inicialmente false. |
| `KIKI_DOCUMENT_WORKSPACE_ENABLED` | Flag existente; requiere tablas, columnas, índice y fila de control documental. |
| `KIKI_CHANNEL_WORKSPACE_ENABLED` | Flag existente; revisión por variante, con las tablas originales validadas. |
| `KIKI_EDITORIAL_BATCHES_ENABLED` | Flag existente; requiere documentación y esquema de lotes validado. |
| `KIKI_EDITORIAL_EXECUTOR_ENABLED` | Flag existente; conecta el `Executor` ya desarrollado al ciclo del FastAPI existente cuando v2 está habilitado. No crea una nueva cola o servicio. |

La comprobación de esquema informa nombres de elementos faltantes, sin contenido comercial ni secretos. No certifica por sí sola igualdad de tipos, constraints, datos o compatibilidad con una base productiva desconocida: eso requiere comparar el esquema y validar la copia autorizada. El ejecutor utiliza leases e idempotencia existentes, se detiene con el proceso y conserva los trabajos en PostgreSQL. No arranca en el arnés sintético, que ya supervisa ese mismo ejecutor por separado. No realiza IA externa ni publicaciones. Los lotes necesitan previsualización y confirmación; no hay aprobación masiva automática.

## Servicios y contratos conservados

- Catálogo: `GET /api/ecomm-app/stage/catalog` y `GET /api/ecomm-app/workspace/queue`.
- Vistas de canales: `GET /api/ecomm-app/workspace/channels/listings`; revisión `/{ecomm_id}/channels` y `/channels/review`.
- Editor: `GET/POST /api/ecomm-app/workspace/{ecomm_id}`, `expected_version`, CSRF y las cabeceras existentes de propuesta.
- Documentos: `/{ecomm_id}/evidence`, `/documents/import`, revisión de procedencia, extracción, hechos y originales/versiones.
- Propuestas: `/{ecomm_id}/proposals`, `/generate`, revisión por campo, generación-context y aplicación por el editor existente.
- Lotes: `/api/ecomm-app/editorial-batches`, preview/start/detail/cancel/retry; mismo servicio y ejecutor.
- Conexiones: `/api/connections/status`, POST manual/start, mercadolibre/auth-url, mercadolibre/sync y tiendanube/import-csv existentes.
- OpenAI histórico: `GET /api/ecomm-app/workspace/ai/{id}/latest` y, sólo con habilitación posterior, POST `.../suggest`. No se creó cliente ni presupuesto.

## Capacidades reales y límites de IA/documentos

1. El generador determinista existente usa hechos aprobados vigentes y conserva citas, versiones, decisiones y campos sin respaldo. El recorrido documental funciona en aislamiento con documentación de prueba explícitamente identificada. No es búsqueda web ni OpenAI.
2. OpenAI histórico produce título y descripción con su cuota global original de 10 intentos/día. Se conectaron consulta y solicitud manual al panel, manteniendo el presupuesto, expected_version y revisión humana. Sus sugerencias no equivalen a hechos oficiales ni completan 18 campos con citas. **No se ejecutó una llamada real** y la generación sigue bloqueada por defecto.
3. `generation-context` conserva su contrato futuro respaldado, proveedor deshabilitado y costo 0. No se alteró para afirmar que el OpenAI histórico ya consume y verifica todas sus citas.
4. El recolector HTTPS real no está validado/activado desde este dashboard. No hay dominios autorizados para esta entrega ni llamadas externas. Se mantienen el lector, allowlist y controles existentes; faltan autorización de producto/dominio, prueba de infraestructura y validación de una descarga auténtica antes de anunciar ese recorrido.
5. **El lector documental requiere `/document-parser/parser.sock`.** El build productivo actual de `backend/Dockerfile` no empaqueta ni inicia el lector aislado. La capacidad informa su presencia sin consultar Internet; su ausencia bloquea la selección de archivos. Registrar una URL no descarga contenido ni aprueba hechos. Una presencia de socket no certifica salud: el protocolo mantiene sus límites y falla cerrado ante errores.
6. Para procesar archivos en el alojamiento futuro se debe suministrar el lector **existente** con sus límites y sin red/credenciales, en aislamiento real y con socket compartido autorizado. No se trasladó el parser al proceso web ni se redujeron sus protecciones. El Blueprint actual no declara esa infraestructura; su viabilidad efectiva en Render debe comprobarse antes de prometer procesamiento PDF online. No se creó ningún servicio.
7. Se conserva la incidencia intermitente del PDF registrada en `FUNCTIONAL-VALIDATION.md`. No se amplió el perfil especial por hash ni se transfirió al Ecomm ID real; no hubo una nueva prueba con bytes auténticos en esta entrega.

## Esquema y copia previa

No hay migraciones comerciales nuevas. Se reutilizan los UP existentes de `documental/migration.py`, `editorial_batches/migration.py` y `editorial_batches/migration_2r.py`:

- Tres tablas documentales: control, documentos y expedientes; índice de identidad.
- Dos tablas de lotes y sus índices/constraints.
- Señales de cancelación y los dos índices del ejecutor.

El planificador **offline** `backend/app/services/v2_schema.py` imprime esos mismos UP con transacción, búsqueda en public, límite de espera de locks, exclusión de migración simultánea y rechazo de grupos parcialmente instalados. No importa settings, engine ni credenciales; no ejecuta SQL. Repetirlo no reinserta filas ni elimina datos. Un grupo con todas las tablas pero columnas/índices incorrectos necesita revisión; la comprobación de capacidades lo mantiene deshabilitado. No hay ALTER, UPDATE ni DROP sobre tablas comerciales originales.

La prueba de compatibilidad realizada copia **estructura original y datos sintéticos** de capturas/fichas a otro schema dentro de PostgreSQL descartable, aplica dos veces los UP preparados y compara el contenido antes/después. No copia sesiones ni tokens. También se verifican columnas faltantes y persistencia/concurrencia mediante los contratos normales, incluidos IDs ajenos a la lista de fixtures. Esto no sustituye una copia auténtica protegida.

**Bloqueo pendiente:** no hay una copia productiva autorizada de estructura/datos disponible y no se autorizó obtenerla. No se consultó la base para inventar un diagnóstico de su estado. La aceptación con datos auténticos y el cumplimiento final del piloto comercial están pendientes de esa validación; esta entrega no se presenta como aprobada sólo por pasar pruebas sintéticas.

## Procedimiento de activación (PREPARADO, NO EJECUTADO)

1. Revisar el commit local y autorizar por separado la obtención de una copia protegida y las operaciones necesarias. Verificar configuración efectiva de API/web/Blueprint/auto-deploy en Render; lo que figura en `render.yaml` es una referencia, no una observación del servicio. Mantener intacta la demo pública.
2. El responsable de la base debe generar resguardo privado con restauración comprobada. Preparar una copia descartable con estructura original y datos comerciales mínimos autorizados. **Excluir** sesiones, intentos de autenticación, conexiones/tokens OAuth, estados OAuth, credenciales, secretos de entorno y URLs sensibles. La anonimización debe conservar IDs/relaciones, presentaciones, tipos y conflictos relevantes. No adjuntar dumps ni secretos al repositorio o al chat.
3. Confirmar que esa copia usa un DSN y usuario independientes y sin permisos/rutas a producción. Validar nombre/host/puerto/base/rol antes de importar módulos con engine. Ejecutar FastAPI y el build productivo contra esa copia sin egress, con autenticación exclusiva de prueba; sin seed/fallback comercial. El arnés `--production-compat` actual valida fixtures y no debe abrirse indiscriminadamente para cargar copias reales: la incorporación autorizada requiere revisión de privacidad, entorno y allowlist de IDs. Comparar tipos, índices, constraints, conteos y versiones antes/después. Si falta una columna original, detenerse: este plan no inventa su migración.
4. Preparar el SQL offline desde la raíz del checkout revisado: `PYTHONPATH=backend python -m app.services.v2_schema > /tmp/kiki-v2-reviewed.sql`. Inspeccionarlo. Sólo tras autorización, ejecutar contra el **destino descartable previamente comprobado**: `psql "$KIKI_VALIDATED_PG_DSN" -X -v ON_ERROR_STOP=1 -f /tmp/kiki-v2-reviewed.sql`. El DSN lo suministra el operador por un mecanismo seguro, nunca en documentación/logs. Verificar estructura/capacidades y ejecutar los recorridos y regresiones sobre esa copia. No apuntar este comando a producción durante esta preparación.
5. Tras validar esa copia y recibir autorización productiva separada, repetir resguardo, destino, plan de cambios y SQL necesarios, en ventana acordada. No ejecutar los DOWN. Mantener los flags de documentos/lotes apagados hasta que sus estructuras estén comprobadas. Los flags no crean el esquema.
6. Autorizar distribución/despliegue del commit revisado en los servicios **existentes**, sin hacerlo desde esta sesión. Backend: habilitar `KIKI_V2_ENABLED=true` y mantener `KIKI_V2_WRITES_ENABLED=false`, `KIKI_V2_CONNECTIONS_ENABLED=false`, `KIKI_V2_AI_GENERATION_ENABLED=false`, ejecutor inicialmente apagado. No cambiar secretos/cuentas/URLs de proveedor. Confirmar antes que las tablas originales están completas: con v2 activo no hay auto-DDL.
7. Frontend del servicio habitual: build `cd frontend && npm ci && npm run build:production`; directorio publicado `frontend/.production-dist`. Conservar rewrite `/api/*` al FastAPI existente antes de `/* → /index.html`, HTTPS y forwarding de cookies, Set-Cookie, CSRF, `X-Kiki-UI`, `X-Kiki-UI-Contract` y cabeceras de propuestas. No hacer una llamada externa desde el navegador al origen API. No reemplazar el build de `kiki-tech-2-demo`, que sigue siendo `npm run build`.
8. En Chrome del operador, con usuario habitual, validar `/v2/` y volver a `/dashboard-classic`: sesión, contadores, captura completa, ML/TN sin vínculos, búsquedas y filtros sobre datos auténticos, ficha de 18 campos, fuentes e historial. Una sesión expirada debe requerir ingreso, sin fallback. Verificar ausencia de escrituras/calls de proveedor al navegar. No interpretar GET como ausencia de efectos internos: la autenticación existente actualiza last_seen.
9. Solicitar autorización explícita para **un único guardado interno de un producto identificado**, habilitar escritura y comprobar versión, recuperación, historial y 409 con dos operadores. No vincular Hileret por EAN: contrastar variante, marca, cantidad y unidad/pack con una referencia autorizada del catálogo. No trasladar decisiones sintéticas.
10. Documentos: habilitar sólo con esquema y lector aislado disponibles/validados. Canales: habilitar revisión interna tras comprobar estructura y relaciones. Lotes: habilitar esquema/servicio y ejecutor existentes sólo después de validar el recorrido individual; previsualizar, confirmar y revisar resultados sin aprobaciones automáticas.
11. Mantener conexiones y OpenAI apagados hasta autorizaciones específicas. Para actualizar capturas, habilitar conexiones y confirmar una acción; verificar el bloqueo Ecomm manual/programado y conservación de fichas. Para OpenAI, revisar cuota, modelo y costo existentes, autorizar una llamada, inspeccionar su resultado limitado. La investigación real de fabricante requiere además producto y dominio autorizados y una validación real; no activar tareas masivas.

Ningún paso productivo de esta lista está autorizado por haber preparado este documento.

## Reversión

- Deshabilitar primero nuevas operaciones; cancelar de forma explícita los lotes que corresponda, dejar terminar o recuperar leases de trabajos autorizados y detener el ejecutor. No interrumpir una actualización de captura a ciegas.
- Desactivar `KIKI_V2_ENABLED` y volver a `/dashboard-classic`; la interfaz anterior y sus sesiones/contratos permanecen. Conservar el build anterior revisado y los valores de configuración previos para un rollback de código si fuera necesario.
- **Conservar las tablas aditivas y los datos/historial.** No ejecutar DOWN ni restaurar toda la base sobre trabajo reciente del cliente. Una reversión de datos requiere decisión específica y plan de recuperación; no forma parte del rollback de UI.
- Restituir únicamente los flags/build anteriores mediante la operación manual autorizada. No rotar credenciales ni reconectar cuentas como parte de un rollback visual.

## Validación y archivos

- Backend: **102** comprobaciones seleccionadas (19 de aislamiento/PG, 9 de compatibilidad v2, 7 de editor, 17 documentales, 18 de canales, 22 de lotes y 10 de conexiones), más **484** regresiones heredadas. Ruff aprobado. Las pruebas nuevas usan también los routers normales de FastAPI sin allowlist sintética de IDs y con sesiones reales exclusivamente de prueba.
- Capacidad de canales existente: 50 y 5.000 variantes, **6 consultas SQL** en ambos casos; 0,018 s y 1,387 s en esa medición aislada. No es un SLA de producción ni una medición de carga concurrente del nuevo endpoint de capacidades.
- Demo estática: **58** pruebas escritorio/celular aprobadas después de separar la entrada LegacyApp; sus bloqueos de API/transportes y rutas históricas se conservan.
- Build productivo y TypeScript aprobados; build demo e integración aprobados. El build productivo además rechaza upstreams `VITE_*` y la inclusión de módulos/controladores demo.
- Navegador productivo contra FastAPI/PG aislados: recorrido de cinco vistas, filtros/URL, editor/18 campos/guardado, cinco pestañas, importación local, revisión humana de hechos, propuesta determinista, aprobación por campo y recuperación/historial. También sólo lectura, funciones sin habilitar y error sin fallback. **12 casos aprobados** (seis por tamaño), incluyendo transporte OpenAI completamente simulado: expected_version visible, campos intactos y bloqueo con cambios sin guardar. No hubo llamadas reales ni consumo.
- Comprobación adicional en ambos tamaños: consulta del OpenAI histórico sin generar, generación deshabilitada y cero requests a proveedores o rutas de prueba. Sus respuestas no prueban disponibilidad auténtica de OpenAI ni de credenciales productivas.
- Una primera ejecución descubrió que la nueva entrada no cargaba las hojas de estilo compartidas y el sidebar interceptaba clics; se corrigieron los imports de CSS existentes. El recorrido posterior aprobó con clics normales, sin force ni relajación de aserciones. Las primeras comprobaciones backend devolvieron 401 porque el TestClient usaba HTTP y la cookie original es Secure; se corrigió el cliente a HTTPS, sin cambiar cookies ni autenticación.

Una repetición final de Ruff se bloqueó por espacio temporal al crear un contenedor; se retiraron únicamente cinco imágenes sin etiquetas, creadas por esta ejecución y sin contenedores asociados, conservando la imagen vigente y los datos del proyecto. La repetición sobre el código final se verificó por separado.

Todas las capturas siguientes corresponden a **datos sintéticos de compatibilidad, NO a catálogo productivo**:

| Vista | Escritorio | Celular |
|---|---|---|
| Dashboard productivo en aislamiento | [Captura](../frontend/artifacts/v2-dashboard-desktop.png) | [Captura](../frontend/artifacts/v2-dashboard-mobile.png) |
| Editor existente | [Captura](../frontend/artifacts/v2-editor-desktop.png) | [Captura](../frontend/artifacts/v2-editor-mobile.png) |
| Centro de conexiones | [Captura](../frontend/artifacts/v2-conexiones-desktop.png) | [Captura](../frontend/artifacts/v2-conexiones-mobile.png) |

Reproducción del recorrido aislado (sin modificar ni consultar proveedores):

```bash
python integration/run.py build
cd frontend
npm run build:production
cd ..
python integration/run.py browser-test --production-compat
```

Ese perfil es opcional y no abre rutas ni transportes del arnés habitual. Autenticación de fixtures identificada, DB descartable, red de contenedores `none`, raíz de sólo lectura, sin puertos de contenedor ni credenciales reales. No es un método para cargar datos productivos. El comando termina retirando los contenedores/volúmenes y su marcador. No hay URL online nueva ni despliegue.

 La lista exacta de archivos del commit se obtiene con `git show --stat --oneline HEAD`. Grupos: entrada/build productivos y LegacyApp; control runtime/transportes y textos de los paneles existentes; capacidades/configuración/ciclo de vida FastAPI y planificador SQL; escenario opcional del arnés y pruebas de compatibilidad. No se modifican clientes Ecomm/ML/TN, presupuesto OpenAI, sus modelos comerciales ni migraciones existentes; tampoco render.yaml o workflows.

### Archivos de esta entrega

- `.gitignore`
- `backend/app/api/routes/connections.py`
- `backend/app/api/routes/v2.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/services/v2_lifecycle.py`
- `backend/app/services/v2_schema.py`
- `backend/integration_sandbox/bootstrap.py`
- `backend/integration_sandbox/policy.py`
- `backend/integration_sandbox/server.py`
- `backend/integration_sandbox/v2_checks.py`
- `frontend/integration-tests/production-connected.spec.ts`
- `frontend/package.json`
- `frontend/production.html`
- `frontend/scripts/build-production.mjs`
- `frontend/src/LegacyApp.tsx`
- `frontend/src/integration/BatchPanel.tsx`
- `frontend/src/integration/ChannelsPanel.tsx`
- `frontend/src/integration/ConnectionCenter.tsx`
- `frontend/src/integration/DocumentImport.tsx`
- `frontend/src/integration/GenerationReadiness.tsx`
- `frontend/src/integration/IntegrationCatalog.tsx`
- `frontend/src/integration/PersistentWorkspace.tsx`
- `frontend/src/integration/ProposalPanel.tsx`
- `frontend/src/integration/ResearchPanel.tsx`
- `frontend/src/integration/SavedHistory.tsx`
- `frontend/src/integration/catalog-adapter.ts`
- `frontend/src/integration/connections.ts`
- `frontend/src/integration/runtime.ts`
- `frontend/src/main.tsx`
- `frontend/src/production/main.tsx`
- `frontend/src/prototype/CatalogView.tsx`
- `integration/PRODUCTION-V2-ROLLOUT.md`
- `integration/browser_tests.py`
- `integration/gateway.py`
- `integration/run.py`

Además, las seis capturas `frontend/artifacts/v2-*.png` enlazadas arriba. Las capturas históricas regeneradas por pruebas se restauraron.
