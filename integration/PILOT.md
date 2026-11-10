# Etapa 2I — Preparación del piloto documental

Base comprobada: `feature/kiki-tech-2-dashboard`, HEAD
`95dad16d4afbe192e87e31b2ff5909b0482a86dc`, árbol inicialmente limpio.

## Estado de esta entrega

**No se ejecutó el piloto real. No se recibieron documentos auténticos ni se
seleccionaron productos o dominios de fabricantes.** El manifiesto incluido está
vacío. Los nombres, productos, EAN y documentos de las pruebas son sintéticos;
no representan a un fabricante ni a un cliente.

Se implementa el adaptador HTTPS independiente y su política, pero no se conecta
al recolector activo de 2H. Ese recolector sigue exclusivamente simulado. FastAPI,
PostgreSQL, lector y recolector conservan `network_mode:none`. El demo conserva
su aislamiento sin backend. No se agrega un servicio con salida a Internet.

## Arquitectura del conector

```text
dashboard único -> gateway local -> FastAPI de integración
                                    -> PostgreSQL por socket Unix
                                    -> recolector 2H por socket Unix (simulado)
                                    -> lector documental 2G por socket Unix

adaptador HTTPS 2I, preparado pero NO conectado al runtime:
  plan explícito -> alcance por Ecomm ID/fabricante/URL/vigencia
                -> DNS público validado -> IP numérica fijada
                -> TLS con hostname/SNI original -> HTTP GET acotado
                -> documento + hash + cadena de destinos + auditoría
                -> futura transferencia controlada al lector 2G
```

`https_connector.py` y `pilot_policy.py` no importan la aplicación, engine,
configuración o credenciales comerciales. No hay cambios en `backend/app`,
modelos productivos, integraciones Ecomm-App/ML/TN, dependencias productivas,
Render, workflows ni código del demo. No hay tablas ni migraciones nuevas.

La revisión 2E conserva referencias ORM a documentos durante cada operación,
bajo su mutex existente, para evitar recargas SQL por cada par de hechos. No se
memorizan reglas, decisiones ni resultados de validación; reemplazos y revocaciones
siguen comprobando versiones/hashes. Una prueba limita las lecturas SQL de una
consulta documental y las suites conservan los casos de concurrencia e invalidación.

El adaptador tiene dos cierres: `REAL_NETWORK_ENABLED=False` en esta entrega y
`network_enabled:false` obligatorio en el plan. No se leen variables para
activarlos. El conector, el DNS y el transporte real rechazan antes de resolver
nombres o abrir sockets. Validar un plan no habilita red. La inyección de dobles
se reserva a código de pruebas confiable; no se expone a HTTP ni a documentos.
La entrada pública del transporte permanece bloqueada incluso al inyectar
dependencias; los ensayos del códec usan su método privado con sockets falsos.

## Controles implementados

- Dominios exactos, sin comodines, URL exacta y fabricante/variantes autorizados.
  Cada salto debe estar incluido, incluso un CDN del fabricante. Se rechazan
  HTTP, IP literales, credenciales, puertos alternativos, query, fragmentos,
  escapes, rutas con `..` y nombres locales. Las URL actuales deben ser ASCII.
- Todas las respuestas DNS deben ser públicas; se rechazan loopback, privadas,
  link-local, CGNAT, multicast, mezclas públicas/privadas, IPv4 mapeada en IPv6,
  6to4 y Teredo. Una consulta DNS por salto; conexión a IP numérica y comprobación
  del peer antes y después de TLS. No hay segunda resolución implícita en HTTP.
- TLS con `CERT_REQUIRED`, verificación de hostname/SNI, mínimo TLS 1.2 y CA del
  sistema por ruta fija. No consume `SSL_CERT_FILE`, certificados del documento,
  cookies, autenticación, proxy con credenciales ni cabeceras arbitrarias.
- DNS acotado por tiempo, con un único resolver en segundo plano como máximo;
  si queda pendiente, se rechazan otras consultas. El vencimiento no espera a un
  `getaddrinfo` bloqueado. El runtime actual bloquea además DNS en el kernel/hooks.
