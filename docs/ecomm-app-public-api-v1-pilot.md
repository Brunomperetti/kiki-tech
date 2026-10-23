# KIKI Tech — Piloto API pública Ecomm-App v1.0

**Fuente:** documentación OAS 3.0 facilitada por el usuario el 23/10/2026. **Conexión real pendiente de credencial y prueba en Render.**

## Alcance confirmado por el proveedor

- Host fijo producción: `https://admin.ecomm-app.com`.
- Inventario **solo lectura**: scope `inventario:leer`.
- `GET /api/v3/public/inventario/depositos`: depósitos activos e ID.
- `GET /api/v3/public/inventario/productos`: productos, variantes y stock por depósito. Parámetros: `q`, `sku`, `barcode`, `low_stock`, `warehouse_id`, `page`, `limit` (máximo 50), `sort` (`sku_desc`, `sku_asc`, `stock_desc`, `stock_asc`).
- `POST /api/v3/public/inventario/productos/consulta`: **consulta** exacta de hasta 100 SKU. El piloto lo limita a 3. Se usa este endpoint para SKU que contengan barras, espacios, + y #. No escribe datos.
- Éxito: `{"data": ...}`; error: `{"error":{"code","message"}}`.
- Token privado en `Authorization: Bearer ...`. Se muestra una sola vez, no expira, se revoca manualmente y los scopes son reevaluados por request.
- 120 consultas/minuto por token. **El piloto hace máximo dos requests al probar la conexión**, o una consulta acotada de SKU; no hace sincronizaciones automáticas.

El módulo **Facturación** (`facturacion:leer`, `facturacion:emitir`) queda expresamente fuera del alcance del piloto.

## Configuración inicial

1. En Ecomm-App, crear una clave `KIKI Tech - Stock Lectura` con únicamente `inventario:leer`. Copiar el token una sola vez; **no pegarlo en ChatGPT, GitHub, frontend, capturas ni documentos**.
2. En el servicio de **backend** de Render, agregar variable secreta `ECOMM_APP_API_TOKEN` con el token. El valor no debe quedar en `.env` versionado ni en el build del frontend.
3. Revisar Render Live y abrir KIKI > **Importar archivos** > **Ecomm-App · Conexión directa de inventario**.
4. Pulsar **Probar conexión y leer 3 productos**. KIKI consulta solo depósitos y primera página limitada de productos; no guarda ni sobrescribe ninguna tabla.
5. Verificar que el panel muestre campos presentes en la respuesta, productos, variantes y desglose de stock. Si indica formato desconocido, tomar captura de los nombres de los campos (no secretos), para mapear correctamente el DTO sin suposiciones.
6. Opcional: consultar **VITANERALVAINILLA** y **VITANERALCHOCOLATE** usando el POST de lectura para verificar los datos reales de inventario.
7. **No ejecutar todavía** importación total, reconciliación basada en datos API ni habilitar escritura.

## Siguiente fase (NO implementada en este PR)

- Confirmar los campos concretos del DTO `ProductosPorSkuDto` en producción antes de definir mapeo permanente.
- Hacer una sincronización en snapshot independiente `ECOMM_APP_API_PREVIEW` y comparación de cobertura/ID/SKU/GTIN/depósitos contra XLSX histórico; **nunca** reemplazar `ECOMM_APP` o `ECOMM_APP_RAW` con un resultado parcial.
- Confirmar si otros recursos ofrecen relaciones Ecomm/ML/Tiendanube: **no aparecen en los tres endpoints de inventario compartidos**. No inventar vínculos.
- Manejar paginación, consistencia temporal, faltantes por SKU y controles de calidad, rollback y trazabilidad.
- Aprobación explícita antes de cambiar la fuente de reconciliación.

## Manejo de errores

- `401`: token no válido.
- `403 SCOPE_INSUFICIENTE`: revisar `inventario:leer`.
- `403 PLAN_SIN_STOCK`, `PLAN_NO_HABILITADO`, `API_PUBLICA_NO_HABILITADA`: solicitar habilitación del plan/permisos a Ecomm.
- `402 SUSCRIPCION_VENCIDA`: renovar la cuenta.
- `429`: límite temporal; no se reintenta automáticamente desde este piloto.
- `404 DEPOSITO_INEXISTENTE`: error, nunca interpretar como stock cero.
- Formato JSON extraño o respuestas muy grandes: detener piloto e investigar.

**Política:** el token solo sale desde el backend hacia el host fijo del proveedor. No se loguea, no vuelve al navegador y no se guarda en la base de KIKI.
