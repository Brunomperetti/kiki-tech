# KIKI Tech — preparación de integración Ecomm-App API

**Estado: contrato pendiente de confirmar con Ecomm-App. No se han confirmado endpoints, esquemas, autenticación, webhooks ni permisos de escritura.**

## Objetivo
Reemplazar las exportaciones manuales del catálogo por una ingesta confiable de datos desde Ecomm-App y conservar la trazabilidad de reconciliación Ecomm / Mercado Libre / Tiendanube.

Ecomm-App es la fuente operativa de inventario; KIKI Tech audita y sugiere decisiones. En la primera fase **solo leemos**.

## Información que debemos confirmar con el equipo técnico

| Dato | Necesidad de KIKI | Confirmación pendiente |
|---|---|---|
| Producto | ID estable en Ecomm, nombre, SKU principal o madre, marca/categoría y estado | Endpoint, tipos, paginación y cambios |
| Variantes | ID de variante, SKU individual, sabor/presentación, GTIN individual | ¿Un producto tiene una o muchas variantes? |
| Inventario | Stock por SKU/variante y por depósito/sucursal; fecha de actualización | ¿Saldo disponible, reservado o físico? |
| Precios | Precio de lista y precio por canal, moneda e impuestos | ¿Qué campo usa el e-commerce? |
| Publicaciones vinculadas | Canal, MLA y variation_id ML si existe, ID/variante TN, SKU vinculado | ¿Se puede obtener asociación sin ambigüedad? |
| Familias/combos | SKU base, SKU de combo, productos incluidos y unidades | ¿Existe relación explícita o es convención de nombres? |
| Cambios incrementales | updated_at, cursor de cambios o webhooks | ¿Cómo evitar recorrer el catálogo completo cada hora? |
| Acceso | Token/autenticación, permisos granulares, sandbox y rate limit | ¿Acceso restringido a lectura disponible? |

**Nunca asumir que un MLA identifica por sí solo una variación.** Si se usa una publicación con varias variantes, requerir IDs y SKU de cada variación. **Nunca utilizar una coincidencia por familia de SKU para descontar stock.**

## Primer despliegue (sin escrituras)
1. Credenciales solo en backend de Render, nunca en React, archivos versionados, capturas o logs.
2. Consultar metadatos y **una página pequeña** de productos; registrar cantidad/fecha, no tokens.
3. Guardar respuesta en un nuevo snapshot de staging `ECOMM_APP_API_PREVIEW`, **sin sobrescribir ECOMM_APP ni ECOMM_APP_RAW**.
4. Mapear IDs estables, SKU de producto, SKU de variante, GTIN, stock y precios con validación explícita de nulidad y formato.
5. Comparar contadores, productos y 10 casos reales contra la última importación XLSX. Analizar diferencias de variante, stock y asociadas ML/TN.
6. Mostrar reporte de diagnóstico: total obtenido, paginación, duplicados de ID, campos vacíos, referencias sin padre, latencia/frescura.
7. Solo tras validar y con aprobación humana habilitar el cambio de fuente de lectura para reconciliaciones futuras. Mantener rollback inmediato al snapshot de Excel.
8. **Escrituras externas y sincronización de stock** son una fase posterior, con permisos separados, dry run, confirmación explícita por lote, idempotencia, auditoría y reversión.

## Casos de aceptación mínimos
- Vitaneral Vainilla y Chocolate no se mezclan por alias `VITANERAL`. Los stocks se atribuyen a IDs de variante distintos.
- `5028`, `5028000` y `5028999` se reconocen como familia comercial potencial, **no** como la misma variante física.
- Diferentes publicaciones ML del mismo SKU mantienen sus MLA/precios; variaciones solo si existe un ID verificable.
- Ecomm-App informa explícitamente qué canal está vinculado a cada variación; si la API no lo provee, KIKI marca «no verificable».
- Falta de campo, servicio caído, 401/403, rate limit o paginación parcial NO borran el último snapshot confiable.

## Preguntas de cierre para la reunión
- ¿Cuál es la documentación y URL base oficial? ¿Qué versión es estable?
- ¿Cómo conseguir credenciales de **solo lectura** para KIKI Market y quién las autoriza?
- ¿Hay endpoint de **productos + variantes + stock + vinculaciones con los canales**?
- ¿Se permite consulta incremental y cómo funcionan los límites de API?
- ¿Hay ambiente de pruebas o datos ficticios? ¿Cómo saber cuándo los datos están actualizados?
- ¿Cuáles operaciones de escritura existen para una fase futura y qué validaciones exige Ecomm-App?

**No implementar llamadas reales hasta disponer de respuestas y credenciales autorizadas.**
