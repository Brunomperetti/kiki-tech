# KIKI Tech — Conciliación PRELIMINAR API Ecomm ↔ API Mercado Libre

## Estado
Diagnóstico exclusivamente de lectura; NO reemplaza el reconciliador histórico
ni confirma asociaciones entre canales. El catálogo Ecomm se lee únicamente de
`ECOMM_APP_API_STAGE` (captura API completa). Mercado Libre se lee únicamente
de `MERCADOLIBRE_API` (último snapshot generado por su integración).
No hay fallback al Excel de Ecomm (`ECOMM_APP`, `ECOMM_APP_RAW`) ni al
archivo Excel ML (`MERCADOLIBRE`).

## Acceso
`GET /api/ecomm-app/stage/ml-reconciliation-preview`, sesión autenticada,
solo lectura de PostgreSQL, sin llamadas remotas ni escrituras.
Botón manual en `/pilot`, apartado 3.

## Clasificación
- `SKU_GTIN_AGREE_REVIEW`: SKU de variante exacto y GTIN válido coincidente;
  aún exige verificación de correspondencia real de publicación y variante.
- `SKU_ONLY_REVIEW`: SKU exacto sin corroboración suficiente de GTIN.
- `SHARED_GTIN`: GTIN repetido entre varios IDs Ecomm.
- `GTIN_CONFLICT`: SKU exacto con códigos GTIN válidos distintos.
- `PRESENTATION_CONFLICT`: diferencias de sabor/presentación conocidas.
- `INVALID_ML_GTIN`, `INVALID_ECOMM_GTIN`: identificador no verificable.
- `DUPLICATE_API_SKU`: SKU API asignado a múltiples variantes.
- `SKU_NOT_IN_API`: no coincide con ningún SKU exacto en copia API.
- `NO_EXPLICIT_VARIANT_SKU`: ML no aporta SKU de variante.
- `PRODUCT_SKU_ONLY`: existe pista por SKU general, no confirma variante.

Un SKU compartido por varios MLA no demuestra duplicación, ni que sus
variaciones deban fusionarse. La coincidencia de familia SKU (ej.
5028/5028000/5028999) nunca se interpreta como identidad física ni stock.

## Requisitos antes de conciliar operativamente
1. Reautorizar o verificar el estado de Mercado Libre y sincronizar un
   snapshot reciente. Al momento de la captura facilitada, la última fecha
   visible era **5/10/2026** y la conexión aparecía sin comprobar.
2. Recapturar Ecomm por API con consistencia, control de versionado/frescura.
3. Resolver discrepancias GTIN, presentaciones, combos y SKU duplicados.
4. Contar con fuente de precios/costos y política de stock/canales.
5. Diseñar mapeo de decisiones históricas por ID variante, no por prefijo de
   SKU, y validarlo mediante regresiones y reversión.
6. Solo con aprobación expresa habilitar un reconciliador operativo sobre API
   y, mucho después, publicación idempotente con validación por lote.

## Cómo probar
Después de CI verde y Render Live, abrir `/pilot`, sección 3, y pulsar
**Analizar catálogos API sin modificar datos**.
Revisar fechas de ambos snapshots, totales de variantes y publicaciones,
motivos y ejemplos. Si falta la copia ML API, debe salir un aviso claro, NO
silenciarse ni utilizar el Excel ML. No aprobar ningún vínculo con este informe.

## Seguridad
Ni este endpoint ni su UI modifican snapshots, `ReconciliationRun`,
inventario, GTIN, marca, MLA, decisiones humanas, Tiendanube ni Mercado Libre.
Los ejemplos tienen límite por categoría. El nombre del modo es
`API_ONLY_ML_READ_ONLY_PREVIEW`; `operational_reconciliation_activated`
es siempre `false`.
