# Etapa 2H — Investigación asistida, exclusivamente simulada

La [etapa 2I](PILOT.md) prepara un adaptador HTTPS independiente, sin activarlo ni
sustituir este recolector simulado. Los resultados de este documento son los de 2H.

Base comprobada antes de modificar: rama `feature/kiki-tech-2-dashboard`, HEAD
`e2a22b9d21568076e1c31b7513ec4b0397396c42`, árbol limpio. No se realizaron
operaciones remotas de Git ni se habilitaron proveedores.

## Recorrido dentro del dashboard

1. Abrir una variante y pulsar **Investigar producto** en Ficha. Los cambios del
   editor deben guardarse primero; la investigación utiliza una versión persistida.
2. Consultar los datos utilizados y los ausentes. El Ecomm ID identifica la variante;
   SKU y EAN nunca fusionan productos. La captura no tiene por qué contener EAN,
   marca, fabricante o contenido neto. Las propuestas manuales KIKI se rotulan
   como no verificadas; los hechos aprobados se identifican separadamente.
3. Revisar candidatos priorizados: sitio del fabricante, ficha técnica, etiqueta,
   catálogo y documentación comercial. Las fuentes públicas restantes son pistas.
   Todos los candidatos son **SIMULADOS**. «Oficial declarada» no verifica procedencia.
4. Contrastar EAN, marca, fabricante, nombre, presentación, contenido neto y
   unidad/pack. La coincidencia de EAN no resuelve discrepancias ni aprueba datos.
5. Seleccionar o rechazar con motivo. Confirmar la incorporación del documento
   simulado, sin visitar su URL ni modificar la ficha comercial.
6. Usar el flujo existente de Evidencias: revisión humana de procedencia, extracción
   y aprobación/rechazo individual de datos. Consultar el original, su hash y ubicación.
7. En IA generar la propuesta determinista 2F desde hechos aprobados vigentes;
   revisar campos y guardar por el editor 2D. Recargar e inspeccionar el historial.

La selección de un candidato, su origen declarado y la aprobación de cada dato
son decisiones distintas. La revisión humana del fixture nunca lo convierte en
documentación auténtica. Ninguna acción publica o sincroniza productos.

## Arquitectura y reutilización

```text
dashboard / gateway HTTPS local
  -> FastAPI sintético + autenticación, CSRF y versiones existentes
      -> PostgreSQL descartable por socket Unix
         (Dossier/Document/historial 2E y editor/propuestas existentes)
      -> recolector por /discovery-collector/collector.sock
         (índice y respuestas HTTP/DNS en memoria; sin acceso a Internet)
      -> lector 2G por /document-parser/parser.sock
         (PDF/TXT/HTML pasivo/JSON, proceso limitado por documento)
```

Los cuatro contenedores —PostgreSQL, FastAPI, lector y recolector— tienen
`network_mode:none`, sin puertos TCP publicados, raíz de sólo lectura y
`no-new-privileges`. FastAPI, lector y recolector eliminan todas las capacidades.
El recolector usa UID 1000,
128 MiB, 1 CPU y 16 procesos como límites; sólo monta su directorio de socket.
No monta base, socket API, Docker, `.env` ni credenciales. El hook de auditoría
impide conexiones salientes, DNS y procesos, además del aislamiento del kernel.

No hay tablas ni migraciones nuevas. Las investigaciones y sus decisiones usan
el historial del expediente 2E. Cada documento conserva original, SHA-256,
solicitud y destino final simulados, redirecciones, IPs, fecha y relación con el
candidato. Se transfiere por protocolo de longitud acotada, nunca mediante una
URL que el backend deba descargar. El lector e ingestor 2G procesan los mismos
formatos y conservan las decisiones de procedencia existentes.

La versión del expediente, de la ficha y de cada candidato evitan decisiones
obsoletas. Si cambia identidad, edición o evidencia aprobada, la investigación
queda desactualizada. Las llamadas al recolector/lector liberan los bloqueos;
antes de incorporar se recuperan y revalidan las versiones y se bloquea la fila
del editor. Dos decisiones concurrentes sobre la misma base producen 200 y 409.
No hay sobrescritura silenciosa ni reintento automático del navegador.

## Política de obtención

No existe adaptador HTTP/DNS real, interruptor para activarlo ni parámetro de
URL arbitraria. Sólo se aceptan instancias exactas de `SimulatedHTTP` y
`SyntheticDNS`; el catálogo de respuestas se escribe independientemente de la
consulta, para no inventar una fuente a partir de datos introducidos.

- HTTPS y dominios exactos reservados: `fabricante-prueba.invalid`,
  `documentos-prueba.invalid` y `pista-publica.invalid`. No se resuelven en red.
- Rechazo de credenciales en URL, puertos alternativos, query, fragmentos,
  escapes, controles y destinos fuera de la lista.
