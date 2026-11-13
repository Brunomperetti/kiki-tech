# Etapa 2F — Propuestas comerciales documentadas, exclusivamente de prueba

La etapa 2G incorpora [archivos locales autorizados y procedencia revisada](DOCUMENTS.md),
reutilizando estas propuestas y guardado, sin habilitar IA ni proveedores reales.

Base verificada antes de modificar: rama `feature/kiki-tech-2-dashboard`, HEAD
`075664c46f0f3bf4b55b3afcb69e4b845052d3a1`, árbol limpio.

## Arquitectura y reutilización

El mismo dashboard conserva su editor de 18 campos, Evidencias e Historial.
La pestaña IA incorpora una propuesta **determinista y sintética**, con comparación
por campo, respaldo documental, edición limitada, aceptación/rechazo individual,
revisión persistida y guardado explícito como borrador.

Se reutilizan:

- `EcommApiProductWorkspace.get/save`: único almacenamiento comercial, validaciones,
  normalización, completitud, historial y `expected_version` existentes.
- `CommercialBackofficeFields`, DTO y adaptador del editor 2D. No hay otro editor
  ni un segundo modelo de ficha. La vista de propuesta es material de comparación.
- `KikiAiEditorialDraft`: mismo registro de propuestas existente, discriminado por
  `model=deterministic-synthetic-evidence-v1` y `product_key=ECOMM_API:{id}`.
- `EcommAiEditor._serialize`: DTO existente de propuestas, extendido por el harness.
  No se llama ni reemplaza `suggest`, no hay reserva de intentos/gasto ni OpenAI.
- `Research`: expediente por Ecomm ID, comprobación de evidencia vigente y mutex
  transaccional 2E, además de sesiones y CSRF existentes.

El adaptador `integration_sandbox.proposals` prepara entradas documentadas para
una integración futura del servicio IA. No altera servicios, modelos o routers
en `backend/app`. La API IA productiva continúa bloqueada en el harness.

## Hechos autorizados y generación

El servidor selecciona únicamente hechos `APPROVED` sin bloqueos actuales, ligados
a la variante exacta, documento/huella/versión e identidad actuales. Las referencias
de identidad de Ecomm-App o del fixture **no equivalen a hechos aprobados**.

Cada propuesta conserva los hechos usados completos (sin duplicar su historial):
Ecomm ID, tipo/campo comercial, valor/unidad, presentación, documento/procedencia,
cita/ubicación, fecha, aprobación, revisor, versión y huellas. Cada campo propuesto
enumera sus evidencias. Se registra versión y campos base de la ficha, identidad,
fecha/autor de generación, frases permitidas y decisiones posteriores.

Reglas de esta demostración:

- Nombre y presentación documentados y aprobados permiten título, título corto y
  título SEO. El ID o SKU nunca prueban cantidades ni contenido de un pack.
- Ingredientes, alérgenos, energía, proteínas, peso y declaración comercial sólo
  aparecen si cuentan con evidencia aprobada vigente. Faltantes y contradicciones
  bloquean esa afirmación, sin rellenar huecos con suposiciones.
- Descripciones, detalles y atributos usan frases completas de esos hechos. Las
  descripciones necesitan también nombre y presentación aprobados.
- Marca y fabricante sólo se proponen si tienen hechos aprobados propios; los
  valores actuales no seleccionados se conservan. Se exige clasificación aprobada
  para categoría/subcategoría; esta última requiere categoría.
- No se proponen URLs, archivos, derechos de uso, EAN, notas ni palabras clave.
  Multimedia y fuentes registradas se mantienen exactamente como estaban.
- Si el contenido respaldado supera un límite del editor, se omite el campo y se
  explica el vacío. No se truncan cantidades o advertencias para que entren.

La edición de propuesta permite **quitar o reordenar frases completas respaldadas**
(y segmentos de títulos). No permite agregar texto libre con afirmaciones nuevas,
negar una declaración o alterar valores/unidades. Atributos/clasificaciones deben
conservar los valores respaldados. La validación se ejecuta en el servidor, tanto
al revisar como al aplicar; editar el DOM o enviar otro JSON no la evita. El editor
manual 2D conserva sus capacidades anteriores y no se presenta como validado por
esta generación.

## Contratos exclusivos del entorno aislado

| Método y ruta | Contrato |
| --- | --- |
| GET `/api/test-proposals/{ecomm_id}` | Última propuesta sintética, o `available:false`; hechos autorizados actuales |
| POST `/api/test-proposals/{ecomm_id}/generate` | `{expected_version}`; genera sin modificar ficha |
| POST `/api/test-proposals/{ecomm_id}/{draft_id}/review` | `{expected_revision, decisions:{campo:{decision:ACCEPTED\|REJECTED,value}}}`; persiste revisión, sin aplicar |
| POST `/api/ecomm-app/workspace/{ecomm_id}` | **Mismo DTO existente** `{expected_version,status,fields}`; aplicación identificada por headers `X-Kiki-Proposal-Id` y `X-Kiki-Proposal-Revision` |

