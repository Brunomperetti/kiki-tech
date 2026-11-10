# Etapa 2J — Piloto comercial MAMA 350 g / 10 mm

Base comprobada antes de modificar: `feature/kiki-tech-2-dashboard`,
`ac3062d5d81b84bfe953eea8a2b3dfb4f7da1722`, árbol limpio.

## Resultado comercial y alcance de la evidencia

**Expediente preparado; propuesta comercial bloqueada por falta de documentos
auténticos específicos.** No se suministró `productos.xlsx` ni una copia del
catálogo, etiqueta o ficha técnica al entorno. Se conserva la transcripción del
mensaje del usuario, sin afirmar lectura independiente del Excel ni del sitio.
No se descargó la URL y no se agregó el dominio a ninguna lista de acceso real.

Identificador local: **`PILOT-MAMA-350-SYNTHETIC`**. Es un identificador de pruebas,
no un Ecomm ID auténtico. Vinculación real: **pendiente**. El SKU del archivo no
se utiliza como clave, coincidencia automática ni dato capturado de Ecomm-App.

El Excel es una referencia auxiliar. El catálogo de integración conserva sus seis
variantes inventadas, sus páginas e indicadores; el piloto abre el panel existente
desde una entrada diferenciada en el mismo dashboard, fuera de esa tabla.
El catálogo maestro y las integraciones productivas permanecen intactos.

## 1. Ficha inicial y procedencia

| Dato informado | Valor | Qué acredita esta etapa |
| --- | --- | --- |
| Archivo/fila | `productos.xlsx`, fila 37 | Referencia comunicada por el usuario, sin archivo original disponible |
| Nombre | Fideos De Arroz Mama 10mm 350g | Identificación declarada por el cliente |
| Marca | Mama | Marca declarada, pendiente de contraste documental |
| EAN declarado | `8851876201433` | Checksum matemáticamente válido; no prueba correspondencia oficial |
| SKU del archivo | `fideos 10mm Mama` | Referencia auxiliar; nunca identidad ni vínculo |
| Presentación declarada | 350 g | Declaración del cliente, no contenido neto oficialmente verificado |
| Ancho declarado | 10 mm | Parte de la identificación, pendiente de documento específico |
| Peso logístico | 0,4 kg | No se usa como contenido neto |
| Descripción comercial / título SEO / descripción SEO | Vacíos | Se conservan sin completar |
| Ecomm ID auténtico | Desconocido | No inventado ni vinculado por parecido |

El registro conserva `USER_TRANSCRIPTION_ONLY`, fila, origen, datos declarados y
`original_file_sha256:null`. El hash del **registro de referencia** sólo protege
ese JSON; no se presenta como hash del Excel ni de un documento del fabricante.

Los 18 campos del editor se mantienen. Su superposición comercial comienza vacía:
no se importa el Excel ni se aprueban automáticamente nombre, marca o presentación.
La identificación declarada se muestra separada de los campos editables KIKI.

## 2. Referencia oficial candidata y límites

Fabricante candidato informado: **Thai President Foods**.

URL comunicada por el usuario:
`https://www.mama.co.th/en/products-export-brand-list/21/34/Instant-Rice-Vermicelli`

Ítem referido: **Mama Rice Noodles 350g (10 Mm.)**.

El expediente distingue esta referencia de los datos atribuidos al Excel. Se
registra mediante el contrato URL de 2G, con procedencia pendiente, cero bytes,
sin descarga ni extracción. La fecha de consulta y el hash de un documento son
nulos porque no hubo consulta ni copia. El hash técnico de la referencia URL
reproducible no es un hash de contenido del sitio.

No se acreditan por esta URL: EAN, ingredientes, alérgenos, nutrientes, contenido
neto documentado, certificaciones o ausencia de gluten. La presencia del nombre
del fabricante o un nombre comercial coincidente no verifica esos datos.

## 3. Qué puede registrarse y qué debe bloquearse