- Todas las direcciones DNS simuladas deben ser públicas: se rechazan privadas,
  loopback, link-local, multicast, mezclas públicas/privadas y privadas mapeadas.
- Cada salto vuelve a validarse; máximo dos redirecciones, sin bucles. Se comprueba
  que la IP final pertenezca al conjunto validado y se registra la cadena.
- Sólo GET con Accept y User-Agent fijos; sin cookies, tokens, cabeceras arbitrarias,
  escrituras, ejecución de JavaScript ni elusión de 403/429 u otras restricciones.
- Hasta 512 KiB, cinco segundos agregados, longitud consistente y MIME PDF,
  texto, HTML pasivo o JSON. No se acepta compresión HTTP. El lector valida
  además formato real, complejidad y contenido activo según 2G.
- Consulta al recolector hasta 16 KiB; respuesta hasta 750.000 bytes y socket con
  timeout. Como máximo veinte candidatos por consulta y diez investigaciones por
  variante en este entorno descartable. Los límites de documentos 2G se conservan.

Estas pruebas validan la política con dobles; **no acreditan comportamiento de
TLS, DNS o servidores reales**. El permiso de red del host para descargar paquetes
durante build no concede red a los servicios ni a los documentos.

## Documentos y extracción

Se incluyen ejemplos sintéticos de las seis variantes de dietética. Hay HTML
pasivo de fabricante, fichas TXT, una ficha PDF, etiquetas JSON, catálogos y
documentación comercial; también pistas, otro fabricante, una contradicción
nutricional y un documento insuficiente. Los EAN y certificaciones son ficticios.

El lector conserva ingredientes, alérgenos, contenido neto, presentación,
características y conservación. Añade carbohidratos, azúcares, grasas totales,
grasas saturadas, fibra y sodio, junto con energía y proteínas. Reconoce etiquetas
explícitas y filas simples con unidades, sin cruzar filas ni completar valores.
Cada hecho mantiene documento, página/ubicación, fragmento y unidad original.

Las certificaciones necesitan un respaldo específico del mismo documento
aprobado primero; una declaración «sin gluten» u «orgánico» aislada no basta.
Revocar el respaldo invalida el uso posterior. El control verifica trazabilidad
documental y revisión humana, no la validez legal de una certificación. Los
documentos con identidad incompatible o hechos contradictorios mantienen los
bloqueos 2E; no existe aprobación automática.

No hay OCR, crawler, buscador web, interpretación general de tablas complejas,
descarga de multimedia ni inferencia alimentaria. Los PDF sin texto quedan
pendientes de OCR; entradas activas, excesivas o no admitidas se rechazan.

## Contratos del harness

Todos los POST exigen sesión, CSRF y únicamente uno de los seis Ecomm ID sintéticos.
No se agregan rutas al punto de entrada productivo.

| Ruta | Datos obligatorios |
| --- | --- |
| POST `/api/test-discovery/{id}/start` | `expected_version`, `expected_workspace_version` |
| POST `/api/test-discovery/{id}/candidates/{candidate_id}/decision` | `expected_version`, `run_id`, `expected_candidate_version`, `decision: SELECTED\|REJECTED`, `reason` |
| POST `/api/test-discovery/{id}/candidates/{candidate_id}/acquire` | `expected_version`, `run_id`, `expected_candidate_version` |

Las respuestas devuelven el expediente existente con `assisted`,
`simulated_only:true` y `network_enabled:false`. Claves extra, candidatos de otra
variante, versiones antiguas y destinos arbitrarios se rechazan. Se reutilizan
`/api/test-documents`, `/api/test-research`, `/api/test-proposals` y GET/POST
`/api/ecomm-app/workspace/{ecomm_id}`, sin otro editor ni persistencia paralela.

## Inicio y comprobaciones

Requisitos y configuración detallados en [README](README.md): Linux/WSL2,
UID 1000, Docker local, Python y Node. Desde la raíz, ejecutar secuencialmente:

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
python3 integration/run.py up
```

`up` mantiene la pasarela local en primer plano: `https://127.0.0.1:8443/`.
Usuario `operador-prueba`, contraseña sintética `solo-datos-sinteticos`.
Confiar en el certificado local según README. Ctrl+C elimina los contenedores y
volumen de socket; PostgreSQL usa tmpfs y sus datos se pierden. No ejecutar dos
comandos sobre el mismo proyecto Docker simultáneamente. No se publica una URL cloud.

Desde `frontend`, `npm run typecheck`, `npm run build`,
`npm run build:integration` y `npm test` comprueban también el demo conservado.
Ruff se ejecuta sobre `backend/integration_sandbox` e `integration`.

## Archivos de la etapa

- Recolector y política: `backend/integration_sandbox/discovery_http.py`,
  `discovery_worker.py`, `discovery_fixtures.py`,
  `discovery-fixtures/harina-tecnica.pdf`.
