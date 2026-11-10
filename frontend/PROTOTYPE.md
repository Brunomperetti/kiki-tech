# KIKI Tech 2.0 · Demo y catálogo de integración

La etapa 2E incorpora documentos sintéticos, evidencias por dato y revisión humana
en el mismo panel, preservando la edición 2D: [documentación](../integration/RESEARCH.md).

La etapa 2D incorpora el editor comercial existente en el panel del modo
integración, con guardado individual en PostgreSQL descartable, versiones e
historial: [documentación de la etapa](../integration/EDITOR.md). El modo demo
conserva su aislamiento y persistencia simulada anterior.

La etapa 2C agrega un modo explícito de lectura desde FastAPI/PostgreSQL descartable.
No utiliza las cifras ni productos de este demo como fallback. Ver
[inicio, arquitectura, límites y pruebas](../integration/CATALOG.md).
El build habitual y `npm run dev` conservan el modo demo sin backend. El build
`npm run build:integration` sólo se sirve en el gateway sintético autorizado.

## Etapa 1.3 — Visibilidad por canal (modo demo)

Base comprobada: `730dcbccae63182aee2a03095821b89530317397`, rama `feature/kiki-tech-2-dashboard`, árbol limpio antes de editar.

## Cobertura comercial en una pantalla

El dashboard existente prioriza Ecomm-App, Mercado Libre y Tiendanube. Ocho indicadores permanecen visibles sin abrir herramientas: variantes del catálogo central, publicaciones confirmadas de ML/TN, variantes sin confirmación en ML/TN, variantes que requieren revisión y variantes listas internamente para cada canal.

Los valores se calculan sobre los fixtures. **No se suman variantes y publicaciones.** Una publicación se cuenta una vez por su identificador dentro de su canal; una variante se cuenta una vez por Ecomm ID. Un mismo artículo puede tener varias publicaciones. Las tarjetas de confirmación indican tanto publicaciones como variantes cubiertas; al pulsarlas, la tabla muestra esas variantes.

Ejemplo inicial calculado: ocho variantes de siete productos base; ML tiene cuatro publicaciones únicas de tres variantes, TN tiene dos publicaciones únicas de dos variantes. Hay cinco variantes sin confirmación ML y seis sin confirmación TN; tres requieren revisión, una está lista para ML y otra para TN. Estas cifras son resultados de los fixtures, no constantes del dashboard.

## Fixtures de dietética

Almendras naturales de 250 g y 1 kg, nueces de 500 g, chía de 250 g, harina integral de 1 kg, avena de 500 g, lentejas de 1 kg y garbanzos de 500 g. Las dos presentaciones de almendras comparten SKU pero mantienen Ecomm ID distintos.

La chía tiene dos publicaciones ML distintas y un registro repetido de una de ellas: el contador elimina ese duplicado. La evidencia TN de lentejas es histórica/desactualizada; una variante de almendras tiene información TN desconocida. Esos casos no cuentan como confirmaciones vigentes.

Cada evidencia de muestra declara vigencia (`current`, `stale` o `unknown`) y referencias con identificador, fundamento y fecha. La vigencia es una propiedad explícita del fixture, no una observación de un servicio real ni una promesa de actualización automática.

## Estados independientes

| Estado de canal | Interpretación |
|---|---|
| Publicado con evidencia | Existe al menos una referencia con evidencia y fecha, marcada vigente en la muestra. |
| Vinculación por revisar | Hay un candidato pendiente de comparar por identidad y presentación. No confirma publicación. |
| Sin publicación confirmada | No tenemos evidencia suficiente. Nunca significa que el producto no esté publicado. |
| Listo para publicar | Ficha aprobada, requisitos internos completos y preparación del canal vigente en la muestra. No ejecuta publicación; exige revisar vigencia antes de operar. |
| Información desactualizada / desconocida | No permite establecer el estado actual del canal. La referencia histórica se conserva para revisión. |

La calidad editorial sigue separada de los canales. Editar una ficha invalida su preparación previa, pero conserva la evidencia de publicación. Aceptar o rechazar una vinculación no crea evidencia de publicación. La preparación de un canal no incrementa los contadores de publicaciones.

La tabla muestra producto, presentación, SKU, Ecomm ID, ficha editorial, ambos canales y siguiente paso. En celular los estados de ML y TN aparecen también junto al producto. Las referencias y fechas pueden consultarse en Evidencias y Canales. La leyenda «Cómo interpretar los estados de canal» explica los términos en lenguaje sencillo.

