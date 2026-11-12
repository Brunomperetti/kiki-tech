# Activación controlada de KIKI Tech 2.0

Base de esta entrega: `3500c4b2369240a8dc7a109c79691d10ee85f48f`, rama `feature/kiki-tech-2-dashboard`. Preparación local del 12/11/2026. **No se ejecutó ninguna operación productiva ni se cambió Render.**

## Resuelto en código

- Un solo servicio/imagen: FastAPI original y el lector existente, ahora compartido en `backend/document_reader`. `backend/Dockerfile` instala `pypdf==7.0.0` en una raíz separada; no incluye PDFs del cliente, tests, `.env` ni secretos. No se crea un servicio de pago ni otra integración.
- El lector corre como UID 10001 dentro de chroot, sin `/app`, `/proc`, directorios de secretos ni entorno productivo. Cada documento tiene un hijo con seccomp nativo, además del audit hook anterior: sin sockets/red, ejecución de procesos, escapes de namespace o escrituras de archivos. CPU 4/5 s, memoria virtual 192 MiB, plazo total 8 s, salida 512 KiB. En producción se limita a un hijo; el arnés conserva sus dos hijos y `network=none`.
- FastAPI usa UID 10000 cuando la plataforma lo permite. Si falta la frontera del lector, **no se procesa dentro del backend**: se bloquean los archivos y continúa la API anterior. `start.py` supervisa ambos procesos y propaga el apagado. El readiness del lector verifica versión, bloqueo nativo y ausencia de backend/proc/credenciales; no basta con que exista un socket.
- El Dockerfile fija `KIKI_AUTO_CREATE_SCHEMA=false`, incluso con `/v2/` desactivada. No se crean tablas al arrancar esa imagen. El arnés prepara su estructura descartable explícitamente, conservando su aislamiento.
- Perfil general sin cambios: 512 KiB, 10 páginas PDF, límites de texto/streams/objetos, archivos activos rechazados. Sólo los bytes Hileret de SHA-256 `bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291` y tamaño 6.232.081 admiten el perfil existente de página 2. El contrato habitual lo reutiliza sin requerir un ID sintético. Otro archivo grande sigue rechazado; importar no aprueba ni vincula identidades.
- `/` conserva el controlador anterior, la sesión y API. `/v2/` conserva las validaciones de identidad y permite IDs API fuera de los fixtures. Build productivo separado, API del mismo origen, cookies Secure/HttpOnly, CSRF, versiones/409 e historial existentes; sin fallback a fixtures. La demo pública conserva sus bloqueos.

## Preflight PostgreSQL: sólo lectura

`backend/app/services/v2_preflight.py` no importa Settings, `.env`, engine del backend, usuarios ni filas comerciales. Exige base, rol, host y puerto esperados **antes** de conectar. Usa una conexión propia con `default_transaction_read_only=on`, `SET TRANSACTION READ ONLY`, timeouts y sin pool. Verifica base/rol efectivos y `transaction_read_only`. Compara tablas, columnas, tipos, nulabilidad, PK, UNIQUE, FK e índices exigidos por el esquema/migraciones existentes; no propone ALTER automáticos. No imprime el DSN, contraseña ni errores crudos de libpq.

Ejemplo **únicamente para un destino descartable previamente autorizado**, desde un contenedor sin egress que comparte el socket del PostgreSQL de pruebas:

```bash
# KIKI_PREFLIGHT_DSN se suministra por el mecanismo privado del operador, nunca en argumentos/logs.
PYTHONPATH=backend python -m app.services.v2_preflight \
  --expected-database kiki_integration --expected-user kiki_integration \
  --expected-host /var/run/postgresql --require core
```

Retornos: `0` grupos requeridos compatibles, `3` diferencias para revisión, `2` conexión/configuración bloqueada. `--require core,documents,batches` exige el esquema completo. Un destino remoto requiere además `--permit-remote-read`, TLS `verify-full` y CA explícita en el DSN; **esto no otorga autorización para consultar producción**. No se asume que la credencial sea de sólo lectura: también se fuerza la transacción en el servidor. La prueba de UPDATE fue rechazada con SQLSTATE `25006`.

La comprobación no certifica triggers, extensiones, políticas/RLS, semántica de datos ni todos los defaults de una base desconocida. No lee la fila de control documental: el readiness autenticado la comprueba además antes de habilitar funciones. Un resultado estructural no sustituye el ensayo con copia y los recorridos funcionales.

