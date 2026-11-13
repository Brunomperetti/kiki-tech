# MAMA — Actualización de procedencia autorizada

Base comprobada: `feature/kiki-tech-2-dashboard`,
`60f346e61b9db6dbb4195b58a250ded3f1e370e2`, árbol inicialmente limpio.

## Excel: original comprobado externamente

El usuario confirma que `productos.xlsx`, hoja `Sheet1`, fila 37 y SHA-256 fueron
comprobados **fuera del entorno de Codex**. El archivo sigue sin estar disponible
localmente. Se registra la confirmación externa; no se atribuye a Codex una lectura
del archivo, recálculo de su hash ni verificación independiente de las celdas.

| Campo | Celda | Dato |
| --- | --- | --- |
| Nombre | B37 | Fideos De Arroz Mama 10mm 350g |
| Marca | Y37 | Mama |
| SKU del archivo | Q37 | `fideos 10mm Mama` |
| EAN declarado | R37 | `8851876201433` |
| Peso logístico | L37 | 0,4 kg; no es contenido neto |
| Descripción comercial | U37 | Vacía |
| Título SEO | W37 | Vacío |
| Descripción SEO | X37 | Vacía |

Presentación/ancho declarados: 350 g y 10 mm, en la denominación informada.

SHA-256 del original, con verificación externa confirmada por el usuario:
`03c6b219335ee1dad31f8bc2c1cbd51d12f416fbe25bd9a26ece8350c30c414f`.

Se conserva `original_file_available:false`, junto con
`EXTERNALLY_VERIFIED_ORIGINAL_NOT_IN_CODEX` y una verificación de alcance
`EXTERNAL_TO_CODEX`, `verified_in_codex:false`. No se inventa una fecha de la
comprobación externa. El Excel sigue siendo una referencia auxiliar del cliente;
la verificación del archivo no lo convierte en fuente oficial del fabricante ni
en catálogo operativo Ecomm-App.

## Referencias separadas

**Fabricante: Thai President Foods, referencia oficial candidata.**

`https://www.mama.co.th/en/products-export-brand-list/21/34/Instant-Rice-Vermicelli`

Ítem informado: «Mama Rice Noodles 350g (10 Mm.)». Se conserva la referencia para
350 g / 10 mm, sin consulta o descarga en Codex, sin fecha de consulta ni hash de
contenido del sitio y sin confirmar oficialmente el EAN.

**Tercero: Barcode-List, evidencia secundaria no oficial.**

`https://barcode-list.com/barcode/EN/Search.htm?barcode=Rice`

Registros que el usuario informa asociados a `8851876201433`:

- «Mama Rice Noodles 350g».
- «MAMA RICE NOODLE 350G 10MM».

Se conserva exactamente la URL suministrada, identificada como página de
resultados de búsqueda, no como ficha individual permanente. No se visitó ni se
obtuvo una copia. Los nombres y la asociación son información comunicada por el
usuario, pendientes de revisión. Clasificación: `NON_OFFICIAL`. No acreditan
composición, origen oficial del EAN, Ecomm ID auténtico ni hechos comerciales.
No se añaden estos nombres a las reglas de coincidencia de identidad.

## Persistencia e historial

Se reutiliza el POST existente `/api/test-commercial-pilot/mama-350/prepare`, con
cuerpo `{}`, sesión y CSRF. No se agregan rutas, servicios o tablas.

- Un expediente nuevo registra la procedencia actual desde su creación.
- En un expediente de la base 60f346e, ese POST agrega
  `MAMA_PILOT_PROVENANCE_UPDATED`, con referencias, hash nuevo y hash previo.
  Conserva el registro original, autor, fecha del evento e historial.
- Repetir el POST con la misma procedencia no agrega eventos ni versiones.
- El GET informa la última versión registrada y conserva la ficha inicial del
  primer evento; no aplica automáticamente la actualización de procedencia.
- No se modifican campos comerciales, versiones del editor, documentos,
  revisiones de fuentes ni estados de hechos. La actualización no aprueba datos
  ni genera propuestas. Se mantiene el identificador
  `PILOT-MAMA-350-SYNTHETIC` y el Ecomm ID auténtico nulo.

Persistencia exclusivamente en PostgreSQL descartable, con aislamiento previo
al engine y controles existentes. Al retirar la base tmpfs se pierden sus datos;
el código conserva la procedencia autorizada para preparar otra sesión de pruebas.

## Pendientes y preservación

Siguen pendientes el Ecomm ID auténtico, la correspondencia oficial del EAN,
ingredientes, alérgenos y nutrición. La composición y propiedades como «sin gluten»
no se infieren. Los campos comerciales y la propuesta siguen bloqueados sin
hechos aprobados suficientes; el procedimiento documental y de vinculación de
[la etapa 2J](MAMA-PILOT.md) permanece vigente.

No se modifican el catálogo maestro, integraciones, credenciales, OAuth, contratos
productivos, modelos productivos, red, listas de dominios, Render ni OpenAI.
Sin búsquedas externas, consultas a los enlaces, publicaciones, push, PR, merge o
despliegue.

## Archivos

- `backend/integration_sandbox/mama_reference.py`: procedencia y referencias.
- `backend/integration_sandbox/mama_routes.py`: actualización versionada mediante
  el contrato existente, conservando el estado inicial.
- `backend/integration_sandbox/mama_checks.py`: datos, separación de fuentes,
  migración, idempotencia y preservación de la ficha/evidencias.
- `frontend/src/integration/MamaPilot.tsx` y `mama-pilot.ts`: visualización del
  alcance externo de la verificación, celdas y evidencia no oficial.
- `frontend/integration-tests/zzzzzmama.spec.ts`: comprobación del recorrido y
  procedencia sin solicitudes externas ni aprobaciones automáticas.
- Este documento y la nota de actualización en `integration/MAMA-PILOT.md`.

## Validación de esta actualización

- `python3 integration/run.py test`: **117 pruebas aprobadas**, incluidas las de
  PostgreSQL, autenticación, aislamiento y actualización de procedencia sobre el
  registro anterior, con preservación de ficha y evidencias e idempotencia.
- Playwright de integración, `zzzzzmama.spec.ts`: **6 pruebas aprobadas**, tres
  recorridos en escritorio y celular. Comprueban procedencia, bloqueos sin
  documentos, identidad sintética, seguimiento persistente y ausencia de
  solicitudes externas.
- TypeScript, build del modo demo y build de integración: aprobados. El build del
  demo mantiene el aviso de tamaño del bundle, sin errores.
- Ruff y su comprobación de formato: **43 archivos aprobados**. Prettier de los
  tres archivos TypeScript modificados y `git diff --check`: aprobados.
- Sin cambios en servicios productivos, configuración de red o aislamiento ni
  código del modo demo. Las capturas generadas por las pruebas no se incluyen en
  esta actualización de procedencia.

Los contenedores y volúmenes descartables de estas pruebas se retiraron al
finalizar; no queda una base de pruebas encendida ni persistencia externa. El
registro autorizado se prepara nuevamente con el contrato existente en la
siguiente sesión aislada.
