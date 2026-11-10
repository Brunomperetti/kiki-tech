# Integración local aislada: etapas 2B–2G

La etapa actual agrega [documentos locales autorizados y revisión de procedencia 2G](DOCUMENTS.md),
con lector separado sin red y preservación del original. El catálogo continúa sintético;
no hay conexión productiva ni investigación externa.

La etapa 2F agregó [propuestas comerciales documentadas](PROPOSALS.md), con
generación determinista, revisión individual y guardado mediante el editor existente.

La etapa 2E agregó [investigación documental sintética y trazabilidad](RESEARCH.md),
en un esquema de pruebas independiente. Ver también su
[plan de migración separado, no ejecutado](RESEARCH-MIGRATION-PLAN.md).

La etapa 2D agregó el editor comercial existente y persistencia interna
individual. Ver [Editor persistente 2D](EDITOR.md) para los contratos habilitados,
concurrencia, seguridad y validación. El resto de este documento conserva la
infraestructura de aislamiento y el registro histórico de 2B/2C.

La etapa 2C conecta **sólo la lectura** del dashboard al backend sintético. Ver
[Catálogo conectado y validación 2C](CATALOG.md) para la arquitectura actual,
sesiones, pruebas y capturas. La infraestructura de aislamiento de 2B se conserva.
El punto de entrada productivo `app.main:app`,
los modelos, servicios, reglas comerciales, rutas antiguas, `render.yaml` y el
aislamiento del frontend de demostración no se modifican.

## Arquitectura

```text
cliente local HTTPS (127.0.0.1:8443)
    -> pasarela Python: origen/rutas fijos, sin proxy configurable ni redirects
    -> socket Unix api.sock
    -> FastAPI existente + bootstrap exclusivo del harness
       [contenedor sin red, raíz de sólo lectura, UID 1000, sin capacidades]
    -> socket Unix PostgreSQL (único destino permitido)
    -> PostgreSQL descartable con datos inventados
       [contenedor sin red, sin puertos TCP, datos en tmpfs]
```

Ambos contenedores usan `network_mode: none`. La única interfaz es loopback y no
hay ruta de salida, incluso para conexiones nativas de libpq que no pasan por
los hooks de Python. No se monta el socket de Docker, `.env`, credenciales ni el
repositorio completo en el backend. El contexto de build tiene una lista explícita
de archivos permitidos y excluye `.env` y cachés. Sólo durante **build/pull** se
utiliza red para descargar imágenes y dependencias; nunca para llamar proveedores.

El bootstrap, antes de importar cualquier módulo `app`:

1. Exige `KIKI_INTEGRATION_MODE=local-synthetic` y una URL PostgreSQL literal por
   socket. Rechaza TCP, SQLite, otros nombres, parámetros extra y variables de
   proveedores/aplicación heredadas, incluso en minúsculas. No muestra valores.
2. Instala un hook irreversible que bloquea DNS, conexiones TCP/UDP, otros sockets
   Unix, shell y procesos hijos. Es una defensa adicional, no un sandbox para
   ejecutar código arbitrario.
3. Comprueba en el servidor `current_database`, usuario, conexión sin dirección
   TCP, comentario `KIKI_LOCAL_SYNTHETIC_2B` y rol sin superusuario, creación de
   bases/roles ni replicación. Son consultas, sin DDL. Si falla, no importa `app`
   ni crea tablas.
4. Construye `Settings(_env_file=None)` con valores sintéticos explícitos, claves
   de proveedores vacías e IA apagada. Vincula esa configuración **sólo en este
   proceso** antes de importar el engine actual.
5. Reutiliza `create_app` y su lifespan. Crea los modelos existentes únicamente en
   PostgreSQL ya verificado y agrega seis variantes inventadas, identificadas por
   Ecomm ID. Dos comparten SKU deliberadamente. No inventa EAN ni publicaciones.

La URL sintética fija no es una credencial de producción; no se deben insertar
credenciales reales en este entorno. Las sesiones de prueba usan el servicio
existente, Argon2, cookie HttpOnly/Secure/SameSite y CSRF reales. La clave de cifrado
local se genera en memoria. Los datos PostgreSQL y sesiones desaparecen al quitar
los contenedores; el volumen compartido sólo contiene el socket y se elimina.