## Copia protegida y migraciones

**No se obtuvo ni se consultó una copia productiva.** El resultado local confirma compatibilidad sobre estructura original y datos de prueba. Para validar la base auténtica se necesita una copia autorizada, bajo custodia del cliente/DBA:

1. Resguardo consistente y privado con restauración ensayada; nunca subir dumps al repositorio/chat. Conservar cifrados los tokens; no copiar a la prueba `APP_ENCRYPTION_KEY`, secretos de sesión, credenciales de proveedores ni variables productivas. No descifrar credenciales para esta validación.
2. Restaurar en PostgreSQL descartable, con rol propio y sin egress a proveedores/producción. Proteger o anonimizar datos no necesarios, conservando IDs, relaciones y casos de unidad/pack. La copia completa protegida debe permitir comparar sesiones, fichas, versiones, vínculos y **bytes cifrados**, sin usar esos tokens. No arrancar el arnés con un dump auténtico: sus seeds/listas sintéticas siguen rechazándolo.
3. Registrar esquema y conteos/digests privados de las tablas originales antes del cambio, usando una transacción consistente. Hacer preflight `--require core`. Detenerse ante diferencias del esquema original; no inventar su migración. Los datos reales nunca deben sustituirse por fixtures para hacer pasar pruebas.
4. Generar offline el SQL reutilizado: `PYTHONPATH=backend python -m app.services.v2_schema > /ruta/privada/v2-reviewed.sql`. Revisarlo. Son los mismos UP de `documental/migration.py`, `editorial_batches/migration.py` y `migration_2r.py`: tres tablas documentales, dos de lotes, una de señales, sus constraints/índices y una fila de control. Tablas exactas: `kiki_evidence_control`, `kiki_evidence_documents`, `kiki_evidence_dossiers`, `kiki_editorial_batches`, `kiki_editorial_batch_items` y `kiki_editorial_batch_signals`. No hay ALTER/UPDATE/DROP de tablas comerciales anteriores.
5. Sólo con autorización para **esa copia**, el DBA ejecuta el archivo con `psql -X -v ON_ERROR_STOP=1 -f /ruta/privada/v2-reviewed.sql`, usando un servicio/PGPASSFILE privado previamente comprobado, sin contraseña en argumentos. El SQL es transaccional, usa advisory lock y lock timeout, rechaza grupos parcialmente instalados y evita reinserciones al repetirlo. Tablas presentes con columnas/índices incompatibles requieren revisión, no ejecución a ciegas.
6. Repetir preflight completo y comparar registros/digests/versiones/cifrados antes/después. Probar la autenticación de **prueba** y editor sobre una variante de esa copia; no reutilizar la sesión/clave/cookies productivas. No restaurar ni borrar sesiones del cliente como parte de la migración.

El ensayo automatizado local copió todas las tablas originales a otro schema, incluyó fichas versionadas, vínculos y credenciales cifradas **inventadas**, aplicó dos veces los UP y comparó todos los registros: iguales. El preflight no modificó last_seen. Después, la sesión anterior de prueba siguió autenticando, la ficha conservó versión/contenido y los cifrados siguieron iguales. El GET autenticado puede actualizar last_seen por el contrato original; no se presenta como una consulta SQL sin efectos.

## Orden de despliegue en Render — preparado, NO autorizado ni ejecutado

**API y web tienen auto-deploy desde main según la configuración comunicada. Una fusión puede desplegar ambos a la vez. NO fusionar ni publicar main antes de controlar eso.**

