# Etapa 2O — Evidencias y propuestas en el dashboard conectado

Base verificada antes de cambios: `feature/kiki-tech-2-dashboard`,
`51aea3cf681f635f01feb2f23b6f8b60eb24520d`, árbol limpio.

## Implementación y reutilización

El catálogo conectado conserva el dashboard 2N, filtros, indicadores, búsqueda,
paginación, URL y las cinco pestañas. Para sus variantes de API, **Evidencias e IA
usan ahora rutas autenticadas del backend habitual**, sin crear páginas ni otro
editor. La ejecución de esta entrega sigue exclusivamente en el entorno aislado.

Se extrajeron las reglas ya desarrolladas en 2E–2K a
`backend/app/services/documental/`: investigación, validación/citas/revocaciones,
versionado de documentos y originales, propuestas, revisión individual y contrato
para una futura IA. Los perfiles sintéticos anteriores heredan esos servicios;
conservan solamente fixtures, referencias de pilotos, revisiones simuladas y
excepciones explícitas del arnés. No hay un segundo algoritmo de propuestas ni
otra persistencia de fichas.

Los módulos compartidos no importan `integration_sandbox`, no incluyen documentos
de prueba, identidades inventadas o autenticación sintética. Reutilizan
`require_session`, `require_csrf`, `get_db` y el catálogo API capturado existente.
El flag `kiki_document_workspace_enabled` es **false por defecto**. No se cambian
variables de despliegue ni se habilita el servicio en producción.

## Contratos

Todos los siguientes son relativos a `/api/ecomm-app/workspace/{ecomm_id}`:

| Método y sufijo | Función |
| --- | --- |
| GET `/evidence` | Expediente, documentos, hechos, contradicciones y decisiones |
| POST `/evidence/extract` | Extracción existente; versión de expediente y documento |
| POST `/evidence/facts/{fact_id}/review` | Aprobar/rechazar/revocar con motivo y versiones |
| POST `/documents/import` | Incorporar archivo autorizado o referencia sin descargar |
| POST `/documents/{document_id}/provenance` | Revisar/revocar procedencia con versión |
| GET `/documents/{document_id}/original/{version}` | Recuperar los bytes y SHA-256 de esa versión |
| GET `/proposals` | Última propuesta documental de esta variante y su historial |
| POST `/proposals/generate` | Generación determinista desde hechos aprobados vigentes |
| POST `/proposals/{draft_id}/review` | Decisiones por campo, edición respaldada y revisión CAS |
| GET `/proposals/generation-context` | Contrato preparado para proveedor, deshabilitado |

El guardado sigue siendo **POST al workspace existente**, con `expected_version`,
CSRF y los encabezados pareados `X-Kiki-Proposal-Id` y
`X-Kiki-Proposal-Revision`. No se creó un endpoint de guardado equivalente.
El servicio combina sólo campos aceptados sobre la ficha base y guarda como
borrador mediante `EcommApiProductWorkspace.save`. El historial sigue siendo el
existente. Rechazados, no decididos y multimedia no se reemplazan.

Las rutas `/api/test-*` quedan reservadas a regresiones y pilotos auxiliares;
no son la implementación de Evidencias/IA para el catálogo conectado. Las
regresiones históricas del navegador usan un adaptador **exclusivamente de test**
para comprobar el perfil anterior. Los nuevos casos de aceptación no usan esa
adaptación: consumen directamente las rutas habituales, el parser aislado y
PostgreSQL, sin mocks de sus respuestas.

## Identidad, permisos y concurrencia

- Un documento local pertenece a un único Ecomm ID. No se comparte por SKU, EAN,
  nombre o familia. Cada presentación conserva expediente y decisiones propios.
- No se inventan marca, fabricante ni EAN cuando la captura no los aporta.
  Campos editoriales son referencias de contraste, no hechos aprobados.
- Se compara nombre, presentación, códigos disponibles, tipo unidad/pack y
  contradicciones editoriales. Si la presentación o tipo de venta son desconocidos,
  los hechos no se pueden aprobar. Barcode y GTIN incompatibles bloquean el flujo.