| Información | Estado actual / decisión |
| --- | --- |
| Datos comunicados por el cliente y fuente atribuida | Registrados con procedencia declarada, sin aprobación comercial automática |
| Validez matemática del EAN | Comprobada localmente; se separa de la correspondencia con el envase |
| Nombre del ítem y URL candidata | Registrados como referencia suministrada, no como contenido consultado |
| Correspondencia EAN / marca / fabricante / 10 mm / 350 g | Pendiente de copia auténtica específica y revisión humana |
| Ingredientes, alérgenos y nutrientes | Bloqueados por ausencia de respaldo |
| «Sin gluten», orgánico y otras certificaciones | Bloqueados; no inferidos del arroz o de la marca |
| Categoría y subcategoría | Sin asignación automática; requieren clasificación justificada y trazada |
| Publicación y cobertura por canal | No inferidas ni ejecutadas |
| Vinculación al maestro Ecomm-App | Pendiente de ID auténtico y evidencia autorizada del maestro |

No hay hechos aprobados al preparar el expediente. Intentar extraer la referencia
URL o generar la propuesta devuelve un bloqueo explicativo; no crea un borrador
IA vacío que pueda confundirse con una propuesta respaldada. También se rechaza
usar fixtures sintéticos de otros productos como documentos del piloto.

## 4. Propuesta y comparación antes/después

**No se obtuvo una propuesta comercial aprobable.** La validación exige mantener
el bloqueo; no se sustituye documentación ausente por textos comerciales ficticios.

| Campo comercial | Inicial | Después del recorrido sin documentación |
| --- | --- | --- |
| Título comercial | Sin completar | Sin completar / sin propuesta respaldada |
| Descripción corta | Sin completar | Sin completar / sin propuesta respaldada |
| Descripción larga | Sin completar | Sin completar / sin propuesta respaldada |
| Características | Sin completar | Sin completar / sin propuesta respaldada |
| Presentación editorial | Sin completar | La declaración de 350 g está en la referencia; no se aprueba automáticamente |
| Categoría / subcategoría | Sin completar | Sin completar / sin clasificación justificada |
| Título / descripción SEO | Sin completar | Sin completar / sin propuesta respaldada |
| Nota de seguimiento | Vacía | Guardada y recuperada desde PostgreSQL de pruebas |

La nota del recorrido probado expresa que falta documento auténtico con EAN,
ancho 10 mm, contenido neto 350 g y vinculación Ecomm-App. Es seguimiento operativo,
no una descripción comercial del producto. El panel permite comparar el estado
inicial con el guardado y consultar el historial del editor existente.

Cuando existan hechos aprobados suficientes, se reutilizarán las propuestas 2F:
títulos/SEO requieren nombre y presentación; descripciones y características,
hechos respaldados; categorías, hechos de clasificación justificados. Cada campo
mantendrá sus IDs de evidencia, citas, versiones y revisión antes de guardar.
La ausencia de un grupo de evidencias debe producir una propuesta parcial con
campos faltantes explícitos, sin completar atributos por conocimiento general.

## 5. Arquitectura reutilizada

- Se reutilizan `Dossier`, `Document`, control transaccional e historial 2E. Los
  datos declarados se conservan en un evento versionado del expediente, separados
  del documento URL. No hay tablas ni migraciones nuevas.
- Una subclase exclusiva del harness aporta `_source` para **un único ID de pruebas**
  y delega persistencia, normalización, CAS, historial y los 18 campos al servicio
  de editor existente. No agrega registros a `CatalogSnapshot`, no cambia la API
  Ecomm-App ni sustituye el catálogo por el Excel.
- Los contratos GET/POST de workspace, documentos 2G, propuestas 2F y contexto
  aprobado 2I se reutilizan. Sólo se amplía la lista cerrada a ese ID sintético;
  no se habilitan IDs auténticos arbitrarios.
