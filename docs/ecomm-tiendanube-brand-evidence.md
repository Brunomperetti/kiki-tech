# KIKI Tech — Evidencia de marcas desde Tiendanube para productos Ecomm-App

## Resultado de la auditoría comercial (23/10/2026)

De **3.028** productos históricos con ID coincidente en la copia API:
- **1.257** informan marca en Excel; **1.771** no la informan.
- **3.026** tienen precio de lista positivo y 2 precio 0.
- **3.025** tienen costo positivo y 3 costo 0.
- **557** informan EAN, **2.471** tienen campo vacío.
- Entre 758 combos identificados por ID, 29 carecen de marca histórica.

Que falte marca en el Excel no demuestra que falte en Tiendanube, Mercado Libre o el catálogo fabricante. Ni las marcas presentes en TN prueban por sí solas identidad de fabricante.

## Nueva investigación controlada

En `/imports` > copia completa de Ecomm-App > comparar con Excel histórico > **«Buscar marcas ya informadas en Tiendanube (sin aplicarlas)»**, el nuevo diagnóstico busca pistas con estas condiciones SIMULTÁNEAS:

1. El producto tiene ID de variante **único** tanto en el Excel histórico como en la copia API.
2. Su marca histórica está vacía o lleva un marcador como `Sin marca`.
3. Su SKU anterior **no ha cambiado sustancialmente** en la copia API.
4. Su SKU del Excel coincide de forma literal con exactamente **una fila de Tiendanube** (se permiten únicamente diferencias de mayúsculas/minúsculas y espacios exteriores).
5. Ese SKU pertenece a **un solo ID de Ecomm-App**. No se propone cuando varios productos comparten ese mismo SKU.
6. Tiendanube informa una marca no vacía ni genérica.

El diagnóstico devuelve el total de candidatos, el desglose de casos excluidos por ambigüedad, falta de SKU, cambio de código o marca vacía de Tiendanube, y como máximo 20 ejemplos de revisión (nombre, ID, SKU Ecomm/API/TN, marca literal Tiendanube e indicador de combo).

**Una coincidencia no significa aprobación**: muestra una marca de Tiendanube como *evidencia interna por verificar*. La identidad del fabricante, el producto y la presentación aún deben validarse por medios confiables. No existe botón de «aplicar» ni «aprobar» en esta etapa.

## Garantías

- Consulta únicamente las copias ya guardadas `ECOMM_APP`, `ECOMM_APP_API_STAGE`, `TIENDANUBE`. No llama a proveedores ni consume créditos de IA.
- No escribe ningún dato de marca, precio, costo, stock, EAN, publicación o catálogo.
- No crea vínculos comerciales automáticos, no modifica decisiones ni solicita claves.
- Los SKU duplicados, productos no coincidentes y combos conservan revisión humana.
- Si no hay CSV de Tiendanube guardado, no produce falsos candidatos.
- No reduce automáticamente el recuento de 1.771 marcas históricas vacías.

## Pruebas tras merge y Render Live

1. En `/imports` abrir copia de prueba y pulsar **Comparar con el Excel histórico**.
2. Abrir **Buscar marcas ya informadas en Tiendanube (sin aplicarlas)**.
3. Pulsar **Comparar marcas con Tiendanube (solo lectura)**. Debe mostrar hasta cuántos de los 1.771 sin marca histórica tienen **una pista única** en Tiendanube. No asumir un número por adelantado.
4. Expandir **Ver candidatos encontrados**. Revisar los nombres e identificadores; **no** dar por confirmada la marca a partir de un SKU coincidente.
5. Revisar cuántos SKU son ambiguos, no existen en TN o cambiaron en la API.
6. Verificar que siguen intactos los 3.028 IDs emparejados, los 2 precios cero, los 3 costos cero y la revisión habitual de marcas de KIKI.

**Siguiente paso posible, por separado:** integrar estos hallazgos al flujo existente de revisión humana de marcas, previa evaluación de conflictos con decisiones anteriores.