GET exige sesión y POST exige sesión y CSRF. Sólo se permiten los seis IDs del
fixture; no hay rutas masivas ni parámetros de proveedor/red. El gateway reenvía
exclusivamente los dos headers adicionales de propuesta, además de los anteriores.

El wrapper POST sólo existe en `bootstrap` del harness y precede a la ruta original.
Sin ambos headers adicionales, delega el guardado manual al mismo servicio de 2D.
Con headers, exige que la propuesta esté revisada y vigente y que el cuerpo sea
exactamente la ficha base más los campos aceptados. Cualquier otro cambio, campo
no propuesto, revisión desactualizada o estado distinto de DRAFT se rechaza con 409.
Nunca se acepta automáticamente una propuesta ni se sube el estado editorial.

Antes de aplicar, la UI confirma explícitamente el reemplazo de valores seleccionados,
incluso si la ficha estaba aprobada. Rechazados y campos sin decidir se conservan.
Los cambios locales no revisados bloquean la aplicación; el editor con cambios
pendientes bloquea la revisión de propuestas. La selección sobrevive al cambiar
de pestaña y una respuesta 409 no dispara reintentos ni descarta la edición local.
Si otra sesión cambió la ficha, cerrar y reabrir el mismo panel recupera su nueva
versión; después se genera y revisa otra propuesta. No hay rebase ni aplicación
automática sobre los cambios del otro operador.

## Persistencia, versiones y atomicidad

No se agrega esquema ni migración en 2F. Las propuestas usan la tabla existente
`kiki_ai_editorial_drafts` **sólo en PostgreSQL descartable**. Sus campos tradicionales
guardan título/descripción, hechos, huella y estado; `history` guarda la propuesta
extendida, base y decisiones. El historial editorial de la ficha sigue siendo el
del servicio existente. Los expedientes/documentos siguen en `kiki_research_test`.

La huella vincula identidad con todo el conjunto autorizado: ID, versión y contenido
de cada hecho. Cualquier cambio de ficha (aunque sea otro campo), revocación,
revisión documental, contradicción o modificación del conjunto aprobado invalida
la propuesta. Una lectura comprueba vigencia y registra `STALE`; aplicar siempre
comprueba otra vez, aunque el navegador aún no haya recibido esa invalidación.
Una propuesta STALE exige generación y revisión nuevas. No se reutiliza una aplicada.

Al aplicar, el mutex de investigación impide modificar/revocar evidencias durante
la validación y el commit. El registro comercial existente se bloquea también con
`FOR UPDATE`; la versión sigue siendo la precondición del servicio original.
El evento APPLIED y el guardado comercial se confirman juntos. Una aplicación
fallida hace rollback, sin dejar un falso APPLIED. Dos operadores sobre la misma
base obtienen un guardado y un 409. Si los valores ya eran idénticos, el servicio
puede realizar su no-op habitual sin crear una versión comercial innecesaria.

Se afinó la huella de identidad 2E para que copiar exactamente marca/fabricante/
presentación canónicos al editor no invalide hechos sólo por cambiar la etiqueta
de procedencia o pasar de presentación vacía a la misma presentación canónica.
Cambios reales de valores, EAN, SKU, presentación incompatible o identidad siguen
invalidando; las procedencias visibles se actualizan sin elevar su verificación.

## Casos sintéticos

- Completo: `alm-tecnica` y `alm-clasificacion`, revisados hecho por hecho, producen
  hasta 13 campos respaldados. Los otros cinco del editor quedan conservados.
- Ingredientes no aprobados: se omite la afirmación en descripciones/atributos;
  editar a «Sin gluten» u «Orgánico» se rechaza por falta de respaldo.
- Dos tablas nutricionales discrepantes: energía no es utilizable hasta resolver
  el conflicto. La propuesta anterior queda desactualizada.
- Ecomm IDs 900001 y 900002 comparten SKU pero tienen presentaciones independientes.
  El documento 1 kg no permite reutilizar el título ni ingredientes de 250 g.
- La prueba PostgreSQL de pack cambia temporalmente **sólo el fixture de prueba**
  de 900002 a `Pack x2 de 250 g`, con un documento explícito propio, y restaura la
  captura al terminar. No se deduce la composición desde el SKU ni se modifica el
  catálogo inicial del prototipo. El documento queda incompatible con 1 kg normal.
- Revocar un hecho, actualizar el documento o guardar en otra sesión después de
  revisar bloquea la aplicación, sin sobrescribir fichas ni marcar falsamente APPLIED.

