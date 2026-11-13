# Etapa 2R — Dashboard operativo y lotes autónomos

Punto de partida comprobado: rama `feature/kiki-tech-2-dashboard`, HEAD
`ea87954a45ed4785d66025c61e471da3382c16d6`, árbol limpio. Sin conexiones productivas,
OpenAI real, credenciales reales, Render, push, PR, merge ni despliegue. IA: USD 0.

## Dashboard único

La misma aplicación conserva las cinco pestañas **Ficha, Evidencias, IA, Canales e
Historial**. Los cuatro indicadores principales muestran variantes Ecomm-App,
identidad por revisar, ML confirmado en captura y vínculos TN verificados. El CSV
sigue sin acreditar publicación actual en Tiendanube. No se suman publicaciones y
variantes ni se cuentan candidatos como publicaciones.

Los demás indicadores editoriales, de canales y fechas permanecen en **Más
indicadores y alcance de capturas**. Cada indicador aparece una sola vez y sigue
filtrando la misma tabla, conservando búsqueda, paginación y contexto de URL.
La tabla queda después de la búsqueda/filtros, con una barra compacta de selección
siempre recuperable. Operaciones, previsualizaciones y resultados se abren en el
panel lateral reutilizado; no desplazan permanentemente la tabla ni crean páginas.
Se puede cerrar el panel, editar otra variante y regresar a los lotes guardados.

La selección conserva Ecomm ID exacto. El SKU/EAN compartido no fusiona variantes;
los pilotos auxiliares MAMA/Hileret siguen fuera del catálogo maestro y con su
identidad auténtica pendiente. Se conservan sus originales, decisiones e historial.

## Ejecución y persistencia reutilizadas

Se conserva la cola de 2Q y las mismas tablas `kiki_editorial_batches` e
`kiki_editorial_batch_items`. No hay otro catálogo, editor, generador ni base
comercial. El ejecutor usa `Batches`, `Research`, `Proposals`, `KikiAiEditorialDraft`,
`EcommApiProductWorkspace` y la captura API existente, con sus validaciones,
identidad, citas, estados editoriales, revisión humana y control de versiones.

El navegador **no solicita pasos** ni mantiene vivo el trabajo. Sólo crea una
previsualización, confirma el lote, consulta estado, solicita cancelación y revisa
resultados. `/step` se conserva para compatibilidad del perfil manual, pero se
rechaza cuando está habilitada la ejecución autónoma.

1. La petición de previsualización congela IDs de la captura y guarda ítems
   PREPARING en grupos de 100. No obtiene documentos de Internet ni genera fichas.
2. El ejecutor analiza grupos acotados y persiste progreso, versiones y evidencias.
   El trabajo se puede recuperar después de cerrar el navegador o reiniciar el proceso.
3. Al terminar, el lote queda PREVIEW. **No se ejecuta sin confirmación explícita**
   con revisión, huella e idempotency key. La huella final y los resultados coinciden
   con el recorrido de referencia de 2Q para entradas equivalentes.
4. El backend procesa los trabajos autorizados en pasos limitados, creando propuestas
   deterministas sólo para campos vacíos respaldados, o tareas de revisión humana.
5. Las propuestas se abren por su ID exacto en IA. Su aceptación por campo y guardado
   siguen utilizando el editor versionado. No se aprueban fichas ni se publica automáticamente.

Estados visibles: **Pendiente, Ejecutándose, Completado, Completado con bloqueos,
Bloqueado, Fallido y Cancelado**. Se agregan Preparando previsualización y Cancelación
solicitada mientras corresponde. Se muestran cantidades preparadas, procesadas,
completadas, bloqueadas, pendientes, en proceso, fallidas y canceladas. Los conflictos
siguen registrados por variante, separados de ausencia de documentación.

## Reclamación, recuperación y cancelación

- Reserva corta mediante advisory lock transaccional y `SKIP LOCKED`, con propietario
  y concesión persistidos en PostgreSQL. Dos ejecutores no reclaman la misma acción.
- La reserva considera otras variantes en ejecución con el mismo Ecomm ID, incluso
  en otro lote. Espera sin fusionar productos ni confundir SKUs relacionados.
- Los bloqueos del trabajo usan `FOR NO KEY UPDATE`, manteniendo exclusión entre
  ejecutores y permitiendo registrar una cancelación mientras termina un paso.
- Un token de propiedad invalida al ejecutor anterior. Las concesiones vencidas se
  recuperan; los ítems terminados nunca vuelven a ejecutarse al reiniciar.
- Resultados y propuestas se confirman en una sola transacción mediante la fachada
  de sesión existente de 2Q. Un fallo revierte el paso entero.
- Máximo tres intentos por variante; errores de previsualización también acotados.
  Los errores requieren revisión/reintento explícito; el reinicio de un proceso no
  transforma hechos dudosos en aprobaciones.
