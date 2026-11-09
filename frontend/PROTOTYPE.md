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