- Aprobar procedencia no aprueba hechos. Extraer no aprueba ni aplica información.
  Un archivo aportado y declarado oficial no se autentica por esa declaración.
- Cada aprobación necesita motivo, sesión y versiones vigentes. Cambios de
  documento/identidad, revocaciones y contradicciones invalidan hechos/propuestas.
- La propuesta incluye citas, ubicación, hashes y versiones por afirmación.
  La edición permite quitar/reordenar cláusulas completas respaldadas; una
  afirmación nueva requiere evidencia nueva. No se acepta redacción libre como
  si estuviera verificada.
- El mutex transaccional inicial evita actualizaciones perdidas en las decisiones;
  CAS del editor evita sobrescribir la ficha. Las aplicaciones fallidas se revierten.
  La autorización es la de administrador de la aplicación existente; no se creó
  un modelo de roles nuevo. La granularidad de permisos sigue siendo una limitación.
- `internal_only` expresa que no hay escrituras en proveedores. El servicio
  habitual no afirma aislar la red por sí mismo. El aislamiento real lo garantiza
  el arnés validado, sus contenedores sin red y las barreras existentes.

## Documentos y seguridad

Se reutiliza el parser en proceso/contenedor aislado, con transporte Unix,
restricciones de recursos, tamaño, MIME real, texto, páginas, contenido activo y
tiempo. El camino habitual admite como máximo **512 KiB**, 10 páginas y los tipos
ya soportados (PDF de texto, TXT, HTML pasivo y JSON). No ejecuta JavaScript ni
realiza OCR, descargas o búsquedas web. Las URLs son referencias de texto.

La excepción de tamaño por SHA-256 del PDF Hileret queda sólo en el perfil del
piloto sintético existente. Las rutas habituales no la importan ni aceptan su
límite ampliado. Sin parser Unix disponible, no hay fallback inseguro en el backend.
Las imágenes/videos externos siguen bloqueados en el frontend conectado.

El PDF original Hileret está disponible localmente en
`integration/fixtures/hileret-original.pdf`, SHA-256
`bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291`.
Se conserva el piloto y se incluye su regresión auténtica. El Ecomm ID real sigue
pendiente; sus decisiones automatizadas de prueba no se transfieren a las
variantes del catálogo ni se presentan como aprobaciones humanas del cliente.
MAMA permanece como caso de evidencia insuficiente, sin nueva vinculación.

## Persistencia y migración reversible

**Una misma base PostgreSQL.** No se crea otra base comercial. Las fichas siguen
en `ecomm_api_product_edits` y las propuestas en `kiki_ai_editorial_drafts`
(modelo `KikiAiEditorialDraft`, con identificador de generador y eventos propios).
Las propuestas documentales habituales usan la clave `ECOMM_DOCUMENTAL:{ecomm_id}`;
las sugerencias históricas conservan `ECOMM_API:{ecomm_id}`. Esa separación dentro
del mismo modelo evita que el lector histórico recupere una propuesta documental
como si fuera una sugerencia API/OpenAI. No se altera el servicio histórico.
Las tablas aditivas documentales son:

- `kiki_evidence_control`: control transaccional inicial.
- `kiki_evidence_documents`: versiones, procedencia, originales, hash e historial.
- `kiki_evidence_dossiers`: identidad, hechos y decisiones por Ecomm ID.

La migración explícita `app/services/documental/migration.py` contiene `UP` y
`DOWN`. Los modelos no forman parte del `Base.metadata.create_all` de arranque;
**el backend habitual no ejecuta DDL automáticamente**. La inicialización automática de
`UP` se limita al bootstrap del entorno descartable, después del preflight
que verifica destino, rol y marcador PostgreSQL antes de importar el engine.

Para una futura adopción, revisar y versionar la migración con las herramientas
de operación del proyecto, hacer copia/exportación de documentos, expedientes y
referencias de propuestas, ejecutar `UP` en una transacción y verificar tablas,
índice y control antes de habilitar el flag. No habilitar primero el flag ni
usar variables productivas dentro del arnés sintético.