- Hasta 5 segundos por obtención, incluyendo resolución, conexión, handshake,
  cabeceras y cada lectura; timeout de inactividad hasta 3 segundos. Sin reintentos.
  La pasarela local espera hasta 25 segundos por el socket Unix para cubrir
  recolector, lector y serialización. No amplía plazos de conexiones externas.
- Hasta 512 KiB por documento, 3 documentos, 9 intentos HTTP/DNS y 30 segundos por
  instancia de piloto. Máximo dos redirecciones por obtención y 1,5 MiB de cuerpos
  acumulados, incluidos cuerpos rechazados. Auditoría en memoria de las últimas
  100 operaciones. Una instancia debe corresponder al alcance autorizado completo.
- Sólo GET y tipos PDF, texto UTF-8, HTML pasivo y JSON. Comprueba MIME explícito,
  longitud, firma/contenido básico y compresión. Rechaza cabeceras ambiguas,
  longitudes truncadas, binarios encubiertos, compresión HTTP y codificaciones de
  transferencia ajenas a chunked. La lectura chunked también está acotada.
- El lector 2G sigue siendo obligatorio para validar formato completo, complejidad,
  contenido activo y extracción. Una firma PDF no acredita que el PDF sea válido.
  HTML nunca se renderiza ni ejecuta; scripts y recursos se rechazan en 2G.
- 401/403/429 y otros errores detienen la obtención: sin evasión, login, CAPTCHA,
  reutilización de tokens o scraping alternativo. La autorización exige revisión
  de condiciones y permiso de acceso automatizado; no se presume por ser público.
- Auditoría con ID, fecha, método, dominio autorizado, cantidad/tamaño y código de
  resultado fijo. No registra cuerpos, cabeceras, URL rechazadas, consultas, tokens
  ni mensajes originales de excepciones. El documento conserva su traza aparte.

## Autorizar productos y fuentes, sin ejecutar consultas

1. Elegir **entre uno y tres productos auténticos**, con Ecomm ID y presentación
   comprobados. Solicitar autorización explícita para cada variante; no usar SKU
   o EAN como identidad primaria ni completar datos ausentes.
2. Copiar `integration/pilot-authorization.example.json` a un archivo local privado.
   El archivo versionado permanece vacío y `network_enabled` permanece `false`.
3. Completar `products` con los campos del esquema `PilotProduct`:
   `ecomm_id`, `name`, `manufacturer`, `presentation`, `authorization_reference`;
   `brand` y `ean` son opcionales. Registrar sólo datos suministrados y comprobados.
4. Completar cada `OfficialSource`: `domain`, `urls`, `ecomm_ids`, `manufacturer`,
   `ownership_evidence`, `conditions_review`, `automated_access_permitted:true`,
   `reviewed_by`, `approval_reference` y `expires_at` con zona horaria. Los dominios
   son únicos y no heredan permisos para subdominios. Autorizar expresamente cada
   URL de redirección, fabricante asociado y variante.
5. La evidencia de titularidad debe explicar cómo se comprobó la relación entre
   dominio, fabricante y documento. Mencionar al fabricante, presentar un EAN o
   declarar «oficial» no basta. Registrar revisión de condiciones/robots y límites
   del sitio; si prohíbe automatización, usar documentación suministrada manualmente.
6. Validar **sin red ni base** desde una instalación con las dependencias Python
   existentes del backend:

   ```sh
   .venv/bin/python integration/validate_pilot.py integration/pilot-authorization.example.json
   # Sustituir el último argumento por el plan local autorizado, cuando exista.
   ```

   El validador rechaza claves extra, más de tres productos, incoherencias de
   fabricante, fuentes vencidas, URLs fuera de alcance y activación de red.
   No imprime los valores del plan en errores ni importa `app`.
7. Someter el plan completo a revisión. **No hay endpoint ni comando de activación
   en esta etapa.** Una autorización posterior requiere revisar el cierre de la
   entrega, el runtime separado y la política de salida antes de ejecutar nada.

Este plan registra decisiones humanas; no verifica legalmente titularidad ni
firma la autorización. Debe conservarse con permisos y trazabilidad apropiados.

