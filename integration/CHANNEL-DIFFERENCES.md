# Diferencias por variante: coincidencia independiente de antigüedad

Base: `main` después de PR #163, `a22d336`. Rama `fix/channel-differences-and-freshness`. Esta entrega reemplaza la clasificación temporal excluyente documentada en `CATALOG-COMPARISON-FIX.md`.

## Resultado funcional

- El dashboard conectado retira las dos tarjetas agregadas «sin publicación confirmada». Sus URLs/filtros históricos siguen aceptados para compatibilidad; no representan faltantes.
- Cada canal muestra **coincidencias encontradas** (variantes con candidatos, incluidos vínculos revisados o conflictos), y **candidatos por revisar** (variantes con relación aún no resuelta, incluyendo conflictos, sin una decisión negativa vigente), además de cinco categorías excluyentes: vínculo de identidad revisado, coincidencia sin conflicto detectado, conflicto/ambigüedad, no encontrado en captura, evidencia insuficiente. Las cinco suman las variantes Ecomm-App. Encontrados y por revisar son indicadores independientes: no son categorías adicionales ni se suman otra vez. Una variante con vínculo validado queda resuelta, aunque conserve otras filas candidatas.
- La vigencia es otra dimensión: fecha, antigüedad y cantidad de variantes afectadas. Vencer una captura no cambia sus candidatos, los no encontrados o las categorías de identidad. Los antiguos filtros `*_comparison_stale` siguen disponibles como filtros de vigencia, combinables con la coincidencia.
- Una revisión manual previa, con fingerprint/identidad sin cambios, continúa visible si sólo pasó el tiempo. La antigüedad bloquea nuevas validaciones y confirmación de publicación actual. Una captura realmente reemplazada sigue invalidando fingerprints como antes; se conserva su decisión e historial para revisar, sin aprobación automática.
- La tabla sigue teniendo una fila por Ecomm ID y ahora expone IDs/títulos coincidentes ML y los identificadores URL de TN, además de estado, discrepancias, cantidad de candidatos y fecha. El identificador de fila TN es interno: el CSV no suministra un ID de API Tiendanube y no se inventa uno. La ficha lateral conserva las cinco pestañas.
- Se reutilizan SKU exacto, GTIN con dígito verificador, marca, título, tamaño, cantidad y condición unidad/pack/combo. Las familias y los EAN compartidos no fusionan variantes. No se cambian los modelos, integraciones, editor de 18 campos, sesiones ni servicios de persistencia.

**«No encontrado en la captura» no significa «no publicado actualmente».** Incluso una captura reciente no acredita por sí sola exhaustividad, alcance de cuenta y suficiencia de identificación. Los contratos almacenados no persisten una certificación de completitud para esta finalidad. Se informa `capture_completeness=NOT_PROVEN_BY_STORED_CONTRACT` y `current_publication_absence_proven=false`; no se emite una ausencia actual inventada. TN CSV nunca acredita publicación actual.

## Contratos y exportación

- Cola existente: `GET /api/ecomm-app/workspace/queue`. `channel_coverage.summary.comparison.{ml,tn}` expone `matching_independent_of_freshness`, `variant_states` (cinco categorías), `variants_with_candidates`, `variants_with_pending_candidates`, `stale_variants`, fechas y conteos de registros/publicaciones. `ml_found` y `tn_found` filtran variantes con candidatos; `*_pending_candidates` filtra las que requieren revisión interna. Las filas paginadas agregan sólo tres previews de coincidencias; no duplican historiales o hacen peticiones por fila.
- Detalle existente: `GET /api/ecomm-app/workspace/{ecomm_id}/channels`, con motivos, discrepancias, decisiones e historial exactos. `freshness` no sustituye `evidence_state`. Por compatibilidad con el frontend de PR #163, el JSON conserva `variant_states.stale=0` como clave **deprecada** (declarada en `deprecated_state_keys`); no es un conteo temporal. La UI nueva la ignora y usa `stale_variants`, sin romper la suma esperada por el cliente anterior.
- Listado de canal existente: `GET /api/ecomm-app/workspace/channels/listings`; conserva candidatos y vínculos aunque envejezca la fuente. No crea identidades para los registros huérfanos.
- CSV nuevo, exclusivamente GET autenticado: `GET /api/ecomm-app/workspace/channels/differences.csv?channel=ml&state=no_match&q=`. `channel=tn` consulta el otro canal. Estados admitidos: `all`, `found`, `pending`, `verified`, `candidates`, `conflicts`, `no_match`, `insufficient`. La UI ofrece no encontrados, pendientes y comparación completa para cada canal; aplica la búsqueda actual. Los estados se filtran en la misma cola, sin releer proveedores ni paginar repetidamente para exportar.

