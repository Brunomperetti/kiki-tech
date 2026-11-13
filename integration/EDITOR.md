# Etapa 2D — Editor comercial persistente de pruebas

La etapa 2E agrega investigación documental en Evidencias sin aplicar hechos a
los campos de este editor: [arquitectura y límites de investigación](RESEARCH.md).

Base verificada: rama `feature/kiki-tech-2-dashboard`, HEAD
`c463f87366726564da9d8e026bb3967016864132`, árbol limpio antes de modificar.

## Reutilización

El panel lateral reutiliza **`CommercialBackofficeFields`**, los tipos existentes
`EcommEditableFields`/`EcommApiProductEdit`, la evaluación de completitud existente
y el servicio **`EcommApiProductWorkspace`**. No se agregó otro formulario de
campos comerciales, servicio de negocio, modelo, tabla o almacenamiento alternativo.

Se habilitaron únicamente, para los seis IDs sintéticos del harness:

- `GET /api/ecomm-app/workspace/{ecomm_id}`: campos completos, fuente original,
  estado, versión, completitud y todos los eventos del historial.
- `POST /api/ecomm-app/workspace/{ecomm_id}`: cuerpo existente
  `{ expected_version, status, fields }`, sesión y `X-CSRF-Token`.

Las rutas de catálogo y autenticación de 2C se conservan. Las demás operaciones
siguen denegadas: IA, actualización, sincronización, publicaciones, revisión
periódica, decisiones de canales y procesos por lote. No se habilitó la ruta
general de workspace, sólo los seis IDs de fixtures mediante una lista cerrada.

## Campos y experiencia

Se conservan los 18 campos del contrato, sin descartar contenido en guardados:

| Contenido | Campos |
| --- | --- |
| Identidad comercial | `brand`, `manufacturer`, `title`, `short_title`, `presentation`, `proposed_gtin` |
| Textos | `short_description`, `description`, `details`, `note` |
| Organización y SEO | `category`, `subcategory`, `seo_title`, `seo_description`, `seo_keywords` |
| Listas | `attributes`, `media` (IMAGE/VIDEO, URL, alt y fuente), `sources` (tipo, nombre, URL, nota y verificación) |

`PersistentWorkspace` controla carga, edición pendiente, guardado y recuperación
dentro del panel existente. `workspace-adapter.ts` valida la respuesta y manda el
contrato existente; no reproduce las reglas de negocio del backend. Un cambio
incompatible del esquema se rechaza en lugar de perder campos silenciosamente.

Los datos originales Ecomm-App son de sólo lectura y están separados de los
campos comerciales de KIKI. El Ecomm ID identifica la variante; un SKU repetido
no fusiona fichas. Se muestra la versión, estado editorial y cambios sin guardar.
La tabla recupera el estado editorial de las fichas efectivamente consultadas;
los indicadores globales de revisión/preparación permanecen sin fuente integrada.

“Guardar borrador” persiste como DRAFT. “Guardar estado editorial” conserva las
transiciones existentes y pide confirmación para estados distintos de borrador.
Las validaciones del backend, incluido EAN, URLs y completitud para
READY_FOR_CHANNELS, siguen siendo la autoridad. Un estado interno no publica nada.

La confirmación de guardado aparece después de la respuesta del POST, con la
versión devuelta. Cerrar/reabrir, recargar o iniciar otra sesión vuelve a leer
PostgreSQL. El historial muestra estado anterior/nuevo y valores antes/después.
Las pestañas conservan la edición pendiente; cerrar, cambiar variante, filtrar,
salir de sesión o abandonar el navegador protegen cambios no guardados. Nunca
se navega al editor antiguo.

Al vencer la sesión, los campos locales permanecen visibles y se permite
reautenticar sin desmontar la ficha. No hay guardado automático tras recuperar
sesión: el operador debe volver a guardar explícitamente.

## Concurrencia e identidad

Se mantiene `expected_version`, el bloqueo `SELECT FOR UPDATE`, la restricción
única por Ecomm ID y el historial del servicio existente. Antes del POST el
frontend consulta de nuevo versión e identidad. Si hay cambios incompatibles,
se bloquea el guardado y se conserva la edición local.

