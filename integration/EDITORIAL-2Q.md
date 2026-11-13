# Etapa 2Q — Lotes editoriales dentro de Mi catálogo

Base comprobada antes de editar: `feature/kiki-tech-2-dashboard`,
`523237fd7977cb51d63c1e2a395d9d2cb7d60428`, árbol limpio. Sin llamadas a
proveedores, credenciales productivas, publicación, push, PR, merge ni despliegue.
Todo lo ejecutado usa PostgreSQL descartable y datos sintéticos. IA real: USD 0.

## Operación del dashboard

La tabla existente incorpora selección por Ecomm ID, conservada entre páginas.
«Seleccionar esta página» agrega las variantes visibles. «Previsualizar resultados
filtrados» congela todos los resultados del mismo buscador y filtro, independientemente
de la página visible. Los IDs repetidos o ajenos a la captura se rechazan.
No se combinan unidades, packs, combos ni familias por SKU/EAN.

El selector existente agrega investigación pendiente, aprobaciones documentales
registradas, evidencia revocada, documentos modificados y próxima revisión mensual.
El filtro de aprobaciones identifica decisiones registradas: **la previsualización
vuelve a verificar vigencia, identidad, citas y contradicciones** antes de declarar
que una variante puede recibir una propuesta. Se conserva la cola de revisión
vencida y la regla existente de 30 días; «próxima» significa dentro de 7 días.
Los filtros y la selección de producto conservan la URL del dashboard.

Hay dos operaciones internas:

- **Preparar propuestas para campos vacíos:** generador determinista existente,
  sólo hechos aprobados actualmente respaldados. Nunca reemplaza campos completos,
  aprueba fichas o guarda contenido comercial automáticamente.
- **Crear tareas de revisión:** registra una tarea por variante con el calendario
  existente, cambios documentales y motivos para revisión humana. No renueva fechas
  de aprobación ni cambia fichas.

Cada previsualización persiste la selección exacta, versiones, huellas y resumen:
con respaldo, sin documentos, con conflictos, desactualizados, elegibles y revisión
humana. Los grupos pueden superponerse. «Con respaldo» no significa ficha completa.
**Crear la previsualización no autoriza su procesamiento.** El operador debe pulsar
«Confirmar e iniciar lote». Se guardan usuario, sesión, fecha y huella confirmada.

El trabajo se procesa por pasos. Se puede pausar después del paso actual, cancelar
lo pendiente, recuperar estado, reanudar explícitamente y habilitar reintentos
limitados de errores. Los bloqueos/conflictos requieren resolver la causa y una
previsualización nueva. Las propuestas ya completadas sobreviven a una cancelación.

«Revisar propuesta #…» abre la versión exacta en la pestaña IA del panel existente
(`product=…&tab=IA&proposal=…`). Conserva comparación, citas, revisión por campo,
edición restringida a frases respaldadas y guardado mediante el editor versionado.
La propuesta de otra variante se rechaza. Ficha, Evidencias, Canales e Historial,
las rutas antiguas y el demo siguen usando sus contratos anteriores.

## Reutilización y persistencia

Se revisaron los servicios existentes antes de implementar. El refresco API tiene
un job orientado a consultar proveedores y el piloto GTIN es síncrono y puede
consultar fuentes externas. Ninguno proporciona una cola editorial durable segura
con resultados por variante. No se reutiliza su ejecución externa ni se reconstruyen
los servicios comerciales.

Se reutilizan:

- `build_queue` y `GET /api/ecomm-app/workspace/queue`, captura API completa y
  proyección compartida `api_variant_row`.
- Editor de 18 campos, `_readiness`, `review_schedule` y concurrencia CAS existentes.
- `documental.Research`: identidad, procedencia, citas, contradicciones,
  certificaciones, revocaciones y hechos aprobados.
- `documental.Proposals`: generador, `KikiAiEditorialDraft`, decisiones por campo,
  invalidación de propuestas y guardado en `EcommApiProductEdit` existente.
- Autenticación y CSRF habituales; sin autenticación sintética en módulos compartidos.

Sólo se agregan **dos tablas de coordinación en la misma base**:
`kiki_editorial_batches` y `kiki_editorial_batch_items`. Guardan autorizaciones,
estado, progreso, versiones/documentos usados, resultados, errores e historial.
Las fichas, documentos y propuestas siguen en sus tablas existentes.