1. Revisar commit/pruebas y obtener autorización de distribución y ventana de mantenimiento. El responsable debe verificar y, con autorización explícita, desactivar auto-deploy de **ambos** servicios y cualquier autosync de Blueprint que pudiera reactivarlo. Confirmarlo en la configuración efectiva. No inferirlo de `render.yaml`; este archivo no se modificó. Si no se puede congelar el despliegue simultáneo, **detenerse antes de merge/main**.
2. Tener listo el respaldo/restauración anterior, la copia validada y los SHA/builds/configuración de reversión. Comprobar que no haya captura Ecomm-App manual/programada o lote activo antes de reiniciar backend. Evitar las ventanas 08:25 y 16:25 de Argentina. No disparar sincronizaciones para probar el despliegue.
3. Autorizar por separado la integración del commit revisado en main y cada despliegue manual. Con ambos auto-deploy apagados, preparar backend primero. Verificar que el comando efectivo use `python /app/start.py` del Dockerfile, no un override antiguo de uvicorn. El lector requiere las capacidades estándar de separación de UID/chroot y seccomp; nunca usar `--privileged` ni una alternativa sin aislamiento. Probar el mismo artefacto y comprobar disponibilidad del lector antes de habilitar documentos. Si la plataforma no permite la frontera, mantener archivos bloqueados y no declarar cerrado el piloto documental online.
4. Inicialmente: `KIKI_V2_ENABLED=false`, `KIKI_AUTO_CREATE_SCHEMA=false`, `KIKI_V2_WRITES_ENABLED=false`, `KIKI_V2_CONNECTIONS_ENABLED=false`, `KIKI_V2_AI_GENERATION_ENABLED=false`, documentos/lotes/ejecutor nuevos apagados. Mantener exactamente los secretos de sesión/cifrado/cuentas existentes. Si hay archivos de secretos, comprobar acceso del usuario API efectivo sin mostrar contenidos. Desplegar API manualmente, validar `/health`, login habitual y las lecturas de la aplicación anterior **antes de tocar web**. Si falla, volver al artefacto anterior.
5. Las migraciones productivas necesitan autorización específica adicional. Repetir comprobación de destino/respaldo y aplicar sólo el SQL ya probado sobre la copia. Verificar antes/después. Si el esquema original difiere, hay bloqueos, falta respaldo o cambia el estado de trabajos, detenerse. Nunca habilitar funciones para disimular una migración faltante.
6. Desplegar web manualmente: `cd frontend && npm ci && npm run build:production`; publicar `frontend/.production-dist`. Preservar `/api/* → FastAPI existente` antes del rewrite SPA `/* → /index.html`, cookies/Set-Cookie, CSRF, cabeceras X-Kiki-UI/contrato y propuestas. El navegador usa el origen web actual para `/` y `/v2/`. No cambiar `kiki-tech-2-demo`, que conserva `npm run build` y su aislamiento.
7. Con `/` validado, autorizar `KIKI_V2_ENABLED=true` y las lecturas autenticadas de capturas reales, inicialmente sin escritura/actualizaciones/IA. Verificar cinco vistas, fechas, Ecomm ID, EAN/SKU repetidos, unidades/packs y canales sin evidencia. No asignar Hileret por EAN: aún necesita la variante auténtica y revisión de identidad autorizada.
8. Sólo tras aprobación: habilitar documentos/canales según esquema/lector, autorizar **un** guardado interno con versión e historial y su prueba 409, y luego lotes con previsualización/confirmación. No autoaprobar ni publicar. Mantener conexiones/consumos desactivados hasta autorización específica. No reactivar auto-deploy hasta cerrar la revisión y acordar expresamente la política futura.

## Reversión probada y condiciones de parada

- `/v2/` desactivada no invalida sesiones ni bloquea `/`/`/dashboard-classic`. Deshabilitar nuevas operaciones y volver a la interfaz anterior; conservar registros, versiones, documentos y tablas aditivas.
- Si se necesita rollback de código, hacerlo manualmente a los SHA previos con auto-deploy todavía congelado, manteniendo variables originales. No ejecutar DOWN ni restaurar toda la base sobre trabajo reciente del cliente. Los lotes/capturas activos requieren cierre o recuperación controlada antes de reiniciar; no matarlos a ciegas.
- Parar ante destino/rol/TLS incorrectos, diferencias de esquema original, SQL parcialmente instalado, datos/cifrados alterados, cookies/CSRF fallidos, captura incompleta, fallo de la app anterior, lector sin aislamiento, consumo no autorizado o imposibilidad de controlar los despliegues simultáneos.

## IA y evidencia real

OpenAI original conserva cliente, presupuesto y cuota. Su alcance es título y descripción; no genera de forma verificada los 18 campos con citas. El generador determinista respaldado, revisión por campo y editor sí se reutilizan. Investigación web de fabricantes y el contrato completo de OpenAI siguen pendientes de autorización/validación real. **No hubo consumos ni investigaciones externas.** El PDF Hileret confirma EAN individual `7794940000796`, 200 ml, caja logística x9 y DUN `97794940000799`, con citas de página 2; no confirma ingredientes, alérgenos, nutrición o certificaciones, ni el Ecomm ID. Pack x6 permanece separado.