Si otra sesión avanzó la versión, o el POST responde 409 por una carrera, el
panel recupera la versión nueva y muestra **base / edición local / versión nueva**,
incluidas listas y estado. No sobrescribe ni reintenta automáticamente. El usuario
puede descartar su edición explícitamente o conservarla para revisar sobre la
nueva base; esta segunda decisión tampoco escribe. El guardado posterior es
otra acción explícita y vuelve a comprobar versión e identidad.

La suite PostgreSQL sincroniza dos sesiones justo antes de sus SELECT FOR UPDATE.
Para creación y actualización, espera una respuesta 200 y una 409, una única fila,
una única versión nueva, contenido del ganador e historial sin el intento perdedor.
La prueba de navegador retiene ambos POST hasta que las dos sesiones terminan la
consulta previa, para comprobar un conflicto real del backend y su comparación UI.

## Aislamiento

Se conserva el bootstrap de 2B antes del import del engine, identidad PostgreSQL
validada, contenedores `network_mode:none`, sin puertos Docker, sin credenciales
de negocio, sin scheduler y sin llamadas a proveedores. El gateway comparte la
misma lista de rutas permitidas que el backend sintético; el navegador tiene su
propia guarda equivalente. No se toca `backend/app`, modelos ni integraciones.

El componente comercial recibe `allowExternalResources={false}` en integración:
no crea imágenes, videos ni enlaces externos de las URLs registradas. Su valor
por defecto mantiene el comportamiento de las rutas anteriores. Las URLs se
guardan como texto; CSP y las guardas de red continúan bloqueando recursos externos.
Se agregó una etiqueta accesible al selector de tipo multimedia.

El límite del gateway para un guardado individual es 1 MiB, compatible con todos
los campos/listas del contrato y UTF-8. Autenticación conserva su límite de 16 KiB.
Se prueba un payload válido mayor de 16 KiB, CSRF ausente y cuerpos excesivos.
Esto no amplía límites comerciales ni habilita importaciones o guardados por lote.

## Inicio y pruebas

Prerrequisitos de 2B/2C: Linux/WSL2, UID 1000, Python, Node 22, dependencias del
frontend instaladas y Docker local. No se agregaron dependencias ni se cambió el lockfile.

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
python3 integration/run.py up
```

Abrir `https://127.0.0.1:8443/` en la máquina que ejecuta el entorno, confiando
explícitamente en `.integration-runtime/api/tls-cert.pem`. Credenciales públicas
sintéticas: `operador-prueba` / `solo-datos-sinteticos`. Nunca ingresar credenciales
reales. `Ctrl+C` detiene y elimina la base descartable. No ejecutar los comandos
que usan el proyecto Docker simultáneamente.

`test` ejecuta las comprobaciones de aislamiento de 2B/2C, `editor_checks.py` y
pruebas HTTPS del gateway. `legacy-test` ejecuta la suite previa dentro del
contenedor sin red. `browser-test` recorre dashboard, editor y errores en
escritorio/celular. TypeScript, build demo y Playwright demo se ejecutan además
desde `frontend`, sin alterar sus guardas.

## Límites que se conservan

- Persistente significa **PostgreSQL durante la vida del entorno descartable**:
  se recupera entre aperturas, recargas y sesiones. Al apagar/quitar contenedores
  tmpfs desaparece, como requiere el aislamiento. No es una base productiva.
- Las dos sesiones de prueba usan la cuenta sintética existente. El backend
  actual no incorpora aquí usuarios/roles nuevos ni atribución individual de
  operadores dentro del historial; no se presenta esa funcionalidad como resuelta.
- La captura está fija y sus rutas de actualización bloqueadas. Antes de permitir
  captura cambiante real habrá que cerrar la vinculación transaccional con su
  versión de fuente, especialmente en la primera edición; esta etapa no cambia
  el contrato productivo ni inventa un token de versión de captura.
- No se habilitan IA, investigación, descarga de recursos, preparación de canales,
  publicación, sincronización ni aprobaciones por lote. Las categorías son campos
  internos existentes; no se agregó mapeo externo.