Estados: PREVIEW (todavía sin autorización), PENDING, RUNNING, COMPLETED,
BLOCKED, CONFLICT, ERROR y CANCELLED. Resultados e historial por variante son
paginados; el historial general registra autorización, cancelación, errores y cierre.

### Atomicidad, recuperación y concurrencia

1. Se reclama un paso bajo bloqueo PostgreSQL NOWAIT del lote. La concesión y el
   intento se confirman antes de procesar: una caída deja el estado recuperable.
2. El procesamiento verifica un token de propietario, bloquea el lote, la captura,
   las fichas seleccionadas en orden de ID y el control documental existente.
3. Revalida versiones y huellas contra la previsualización congelada. Un cambio
   posterior produce CONFLICT, sin sobreescrituras.
4. Propuestas y resultados de los ítems se confirman en **una misma transacción**.
   Una fachada local de sesión convierte únicamente los commits de los servicios
   reutilizados en flush; no cambia Session global ni el editor normal.
5. Un error revierte el paso entero. Ítems terminados nunca vuelven a seleccionarse.
   Reiniciar FastAPI o recargar el navegador **no ejecuta trabajos automáticamente**.
   Reanudar requiere una acción explícita. El token nuevo impide escribir al proceso
   anterior; un paso que aún mantiene el bloqueo no puede ser reemplazado.
6. Claves idempotentes para preview/start, concesión de 60 s, máximo 3 intentos y
   reintento explícito. No hay cron, worker automático, broker ni scheduler nuevo.

Un guardado concurrente de una ficha todavía inexistente puede volver obsoleta una
propuesta recién generada; los controles existentes de base/versión/evidencia
impiden aplicarla sobre esa ficha nueva. El lote nunca guarda fichas, por lo que no
puede sobrescribir el contenido del operador.

### Límites y consultas

Flag `kiki_editorial_batches_enabled=false` por defecto. Sólo el bootstrap aislado
lo habilita tras preflight. Límites validados por configuración:

| Parámetro | Valor predeterminado | Límite de configuración |
| --- | ---: | --- |
| `kiki_editorial_batch_max_items` | 5.000 | 100–10.000 |
| `kiki_editorial_step_size` | 5 | 1–20 |
| `kiki_editorial_step_seconds` | 10 s | 1–30 s; cesión entre ítems |
| `kiki_editorial_max_attempts` | 3 | 1–3 |
| `kiki_editorial_context_bytes` | 2 MB | 64 KiB–8 MB |
| `kiki_editorial_review_soon_days` | 7 | 1–30 |

Preview lee contextos de 25 variantes; cada paso lee sólo sus variantes. Se verifica
el presupuesto de campos/historial antes de materializarlos. La consulta documental
quita `original_base64` en PostgreSQL y no carga el historial de originales. Se
conservan texto, citas, identidad, versiones y hashes necesarios para validar.
No se truncan evidencias para forzar una aprobación; los contextos excesivos se
rechazan y requieren revisión individual o un paso menor.

La cola proyecta presencia de campos y fechas de aprobación para reutilizar las
reglas de completitud y revisión, sin descargar descripciones/historiales completos
para miles de fichas. Esas marcas internas nunca se guardan como contenido comercial.
Documentos y ediciones se consultan por grupos, no mediante peticiones HTTP por fila.
La captura API existente sigue siendo una copia JSON completa; no se crea otro catálogo.

## API y migración

Rutas nuevas bajo `/api/ecomm-app/editorial-batches`, con flag, sesión y CSRF:

| Método | Sufijo | Función |
| --- | --- | --- |
| GET | vacío | Lotes paginados |
| POST | `/preview` | Congelar selección y calcular resumen |
| GET | `/{uuid}` | Estado, historial e ítems paginados |
| POST | `/{uuid}/start` | Confirmación con revisión, huella y clave idempotente |
| POST | `/{uuid}/step` | Un paso acotado; recuperación explícita opcional |
| POST | `/{uuid}/cancel` | Cancelación CAS de lo pendiente |
| POST | `/{uuid}/retry` | Reintento explícito de errores recuperables |

La ruta documental GET `/{ecomm_id}/proposals` acepta `draft_id` opcional y valida
pertenencia exacta. No se agrega otra ruta de guardado.

