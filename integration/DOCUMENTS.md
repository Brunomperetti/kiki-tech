# Etapa 2G — Documentación local y revisión de procedencia

La [etapa 2H](ASSISTED.md) amplía este lector con nutrientes y respaldo de
certificaciones, y agrega un recolector independiente exclusivamente simulado.
Los resultados y límites descritos abajo corresponden a la entrega histórica 2G.

Base verificada: `feature/kiki-tech-2-dashboard`, HEAD
`1dfb12cc5fcb71e530951d2b99a4924a649240e8`, árbol limpio antes de modificar.

## Alcance y recorrido

En Evidencias del mismo panel lateral se incorporan PDF con texto, TXT UTF-8,
HTML pasivo o JSON estructurado. Se admite documentación real que el operador
suministre y autorice expresamente **por cada incorporación**, sin enviarla a
proveedores. No se suministraron documentos reales del cliente durante esta etapa;
todas las pruebas y archivos incluidos en Git son sintéticos.

El catálogo sigue siendo el de seis variantes sintéticas. Incorporar un documento
real no convierte ese catálogo en productivo ni autoriza integrar datos reales.
Las diferencias con la variante seleccionada bloquean el uso de los datos.

Recorrido completo:

1. Abrir una variante, Evidencias e «Incorporar archivo local o referencia oficial».
2. Elegir archivo, registrar cómo se obtuvo, URL opcional y autorización local.
3. Inspeccionar texto extraído, ubicaciones e incompatibilidades. No se aprueba nada.
4. Registrar separadamente la revisión de procedencia con motivo.
5. Extraer los hechos de esa versión y revisar/aprobar cada dato con su cita.
6. En IA generar la propuesta determinista existente, aceptar campos individuales
   y guardar por el editor versionado. No hay OpenAI ni reemplazos automáticos.
7. Recargar, consultar historial/original, reemplazar documentos o revocar decisiones.

Una URL es sólo una referencia reproducible. No se descarga, visita, previsualiza
ni utiliza como fuente de hechos. Tampoco hay scraping, OCR o investigación web.

## Arquitectura y aislamiento

```text
dashboard único HTTPS local
  -> gateway con métodos/rutas cerrados
  -> FastAPI de pruebas, autenticación y CSRF existentes
      -> socket Unix PostgreSQL descartable (catálogo/editor/evidencias/propuestas)
      -> socket Unix fijo del lector documental, sin URL configurable
          -> hijo descartable por archivo: pypdf o lectores locales de texto
```

El lector es un tercer servicio interno del mismo proyecto Docker, sin frontend,
base de datos ni servicios comerciales propios. Usa la misma imagen de pruebas
y una dependencia exclusiva del harness, **pypdf 7.0.0**. No se modifica ningún
requisito productivo ni archivo en `backend/app`.

Los tres contenedores mantienen `network_mode:none`, raíz de sólo lectura y
`no-new-privileges`. El lector tiene UID 1000, capacidades eliminadas, 384 MiB,
1 CPU y 16 procesos como límites de contenedor. Sólo monta el directorio del socket;
no monta PostgreSQL, el socket API, Docker, `.env` ni credenciales.

Cada entrada se procesa en un hijo separado con 192 MiB de espacio de direcciones,
4 segundos de CPU (5 de límite duro), alarma de 8 segundos, máximo 32 descriptores
y cero bytes permitidos para escribir archivos regulares. El padre sólo acepta y
crea hijos; no interpreta documentos. Como máximo hay dos hijos simultáneos.
El hijo bloquea conexiones, DNS, subprocesses y nuevos forks mediante auditoría,
además del bloqueo de red del kernel. No se ejecuta código del documento.

El backend conserva sus bloqueos anteriores. Se agrega únicamente un destino Unix
fijo para el lector; no se habilitan procesos, TCP o DNS en FastAPI. El gateway
sigue pudiendo conectar exclusivamente al socket API, no al del lector. El arranque
comprueba ahora los tres contenedores y los límites del lector. El preflight de
PostgreSQL anterior al engine y al DDL permanece intacto.

## Límites y tipos seguros

- Archivo original: hasta **512 KiB**. Solicitud al lector: hasta 750.000 bytes;
  cuerpo HTTP máximo de 1 MiB. Se comprueba extensión, MIME y formato real.
- Nombres: hasta 120 caracteres, letras/números y espacios/puntos/guiones. Se
  rechazan rutas, `..`, archivos ocultos y controles; nunca se usan como rutas.