No push, PR, merge, Render, variables productivas ni integración de PR #87.

## Capturas

Las capturas se toman sobre el recorrido real de guardado, sin interceptar los
endpoints de ficha. Hay versiones escritorio/celular de cada sección:

- `frontend/artifacts/editor-identidad-{desktop,mobile}.png`
- `frontend/artifacts/editor-descripciones-{desktop,mobile}.png`
- `frontend/artifacts/editor-seo-{desktop,mobile}.png`
- `frontend/artifacts/editor-atributos-{desktop,mobile}.png`
- `frontend/artifacts/editor-multimedia-{desktop,mobile}.png`
- `frontend/artifacts/editor-fuentes-{desktop,mobile}.png`
- `frontend/artifacts/editor-historial-{desktop,mobile}.png`
- `frontend/artifacts/editor-conflicto-{desktop,mobile}.png`

El encabezado/cierre del panel y la barra de guardado permanecen recuperables
durante el desplazamiento. Los selectores multimedia y textareas tienen etiquetas
accesibles estables también al recuperar contenido previamente guardado.

## Archivos de esta etapa

- Formulario reutilizado: `frontend/src/components/CommercialBackofficeFields.tsx`
  (opción para impedir recursos externos y etiquetas accesibles; comportamiento
  predeterminado de las rutas anteriores conservado).
- Integración frontend: `PersistentWorkspace.tsx`, `workspace-adapter.ts`,
  `IntegrationCatalog.tsx`, `catalog-adapter.ts`, `isolation.ts`, `integration.css`
  en `frontend/src/integration/`.
- Pruebas UI: `frontend/integration-tests/{catalog,editor}.spec.ts`.
- Harness: `backend/integration_sandbox/{policy,bootstrap,verify,editor_checks}.py`,
  `integration/{gateway,run,test_gateway}.py`.
- Documentación: `integration/{README,CATALOG,EDITOR}.md`, `frontend/PROTOTYPE.md`
  y las dieciséis capturas anteriores.

No cambian `backend/app`, modelos, integraciones, `render.yaml`, workflows,
credenciales, dependencias, lockfiles ni las guardas del modo demo.

## Resultado de validación

| Comprobación ejecutada | Resultado |
| --- | --- |
| Configuración, PostgreSQL e aislamiento previos | 19/19 |
| Editor PostgreSQL, persistencia, validación, identidad y carreras reales | 7/7 |
| Gateway HTTPS, sesión/CSRF y límites de cuerpo | 7/7 |
| Suite histórica del backend sin red | 484/484 |
| Playwright integración, escritorio y celular | 46/46 |
| Playwright demo, escritorio/celular y controles de tablet | 46/46 |
| TypeScript, build integración y build demo | Correctos |
| Ruff y formato Python | Correctos |

El recorrido completo guardó los 18 campos, un atributo, imagen y video con sus
metadatos y una fuente verificada de prueba. El navegador recuperó los valores
tras cerrar/reabrir y recargar, y comprobó el historial y versiones con GET real.
Las pruebas de sesiones independientes del backend comprobaron la fila y JSON
persistidos directamente con SQLAlchemy. En escritorio se guardó la versión 1
de la ficha completa; el recorrido móvil recuperó ese contenido y guardó una
nueva versión sin perder campos.

En las dos carreras PostgreSQL hubo exactamente una respuesta 200 y una 409,
una sola fila y un único avance de versión; el intento perdedor no agregó un
evento. En el navegador se obtuvieron también 200/409 reales, se conservó la
edición perdedora y sólo se guardó después de comparar y elegir explícitamente.
No se utilizaron dobles para afirmar persistencia ni éxito del conflicto.

Los casos de identidad incompatible de UI usan un doble local para la bandera
de bloqueo; el backend comprueba además el cambio efectivo de SKU sobre el fixture
PostgreSQL y rechaza el guardado sin alterar la ficha. Los tests de URLs/proveedores
continúan bloqueando conexiones antes de salir. Los avisos de AnyIO/plugin de
pytest y tamaño de bundle son los previos; no hubo fallos en las ejecuciones finales.
Los contenedores y volumen de socket se eliminaron al finalizar.
