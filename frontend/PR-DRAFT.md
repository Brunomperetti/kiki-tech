# [Draft] KIKI Tech 2.0 · dashboard aislado con catálogo sintético

Base propuesta: `main` en `f843ce135a87515a8ef8f7ced40e57dc911c0480`.
Rama: `feature/kiki-tech-2-dashboard`.

El trabajo diario se concentra en un dashboard responsive y una ficha lateral con cinco pestañas. Los indicadores, búsqueda y filtros usan ocho variantes sintéticas identificadas por Ecomm ID. Dos variantes comparten SKU para demostrar que no se fusionan; una coincidencia de SKU no confirma publicación.

La preparación interna exige confirmación y solo cambia memoria local. Las rutas anteriores conservan sus componentes; el dashboard previo queda en `/dashboard-classic`. Durante esta revisión, sus operaciones de red están bloqueadas por diseño.

El prototipo bloquea conexiones con CSP, transportes JS y un servidor Vite sin proxy/rewrites. No modifica backend, integraciones, credenciales o Render. No toca PR #87. No iniciar backend ni bases de datos para revisarlo.

Validación: TypeScript, build Vite y 16 pruebas Playwright en escritorio/celular, incluyendo tablet, navegación, filtros, URL, confirmación por ID y ausencia de solicitudes externas aun con VITE_API_URL heredado. Evidencia y reproducción: `frontend/PROTOTYPE.md`; capturas en `frontend/artifacts/`.

Pendiente de revisión de Etapa 1. No fusionar ni avanzar a Etapa 2.

Nota de entrega: la API de GitHub respondió `Forbidden` al consultar el repositorio. Este archivo prepara el contenido de una PR en borrador; no representa una PR creada ni una rama publicada.
