# Etapa 2M — Adaptador HTTPS preparado, consulta real no ejecutada

Base verificada: `feature/kiki-tech-2-dashboard`,
`49e92d28aa7c026444c0dd8b672b470fa9e29d5b`, árbol inicialmente limpio.
Cambios limitados a `tools/ecomm_readonly/`. Sin cambios, inicio o interrupción de
backend, frontend, PostgreSQL, Render, integraciones o expedientes de KIKI.

**No hubo DNS, TLS, HTTP o consultas auténticas a Ecomm-App. No se leyó ninguna
credencial real. El comando de consulta real no se ejecutó.** Las pruebas del
camino nativo reemplazan todas las primitivas de red por dobles en memoria.

## Adaptador y controles conservados

`native.py` implementa resolver de sistema y sockets TCP/TLS nativos, reutilizando
`PinnedGetWire`, `policy.py` y `InventoryReader`. Construir el adaptador no resuelve
ni conecta. Sólo `read()` puede iniciar el recorrido autorizado.

- URL y método cerrados: GET al host/ruta/filtro literales del contrato. El
  escritor nativo valida nuevamente todos los bytes de la petición; rechaza
  texto libre, POST, otra ruta, otra credencial y un segundo envío por conexión.
- TLS >= 1.2, CA del sistema, certificado/hostname verificados y SNI fijo. No
  keylogs, CA introducida por CLI, modo inseguro o sesiones de KIKI.
- Todas las IP DNS deben ser públicas; se fija una única IP numérica, se
  comprueba el peer antes/después del TLS y al leer, y se revalida el conjunto DNS
  antes de Authorization. Cambio de DNS, IP privada o peer distinto bloquean.
- Cero seguimiento de redirecciones, incluso dentro del mismo origen; todo 3xx
  o `Location` se rechaza. Cero retries HTTP, refresh de token, cookies o fallback.
- 12 s por operación y 2 MiB por respuesta; límites de cabeceras, framing y JSON
  anteriores conservados. El resolver usa una espera acotada porque `getaddrinfo`
  no ofrece timeout Python; si se vence, finaliza la consulta y el proceso
  independiente descarta el worker daemon. No se inicia otra resolución de retry.
- Una página por defecto; máximo dos sólo con presupuesto explícito y paginación
  válida. El presupuesto existe tanto en el lector como en la fábrica de sockets.
  Un error consume su intento. Sin metadatos/coherencia, se bloquean conclusiones.
- Hook de auditoría por defecto cerrado: sólo una operación nativa fija recibe
  permiso temporal con autorización vigente. No permite otro hostname, destino,
  puerto, operación o sockets después del bloque. Backend, DB, subprocesos,
  escrituras e imports peligrosos siguen prohibidos.
- Proceso Linux/WSL con Python `-I -S -B` (sin site hooks/paquetes instalados), memoria 160 MiB, CPU 5/6 s, alarma 30 s,
  core dumps y archivos de salida deshabilitados. Sólo salida por stdout al
  operador; no guarda snapshots, sesiones, vínculos, aprobaciones o fichas.

La aplicación limita **las peticiones que solicita** a GET. Eso no prueba que el
proveedor carezca de efectos internos: puede registrar accesos, consumir cuota,
medir uso o actualizar sus propios controles. El resultado declara esos efectos
como no verificados, sin afirmar cero escrituras internas de Ecomm-App.

## Alcances de la credencial: evidencia y límites

La [documentación del contrato aportada por el titular el 23/10/2026](../../docs/ecomm-app-public-api-v1-pilot.md)
describe claves Bearer con selección del scope **`inventario:leer`**, creación de
una clave con sólo ese alcance, revocación manual y reevaluación por request.
El [cliente existente](../../backend/app/integrations/ecomm_app/public_api.py)
reconoce `403 SCOPE_INSUFICIENTE`. Se auditaron como texto; no se importaron.
La configuración de Render de ese informe histórico no corresponde a este
lector y no está autorizada en esta etapa.
Otro documento anterior de readiness deja contratos pendientes: no se usa ese
estado histórico para atribuir permisos a una clave concreta.

**Según el contrato disponible, sí se ofrece lectura de inventario. No se ha
comprobado la configuración actual de una clave ni el panel del proveedor.**
No existe contrato de introspección/listado de scopes implementado en el repositorio.
Un 200 tampoco demostraría ausencia de otros permisos. No se decodifica un token
opaco ni se envían operaciones de escritura para probar su rechazo.

