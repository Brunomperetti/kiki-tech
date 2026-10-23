# Ecomm-App API — Copia completa de prueba, aislada y reanudable

**Contexto:** el 23/10/2026 se validó contra Ecomm-App `inventario:leer`: 3.121 productos padre declarados, 63 páginas a 50, primera auditoría de 100 padres / 100 variantes, 19 padres combo, sin ID/SKU/stock ausentes ni identificadores repetidos en esas dos páginas. Son cifras de la *muestra y metadatos* de la API; no una lectura completa.

## Separación estricta de datos

- `ECOMM_APP`: catálogo **histórico operativo** de KIKI desde Excel; se conserva íntegro.
- `ECOMM_APP_RAW`: evidencia histórica por canales; se conserva íntegra.
- `ECOMM_APP_API_STAGE`: copia **nueva, provisional**, aislada, por páginas. **NO** es fuente del reconciliador, no activa vínculos ni realiza cálculos de stock operativo.
- Mercadolibre, Tiendanube, decisiones de duplicados, historial, GTIN, IA y facturación: sin cambios.

Se utiliza la tabla existente `catalog_snapshots`, bajo un `source` **diferente**. No hay migración ni alteración destructiva.

## Cómo probar tras aprobar PR y desplegar Render

1. Abrir KIKI Tech > **Importaciones** > Ecomm-App.
2. Expandir **Crear una copia completa de prueba del catálogo por API**.
3. Pulsar **Preparar copia de prueba (solo lectura)**. La interfaz consulta 3 páginas por bloque y muestra los contadores actualizados.
4. Puede pausarse al terminar el bloque, abandonar la página o recargarla. La siguiente ejecución empieza donde quedó el bloque persistido.
5. Al terminar debe mostrar **3.121 productos padre y 63 páginas** si el total en Ecomm-App sigue igual, más el recuento real de variantes y combos. **No asumir 3.121 variantes.**
6. Si falta un ID, SKU o stock, se verá como observación. Si cambia el total, falta una página, aparece un ID de variante repetido o falla una petición, se **detiene el bloque sin guardarlo**, y conserva el avance previo.
7. Una copia terminada **no significa que esté aprobada**. Antes de promover el origen a reconciliación necesitaremos comparar identificadores reales e históricos, duplicados de SKU, disponibilidad de GTIN y asociaciones con canales, y establecer procedimiento de rollback.

## Seguridad técnica

- Solo usa el endpoint autorizado `GET /api/v3/public/inventario/productos?page=...&limit=50&sort=sku_asc`.
- Auth `inventario:leer` únicamente, desde backend con `ECOMM_APP_API_TOKEN` en Render.
- Endpoint KIKI `GET /api/ecomm-app/stage/status`: progreso sin datos de inventario.
- Endpoint KIKI `POST /api/ecomm-app/stage/next`: sesión + CSRF, hasta 3 páginas por petición, serialización compacta de producto/variantes/stock y persistencia atómica de cada bloque.
- El navegador puede ejecutar bloques consecutivos por un clic explícito, sin tarea en segundo plano; botón de pausa.
- Límite de la API del proveedor: 120 consultas/minuto. El proceso es secuencial y acotado; no hay concurrencia desde la UI.
- Guarda IDs de variantes, SKU, indicador combo, stock, depósitos y descripción (no descarga fotografías ni guarda tokens).
- Contadores de calidad y posible duplicidad: sin IDs, sin SKU, sin total de stock, IDs duplicados y SKU repetidos.
- Verificación de `page`, `total`, `per_page` y `total_pages` por página; se frena si el proveedor cambia estas cantidades a mitad del recorrido.

**Límite conocido:** aunque `total` permanezca constante, los productos podrían haber cambiado de posición durante la lectura paginada. La copia de prueba no certifica una vista perfectamente consistente; debemos contrastarla antes de utilizarla como fuente operacional.

No se puede reiniciar una copia completada desde la interfaz de este primer piloto. Eso se diseñará como una acción explícita y confirmada, sin tocar las fuentes históricas.