El CSV usa UTF-8 con BOM y separador `;`, apropiado para Windows. Incluye Ecomm ID, SKU, nombre/presentación, marca de referencia, barcode/GTIN, combo, coincidencias e identificadores ML/TN, motivo, discrepancias, bloqueos, fecha/vigencia y dos columnas explícitas `NO_ACREDITADA` para completitud y ausencia actual. No se exportan tokens de sesión/revisión, credenciales ni historiales completos. Se informa cantidad total/detallada y truncamiento de candidatos cuando aplica el límite de visualización existente. Importar códigos en Excel como texto conserva ceros iniciales; no usar el CSV para vincular o escribir automáticamente.

Límites: 10.000 variantes seleccionadas, 10 MiB de respuesta y 4.096 caracteres por celda; exceso implica 409, sin archivo parcial o truncamiento silencioso. Se neutralizan fórmulas de planilla (`=`, `+`, `-`, `@`, prefijos de control/espacios), se respetan autenticación/permisos existentes y se responde `Cache-Control: no-store`. La pasarela de pruebas sólo amplía el límite para esta ruta exacta; los demás límites siguen intactos. Exportar no requiere habilitar escrituras ni sincronizaciones.

## Qué permiten las capturas actuales

Con los bytes existentes se puede calcular coincidencias, incertidumbres, discrepancias y listas de variantes no encontradas **en esas copias**, y preservar revisiones por identidad. Eso no exige refrescar OAuth, importar CSV ni ejecutar sincronizaciones. La antigüedad no borra ninguna coincidencia.

Observaciones aportadas por el usuario, no mediciones de esta sesión:

| Medida | ML | TN |
|---|---:|---:|
| Variantes Ecomm-App del maestro | 3.161 | 3.161 |
| Variantes con candidatos observadas | 1.331 | 525 |
| KPI anterior sin publicación confirmada | 3.161 | 3.161 |
| Fecha/antigüedad de la captura verificable localmente | No disponible | No disponible |
| No encontrados / conflictos / sin evidencia recalculados sobre fuente auténtica | Pendiente | Pendiente |

No hay snapshots auténticos de esos catálogos disponibles localmente y no se accedió a PostgreSQL/Render/proveedores productivos. Los archivos locales del lector anterior están marcados `SIMULATED_RESPONSES_ONLY`/`OFFLINE_ONLY`; no se usan como catálogo auténtico. No corresponde presentar `3161 − 1331` o `3161 − 525` como faltantes reales: entre las variantes sin candidatos puede haber conflictos de origen o insuficiencia de datos. Los valores definitivos provienen de la cola sobre las capturas reales, no de estas restas ni de un fixture.

Prueba de invariancia: sobre la misma captura se compara `now` con `now+100h`; las categorías, IDs y cantidad de coincidencias son iguales, mientras cambia la vigencia. El vínculo humano sin cambios de evidencia se mantiene y el indicador de publicación vigente cae a falso. Se prueban fuentes ausentes, SKU repetidos, EAN compartidos, presentación/cantidad incompatibles y unidad/pack, además de guardado/historial y concurrencia del editor existente.

## Qué exige actualizar y autorización separada

**ML:** las lecturas de estado disponibles (`GET /api/mercadolibre/status` y `/api/connections/status`) consultan metadatos locales. La actualización ya existe en `POST /api/mercadolibre/sync`, con sesión/CSRF y controles de conexiones de v2. `MercadoLibreService.sync()` lee IDs mediante scan/scroll y detalles bulk, transforma y guarda la captura sólo después de completar esas lecturas. Bulk valida cantidad, código y cuerpo; si falla antes de guardar, conserva la copia previa. No publica ni modifica productos.