## Procedimiento del piloto auténtico posterior

### A. Documentos suministrados por el usuario

- Recibir los archivos y autorización para procesarlos localmente, por variante.
  Registrar fabricante declarado, URL de origen cuando exista, fecha de consulta
  informada y cómo se obtuvieron. No inventar fecha o dominio si se desconocen.
- El harness actual sólo admite seis variantes sintéticas. Antes del piloto se
  deberá autorizar una referencia local de las variantes auténticas seleccionadas
  en la base descartable y ajustar su alcance de forma revisada. **No renombrar un
  fixture para hacerlo pasar por el producto real ni modificar Ecomm-App.** Esta
  entrega no carga productos reales ni amplía el acceso del API a otros IDs.
- Dentro del dashboard: Ficha → Investigar producto → incorporación local 2G.
  Preservar original y SHA-256. Contrastar fabricante/EAN/marca/presentación,
  revisar procedencia y aprobar o rechazar cada hecho con su cita. Si no se puede
  contrastar la identidad, mantenerlo bloqueado; el nombre del archivo no valida.
- Generar la propuesta 2F sólo con hechos aprobados, revisar campos y guardar con
  el editor 2D. Consultar historial y recargar. No sincronizar ni publicar.

La incorporación local ya existe: PDF con texto, TXT, HTML pasivo y JSON,
hasta 512 KiB/10 páginas según 2G. Se añadieron fabricante y fecha declarados
opcionales, preservados en las versiones del documento. No son datos extraídos ni
consultas realizadas por el sistema. Las declaraciones y la revisión humana se
muestran separadas; una revisión no aprueba hechos automáticamente.

### B. Documentos desde dominios oficiales

Requiere además autorización posterior del conector y un despliegue de pruebas
separado con salida restringida, sin credenciales y sin acceso a la base/API.
El plan debe estar montado de sólo lectura. Respetar la política de red de la
plataforma: el adaptador de IP fijada no puede usarse para eludir su proxy.
En este cloud no se configuró acceso a fabricantes ni un camino compatible de
salida; la compatibilidad entre proxy, TLS y fijación de destino debe revisarse
antes de habilitarlo. FastAPI, PostgreSQL y lector deben seguir sin red.

El recolector futuro deberá aceptar sólo referencias del plan, obtener un archivo
por vez, transferir bytes y traza por el canal Unix existente y revalidar versiones
antes de guardar mediante 2G. No debe sustituir ni ampliar automáticamente la
allowlist. No hay crawler, motor de búsqueda web ni descubrimiento abierto: los
candidatos reales serán las fuentes explícitas seleccionadas en el plan.

## Registro y verificación por documento

Se reutilizan Document/Dossier, originales y hashes, fuente/fecha de registro,
procedencia declarada, revisión efectiva con operador/fecha/motivo, versiones,
EAN/marca/fabricante/presentación extraídos y sus ubicaciones, citas por campo,
contradicciones y estados de aprobación 2E/2G. Se muestran dominio de referencia,
fabricante declarado frente al extraído y fecha de consulta informada, separada
de la fecha de carga. Una URL manual nunca se visita.

Para el adaptador preparado, la traza contiene URL inicial/final, peers y saltos,
fecha de consulta, hash, MIME, tamaño y referencia de autorización; empieza en
`review_state:PENDING`. **Esa traza todavía no se produce con fuentes reales ni se
incorpora al API activo.** La traza 2H continúa rotulada como simulada.

## Contrato preparado para OpenAI

`GET /api/test-proposals/{ecomm_id}/generation-context`, sólo en el harness, con
sesión y los mismos seis IDs sintéticos. Usa `Proposals.context`, mutex, reglas de
vigencia/bloqueo y versiones existentes. No genera un draft ni modifica el editor.

Versión `kiki-evidence-generation-v1`: Ecomm ID, versión de ficha/expediente,
identidad y huella de evidencias, hechos aprobados vigentes con valor/unidad/cita,
documento/hash/versión/ubicación, límites reales de los 18 campos y `context_hash`.
No se envían originales completos ni datos no aprobados. Un contexto demasiado
largo se rechaza, nunca se recortan citas. Puede consultarse desde IA en el panel.