- La tabla aditiva `kiki_editorial_batch_signals` conserva fecha y actor de la
  cancelación. La API registra la intención sin esperar el bloqueo de la generación.
  El ejecutor la consulta entre variantes y al cerrar el paso: conserva lo completado
  y cancela lo pendiente. Una solicitud que llega después de terminar no borra resultados.
- Las lecturas documentales quedan bajo el control transaccional existente antes de
  consultar hechos/documentos. La previsualización y el procesamiento revalidan versiones;
  el guardado posterior conserva el 409 existente frente a cambios de otra sesión.

## Proceso local controlado y aislamiento

`Executor` es un consumidor opt-in de la cola; no migra esquema ni inicia servicios
externos. `kiki_editorial_executor_enabled` es **false por defecto**. No se agrega
un worker al inicio del backend productivo ni se cambian variables de Render.

El Dockerfile de integración usa un supervisor **exclusivo del arnés** que valida
su entorno limpio e inicia únicamente dos comandos fijos: FastAPI de pruebas y el
módulo ejecutor. Cada hijo ejecuta el preflight de configuración, destino/usuario
PostgreSQL y bloqueo de red **antes de importar la aplicación o el engine**. El
supervisor no importa módulos de aplicación, no accede a credenciales ni a proveedores.
Se inicia el ejecutor después de comprobar la disponibilidad del backend/migración.
Reinicia un ejecutor caído hasta tres veces; ante inestabilidad se detiene visiblemente.
El estado del trabajo permanece en PostgreSQL, no en la memoria del supervisor.

El arnés sigue usando el proyecto Docker fijo, `network:none`, usuario sin privilegios,
raíz de sólo lectura, API/PG por sockets y gateway HTTPS exclusivamente loopback. No
se crean contenedores/servicios productivos ni puertos públicos. Se mantienen los
bloqueos de red, subprocess del backend/ejecutor, TLS, recursos remotos y variables
heredadas. El pequeño supervisor de pruebas es el único lanzador de comandos fijos;
no es una excepción de red o ejecución accesible desde la API.

`integration/run.py` genera el modo local `manual` para pruebas backend y `backend`
para `up`/`browser-test`. No acepta entornos productivos. Un catálogo escalado sólo
sobrevive a reinicios si coincide exactamente con el fixture sintético conocido;
la semilla no acepta ni reemplaza capturas auténticas o datos desconocidos.

La concesión normal es de 60 segundos, configurable entre 3 y 120; el arnés usa 6
segundos para las pruebas de muerte de procesos. El tamaño de análisis es 100 por
paso como máximo y se divide si excede el presupuesto de contexto. El procesamiento
conserva los límites de 2Q: 5 por paso, hasta 20; 10 segundos con cesión entre ítems;
2 MB de contexto por defecto, hasta 8 MB. No se truncan citas para forzar aprobaciones.

## Optimización y comparación equivalente

Los originales/base64 e historiales de documentos no se cargan en los lotes. Para
analizar se proyectan los campos necesarios, fechas de revisión y hechos sin sus
historiales; las decisiones y citas originales permanecen completas en PostgreSQL.
El procesamiento que necesita los servicios versionados conserva sus contratos.

El ejecutor mantiene sólo una copia normalizada de la captura, validada contra el
SHA-256 de sus bytes en PostgreSQL bajo bloqueo compartido. Si cambia la captura,
se invalida esa caché; no es otro catálogo ni una fuente autoritativa en memoria.
Se libera el contexto pesado después de cada grupo. Las reservas no dependen de
esa caché: todos los IDs, estados, versiones, evidencias y propietarios se persisten.

La comparación vuelve a ejecutar el algoritmo síncrono de referencia de 2Q y el
recorrido nuevo con **los mismos 5.000 IDs, captura y operación**, instrumentados
con `tracemalloc` y contador SQL en el mismo arnés. Se verifica igualdad de resumen,
huella final y todas las versiones/identidades por ítem. Como en el punto de referencia,
las 5.000 variantes no tienen 5.000 fichas/documentos completos; no se presenta esta
medición como carga documental real del cliente.

Medición equivalente repetida en la versión final:

| Fase | Tiempo | Consultas SQL | Pico de asignaciones Python |
| --- | ---: | ---: | ---: |
| Previsualización síncrona de referencia 2Q | 10,140 s | 1.407 | 7,54 MiB |
| Petición nueva: guardar selección para analizar | 0,945 s | 58 | 7,06 MiB |
| Análisis autónomo completo recuperable | 11,380 s | 1.057 | 8,35 MiB |

