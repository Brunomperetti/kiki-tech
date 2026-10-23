# KIKI Tech — Diagnóstico de ambigüedad de marcas de Mercado Libre

## Evidencia en Render, 23/10/2026

El usuario ejecutó la PR #126 en `/imports`, con las siguientes cifras:

- **1.771** productos Ecomm históricos sin marca.
- **2.720** registros del snapshot API Mercado Libre (sin atributo BRAND porque fue capturado antes del cambio).
- **2.708/2.708** filas del reporte EDIMA con marca explícita.
- **1.284** filas rechazadas por indicadores de identidad ambiguos.
- **0** candidatos de marca elegibles.

Los 1.284 son **filas detectadas como ambiguas**, no necesariamente publicaciones, variantes o productos únicos, y no prueban error ni fraude de catálogo. El reporte EDIMA ofrece marcas, pero falta probar la relación entre el MLA y una variante precisa.

## Ampliación solo diagnóstica

Un nuevo desplegable **«¿Por qué se descartan tantas coincidencias? Ver motivos»** dentro de *Buscar marcas en Mercado Libre y EDIMA* muestra:

- Filas ML con marca disponible en API o a través de un MLA con marca en EDIMA.
- Filas ML con MLA encontrado en EDIMA.
- Filas rechazadas por identidad ambigua **en la copia ML**, y cantidad de MLA distintos implicados.
- Detalle por **MLA histórico asociado a múltiples IDs Ecomm**, **SKU que apunta a varios IDs Ecomm**, **GTIN con varios dueños** o **señales SKU/GTIN/MLA que apuntan a fichas diferentes**.
- **MLA compartido con SKU de variante único**: pista para inspeccionar variantes reales, sin elevar su confianza automáticamente.
- Filas con identidad única que ya correspondían a productos Ecomm con marca (no recuperables), filas sin identidad única y filas sin marcas en ninguna fuente.
- Cantidad de filas EDIMA cuyo MLA no figura en la copia ML.
- Máximo 8 ejemplos de filas ambiguas, con motivo exacto, MLA y cantidad de propietarios detectados. **No se muestra ni aprueba un producto como vinculado**.

Las causas por fila **pueden superponerse**, por lo que sus subtotales NO deben sumarse. El contador original de ambigüedades de #126 incluye también filas EDIMA sin MLA en el snapshot ML, mientras que el nuevo desglose separa las filas ML para entenderlo.

## Reglas que NO se modifican

- No se relaja el requisito de identificadores inequívocos.
- No se infiere la marca por el título del producto ni por dos/tres dígitos del SKU o por coincidencia de familia.
- Un MLA asociado a varios productos puede contener variantes físicas o publicaciones comerciales. **No se deduce la variante a partir del MLA**.
- No se crean vínculos, no se cambian datos, no se importa ni sincroniza ML, y no se consume IA.
- Tampoco se modifica el contador original de cero candidatos. Hasta inspeccionar la distribución de causas, no hay autorización para aplicar marcas.

## Prueba tras merge + Render Live

1. Abrir [KIKI Tech](https://kiki-tech-web.onrender.com/imports), comparar con Excel histórico.
2. Abrir `Buscar marcas en Mercado Libre y EDIMA (sin aplicarlas)` y pulsar `Investigar marcas de Mercado Libre (solo lectura)`.
3. Abrir **«¿Por qué se descartan tantas coincidencias? Ver motivos»**.
4. Capturar el resumen y **«Ver ejemplos de coincidencias retenidas»**. Comparar los recuentos de MLA compartido, SKU compartido, GTIN y señales contradichas. No esperar que sumen exactamente 1.284 porque se superponen.
5. Con los datos reales, decidir **un único cambio posterior**: auditar IDs de variación auténticos cuando hay MLA compartido y SKU de variante único, o conseguir fuente que contenga identificadores útiles. No cambiar automáticamente ni publicar.

**Meta comercial:** reducir controles manuales sin atribuir marca, presentación o stock equivocados.