Antes de la consulta, el titular deberá revisar los permisos reales en el panel
o mediante una confirmación del proveedor y suministrar una constancia privada.
El lector exige exactamente `["inventario:leer"]`; permisos desconocidos,
adicionales, de escritura o no revisados bloquean. La constancia debe identificar
cuenta, referencia de esa revisión, fecha/expiración y huella del token. El SHA
vincula la constancia con la clave suministrada; **no prueba ante el servidor que
los permisos sean esos**. El resultado lo etiqueta
`OWNER_ATTESTED_NOT_SERVER_VERIFIED`.

## Suministro futuro seguro, sin usar credenciales productivas de KIKI

No se han creado, copiado ni modificado claves. Después de una autorización
separada, el titular/gestor de secretos podrá entregar una clave de inventario
revisada, independiente de Render/KIKI, mediante un archivo privado del sistema
operador. No pegar el secreto en chat, argumentos, shell history, env, capturas,
código, Git o logs. No copiar `.env` ni extraer una clave de Render.

El comando admite **rutas**, nunca el valor del token. Ambos archivos deben ser
regulares, absolutos, del UID ejecutor, permisos 0400/0600, un enlace y sin symlink
final. Se validan metadatos del descriptor antes de leer y de nuevo al terminar;
se rechazan FIFOs, dispositivos, archivos compartidos, cambios y exceso de bytes.
Usar además un directorio privado 0700 del operador. No cambiar permisos de
archivos productivos para hacerlos pasar por esta validación.

El archivo de credencial contiene sólo el valor opaco ASCII (hasta 4096 bytes);
se tolera un LF terminal. No se imprimen su contenido ni huella. El archivo de
constancia, hasta 16 KiB, tiene esta estructura; **esta plantilla es inválida
hasta completarla mediante revisión real del titular**, no es una autorización:

```json
{
  "version": 1,
  "host": "admin.ecomm-app.com",
  "path": "/api/v3/public/inventario/productos",
  "method": "GET",
  "barcode": "7794940000796",
  "max_pages": 1,
  "scopes": ["inventario:leer"],
  "credential_sha256": "<64 hex del valor exacto de la clave, sin LF terminal>",
  "account_reference": "<cuenta real autorizada, sin secretos>",
  "permissions_reference": "<referencia de revisión del panel/proveedor>",
  "reviewed_at": "<UTC YYYY-MM-DDTHH:MM:SSZ>",
  "expires_at": "<UTC YYYY-MM-DDTHH:MM:SSZ>",
  "reviewed_by_owner": false
}
```

La revisión debe tener menos de 24 h y un vencimiento posterior, de hasta 24 h.
Es la vigencia de la constancia local, no una afirmación de expiración del token.
No se imprime ni modifica la constancia. No hay introspección o renovación.

## Comando exacto preparado — NO ejecutado

Desde la raíz del repositorio, **únicamente tras nueva autorización y en un
Linux/WSL directo revisado**, con los dos archivos privados provisionados en las
rutas indicadas:

```bash
python3 -I -S -B tools/ecomm_readonly/query.py --authorize-one-query --credential-file /run/user/1000/kiki-ecomm-pilot/credential --scope-evidence /run/user/1000/kiki-ecomm-pilot/scope-evidence.json --max-pages 1
```

Ese comando contempla **una sola petición GET**, sin segunda página. No se ejecutó
ni siquiera para probar su bloqueo en este entorno. Si luego se autorizan hasta
dos páginas, tanto la constancia como `--max-pages` deben admitir 2; aun así sólo
se pide la segunda si los metadatos válidos de la primera lo justifican. Más
páginas requieren otro alcance, nunca un barrido automático. No repetir la
invocación ante un fallo sin revisar alcance y autorización.

La petición preparada es:

```text
GET https://admin.ecomm-app.com/api/v3/public/inventario/productos?barcode=7794940000796&page=1&limit=50&sort=sku_asc
```

**No funciona como consulta real en el Codex actual.** Se comprobó mediante
metadata, sin sondeos, que la política está `restricted/enforced`, observaciones
actuales, sin `admin.ecomm-app.com` permitido y sin secretos configurados. La
plataforma exige proxy, cuyo peer TCP corresponde al proxy y cuyo DNS remoto no
puede fijarse/verificarse con este adaptador directo. El adaptador rechaza Codex
o cualquier proxy heredado **antes de abrir credenciales o resolver**. No quitar
el proxy, usar `NO_PROXY`, host networking o un túnel para evitar ese bloqueo.