Reversión futura: deshabilitar el flag y cerrar trabajos documentales, exportar
los registros y propuestas asociadas, y sólo con autorización ejecutar `DOWN` en
transacción. `DOWN` elimina esas tres tablas y su índice; **no elimina fichas ni
borradores históricos**. Las propuestas conservadas quedan sin respaldo
consultable y no deben aplicarse hasta recuperar una migración/datos compatibles.
En esta etapa la ida/vuelta se prueba sólo contra PostgreSQL descartable vacío.

El mutex es deliberadamente conservador y compartido para este primer flujo.
Su rendimiento con muchos operadores/documentos requiere medición antes de una
habilitación masiva. La consulta de documentos por variante tiene filtro e índice
por Ecomm ID; no descarga todos los originales al navegador. El almacenamiento
actual conserva originales en JSON/base64 con los límites existentes: evaluar
almacenamiento de objetos versionado cuando el volumen lo justifique, sin otro
sistema de fichas.

## Alcance de IA

No se ejecuta OpenAI ni existe consumo económico autorizado. El servicio histórico
`EcommAiEditor.suggest` propone título/descripcion/preguntas; no cubre una ficha
completa con pruebas documentales por afirmación. Se reutilizan su DTO y su modelo
de borradores, pero la generación de esta etapa usa el contrato y reglas 2F.

Se pueden proponer identidad, presentación, títulos, descripciones, detalles,
atributos, categoría/subcategoría y SEO sólo según hechos aprobados disponibles.
No se inventan ingredientes, alérgenos, nutrición, certificaciones, imágenes o
videos. Los campos sin respaldo se enumeran, no se completan por inferencia.
El contrato futuro conserva evidencia/versiones y presupuesto USD 0,00; activar un
proveedor requerirá revisión de modelo, costos, reservas y validación de salida.

## Recorrido de aceptación

Variante `900006`, **Lentejas sintéticas, 1 kg**, sin vínculo con productos reales:
catálogo → panel Evidencias → archivo TXT inventado explícitamente → revisión de
procedencia → extracción → revisión de cada hecho → IA → comparación actual/propuesto
y citas → título aceptado y descripción rechazada → reordenamiento de cláusulas
respaldadas → revisión → guardado como borrador → recarga → historial.

Antes: título inicial de prueba y descripción inicial. Después: título
`1 kg · Lentejas sintéticas`; descripción y multimedia conservadas. Persistencia
real en la base descartable. Otra presentación no obtiene documentos ni puede
aplicar la propuesta; revocar procedencia invalida hechos y propuesta.

## Validación y capturas

| Validación | Resultado |
| --- | --- |
| Backend/PostgreSQL/aislamiento/documentos/pilotos/gateway | 153 aprobadas; 15 nuevas del espacio documental habitual |
| Regresión heredada de backend | 484 aprobadas; dos avisos previos de AnyIO |
| Playwright del dashboard y perfiles históricos | 130 regresiones anteriores aprobadas |
| Playwright nuevo flujo conectado | 8 aprobadas (4 casos en escritorio y celular) |
| Repetición final dashboard 2N + flujo 2O | 32 aprobadas; las 24 de 2N son repetidas, no se suman otra vez |
| Playwright Hileret auténtico local | 2 aprobadas (escritorio y celular) |
| Playwright demo, escritorio/celular/tablet | 46 aprobadas |
| TypeScript, builds demo/integración, Ruff y formato | Aprobados |

La ejecución amplia del navegador detectó dos selectores incorrectos en la prueba
nueva: el editor usa «Título completo», y un mismo mensaje aparece en alerta e
historial. Se corrigieron las comprobaciones, sin cambios funcionales de interfaz,
y se repitieron los ocho casos nuevos junto con las 24 pruebas 2N y el piloto auténtico; todos aprobaron.
Los ensayos finales también comprobaron el prefijo independiente de borradores,
para conservar intacta la lectura de IA histórica.

Capturas del recorrido con documentos y productos explícitamente sintéticos:

| Vista | Escritorio | Celular |
| --- | --- | --- |
| Evidencias aprobadas y citas | [Ver](../frontend/artifacts/evidencias-2o-desktop.png) | [Ver](../frontend/artifacts/evidencias-2o-mobile.png) |
| Comparación y respaldo por campo | [Ver](../frontend/artifacts/propuesta-2o-desktop.png) | [Ver](../frontend/artifacts/propuesta-2o-mobile.png) |
| Historial tras guardar y recargar | [Ver](../frontend/artifacts/historial-2o-desktop.png) | [Ver](../frontend/artifacts/historial-2o-mobile.png) |

Comandos desde la raíz:

```bash
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run build:integration
npm --prefix frontend test
```

Para revisar localmente, `python3 integration/run.py up`, con el usuario sintético
del README. La URL HTTPS local funciona en la máquina que ejecuta el entorno;
no es un enlace público. Al cerrar, retirar sólo los contenedores y datos de este
proyecto. Al terminar la validación se retiraron los cuatro contenedores, el
volumen y la pasarela HTTPS local; no se conserva la base descartable.

## Pendientes de Canales

1. Adaptar la cobertura histórica ML/TN al Ecomm ID API, conservando fuente, fecha,
   evidencia y decisiones; no confirmar publicaciones por SKU/EAN.
2. Integrar lectura y preparación por canal en la pestaña existente, con categoría,
   contenido y requisitos propios, y vigencia de la información.
3. Separar siempre candidato, preparado internamente y publicación confirmada.
   Publicar/sincronizar y acceso productivo requieren una autorización posterior.
4. Probar revisión individual y luego lotes con previsualización, versiones,
   límites, resultados y trazabilidad. No se implementa ejecución masiva en 2O.

No se modifican clientes Ecomm-App/ML/TN, OAuth, credenciales, modelos productivos
existentes, Render o datos reales. Sin push, PR, merge, PR #87 ni despliegue.

## Archivos modificados

- `backend/app/api/routes/documental_workspace.py`
- `backend/app/api/routes/ecomm_api_workspace.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/services/documental/__init__.py`
- `backend/app/services/documental/contracts.py`
- `backend/app/services/documental/fields.py`
- `backend/app/services/documental/generation_contract.py`
- `backend/app/services/documental/local_documents.py`
- `backend/app/services/documental/migration.py`
- `backend/app/services/documental/proposals.py`
- `backend/app/services/documental/research.py`
- `backend/app/services/documental/storage.py`
- `backend/integration_sandbox/bootstrap.py`
- `backend/integration_sandbox/document_routes.py`
- `backend/integration_sandbox/documental_workspace_checks.py`
- `backend/integration_sandbox/generation_contract.py`
- `backend/integration_sandbox/local_documents.py`
- `backend/integration_sandbox/policy.py`
- `backend/integration_sandbox/proposal_routes.py`
- `backend/integration_sandbox/proposals.py`
- `backend/integration_sandbox/research/documents.py`
- `backend/integration_sandbox/research/routes.py`
- `backend/integration_sandbox/research/service.py`
- `frontend/integration-tests/documental-connected.spec.ts`
- `frontend/integration-tests/legacy-documental.ts`
- `frontend/integration-tests/research.spec.ts`
- `frontend/integration-tests/zproposals.spec.ts`
- `frontend/integration-tests/zzdocuments.spec.ts`
- `frontend/integration-tests/zzzassisted.spec.ts`
- `frontend/integration-tests/zzzzpilot.spec.ts`
- `frontend/src/integration/DocumentImport.tsx`
- `frontend/src/integration/GenerationReadiness.tsx`
- `frontend/src/integration/ResearchPanel.tsx`
- `frontend/src/integration/documental-paths.ts`
- `frontend/src/integration/isolation.ts`
- `frontend/src/integration/proposal-adapter.ts`
- `frontend/src/integration/research-adapter.ts`
- `integration/DOCUMENTAL-2O.md`
- `integration/run.py`

Además, las seis capturas nuevas 2O. Las evidencias históricas regeneradas por
las regresiones se restauran al finalizar y no forman parte del cambio.
