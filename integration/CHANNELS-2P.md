# Etapa 2P — Canales dentro del dashboard conectado

Base verificada: `feature/kiki-tech-2-dashboard`,
`c264570bdd90767ba4142ecb6840bbcab2c891cc`, árbol inicialmente limpio.

Se completa la pestaña Canales del panel existente y se conectan sus indicadores
a la misma tabla de variantes API. El trabajo se ejecuta exclusivamente en el
FastAPI/PostgreSQL descartables existentes. No se habilita acceso productivo.

## Servicios y contratos reutilizados

- `ecomm_channel_coverage_service.build_channel_coverage`: conserva su clasificación
  histórica de candidatos y recibe una proyección API opcional. Sus códigos
  anteriores siguen presentes para compatibilidad.
- `ecomm_api_work_queue_service.build_queue`: reutiliza búsqueda, paginación,
  indicadores globales y filtros, con filas por Ecomm ID, no por SKU/EAN.
- Capturas `CatalogSnapshot` de `ECOMM_APP_API_STAGE`, `MERCADOLIBRE_API` y
  `TIENDANUBE`. No hay fallback a `ECOMM_APP`/ML Excel ni lecturas en vivo.
- Normalización/contraste de presentaciones y cantidades explícitas de
  `tiendanube_assisted_match_service`, y validación de códigos del editor existente.
- `transform_item` para los ejemplos ML y `TiendanubeCsvService.import_csv` con
  `parse_tiendanube_csv` para el escenario de aceptación. No se escribió otro
  cliente ni importador. No se llama a OAuth o al cliente HTTP de ML.
- Tablas de decisiones existentes `InventoryLinkageDecision` y
  `TiendanubeMatchDecision`, con autenticación, CSRF e historial habituales.

El endpoint existente GET `/api/ecomm-app/workspace/queue` incorpora filtros
`ml_confirmed`, `tn_verified`, `channel_candidates`, `channel_conflicts`,
`channel_no_evidence` y `channel_stale`. Los valores son calculados por servidor,
independientes de la página visible. La búsqueda y el filtro se combinan y se
conservan en la URL junto con página, producto y pestaña.

La adaptación mínima por variante añade:

| Método y ruta | Uso |
| --- | --- |
| GET `/api/ecomm-app/workspace/{ecomm_id}/channels` | Capturas, candidatos, identidad, bloqueos, decisiones e historial de esta variante |
| POST `/api/ecomm-app/workspace/{ecomm_id}/channels/review` | Validar o revocar **una relación interna**, sin escribir en proveedores |

El panel reutiliza Ficha, Evidencias, IA e Historial. No se crean otras páginas,
productos, catálogos comerciales o persistencias de fichas.

## Significado de los estados

| Estado mostrado | Qué acredita |
| --- | --- |
| Publicación confirmada en captura | ML: relación API revisada por un operador y fila activa en una captura vigente. No es estado en vivo ni prueba de que Ecomm-App ya haya ejecutado una vinculación externa. |
| Coincidencia candidata | Indicios de la copia por SKU. No confirma identidad ni publicación. |
| Vinculación pendiente de validar | Ambigüedad, packs, múltiples filas o revisión anterior que requiere contraste. |
| Sin evidencia suficiente | Copia ausente o sin evidencia atribuible. No equivale a «no publicado». |
| Información desactualizada | Copia sin fecha válida, futura o fuera del intervalo de revisión. No acredita estado actual. |
| Conflicto de identidad | Discrepancias de identidad/códigos; no permite confirmar ni fusionar variantes. |
| Vínculo verificado · publicación sin confirmar | Relación interna revisada; en TN, el CSV no acredita publicación actual. En ML puede corresponder a una publicación pausada u otro estado sin actividad confirmada. |

ML usa el umbral `ml_snapshot_fresh_hours` ya existente. TN aplica una política
local conservadora de revisión de 24 horas; ese umbral no demuestra por sí mismo
publicación vigente y debe revisarse comercialmente antes de una futura activación.
Siempre se muestran origen, fecha y alcance.

