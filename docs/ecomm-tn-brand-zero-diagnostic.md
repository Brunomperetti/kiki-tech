# KIKI Tech: entender cero coincidencias de marca por SKU

## Hallazgo del 23/10/2026

La PR #124 informó en el entorno real:

- 1.771 variantes del Excel histórico sin marca
- 0 pistas de marca mediante coincidencia única por SKU
- 1.771 sin SKU idéntico en la foto de Tiendanube
- 0 SKU ambiguos entre esos 1.771

Es correcto concluir **cero coincidencias por ese criterio**. Es incorrecto concluir que 1.771 productos carecen de marca en todos los canales.

## Nueva inspección, sin escribir datos

La ampliación de `/imports` → **Buscar marcas ya informadas en Tiendanube** mantiene todos los recuentos originales y agrega:

- Cantidad real de filas TN disponibles y cuántas tienen marca.
- Cuántos IDs históricos Ecomm se solapan por cualquier SKU/alias conocido de Ecomm.
- Cuántos de esos IDs ya tenían marca histórica, explicando la ausencia de oportunidades nuevas.
- Una exploración limitada de coincidencias **únicas por EAN completo válido** (dígito verificador y longitud) o **nombre completo normalizado exactamente igual y único** en ambos inventarios.
- Exclusiones cuando el SKU cambia sustancialmente en API, el EAN o el nombre no son únicos, hay contradicción de sabor/presentación, el SKU de TN pertenece a otro ID histórico, o las señales indirectas apuntan a distintas filas TN.
- Hasta 12 ejemplos de pistas, siempre marcadas `NOT_CONFIRMED`, sin botón de aplicar.

No se usa matching difuso, no se extrae marca del título, no se asigna marca fabricante ni se igualan familias comerciales.

Los valores de marcas no se completan automáticamente. La etiqueta de marca de TN es una **referencia interna que requiere revisión humana** contra producto/etiqueta/fabricante.

## Pasos para comprobar en Render

1. Abrir `/imports`, pulsar **Comparar con el Excel histórico**.
2. Abrir **Buscar marcas ya informadas en Tiendanube (sin aplicarlas)** y pulsar comparar.
3. Revisar el nuevo bloque **¿Por qué aparecen cero coincidencias?** para saber si hay superposición de catálogos.
4. Si aparecen pistas por nombre completo o EAN único, expandirlas y analizar presentación, marca, nombre y SKU antes de cualquier aprobación futura.
5. Si no aparecen pistas, **no significa que no haya marcas**: significa que las copias actuales no permiten derivar un vínculo suficientemente seguro. Revisar si el CSV TN cubre todo el catálogo.
6. Verificar que en este paso no se guardan decisiones ni cambios en Ecomm-App, TN, ML o KIKI.

La API pública de Ecomm-App solo expone inventario/stock. La cobertura de marcas, precios comerciales y EAN debe mantenerse en un flujo separado y verificado.