La migración UP/DOWN está en
`backend/app/services/editorial_batches/migration.py`, separada de Base y del inicio
productivo. **Se ejecutó únicamente en PostgreSQL descartable**, después de comprobar
su destino antes de importar el engine. La reversión elimina primero ítems y luego
lotes; se deben exportar antes coordinación e historial si se requiriera conservarlos.
No elimina propuestas, documentos ni fichas existentes. UP/DOWN se prueba en el arnés.
Un uso futuro fuera de pruebas requiere revisar y autorizar migración/configuración;
esta entrega no lo ejecuta ni lo habilita.

## Reproducir de forma aislada

Desde la raíz, sin cargar `.env` ni variables productivas:

```bash
python integration/run.py build
python integration/run.py test
python integration/run.py legacy-test
python integration/run.py browser-test
python integration/run.py browser-test --channels
python integration/run.py browser-test --batches
```

El último comando carga un escenario **explícitamente sintético** con documentos y
aprobaciones automatizadas de prueba. No son aprobaciones auténticas del cliente.
Cada comando usa el proyecto Docker fijo, red `none`, procesos sin privilegios,
PostgreSQL por socket y protección de red/recursos existente. Las suites retiran los
contenedores y datos temporales al terminar. Para probar manualmente:
`python integration/run.py up --batches`, gateway HTTPS sólo loopback del entorno;
`python integration/run.py down` para retirarlo. `localhost` en Windows no identifica
esta máquina remota. No se agrega ningún túnel o servicio público.

## Validación y capturas

- Backend PostgreSQL/seguridad: **185 pruebas** (22 nuevas de lotes y 163 regresiones).
- Gateway HTTPS y bloqueo de destinos: **8 pruebas**.
- Reinicio real del contenedor FastAPI descartable: **aprobado**, concesión recuperada
  y acción completada una sola vez. También se verifica caída antes del commit,
  rollback de propuestas, fencing de un proceso anterior y reapertura del pool.
- Regresión backend heredada: **484 pruebas**.
- Playwright 2Q: **8 pruebas**, cuatro recorridos en escritorio y cuatro en celular.
  Incluyen guardado en PostgreSQL, recarga, historial, selección entre páginas,
  filtros, cancelación, propuesta ajena y reanudación sin repetir intentos.
- Playwright demo: **46 pruebas**; regresión general conectada: **138 pruebas**
  (16 casos de escenarios alternativos se ejecutan en sus suites separadas).
- Piloto Hileret con PDF auténtico: **2 pruebas**, escritorio y celular.
- Canales conectado: **8 pruebas**, escritorio y celular.
- Total: **677 pruebas backend/HTTPS + reinicio real**, y **202 Playwright**.
- TypeScript y builds normal/integración, Ruff y formato: aprobados.

La comprobación HTTPS se repitió correctamente después de cerrar la pasarela de
vista previa que ocupaba el puerto local. Las suites requieren **8443 libre**;
no se cambió TLS ni se desactivó ningún bloqueo. Los procesos de test ahora se
inician individualmente con `compose exec` dentro del backend cuyo aislamiento
ya fue validado, evitando crear otro contenedor idéntico para cada módulo.

Medición con PostgreSQL 16.6 y **5.000 variantes sintéticas sin fichas/documentos
completos para las 5.000**; no representa aún una carga documental real del cliente:

| Operación | Resultado |
| --- | --- |
| Cola paginada de 50 variantes, 2Q activo | 8 consultas; 3,776 s con tracemalloc |
| Memoria Python máxima durante esa consulta | 27,71 MiB |
| Respuesta JSON de cola | 134.357 bytes |
| Previsualización persistida de las 5.000 | 6,560 s |
| Procesar un paso de 5 tareas sobre ese catálogo | 0,083 s |
| Regresión Canales, flag 2Q desactivado | 6 consultas tanto en 50 como en 5.000; 2,245 s en 5.000 |

La optimización y las dos consultas documentales se activan sólo con el flag 2Q
y PostgreSQL. Con el flag apagado se conserva la lectura anterior y no se consultan
las tablas documentales o de lotes. SQLite heredado conserva también su recorrido;
la cola persistente nueva requiere explícitamente PostgreSQL.

Los valores y el alcance están conservados en
`frontend/artifacts/editorial-2q-validation.json`. No se endurecen conclusiones de
rendimiento sobre documentos reales todavía no autorizados.

