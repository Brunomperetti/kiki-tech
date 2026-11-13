# Etapa 2C — Catálogo de FastAPI en el dashboard

Documento histórico de lectura. La etapa 2D habilita además el editor comercial
individual existente dentro del panel: [contratos, pruebas y límites actuales](EDITOR.md).

Base: `6cf0a2f1de90b52a7a250765ae661daea5b1f6df`, rama
`feature/kiki-tech-2-dashboard`. Antes de implementar se comprobó HEAD, árbol
limpio, ascendencia desde `f843ce135a87515a8ef8f7ced40e57dc911c0480` y referencias
remotas esperadas (rama `c2722cc`, main `f843ce1`). No se integró PR #87.

## Contratos reutilizados, sin backend paralelo

| Contrato existente | Uso en esta etapa |
| --- | --- |
| `GET /api/auth/me` | Comprobar sesión sintética y recuperar CSRF |
| `POST /api/auth/login` | Crear sesión en PostgreSQL descartable |
| `POST /api/auth/logout` | Revocar sesión con CSRF |
| `GET /api/ecomm-app/stage/catalog?q=&page=&limit=` | Leer captura sintética persistida, búsqueda y paginación |

Se reutilizan el engine, modelos, autenticación, servicio de catálogo y lifespan
de FastAPI mediante el bootstrap de 2B. Ningún archivo de `backend/app` cambia.
No se necesitan contratos de cola/editor para mostrar los datos del catálogo;
siguen bloqueados para esta integración hasta su autorización específica.

## Dos modos explícitos, un espacio de trabajo

- **Demo:** `npm run dev` o build habitual. Entrada `index.html`/`src/main.tsx`,
  fixtures del frontend y aislamiento original intactos. No necesita backend.
- **Integración:** `npm run build:integration`, entrada `integration.html` y marca
  de compilación explícita. Se sirve únicamente por la pasarela local de 2B.
  `PrototypeDashboard` selecciona el renderer de consulta; reutiliza el espacio
  visual del dashboard y mantiene toda operación en tabla/panel lateral.

El build de integración usa la API programática de Vite con `configFile:false` y
`envFile:false`. No lee el config demo, `.env`, rewrites ni variables `VITE_*`:
si aparecen, se rechaza el build. No existe un selector configurable de upstream.
La marca de build, un único meta de entorno y el origen exacto
`https://127.0.0.1:8443` son obligatorios. La configuración incompleta/ambigua
muestra “Integración bloqueada”, sin autenticación ni fallback al demo.

```text
navegador -> HTTPS 127.0.0.1:8443
             |-- / y /assets/*.js|css: build local explícito de integración
             |-- lista cerrada de contratos API
                    -> Unix api.sock -> FastAPI existente (network:none)
                    -> Unix PostgreSQL -> PostgreSQL descartable (network:none)
```

No hay proxy Vite ni servidor nuevo de negocio. La pasarela sirve archivos locales
con nombres limitados, verifica los paths resueltos y nunca sirve el repo, el demo,
`.env` o `render.yaml`. Las rutas antiguas y servicios productivos se conservan.

## Adaptador y experiencia

`frontend/src/integration/catalog-adapter.ts` valida el contrato antes de dibujar
filas: modo, fuente, banderas de sólo lectura, eco de búsqueda/página/tamaño,
totales coherentes con calidad y número esperado de filas, Ecomm IDs únicos,
tipos de texto/stock y fechas. Nunca usa SKU como identificador ni fusiona packs.
Conserva nombre original, presentación, stock capturado, fecha y origen.

No transforma la respuesta en un producto ficticio del demo. Marca, imágenes,
precios y cualquier campo no entregado no se inventan. Un stock `0` se conserva;
un valor ausente se representa como “Sin datos disponibles”. Los totales globales
provienen del backend; el recuento mostrado corresponde sólo a la página.

