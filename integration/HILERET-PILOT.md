# Etapa 2K — Hileret Stevia: preparación con original pendiente

La [continuación con el original auténtico adjunto](HILERET-AUTHENTIC.md) documenta
su SHA-256, extracción de página 2 y recorrido posterior. Este informe conserva el
resultado histórico de preparación, anterior a disponer de los bytes del PDF.

Base comprobada: `feature/kiki-tech-2-dashboard`,
`df6fa70aa4b4f03d310460f37d012560bad601e1`, árbol inicialmente limpio.

## Resultado documental y comercial

**El PDF auténtico no está disponible localmente. No fue descargado ni procesado.**
Se revisaron los archivos del repositorio y los directorios de adjuntos locales;
no se encontraron los bytes del folleto. No se consultó el enlace ni se activó el
recolector. La política de red tampoco incluye el dominio Hileret, y no se solicitó
agregarlo. El vínculo se guarda como referencia, con procedencia pendiente.

Referencia oficial informada por el usuario:

`https://descargas.hileret.com.ar/Hileret/Folleto%20Ventas%20Hileret%2017x25_400s.pdf`

Página informada: **2**. La página no es una cita extraída por Codex. No hay hash
del PDF, fecha de consulta, texto extraído ni ubicaciones verificadas del original.
El hash que el lector existente asigna a una referencia URL es sólo el hash de
esa cadena; el informe del piloto devuelve `original:null` para esa referencia.
No se presenta como SHA-256 de un PDF.

| Dato | Procedencia actual | Decisión |
| --- | --- | --- |
| Unidad líquida Hileret con Stevia, 200 cc | Excel fila 28, comunicado por usuario | Identificación auxiliar; no hecho aprobado |
| Pack x6 de 200 ml | Excel fila 27, comunicado por usuario | Registro separado; respaldo del pack pendiente |
| EAN declarado `7794940000796` en ambas filas | Excel informado; también reportado para la unidad en el folleto | No fusionar; correspondencia documental aún no comprobada por Codex |
| Hileret Stevia, 200 ml y EAN individual | Contenido del folleto comunicado por usuario | Aprobable sólo después de incorporar y revisar original, identidad y citas |
| Caja logística de 9 unidades de 200 ml | Contenido del folleto comunicado por usuario | Dato logístico pendiente; no pack comercial x6 |
| DUN `97794940000799` | Contenido del folleto comunicado por usuario | Código logístico; nunca EAN de la unidad ni verificación del pack x6 |
| Ingredientes, alérgenos, nutrición | Sin documento específico | Bloqueados; el folleto no acredita toda la composición |
| Certificaciones, beneficios, «sin gluten» | Sin documentación específica vigente | Bloqueados; no se infieren |
| Categoría, subcategoría y recursos multimedia | Sin evidencia y clasificación revisadas | Sin completar |
| Ecomm ID auténtico, por cada variante | Catálogo maestro no consultado | Pendiente; no se inventa ni se deduce de EAN/SKU |

No se atribuyen celdas exactas del Excel a esta etapa, ni se reutiliza la
verificación de MAMA para afirmar una lectura de estas filas. No se deduce una
razón social del fabricante desde la marca o el dominio.

## Tres presentaciones que no se confunden

- Unidad: `PILOT-HILERET-200-UNIT-SYNTHETIC`, referencia de fila 28, `200 ml`.
- Pack comercial: `PILOT-HILERET-200-PACK6-SYNTHETIC`, referencia de fila 27,
  `6 x 200 ml`. El EAN comunicado sigue siendo un dato declarado, sin adoptarlo
  como identificador del pack.
- Caja logística: x9, sólo referencia logística, sin crear un tercer producto
  comercial ni una variante del catálogo maestro.

Los dos expedientes tienen documentos asociados, identidad, hechos e historial
independientes. Un documento asociado a la unidad no se extrae en el pack por
compartir EAN. La identidad del pack exige nombre, presentación y tipo de venta
compatibles; el folleto de la unidad no prueba por sí solo el pack. El DUN no
coincide con el EAN esperado. `200 cc` se conserva como declaración del Excel y
`200 ml` como referencia de volumen; no se inventa un peso.

## Reutilización y persistencia aislada

No hay otro editor, tablas nuevas, migraciones ni un segundo catálogo. Se usan
`Dossier`, `Document`, los registros de edición y las propuestas existentes.

- `GET /api/test-commercial-pilot/hileret-200` informa los expedientes preparados.
- `POST /api/test-commercial-pilot/hileret-200/prepare`, cuerpo `{}`, requiere
  sesión y CSRF; prepara los dos casos explícitos de forma idempotente.