## Filtros y operaciones

Las tarjetas filtran la misma tabla. Los filtros por estado ML y TN se combinan entre sí y con búsqueda, marca, calidad editorial, conflicto y siguiente acción. Los parámetros `mlState` y `tnState` conservan el contexto en URL, recarga y navegación. «Ecomm-App · catálogo central» y «Ver todo el catálogo» recuperan el catálogo completo.

Los contadores siempre describen el catálogo completo, aunque la tabla esté filtrada; la cantidad visible se informa en el pie de la tabla. Las publicaciones confirmadas y sus variantes cubiertas tienen unidades diferenciadas.

Se mantienen las cinco pestañas operativas, borradores, propuestas IA simuladas, revisión de evidencias, preparación por canal, imágenes, familias, duplicados, lotes, actualización, trabajos, diagnóstico e historial, dentro del mismo dashboard. Se conservan las rutas antiguas. No se crea una pantalla paralela.

## Validación y entrega

Desde `frontend/`: `npm run typecheck`, `npm run build`, `npm test`. La suite incluye 46 ejecuciones de Playwright: 23 escenarios en escritorio y celular, con comprobación adicional de tablet. Prueba contadores derivados de los fixtures, eliminación de registros de publicación repetidos, diferencia entre publicaciones y variantes, estados de vigencia, filtros combinados, Ecomm ID, URL/Atrás, edición, candidatos, preparación por canal, todas las operaciones integradas y ausencia de solicitudes externas.

El build conserva el aviso por bundle >500 kB debido a los componentes anteriores retenidos. No se cambiaron backend, integraciones, credenciales, migraciones, Render, aislamiento de red ni PR #87. No se hace push, despliegue ni merge. Todo continúa siendo simulado en memoria y se reinicia al recargar.

| Captura actual | Escritorio | Celular |
|---|---|---|
| Cobertura comercial | [Ver](artifacts/cobertura-desktop.png) | [Ver](artifacts/cobertura-mobile.png) |
| Evidencias | [Ver](artifacts/evidencias-desktop.png) | [Ver](artifacts/evidencias-mobile.png) |
| Canales | [Ver](artifacts/canales-desktop.png) | [Ver](artifacts/canales-mobile.png) |
| Edición | [Ver](artifacts/edicion-desktop.png) | [Ver](artifacts/edicion-mobile.png) |
| IA | [Ver](artifacts/ia-desktop.png) | [Ver](artifacts/ia-mobile.png) |
| Historial | [Ver](artifacts/historial-desktop.png) | [Ver](artifacts/historial-mobile.png) |
| Lotes | [Ver](artifacts/lotes-desktop.png) | [Ver](artifacts/lotes-mobile.png) |

Archivos de etapa 1.3: `data.ts`, `operations-model.ts`, `Dashboard.tsx`, `OperationalPanel.tsx`, `OperationsCenter.tsx`, `channel-dashboard.css`, las cuatro suites `tests/*.spec.ts`, este documento y capturas en `artifacts/`.

Pendiente de revisión antes de publicar o avanzar a la etapa 2.

---

Las secciones siguientes documentan etapas anteriores. Los fixtures, indicadores y cifras de pruebas vigentes son los de etapa 1.3 definidos arriba.

# KIKI Tech 2.0 · Etapa 1.2 — Mi catálogo

Base verificada: `c2722cc3f6c4a32c3aed448bb14b2c7992b0e619`, rama `feature/kiki-tech-2-dashboard`, árbol limpio al comenzar. Se mejora el dashboard existente; no se crea una pantalla paralela.

## Vista cotidiana

- Una entrada principal: **Mi catálogo**. Historial abre los trabajos de esta sesión dentro del dashboard. Configuración abre un modal con preferencias locales de precios y detalles avanzados.
- Cuatro indicadores que filtran en la misma URL: **Necesita atención**, **En preparación**, **Listo para publicar**, **Publicado**. Volver a pulsar el indicador activo quita ese filtro; «Ver todo el catálogo» recupera la tabla completa.
- Búsqueda, marca, filtro editorial y canal disponibles junto a la tabla. Los filtros por conflicto y siguiente acción se conservan bajo «Más filtros y detalles».
- Tabla completa con Ecomm ID inmutable, calidad editorial, estado de ML y TN por separado, y una acción prioritaria por variante. En celular los dos canales también aparecen junto al nombre.
- Operaciones generales bajo «Más acciones del catálogo», después de la tabla. No redirigen a páginas anteriores. «Volver a búsqueda y productos» conserva filtros y da foco al buscador.
- Todos los formularios y recorridos de etapa 1.1 se conservan: edición, imágenes, propuestas IA, evidencias, familias/duplicados, comparación de canales, lotes, actualización, diagnóstico e historial.