**Limitación real de Tiendanube:** el importador CSV existente no conserva un
estado verificable de publicación. No se inventa ese dato ni se interpreta una
fila como publicación actual. El dashboard muestra explícitamente pendiente la
cantidad de publicaciones TN y ofrece el filtro de vínculos TN revisados. No
presenta cero publicaciones como respuesta a esa falta de información.

`confirmed_listing: false` sigue significando ausencia de confirmación, no ausencia
demostrada de publicación. Los estados editoriales continúan siendo independientes.

## Revalidación e identidad

Se conservan separados SKU, barcode, GTIN, marca con su origen, presentación,
condición de combo de producto/variante y cantidad comercial. El panel permite
consultar la identidad API utilizada en la revisión y los datos originales del canal.
En TN se muestra el identificador URL (slug) que conserva el CSV. Su clave interna
de fila es una huella para revisar y versionar, **no un ID auténtico de Tiendanube**.

No hay vinculación automática por coincidencia de SKU, EAN o familia. Las filas
ML con variación sin SKU propio no se heredan desde el SKU del padre. IDs ML
vacíos/incorrectos o repetidos no permiten validar una fila única. Se rechazan
capturas API con identidades vacías, inválidas o duplicadas.

La validación interna exige:

1. Elegir una fila concreta y un Ecomm ID exacto.
2. Contrastar nombre, marca, presentación, cantidad, tipo de venta y códigos.
3. Registrar explícitamente cantidad comercial y motivo; no se deduce una unidad
   desde `is_combo=False`. La cantidad registrada es una **declaración del operador**,
   identificada como tal en historial, no un dato inventado del proveedor.
4. No tener bloqueos de códigos, marca/presentación, composición de pack, identidad
   o vigencia. Si producto y variante discrepan en su marca de combo, se bloquea.
5. Confirmar el diálogo de revisión antes de persistir.

Las aprobaciones del entorno se identifican como decisiones de un operador de
prueba. No son aprobaciones auténticas del cliente. Hileret/MAMA conservan Ecomm ID
real pendiente y no reciben asociaciones ni decisiones transferidas desde estos casos.

Una fila revisada para otra variante bloquea asignaciones nuevas. Para cambiarla
se requiere revocar explícitamente la relación anterior desde su variante y
realizar otra revisión. El código no modifica la relación en Ecomm-App, ML ni TN.

## Persistencia, compatibilidad y concurrencia

**No hay nuevas tablas ni migraciones en 2P.** Se utiliza el mismo PostgreSQL y
las tablas de decisiones existentes. Las claves `API_ML:{id}` y `API_TN:{clave}`,
y el perfil `API_VARIANT_CHANNEL_REVIEW_V1`, separan las revisiones API de las
históricas. Una decisión Excel, aunque coincida su número de Ecomm ID, nunca se
promueve a una vinculación API ni se sobrescribe automáticamente.

Cada decisión conserva actor/sesión, motivo, cantidad declarada, comprobaciones,
identidad API, fila de canal, fecha de captura y huella. El historial se conserva
al aprobar, renovar o revocar. Huellas de identidad/captura y revisión optimista
impiden reutilizar decisiones ante cambios. Fechas, contenido y condiciones de
vigencia se reevalúan en cada lectura; un GET no refresca tokens ni sincroniza.

POST bloquea transaccionalmente las filas de captura existentes en orden estable
y comprueba huella/revisión antes de persistir. Dos operadores sobre la misma
revisión producen un éxito y un 409, sin sobrescritura silenciosa. La interfaz
conserva el motivo y recupera datos para comparar tras un conflicto, sin reintento
ni confirmación automática.

El nuevo comportamiento está desactivado en configuración habitual mediante
`kiki_channel_workspace_enabled=False`. Sólo el bootstrap aislado lo habilita en
esta etapa. No se cambia Render, variables o credenciales de producción.