- Se reutilizan los contratos `GET/POST /api/ecomm-app/workspace/{id}`, los 18
  campos, validaciones, historial y concurrencia por `expected_version`.
- Se reutilizan `/api/test-documents`, `/api/test-research` y
  `/api/test-proposals` para originales, procedencia, extracción, revisión,
  propuestas y aplicación de cambios revisados.
- Sólo se amplía la lista de rutas **locales** para los dos IDs sintéticos.
  No se permiten IDs arbitrarios, descubrimiento Hileret, nuevas conexiones
  externas ni cambios de dominios autorizados.
- Los pilotos sólo admiten `DRAFT`; Ecomm ID real pendiente impide declararlos
  listos para canales. No se generan propuestas sin hechos aprobados.
- En Hileret, una transcripción TXT/HTML/JSON o una URL no permite aprobar hechos
  como sustituto del PDF original, aunque su identidad textual parezca compatible.

El modo demo y los servicios productivos no se modifican. El expediente MAMA se
conserva como caso de evidencia insuficiente. Los contenedores mantienen
`network_mode:none`, sin tokens, PostgreSQL descartable por socket y preflight
anterior al engine/DDL; el gateway sólo escucha en loopback HTTPS.

## Recorrido desde el dashboard

Seguir [el arranque aislado existente](README.md). Con las dependencias locales:

```sh
python3 integration/run.py build
python3 integration/run.py up
```

Abrir `https://127.0.0.1:8443` desde el mismo entorno; usar únicamente el usuario de
pruebas documentado en la configuración aislada. Este enlace es local al entorno,
no una URL pública ni el localhost de otra computadora.

1. Abrir «Hileret unidad de pruebas» o «Hileret pack x6 de pruebas». Los casos
   quedan fuera de la tabla y de sus indicadores Ecomm-App.
2. La ficha lateral muestra la procedencia, las tres presentaciones y el motivo
   de bloqueo; la búsqueda y URL del dashboard se conservan.
3. «Investigar producto» abre Evidencias sin arrancar el recolector.
4. En «Incorporar archivo local o referencia oficial», seleccionar el **PDF
   original** y registrar autorización, URL original, cómo se obtuvo y fecha
   cierta, si se conoce. No usar un PDF reconstruido con los datos del mensaje.
5. Comprobar el SHA-256 del archivo conservado, recuperarlo con «Comprobar
   original conservado» y revisar su procedencia. Declarar oficial no lo aprueba.
6. Revisar texto y ubicaciones `pagina/N/linea/M`, especialmente página 2, sin
   asociar líneas de otros productos a Stevia. Contrastar EAN, marca y volumen.
   Mantener separados el pack x6 y la caja x9. Si no hay extracción inequívoca,
   conservar el bloqueo.
7. Aprobar individualmente sólo hechos respaldados. Generar y comparar una
   propuesta limitada a esos hechos, revisar decisiones y guardar mediante el
   editor existente. No hay OpenAI real ni aplicación automática.
8. Cerrar, reabrir y consultar comparación e historial. Dos operadores sobre la
   misma versión deben obtener un guardado y un conflicto 409, sin sobrescritura.

**Límites existentes:** 512 KiB, máximo 10 páginas PDF, texto accesible y ausencia
de acciones activas/cifrado. No hay OCR ni extracción general de tablas o diseños
arbitrarios. La disponibilidad del PDF no garantiza que el parser pueda
interpretarlo. Un folleto más grande, escaneado o con estructura no soportada
debe permanecer bloqueado; esta etapa no relaja límites, modifica el original ni
agrega un extractor basado en contenido todavía no inspeccionado.

## Comparación antes/después de esta etapa

| Elemento | Antes | Después |
| --- | --- | --- |
| Expediente Hileret | No disponible | Dos expedientes auxiliares separados en PostgreSQL de pruebas |
| Documento original | No suministrado | Continúa pendiente, sin fingir descarga ni extracción |
| Hechos aprobados / propuesta | Ninguno | Ninguno; bloqueo explícito y procedimiento manual disponible |
| Ficha comercial | Sin completar | Campos comerciales siguen sin completar; nota de seguimiento recuperable |
| Unidad / pack / logística | Datos comunicados | Contrastes explícitos, sin fusión por EAN ni copia entre expedientes |
| MAMA | Evidencia insuficiente | Preservado |

Los datos de la ejecución son descartables y desaparecen al retirar los
contenedores/volúmenes. La preparación se puede repetir en otra sesión de
pruebas; no se promete persistencia productiva.

## Validación y limitación del piloto