La petición libera la interfaz unas diez veces antes. El coste total nuevo es
aproximadamente 12,325 s, frente a 10,140 s del recorrido síncrono: las transacciones,
reservas y actualizaciones recuperables agregan coste. No se presenta como una
mejora de tiempo total. Las consultas totales bajan de 1.407 a 1.115, con resultados
comerciales, huella y versiones iguales. La caché retiene sólo una captura y el
análisis conserva presupuestos por contexto.

La cola normal también se midió: 5.000 variantes, 8 consultas, 27,74 MiB y 2,390 s
con instrumentación. El [informe original de 2Q](EDITORIAL-2Q.md) separa la consulta
paginada (8 SQL, 27,71 MiB, 3,776 s con tracemalloc) de la previsualización persistida
completa (6,560 s). No atribuye aquellas 8 SQL y 27,71 MiB a la previsualización.
Por eso la tabla anterior vuelve a ejecutar las dos rutas de previsualización con
las mismas entradas e instrumentación, en vez de mezclar mediciones de fases
diferentes o atribuir a 2Q un contador no medido para esa fase.

Las cifras y su alcance quedan en `frontend/artifacts/operations-2r-validation.json`.

## Migración y reversión

`backend/app/services/editorial_batches/migration_2r.py` agrega sólo la tabla de
señales y dos índices de coordinación. No altera fichas, documentos, propuestas,
canales, sesiones ni credenciales. Se ejecutó/probó únicamente en PostgreSQL
descartable, después de verificar el destino antes de inicializar el engine.

UP instala señales e índices. Antes de DOWN se deben terminar/cancelar los lotes
PREPARING/PENDING/RUNNING y exportar las señales si se desean conservar. DOWN elimina
señales e índices y conserva todas las tablas/datos de 2Q. La cadena 2R → 2Q → 2R
se prueba para verificar compatibilidad de migraciones. No se traslada a producción.

## Reproducir

Desde la raíz, sin cargar `.env` productivo y con 8443 libre:

```bash
python integration/run.py build
python integration/run.py test
python integration/run.py legacy-test
python integration/run.py browser-test
python integration/run.py browser-test --channels
python integration/run.py browser-test --batches
python integration/run.py browser-test --autonomous
```

El último escenario usa 5.000 variantes sintéticas; los anteriores conservan los
casos previos. Los flags de escenarios son mutuamente excluyentes. Para explorar
manualmente: `python integration/run.py up --autonomous`, que mantiene activos el
backend y su supervisor; cerrar el navegador no detiene los trabajos. Detener el
entorno completo retira la base descartable y sus datos. Reiniciar sólo FastAPI o
el ejecutor mientras PostgreSQL sigue activo conserva los trabajos. La URL loopback
pertenece al entorno remoto; no se agrega túnel o servicio público para Windows.

## Validación y entrega

Backend: **208 comprobaciones** del entorno aislado y gateway, incluidas 15 nuevas
de ejecución autónoma, más **484 regresiones heredadas**. PostgreSQL descartable
validó reclamación simultánea, variantes incompatibles entre lotes, expiración de
propiedad, cancelación durante una transacción, errores acotados, persistencia,
versiones de fichas y migración/reversión. Se repitieron las 15 nuevas y las 484
heredadas tras ajustar los contadores de cancelación.

La prueba de procesos mata con SIGKILL al ejecutor después de una reserva duradera,
permite que el supervisor lo reinicie, usa dos ejecutores y luego reinicia realmente
el backend. Termina con **1.000 tareas únicas**, sin repetir tareas completadas ni
añadir fichas comerciales. No simula un reinicio con una nueva instancia Python
dentro del mismo proceso.

Playwright comprueba el cierre de un proceso Chromium propio con un lote autorizado
en curso. Mientras no hay navegador se observa avance mediante consultas GET; se
reabre una sesión del dashboard y se recupera el mismo lote. Otros casos verifican
5.000 seleccionados, previsualización sin autorización, cancelación, estados mixtos,
citas, aprobación individual y guardado en el editor existente. Se mantienen las
pruebas anteriores de cinco pestañas, canales, documentos e identidad.

La regresión detectó un botón inferior tapado por la barra fija en celular: el
shorthand móvil heredado llevaba `!important` y anulaba el espacio inferior. Se
corrigió la prioridad exclusivamente dentro de `.i-app`; no se forzó el clic en
Playwright. El demo conserva sus **46 pruebas aprobadas**.

TypeScript, build general, build de integración, Ruff, formato y `git diff --check`
aprobados. Vite conserva su advertencia de tamaño de bundle; no bloquea los builds.
Los contenedores, procesos gateway y volúmenes descartables se retiran al terminar.

Resultado final de Playwright: **210 pruebas aprobadas** en conjunto:

| Suite | Aprobadas |
| --- | ---: |
| Dashboard conectado, regresión general | 138 |
| Piloto Hileret con PDF auténtico | 2 |
| Canales, escenario sintético explícito | 8 |
| Lotes existentes adaptados al ejecutor backend | 8 |
| Ejecución autónoma y 5.000 variantes | 8 |
| Demo sin backend | 46 |

