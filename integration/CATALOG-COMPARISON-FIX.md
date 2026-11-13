# Comparación de catálogos por variante Ecomm-App

Base: `main`, commit `3533f0c`. Rama `fix/catalog-channel-comparison`. La corrección no consulta proveedores, no modifica capturas ni decisiones y no requiere migraciones o variables nuevas.

## Problema y resultado

Antes, el KPI «sin confirmación» contaba todas las variantes sin vínculo manual vigente. Ese número no significa «no publicado». El cruce sólo recuperaba SKU exactos y trataba su repetición como ambigüedad, sin presentar un desglose visible reconciliable. Las variaciones ML sin SKU propio tampoco podían identificarse mediante el SKU heredado del padre.

Ahora se conserva el KPI como agregado de falta de confirmación, con una explicación explícita y una matriz por canal. Se separan **variantes Ecomm-App**, **filas capturadas** y **publicaciones/productos distintos**. No se restan directamente esos totales ni se sustituyen datos ausentes por fixtures.

Cada variante pertenece exactamente a una de seis categorías por canal, en este orden: vínculo vigente verificado; conflicto/ambigüedad; captura vencida; candidato pendiente; sin coincidencia en captura con identidad contrastable; evidencia insuficiente. Las seis cantidades suman las variantes maestras. La fecha/vigencia de la fuente permanece visible incluso cuando el conflicto tiene prioridad de clasificación. «Vínculo verificado» no implica publicación actual; ML requiere además estado activo en la captura y TN CSV nunca acredita publicación actual.

Controles independientes y reconciliaciones:

- Registros válidos con candidatos + sin candidatos = registros válidos capturados. Las filas inválidas se informan aparte.
- Variantes con candidatos y pares candidato-variante se informan por separado; un registro puede ser candidato de varias variantes sin vincular ninguna.
- Publicaciones ML distintas se cuentan por ID padre, sin contar sus variaciones como publicaciones adicionales. TN cuenta productos distintos por slug y conserva sus filas separadas.
- Captura ausente, sin fecha, futura o fuera de vigencia no demuestra ausencia de publicación. Se conservan la política existente ML (`ml_snapshot_fresh_hours`, por defecto 24 h) y TN (24 h para revisión local, sin garantía de publicación).

## Recuperación de candidatos y revisión

Se reutilizan las capturas `ECOMM_APP_API_STAGE`, `MERCADOLIBRE_API` y `TIENDANUBE`, sin usar Ecomm XLSX ni ML Excel. Se construyen índices en memoria de SKU exacto (trim/casefold, conservando ceros, puntuación y sufijos), GTIN con dígito verificador y nombre. Cuando no hay coincidencia por código, marca y palabras significativas del nombre permiten sugerencias conservadoras con presentación y números contrastables. No se hace una búsqueda difusa por familia SKU ni se hereda SKU de padre ML a una variación.

Cada candidato expone razones, datos Ecomm/canal, diferencias, cantidad, fecha y bloqueos. La coincidencia no confirma identidad ni habilita aprobación automática. Se contrastan marca, códigos, tamaño, unidad/pack/combo y cantidad. El conflicto barcode/GTIN bloquea aprobación. TN incorpora a la comparación los valores de presentación de sus atributos CSV.

Se mantienen las tablas, fingerprints, checks explícitos, CSRF, revisión de versiones, decisiones y su historial existentes. Las filas anteriormente revisadas siguen visibles aunque cambien sus códigos; el fingerprint anterior queda obsoleto y no vuelve a aprobarse. No se transfieren decisiones históricas de Excel. Los ocho candidatos iniciales se muestran junto con cualquier fila previamente revisada; se informa el truncamiento. El listado del canal permite abrir variantes candidatas sin inventar un Ecomm ID.

El dashboard usa el resumen de la misma cola para los KPI y la preparación interna: elimina cuatro consultas iniciales adicionales que recalculaban la matriz. Los filtros guardan su contexto en la URL y mantienen la misma tabla. El panel lateral y las cinco pestañas se conservan.

## Cifras auténticas y limitación de acceso

| Fuente | Total comunicado por el usuario | Fecha y antigüedad verificadas localmente |
|---|---:|---|
| Ecomm-App | 3.161 variantes | No disponible |
| ML API | 2.844 publicaciones capturadas | No disponible; falta distinguir filas/variaciones de publicaciones distintas mediante la captura |
| TN CSV | 550 productos capturados | No disponible; puede haber más filas/variantes que productos |

El usuario informó 3.161 «sin confirmación» en cada canal y HTTP 200 para la variante `8021010`. Son observaciones aportadas, no mediciones hechas en esta sesión. No hay capturas auténticas disponibles localmente ni credenciales autorizadas; no se consultó la API, PostgreSQL o Render productivos. **No se puede presentar un antes/después real de coincidencias ni fechar esas fuentes con la información disponible.** Tampoco corresponde inferir 317 productos faltantes restando 3.161 y 2.844.

