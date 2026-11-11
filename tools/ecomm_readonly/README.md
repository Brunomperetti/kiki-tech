# Lector Ecomm-App: modo offline y adaptador preparado en 2M

La etapa 2M agregó un adaptador nativo HTTPS sin ejecutarlo. Véase
[PREPARED-QUERY-2M.md](PREPARED-QUERY-2M.md) para autorización, credenciales,
comando futuro, pruebas y límites de despliegue. **Codex/proxies se rechazan antes
de leer credenciales: este transporte no permite verificar su destino final.**
Los comandos `run.py plan/demo/test` conservan su operación sin red.

Base comprobada antes de modificar archivos: rama
`feature/kiki-tech-2-dashboard`, HEAD
`3eb6e27b20b96aa670532a3fbcd81a7bfce5ac43`, árbol limpio.

**No se ejecutó ninguna consulta auténtica. El Ecomm ID Hileret sigue pendiente.**
Este directorio nuevo no modifica ni importa el backend, frontend, integración
activa, expediente, documento, decisiones ni aprobaciones de KIKI.

## Arquitectura y aislamiento

- `run.py`: lanzador de un contenedor independiente, efímero y sin red. Usa el
  socket Docker local y una configuración Docker temporal vacía; no hereda
  tokens, variables de proveedor, PostgreSQL, proxies ni configuración de registro.
  No inicia Compose, FastAPI o PostgreSQL, ni detiene contenedores existentes.
- `Dockerfile`/`prepare_runtime.py`: reutilizan únicamente CPython 3.12, su stdlib,
  bibliotecas de sistema necesarias y certificados CA de una imagen **local** ya
  instalada. La imagen final parte de `scratch`: no incluye el código del donante,
  paquetes instalados, aplicación, shell, `.env`, documentos ni credenciales.
  La copia usa Python `-I -S`; no ejecuta el backend del donante. La compilación
  tiene `--network=none`, `--pull=false` y se detiene si falta la imagen local.
- `entrypoint.py`/`ecomm_reader/safety.py`: Python aislado, sin bytecode, hook de
  auditoría irreversible con rechazo por defecto de sockets/DNS, escrituras, subprocesos e importaciones
  de backend/DB/ctypes. Se bloquea el inicio si el proceso ya importó esos módulos.
  Es defensa adicional; el límite de sistema operativo del modo offline es el
  contenedor sin red. En 2M sólo el adaptador autorizado puede abrir un permiso
  temporal para una operación nativa fija, sin relajar las demás prohibiciones.
- El contenedor no tiene montajes, puertos publicados, privilegios o capacidades;
  raíz readonly, UID/GID 1000, `no-new-privileges`, 192 MiB, un CPU y 16 procesos.
  El lector limita memoria virtual a 160 MiB y CPU a 5/6 s. Sólo devuelve resultados
  por stdout; no escribe archivos, sesiones, referencias, decisiones o fichas.
- `policy.py`/`wire.py`: política cerrada de GET y codec HTTP real, ejercitado con
  sockets/TLS de memoria. El CLI offline no admite `--live`, credenciales, `.env`
  o fallback de red. `native.py` agrega en 2M resolver y sockets nativos a través
  del mismo codec, sólo mediante el comando independiente `query.py` y su
  autorización explícita. Ese comando no se ejecutó contra ningún servicio.
- `catalog.py`/`reader.py`: validación de respuesta, identidad y paginación. Los
  dobles están separados en `simulated.py`; sus IDs y SKU son explícitamente
  ficticios y nunca se guardan en KIKI. `authentic_ecomm_id` permanece `null` y
  `binding_permitted` siempre es `false`.

## Contrato de consulta preparado, no ejecutado

Único host permitido: `admin.ecomm-app.com`. Único método: `GET`.
Primera operación futura propuesta:

```text
https://admin.ecomm-app.com/api/v3/public/inventario/productos?barcode=7794940000796&page=1&limit=50&sort=sku_asc
```

La segunda usa exactamente el mismo URL con `page=2`, sólo si la paginación
validada de la primera demuestra que existe. Máximo **dos solicitudes**, cero
reintentos, sin renovación de tokens, cookies, sesiones, POST o búsquedas sin
filtro. Un error consume su solicitud. La instancia no puede reutilizarse.

Se exige `data.items` y, cuando exista, `data.paginacion` o `data.pagination`
con `page`, `total`, `per_page` y `total_pages` enteros coherentes con el tamaño
de página y la cantidad de productos. Metadatos incompatibles detienen el lector.
Sin paginación sólo se permite una página y se bloquea cualquier conclusión de
identidad completa. Con más de dos páginas se declara truncamiento y se bloquea
la revisión favorable; jamás se solicita una tercera. Cero resultados no acredita
ausencia de Hileret en el catálogo. No se promueve la respuesta a catálogo maestro.

Límites: 12 s por operación completa, 2 MiB por cuerpo, 16 KiB de cabeceras,
presupuesto adicional acotado de framing HTTP y límites de JSON/estructura.
Sólo JSON UTF-8, sin compresión, claves duplicadas o valores no finitos. Se rechazan
errores HTTP y cuerpos que repitan la credencial de control.

## Controles de destino y redirecciones