- PDF: máximo 10 páginas, 3.000 entradas de referencias, profundidad/objetos
  limitados, streams decodificados de hasta 1 MiB y trabajo agregado acotado.
  Se acepta texto/FlateDecode; las imágenes se conservan opacas, sin decodificarlas.
  Se rechazan cifrado, acciones, enlaces activos, JavaScript y adjuntos accesibles.
- Texto: hasta 65.536 caracteres, 1.000 fragmentos y 2.000 caracteres por fragmento;
  controles inseguros o bidireccionales se rechazan también en texto extraído de PDF.
- HTML: sólo etiquetas pasivas conocidas, sin atributos, scripts, estilos,
  imágenes, enlaces o recursos; 2.000 etiquetas y profundidad 32 como máximos.
  Se usa HTMLParser, nunca un navegador o motor que cargue recursos.
- JSON: objeto plano de hasta 40 claves; valores textuales o `{valor, unidad}`
  textuales. No se aceptan objetos arbitrarios anidados, arrays ni código.
- Hasta 10 documentos locales por variante y 8 versiones por documento para este
  prototipo. Son límites explícitos; no se presenta como procesamiento masivo.

El texto se muestra como nodos escapados de React. No se renderiza HTML original
ni se abre el PDF en un iframe. Los originales se consultan autenticados como
JSON/base64, nunca como contenido ejecutable. Se conserva el bloqueo de recursos
multimedia externos del editor y del modo demo.

## Extracción y datos faltantes

El extractor es determinista y conservador, sin IA. Reconoce etiquetas explícitas
`Nombre`, `Marca`, `Fabricante`, `EAN`, `Presentación`, `Tipo de venta`,
`Ingredientes`, `Alérgenos`, `Energía`, `Proteínas`, `Contenido neto`,
`Características`, `Conservación`, `Formulación`, `Declaración comercial`,
`Categoría` y `Subcategoría`, con algunos alias explícitos. No interpreta cualquier
tabla o documento libre como si comprendiera su contenido.

En PDF/TXT/HTML se reconocen líneas `Etiqueta: valor`. En JSON se usan claves
equivalentes; los nutrientes/pesos admiten `{valor,unidad}`. Ubicaciones:
`pagina/1/linea/3`, `texto/linea/3`, `html/linea/3/bloque/2` o `json/Ingredientes`.
Las líneas son las del texto extraído, no coordenadas gráficas del PDF. JSON y HTML
usan una representación textual normalizada, reproducible desde el original.
La identidad conserva también `identity_evidence`: valor, cita y ubicación para
nombre, marca, fabricante, EAN, presentación y tipo de venta. Se consulta en el panel
como referencia extraída sin aprobación automática.

No se reescriben pesos ni se infieren ingredientes, unidades, certificaciones,
packs o formulaciones. Las etiquetas duplicadas con valores distintos se omiten
y bloquean la revisión por ambigüedad. Datos desconocidos quedan vacíos. Un PDF sin
texto accesible se conserva con `NEEDS_OCR`, sin hechos ni extracción exitosa fingida.
En presentaciones simples de unidad se compara además contenido neto con cantidad
declarada (g/kg o ml/l), sin alterar el dato original ni extrapolar contenido de packs.
Un documento legible sin etiquetas suficientes queda `INSUFFICIENT_DATA`.

Ejemplo de TXT sintético (equivalente al PDF incluido para pruebas):

```text
Nombre: Semillas de chía sintéticas
Marca: Marca sintética KIKI
Fabricante: Fabricante de prueba
EAN: 12345670
Presentación: 250 g
Tipo de venta: Unidad
Ingredientes: Semillas de chía
Energía: 600 kcal/100 g
Conservación: Mantener en lugar fresco y seco
```

Esos valores son inventados para probar el flujo, no información nutricional real.

## Identidad y cuatro estados distintos

El documento se asocia explícitamente al **Ecomm ID** de la ruta. No aparece en el
expediente de otra variante y no puede extraerse o recuperarse desde otro ID.
EAN, nombre, marca, fabricante y presentación se contrastan con las referencias
existentes; no sustituyen la identidad canónica. Unidad/pack debe estar explícito
y ser compatible con `is_combo`. Pesos/presentaciones incompatibles bloquean.
Formulaciones e ingredientes contradictorios entre documentos mantienen los
controles de conflictos de 2E. Sin una referencia de formulación no se certifica
automáticamente equivalencia: se requiere revisión humana de los datos y sus fuentes.

Los estados permanecen separados:

1. **Declarada oficial**: manifestación del operador, no autenticación.
2. **Procedencia revisada**: decisión humana motivada, con responsable, fecha y versión.
3. **Dato extraído pendiente**: transcripción local sin aprobación.
4. **Dato aprobado vigente**: revisión individual con respaldo, identidad y fuente vigentes.

Ni el nombre, URL, hash, formato PDF ni la revisión de procedencia aprueban hechos.
Los documentos locales requieren procedencia REVIEWED antes de aprobar datos.
Rechazar/revocar la procedencia o reemplazar el documento invalida la evidencia.
Revisar otra vez una fuente nunca restaura automáticamente sus aprobaciones.

## Persistencia y contratos reutilizados

No hay tablas ni migraciones nuevas. Se reutilizan `Document`, `Dossier`, control
transaccional e historial del esquema aislado `kiki_research_test`. El original
queda como base64 junto con SHA-256, nombre, MIME y tamaño, o como URL reproducible.
Cada versión conserva cuerpo anterior, original, hash, motivo/acción, autor y fecha.
Las respuestas normales omiten los bytes originales y muestran sólo metadatos.

El reemplazo y revisión de procedencia usan el mutex y versiones existentes; dos
escrituras sobre la misma base no se sobrescriben. El hash del cuerpo incluye la
procedencia, además del contenido. Los hechos ligados a versiones anteriores pasan
a STALE y las propuestas 2F se invalidan antes de cualquier aplicación.

Se reutilizan la extracción/revisión por hecho de `/api/test-research`, el generador
de `/api/test-proposals`, `KikiAiEditorialDraft`, las validaciones y guardado de
`POST /api/ecomm-app/workspace/{ecomm_id}`, sus 18 campos, CSRF, CAS e historial.
Conservación, características y formulación aprobadas alimentan detalles/atributos;
no se aplican automáticamente. Las banderas distinguen entorno `isolated_only:true`
de datos `synthetic_only`; un archivo suministrado no se rotula como fixture sintético.

| Contrato nuevo, sólo harness | Cuerpo/resultado |
| --- | --- |
| POST `/api/test-documents/{id}/import` | `kind:FILE\|URL`, `expected_version`, nombre/MIME/base64 o URL, nota de procedencia, declaración oficial y autorización local obligatoria; devuelve expediente y `incorporated_document_id` |
| Mismo POST para reemplazar | Agrega `document_id` y `expected_document_version`; conserva originales/versiones |
| POST `/api/test-documents/{id}/{doc}/provenance` | `expected_document_version`, `decision:REVIEWED\|REJECTED\|REVOKED`, `reason`; devuelve expediente |
| GET `/api/test-documents/{id}/{doc}/original/{version}` | Original base64 y metadatos/URL reproducible; sesión obligatoria |

POST exige autenticación y CSRF; claves extra o autorización ausente/falsa se
rechazan. Todos los contratos limitan IDs a los seis fixtures y documentos locales
asociados. No existe endpoint de descargar URL ni parámetro de destino del lector.

## Inicio

Usar los mismos requisitos Linux/WSL2, UID 1000, Docker y Node de etapas previas:

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
python3 integration/run.py up
```

En la máquina del entorno, abrir `https://127.0.0.1:8443/` y la cuenta sintética
existente. El build instala la dependencia exclusiva del lector. El script prepara
los directorios seguros de sockets y no consume `.env` ni overrides. No ejecutar
comandos simultáneos sobre el mismo proyecto. Ctrl+C retira los tres contenedores;
PostgreSQL tmpfs y originales desaparecen. `npm test` en frontend verifica el demo
sin backend. No se publica un puerto cloud ni se despliega un servicio.

## Límites pendientes

- No se probó documentación real de KIKI: no se adjuntó ninguna. El soporte es para
  archivos locales autorizados; su autenticidad no queda certificada por el sistema.
- PDFs cifrados, activos, codecs no admitidos, maquetaciones complejas, tablas sin
  etiquetas reconocibles o documentos con varios productos pueden requerir revisión
  y otro procesamiento. No hay OCR, visión, NLP general ni búsqueda de fabricantes.
- La identificación estructurada nutricional actual comprende energía y proteínas,
  con unidades reconocibles explícitas. Otros nutrientes se conservan en el texto
  original, sin presentarlos como hechos identificados o aprobados automáticamente.
- La igualdad de identidad es conservadora; no hay equivalencias semánticas ni
  conciliación automática de formulaciones. Referencias faltantes no se inventan.
- Originales e historial JSON están limitados y son descartables. Antes de un uso
  productivo hacen falta almacenamiento duradero privado, retención, permisos,
  análisis de seguridad y capacidad, versiones de parser y contrato/migración revisados.
