# Etapa 2E — Investigación documental sintética

Base verificada antes de modificar: `feature/kiki-tech-2-dashboard`, HEAD
`691b9a93ed47a9deb6498f01a3ef5510e095e0ff`, árbol limpio.

## Alcance operativo

Desde Evidencias, en el panel lateral existente, se selecciona un documento de
prueba, se inspeccionan sus fragmentos y se extraen hechos determinísticamente.
Cada hecho requiere revisión individual con motivo. Se puede aprobar, rechazar,
revocar, consultar historial y simular una nueva versión documental. La pestaña
Ficha consulta los hechos aprobados vigentes sin aplicar valores a campos
comerciales. El editor y su persistencia 2D se conservan.

No hay búsqueda web, scraping, IA, PDFs reales, uploads, descarga de URLs ni
publicación. Los documentos son JSON/texto escritos como fixtures y están
identificados como DOCUMENTOS SINTÉTICOS DE PRUEBA. No se presentan como documentos
oficiales de un fabricante. La extracción lee campos estructurados y los contrasta
con texto local; no es OCR ni comprensión general de documentos.

## Identidad y referencias

El Ecomm ID de la ruta y del registro es la identidad canónica. SKU y EAN no
seleccionan, vinculan ni fusionan variantes. Se reutiliza la lectura local del
catálogo maestro existente para comprobar que el ID corresponde a una variante
única de la captura completa.

Se comparan nombre original, presentación, EAN, marca y fabricante. El EAN de la
captura tiene preferencia; si falta, se contrasta con la propuesta editorial
guardada o la referencia sintética declarada del fixture. Marca/fabricante
provienen de la ficha guardada o de referencias sintéticas explícitas. **Estas
referencias no son datos verificados de Ecomm-App ni del fabricante.** La UI
indica procedencia y ausencia por campo. Una diferencia impide aprobar hechos.
Una presentación editorial que difiere de la captura también genera bloqueo.

Las dos presentaciones de almendras comparten SKU, tienen Ecomm IDs diferentes
y referencias EAN de prueba distintas. Cada expediente y cada ID de hecho quedan
ligados al Ecomm ID; no hay registro canónico por SKU o EAN.

## Contratos, todos exclusivos del harness

| Método y ruta | Propósito |
| --- | --- |
| GET `/api/test-research/{ecomm_id}` | Expediente, versión, identidad/procedencia, documentos completos, hechos, bloqueos, faltantes e historial |
| POST `/api/test-research/{ecomm_id}/extract` | `{expected_version, document_id, document_version}`; extracción sin aprobación |
| POST `/api/test-research/{ecomm_id}/facts/{fact_id}/review` | `{expected_version, expected_fact_version, decision, reason}`; decisión individual |
| POST `/api/test-research/documents/{document_id}/revision` | `{expected_version, new_version}`; sólo siguiente revisión de fixture predefinida |

Los IDs permitidos son los seis fixtures. GET requiere sesión; todos los POST
requieren sesión y CSRF. No hay contrato de aplicar a ficha, búsqueda, IA, subida
de documentos, credenciales ni proveedor configurable. El gateway y el navegador
permiten exclusivamente esos métodos/rutas, además de 2B–2D.

Los conflictos de versión/identidad/evidencia devuelven 409 y los cuerpos
inválidos 422. La UI conserva el motivo ante 409, recupera la versión nueva y
exige otra acción explícita, sin reintentar una aprobación automáticamente.

## Persistencia aislada

Se usa un `ResearchBase` independiente de los modelos productivos, con tres tablas
en el esquema **`kiki_research_test`** del PostgreSQL descartable:

- `control`: fila única que serializa las transacciones del pequeño prototipo.
- `documents`: ID, versión activa, cuerpo local, SHA-256 e historial con cuerpos
  y huellas anteriores. Sólo se aceptan versiones incluidas en los fixtures.
- `dossiers`: Ecomm ID (PK), versión, identidad y huella, hechos JSON e historial.

Cada hecho guarda Ecomm ID, campo comercial y tipo de dato, valor, unidad,
presentación, documento/versión/huella, ubicación, cita, fecha de consulta,
creador, estado, revisor, fecha de revisión, versión e historial antes/después.
Una aprobación se vincula con una huella del contenido y de la identidad.