- El piloto admite sólo estado DRAFT mientras el Ecomm ID real está pendiente.
  No se habilitan aprobaciones de canal, lotes, sincronizaciones o publicaciones.
- La acción Investigar producto abre Evidencias en el mismo panel. Para este
  expediente no inicia el descubrimiento simulado 2H ni devuelve fabricantes
  inventados. El recolector real sigue apagado y sin acceso a nuevos dominios.
- Se añade el campo documental explícito `Ancho`, con valor/unidad/cita/ubicación.
  No se interpreta cualquier número del texto como ancho del fideo.

Rutas nuevas, sólo harness, con autenticación:

| Ruta | Efecto |
| --- | --- |
| GET `/api/test-commercial-pilot/mama-350` | Lee disponibilidad, referencias, estado inicial/actual y faltantes |
| POST `/api/test-commercial-pilot/mama-350/prepare` | Cuerpo `{}`, CSRF obligatorio; prepara idempotentemente el expediente y la referencia URL |

No existe endpoint de asignación automática del Ecomm ID. Claves extra al preparar
se rechazan; endpoints de vinculación, proveedores y descubrimiento para el piloto
no están autorizados. Todas las escrituras son a PostgreSQL descartable.

## 6. Incorporar posteriormente una copia auténtica

1. Obtener del usuario una copia auténtica y autorización explícita de uso local.
   No activar el recolector ni descargar la URL. La fuente debe permitir contrastar
   exactamente marca, EAN, ancho y contenido neto de esta presentación.
2. Abrir el expediente MAMA → Investigar producto → Evidencias → Incorporar archivo
   local. Reutilizar el lector 2G: PDF con texto, TXT UTF-8, HTML pasivo o JSON;
   hasta 512 KiB y 10 páginas PDF. XLSX no es un formato del lector documental.
3. Registrar quién suministró el documento, cómo lo obtuvo, fabricante declarado,
   URL de procedencia cuando se conozca y fecha informada. Declarar oficial no
   verifica procedencia. Preservar original y SHA-256 antes de extraer o aprobar.
4. Revisar la extracción y citas. Se reconocen etiquetas explícitas: Nombre, Marca,
   Fabricante, EAN, Presentación, Tipo de venta, Ancho y Contenido neto, además de
   los campos técnicos existentes. Documentos libres, escaneados o con maquetación
   no admitida requieren otro procesamiento/revisión; no reescribir el original
   para hacer pasar una incompatibilidad.
5. Contrastar las dos denominaciones informadas. Admitir una denominación no
   basta: deben estar documentados EAN, Mama, fabricante, 10 mm y 350 g, con tipo
   de venta explícito. `0,35 kg` puede contrastarse con 350 g; `0,4 kg` no.
   Un ancho distinto, datos ausentes o identidad incompatible bloquean la aprobación.
6. Registrar la revisión humana de procedencia; después extraer y revisar cada
   hecho. Incompatibilidades o contradicciones no se resuelven por semejanza de
   SKU ni por validez matemática del EAN. No omitir certificaciones o alérgenos
   pendientes para declarar la ficha completa.
7. Categorías deben tener una clasificación interna aprobada y trazable, separada
   de afirmaciones del fabricante; no se generan por intuición. Sin evidencia
   suficiente, registrar el campo pendiente.
8. Generar propuesta 2F sólo desde hechos aprobados vigentes, revisar cada campo,
   comparar con la ficha inicial y guardar mediante el editor 2D con CSRF y
   `expected_version`. Recargar, consultar historial y comprobar el original.

## 7. Incorporar el Ecomm ID auténtico sin falsificar el historial

Esta entrega no ejecuta el vínculo y no ofrece un campo para cambiar la clave.
El procedimiento posterior requiere nueva revisión/autorización de alcance:

1. Recibir una referencia autorizada de **una variante del maestro Ecomm-App**, con
   ID auténtico, producto, presentación, SKU, EAN cuando exista, tipo de venta,
   fecha/versión y procedencia. No consultar APIs productivas en esta etapa ni
   obtenerlo del SKU del Excel.
2. Comparar esa variante con la documentación auténtica: marca/fabricante, EAN,
   ancho 10 mm, contenido neto 350 g y unidad/pack. Si el maestro carece de algún
   campo, registrarlo como desconocido y exigir evidencia adicional. No fusionar
   variantes ni asumir que el nombre basta.
3. Autorizar expresamente el ID y la referencia local del maestro para la base
   descartable. El harness actual rechaza cualquier ID fuera de sus seis fixtures
   y el alias; ampliar ese alcance exige un cambio revisado con pruebas.
4. Registrar una decisión de vinculación motivada: operador, fecha, fuente/hash del
   maestro, ID candidato y versión del expediente. Conservar el ID sintético y
   sus referencias como historia de pruebas. **No hacer UPDATE de la clave primaria
   para que el alias parezca un Ecomm ID real.**
5. Abrir un expediente/overlay para el ID auténtico mediante los servicios
   existentes. Asociar nuevamente originales autorizados con trazabilidad de su
   procedencia; reextraer y revisar los hechos bajo el nuevo hash de identidad.
   Las aprobaciones/propuestas del alias no se trasladan automáticamente.
6. Comparar la ficha existente del ID auténtico y sus versiones antes de aplicar
   campos revisados. Usar `expected_version`, revisión humana y conflicto 409;
   no sobrescribir silenciosamente ni modificar el maestro/API del proveedor.
7. Mantener el trabajo en pruebas, sin publicación/sincronización, hasta la
   autorización específica de una etapa posterior.

## 8. Inicio, límites y riesgos pendientes

Desde Linux/WSL2 con requisitos de [README](README.md), ejecutar secuencialmente:

```sh
python3 integration/run.py build
python3 integration/run.py up
```

Abrir `https://127.0.0.1:8443/`, usuario `operador-prueba`, contraseña de pruebas
`solo-datos-sinteticos`. Usar «Abrir expediente MAMA de pruebas». El POST prepara
el expediente explícitamente; no se incorpora en el arranque ni en la tabla del
catálogo. Una recarga conserva URL, ficha y notas durante la vida de PostgreSQL.

Ctrl+C retira contenedores; la base usa tmpfs y es descartable. Al iniciar otra
base, preparar de nuevo el expediente. No prometer almacenamiento duradero ni
pérdida cero de documentos auténticos sin una política de conservación revisada.

Pendientes reales: Excel original no recibido, copia auténtica del fabricante no
recibida, correspondencia oficial del EAN sin comprobar, fabricante/presentación
sin documento específico, categorías sin justificación y Ecomm ID desconocido.
El lector no tiene OCR ni reconocimiento semántico general; variantes de nombre
legal del fabricante o información ambigua requieren revisión, no normalización
silenciosa. El piloto sigue sin tráfico de fabricantes, OpenAI o proveedores.

No se modifican `backend/app`, integraciones productivas, OAuth, credenciales,
PostgreSQL productivo, Render, modo demo ni PR #87. Sin push, PR, merge o despliegue.

## Archivos de la etapa

- Referencias y operación del piloto: `backend/integration_sandbox/mama_reference.py`,
  `mama_routes.py` y `mama_checks.py`.
- Adaptación local de origen, sin otro editor: `backend/integration_sandbox/workspace.py`.
- Contratos existentes del harness: `bootstrap.py`, `policy.py`, `proposal_routes.py`,
  `proposals.py`, `assisted_research.py`, `document_parser.py`,
  `research/service.py` y `research/documents.py`, dentro del mismo directorio.
- Dashboard: `frontend/src/integration/MamaPilot.tsx`, `mama-pilot.ts`,
  `IntegrationCatalog.tsx`, `PersistentWorkspace.tsx`, `ResearchPanel.tsx`,
  `ProposalPanel.tsx`, `catalog-adapter.ts` e `isolation.ts`.
