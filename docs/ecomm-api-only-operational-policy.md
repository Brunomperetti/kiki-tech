# KIKI Tech — Retiro de Excel Ecomm-App del flujo operativo

## Decisión obligatoria
Ecomm-App **solo mediante la API oficial**. Se prohíbe el origen de
archivo `ECOMM_APP` para comparaciones actuales, inventario,
precios o decisiones comerciales.

## Cambios entregados
- `POST /api/imports/ECOMM_APP` devuelve HTTP 410 sin procesar archivos.
- La pantalla «Importaciones» ya no ofrece cargar Excel Ecomm-App.
- Se ocultan del menú los flujos Excel históricos de Ecomm-App
  (no se eliminan físicamente registros ni tablas por seguridad).
- `GET /api/tiendanube/reconciliation`: cruce del CSV Tiendanube
  exclusivamente contra captura completa `ECOMM_APP_API_STAGE`.
  Los SKU son exactos y únicos, no familias ni parecidos. Los
  conflictos o duplicaciones quedan fuera del cruce.
- `GET /api/tiendanube/price-stock-audit`: Tiendanube CSV,
  **Ecomm-App API** para stock capturado y **MERCADOLIBRE_API**
  para precios del snapshot ML, sin volver a los Excel.
- La API pública Ecomm conectada es `inventario:leer`, con
  `total_stock` disponible al capturar la variante. No hay un
  precio confirmado en ese DTO: `ecomm_list_price=null`
  explícitamente, indicador «No disponible por API».
- Se calcula la diferencia TN/ML en un SKU con una única
  publicación API y precios válidos, pero la coincidencia
  de SKU no garantiza la misma presentación.
- Ausencia de copia Ecomm API completa = comparación
  no disponible con advertencia clara, SIN FALLBACK.
- La aplicación no actualiza stock, precio ni publicaciones.
  Cualquiera de los tres canales puede tener capturas antiguas.

## No realizado
- **No se borraron snapshots Excel históricos** ni fichas en
  PostgreSQL. Borrarlos sin un backup verificado podría causar
  pérdida de datos y romper módulos antiguos no migrados.
- Existen rutas de *legado* fuera del flujo nuevo; sus módulos
  se deben migrar o clausurar en una etapa independiente,
  nunca tratarlos como operativos.
- La conexión ML puede requerir autorización del titular
  para renovar su snapshot; sin API ML no se usa el Excel
  ML como alternativa.
- No se obtiene precio actual Ecomm-App hasta disponer
  de un endpoint oficial y credenciales compatibles.

## Pruebas recomendadas
1. Confirmar backend y frontend Live en Render.
2. Ir a Canales de venta → Comparar precios y stock.
3. Verificar `ECOMM_APP_API_STAGE` y fecha de captura.
4. Confirmar que el precio Ecomm dice «No disponible por API»,
   no un número tomado del Excel.
5. Comprobar stock Ecomm API y precio TN/ML cuando haya
   correspondencia única. Verificar que el listado ML sea
   API, y si falta se muestre «Sin snapshot ML».
6. Probar que la importación XLSX Ecomm ya no figura y
   que POST directo devuelve HTTP 410.
7. Comprobar que los borradores de KIKI siguen intactos.