En la demostración de escritorio, la ficha inicial estaba vacía: el lote generó
una propuesta, bloqueó otras cinco variantes sin documentos y conservó todo para
revisión. El operador aceptó sólo **marca**; el editor guardó versión 1 y la recuperó
tras recargar. En celular se repitió el recorrido sobre otra propuesta, conservando
la marca ya completada y aceptando sólo **fabricante**, con versión posterior.
Los demás campos permanecen sin aplicar. Sus citas y decisiones siguen en el
historial existente. SEO sin respaldo, EAN propuesto, notas y recursos multimedia
no se inventan.

Capturas reproducibles:

- `frontend/artifacts/batches-preview-desktop.png` y `batches-preview-mobile.png`.
- `frontend/artifacts/batches-results-desktop.png` y `batches-results-mobile.png`.
- `frontend/artifacts/batches-proposal-desktop.png` y `batches-proposal-mobile.png`.

Las capturas muestran únicamente dietética sintética. Hileret/MAMA no se vinculan,
no reciben aprobaciones transferidas ni se modifican para hacer pasar el recorrido.

## Pendientes para uso auténtico

- Mantener el cerco del frontend de integración: exige HTTPS loopback y el marcador
  `local-synthetic`. No admite todavía una URL productiva. Un modo conectado auténtico
  requiere autorización/configuración revisada usando los mismos contratos, sin
  quitar las protecciones del demo o del arnés.
- Autorizar el uso de la captura Ecomm-App auténtica y comprobar identidad/cantidad
  de cada variante mediante la integración existente, sin vincular por EAN/SKU.
- Revisar despliegue, migración aditiva y configuración antes de habilitar este flag
  fuera del entorno aislado. No se realizan en esta etapa.
- Documentación auténtica vigente, citas y revisión humana del cliente. Los casos
  bloqueados deben resolverse por Evidencias, no por generación inventada.
- IA real requiere autorización separada, presupuesto/cuotas, proveedor y límites
  de coste. Aquí se reutiliza sólo el generador determinista, con consumo USD 0.
- La ejecución avanza mientras el operador mantiene el recorrido activo. Trabajo
  autónomo sin navegador requerirá una decisión posterior sobre ejecución; la cola
  y la recuperación ya quedan persistidas, sin activar tareas programadas ahora.

## Archivos de esta entrega

Se agregan/ajustan los siguientes archivos; las capturas históricas reescritas por
las regresiones se restituyen para no mezclar entregas:

```text
backend/app/api/routes/documental_workspace.py
backend/app/api/routes/editorial_batches.py
backend/app/core/config.py
backend/app/main.py
backend/app/services/documental/proposals.py
backend/app/services/documental/research.py
backend/app/services/ecomm_api_work_queue_service.py
backend/app/services/editorial_batches/__init__.py
backend/app/services/editorial_batches/context.py
backend/app/services/editorial_batches/migration.py
backend/app/services/editorial_batches/queue_projection.py
backend/app/services/editorial_batches/service.py
backend/app/services/editorial_batches/storage.py
backend/integration_sandbox/bootstrap.py
backend/integration_sandbox/channel_checks.py
backend/integration_sandbox/editorial_checks.py
backend/integration_sandbox/editorial_fixtures.py
backend/integration_sandbox/editorial_restart.py
backend/integration_sandbox/policy.py
frontend/artifacts/batches-preview-desktop.png
frontend/artifacts/batches-preview-mobile.png
frontend/artifacts/batches-proposal-desktop.png
frontend/artifacts/batches-proposal-mobile.png
frontend/artifacts/batches-results-desktop.png
frontend/artifacts/batches-results-mobile.png
frontend/artifacts/editorial-2q-validation.json
frontend/integration-tests/batches-connected.spec.ts
frontend/src/integration/BatchPanel.tsx
frontend/src/integration/IntegrationCatalog.tsx
frontend/src/integration/PersistentWorkspace.tsx
frontend/src/integration/ProposalPanel.tsx
frontend/src/integration/batches.css
frontend/src/integration/catalog-adapter.ts
frontend/src/integration/isolation.ts
frontend/src/integration/proposal-adapter.ts
integration/EDITORIAL-2Q.md
integration/browser_tests.py
integration/run.py
integration/test_batch_restart.py
```