## Significado de los indicadores

Se cuentan variantes identificadas por Ecomm ID. Una variante puede aparecer en varios indicadores, porque los canales tienen estados independientes; los números **no se suman** para obtener un total. El total de referencia sigue siendo siete productos base y ocho variantes sintéticas.

| Indicador | Regla |
|---|---|
| Necesita atención | Hay un conflicto de identidad o falta un dato indispensable. |
| En preparación | Sin bloqueo, falta completar/aprobar la ficha o preparar un canal sin publicación verificada. |
| Listo para publicar | Al menos un canal sin publicación verificada tiene preparación interna vigente, ficha aprobada y requisitos completos. Requiere revisar vigencia y evidencia antes de publicar. |
| Publicado | Existe evidencia verificable de muestra para al menos un canal. No depende de que el texto editorial esté aprobado. |

La ficha editorial usa Borrador, Ficha aprobada, Revisión necesaria o Datos incompletos. Cada canal muestra Publicado, Listo para publicar o Por verificar. **Por verificar no significa sin publicar.** Los candidatos aceptados o rechazados nunca se convierten automáticamente en publicaciones verificadas.

Ejemplos de muestra:

- DEMO-1005: ficha aprobada, ML publicado, TN por verificar; siguiente paso: preparar canal.
- DEMO-1008: ficha aprobada, ML publicado, TN listo para publicar; siguiente paso: verificar antes de publicar.
- DEMO-1002: conflicto de identidad y coincidencia candidata; no se cuenta como publicado.
- Cambiar una ficha invalida sus preparaciones previas; si falta una imagen pasa a necesitar atención. La evidencia de publicación existente se conserva independientemente de esa edición.

## Validación de etapa 1.2

Desde `frontend/`: `npm run typecheck`, `npm run build`, `npm test`. La suite contiene 38 ejecuciones (19 escenarios en escritorio y celular), con comprobación adicional de tablet. Conserva las pruebas de etapa 1.1 y suma indicadores, cobertura mixta por canal, invalidez de preparación tras edición, menú simple, configuración e historial sin pérdida de búsqueda.

Se mantiene el mismo aislamiento: solo fixtures en memoria, CSP y transportes bloqueados, servidor de assets sin proxy ni backend. Los tests compilan con un upstream heredado ficticio y bloquean cualquier intento de conexión externa. No se alteran integraciones, credenciales, Render, rutas antiguas ni PR #87. No se hace push ni despliegue.

El build puede conservar el aviso por bundle >500 kB de los componentes antiguos retenidos. Borradores, decisiones y preferencias se reinician al recargar.

| Capturas actualizadas | Escritorio | Celular |
|---|---|---|
| Mi catálogo | [Ver](artifacts/simple-dashboard-desktop.png) | [Ver](artifacts/simple-dashboard-mobile.png) |
| Configuración | [Ver](artifacts/configuracion-desktop.png) | [Ver](artifacts/configuracion-mobile.png) |
| Edición | [Ver](artifacts/edicion-desktop.png) | [Ver](artifacts/edicion-mobile.png) |
| Evidencias | [Ver](artifacts/evidencias-desktop.png) | [Ver](artifacts/evidencias-mobile.png) |
| IA | [Ver](artifacts/ia-desktop.png) | [Ver](artifacts/ia-mobile.png) |
| Canales | [Ver](artifacts/canales-desktop.png) | [Ver](artifacts/canales-mobile.png) |
| Historial | [Ver](artifacts/historial-desktop.png) | [Ver](artifacts/historial-mobile.png) |
| Lotes | [Ver](artifacts/lotes-desktop.png) | [Ver](artifacts/lotes-mobile.png) |

Archivos de etapa 1.2: `src/prototype/Dashboard.tsx`, `operations-model.ts`, `OperationalPanel.tsx`, `SettingsDialog.tsx`, `simple-dashboard.css`, las tres suites `tests/*.spec.ts`, este documento y `artifacts/*.png`.

