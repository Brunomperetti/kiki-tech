# Hileret 2K — Piloto con el PDF original adjunto

Base comprobada antes de modificar: `feature/kiki-tech-2-dashboard`,
`a95a897a4f5f1d82701d3fb32f61eb78f5686534`, árbol limpio.

## Documento y procedencia

Ahora sí se dispone de los bytes del documento suministrado por el usuario:

- Nombre recibido: `Folleto Ventas Hileret 17x25_400s.pdf`.
- Tamaño comprobado: **6.232.081 bytes**. PDF de **4 páginas**, no cifrado.
- SHA-256 calculado sobre el original completo:
  `bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291`.
- Copia idéntica para reproducir el piloto:
  [integration/fixtures/hileret-original.pdf](fixtures/hileret-original.pdf).
- Procedencia declarada por el usuario: descarga del dominio oficial Hileret,
  `https://descargas.hileret.com.ar/Hileret/Folleto%20Ventas%20Hileret%2017x25_400s.pdf`.
- Procedencia efectivamente revisada por Codex: archivo adjunto, integridad local,
  estructura PDF, contenido textual y contraste visual de página 2. **Codex no
  descargó el sitio ni verificó por red su copia actual.** No se inventa una fecha
  de consulta del fabricante; queda nula. El hash no certifica por sí solo origen
  oficial, vigencia, identidad Ecomm-App ni aprobación humana.

Se conserva el original entero sin recomprimirlo, recortarlo ni reescribirlo.
El render de inspección no reemplaza los bytes conservados en PostgreSQL.

## Evidencias extraídas del original

La página 2 incluye Zucra y Stevia. El perfil lee únicamente la tabla inferior
de Stevia y el rótulo del envase de 200 ml, mediante coordenadas de texto nativo.
No empareja filas a partir del orden de texto aplanado del PDF.

Coordenadas en puntos PDF, origen inferior izquierdo:

| Evidencia | Cita literal | Ubicación en página 2 |
| --- | --- | --- |
| Nombre, marca y cantidad logística | `Hileret Stevia 9 x 200 ml` | Tabla Stevia, fila líquido 200 ml, columna Producto; x31.99 / y41.31 |
| Presentación del envase individual | `200 ml` | Rótulo del envase; x438.57 / y152.97 |
| EAN individual | `7794940000796` | Misma fila, columna EAN; x142.57 / y41.32 |
| DUN logístico | `97794940000799` | Misma fila, columna DUN; x190.98 / y41.32 |
| Contexto de columnas | `Producto Familia EAN DUN Unidad por capa Número de capas Packs por pallet` | Cabeceras Stevia; x31.98 / y120.15 |

Se registran **7 hechos candidatos**, inicialmente pendientes: nombre `Hileret
Stevia`, marca `Hileret`, presentación `200 ml`, volumen de contenido `200 ml`, EAN,
cantidad logística `9` y DUN. Marca/nombre son fragmentos literales de la celda
Producto, no una razón social del fabricante. El campo histórico `net_weight`
admite unidad `ml`: aquí expresa volumen, nunca masa en gramos ni peso logístico.
Cada hecho conserva cita, localización, hash y versión del documento.

Se confirma **en este documento** la asociación de Hileret Stevia 200 ml al EAN
declarado. No se atribuyen a la unidad pesos de pallet, datos de Zucra, ingredientes,
información nutricional, certificaciones o beneficios de salud. Tampoco se extrae
el eslogan «Naturalmente dulce» para generar afirmaciones comerciales.

## Unidad, pack comercial y logística

| Registro | Resultado |
| --- | --- |
| Unidad, fila 28 del Excel informado | Expediente `PILOT-HILERET-200-UNIT-SYNTHETIC`; identidad documental compatible con Hileret Stevia 200 ml |
| Pack comercial x6, fila 27 informada | Expediente `PILOT-HILERET-200-PACK6-SYNTHETIC`; el original de unidad/caja x9 no respalda el pack x6, aunque el Excel repita EAN |
| Caja logística x9 del fabricante | Dato logístico separado, no tercer producto comercial ni pack x6 |
| DUN `97794940000799` | Hecho logístico; no se copia al EAN, título, atributos comerciales ni SEO de la unidad |

Los documentos se asocian por expediente, no por EAN. Importar la misma copia en
el pack permite observar el contraste incompatible; sus hechos no se pueden
aprobar. El DUN y la cantidad x9 quedan visibles como evidencia pero el generador
los excluye de la ficha comercial individual. Ambos Ecomm ID auténticos siguen
nulos. El Excel sigue siendo una referencia auxiliar, nunca catálogo operativo.

## Revisión, propuesta y antes/después

La importación no crea aprobaciones ni escribe campos comerciales. La extracción
crea hechos pendientes. Revisar la procedencia no aprueba los hechos: cada uno
necesita una decisión explícita, motivo y confirmación. Cambiar la procedencia
versiona el documento e invalida verificaciones anteriores, que requieren nueva
extracción/revisión.

