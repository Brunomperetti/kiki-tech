# Validación del cierre funcional

Entorno: PostgreSQL descartable, FastAPI existente, parser/recolector sin red, pasarela TLS de loopback y Chromium. Sin llamadas a proveedores, credenciales productivas ni datos productivos. Los builds usan los entrypoints existentes, conservando separación demo/conectado.

## Comprobaciones finales

Resultados finales: **706 comprobaciones backend y 226 pruebas de navegador aprobadas en las ejecuciones finales por escenario**. Hay una incidencia intermitente del lector documentada abajo; el comando conjunto de navegador terminó con código 1 por ese piloto, aunque sus 138 casos generales aprobaron. El piloto independiente final aprobó 2/2. Resumen legible por máquina: `frontend/artifacts/functional-validation.json`.

| Comprobación | Resultado |
|---|---|
| Backend, PostgreSQL y seguridad | 222 tests aprobados; incluye 12 nuevos de calidad/vistas, persistencia, revisión mensual, CAS, autenticación y límites |
| Regresiones heredadas | 484 aprobadas, 2 advertencias de dependencias |
| Playwright presentación conectada | 12 aprobadas: cinco vistas, calidad/intersecciones/URL, exportación, historial, rechazo de falsa confirmación TN, recorrido documental completo y PDF Hileret; escritorio/celular |
| Playwright general conectado | 138 aprobadas; 36 omitidas por corresponder a otros escenarios, ejecutados separadamente |
| Playwright Canales | 8 aprobadas; unidades, packs, EAN compartidos, fechas, revocaciones y navegación |
| Playwright lotes | 8 aprobadas; selección filtrada, propuestas, reapertura y revisión por campo |
| Playwright autónomo | 8 aprobadas; 5.000 variantes, cancelación, navegador cerrado y recuperación |
| Piloto auténtico aislado | 2 aprobadas (escritorio/celular), manteniendo los límites originales del lector; ver incidencia anterior |
| Playwright demo | 50 aprobadas; incluye edición del formulario compartido, navegación dentro del borrador, filtros y ausencia de solicitudes API/externas |
| TypeScript y builds | Aprobados; build demo e integración |
| Ruff | Aprobado sobre backend/app, integration_sandbox y scripts modificados |
| Pasarela y recuperación real de procesos | 8 tests de gateway incluidos en 222, más scripts de muerte/reinicio del worker y del backend aprobados |

Las regresiones generales, Canales, lotes y ejecutor quedaron aprobadas en las ejecuciones finales de cada escenario. La suite general completó 138 casos aprobados; posteriormente el comando conjunto recibió un 409 del lector en una importación Hileret de escritorio, mientras el caso móvil del mismo original aprobó. El piloto se repitió por separado: escritorio y celular aprobaron (2/2), con idénticos límites. La primera ejecución conjunta no se presenta como exitosa. El rechazo bajo carga sigue documentado como limitación del lector: un documento válido puede requerir una nueva incorporación manual con recursos disponibles, nunca un bypass ni un reintento automático. No contar tests omitidos de otros escenarios como aprobados.

Incidencias corregidas durante la preparación: las pruebas antiguas deben abrir el grupo plegable de indicadores antes de pulsarlos; la prueba nueva identificaba equivocadamente la harina sintética de 1 kg como un pack; el recorrido documental necesitaba esperar la respuesta de extracción antes de consultar hechos. Se conservaron las exigencias sobre cantidad de hechos, versiones, citas, aprobaciones y guardado. Una ejecución simultánea de las suites demo y conectada agotó el timeout de 30 segundos en dos casos móviles de investigación; al repetir en serie, ambos casos aprobaron en 10,4 y 13,7 segundos con el mismo límite de 30 segundos. No se añadieron reintentos para ocultar fallos ni se relajaron límites de seguridad.

## Rendimiento de prueba

Medición de servicios Python/SQL de la ejecución backend final: excluye TLS, navegador y autenticación HTTP; no es un SLA de producción. En la medición nueva de canales se varió el maestro de 50 a 5.000 variantes manteniendo cinco filas ML. No se hizo prueba de carga concurrente ni se midió producción:

| Recorrido | Variantes | Consultas SQL | Tiempo / memoria |
|---|---:|---:|---|
| Vista completa de canal | 50 | 4 | 0,009 s |
| Vista completa de canal | 5.000 | 4 | 0,281 s |
| Cobertura por variante existente | 5.000 | 6 | 1,587 s |
| Cola editorial con nuevos filtros | 5.000 | 8 | 3,525 s; pico Python 28,89 MiB; respuesta paginada 148.797 bytes |
| Servicio de alta del análisis incremental 2R | 5.000 | 58 | 1,239 s; 7,06 MiB |
| Análisis incremental backend 2R | 5.000 | 1.057 en todos sus bloques | 12,481 s; 8,35 MiB |

Se preservó igualdad de resumen, huellas y versiones frente al análisis síncrono anterior. Las vistas no consultan por fila. El catálogo y las capturas siguen siendo JSON existentes: recorrerlos cuesta O(n); se pagina la salida, se usan proyecciones SQL y no se transfieren originales de documentos o historiales completos para la tabla. No se promete escalabilidad ilimitada ni latencia productiva con estas mediciones. El historial global reutiliza `list_saved` original, que aún carga las ediciones completas antes de paginar; no se midió aquí con miles de historiales extensos y requiere optimización de proyección para ese volumen.

## Capturas de esta entrega

| Recorrido | Escritorio | Celular |
|---|---|---|
| Dashboard conectado | [Captura](../frontend/artifacts/functional-catalog-dashboard-desktop.png) | [Captura](../frontend/artifacts/functional-catalog-dashboard-mobile.png) |
| Registros ML sin vincular | [Captura](../frontend/artifacts/functional-catalog-ml-desktop.png) | [Captura](../frontend/artifacts/functional-catalog-ml-mobile.png) |
| Calidad y filtros | [Captura](../frontend/artifacts/functional-catalog-quality-desktop.png) | [Captura](../frontend/artifacts/functional-catalog-quality-mobile.png) |
| Ficha conectada | [Captura](../frontend/artifacts/functional-catalog-editor-desktop.png) | [Captura](../frontend/artifacts/functional-catalog-editor-mobile.png) |
| Comparación y revisión de propuesta | [Captura](../frontend/artifacts/functional-flow-propuesta-desktop.png) | [Captura](../frontend/artifacts/functional-flow-propuesta-mobile.png) |
| Lote persistente completado | [Captura](../frontend/artifacts/functional-flow-lote-desktop.png) | [Captura](../frontend/artifacts/functional-flow-lote-mobile.png) |
| PDF Hileret y evidencias | [Captura](../frontend/artifacts/functional-flow-hileret-desktop.png) | [Captura](../frontend/artifacts/functional-flow-hileret-mobile.png) |
| Hileret auténtico: antes | [Captura](../frontend/artifacts/functional-authentic-antes-desktop.png) | [Captura](../frontend/artifacts/functional-authentic-antes-mobile.png) |
| Hileret auténtico: guardado de pruebas | [Captura](../frontend/artifacts/functional-authentic-guardado-desktop.png) | [Captura](../frontend/artifacts/functional-authentic-guardado-mobile.png) |
| Demo visual estático | [Captura](../frontend/artifacts/functional-demo-dashboard-desktop.png) | [Captura](../frontend/artifacts/functional-demo-dashboard-mobile.png) |
| Editor compartido en memoria | [Captura](../frontend/artifacts/functional-demo-editor-desktop.png) | [Captura](../frontend/artifacts/functional-demo-editor-mobile.png) |

El escenario conectado parte sin aprobaciones; las decisiones del recorrido Playwright llevan una justificación de prueba automatizada. Hileret conserva su identidad real pendiente y no hereda esas decisiones. Las capturas del demo no prueban persistencia PostgreSQL.

## Reproducción

En el entorno Linux aislado ya preparado:

```bash
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test --presentation
python3 integration/run.py browser-test
python3 integration/run.py browser-test --channels
python3 integration/run.py browser-test --batches
python3 integration/run.py browser-test --autonomous
cd frontend
npm test
npm run typecheck
npm run build
npm run build:integration
```

Cada ejecución del arnés retira sus contenedores y PostgreSQL temporal. El build necesita las dependencias/imágenes ya preparadas o las descargas de desarrollo autorizadas; el runtime de las pruebas no tiene acceso a proveedores. La validación TLS del navegador confía sólo en la clave efímera local, sin desactivar TLS globalmente.

Archivos modificados: `FUNCTIONAL-FILES.md`. Alcance y pendientes: [cierre funcional](FUNCTIONAL-CLOSE.md), [paridad](FUNCTIONAL-PARITY.md), [opción online](ONLINE-PRESENTATION-PLAN.md).