Pendiente de revisión. No avanzar a la etapa 2 ni publicar sin autorización.

---

La documentación siguiente conserva el detalle de los flujos operativos introducidos en etapa 1.1; el menú, indicadores y cifras de pruebas vigentes son los definidos arriba.

# KIKI Tech 2.0 · Etapa 1.1 — Centro de operaciones

Base verificada: `cff88e1a880567d5d304b88bb566d63583d3c00d`, rama `feature/kiki-tech-2-dashboard`, árbol limpio al comenzar. Este trabajo continúa en esa misma rama.

## Ejecutar y validar

Desde `frontend/`, con Node 20+ y las dependencias instaladas:

```sh
npm ci
npm run dev
npm run typecheck
npm run build
npm test
```

Solo se inicia Vite. No iniciar backend, Docker, bases de datos, integraciones ni trabajos reales. HMR está deshabilitado para impedir WebSockets: recargar manualmente después de editar. Playwright usa Chromium de `/usr/bin/chromium`; se puede indicar otro ejecutable local mediante `PLAYWRIGHT_CHROMIUM_EXECUTABLE`.

## Un catálogo, un espacio de trabajo

El dashboard conserva búsqueda, filtros, ficha, pestaña y herramienta mediante URL. Todos los flujos habituales de la demostración empiezan y terminan aquí. Las herramientas anteriores mantienen sus rutas y componentes, con red bloqueada; el dashboard clásico sigue en `/dashboard-classic`.

Las ocho variantes se agrupan en siete productos base sintéticos. DEMO-1001 y DEMO-1006 son variantes diferentes de una familia y comparten SKU; su identidad siempre es el Ecomm ID. Los indicadores separan variantes, fichas preparadas, publicaciones verificadas por canal y coincidencias candidatas. Los candidatos pendientes se cuentan como relaciones de canal, no se suman a productos ni a publicaciones confirmadas.

El catálogo prioriza conflictos y tareas pendientes. Los filtros combinan búsqueda, marca, estado, canal, conflicto y siguiente acción. Las acciones rápidas abren la pestaña pertinente sin perder el catálogo. El progreso mide preparación interna, no publicación externa.

## Panel lateral operativo

| Pestaña | Recorrido cubierto |
|---|---|
| Ficha | Editar nombre, descripción, características, precio, stock, imagen de muestra, texto alternativo y título SEO. Comparar versión guardada/borrador, revertir o guardar. Se invalidan las preparaciones previas al editar. |
| Evidencias | Consultar captura, fecha, canal, Ecomm ID y presentación. Aceptar/rechazar con fundamento de al menos 12 caracteres y confirmación. Aceptar exige además comprobar explícitamente la identidad. No transforma un candidato en publicación verificada. |
| IA | Generar plantilla simulada, comparar con el original, editar, aceptar con confirmación o descartar. La procedencia y la referencia futura a un manual ficticio se explican como información no verificada. No se consulta un modelo ni un manual real. |
| Canales | Consultar Ecomm-App, ML y TN por separado; ver candidato, evidencia y preparación. Verificar requisitos y confirmar preparación interna de cada canal. Los conflictos bloquean la preparación. |
| Historial | Ver cambios, responsable demo, hora argentina, fundamentos y snapshots. Consultar versiones anteriores sin reemplazar el estado actual. |

Los formularios tienen aviso de cambios sin guardar. Cerrar, cambiar pestaña, navegar con Atrás o abrir otra herramienta exige seguir editando o descartar. La recarga/salida del documento utiliza el aviso nativo del navegador. Los paneles tienen cierre con Escape, foco contenido y navegación por teclado en las pestañas y en el diálogo de descarte.

## Herramientas generales integradas

Cada herramienta utiliza una vista interna del dashboard, con selección por Ecomm ID, revisión previa, confirmación y resultado consultable. No redirige a rutas antiguas.