La suite general omite los 24 casos que requieren escenarios alternativos; esos
mismos casos se ejecutaron y aprobaron separadamente en sus tres perfiles. No se
cuentan los reintentos ni las repeticiones de verificación como pruebas adicionales.
Las 138 pruebas generales y el piloto auténtico volvieron a pasar después de la
corrección de espacio inferior en celular. Los escenarios 2R también verifican la
alineación de los cuatro indicadores y regeneran las capturas con el CSS final.

Capturas nuevas, siempre con fixtures identificados como sintéticos:

| Vista | Escritorio | Celular |
| --- | --- | --- |
| Dashboard compacto | [captura](../frontend/artifacts/operations-2r-dashboard-desktop.png) | [captura](../frontend/artifacts/operations-2r-dashboard-mobile.png) |
| Previsualización de 5.000 variantes | [captura](../frontend/artifacts/operations-2r-preview-desktop.png) | [captura](../frontend/artifacts/operations-2r-preview-mobile.png) |
| Progreso recuperado | [captura](../frontend/artifacts/operations-2r-progress-desktop.png) | [captura](../frontend/artifacts/operations-2r-progress-mobile.png) |
| Propuesta guardada mediante el editor | [captura](../frontend/artifacts/operations-2r-editor-desktop.png) | [captura](../frontend/artifacts/operations-2r-editor-mobile.png) |

Permanece pendiente autorizar/configurar el catálogo auténtico por la integración
existente, revisar un eventual despliegue/migración y presupuestar cualquier IA real.
El frontend de integración sigue exigiendo HTTPS loopback y `local-synthetic`;
esta entrega no lo conecta a producción ni habilita consumo económico.

Límites pendientes: la medición no contiene 5.000 expedientes documentales completos;
esa carga necesita una validación específica antes de uso real. Se conserva el bloqueo
documental global existente para impedir revocaciones simultáneas durante un paso:
dos ejecutores son seguros, pero ese tramo se serializa y puede limitar el rendimiento.
El tiempo por paso es cooperativo entre variantes; no interrumpe una operación
transaccional a mitad de guardado. No se promete una duración máxima para cualquier
documento real ni se habilitan originales externos para acelerar la medición.

## Archivos de esta entrega

- `backend/app/api/routes/editorial_batches.py`
- `backend/app/core/config.py`
- `backend/app/services/editorial_batches/context.py`
- `backend/app/services/editorial_batches/executor.py`
- `backend/app/services/editorial_batches/migration_2r.py`
- `backend/app/services/editorial_batches/preview_projection.py`
- `backend/app/services/editorial_batches/service.py`
- `backend/app/services/editorial_batches/status.py`
- `backend/app/services/editorial_batches/storage.py`
- `backend/integration_sandbox/autonomous_checks.py`
- `backend/integration_sandbox/autonomous_restart.py`
- `backend/integration_sandbox/bootstrap.py`
- `backend/integration_sandbox/editorial_checks.py`
- `backend/integration_sandbox/editorial_executor.py`
- `backend/integration_sandbox/editorial_fixtures.py`
- `backend/integration_sandbox/fixtures.py`
- `backend/integration_sandbox/runtime_supervisor.py`
- `backend/integration_sandbox/server.py`
- `frontend/artifacts/operations-2r-dashboard-desktop.png`
- `frontend/artifacts/operations-2r-dashboard-mobile.png`
- `frontend/artifacts/operations-2r-editor-desktop.png`
- `frontend/artifacts/operations-2r-editor-mobile.png`
- `frontend/artifacts/operations-2r-preview-desktop.png`
- `frontend/artifacts/operations-2r-preview-mobile.png`
- `frontend/artifacts/operations-2r-progress-desktop.png`
- `frontend/artifacts/operations-2r-progress-mobile.png`
- `frontend/artifacts/operations-2r-validation.json`
- `frontend/integration-tests/autonomous-connected.spec.ts`
- `frontend/integration-tests/batches-connected.spec.ts`
- `frontend/integration-tests/channels-connected.spec.ts`
- `frontend/src/integration/BatchPanel.tsx`
- `frontend/src/integration/IntegrationCatalog.tsx`
- `frontend/src/integration/batches.css`
- `frontend/src/integration/integration.css`
- `frontend/src/prototype/CatalogView.tsx`
- `integration/Dockerfile`
- `integration/OPERATIONS-2R.md`
- `integration/browser_tests.py`
- `integration/run.py`
- `integration/test_autonomous_restart.py`

Las capturas históricas regeneradas por regresiones se restauran; se conservan sólo
las capturas nuevas 2R. No se modificaron dependencias, credenciales, configuración
de Render ni integraciones de proveedores.