Se rechaza cualquier URL diferente del contrato literal: HTTP, otros hosts/rutas,
puertos explícitos, credenciales en URL, fragments, filtros extra o métodos
distintos de GET. Todas las respuestas 3xx y cualquier `Location`, incluso en un
200, se rechazan. No hay código de seguimiento de redirecciones.

La política comprueba todas las direcciones DNS: sólo IP públicas, sin destinos
privados, locales, link-local, reservados, multicast, metadata, IPv4 mapeada o zonas.
Fija una IP numérica, exige TLS con SNI del host exacto, verificación de certificado
y hostname, CA del sistema y TLS >= 1.2. Se verifica el peer TCP/TLS/final y se
revalida el conjunto DNS antes de enviar Authorization. Cambios de DNS bloquean
el envío. Se prohíben keylogs y contextos TLS debilitados. Todo se prueba con
dobles: **no demuestra un handshake o DNS auténtico de Ecomm-App**.

Los errores públicos son códigos fijos: no incluyen argv, valores recibidos,
cabeceras, mensajes del proveedor o excepciones originales. La credencial no
aparece en `repr`. Los tests sólo emplean controles explícitamente no secretos.

## Identidad de variante y Hileret

| Campo | Regla |
| --- | --- |
| ID | Exclusivamente `data.items[i].variants[j].id`, conservado como cadena. Se aceptan enteros positivos o cadenas decimales canónicas de hasta 120 caracteres. Se rechazan nulos, vacíos, `None`, `null`, booleanos, floats, ceros, duplicados y formatos desconocidos. Sin fallback a SKU, padre o depósito |
| EAN | Conservar `barcode` y `gtin`. Si discrepan, mostrar ambos y bloquear. Exigir checksum válido y correspondencia con `7794940000796`; DUN `97794940000799` no identifica la unidad |
| Marca/nombre | Marca nativa explícita Hileret, sin contradicción padre/variante; nombre del producto con Stevia. No inferir la marca del nombre, SKU, PDF o sugerencias ML/TN |
| Presentación | 200 ml/200 cc/0,2 l explícitos y cantidad comercial explícita. Una presentación ambigua bloquea; la lista de formatos es deliberadamente conservadora |
| Cantidad/combo | Unidad individual explícita y `variant.is_combo is False`; combo del padre incompatible bloquea. `None`, `0` o `"false"` no equivalen a False. Ni stock ni sufijo SKU prueban cantidad |
| Ambigüedad | Dos IDs compatibles bloquean ambas candidaturas. Unidad, pack x6 y caja x9 siguen separados aunque compartan EAN. Cero unión automática |

`eligible_for_human_review` sólo señala compatibilidad de una **respuesta simulada**
para revisar. No acredita identidad auténtica, aprobación humana o vinculación.
No existe operación de vinculación ni traslado de aprobaciones en este lector.

## Cómo repetir la validación offline

Desde la raíz del repositorio, con Docker local y la imagen caché
`kiki-tech-integration:local` disponibles:

```bash
python3 tools/ecomm_readonly/run.py build
python3 tools/ecomm_readonly/run.py test
python3 -B tools/ecomm_readonly/test_launcher.py
python3 tools/ecomm_readonly/run.py plan
python3 tools/ecomm_readonly/run.py demo
.venv/bin/ruff check tools/ecomm_readonly
.venv/bin/ruff format --check tools/ecomm_readonly
```

`plan` sólo imprime el contrato. `demo` sólo usa tres respuestas sintéticas en
memoria, sin conexiones ni base. No ejecutar los módulos con configuraciones de
producción ni añadir sockets, montajes o variables de credenciales al contenedor.

## Resultado y límites pendientes

Validación ejecutada en este entorno: **59 tests dentro del contenedor sin red y
4 tests del lanzador con Docker simulado**, aprobados. Cubren GET exclusivo,
destino cerrado, SSLContext estricto, redirecciones, DNS mixto/rebinding, peer,
límites, errores y redacción de credenciales; identidad por ID anidado, EAN/GTIN,
unidad/pack/caja, cantidad/marca faltantes, duplicados y paginación; bloqueo de
sockets, DNS real antes de I/O, escrituras, subprocesos, imports DB/backend y
aislamiento efectivo del contenedor. Ruff y formato verificados. `plan`/`demo`
devuelven red real deshabilitada y ninguna vinculación.

No se ejecutaron suites de backend, frontend ni PostgreSQL: esos componentes no
cambiaron y no se iniciaron para esta tarea. El PDF Hileret conserva SHA-256
`bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291`.

La primera consulta auténtica **sigue sin estar autorizada**. El adaptador directo
está preparado en 2M, con pruebas exclusivamente simuladas. Faltan autorización
explícita, provisión segura y revisión de scopes de una credencial concreta.
En Codex faltan además acceso permitido al host y un transporte compatible con
el proxy que garantice TLS/DNS/destino final. El adaptador directo rechaza ese
entorno; no se debe retirar el proxy para ejecutarlo. Véase el informe 2M para
la alternativa de ejecución futura en un entorno directo revisado y autorizado.

La forma exacta de IDs, paginación y campos nativos de la cuenta no fue comprobada
en vivo. Si difiere, se rechaza; no se relajan reglas ni se completan con Excel o
datos simulados. La identidad y la aprobación humana del expediente siguen
pendientes. Una futura lectura tampoco autoriza escribir o vincular.