| Herramienta | Resultado de demostración |
|---|---|
| Actualización de catálogo | Renovar stock con fixture local (+1 unidad por variante elegida), registrar resultado e invalidar preparación anterior. |
| Familias SKU y duplicados | Comparar variantes del mismo SKU/familia; revisar cada identidad y justificar por qué se conservan separadas. Nunca fusionar variantes por SKU. |
| Conciliación de canales | Comparar candidatos y descartar candidatos ML con revisión individual y fundamento. Aceptar identidad se hace en Evidencias, no automáticamente por lote. |
| Evidencias y conflictos | Revisar cada variante seleccionada y resolver la revisión interna con fundamento y confirmación; no confirma publicaciones. |
| Propuestas IA | Generar propuestas locales por lote y abrir cada una para comparar, editar, aprobar o descartar en el panel lateral. |
| Preparación por lotes | Revisar requisitos, omitir conflictos o datos faltantes e informar preparadas/omitidas. No crea publicaciones. |
| Trabajos y resultados | Consultar trabajos completados, responsable, fecha, resultado e IDs afectados; volver a la lista sin perder búsqueda/filtros. |
| Diagnóstico operativo | Analizar identidades, conflictos y requisitos pendientes de la selección; registrar el diagnóstico sin modificar fichas. |

## Aislamiento y límites

- Solo fixtures en memoria. Borradores, versiones, decisiones, trabajos y propuestas se pierden al recargar; no hay persistencia ni datos reales.
- Se conserva el aislamiento de etapa 1: CSP `connect-src 'none'` en HTML y encabezados; transportes JS bloqueados; Vite sin proxy/rewrites y `/api/*`/`/health` devuelven 403. El único mock del cliente heredado devuelve un historial vacío para importaciones.
- No se modificaron backend, clientes de integración, credenciales, migraciones, Render ni PR #87. No hay IA real, escritura externa, despliegue, push, merge ni publicación.
- Los requisitos y fuentes son ejemplos sintéticos. La preparación interna no prueba que la información técnica sea verdadera ni que el producto esté publicado.
- El build conserva el aviso por bundle >500 kB de los componentes anteriores retenidos.

## Pruebas y evidencia

La suite ejecuta 30 pruebas: 15 escenarios en escritorio y celular, incluyendo comprobación adicional de tablet. Cubre compatibilidad de rutas, búsqueda y URL, identidad, prioridad, edición y versiones, advertencias de descarte/Atrás, IA, conflictos, preparación por canal y por lote, todos los flujos generales y resultados, teclado/foco, responsive y bloqueo de conexiones.

Las pruebas arrancan únicamente un servidor de assets local y compilan con un upstream heredado ficticio (`VITE_API_URL=https://production.invalid`). Cortan antes de emitir cualquier solicitud externa y exigen cero destinos externos. La suite de aislamiento también prueba el fetch nativo, anterior al reemplazo JS, para verificar que CSP impide conexiones a API.

Las capturas se regeneran al ejecutar la suite:

| Flujo | Escritorio | Celular |
|---|---|---|
| Dashboard | [Ver](artifacts/dashboard-desktop.png) | [Ver](artifacts/dashboard-mobile.png) |
| Ficha / evidencia | [Ver](artifacts/ficha-desktop.png) | [Ver](artifacts/ficha-mobile.png) |
| Edición y comparación | [Ver](artifacts/edicion-desktop.png) | [Ver](artifacts/edicion-mobile.png) |
| Propuesta IA | [Ver](artifacts/ia-desktop.png) | [Ver](artifacts/ia-mobile.png) |
| Decisión de evidencia | [Ver](artifacts/evidencias-desktop.png) | [Ver](artifacts/evidencias-mobile.png) |
| Preparación por canal | [Ver](artifacts/canales-desktop.png) | [Ver](artifacts/canales-mobile.png) |
| Historial | [Ver](artifacts/historial-desktop.png) | [Ver](artifacts/historial-mobile.png) |
| Preparación por lotes | [Ver](artifacts/lotes-desktop.png) | [Ver](artifacts/lotes-mobile.png) |

## Archivos de etapa 1.1

- `src/prototype/Dashboard.tsx`: coordinación, filtros/URL, prioridades, progreso, guardado del contexto y diálogos de navegación.
- `src/prototype/operations-model.ts`: estado sintético de variantes, snapshots, decisiones, requisitos y trabajos.
- `src/prototype/OperationalPanel.tsx`: formularios y recorridos de las cinco pestañas.
- `src/prototype/OperationsCenter.tsx`: ocho herramientas integradas.
- `src/prototype/operations.css`: legibilidad, formularios y adaptación responsive.
- `tests/dashboard.spec.ts` y `tests/operations.spec.ts`: regresión y recorridos operativos.
- `artifacts/*.png`: capturas de escritorio/celular.
- Este documento: reproducción, alcance y límites.

Pendiente de revisión de etapa 1.1. No avanzar a etapa 2 ni conectar sistemas reales.
