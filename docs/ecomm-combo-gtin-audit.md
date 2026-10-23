# KIKI Tech — Auditoría de combos y GTIN compartidos (solo lectura)

## Origen y propósito

En la prueba en Render tras la PR #129 (23/10/2026), la investigación de marcas observó 1.024 filas ML con GTIN compartido, 399 con SKU/GTIN o MLA históricos incompatibles, y 1 única pista de marca pendiente (Maní King 485 g). El pack de Vitamin Way 240 cápsulas vs 180 cápsulas se excluye por presentación.

La hipótesis comercial es que **algunos** GTIN repetidos podrían pertenecer a artículos incluidos en un combo o a promociones especiales de una familia SKU. No contamos aún con comprobación de esa composición.

## Qué informa realmente la API pública Ecomm-App

La copia independiente `ECOMM_APP_API_STAGE` (importador `catalog_stage.py`) contiene:
- productos madre: `code`, `description`, `is_combo`, `total_stock`;
- variantes: `id`, `sku`, `is_combo`, `description`, `variant_description`, `barcode`, `gtin`, `total_stock` y stock por `warehouses`.

**No incluye una lista explícita de componentes por combo** (ni `component_id` / `component_variant_id`, cantidades de cada artículo, ni una relación padre→componentes). El endpoint documentado de inventario `GET /api/v3/public/inventario/productos` y el `POST /api/v3/public/inventario/productos/consulta` exponen productos y stock, no una composición autorizada. Por tanto, el análisis NO demuestra relaciones de componentes ni permite ajustar existencias.

## Diagnóstico nuevo

`combo_gtin_conflict_audit`, agregado al `GET /api/ecomm-app/stage/ml-brand-evidence` autenticado, procesa **solamente las copias ya almacenadas en PostgreSQL** y distingue:

- Filas ML con GTIN válido pero compartido, marca disponible en ML/EDIMA, SKU exacto que identifica un solo ID Ecomm y una contradicción de identidad respecto a GTIN o MLA históricos.
- **Filas ML** vs **MLA distintos** vs **GTIN distintos** vs **ID Ecomm por SKU** vs **casos únicos SKU+GTIN**, de modo que 2 publicaciones del mismo conflicto no parezcan 2 artículos diferentes.
- `is_combo` informado por la **variante** Ecomm (Sí/No/Sin dato) y el `is_combo` del **producto madre**, explícitamente separados.
- **Patrón posible**: el SKU de la publicación apunta a una variante `is_combo=True` y algún propietario del GTIN aparece como `is_combo=False`. **No equivale a composición confirmada.**
- GTIN con propietarios marcados combo/no combo/sin dato, pistas de **familia comercial numérica** por las reglas que definió KIKI Market (sin inferir parentesco físico), SKU que no pertenece al grupo GTIN y MLA histórico que apunta a otro ID.
- Hasta **12 grupos SKU+GTIN** con SKU Ecomm, nombre histórico, GTIN del ML, GTIN de la variante API, MLA implicados (máx. 8 mostrados), título ML, bandera combo de la variante/padre, y hasta 8 propietarios históricos del GTIN con sus banderas.
- Si faltan flags o relaciones, la UI dice **sin dato** y **no confirmado**, nunca `no es combo` por defecto.
- Los recuentos de banderas de los propietarios del GTIN se superponen y **no son sumables**.

## Garantías

- `components_available_in_snapshot = false`, `component_membership_confirmed = false`, `activation_allowed = false`.
- No se transforma un GTIN compartido en relación componente→combo; tampoco se valida stock, SKU, marca, EAN, ID de variante ML ni publicación.
- No usa IA, no se conecta a las API externas durante el análisis, no reimporta ni promueve snapshots, no actualiza PostgreSQL, no crea ni aprueba decisiones y no publica en ML/TN.
- `shared_gtin_review`, candidatos de marcas originales y controles de presentación de PR #129 quedan sin cambios.

## Prueba tras merge y Render Live

1. `https://kiki-tech-web.onrender.com/imports` > comparar copia API Ecomm con Excel histórico.
2. *Buscar marcas en Mercado Libre y EDIMA* > *Investigar marcas de Mercado Libre*.
3. Abrir **«Auditar combos y GTIN: separar hipótesis de componentes de datos comprobados»**.
4. Revisar: cantidad de **filas**, **SKU+GTIN agrupados**, **combos identificados**, **patrones posibles** y **datos sin bandera combo**. Estos números pueden diferir del contador anterior de 399 por filtros y agrupación; no inventar equivalencias.
5. Abrir **«Investigar casos concretos»**: inspeccionar por qué cada GTIN se relaciona con varias fichas y cómo aparece `is_combo` de la API. Ningún dueño del GTIN se marca como componente confirmado.
6. Enviar una captura del resumen y un grupo completo para decidir qué integración se necesita realmente.

## Próxima integración si se quiere demostrar composición real

Solicitar a Ecomm-App un **endpoint o exportación oficial de composición de combos** con estos campos mínimos:
`combo_variant_id`, `component_variant_id`, `quantity`, `unit`, fecha/versionado y, cuando exista, SKU de ambos. Usar ID interno de variante (no MLA ni GTIN compartido) como identidad. Si no existe ese endpoint, mantener relaciones como **hipótesis pendiente**, sin inferir recetas desde los SKU.

Una vez confirmados los vínculos, recién entonces se podrá diseñar una tarea guiada en KIKI Tech para resolverlos con control humano, dejando marcas y sincronización de stock como flujos separados.
