# KIKI Tech — Bandeja de propuestas IA guardadas

## Necesidad
El cliente probó un lote real con dos SKU (salsa de soja SKU 1,
ID 9439822 y aceite de oliva SKU 100000, ID 8021009). Ambas propuestas
quedaron generadas en PostgreSQL, pero al salir del resultado del lote se
perdió el acceso inmediato a ellas. Solo una ficha comercial, el SKU 2500400,
se había guardado como borrador, y los indicadores no distinguían claramente
estos dos tipos de almacenamiento.

## Nueva bandeja
- Ruta `/propuestas-ia`, accesible desde Inicio, menú lateral, Cola de
  mejoras, editor y Guía interactiva.
- Recupera desde `kiki_ai_editorial_drafts` **una propuesta más reciente
  por ID de variante** con prefijo `ECOMM_API:`. No mezcla borradores del
  piloto Tiendanube.
- Lista producto, SKU, ID Ecomm, propuesta más reciente y fecha de creación.
- Consulta si la misma variante **tiene una ficha comercial guardada** en
  `ecomm_api_product_edits`, y su estado. No infiere que una propuesta
  haya sido aceptada, solo que existe una edición separada.
- Buscador por SKU, ID, nombre y título generado; filtros «todas»,
  «con ficha guardada» y «sin ficha guardada»; paginación de 25 registros.
- Cada fila abre `/workspace?id=...`, donde el editor carga la propuesta
  vigente y vuelve a validar la seguridad semántica antes de mostrar botones
  para copiar texto. Si el origen cambió, el editor deberá indicar que la
  propuesta está desactualizada.
- El listado no solicita OpenAI, no modifica fichas y no publica ni
  sincroniza con Ecomm-App/ML/TN.

## Diferencia que el equipo debe comprender
**Propuesta IA generada** → guardada automáticamente como documento de IA.
**Usar este título/descripción** → coloca texto en el formulario únicamente.
**Guardar borrador / Enviar a revisión interna** → persiste campos aceptados,
estado e historial por ID de variante en PostgreSQL.
La última acción NO es publicación comercial ni aprobación definitiva.

## Verificación
1. Confirmar que backend y web estén Live en Render.
2. Abrir `/propuestas-ia` y encontrar los SKU 1 y 100000.
3. Ambos deben figurar como sin ficha comercial guardada si siguen
   sin cambios desde la prueba.
4. Abrir cada propuesta y volver a la bandeja sin usar la flecha Atrás.
5. No consumir solicitudes adicionales IA por consultarlas.
6. Revisar/corregir un campo, pulsar «Guardar borrador» y recargar
   bandeja: ahora mostrará que existe una ficha guardada; comprobar el
   historial en el editor.
7. Comprobar que el SKU 2500400 mantiene su borrador sin cambios.
8. Nunca confundir estado de propuesta con estado de publicación.

## Pendientes de próxima etapa
- Revisión por dos personas/roles y auditoría explícita de aceptación
  de propuestas IA individuales.
- Respaldo automatizado y recuperación probada de PostgreSQL.
- Flujo bulk idempotente para aplicar solo propuestas corroboradas,
  validando tipo de producto, fuente y versión.