## Inicio y apagado

Requisitos: Linux o WSL2, usuario UID 1000, Python 3.11+, Node.js 22 y dependencias
del frontend instaladas con `npm ci`, Docker local en
`/var/run/docker.sock`, Docker Compose v2 con soporte de build secrets y bundle de
CA en `/etc/ssl/certs/ca-certificates.crt`. No se admite Docker remoto ni cambiar
permisos para eludir estas comprobaciones. En Docker Desktop usar la integración
WSL2 desde una terminal Linux. El gateway es de desarrollo local, no un servidor
público.

Desde la raíz del repositorio:

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py up
```

`up` inicia los contenedores y mantiene la pasarela en primer plano:
`https://127.0.0.1:8443/` (dashboard) y `/health`. Ctrl+C los detiene y elimina sus volúmenes. Otra
terminal permite `python3 integration/run.py status` y
`python3 integration/run.py down`. No ejecutar simultáneamente `up` y `test`:
usan el mismo proyecto local y las pruebas lo limpian al terminar. Ante errores
también se limpian los contenedores; los logs muestran sólo este entorno sintético.

El certificado autofirmado local se renueva al arrancar y vence a los dos días.
No deshabilitar validación TLS. Para herramientas, confiar explícitamente en él:

```sh
curl --cacert .integration-runtime/api/tls-cert.pem https://127.0.0.1:8443/health
```

Para un navegador, importar ese certificado en un perfil de pruebas local si se
necesita. No instalarlo como certificado de producción ni compartir la clave.
`localhost` de Windows no apunta al entorno Codex; estas instrucciones sirven
al ejecutar el repositorio en la propia máquina/WSL2, sin publicar puertos cloud.

Autenticación de demostración de backend:

- usuario: `operador-prueba`
- contraseña sintética pública: `solo-datos-sinteticos`
- `POST /api/auth/login` con JSON `{"username":"operador-prueba","password":"solo-datos-sinteticos"}`.
- reutilizar cookie en `GET /api/auth/me`; para `POST /api/auth/logout` enviar además
  `X-CSRF-Token` devuelto por login.

El dashboard de integración agrega un formulario para estas credenciales de prueba,
sin bypass de autenticación. Las pruebas hacen el ciclo completo sobre HTTPS
con certificado validado. El demo conserva su funcionamiento anterior sin backend.

## Superficie habilitada y límites

Únicamente `/health`, login/me/logout, `GET /api/ecomm-app/stage/catalog` y,
desde 2D, GET/POST individual de workspace para los seis IDs sintéticos.
El último sirve exclusivamente el fixture interno, consumido desde el dashboard
en etapa 2C. El resto responde 403 antes de
ejecutar endpoints, incluidas actualización manual/programada, OAuth/callback,
sincronización, CSV, IA, edición fuera de esos IDs y documentación API. Las rutas originales siguen
en el backend habitual, sin cambios.

Las respuestas API mantienen la CSP de 2B. El HTML del dashboard admite sólo
scripts y estilos locales y conexiones al mismo gateway; bloquea imágenes,
videos, frames, fuentes y recursos externos. La pasarela sólo acepta los hosts loopback
previstos, rechaza orígenes ajenos y URLs absolutas y nunca lee rewrites de Render.
No hay scheduler ni workers de negocio. El healthcheck Docker sólo ejecuta un
`SELECT 1` local; no es una tarea de sincronización.

La configuración de producción/desarrollo sigue siendo la existente. El harness
es opt-in y sólo acepta su modo específico: no tiene un modo “production”,
fallback a SQLite o selector de proveedor real. `run.py` usa un entorno mínimo,
un archivo Compose explícito y `--env-file /dev/null`; no hereda variables de
aplicación, `COMPOSE_FILE`, `DOCKER_HOST`, contexto/TLS ni otros `.env`. El cliente
Docker conserva su configuración de autenticación de registro y la confianza CA
durante build, sin copiarla a la imagen o al runtime. En cloud, la caché de buildx
usa `.integration-runtime/buildx` para no escribir en el home restringido.

## Validación

```sh
python3 integration/run.py test
python3 integration/run.py legacy-test
# Frontend demo, por separado y sin modificar sus guardas:
cd frontend
npm run typecheck
npm run build
npm test
```