La búsqueda y los parámetros `q`, `page`, `limit`, `product`, `tab` viven en la URL.
Se conservan al cerrar la ficha, usar atrás/adelante o volver a autenticarse.
Los parámetros inválidos, duplicados o desconocidos detienen la consulta. El panel
permite cerrar con Escape y contiene el foco de teclado. En celular la tabla usa
tarjetas legibles con las mismas filas/identidades.

ML/TN, cobertura, revisión y preparación dicen “Sin datos disponibles”. Las
acciones de editar, IA, aprobar y preparar están deshabilitadas; historial y
configuración de negocio no se presentan como funciones conectadas. Las pestañas
de consulta distinguen datos de captura de evidencia comercial no integrada.

Las respuestas 403/409/500, errores de red/contrato y redirecciones limpian los
datos visibles y ofrecen reintentar, sin conservar cifras ficticias o una copia
alternativa. El 401 exige nuevo login y mantiene los filtros. No hay auto-retry de
login ni almacenamiento de credenciales/CSRF en localStorage.

## Inicio

Desde la raíz, Linux/WSL2, UID 1000 y Docker local (prerrequisitos de 2B):

Requiere Node.js 22 y las dependencias del frontend instaladas (`npm ci` desde
`frontend` en Linux/WSL2). No agrega dependencias ni modifica el lockfile.

```sh
python3 integration/run.py build
python3 integration/run.py up
```

Abrir `https://127.0.0.1:8443/` en la **máquina que ejecuta el entorno**.
El certificado efímero se encuentra en `.integration-runtime/api/tls-cert.pem`.
Confiar explícitamente en ese certificado sólo en un perfil local de pruebas;
no desactivar TLS ni compartir su clave. El gateway también conserva `/health`.
El hostname alternativo `localhost` no habilita el frontend: se exige el origen
canónico anterior para evitar ambigüedad.

Usuario sintético público: `operador-prueba`; contraseña: `solo-datos-sinteticos`.
Nunca ingresar credenciales reales. El backend mantiene Argon2, cookies Secure,
HttpOnly y SameSite, y CSRF. Solamente se crean/actualizan sesiones en la base
descartable; no se escriben productos desde el navegador.

Ctrl+C apaga y elimina contenedores/volumen de socket. Los datos PostgreSQL están
en tmpfs y no sobreviven. No ejecutar `up`, `test`, `legacy-test` o `browser-test`
simultáneamente: comparten el mismo proyecto sintético. No publicar el puerto,
crear túneles o desplegar. Windows `localhost` no representa el entorno cloud.

## Pruebas y evidencia

```sh
python3 integration/run.py test          # PostgreSQL real descartable + gateway
python3 integration/run.py legacy-test   # suite histórica en contenedor sin red
python3 integration/run.py browser-test  # Chromium -> gateway -> FastAPI -> PG
cd frontend
npm run typecheck
npm run build
npm test                                # regresión del demo
```

El runner inspecciona `network_mode:none`, raíz de sólo lectura, sin privilegios
ni puertos Docker, antes de las suites. Se mantienen los bloqueos de DNS, sockets,
procesos, credenciales heredadas y validación de identidad de base anteriores al
import del engine. No se amplía la lista de rutas comerciales de 2B.

En el navegador se permiten sólo los contratos enumerados en el origen canónico,
con credenciales same-origin y `redirect:error`. XHR, WebSocket, EventSource,
beacons y apertura de ventanas quedan bloqueados; enlaces ajenos no se abren.
CSP impide imágenes, videos, frames y recursos externos. Las pruebas interceptan
y abortan cualquier intento fuera del gateway, y fallan si se detecta alguno.

Playwright confía en la clave pública exacta del certificado local por SPKI;
su cliente HTTP Node usa `NODE_EXTRA_CA_CERTS` con ese certificado. No se usa
`ignoreHTTPSErrors:true` ni una desactivación global de TLS. Los tests de errores
usan respuestas sintéticas interceptadas en el gateway; no llaman proveedores.