La inicialización del esquema ocurre sólo en el lifespan del harness, después
del preflight de 2B y la validación de fixtures. `app.main`, `Base` y los modelos
productivos no importan este esquema. El contenedor productivo tampoco copia el
paquete del harness. No se ejecutan migraciones productivas.

Ver [plan separado de migración y reversión](RESEARCH-MIGRATION-PLAN.md). Apagar el
entorno destruye el PostgreSQL tmpfs y su esquema; no es una base duradera fuera
del ciclo de prueba.

## Verificación, contradicciones y caducidad

Estados: PENDING, APPROVED, REJECTED, REVOKED y STALE. Extraer siempre crea
propuestas pendientes; repetir la misma extracción conserva las decisiones de
rechazo o revocación y no genera versiones innecesarias. Un documento revisado
requiere una nueva extracción y revisión explícitas.

Para aprobar, deben coincidir identidad/presentación, versión y huella documental,
ubicación/cita y transcripción explícita. Ingredientes, alérgenos, nutrientes,
peso y declaraciones no se completan por suposición. Los nutrientes y el peso
requieren una unidad explícita en el fragmento. Que un valor aparezca sólo en
metadatos estructurados no basta si su fragmento no lo respalda.

Dos valores incompatibles para un mismo dato y variante bloquean la aprobación.
Si aparece una fuente contradictoria válida, se invalida la aprobación anterior.
El operador debe rechazar o resolver el respaldo incompatible y volver a extraer
y revisar el hecho invalidado. Rechazar la alternativa no restaura automáticamente
la verificación previa. No se hacen conversiones de unidades ni equivalencias de packs.

Cambios de documento, valor, unidad, presentación o identidad invalidan las
verificaciones afectadas. GET también comprueba vigencia y **puede persistir una
invalidación automática** con actor Sistema y sesión disparadora. Si la variante
deja de tener identidad única disponible, se invalidan sus hechos y se responde
409. Nunca se sustituye la variante por otra con el mismo SKU.

Los textos/documentos anteriores y decisiones no se eliminan al revisar. Una
decisión humana registra cuenta y sesión del servidor, motivo, fecha y versiones;
no acepta un nombre de revisor suministrado por el cliente. El historial del
editor 2D sigue separado del historial documental.

La fila de control se bloquea con `FOR UPDATE` antes de leer/modificar. Se compara
la versión del expediente y del hecho dentro de esa transacción. Una revisión
documental usa la misma exclusión, evitando carreras entre aprobar e invalidar.
Dos decisiones sobre la misma base no pueden sobrescribirse: una gana y la otra
recibe 409. Este bloqueo global es conservador y adecuado sólo para el prototipo
pequeño; no se presenta como arquitectura de procesamiento masivo.

## Ejemplos verificables

| Caso | Documento/resultado |
| --- | --- |
| Correcto | `alm-tecnica`, ingredientes «Almendras» con cita y presentación 250 g; aprobación manual |
| Insuficiente | `alm-incompleta`, energía «500» sin unidad y declaración «Orgánico» ausente en el fragmento: no aprobables |
| Contradictorio | Técnica: 600 kcal/100 g (revisiones sintéticas posteriores: 620/640) frente a tabla alternativa 610 kcal/100 g (revisión: 611) |
| Identidad incompatible | Etiqueta con EAN diferente o contenido neto 1 kg seleccionado para variante de 250 g |
| SKU compartido | El documento 1 kg es compatible con Ecomm ID 900002, sin fusionarlo con 900001 |
| Documento cambiado | Revisión sintética v1→v2→v3; se conservan fragmentos anteriores y se exige nueva revisión |

Hay ejemplos de ficha técnica, etiqueta, ingredientes, tabla nutricional y
presentación/contenido neto. La incompletitud es visible: la UI enumera datos
sin respaldo aprobado, sin rellenar valores desconocidos.

## Ejecución

Se conservan los prerrequisitos y el certificado local de 2B–2D:

```sh
python3 integration/run.py build
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
python3 integration/run.py up
```

En la máquina que ejecuta el entorno, abrir `https://127.0.0.1:8443/`, confiar
explícitamente en el certificado local y entrar con la cuenta de prueba habitual.
No ejecutar simultáneamente comandos que usan el mismo proyecto Docker. Ctrl+C
elimina el entorno descartable. No hay puerto publicado cloud ni despliegue.