- Playwright: `frontend/integration-tests/zzzzzmama.spec.ts`.
- Ejecución y documentación: `integration/run.py`, `README.md`, este archivo y
  `frontend/PROTOTYPE.md`.
- Seis capturas nuevas: `frontend/artifacts/mama-{inicial,evidencia,bloqueo}-{desktop,mobile}.png`.

| Captura | Escritorio | Celular |
| --- | --- | --- |
| Ficha inicial y procedencia | [Ver](../frontend/artifacts/mama-inicial-desktop.png) | [Ver](../frontend/artifacts/mama-inicial-mobile.png) |
| Referencia sin documento descargado | [Ver](../frontend/artifacts/mama-evidencia-desktop.png) | [Ver](../frontend/artifacts/mama-evidencia-mobile.png) |
| Propuesta bloqueada con motivo | [Ver](../frontend/artifacts/mama-bloqueo-desktop.png) | [Ver](../frontend/artifacts/mama-bloqueo-mobile.png) |

## Validación ejecutada

| Comprobación | Resultado |
| --- | --- |
| Backend, PostgreSQL descartable, aislamiento y gateway | 116 aprobadas: 110 anteriores y 6 nuevas del piloto |
| Backend existente | 484 aprobadas; dos advertencias previas de plugins de pytest |
| Playwright integración, escritorio y celular | 94 regresiones previas aprobadas y 6 casos MAMA aprobados tras la corrección focalizada |
| Playwright demo | 46 aprobadas |
| TypeScript y builds demo/integración | Aprobados; aviso previo de tamaño del bundle demo conservado |
| Ruff y formato Python | Aprobados, 43 archivos |
| Prettier y espacios Git | Aprobados |

Las pruebas del piloto comprueban referencias separadas, hash del archivo ausente,
checksum independiente de identidad, idempotencia, ausencia de cambios en la
captura del catálogo, contexto IA sin hechos, rechazo de generación sin respaldo,
originales, diferencias de EAN/marca/ancho/contenido neto, tipo de venta, notas
persistentes, comparación y concurrencia 200/409. No habilitan vinculación ni red.

Los archivos generados para pruebas de carga son **controles negativos sintéticos**,
rotulados como tales, nunca documentación auténtica ni propuesta comercial del
producto. No se inventan ingredientes, nutrientes o certificaciones en esos controles.
La comprobación estructural del lector no se contabiliza como una revisión de fabricante.

La primera pasada del backend detectó en una aserción nueva el uso de `total` en
lugar del campo real `total_variants_in_capture`. Se corrigió la prueba y se repitió
la suite. No se modificó el contrato de catálogo para acomodar esa aserción.

La suite completa de navegador aprobó las 94 regresiones anteriores y detectó
problemas en los casos nuevos: selección inicial apuntando a un fixture que no
pertenece al piloto, y preparación de prueba que intentaba vaciar un borrador.
Se corrigió la selección únicamente para el ID del piloto y se conservó la regla
del editor que exige al menos un dato u observación. Después se reconstruyó el
frontend y se repitieron los seis casos MAMA sobre FastAPI/PostgreSQL reales de
pruebas: todos aprobados. Son 100 escenarios únicos cubiertos, sin presentar la
primera pasada de 100 como una ejecución completamente aprobada.

Se revisaron visualmente las seis capturas. El recorrido prueba apertura,
referencias, bloqueo, carga manual disponible, guardado, recarga, comparación,
historial, URL y conservación de filtros, sin solicitudes fuera del origen local.
Los contenedores y la base descartable quedaron retirados al terminar.

Pendiente: ensayo con copia auténtica, porque no fue suministrada. El resultado
comercial de esta etapa es el bloqueo trazable y la preparación para revisión,
no una ficha MAMA completa supuestamente verificada.