El resultado calculado queda disponible en la respuesta existente de `GET /api/ecomm-app/workspace/queue`: `channel_coverage.summary.comparison.ml/tn`, junto con las fechas y fuentes. El detalle sigue en `GET /api/ecomm-app/workspace/{ecomm_id}/channels`; el listado reutiliza `GET /api/ecomm-app/workspace/channels/listings`. No se creó otro lector, importador o fuente comercial. La comprobación con los snapshots auténticos queda pendiente de acceso de lectura expresamente autorizado en el entorno que ya los contiene; no necesita una nueva captura ni sincronización.

## Ensayo reproducible sintético, NO cifras del cliente

Fixture de 3.001 variantes, 2.844 filas ML y 550 filas TN, con SKU únicos y sin revisiones manuales:

| Medida calculada | ML | TN |
|---|---:|---:|
| KPI agregado «sin confirmación» anterior | 3.001 | 3.001 |
| Variantes candidatas ahora visibles | 2.844 | 550 |
| Sin coincidencia en esa captura | 157 | 2.451 |
| Vínculos verificados | 0 | 0 |
| Conflictos / evidencia insuficiente / vencidas | 0 | 0 |
| Total de variantes clasificadas | 3.001 | 3.001 |

El agregado no se reduce artificialmente aprobando candidatos. El nuevo desglose explica su composición. Este fixture fue construido para pruebas y no reproduce ni afirma las coincidencias del catálogo auténtico.

Rendimiento: 1,031 s y cuatro SELECT para esa matriz en el ensayo aislado; 3,236 s en la ejecución final concurrente de CI local. La regresión PostgreSQL existente midió 50 y 5.000 variantes: seis consultas en ambos casos, 0,024 y 2,148 s respectivamente. Sin solicitudes por fila, escrituras o llamadas a proveedores. Son tiempos de este entorno, no un SLA productivo.

## Validación

- 499 pruebas pytest, incluyendo 15 nuevas de comparación y las regresiones anteriores; Ruff aprobado.
- 239 pruebas de integración PostgreSQL de los módulos del arnés, además del preflight independiente: identidad, fichas, evidencias, canales, concurrencia, sesiones, lotes, conexiones simuladas y PDF auténtico. El paso posterior de reinicios encontró falta de espacio en Docker. Tras eliminar caché reconstruible, pasó la repetición separada: sin acción duplicada, recuperación de lease con dos ejecutores y 1.000 tareas únicas recuperadas sin escrituras comerciales; también aprobaron las ocho pruebas HTTPS/pasarela. No se borraron bases ni capturas para resolver el espacio.
- TypeScript y builds demostrativo, integración y productivo aprobados. El build productivo conserva el control de exclusión de fixtures y API del mismo origen.
- Playwright: diez pruebas de canales aprobadas (escritorio/celular) y 58 regresiones demo aprobadas. 16 pruebas de entrada productiva/clásica aprobadas. Capturas sintéticas: `frontend/artifacts/comparacion-catalogos-desktop.png` y `comparacion-catalogos-mobile.png`.

No se ejecutaron sincronizaciones, importaciones, OAuth, OpenAI o publicaciones reales. Las únicas escrituras de pruebas fueron en bases descartables. Sin merge o despliegue. La PR utiliza el CI existente (`pull_request`: Ruff, pytest y build); su creación/ejecución remota requiere acceso a la API de GitHub.

## Archivos modificados

- `backend/app/api/routes/ecomm_api_channels.py`
- `backend/app/services/ecomm_api_channel_evidence.py`
- `backend/app/services/ecomm_api_work_queue_service.py`
- `backend/app/services/ecomm_channel_coverage_service.py`
- `backend/app/services/ecomm_channel_listings.py`
- `backend/integration_sandbox/channel_checks.py`
- `backend/tests/test_ecomm_channel_comparison.py`
- `frontend/artifacts/comparacion-catalogos-desktop.png`
- `frontend/artifacts/comparacion-catalogos-mobile.png`
- `frontend/integration-tests/channels-connected.spec.ts`
- `frontend/integration-tests/functional-catalog.spec.ts`
- `frontend/integration-tests/production-connected.spec.ts`
- `frontend/src/integration/ChannelsPanel.tsx`
- `frontend/src/integration/CommercialViews.tsx`
- `frontend/src/integration/IntegrationCatalog.tsx`
- `frontend/src/integration/catalog-adapter.ts`
- `frontend/src/integration/channel-adapter.ts`
- `frontend/src/integration/channel-labels.ts`
- `frontend/src/integration/integration.css`
- `frontend/tests/channel-coverage.spec.ts`
- `integration/CATALOG-COMPARISON-FIX.md`