- La revisión de procedencia es una declaración humana de la sesión de prueba,
  no validación legal de derechos, certificaciones, fabricante o información alimentaria.

Sin servicios reales, cambios en backend/integraciones productivos, OAuth, tokens,
credenciales, Render, OpenAI, PR #87, publicaciones, push, PR, merge o despliegues.

## Archivos de la etapa

- Lector local: `backend/integration_sandbox/document_parser.py`,
  `document_worker.py` y `requirements-documents.txt`.
- API/servicios de pruebas: `document_routes.py`, `local_documents.py`,
  `bootstrap.py`, `policy.py`, `proposals.py`, `research/service.py` y
  `research/documents.py`, dentro de `backend/integration_sandbox`.
- Pruebas backend y archivos sintéticos: `document_checks.py`,
  `document_test_fixtures.py` y `frontend/integration-fixtures/*`.
- `.gitattributes` conserva los bytes de los PDF de prueba sin normalizar sus líneas.
- Panel lateral: `frontend/src/integration/DocumentImport.tsx`, `ResearchPanel.tsx`,
  `research-adapter.ts`, `ProposalPanel.tsx`, `proposal-adapter.ts`,
  `catalog-adapter.ts`, `isolation.ts` y `research.css`.
- Espacio de trabajo: `frontend/src/integration/IntegrationCatalog.tsx` aclara el
  alcance actual del catálogo y documentos, sustituyendo el aviso anterior de sólo lectura.
- Playwright: `frontend/integration-tests/zzdocuments.spec.ts`,
  `research.spec.ts` (etiqueta accesible y tiempo del recorrido completo) y
  `zproposals.spec.ts` (tiempo del recorrido completo).
- Harness: `integration/Dockerfile`, `compose.yaml`, `gateway.py` y `run.py`.
- Documentación: este archivo, `integration/README.md`, `RESEARCH.md`,
  `PROPOSALS.md` y `frontend/PROTOTYPE.md`.
- Seis capturas nuevas: `frontend/artifacts/documento-{local,propuesta,sin-texto}-{desktop,mobile}.png`.

## Validación ejecutada

| Comprobación | Resultado |
| --- | --- |
| `python3 integration/run.py test` | 76 aprobadas: 61 anteriores y 15 de documentos, con PostgreSQL y lector aislados reales |
| `python3 integration/run.py legacy-test` | 484 aprobadas; 2 advertencias previas de plugins de pytest |
| `python3 integration/run.py browser-test` | 78 aprobadas: 70 anteriores y 8 documentales, escritorio y celular |
| Comprobación focalizada tras cerrar la trazabilidad | 15 backend y 8 Playwright aprobadas, incluyendo ubicación del EAN e integridad del original |
| Playwright demo (`npm test`) | 46 aprobadas |
| TypeScript y builds demo/integración | Aprobados; advertencia habitual de tamaño del bundle demo |
| Ruff, formato Python y espacios de Git | Aprobados |

Se probaron PDF con texto/comprimido, imagen sin texto, documentación insuficiente,
JSON/HTML pasivos, discrepancias de EAN/presentación/pack, peso interno incompatible,
unidades nutricionales faltantes, formulaciones contradictorias, procedencia ausente,
reemplazo y revocación, originales históricos, generación/guardado/recarga e historial.
Dos operadores reemplazando la misma base obtuvieron 200 y 409, sin sobrescritura.

Los casos de seguridad cubren nombres/rutas, tamaño, MIME/firma, cifrado, contenido
activo, complejidad/páginas, expansión excesiva, HTML con recursos y JSON no admitido.
Se verificaron autenticación/CSRF y los bloqueos de red/procesos del lector. Playwright
vigila solicitudes fuera del origen local y comprueba que la referencia URL no se visita.

«Comprobar original» calcula SHA-256 sobre los bytes recuperados (o la URL registrada),
además de comparar ID, versión y tamaño. Una respuesta con bytes alterados pero el
hash declarado intacto fue rechazada en la prueba de navegador; luego se recuperó
correctamente el original real de la base de pruebas.

Capturas: [documento en escritorio](../frontend/artifacts/documento-local-desktop.png),
[documento en celular](../frontend/artifacts/documento-local-mobile.png),
[ficha guardada](../frontend/artifacts/documento-propuesta-desktop.png) y
[PDF sin texto](../frontend/artifacts/documento-sin-texto-mobile.png).

No hay diferencias en `backend/app`, integraciones productivas, entrada/configuración
del demo, Render ni workflows respecto a la base 2F. El modo demo conserva su aislamiento.