**Las decisiones de las pruebas automatizadas simulan al operador de prueba.**
Sus motivos indican `RECORRIDO AUTOMATIZADO DE PRUEBA, no aprobación efectiva del
cliente`. Demuestran los controles de revisión, generación y guardado; **no se
presentan como aprobación humana efectiva de KIKI Market**. El operador real
puede reproducir el circuito y decidir individualmente desde el dashboard.

Propuesta limitada obtenida después de las decisiones explícitas de prueba:

| Campo | Antes de generar | Después de aceptar y guardar en pruebas |
| --- | --- | --- |
| Marca | Vacía | Hileret |
| Presentación | Vacía | 200 ml |
| Título, título corto y título SEO | Vacíos | Hileret Stevia · 200 ml |
| Descripción corta y descripción SEO | Vacías | Hileret Stevia · 200 ml. |
| Descripción larga | Vacía | Hileret Stevia · 200 ml. / Contenido neto: 200 ml. |
| Detalles y atributos | Vacíos | Contenido neto: 200 ml. |
| Fabricante legal, categoría/subcategoría | Sin respaldo | Permanecen sin completar |
| Palabras clave, imágenes y videos | Sin respaldo/recursos autorizados | Permanecen sin completar |
| Ingredientes, alérgenos, nutrición, certificaciones y beneficios | Sin documentación específica vigente | No se generan |
| EAN propuesto en el editor | Vacío | Sigue vacío: el hecho EAN no dispara vinculación ni copia automática |
| Ecomm ID auténtico | Pendiente | Pendiente |
| Estado editorial | Borrador local | Borrador local; no listo para canales ni publicado |

Cada campo propuesto referencia los IDs de los hechos aprobados que lo respaldan.
Sólo aprobar marca produce una propuesta de marca, sin completar títulos o
descripciones por inferencia. El guardado usa los contratos existentes y preserva
los campos no seleccionados. La ficha se cierra/reabre y recupera desde PostgreSQL;
su historial conserva cambios y versión. El pack no recibe la ficha de la unidad.

## Adaptación segura del lector

El original superaba el límite de 512 KiB y varios presupuestos internos por sus
gráficos vectoriales. Se añadió un perfil **exclusivo para el tamaño y SHA-256
anteriores**, no una ampliación general ni una excepción basada en nombre o URL.

- Los demás documentos conservan **512 KiB**. Un byte modificado, bytes añadidos,
  MIME incorrecto u otro documento grande no obtiene el perfil.
- El original ampliado sólo se importa en los dos IDs Hileret de pruebas.
- Se conserva `POST /api/test-documents/{id}/import`, con sesión, CSRF,
  autorización de procesamiento, procedencia y versión esperada.
- El gateway amplía únicamente esos dos POST de importación y sus GET de original
  versionado. Entrada/respuesta máxima de **8.325.828 bytes** para esos casos;
  el resto conserva sus límites. Un tamaño declarado de 9.000.000 se rechaza.
- DTO: máximo 8.309.444 caracteres base64; parser por socket: máximo 8.317.636
  bytes de solicitud y 524.288 de resultado. Las solicitudes ampliadas se validan
  por hash antes de enviarlas al lector.
- Para el hash autorizado: hasta 5 MiB por stream y 16 MiB acumulados, 40.000
  visitas de objetos, 128 entradas de diccionario de página y 2.000.000 unidades
  de trabajo de parsing. Se inspecciona la estructura completa, pero se extraen
  sólo las cinco ubicaciones de página 2. Sigue limitado el número de objetos,
  profundidad, arrays, páginas, texto y llamadas a formularios.
- Se mantienen rechazo de JavaScript/acciones/enlaces activos/adjuntos, cifrado,
  estructuras no soportadas, MIME o firma inválidos y expansiones fuera de límite.
- El proceso hijo mantiene **192 MiB de memoria**, **4/5 s de CPU**, alarma de
  **8 s**, sin red ni subprocesos. El contenedor mantiene su red deshabilitada,
  raíz de sólo lectura, límites y ausencia de credenciales. No se ejecuta JS,
  OCR, OpenAI ni recolector externo.
- El original se copia sólo en la imagen del harness de integración; no se
  añaden archivos al código productivo `backend/app` ni se modifica su Dockerfile.

El perfil no generaliza a otras versiones del folleto. Un PDF distinto requerirá
revisión acotada nueva; no se aceptan sus valores por semejanza de diseño o EAN.

## Reproducir y revisar personalmente