**Límite crítico:** esa ruta llama `_refresh_if_needed` y puede renovar OAuth también ante un 401. No es una operación libre de efectos sobre credenciales. Bajo la restricción actual NO debe ejecutarse. Una actualización futura requiere autorización de captura y, si corresponde, de renovación de OAuth; revisar primero cuenta, expiración y alcances sin revelar tokens. No se presume que todos los registros de la cuenta equivalgan al catálogo maestro ni que la captura pruebe la ausencia de un producto. No se encontró un bloqueo de concurrencia explícito en `sync()`; ejecutar una única actualización supervisada y evitar solicitudes simultáneas hasta revisar ese aspecto. No se modifica esa integración en esta entrega.

**TN:** reutilizar `POST /api/tiendanube/import-csv`, sesión/CSRF y controles v2. Exige CSV, tamaño máximo configurado, esquema con columnas obligatorias y parser existente; parsea antes de reemplazar la captura. No consulta una API TN ni escribe al proveedor. Requiere que el operador autorice y aporte una exportación completa de la tienda correcta, con fecha de exportación y alcance conocidos; no importarla aquí. Conservar un resguardo previo: `save_snapshot` reemplaza/commitea y luego se registra el trabajo en otro commit, no hay rollback conjunto de captura y registro de importación. El timestamp actual es **fecha de importación**, no prueba la fecha original de exportación. Reimportar un archivo viejo no acredita actualidad.

No se ejecutaron esas rutas reales, renovación OAuth, publicación, importación productiva, IA ni escritura en Ecomm-App. Para afirmar estado comercial actual hacen falta capturas autorizadas recientes, alcance/exhaustividad comprobados y contraste de identidad suficiente. Actualizar fecha o quitar un aviso no sustituye esa evidencia.

## Validación y distribución

Se ejecutaron las pruebas sobre PostgreSQL descartable y fixtures expresamente sintéticos, sin introducirlos en producción:

- Ruff y suite backend: **517 aprobadas**, con un aviso de deprecación de Starlette/AnyIO.
- PostgreSQL aislado: **67 casos** entre verificación/aislamiento (19), editor/persistencia/concurrencia (7), canales (20), operaciones comerciales (12) y compatibilidad `/v2/` (9). Los 20 casos de canales se repitieron después del ajuste final del indicador de pendientes.
- Playwright escritorio/celular: canales (12), interfaz conectada productiva con transporte aislado (16), catálogo/presentación (14) y demo (58). Incluye descarga real de CSV, ausencia de escrituras durante la exportación y rechazo de enlaces blob arbitrarios.
- TypeScript y builds de integración, producción y demo aprobados.
- Rendimiento **sintético**, no medición productiva: 3.001 variantes, 2.844 filas ML y 550 TN, cuatro SELECT y 1,149 s; 3.201 variantes con títulos compartidos, 3.201 pares candidatos y 1,686 s. La prueba PostgreSQL de 5.000 variantes mantiene seis SELECT y 1,945 s (sin N+1); son tiempos orientativos de este entorno.

La descarga sólo habilita el GET exacto y un enlace registrado por una capacidad privada para el CSV generado. No se abre la navegación genérica a blobs ni recursos externos. Las capturas de aceptación son sintéticas: [escritorio](../frontend/artifacts/diferencias-catalogos-desktop.png) y [celular](../frontend/artifacts/diferencias-catalogos-mobile.png).

Archivos funcionales: `ecomm_channel_coverage_service.py`, `ecomm_api_channel_evidence.py`, `ecomm_api_work_queue_service.py`, `ecomm_channel_listings.py`, nuevo `ecomm_channel_export.py`, ruta `ecomm_api_channels.py`; componentes `CommercialViews.tsx`, `IntegrationCatalog.tsx`, `ChannelsPanel.tsx`, adaptador `catalog-adapter.ts`, nuevo `csv-download.ts` y allowlist `isolation.ts`. Se actualizan pruebas unitarias/PostgreSQL/Playwright, allowlist/pasarela aislada y las dos guías de comparación. No hay cambios de esquema.

La PR utilizará el CI existente de Ruff, pytest y build; los resultados locales no equivalen a un resultado de GitHub Actions. No se modifica Render, workflows, variables ni migraciones; sin merge o deploy. En una futura activación autorizada, backend compatible primero y frontend nuevo después: el cliente nuevo exige `matching_independent_of_freshness=true` y no inventa categorías al recibir un backend antiguo.
