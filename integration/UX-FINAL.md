# Ajuste final de usabilidad del dashboard

Base: `2abbb72f5c013a57cdb07b2621b29ee6050760ff`, rama `feature/kiki-tech-2-dashboard`. Se verificaron rama, HEAD y árbol limpio antes de editar. Alcance: frontend y sus pruebas; sin cambios en backend comercial, integraciones, esquema, presupuesto de IA ni configuración de despliegue.

## Jerarquía y operaciones conservadas

- Cinco vistas comerciales siempre visibles, seguidas inmediatamente por **Listos para Mercado Libre** y **Listos para Tiendanube**. Preparación interna y publicación efectiva siguen siendo conceptos diferentes.
- Indicadores secundarios dentro de **Más indicadores comerciales**. **Calidad del catálogo** tiene su propio desplegable compacto: conserva los controles de EAN, SKU, duplicados, descripciones, imágenes, SEO, categorías y demás filtros existentes.
- La tabla conserva búsqueda, selección, paginación, filtros combinados y URL recuperable. El acceso principal al catálogo completo reemplaza el antiguo indicador duplicado y limpia la búsqueda anterior; pulsar una tarjeta de preparación conserva el contexto de búsqueda.
- Las cinco pestañas permanecen en el mismo panel. **IA** tiene énfasis visual y la acción **Investigar y completar ficha con IA**, que abre el recorrido existente de Evidencias; no ejecuta investigación web real. La ficha conserva un acceso secundario a IA.
- Los estados de disponibilidad explican que investigación web y OpenAI reales están bloqueados. Se reutilizan documentos locales autorizados, fuentes sintéticas y el generador determinista existente, revisión por campo y editor versionado. No se modificaron los contratos ni el presupuesto de OpenAI.
- El Centro de operaciones sigue plegado por defecto, con preparación de propuestas para varias variantes y resultados. Las acciones de fila priorizan conflictos de identidad/canal, evidencias vencidas, propuestas pendientes y campos incompletos según estados existentes.

## Cálculos reutilizados y límites

En la demo se reutilizan `coverage` e `isReady` sin cambiar sus reglas, con datos sintéticos explícitos.

En el dashboard conectado se reutiliza `GET /api/ecomm-app/workspace/queue` con las intersecciones existentes `ready_for_channels+ml_unconfirmed` y `ready_for_channels+tn_unconfirmed`. Son dos consultas adicionales al cargar/actualizar la tabla, independientes de cuántas filas se muestran; no hay solicitudes por fila ni servicios nuevos. Reutilizan el cálculo global de la cola, cuyo costo crece con el catálogo; no se promete tiempo constante. El adaptador conserva las validaciones del contrato y del entorno sintético. Ante error o metadatos incompatibles se muestra **—**, sin inventar ceros.

Estos conteos significan **ficha interna completa sin confirmación en ese canal**. No certifican requisitos externos específicos, identidad ni vigencia; la interfaz lo advierte y exige verificaciones posteriores. No publica, sincroniza ni ejecuta proveedores. Un CSV Tiendanube tampoco se convierte en evidencia de publicación actual.

Se conservaron los fixtures y las reglas de los expedientes Hileret y MAMA; las decisiones de los recorridos siguen identificadas como pruebas automatizadas. La prueba de los conteos revoca explícitamente su vínculo sintético y recupera los campos previos mediante el editor existente. Si no había ficha iniciada, queda un borrador vacío de prueba, sin inventar una operación de borrado. Todo PostgreSQL se descarta al finalizar el escenario; ninguna decisión se transfiere a una identidad auténtica.

## Validación

Las suites se ejecutaron en serie para evitar competencia entre navegadores; FastAPI, lector y recolector permanecieron sin red, con PostgreSQL descartable y pasarela TLS de loopback.

| Comprobación | Resultado observado |
|---|---|
| Playwright demo completo | **56 aprobadas**: navegación, rutas anteriores, edición, URL, filtros, operaciones y ausencia de conexiones externas/API |
| UX demo final | **6 aprobadas**, incluidas en las 56 anteriores, repetidas para verificar la captura móvil completa y la jerarquía final |
| Presentación conectada final | **14 aprobadas**, escritorio/celular: cinco vistas, calidad, preparación calculada por canal, acción recomendada, disponibilidad IA, revisión, persistencia e historial |
| Regresión conectada general | **136 aprobadas, 2 fallidas inicialmente**, 38 omitidas por pertenecer a otros escenarios. Las dos fallidas detectaron que el acceso principal al catálogo conservaba la búsqueda; se corrigió el frontend y se repitió la suite específica completa, indicada abajo |
| Dashboard conectado después de corregir la búsqueda | **24 aprobadas**, incluidos ambos casos de guardado, búsqueda, recarga y regreso al catálogo completo; también identidad, navegación y controles de error |
| Canales final | **8 aprobadas**: unidades/packs, EAN compartido, conflictos, capturas, decisiones y revocaciones |
| Lotes | **8 aprobadas**: selección, previsualización, propuestas, revisión por campo y recuperación |
| Ejecutor con 5.000 variantes sintéticas | **8 aprobadas**, escritorio/celular: tabla, cinco pestañas, selección exacta, cancelación, navegador cerrado y recuperación |
| TypeScript y builds | Aprobados: `tsc -b`, build demo y build conectado |
| Control del alcance | Sin cambios en backend, scripts de integración, migraciones, entrypoint productivo ni Render. Escaneo de los archivos de texto modificados sin patrones de claves privadas/tokens |