Con las dependencias y Docker locales descritos en [README](README.md):

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
```

La última orden ejecuta las regresiones de integración y después el circuito del
PDF auténtico en escritorio y celular. Se puede ejecutar `npm run test:pilot`
desde `frontend` con el gateway/backend aislados ya iniciados. No consulta dominios
externos.

Para revisión humana efectiva: iniciar `python3 integration/run.py up`, ingresar
con el usuario de prueba, abrir Hileret unidad e Investigar producto. Incorporar
manualmente la copia original indicada arriba, registrar su procedencia declarada
y dejar vacía la fecha de consulta si no se conoce. Comprobar el original conservado,
revisar citas y decidir fuente/hechos de forma independiente. Generar, revisar y
guardar sólo lo aceptado, sin marcar completo lo que aún no está respaldado.

Todo permanece en PostgreSQL descartable. Al retirar contenedores y volúmenes se
pierden sus datos; los originales, pruebas, capturas e informes permiten repetir
el recorrido. No se promete persistencia productiva. No se utiliza un Ecomm ID real
ni se conecta una API para buscarlo en esta etapa.

## Validación y entrega

- Backend/aislamiento/PostgreSQL/gateway: **132 pruebas aprobadas**, incluidas
  seis nuevas con el original auténtico y el nuevo control de tamaños del gateway.
- Regresiones heredadas en contenedor sin red: **484 aprobadas** (dos avisos de
  pytest existentes, sin errores).
- Modo demo: **46 Playwright aprobadas**.
- Piloto auténtico inicial: **2 Playwright aprobadas**, escritorio y celular,
  importando y recuperando el archivo completo a través del gateway HTTPS real.
- TypeScript, builds de demo e integración, Ruff y formato de 48 archivos Python,
  Prettier de los TypeScript modificados y comprobación de diff: aprobados.
- Regresión completa final del frontend: **106 Playwright de integración y 2 del
  piloto auténtico aprobadas**, escritorio y celular, con la versión final de la
  interfaz. Los contenedores y volúmenes descartables se retiraron al finalizar;
  no queda gateway ni base de pruebas encendidos.

Riesgos pendientes: aprobación humana efectiva, vigencia documental, respaldo del
pack x6 y de composición/certificaciones, identidad Ecomm-App auténtica y cualquier
preparación real para canales. No hubo push, PR, merge ni despliegue.

## Capturas y resultado inspeccionable

| Recorrido | Escritorio | Celular |
| --- | --- | --- |
| Antes de generar | [Captura](../frontend/artifacts/hileret-autentico-antes-desktop.png) | [Captura](../frontend/artifacts/hileret-autentico-antes-mobile.png) |
| EAN y cita documental | [Captura](../frontend/artifacts/hileret-autentico-evidencias-desktop.png) | [Captura](../frontend/artifacts/hileret-autentico-evidencias-mobile.png) |
| Propuesta limitada | [Captura](../frontend/artifacts/hileret-autentico-propuesta-desktop.png) | [Captura](../frontend/artifacts/hileret-autentico-propuesta-mobile.png) |
| Guardado y recarga | [Captura](../frontend/artifacts/hileret-autentico-guardado-desktop.png) | [Captura](../frontend/artifacts/hileret-autentico-guardado-mobile.png) |
| Pack x6 incompatible | [Captura](../frontend/artifacts/hileret-autentico-pack-bloqueado-desktop.png) | [Captura](../frontend/artifacts/hileret-autentico-pack-bloqueado-mobile.png) |

Resultados completos, sin credenciales ni los grandes bloques base64: [escritorio](../frontend/artifacts/hileret-autentico-resultado-desktop.json)
y [celular](../frontend/artifacts/hileret-autentico-resultado-mobile.json). Incluyen
ficha antes/después, versiones, hechos/citas, hash del original y estado separado
del pack. Los motivos hacen explícito el carácter automatizado de las decisiones
del operador de prueba. No son constancia de aprobación efectiva del cliente.

## Archivos modificados

- Backend del harness: `backend/integration_sandbox/document_parser.py`,
  `document_routes.py`, `document_worker.py`, `local_documents.py`,
  `hileret_routes.py`, `hileret_brochure.py`, `hileret_authentic_checks.py`,
  `proposals.py` y `research/documents.py`.
- Interfaz de integración: `frontend/src/integration/DocumentImport.tsx`,
  `HileretPilot.tsx`, `IntegrationCatalog.tsx` y `hileret-pilot.ts`.
- Pruebas frontend: `frontend/pilot-tests/hileret-authentic.spec.ts`,
  `frontend/playwright.pilot.config.ts` y script en `frontend/package.json`.
- Ejecución aislada: `integration/Dockerfile`, `Dockerfile.dockerignore`,
  `gateway.py`, `test_gateway.py`, `browser_tests.py` y `run.py`.
- Entrada auténtica: `integration/fixtures/hileret-original.pdf`.
- Documentación: `integration/HILERET-AUTHENTIC.md` y nota histórica en
  `integration/HILERET-PILOT.md`.
- `.gitignore`: resultados y trazas temporales del piloto no se versionan.
- Evidencia de entrega: los diez PNG y dos JSON enlazados arriba. No se modifican
  las capturas históricas de MAMA ni las del demo.

Sin cambios en `backend/app`, modelos/integraciones productivos, credenciales,
Render, `integration/compose.yaml`, código del modo demo ni fuentes del expediente
MAMA. Se reutilizan almacenamiento, contratos y controles existentes.