## Indicadores y costo de lectura

Los indicadores cuentan variantes Ecomm únicas. Se muestra por separado la
cantidad de publicaciones ML confirmadas; dos publicaciones de una variante
incrementan ese total, pero la variante se cuenta una sola vez. La confirmación
de una fila no oculta los candidatos pendientes de otras filas del mismo canal.
Los filtros de candidatos, conflictos, insuficiencia y vigencia pueden superponerse;
no se suman como si fueran entidades distintas.

El servicio construye índices de SKU/filas y carga las decisiones en dos consultas
agrupadas; no consulta al proveedor ni a la base por cada fila. El panel obtiene
su detalle al seleccionar un producto. La cola devuelve estados y metadatos,
sin trasladar candidatos e historiales completos por cada fila de la tabla. El escenario mide 50 y 5.000 variantes,
con una respuesta paginada de 25 filas y verificación de un número constante de
consultas SQL. La medición final de Canales fue:

| Variantes sintéticas | Consultas SQL | Tiempo local |
| --- | --- | --- |
| 50 | 6 | 0,017 s |
| 5.000 | 6 | 1,186 s |

No hay consultas por fila ni solicitudes HTTP a proveedores.

No es una garantía de rendimiento productivo. La lectura sigue siendo lineal
sobre capturas JSON y decisiones. El historial y las filas candidatas visibles
requieren límites/paginación adicionales para grandes volúmenes; se muestran
hasta ocho candidatas y se informa su cantidad total, sin fingir cobertura completa.

## Inicio del escenario aislado

Con Docker local y dependencias del proyecto, desde la raíz:

```bash
python3 integration/run.py build
python3 integration/run.py up --channels
```

`--channels` exige una base sintética nueva: verifica destino/rol/marcador antes
de importar el engine, y rechaza datos previos ajenos al escenario. Reutiliza los
cuatro contenedores sin red existentes y no añade servicios. Instala variaciones
sintéticas de las seis identidades del fixture, marca los packs x2/x6, usa DTOs ML
inventados y procesa un CSV redactado para esta prueba mediante el importador actual.
Los identificadores ML tienen forma del contrato pero **son inventados**, nunca
se consultan ni se presentan como publicaciones del cliente.

La captura ML se fecha al iniciar; el CSV se fecha 48 horas antes para demostrar
el bloqueo por vigencia. Incluye dos decisiones antiguas de prueba que no deben
transferirse al catálogo API. El usuario y autenticación de prueba son los del
README de integración. La URL `https://127.0.0.1:8443/` sólo funciona en la máquina
que ejecuta el entorno; no es un enlace público ni un despliegue.

Sin `--channels`, se conserva el escenario base de 2N/2O con ausencia de capturas
ML/TN. Ctrl+C retira contenedores y datos descartables. No usar variables productivas
para convertir ese arnés en un entorno real.

## Pruebas y capturas

```bash
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
python3 integration/run.py browser-test --channels
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run build:integration
npm --prefix frontend test
```

Las pruebas nuevas de navegador requieren el escenario explícito. En la suite
base se omiten esos casos y se ejecutan por separado con `--channels`; no se
cuentan omisiones como aprobaciones. El demo sigue sin backend.

| Validación | Resultado |
| --- | --- |
| Backend/aislamiento/PostgreSQL/documentos y pilotos previos | 153 regresiones aprobadas |
| Nuevos casos de Canales | 18 aprobados en la comprobación final; incluyen concurrencia, formatos desconocidos y estados superpuestos |
| Ejecución completa de backend | 169 aprobadas en la ejecución amplia (153 previas + 16 de Canales); las 18 finales incluyen las 16 repetidas y dos casos adicionales, no se suman repeticiones |
| Regresión heredada backend | 484 aprobadas, dos avisos anteriores de AnyIO |
| Playwright base 2N/2O | 138 aprobadas; ocho casos de escenario Canales omitidos aquí y ejecutados aparte |
| Playwright Hileret PDF auténtico local | 2 aprobadas |
| Playwright Canales, escritorio y celular | 8 aprobadas sobre el escenario explícito |
| Playwright demo, escritorio/celular/tablet | 46 aprobadas |
| TypeScript, builds demo/integración, Ruff y formato | Aprobados |