La política especifica máximo 40 hechos, 24.000 caracteres de contexto, 1.500
tokens de salida, una llamada por propuesta y cero reintentos automáticos.
Modelo sin seleccionar, proveedor apagado, llamadas 0 y presupuestos por operación
y diario de **USD 0,00**. Este contrato no instancia clientes, consume claves ni
llama a OpenAI. El servicio de IA existente permanece deshabilitado y sin cambios.

El backend ya dispone de `EcommAiEditor._reserve`, `KikiEcommAiDailySlot`, límite
global de diez intentos diarios y reutilización de `KikiAiEditorialDraft` por
huella de origen. Se conservan; consultar el contrato no reserva un intento.
No se debe llamar directamente a `suggest` con la captura antigua como si fueran
hechos verificados: el adaptador futuro debe recibir este contexto de evidencias.

Antes de habilitar IA se deben aprobar modelo/precios y límites monetarios,
reutilizar esas reservas/drafts y extenderlas con consumo monetario atómico por
usuario/día, idempotencia
por `context_hash`, control de tokens y auditoría de uso sin cuerpos sensibles.
La respuesta deberá citar IDs aprobados por campo y respetar esquema/límites;
texto de fuentes se trata como dato no confiable, nunca como instrucciones.

Se deberá revalidar contexto, citas, certificaciones y afirmaciones con los
controles 2F existentes; rechazar cualquier afirmación sin respaldo o evidencia
revocada. La aceptación humana por campo y el guardado 2D con `expected_version`
seguirán siendo obligatorios. El límite de tokens, reserva monetaria y contrato
de salida se especifican para el adaptador futuro: **no se presentan como un
servicio OpenAI ya operativo**. El generador determinista actual se conserva.

## Ejecutar el entorno y la validación

Usar requisitos y certificado de [README](README.md). Desde la raíz, secuencialmente:

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
python3 integration/run.py up
```

`up` sirve `https://127.0.0.1:8443/`, cuenta `operador-prueba` /
`solo-datos-sinteticos`. Ctrl+C retira contenedores y PostgreSQL tmpfs. No ejecutar
comandos simultáneos sobre el mismo proyecto. No publica puertos cloud.
Desde `frontend`, ejecutar `npm run typecheck`, `npm run build` y `npm test`.

## Limitaciones y revisión pendiente

- No se verificó ningún sitio ni documento auténtico. Los ensayos no certifican
  veracidad alimentaria, permisos, fabricante, formulación o certificaciones.
- No hay activación de Internet, runtime con egress ni integración del adaptador
  en el recolector. No basta con editar el JSON o una variable de entorno.
- La fijación DNS/TLS y el códec se probaron con dobles y TLS en memoria, sin
  servidores externos. Hace falta una validación posterior del camino de red
  autorizado y la transferencia íntegra al entorno aislado.
- No hay OCR, ejecución JS, formatos Office, imágenes/vídeos descargados, búsqueda
  web, traducción de maquetaciones complejas ni extracción nutricional inferida.
- URLs con query/escapes, portales con login/CDN no autorizado o HTML activo
  requieren otra fuente autorizada o exportación manual, sin relajar controles.
- Los límites de peticiones y auditoría son por instancia; un futuro servicio debe
  conservarlos por autorización y evitar el reinicio de instancias como reintento.
- No se implementó un proveedor IA ni un sistema de cobro. Retención duradera,
  roles de revisión y política de datos reales requieren revisión antes del piloto.

Sin push, PR, merge, despliegue, Render, cambios de credenciales, publicaciones,
sincronizaciones, operaciones productivas ni integración de PR #87.

## Archivos de la etapa

- Conector y autorización: `backend/integration_sandbox/https_connector.py`,
  `pilot_policy.py`; `integration/pilot-authorization.example.json` y
  `validate_pilot.py`.
- Contrato IA de sólo lectura: `backend/integration_sandbox/generation_contract.py`;
  registro de rutas en `proposal_routes.py`, `assisted_routes.py` y `policy.py`.
- Procedencia y lectura existente: `document_routes.py`, `local_documents.py`,
  `research/service.py`, dentro de `backend/integration_sandbox`.
