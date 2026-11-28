# Circuito comercial integral — activación bajo revisión

Base de esta rama: `main` `1eb1116` (incluye #223 y Tiendanube API #225–#230).
Se recupera el trabajo local de E4; no se reemplazan catálogo, editor, integraciones ni colas.

## Recorrido implementado

1. Seleccionar hasta 20 Ecomm ID de la captura API completa → Operaciones → Investigar y completar.
2. Comprobar disponibilidad y confirmar el lote. El buscador entrega referencias, no hechos aprobados. Sólo una fuente candidata de un dominio autorizado puede incorporarse sin selección adicional; las ambigüedades exigen elegir la URL y justificarla.
3. La cola existente conserva identidad, versión, original, SHA-256, citas, intentos, cuota y resultados. El navegador solicita pasos secuenciales: cerrar o pausar detiene los siguientes; el trabajo queda recuperable. No se anuncia un trabajador autónomo de investigación inexistente.
4. Si un original venció, la comprobación autorizada de esa URL conserva el documento y las decisiones cuando los bytes son idénticos. Si cambiaron, archiva una versión nueva, invalida respaldos anteriores y requiere revisión; no supera el máximo existente de ocho versiones ni acepta comprobantes de otro paso.
5. Revisar procedencia, identidad y hechos PENDING en Evidencias. Después, «Preparar propuestas desde hechos revisados» reutiliza el generador determinista. No aprueba hechos, no sobrescribe fichas y no invoca OpenAI automáticamente.
6. Revisar categorías internas y equivalencias por canal en el catálogo versionado; aprobar por variante o lote. Un cambio de vocabulario invalida sugerencias anteriores. Una clasificación comercial humana no es una afirmación del fabricante.
7. Revisar los 18 campos, valores anteriores/propuestos, límites y citas. Seleccionar campos, confirmar y guardar DRAFT mediante el editor PostgreSQL existente. CAS/409 y transacción atómica preservan cambios concurrentes.
8. Registrar imágenes/videos exactos, presentación, alt, fuente, documento/hash, autorización y vigencia. Una URL pública no prueba derechos. Previsualización remota sólo por acción explícita y recurso autorizado; nunca cargas automáticas.
9. Preparar y descargar paquetes comerciales por canal con sus bloqueos. El envío TN es una autorización independiente, desactivada por defecto.

## API reutilizada/adaptada

- `/api/ecomm-app/workspace/research/automation`: crear/listar; `/{id}`, `/{id}/step`, `/recover`, `/retry`, `/cancel`, `/select-source`, `/proposals`; `/capabilities` describe disponibilidad efectiva sin consultar proveedores.
- `/commercial-review/preview` y `/commercial-review/apply`: revisión explícita por campo de hasta 20 propuestas existentes, sin segunda persistencia.
- `/taxonomy/catalog`, `/taxonomy/review-preview`, `/taxonomy/review-batch`; clasificación individual existente preservada.
- `/{ecomm_id}/commercial-coverage`, `/{ecomm_id}/media-review` y revisión documental/multimedia existente.
- `/reports/periodic/policy`, `/tasks`, `/automation`: programación, pendientes y diagnóstico automático real.
- `/channels/tn/submissions`: previsualización/registro y envío explícito. Véase [contrato y restricciones TN](CONTROLLED-TIENDANUBE-SUBMISSIONS.md).

## Configuración nueva, sin modificar el entorno productivo

| Variable | Valor seguro inicial | Alcance |
|---|---|---|
| `KIKI_RESEARCH_SEARCH_ENABLED` | `false` | No buscar por desplegar código |
| `KIKI_RESEARCH_SEARCH_PROVIDER` | `BRAVE` | Adaptador HTTPS acotado |
| `KIKI_RESEARCH_SEARCH_API_KEY` | vacía | Sólo gestor de secretos; nunca código, chat o registros |
| `KIKI_RESEARCH_SEARCH_MAX_REQUESTS` | `20` | Límite por lote, hasta 20 |
| `KIKI_RESEARCH_SEARCH_DAILY_REQUESTS` | `20` | Cuota global persistente UTC, máximo configurable 200 |
| `KIKI_MONTHLY_REVIEW_ENABLED` | `false` | Diagnósticos en el ejecutor existente, no otro servicio |
| `KIKI_TIENDANUBE_WRITES_ENABLED` | `false` | Escritura externa independiente de lectura/previsualización |

Se conservan todos los requisitos previos: espacio documental, esquema ya instalado, lector de producción con kernel guard y salud efectiva, flags de incorporación y dominios exactos autorizados, TLS/DNS/robots, límites de tamaño y permisos del sitio. La búsqueda no debe empezar si el lector no está disponible. El caso `.aspx?id=<entero positivo>` conserva la consulta exacta; no habilita parámetros arbitrarios ni redirecciones.

Brave puede tener cargos según la cuenta y tarifa del propietario. La cuota limita solicitudes; no equivale a un presupuesto monetario acreditado. No se crean cuentas ni servicios pagos. No se reutiliza la clave OpenAI para búsquedas. El presupuesto OpenAI histórico permanece intacto; sus créditos son independientes de Codex. El circuito automático aquí es determinista; el generador OpenAI existente conserva sus permisos, cuota y restricciones, y no se considera reparado un HTTP401 por cambiar esta rama.

## Revisión periódica automática

Además de la política guardada, exige `KIKI_V2_ENABLED`, el ejecutor editorial existente habilitado y `KIKI_MONTHLY_REVIEW_ENABLED`. Evalúa como máximo cada hora y crea un diagnóstico según el intervalo configurado (1–30 días, sin superar el mínimo mensual), con exclusión mutua PG, checkpoint, idempotencia e historial. No crea usuarios/sesiones, aprobaciones de hechos, ACK humanos ni publicaciones. Detecta cambios en capturas/documentos archivados, vencimientos, nuevos productos y fichas incompletas. **No es un rastreador periódico de Internet**: consultar nuevamente un fabricante sigue sujeto al circuito autorizado y sus límites. La revisión editorial de 30 días no se extiende por cambiar esta política.

## Persistencia y despliegue posterior

Sin DDL nuevo: se reutilizan `CatalogSnapshot`, `SourceIntakeJob`, expedientes/documentos/propuestas y editor; envíos TN usan el registro `ImportJobRecord`. No se ejecutan migraciones. Si faltan tablas históricas, detener la activación y seguir el preflight/migración previamente revisado; no crear tablas automáticamente sobre producción.

1. Revisar PR y CI, respaldo/restauración y esquema del destino antes de autorizar producción.
2. Controlar los despliegues automáticos y desplegar sólo bajo autorización separada. Mantener las nuevas capacidades OFF.
3. Verificar catálogo API auténtico, sesiones/CSRF, editor/historial y capturas ML/TN sin ejecutarlas desde esta entrega.
4. Autorizar dominios exactos, condiciones de uso, proveedor y cuotas; configurar secretos por su propietario. Activar primero lectura/investigación con un lote pequeño y revisar originales.
5. Activar informes automáticos por separado. Activar escrituras TN sólo tras revisar paquete/identidad/permisos y validar un caso autorizado.
6. Reversión: desactivar primero nuevos flags; pausar/cancelar pendientes. No borrar originales, historial, fichas ni registros de envío. Un envío RUNNING/UNKNOWN exige consultar el proveedor antes de considerar otro intento.

## Límites de aceptación real

- [Referencia Coopar](reference-candidates/coopar-blue-patna.json): datos declarados por el usuario; EAN con checksum válido. No se descargó su página ni se acreditó la relación fabricante/producto. No se creó una variante ni se aprobaron datos de ese caso.
- Los ensayos usan PostgreSQL descartable y documentación/transportes sintéticos identificados; no prueban derechos reales ni aceptación de Guillermo/Mercedes.
- Natural Seed incompleto conserva DRAFT y bloqueos; no se transfieren aprobaciones de unidad a pack ni por GTIN repetido.
- ML conserva la previsualización existente y su método de validación oficial; sin payload/seller/permisos validados no se afirma validación oficial exitosa.
- TN crea ocultos y actualiza únicamente contenido expresamente admitido por el cliente existente. SEO, multimedia y taxonomía se conservan en el paquete revisado; no se inventan contratos remotos para enviarlos.
