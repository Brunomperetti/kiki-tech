# KIKI Tech — Marcas en Mercado Libre: prueba de evidencia sin modificaciones

## Motivo (23/10/2026)

La auditoría Ecomm-App halló **1.771 de 3.028** fichas históricas sin marca. El CSV de Tiendanube (552 filas; 550 con marca) solapó con 496 IDs históricos **que ya tenían marca**: 0 propuestas nuevas por SKU, EAN único o título completo. La siguiente hipótesis es revisar el inventario de publicaciones de Mercado Libre.

El análisis del código revela dos fuentes con **comportamientos distintos**:
- **EDIMA_LINKAGE**, exportado desde Ecomm-App para publicaciones de Mercado Libre, ya admite campo `brand`/Marca por publicación.
- **MERCADOLIBRE_API** sincroniza publicaciones y variantes, pero hasta ahora el transformador descartaba `BRAND`. Desde esta PR, los **futuros** syncs read-only de ML conservan el atributo `BRAND` explícito en el snapshot. **No se rellena retrospectivamente el snapshot histórico**, ni se consulta ML desde esta auditoría.
- El importador Excel Mercado Libre ahora acepta columna `Marca` si existe.

## Panel nuevo

En `/imports` > copia Ecomm completa > comparar Excel histórico > **Buscar marcas en Mercado Libre y EDIMA (sin aplicarlas)** se muestra bajo demanda:
- Filas disponibles en snapshot de ML y cuántas contienen marca explícita.
- Filas EDIMA y cuántas tienen marca.
- Productos sin marca histórica (sobre IDs únicos emparejados).
- Cuántos productos Ecomm reciben una **pista de marca para revisión**, no aprobación.
- Casos ambiguos, marcas discordantes dentro de MLA o entre publicaciones y número de combos.
- Fechas del snapshot ML, EDIMA y ambos inventarios Ecomm.
- Hasta 20 ejemplos con ID, SKU, MLA, marca textual de publicación, fuente, criterio y estado `NEEDS_HUMAN_VERIFICATION`.

## Cruce prudente y determinista

Una pista requiere:
1. ID variante único en catálogo Ecomm histórico y copia Ecomm API completa.
2. Marca Ecomm histórica faltante.
3. SKU histórico y SKU Ecomm API **sin cambio sustancial**.
4. Marca explícita en ML o EDIMA.
5. Coincidencia inequívoca basada en **SKU exacto y único** entre publicación ML y Ecomm, **EAN con dígito verificador válido y dueño único**, o **referencia MLA histórica única** de las filas del inventario. No se usan prefijos de SKU, familias, nombres similares ni título por sí solo.
6. No conflicto entre SKU, EAN y referencia MLA. No marcas diferentes para el mismo MLA ni diferentes marcas de publicaciones para un mismo ID Ecomm.
7. Sin conflicto evidente de presentación/variante entre el producto Ecomm y el título ML.

Una coincidencia por MLA o EAN no prueba que ese MLA sea una variación física ni que una marca sea correcta. Los resultados requieren comprobación humana contra etiqueta/fabricante y contra las publicaciones vigentes, especialmente combos. Los snapshots pueden estar desactualizados.

## Seguridad

- Audita `ECOMM_APP`, `ECOMM_APP_API_STAGE`, `EDIMA_LINKAGE` y `MERCADOLIBRE_API` o `MERCADOLIBRE` **ya guardados en PostgreSQL**.
- `GET /api/ecomm-app/stage/ml-brand-evidence` solo lectura y autenticado.
- No llama a la API de Mercado Libre ni a Ecomm-App durante el diagnóstico; no requiere credenciales nuevas ni IA.
- No persiste propuestas, no modifica catálogo operativo, precios, costos, GTIN, stock, publicaciones ML/TN, conciliación, decisiones, alias o familias.
- El ajuste al transformador API simplemente **retiene** información de marca explícita en futuras importaciones ordinarias de ML. No modifica publicaciones externas ni genera sincronización automática.

## Prueba en Render después de CI y merge

1. `/imports` > copia Ecomm completa > comparar Excel histórico.
2. Abrir **Buscar marcas en Mercado Libre y EDIMA (sin aplicarlas)** > **Investigar marcas de Mercado Libre (solo lectura)**.
3. Revisar filas ML, EDIMA con marca y total de pistas. Si la copia ML API anterior muestra 0 marcas, es esperable: se guardó antes de que el importador capturara `BRAND` (no ejecutamos automáticamente una nueva sincronización).
4. Abrir ejemplos y confirmar que todos dicen pendiente de verificación humana, sin botones de aplicar.
5. Verificar fechas. Si EDIMA no trae campo Marca, el conteo será 0: corresponde conseguir un reporte actualizado del origen antes de ampliar el algoritmo.
6. El catálogo original, inventario y publicaciones deben permanecer intactos. Para capturar marcas **nuevas** de ML API hará falta una sincronización normal *explícitamente iniciada*, cuando estemos de acuerdo en la fuente.

El objetivo es medir la evidencia existente antes de decidir si conviene añadir el flujo de revisión manual de marcas de ML.