## Ejecución y aislamiento

Con los prerrequisitos locales 2B–2E:

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
python3 integration/run.py up
```

Abrir `https://127.0.0.1:8443/` en la máquina del entorno y usar la cuenta sintética
existente. No ejecutar simultáneamente comandos sobre el mismo proyecto Docker.
Ctrl+C elimina el entorno y sus datos tmpfs. El modo demo habitual sigue usando
`npm test` / `npm run build` en `frontend`, sin backend.

Se mantienen el preflight de base antes del engine/DDL, variables saneadas,
contenedores sin red, sin puertos TCP ni credenciales productivas y el bloqueo
de proveedores/DNS/procesos. Navegador y gateway usan rutas fijas, sin rewrites,
fallback, descargas de documentos ni recursos multimedia externos.

## Riesgos pendientes

- Plantillas deterministas y documentos redactados manualmente: no OCR, fuentes oficiales,
  investigación web, IA real ni certificación legal/nutricional.
- La edición de propuestas es deliberadamente limitada; admitir redacción libre
  requiere otro mecanismo de validación semántica, revisión y autorización.
- La extensión de propuestas en JSON/history y el serializador interno reutilizado
  necesitan un contrato estable, migración revisada y pruebas de compatibilidad
  antes de habilitar el proveedor real. No es una nueva persistencia comercial.
- Mutex global y cuenta/sesiones sintéticas son adecuados para esta validación,
  no para carga masiva ni permisos/autoría multiusuario productivos.
- La invalidación es conservadora sobre el conjunto aprobado completo, incluso
  si el hecho cambiado no estaba entre los campos seleccionados.
- PostgreSQL tmpfs persiste durante la sesión de prueba, no después de apagarla.
  El editor manual conserva campos anteriores que esta propuesta no certifica.

## Archivos de la etapa

- Backend de pruebas: `backend/integration_sandbox/proposals.py`,
  `proposal_routes.py`, `proposal_checks.py`, `bootstrap.py`, `policy.py`,
  `research/documents.py` y `research/service.py`.
- Interfaz de integración: `frontend/src/integration/ProposalPanel.tsx`,
  `proposal-adapter.ts`, `PersistentWorkspace.tsx`, `workspace-adapter.ts`,
  `catalog-adapter.ts`, `isolation.ts` y `research.css`.
- Playwright: `frontend/integration-tests/zproposals.spec.ts`.
- Harness: `integration/gateway.py` y `integration/run.py`.
- Documentación: este archivo, `integration/README.md`, `integration/RESEARCH.md`
  y `frontend/PROTOTYPE.md`.
- Capturas: `frontend/artifacts/propuesta-{comparacion,guardada,bloqueada}-{desktop,mobile}.png`.

## Validación ejecutada

| Comprobación | Resultado |
| --- | --- |
| `python3 integration/run.py test` | 61 aprobadas: 19 de base/aislamiento, 7 del editor, 13 documentales, 15 de propuestas y 7 del gateway |
| `python3 integration/run.py legacy-test` | 484 aprobadas; 2 advertencias previas de plugins de pytest |
| `python3 integration/run.py browser-test` | 70 aprobadas: 58 anteriores y 12 de propuestas, escritorio y celular |
| Playwright focalizado de propuestas tras ajustes finales | 12 aprobadas; incluye ancho del historial en celular, aviso de revisión pendiente y ausencia de errores tras aplicar |
| Playwright demo (`npm test` en frontend) | 46 aprobadas |
| TypeScript, build demo y build de integración | Aprobados; advertencia habitual de tamaño del bundle demo |
| Ruff, formato Python y espacios de Git | Aprobados |

Los tests de propuestas usan PostgreSQL real descartable, no mocks de persistencia.
Cubren generación completa y parcial, fuentes contradictorias, edición sin respaldo,
selección/rechazo por campo, recursos preservados, versiones/historial y recarga,
revocación/revisión documental, cambio de ficha o presentación, hechos asignados a
otro Ecomm ID, pack frente a unidad, conservación de fichas aprobadas y dos sesiones
aplicando la misma base (200 y 409). También comprueban que no se reservan intentos
del proveedor real y que autenticación, CSRF y rutas bloqueadas siguen activos.

Capturas: [comparación en escritorio](../frontend/artifacts/propuesta-comparacion-desktop.png),
[comparación en celular](../frontend/artifacts/propuesta-comparacion-mobile.png),
[guardado e historial](../frontend/artifacts/propuesta-guardada-desktop.png) y
[afirmación sin respaldo bloqueada](../frontend/artifacts/propuesta-bloqueada-mobile.png).

Sin proveedores reales, OpenAI, producción, Render, PR #87, push, PR, merge ni despliegue.