Para ejecutarlo desde Codex faltaría, con revisión/autorización posterior, una
ruta de plataforma que permita demostrar el destino final y acceso permitido al
host. Agregar el host por sí solo no resuelve la incompatibilidad del transporte.
No se cambió configuración de red, credenciales o servicios. Si esa garantía no
está disponible, usar el entorno directo autorizado o una exportación del titular.

## Información devuelta y Hileret

Resultado JSON por stdout: origen fijo, EAN consultado, presupuesto de páginas,
fecha UTC, alcance completo/desconocido/truncado, hash SHA-256 de cada cuerpo
recibido, hash de la constancia y candidatas por variante. Devuelve:

- `response_variant_id` literal desde `data.items[i].variants[j].id`, ruta y página
  de origen; sin fallback a SKU, padre, depósito o filas del Excel.
- Campos nativos de nombre, SKU, marca, presentación, `barcode`, `gtin`, combo
  del padre y variante; cantidad comercial y volumen sólo cuando son explícitos.
- Bloqueos por identidad nula/inválida, EAN/GTIN contradictorios, marca ausente,
  presentación/cantidad/combo sin comprobar, múltiples candidatas o paginación
  incompleta. Los duplicados de ID invalidan la respuesta, no se fusionan.

Varias variantes siguen siendo candidatas separadas. Compartir EAN no fusiona la
unidad 200 ml, pack x6 y caja x9. El DUN no identifica la unidad. El resultado no
aporta composición, nutrición o certificaciones. `authentic_ecomm_id` sigue nulo,
`binding_permitted` es false y requiere revisión humana, aun si una candidata
parece compatible. No modifica el expediente ni transfiere aprobaciones.

Los errores son códigos fijos, sin tokens, paths, respuestas o excepciones
originales. Se bloquean ecos de la credencial en cuerpos y valores JSON escapados.
No se expone la respuesta HTTP original completa ni cabeceras al operador.

## Validación offline y archivos

Se conservaron **sin editar** las 59 pruebas previas en contenedor y 4 del lanzador.
Se agregaron **30 pruebas** de 2M; total **93 aprobadas** (88 en contenedor sin red,
4 del lanzador con Docker simulado y 1 de arranque negativo sin autorización).
Incluyen recorrido completo del futuro CLI
en memoria, scopes desconocidos/adicionales, huella, vigencia, archivos privados,
credencial ausente, destino/método, TLS inválido, redirecciones/errores, DNS público
mixto/rebinding/timeout, peer, páginas, variantes, IDs/EAN y no acceso a backend/DB.
Se comprueba también el pin IPv6, con rechazo de loopback y scope IDs.
El modo offline mantiene sockets bloqueados fuera de los permisos acotados.

```bash
python3 tools/ecomm_readonly/run.py build
python3 tools/ecomm_readonly/run.py test
python3 -B tools/ecomm_readonly/test_launcher.py
python3 -I -S -B tools/ecomm_readonly/test_query_entrypoint.py
.venv/bin/ruff check tools/ecomm_readonly
.venv/bin/ruff format --check tools/ecomm_readonly
```

Construcción desde caché local, sin red ni descargas. Ruff y formato aprobados.
Las pruebas sólo emiten eventos de auditoría simulados y usan DNS/socket/TLS de
memoria; no establecen DNS/certificados/scopes/cuenta reales de Ecomm-App. No se
iniciaron backend o PostgreSQL ni se ejecutaron suites contra servicios activos.
PDF Hileret conservado con SHA-256
`bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291`.

Modificados: `ecomm_reader/{__init__,reader,safety,wire}.py`, `README.md`.
Agregados: `ecomm_reader/{authorization,native,query}.py`, `query.py`,
`tests/test_native.py`, `test_query_entrypoint.py`, este informe. Sin cambios fuera de este directorio.

Riesgos pendientes: compatibilidad con proxy/entorno de ejecución, verificación
actual de la clave por su titular/proveedor, confianza y posible cambio posterior
de esa constancia (no es una firma del proveedor), formato real de cuenta/campos
nativos y respuesta, frescura/consistencia entre páginas y efectos internos del
GET. La constancia no tiene consumo persistente anti-replay; cada invocación
necesita autorización, sin cron o reintentos. Python no garantiza borrado de
cadenas en memoria; se restringen archivos, procesos, dumps y salida, sin prometer
zeroización. No hubo push, PR, merge, despliegue o consulta real.