- Pruebas backend: `backend/integration_sandbox/connector_checks.py` y `pilot_checks.py`.
- Dashboard: `frontend/src/integration/PilotReadiness.tsx`, `GenerationReadiness.tsx`,
  `AssistedResearch.tsx`, `DocumentImport.tsx`, `ProposalPanel.tsx`,
  `research-adapter.ts` e `isolation.ts`.
- Navegador: `frontend/integration-tests/zzzzpilot.spec.ts` y
  `frontend/playwright.integration.config.ts`.
- Harness: `integration/run.py`, `gateway.py`.
- Documentación: este archivo, `integration/README.md`, `ASSISTED.md` y
  `frontend/PROTOTYPE.md`.
- Seis capturas nuevas: `frontend/artifacts/piloto-{preparacion,documento,contrato-ia}-{desktop,mobile}.png`.

| Captura | Escritorio | Celular |
| --- | --- | --- |
| Estado del piloto y bloqueos | [Ver](../frontend/artifacts/piloto-preparacion-desktop.png) | [Ver](../frontend/artifacts/piloto-preparacion-mobile.png) |
| Procedencia y original | [Ver](../frontend/artifacts/piloto-documento-desktop.png) | [Ver](../frontend/artifacts/piloto-documento-mobile.png) |
| Contrato de hechos para IA | [Ver](../frontend/artifacts/piloto-contrato-ia-desktop.png) | [Ver](../frontend/artifacts/piloto-contrato-ia-mobile.png) |

## Validación ejecutada

| Comprobación | Resultado |
| --- | --- |
| Build de imagen y frontend de integración | Aprobado |
| Backend, PostgreSQL descartable, parser/recolector y gateway | 110 aprobadas: 90 anteriores y 20 nuevas (15 del conector, 5 del piloto) |
| Backend existente dentro del contenedor aislado | 484 aprobadas; dos advertencias previas de plugins de pytest |
| Playwright integración completo, escritorio y celular | 94 aprobadas: 88 anteriores y 6 nuevas |
| Playwright demo | 46 aprobadas |
| TypeScript y build demo | Aprobados; aviso previo de tamaño de bundle conservado |
| Ruff y formato Python | Aprobados, 39 archivos |
| Prettier y espacios Git | Aprobados |
| Validación offline del manifiesto vacío | Aprobada; 0 productos, 0 dominios y red desactivada |

Las pruebas incluyen TLS real en MemoryBIO sin sockets, certificado no confiable,
hostname incorrecto, conexión por IP fijada con SNI, DNS privado/mixto/rebinding,
redirecciones, cabeceras ambiguas, compresión, límites, truncamiento, MIME/firma,
rechazo de activación por entorno/API y ausencia de datos sensibles en errores.
Se conservan los originales y citas, versiones y controles de concurrencia reales
sobre PostgreSQL descartable; las dos decisiones sobre una base producen 200/409.
El contrato de IA excluye datos no aprobados, identidades incompatibles y
contradicciones, conserva citas/hashes y cambia al cambiar la versión de ficha.

La primera pasada de navegador detectó esperas locales insuficientes, recargas
repetidas de documentos, un doble HTTP sin la cabecera de aislamiento y la
conversión de una fecha declarada al día anterior. Se corrigieron la espera
local/pruebas, las referencias ORM, el doble y la presentación de la fecha,
sin cambiar plazos externos, reglas de evidencia ni integraciones productivas.
No se redujeron escenarios ni se añadieron reintentos automáticos.

Documentación auténtica: **no disponible y no ensayada**. Ningún resultado
sintético se contabiliza como validación de una fuente oficial auténtica.

Las seis capturas se revisaron visualmente en escritorio y celular. El demo
conserva sus rutas y guardas; ninguna integración productiva, credencial,
configuración de Render ni workflow difiere de la base 2H.

Tras reforzar el cierre público del transporte se reconstruyó la imagen y se
repitieron las 110 pruebas del backend: todas aprobadas. Los cuatro contenedores
y el volumen de socket quedaron retirados; no quedó una base de integración activa.