Los fallos iniciales de la demo expusieron reglas de grilla antiguas que agrandaban las tarjetas y filtros que no se limpiaban al volver al catálogo. Se corrigió el frontend conservando los límites de posición de la tabla y las aserciones de negocio. En Canales, cuatro casos iniciales buscaban métricas plegadas: los recorridos ahora abren el desplegable antes de comprobar los mismos valores, incluida la revocación. Su repetición final aprobó 8/8. No se cuentan los escenarios omitidos como aprobados.

**Incidencia PDF reproducida:** después de la suite específica del dashboard, las dos importaciones del original Hileret recibieron **409**: «Lector aislado no disponible o límite de tiempo/memoria excedido. No se importó el documento». Esa ejecución conjunta terminó con error aunque los 24 casos del dashboard aprobaron. No se presenta como exitosa, no se atribuye con certeza a una causa concreta de recursos y no se modificaron los límites, el perfil por hash ni el procesamiento del backend.

**Diagnóstico separado final: 2/2 pilotos auténticos aprobados**, escritorio/celular, con los mismos límites y el arnés existente. Se comprobaron original, citas, revisiones explícitamente automatizadas de prueba, propuesta limitada, guardado y separación del pack. Fue una repetición diagnóstica manual por separado, sin introducir reintentos automáticos. El éxito aislado no elimina la incidencia intermitente anterior ni convierte la ejecución conjunta fallida en una exitosa.

Se conserva la incidencia intermitente previa del lector de PDF bajo carga, documentada en [FUNCTIONAL-VALIDATION.md](FUNCTIONAL-VALIDATION.md). No se relajaron sus límites ni se modificó el lector como parte de este ajuste visual.

Comandos de las suites principales (entorno Linux aislado ya preparado):

```bash
cd frontend
npm test
npm test -- ux-final.spec.ts
npm run typecheck
npm run build
npm run build:integration
cd ..
python integration/run.py browser-test --presentation
python integration/run.py browser-test
python integration/run.py browser-test --channels
python integration/run.py browser-test --batches
python integration/run.py browser-test --autonomous
```

La repetición específica utilizó el ciclo existente `runtime_directory` → `compose up` → `verify_containers` → pasarela local → `npm run test:integration -- dashboard-connected.spec.ts` → `compose down --volumes`, sin añadir un servicio o arnés permanente al repositorio. El piloto utiliza el comando existente `npm run test:pilot` dentro del mismo aislamiento. Retirar contenedores y volúmenes destruye los datos de prueba.

## Capturas actualizadas

| Vista | Escritorio | Celular |
|---|---|---|
| Dashboard demo | [Captura](../frontend/artifacts/ux-final-dashboard-desktop.png) | [Captura](../frontend/artifacts/ux-final-dashboard-mobile.png) |
| IA demo | [Captura](../frontend/artifacts/ux-final-ai-desktop.png) | [Captura](../frontend/artifacts/ux-final-ai-mobile.png) |
| Dashboard conectado de pruebas | [Captura](../frontend/artifacts/ux-final-connected-dashboard-desktop.png) | [Captura](../frontend/artifacts/ux-final-connected-dashboard-mobile.png) |
| IA conectada de pruebas | [Captura](../frontend/artifacts/ux-final-connected-ai-desktop.png) | [Captura](../frontend/artifacts/ux-final-connected-ai-mobile.png) |

## Archivos

Frontend: `IntegrationCatalog.tsx`, `CommercialViews.tsx`, `catalog-adapter.ts`, `product-actions.ts`, `PersistentWorkspace.tsx`, `BatchPanel.tsx`, `commercial-views.css`, `Dashboard.tsx`, `OperationalPanel.tsx`, `operations-model.ts`.

Pruebas: `tests/ux-final.spec.ts`, `channel-coverage.spec.ts`, `simple-dashboard.spec.ts`, `dashboard.spec.ts`; `integration-tests/functional-catalog.spec.ts`, `dashboard-connected.spec.ts`, `channels-connected.spec.ts`, `autonomous-connected.spec.ts`, `zzzassisted.spec.ts`, `zzzzpilot.spec.ts`, `zzzzzmama.spec.ts`, `zzzzzzhileret.spec.ts`; `pilot-tests/hileret-authentic.spec.ts`. Los recorridos existentes ahora abren IA para iniciar la investigación y los indicadores secundarios mediante su desplegable; se conservan sus comprobaciones comerciales, documentales y de seguridad.

Entrega complementaria: este informe y las ocho capturas `ux-final-*`. No se publicaron cambios ni se actualizaron servicios externos.