`test` comprueba configuración y destinos rechazados antes de importar `app`,
identidad/privilegios del PostgreSQL real descartable, `.env` contaminado ignorado,
credenciales vacías, sesiones/CSRF, identidad por variante y ausencia de filas de
negocio generadas. Intenta DNS/HTTP y sockets para proveedores y Render; los hooks
los rechazan antes de salir. Un destino de documentación `192.0.2.1` comprueba
además el bloqueo de conexiones nativas de libpq por falta de red. No se prueban
hosts productivos con una conexión real.

El runner inspecciona los contenedores locales y exige red `none`, ausencia de
puertos, raíz de sólo lectura y `no-new-privileges` antes de la suite. La pasarela
se prueba por HTTPS real sobre loopback, con certificado validado, autenticación
y rechazos de upstream/origen/host. `legacy-test` ejecuta los tests existentes
dentro del contenedor sin red y con configuración sintética. Ninguna suite se
ejecuta contra Render o una base productiva.

## Riesgos pendientes

- Este arnés no sustituye pruebas de concurrencia, migración, rendimiento o
  recuperación de PostgreSQL productivo, ni acredita que una integración real
  esté conectada. No toca sus tokens o datos.
- El administrador local de Docker puede alterar contenedores y políticas: este
  límite supone un host de desarrollo confiable, no ejecución multiusuario hostil.
- Se requiere soporte de sockets Unix y UID 1000; no se promete ejecución nativa
  en PowerShell sin WSL2.
- El gateway es mínimo, sólo para pruebas locales, con límites de cuerpo y sin
  exposición pública. El modo demo continúa con `connect-src 'none'`; el modo
  integración tiene un build y entrada explícitos con su propia CSP y guardas.
- Fixtures, credenciales de prueba y certificados temporales nunca deben usarse
  con datos reales. El certificado/clave permanecen ignorados localmente después
  de apagar; la base no persiste. Para borrarlos, con todo detenido quitar
  únicamente `.integration-runtime/api`.
- Las dependencias Python conservan las versiones actuales del proyecto; este
  cambio no es una actualización de dependencias ni una revisión de seguridad
  de todo el backend.

Sin push, PR, merge, despliegue, cambios en Render o integración de PR #87.

## Resultado histórico de la validación 2B del 9 de noviembre de 2026

Base comprobada: `feature/kiki-tech-2-dashboard`,
`377efe78894c1fc8ba999818e28b959282845890`, árbol inicialmente limpio.
Las referencias remotas de la rama (`c2722cc`) y main (`f843ce1`) se comprobaron
antes y después: no cambiaron. No se hizo fetch con merge, push ni despliegue.

| Comprobación ejecutada | Resultado |
| --- | --- |
| Build de imagen y descarga explícita de PostgreSQL de pruebas | Correcto |
| Pruebas de configuración, aislamiento y backend sobre PostgreSQL descartable | 17/17 |
| Pasarela loopback HTTPS, sesión/CSRF y rechazo de origen/upstream | 5/5 |
| Suite histórica del backend, dentro del contenedor sin red | 484/484 |
| Playwright del demo, escritorio/celular y comprobaciones de tablet | 46/46 |
| TypeScript y build del frontend | Correctos |
| Ruff y comprobación de formato de archivos nuevos | Correctos |
| Diferencia en `backend/app`, `frontend`, `render.yaml` y `.github` respecto de la base | Ninguna |

Las pruebas negativas rechazaron URLs PostgreSQL productivas y TCP, SQLite,
parámetros adicionales, modos ajenos, variables de credenciales y `.env`
contaminado. Las conexiones DNS/HTTP de proveedores y Render se bloquearon antes
de salir. El rol PostgreSQL rechazó una contraseña incorrecta. La inspección real
de los contenedores y `/sys/class/net` acreditó red `none`, sólo loopback y sin ruta
externa; también falló la conexión nativa a una dirección de documentación.

La suite histórica informó dos advertencias: deprecación de AnyIO/Starlette y
reescritura de asserts de un plugin importado antes de pytest. El build del demo
mantiene el aviso previo de tamaño de bundle. Ninguna es un fallo de prueba.
Los contenedores y el volumen de socket se eliminaron al terminar; no quedó una
base de integración activa.