- Orquestación, API y pruebas: `assisted_research.py`, `assisted_routes.py`,
  `assisted_checks.py`, dentro de `backend/integration_sandbox`.
- Reutilización del harness: `bootstrap.py`, `policy.py`, `local_documents.py`,
  `document_parser.py`, `proposals.py`, `research/documents.py`,
  `research/service.py` dentro del mismo directorio.
- Dashboard: `frontend/src/integration/AssistedResearch.tsx`, `PersistentWorkspace.tsx`,
  `ResearchPanel.tsx`, `DocumentImport.tsx`, `research-adapter.ts`,
  `catalog-adapter.ts`, `isolation.ts`, `research.css`.
- Playwright: `frontend/integration-tests/zzzassisted.spec.ts`.
- Infraestructura: `integration/compose.yaml`, `gateway.py`, `run.py`.
- Documentación: este archivo, `integration/README.md`, `DOCUMENTS.md`,
  `frontend/PROTOTYPE.md`; `.gitattributes` conserva el PDF sin normalizar bytes.
- Capturas: `frontend/artifacts/investigacion-{asistida,guardada,discrepancias}-{desktop,mobile}.png`.

## Antes de probar una fuente auténtica

Se requiere autorización posterior y una lista explícita de dominios y documentos,
con revisión de permisos/condiciones del sitio y de la identidad del fabricante.
Debe diseñarse y revisarse un adaptador HTTPS real separado: TLS/hostname, DNS
fijado, redirecciones, destino final, límites en streaming, robots/condiciones,
retención y tratamiento seguro de documentos reales. La salida del recolector
debe restringirse también en red; FastAPI, PostgreSQL y el lector seguirán sin red.
No basta con cambiar un dominio o una variable para habilitarlo.

Hacen falta pruebas específicas del adaptador y una primera revisión humana
controlada de un documento auténtico. Ninguna validación sintética sustituye
comprobar fabricante, presentación, formulación o certificación real. Esta etapa
no habilita búsquedas reales, IA externa, sincronizaciones ni publicaciones.

## Validación ejecutada

| Comprobación | Resultado |
| --- | --- |
| Build de imagen del harness | Aprobado |
| Backend, PostgreSQL descartable, lector, recolector y gateway | 90 aprobadas: 76 anteriores y 14 nuevas |
| Suite histórica del backend, dentro del contenedor sin red | 484 aprobadas; dos advertencias previas de plugins |
| Playwright integración, escritorio/celular | 88 aprobadas: 78 anteriores y 10 nuevas |
| Playwright demo | 46 aprobadas |
| TypeScript y builds demo/integración | Aprobados; se conserva el aviso previo de tamaño del bundle demo |
| Ruff y formato Python | Aprobados, 33 archivos |
| Prettier de los archivos frontend de esta etapa y espacios Git | Aprobados |

Las pruebas nuevas cubren EAN ausente/incorrecto, variante y presentación
incompatibles, otro fabricante, datos disponibles sin valores de relleno,
priorización, procedencia sin comprobar, PDF y conservación del original,
nutrientes estructurados y unidades, contradicciones e información insuficiente,
certificaciones con respaldo y revocación, generación y guardado por el editor
existente, historial, investigación desactualizada, autenticación/CSRF y dos
operadores concurrentes sobre PostgreSQL real descartable.

Las pruebas negativas rechazan dominios ajenos, protocolos, credenciales, DNS
privado/mixto, redirecciones inseguras, bucles, IP final inesperada, tamaño, tiempo,
MIME, compresión y restricciones de acceso. El transporte real se rechaza por
tipo. Las guardas anteriores siguen bloqueando proveedores, destinos PostgreSQL
productivos, procesos y recursos externos del navegador.

| Captura | Escritorio | Celular |
| --- | --- | --- |
| Candidatos y contraste de identidad | [Ver](../frontend/artifacts/investigacion-asistida-desktop.png) | [Ver](../frontend/artifacts/investigacion-asistida-mobile.png) |
| Ficha guardada y recuperada | [Ver](../frontend/artifacts/investigacion-guardada-desktop.png) | [Ver](../frontend/artifacts/investigacion-guardada-mobile.png) |
| EAN y fabricante incompatibles | [Ver](../frontend/artifacts/investigacion-discrepancias-desktop.png) | [Ver](../frontend/artifacts/investigacion-discrepancias-mobile.png) |

No hay diferencias en `backend/app`, requisitos productivos, integraciones,
entrada/configuración y código del demo, Render ni workflows respecto a la base
2G. Se revisaron visualmente las capturas de escritorio y celular. Los cuatro
contenedores y el volumen de socket se eliminaron al terminar; no quedó una base
de integración activa. Sin push, PR, merge, despliegue ni acceso a documentación auténtica.