Las pruebas nuevas usan únicamente controles negativos etiquetados como
sintéticos. Verifican bytes, SHA-256, páginas, citas, revisión e historial del
lector existente; **no constituyen procesamiento documental auténtico de
Hileret**. Ese tramo, la aprobación de sus hechos y la propuesta comercial real
quedan pendientes hasta disponer del original y revisar lo que efectivamente
contiene. No se entrega una ficha comercial inventada para completar el piloto.

Resultados de las regresiones:

- `python3 integration/run.py test`: **125 pruebas aprobadas**, incluidas las
  ocho nuevas de Hileret, PostgreSQL, autenticación, aislamiento y controles de
  destinos productivos. Las ocho de Hileret volvieron a pasar tras comprobar que
  copiar marca/EAN compatibles al editor no invalida artificialmente la identidad.
- Regresiones heredadas dentro del contenedor sin red: **484 aprobadas**. Dos
  avisos existentes de pytest no provocaron errores.
- `python3 integration/run.py browser-test`: **106 pruebas aprobadas** en
  escritorio y celular, con catálogo, editor, evidencias, propuestas, recolector
  simulado, MAMA e Hileret. Se comprobó también el rechazo de configuración de
  build ambigua, sin fallback.
- `npm test`: **46 pruebas del demo aprobadas**.
- TypeScript, build del demo y build de integración: aprobados. El demo conserva
  el aviso de tamaño del bundle, sin errores.
- Ruff y comprobación de formato: **46 archivos aprobados**. Prettier de los
  archivos TypeScript modificados y `git diff --check`: aprobados.

La precisión de la etiqueta «SHA-256 de la URL (no del PDF)» se validó además con
**20 pruebas enfocadas aprobadas** del lector, MAMA e Hileret, después de ese
ajuste. No cambia los bytes, la procedencia ni las decisiones de ningún documento
existente.

## Capturas

| Recorrido | Escritorio | Celular |
| --- | --- | --- |
| Unidad de 200 ml | [Captura](../frontend/artifacts/hileret-unidad-desktop.png) | [Captura](../frontend/artifacts/hileret-unidad-mobile.png) |
| Pack comercial x6 | [Captura](../frontend/artifacts/hileret-pack6-desktop.png) | [Captura](../frontend/artifacts/hileret-pack6-mobile.png) |
| Documento pendiente y procedencia | [Captura](../frontend/artifacts/hileret-documento-pendiente-desktop.png) | [Captura](../frontend/artifacts/hileret-documento-pendiente-mobile.png) |

Estas capturas muestran un expediente con documento pendiente, no un folleto
auténtico procesado. Los contenedores/volúmenes se retiran al terminar las pruebas;
no queda una base encendida ni persistencia externa.

## Archivos de esta etapa

- `backend/integration_sandbox/hileret_reference.py`: referencias declaradas y
  contraste de identidades; sin contenido oficial inventado.
- `backend/integration_sandbox/hileret_routes.py`: preparación e informe de los
  dos expedientes sobre almacenamiento existente.
- `backend/integration_sandbox/hileret_checks.py`: controles negativos, aislamiento,
  original, citas, preservación, historial e idempotencia/concurrencia PostgreSQL.
- `backend/integration_sandbox/workspace.py`, `proposal_routes.py` y `proposals.py`:
  dos aliases explícitos del editor existente y bloqueo de propuestas sin hechos.
- `backend/integration_sandbox/research/service.py`: contraste Hileret, separación
  documental por identidad y bloqueo de transcripciones como reemplazo del PDF.
- `backend/integration_sandbox/bootstrap.py` y `policy.py`: montaje sólo en el
  harness aislado y rutas locales limitadas.
- `frontend/src/integration/hileret-pilot.ts` y `HileretPilot.tsx`: contrato,
  preparación y resumen/documentación pendiente en el panel del dashboard.
- `frontend/src/integration/IntegrationCatalog.tsx`, `PersistentWorkspace.tsx`,
  `ResearchPanel.tsx` y `ProposalPanel.tsx`: apertura y operaciones existentes
  integradas, conservando URL y contexto.
- `frontend/src/integration/isolation.ts`: rutas locales para los dos IDs exactos;
  los destinos externos siguen bloqueados.
- `frontend/src/integration/DocumentImport.tsx`: distingue el hash de la URL del
  hash de bytes de archivo, sin modificar documentos ni el expediente MAMA.
- `frontend/integration-tests/zzzzzzhileret.spec.ts`: recorridos en escritorio y
  celular, referencias, bloqueos, URL, guardado e historial sin tráfico externo.
- `integration/run.py`: agrega las comprobaciones Hileret a la suite existente.
- `integration/HILERET-PILOT.md`: este informe y procedimiento.
