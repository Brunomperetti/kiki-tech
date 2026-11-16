# KIKI Tech 2.0 — Validación documental antes de declarar una ficha lista para canales

Estado: **código en PR #172, desactivado, no desplegado**. La prueba de integración utiliza documentos **ficticios** y una base descartable. Este gate **no certifica todo el contenido**: controla la existencia y vigencia del respaldo primario para **identidad (nombre y presentación)**. Faltan aprobaciones específicas de marca, atributos adicionales, categoría/subcategoría, propiedad/licencia de recursos multimedia y revisión de políticas comerciales.

## Brecha que cierra

El editor original admite una fuente `FABRICANTE` con `verified: true`, texto de nota y URL ingresados por un operador. Eso es una declaración manual que NO acredita que el servidor haya guardado un original íntegro, que la identidad concuerde con la variante o que existan hechos citados y aprobados. Por eso se añadió `channel_readiness_guard.require_primary_evidence()` y se protege tanto `save(status=READY_FOR_CHANNELS)` como `confirm_monthly_review()`.

### Opt-in para un único producto, apagado por defecto

- `KIKI_DOCUMENT_CHANNEL_GUARD_ENABLED=false`
- `KIKI_DOCUMENT_CHANNEL_GUARD_PILOT_ID=`
- Requiere también `KIKI_DOCUMENT_WORKSPACE_ENABLED=true` con tablas documentales migradas y control transaccional.
- Los registros fuera del Ecomm ID piloto conservan exactamente el flujo actual. Si el gate está activado para el ID piloto y falta sesión, esquema o control, **se rechaza**, no se admite automáticamente la ficha.

**No habilitar ni migrar producción sin validación del backup real y autorización de despliegue.**

## Requisitos del gate para ese Ecomm ID

1. Fuente comercial `FABRICANTE` marcada por operador `verified: true`, con URL HTTPS **idéntica** a la URL de referencia del original guardado. La marca manual sola nunca basta.
2. Archivo de tipo `FILE`, con contenido original íntegro (`original_base64`), tamaño y SHA-256 consistentes y `provenance` atada al mismo hash. Sin documento de demostración ni referencia URL sin descargar.
3. Documento guardado exactamente para el Ecomm ID, versión y firma correctas, `parse_status=TEXT_EXTRACTED`, sin bloqueos del lector y procedencia `REVIEWED` por operador con motivo registrado.
4. Identidad Ecomm ID+SKU+tipo/presentación sin contradicciones, o diferencia nominal registrada mediante conciliación explícita vigente para **esa versión** documental. Nunca se acepta un EAN contrario.
5. Hechos `product_name` y `presentation` con aprobación individual vigente, sin bloqueos ni cambio del documento. La presentación de la ficha y sus títulos cortos/largos coinciden con estos valores.
6. No se escribe a Ecomm-App, Mercado Libre, Tiendanube ni precios/stock. El gate solo permite o rechaza un **estado interno**.

## Revocaciones y revisión mensual

Si luego la procedencia se revoca o el documento cambia, no se reescribe silenciosamente el historial de la ficha `READY_FOR_CHANNELS`. Al abrirla con sesión, la respuesta incorpora `documentary_gate` y modifica la **readiness efectiva** a no lista, con falta `documentary_primary_source` y aviso en UI. La confirmación mensual queda bloqueada hasta restaurar respaldo válido.

No interpretar estado histórico como disponibilidad de publicación. **La preparación por canal y cada dato comercial deben tener controles de publicación propios**; este piloto no habilita publicación.

## Pruebas en SQLite descartable

- Fuente `verified=true` sin original revisado: bloqueo.
- Falta de sesión, modificación del original, cambio de URL, cambio del SKU o presentación, documento sintético, fuente pendiente, títulos discordantes: bloqueo.
- Documento ficticio **con bytes, hash, revisión, conciliación y hechos vigentes**: guardado interno permitido solo en el caso sintético de aceptación.
- Revocación posterior: consulta devuelve `documentary_gate.ready=false`, la revisión mensual y nuevo guardado `READY_FOR_CHANNELS` se bloquean.
- Con gate apagado: el editor actual mantiene su comportamiento y no se introducen requisitos sobre el resto de las variantes.
- Tests complementarios de CI: frontend y PostgreSQL 18 en entorno sintético.

## Pendientes antes de aceptar el cliente

- Restaurar copia auténtica del backup y probar migraciones/rollback fuera de producción.
- Importar o consultar **legítimamente** el HTML/PDF original de fabricante real; comprobar permiso de acceso y verificar identidad Ecomm ID+SKU.
- Aprobar todos los hechos que se incorporen a la ficha, validar taxonomía interna, medios y permisos de uso, SEO y coherencia por canal.
- Agregar comprobaciones similares de trazabilidad para atributos adicionales, categorías, imágenes y vídeos sin bloquear sin criterio los 2.781 productos existentes.
- Definir el plan de activación gradual y el informe de revisión mensual de procesos/automatizaciones pactado, sin confundirlo con la obligación de verificar manualmente miles de fichas cada mes.

Plan de aceptación comercial: https://github.com/Brunomperetti/kiki-tech/issues/174.