Los rechazos se conservan: 422 en validación inicial del contrato normal para archivos grandes sin hash autorizado; 409 al rechazar el lector tipo/contenido, ante lector no disponible/límites (`READER_LIMIT_OR_UNAVAILABLE`), identidad/versión o concurrencia. Un rechazo por límite no es rechazo comercial ni fallo de publicación. No se amplían límites ni se reintenta automáticamente hasta obtener éxito. Las repeticiones del original son intentos independientes contados, no una máscara de los rechazos. La incidencia histórica sigue siendo pertinente bajo presión de recursos; una tanda exitosa no es garantía de ausencia futura de 409.

## Resultado de validación

- **129 pruebas backend/integración + 484 regresiones heredadas aprobadas**; además, proceso independiente de preflight aprobado sin importar Settings ni engine del backend. Incluye esquema completo, rechazo de escrituras, copia de todas las tablas originales, preservación de datos/cifrados y reversión de flag sin romper sesión/API anterior.
- **16 Playwright productivos aislados** (escritorio/celular): cinco vistas, filtros EAN/SKU repetidos, editor/18 campos/guardado, evidencias, propuesta/revisión por campo, IA con transporte simulado sin consumos, historial, Centro de conexiones, rollback de `/v2/` y lote de seis Ecomm ID que crea tareas sin modificar fichas. **58 regresiones demo aprobadas**. TypeScript, builds demo/integración/productivo y Ruff aprobados.
- **Imagen productiva real probada offline** con API y lector juntos; seccomp nativo, chroot sin backend/proc/credenciales y cuatro rechazos (hash, MIME, tamaño genérico, HTML activo). Sin privilegios de separación, se comprobó API saludable y lector bloqueado, sin parser alternativo. Una tanda anterior se interrumpió al no obtener respuesta del transporte; no hay evidencia suficiente para atribuirla a CPU, memoria o contenido y no se la presenta como exitosa. Una repetición acotada de seis intentos independientes aprobó **6/6**, con EAN/DUN/citas correctos, entre **3,144 y 4,079 s** incluyendo docker-exec y transporte. No se modificaron límites ni se reintentó ocultamente hasta pasar.
- El contenedor de prueba tuvo `--memory=512m`; la métrica de cgroup visible en este Docker anidado no permite certificar un pico por servicio y no se usa como prueba de ese consumo. Los límites por hijo son explícitos de kernel; la capacidad efectiva de Render requiere comprobación autorizada. No se promete ausencia futura de 409 bajo presión.
- La primera prueba de filtros intentaba usar un desplegable después de recargar, cuando estaba cerrado; se corrigió el recorrido del test para abrirlo, manteniendo aserciones y clics normales. Un intento de lanzar un subproceso dentro del arnés fue correctamente bloqueado: el preflight se prueba en un proceso confiable independiente, sin debilitar esa protección. Se contrastan los índices de migraciones aprobadas en las tablas aditivas, no índices automáticos de ORM que esas migraciones deliberadamente no crean.

No hay validación del esquema efectivo de producción, de su copia auténtica ni de capacidades efectivas de Render: esas operaciones siguen pendientes de autorización. Las pruebas locales no sustituyen esa aceptación.

## Archivos de la entrega

- `backend/.dockerignore`
- `backend/Dockerfile`
- `backend/app/api/routes/v2.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/services/documental/contracts.py`
- `backend/app/services/documental/local_documents.py`
- `backend/app/services/v2_preflight.py`
- `backend/document_reader/__init__.py`
- `backend/document_reader/hileret_brochure.py`
- `backend/document_reader/parser.py`
- `backend/document_reader/security.py`
- `backend/document_reader/worker.py`
- `backend/integration_sandbox/activation_checks.py`
- `backend/integration_sandbox/document_parser.py`
- `backend/integration_sandbox/document_worker.py`
- `backend/integration_sandbox/hileret_brochure.py`
- `backend/integration_sandbox/policy.py`
- `backend/integration_sandbox/preflight_checks.py`
- `backend/integration_sandbox/requirements-documents.txt`
- `backend/reader_launcher.py`
- `backend/requirements-reader.txt`
- `backend/start.py`
- `frontend/integration-tests/production-connected.spec.ts`
- `frontend/src/integration/DocumentImport.tsx`
- `integration/ACTIVATION-CHECKLIST.md`
- `integration/Dockerfile`
- `integration/Dockerfile.dockerignore`
- `integration/PRODUCTION-V2-ROLLOUT.md`
- `integration/gateway.py`
- `integration/production_image_checks.py`
- `integration/run.py`
