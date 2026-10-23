# KIKI Tech — Protección de presentaciones y causas reales de contradicción

## Hallazgos que motivaron el cambio (capturas del 23/10/2026)

Después de ejecutar la PR #128, KIKI mostró **dos** fichas sin marca histórica con indicios provenientes de EDIMA:

1. **Pasta de Maní Natural Maní King x 485 g sin TACC**, Ecomm ID `6708437`, SKU Ecomm/ML `246`, marca informada en EDIMA *Maní King*, GTIN repetido en 3 IDs. Producto y presentación coinciden en los títulos; sigue siendo solo pista para revisar, no marca validada.
2. **Pack x3 Colágeno + Calcio Vitamin Way**, Ecomm ID `6821266`, SKU Ecomm/ML `5243200`, marca EDIMA *Vitamin Way*, GTIN repetido en 4 IDs. **Contradicción de presentación**: ficha Ecomm **240 cápsulas**, publicación ML **180 cápsulas neutro**. La app la mostraba como posible marca pese a esta diferencia. Debe quedar fuera de las pistas investigables hasta resolver qué producto representa la publicación.

De la misma prueba:
- 1.024 filas ML con GTIN compartido.
- 993 con SKU que identifica un único ID Ecomm.
- 399 con señales de identidad incompatibles.
- 591 filas compatibilizadas correspondían a Ecomm que ya tenía marca.
- 2 IDs históricos sin marca ofrecidos para investigación (antes del control de cápsulas).
- 12 ejemplos de contradicción mostraban un texto genérico que mezclaba **SKU ajeno al grupo de propietarios del GTIN** con **referencia MLA histórica contradictoria**.

## Qué cambia

- El comparador de presentaciones reconoce **cantidades de cápsulas, comprimidos, tabletas**, incluso grafías abreviadas `caps`, `cap`, y gramajes sin espacio (`485g`).
- Si ambos títulos tienen cantidades con misma unidad pero distintas cifras, se excluye esa publicación como pista. Si uno carece de cantidad, queda sin comprobación suficiente; **no se asume coincidencia** por ausencia.
- Se agregan hasta 12 ejemplos **`PRESENTATION_CONFLICT`** con nombre Ecomm y título ML para revisar casos como 240 vs 180 cápsulas.
- Se distinguen las causas **`SKU_NOT_IN_GTIN_OWNERS`** y **`HISTORICAL_MLA_POINTS_ELSEWHERE`**; pueden darse conjuntamente, por lo que los recuentos de causa no deben sumarse. Los ejemplos muestran ID Ecomm por SKU y los IDs de cada fuente, sin afirmar cuál está mal.
- La primera candidata *Maní King* puede permanecer solo como **pista humana** si los datos del snapshot lo permiten. La candidata *Vitamin Way* con cantidades divergentes debe quedar excluida.

## Seguridad

No se cambia la fuente de inventario, GTIN, marcas, SKU, decisiones, familias, publicaciones ni stock. No se consulta ningún proveedor, no se crea ninguna relación ML↔Ecomm ni se autoriza ninguna marca. Un nombre y cantidad coincidentes tampoco prueban identidad real. El reporte se basa en snapshots históricos y es de lectura.

## Prueba sugerida tras merge y Render Live

1. En `/imports`, ejecutar la comparación y abrir **Buscar marcas en Mercado Libre y EDIMA**.
2. Ejecutar **Investigar marcas de Mercado Libre (solo lectura)** y abrir **Analizar GTIN compartidos**.
3. Comprobar si la cifra de IDs con pista baja de 2 a 1 y si el pack Vitamin Way figura en **Ver presentaciones incompatibles descartadas**.
4. Verificar que *Maní King x 485g* sigue sin aprobación automática.
5. Abrir **Ver ejemplos descartados por contradicción** y revisar los motivos diferenciados e IDs Ecomm.
6. No aprobar marcas hasta comprobar fabricante, presentación y publicación vigentes.

El resultado real puede cambiar si se actualizan los snapshots; las cifras citadas arriba son de las capturas anteriores al cambio.