Las comprobaciones finales también aseguran que el resumen del catálogo no envía
los historiales completos de cada candidata. La inspección visual corrigió la
alineación de los controles de revisión y las capturas enfocan los estados del
canal y su alcance. No cambió la ficha comercial al revisar o revocar vínculos.
Se retiraron los contenedores, volumen y pasarela locales al terminar.

| Captura | Escritorio | Celular |
| --- | --- | --- |
| Panel Canales | [Ver](../frontend/artifacts/canales-2p-desktop.png) | [Ver](../frontend/artifacts/canales-2p-mobile.png) |
| Indicadores y tabla | [Ver](../frontend/artifacts/dashboard-canales-2p-desktop.png) | [Ver](../frontend/artifacts/dashboard-canales-2p-mobile.png) |
| Packs con SKU relacionado | [Ver](../frontend/artifacts/packs-canales-2p-desktop.png) | [Ver](../frontend/artifacts/packs-canales-2p-mobile.png) |

## Pendientes antes de automatizar masivamente

- Contrato confiable para publicación TN y política comercial de vigencia por fuente.
- Identificación auténtica y autorización de lectura de productos reales, sin
  convertir los pilotos sintéticos en identidades reales ni transferir aprobaciones.
- Evidencia estructurada de cantidad/composición que reduzca las declaraciones
  manuales; tratamiento de excepciones y rechazos de candidatas antes de lotes.
- La huella actual incluye los datos y fecha de la copia: incluso una renovación
  de captura sin cambio sustantivo de identidad requiere revisión. Antes de lotes,
  diseñar una renovación de vigencia que distinga esos cambios sin trasladar aprobaciones
  a identidades diferentes.
- Medir concurrencia real y reducir el alcance del bloqueo de captura si el volumen
  lo requiere. Evaluar lecturas proyectadas/paginación de decisiones e historial.
- Previsualización y trazabilidad de lotes, presupuesto, resultados y reanudación;
  los cambios externos requieren una autorización posterior y sus contratos seguros.
- Revisión de configuración, permisos y activación antes de una adopción real.

Sin llamadas productivas, refresco de tokens, publicación, sincronización externa,
OpenAI, cambios Render, push, PR, merge ni integración de PR #87.

## Archivos modificados

- `backend/app/api/routes/ecomm_api_channels.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/services/ecomm_api_channel_evidence.py`
- `backend/app/services/ecomm_api_work_queue_service.py`
- `backend/app/services/ecomm_channel_coverage_service.py`
- `backend/integration_sandbox/bootstrap.py`
- `backend/integration_sandbox/channel_checks.py`
- `backend/integration_sandbox/channel_fixtures.py`
- `backend/integration_sandbox/policy.py`
- `frontend/integration-tests/catalog.spec.ts`
- `frontend/integration-tests/channels-connected.spec.ts`
- `frontend/integration-tests/dashboard-connected.spec.ts`
- `frontend/src/integration/ChannelsPanel.tsx`
- `frontend/src/integration/IntegrationCatalog.tsx`
- `frontend/src/integration/PersistentWorkspace.tsx`
- `frontend/src/integration/catalog-adapter.ts`
- `frontend/src/integration/channel-adapter.ts`
- `frontend/src/integration/channel-labels.ts`
- `frontend/src/integration/integration.css`
- `frontend/src/integration/isolation.ts`
- `integration/CHANNELS-2P.md`
- `integration/browser_tests.py`
- `integration/run.py`

Además de las seis capturas 2P. Las capturas históricas regeneradas se restauran.
