# KIKI Tech 2.0 · Etapa 1

Rama: `feature/kiki-tech-2-dashboard`. Base: `f843ce135a87515a8ef8f7ced40e57dc911c0480`.

Este frontend es un prototipo aislado, no una versión para producción. Usa ocho variantes ficticias en memoria. No necesita backend, base de datos ni credenciales. Los cambios se pierden al recargar.

## Ver el prototipo

Desde `frontend/`, con Node 20+:

```sh
npm ci
npm run dev
```

Solo se inicia Vite. No iniciar Uvicorn, Docker, tareas programadas ni procesos de integración. La recarga automática por WebSocket está deshabilitada deliberadamente: recargar el navegador después de editar.

## Implementación

- Dashboard con seis indicadores calculados de los fixtures, buscador por SKU/nombre/marca/Ecomm ID, filtros combinables y estados vacíos recuperables.
- Panel lateral con Ficha, Evidencias, IA, Canales e Historial; selección, filtros y pestaña conservados en parámetros de URL. Atrás/adelante y recarga restauran la vista.
- Ecomm ID identifica cada variante. DEMO-1001 y DEMO-1006 comparten SKU y siguen siendo fichas independientes.
- Una coincidencia de SKU nunca suma a publicaciones verificadas. La falta de evidencia tampoco demuestra ausencia de publicación.
- Preparación interna con confirmación y cancelación, sin cambiar la evidencia de canales. IA es texto fijo de muestra, sin ejecución de modelos.
- Diseño para escritorio, tablet y celular; navegación por teclado en pestañas, cierre con Escape, foco contenido y restaurado al cerrar.
- Rutas y componentes anteriores conservados; dashboard anterior en `/dashboard-classic`. Las herramientas heredadas no pueden operar contra sus servicios durante el prototipo. Importaciones muestra un historial vacío sintético. El resto conserva sus estados de indisponibilidad y mensajes de bloqueo. La sesión de demostración es explícita y local; no cambia la autenticación del backend.

## Aislamiento

- CSP en HTML (también en el build estático) y en cabeceras Vite: `connect-src 'none'`, `frame-src 'none'`, `form-action 'none'`; scripts, estilos e imágenes locales. Se retiró el import de Google Fonts heredado.
- Fetch devuelve únicamente el historial vacío de importaciones; el resto de solicitudes y todos los XHR, WebSocket, EventSource y Beacon están bloqueados. Apertura de ventanas y enlaces externos se bloquean en la UI.
- Vite sin proxy ni rewrites, ignora upstreams heredados; `/api/*` y `/health` responden 403. Los tests compilan con `VITE_API_URL=https://production.invalid` para comprobar el aislamiento aun con configuración heredada.
- El runner corta cualquier destino distinto del servidor estático local antes de emitirlo y exige cero solicitudes externas. También prueba el fetch nativo previo al bloqueo JS para comprobar que el CSP impide conexiones.
- No se modificaron backend, integraciones, credenciales, configuración de Render ni PR #87. No se desplegó ni fusionó.

## Validación reproducible

```sh
npm run typecheck
npm run build
npm test
```

Playwright usa Chromium en `/usr/bin/chromium` (disponible en este entorno). Para otro entorno se puede definir `PLAYWRIGHT_CHROMIUM_EXECUTABLE` con la ruta de su Chromium. Las pruebas arrancan exclusivamente un servidor de assets; no hay backend de pruebas.

La suite ejecuta ocho escenarios en escritorio y celular (16 ejecuciones), con comprobación adicional del tamaño tablet: búsqueda, filtros/URL, ficha/pestañas/foco, confirmación/cancelación por ID, aislamiento, navegación de todas las rutas originales, capturas y desbordes responsive. Las capturas se regeneran en `artifacts/`.

El build conserva el aviso de Vite por bundle >500 kB, debido a los componentes anteriores retenidos. No afecta la compilación.

## Evidencia visual

- [Dashboard escritorio](artifacts/dashboard-desktop.png)
- [Dashboard celular](artifacts/dashboard-mobile.png)
- [Ficha escritorio](artifacts/ficha-desktop.png)
- [Ficha celular](artifacts/ficha-mobile.png)

La siguiente etapa requiere revisión del usuario. No conectar datos reales ni publicar este prototipo.
