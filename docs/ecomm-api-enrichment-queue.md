# KIKI Tech — Cola de mejoras API (fase 1, sin gasto en IA)

## Necesidad real
El catálogo Ecomm-App registra más de 3.000 variantes. La ficha individual y el
asistente IA ya funcionan, pero no son suficientes para entregar un proceso
utilizable por los operadores del catálogo. Hace falta triage, prioridades y una manera
ordenada de seleccionar muchos productos para revisar.

## Fuente de verdad y límites
- Identidad **únicamente** `ECOMM_APP_API_STAGE`, copia íntegra tomada desde la
  API Ecomm-App: ID de variante, SKU, nombre, GTIN informado, flag combo.
- Borradores y títulos/marcas propuestas provienen **únicamente** de la tabla
  `ecomm_api_product_edits` en PostgreSQL.
- Nunca toma `ECOMM_APP` ni `ECOMM_APP_RAW` históricos del Excel.
- No consulta ML/TN ni interpreta estados de publicación. No genera IA y no
  modifica externos. Las selecciones son organización, NO aprobación.
- Datos API capturados: **no es stock, precio, enlace ni actualización en vivo**.

## Funcionalidades
- `GET /api/ecomm-app/workspace/queue?q=&filter=&page=&limit=`
  autenticado y solo de lectura.
- Contadores de variantes, sin trabajar, borradores y listas para revisión
  interna, con recuento por motivo.
- Filtros: identidad ambigua, borradores, preparados, sin trabajar,
  combos/packs, sin título propuesto, sin marca KIKI, sin descripción,
  sin GTIN informado. **Un producto puede figurar en varios motivos**.
- Priorización: anomalías de identidad, borradores que pueden continuar,
  packs y luego otros productos. Los contadores cambian con los datos,
  no son valores históricos fijos.
- Búsqueda por ID, SKU, nombre, título y marca propuesta.
- 25 variantes por página, con paginación y accesos directos a la ficha.
- Seleccionar registros **de la página visible** y exportar una planilla CSV
  de seguimiento (contiene ID, SKU, estado, motivo, borradores).
  No selecciona miles de filas invisibles por accidente; al cambiar de
  filtro o página se borra la selección.
- Sanear campos CSV que podrían interpretarse como fórmulas al abrir Excel.

## Comprobaciones
1. Esperar Render Live del backend y web, visitar `/queue`.
2. Verificar que el total de variantes coincide con la captura completa API.
3. Comprobar que SKU 2500400 está en packs, borradores y sin GTIN si así
   corresponde a la fuente. La modificación guardada en KIKI permanece.
4. Abrir la ficha del SKU 2500400 desde la cola y verificar historial.
5. Probar filtros, páginas y búsqueda; exportar dos casos seleccionados;
   comprobar que el CSV se abre en Excel sin perder el SKU como texto.
6. Verificar que no hay solicitudes OpenAI ni alteraciones en ML, TN, Ecomm.

## Próxima etapa (no implementada aquí)
- Propuestas **por lote con costo y cuota explicitados antes de ejecutar**.
- Calificación por grado de evidencia y exclusión de combos/conflictos.
- Aprobación/rechazo masivo auditado con optimistic locking de variantes.
- Publicación controlada e idempotente en canales con API escritura autorizada.
- Backups programados de PostgreSQL antes de cualquier operación masiva.

No presentar esta PR como "publicación masiva lista" ni "IA masiva".
Es una etapa operativa de organización de catálogo y selección segura.