El backend y PostgreSQL mantienen `network_mode:none`; siguen los bloqueos de
proveedores, DNS, recursos, redirecciones y variables heredadas. Los documentos
y sus enlaces `fixture://` se muestran como texto, sin abrir recursos.

## Límites pendientes

- Sólo documentos estructurados sintéticos conocidos. No hay OCR, investigación
  externa, validación de autenticidad oficial ni IA.
- «Aprobada» significa revisión humana del ejemplo sintético, no certificación
  nutricional, legal o comercial de un producto real.
- Las referencias faltantes del catálogo se declaran como fixtures o propuestas
  no verificadas; falta integración con identidad/documentación oficial real.
- Autoría usa cuenta y sesión de prueba; no agrega usuarios, roles ni firma
  digital. Debe revisarse antes de un uso multiusuario real.
- JSON e historial completos y mutex global requieren normalización, índices,
  retención y pruebas de carga antes de procesar documentos masivamente.
- La lectura puede registrar invalidaciones. Se conserva fecha de extracción;
  no se agregan revisiones periódicas programadas.
- No existe aplicación automática a fichas aprobadas. Esa acción necesita un
  contrato y autorización posteriores, con control de versiones del editor.

## Validación ejecutada

| Comprobación | Resultado |
| --- | --- |
| `python3 integration/run.py test` | 46/46: 19 de aislamiento/base, 7 del editor, 13 documentales y 7 del gateway HTTPS |
| `python3 integration/run.py legacy-test` | 484 aprobadas; 2 advertencias previas de plugins de pytest |
| `python3 integration/run.py browser-test` | 58 aprobadas, escritorio y celular; 12 de investigación y 46 previas |
| Playwright del modo demo (`npm test`) | 46 aprobadas; sin backend |
| TypeScript y builds demo/integración | Aprobados; advertencia de tamaño de bundle en el build demo |
| Ruff y comprobación de espacios de Git | Aprobados |

La concurrencia se ejecutó contra PostgreSQL descartable real: dos sesiones
intentaron decidir sobre la misma versión, hubo una única escritura y un 409.
Se comprobó persistencia tras recarga, revocación, invalidación por cambios de
valor/presentación/documento/identidad, ausencia de reemplazo de campos comerciales,
rechazo de configuraciones productivas y bloqueo de proveedores. Playwright
vigila y rechaza solicitudes fuera del origen HTTPS local. Al finalizar no quedan
contenedores del proyecto ni datos del PostgreSQL tmpfs.

Las rutas y servicios en `backend/app`, la entrada/configuración del demo,
su aislamiento, Render y los workflows no tienen modificaciones respecto a 2D.

## Archivos de esta etapa

- Backend de pruebas: `backend/integration_sandbox/research/{__init__,documents,
  storage,service,routes}.py`, `research_checks.py`, `bootstrap.py` y `policy.py`.
- Dashboard de integración: `frontend/src/integration/ResearchPanel.tsx`,
  `research-adapter.ts`, `research.css`, `PersistentWorkspace.tsx`,
  `catalog-adapter.ts` e `isolation.ts`.
- Pruebas de navegador: `frontend/integration-tests/research.spec.ts`.
- Harness: `integration/gateway.py`, `run.py` y `test_gateway.py` (incluye manejo
  de cancelaciones TLS y prueba del límite HTTP sin enviar a un socket cerrado).
- Documentación: `integration/RESEARCH.md`, `RESEARCH-MIGRATION-PLAN.md`,
  `README.md`, `EDITOR.md` y `frontend/PROTOTYPE.md`.
- Diez capturas nuevas en `frontend/artifacts/investigacion-{documento,hecho,
  insuficiente,contradiccion,revocacion}-{desktop,mobile}.png`.

Capturas destacadas: [aprobación en escritorio](../frontend/artifacts/investigacion-hecho-desktop.png),
[documento en celular](../frontend/artifacts/investigacion-documento-mobile.png),
[evidencia insuficiente](../frontend/artifacts/investigacion-insuficiente-desktop.png)
y [contradicción en celular](../frontend/artifacts/investigacion-contradiccion-mobile.png).

Sin producción, Render, cambios de credenciales, PR #87, push, PR, merge ni despliegue.