Se prueban catálogo completo, búsqueda sin resultados, identidad por Ecomm ID
con SKU duplicado, paginación, filtros, sesión vencida, datos opcionales, stock
cero, 401/403/409/500, cortes de conexión, contratos ambiguos, configuración,
redirecciones y bloqueo de escrituras/proveedores. Los casos de seis variantes,
búsqueda, paginación y login recorren el backend/PG reales de prueba.

**Diferencia importante:** el servicio de captura vigente rechaza una captura
ausente/incompleta con 409. No se cambió esa regla. La búsqueda sin coincidencias
y el 409 se comprueban en el backend real de prueba. Un catálogo completo de
total cero se valida con un doble local explícito del contrato, no se presenta
como nueva capacidad de captura de Ecomm-App.

Capturas reproducibles del recorrido conectado (sin interceptar el catálogo):

- `frontend/artifacts/integracion-desktop.png`
- `frontend/artifacts/integracion-mobile.png`
- `frontend/artifacts/integracion-ficha-desktop.png`
- `frontend/artifacts/integracion-ficha-mobile.png`

## Pendientes

No se habilitan edición persistente, IA, investigación, publicación, sincronización,
importaciones, generación de captura ni lectura de datos reales. Esos servicios
no se acreditan como operativos desde este dashboard. La integración usa seis
fixtures del backend, distintos de los fixtures del demo frontend.

Antes de habilitar actualización real, habrá que resolver consistencia de captura
entre páginas: el contrato actual no ofrece un identificador de snapshot para
fijar toda una navegación. También permanecen las validaciones de concurrencia,
permisos por operador y trazabilidad de futuras escrituras identificadas en 2A.
El gateway sigue siendo una herramienta local de desarrollo sobre un host Docker
confiable, no un servidor público. Las restricciones de Linux/UID y certificado
autofirmado son las de 2B. No se tocaron proveedores, credenciales, Render o main.

No push, PR, merge, despliegue ni integración de PR #87.

## Archivos de esta etapa

- Frontend: `src/integration/{IntegrationCatalog.tsx,catalog-adapter.ts,isolation.ts,main.tsx,integration.css}`,
  `src/prototype/Dashboard.tsx` (selección explícita de renderer), `integration.html`,
  `scripts/build-integration.mjs`, `package.json`, `playwright.integration.config.ts`,
  `integration-tests/catalog.spec.ts`, `PROTOTYPE.md` y las cuatro capturas mencionadas.
- Harness: `integration/{gateway.py,run.py,browser_tests.py,test_gateway.py,README.md,CATALOG.md}`.
- Pruebas backend: `backend/integration_sandbox/verify.py`.
- `.gitignore`: artefactos de build y resultados de tests locales.

No cambian modelos, reglas comerciales, integraciones oficiales, `backend/app`,
entrada/isolation/CSP del demo, `render.yaml`, workflows o lockfiles.

## Resultado de la validación 2C

| Comprobación | Resultado |
| --- | --- |
| Backend de integración con PostgreSQL real descartable | 19/19 |
| Gateway, TLS, sesiones y superficie estática/API | 6/6 |
| Suite histórica del backend en contenedor sin red | 484/484 |
| Playwright integración, escritorio y celular | 34/34 |
| Playwright del demo, escritorio/celular y controles de tablet | 46/46 |
| TypeScript, build demo y build integración | Correctos |
| Ruff y formato Python del harness | Correctos |

Se ejecutó el build de contenedor con las pruebas nuevas y ambas variantes de
frontend. La suite del backend conserva dos avisos de AnyIO/plugin de pytest;
el build habitual conserva el aviso previo de tamaño de bundle. No hubo fallos
en las ejecuciones finales. La prueba de integración deja cero intentos fuera
del gateway autorizado y los contenedores/volumen de socket se eliminan al terminar.
Los filtros rechazados, ausencia de datos y fallos HTTP nunca activaron el demo.
