# KIKI Tech — GTIN compartidos: investigar marcas por SKU único sin relajar controles

## Lo que comprobamos (23/10/2026)

La PR #127, ejecutada en Render, reveló:

- **2.688** filas del snapshot Mercado Libre (de 2.720) con marca accesible desde EDIMA por MLA.
- **1.284** filas descartadas por identificadores ambiguos, exactamente 1.284 MLA distintos en la copia revisada.
- Entre esas filas: **1.006** con GTIN asociado a más de un ID Ecomm; **278** con señales SKU/GTIN/MLA hacia IDs distintos.
- **0** MLA históricos asociados a varios IDs y **0** SKU con varios propietarios dentro del conjunto evaluado.
- **1.304** filas ML con identidad única hacia fichas Ecomm que ya tienen marca, **100** sin identidad única, **32** sin marca disponible.
- **0** marcas automáticamente asignadas; **0** candidatas con las reglas anteriores.

Estos datos son diagnósticos de copias anteriores, no estado en vivo ni garantía de causalidad única.

## Mejora de la PR #128

Nuevo apartado **«Analizar GTIN compartidos: ¿el SKU ayuda a identificar la publicación?»** dentro del panel *Buscar marcas en Mercado Libre y EDIMA*.

El servicio analiza exclusivamente los GTIN **válidos pero compartidos** por varios IDs Ecomm y clasifica:
- Cuántas filas ML tienen GTIN compartido.
- Cuántas tienen un **SKU exacto único**, distinguiendo SKU de variación explícito frente al SKU de publicación sin identificación de variación.
- Cuántos SKU únicos apuntan a un ID **incluido** en los posibles propietarios del GTIN, sin una referencia MLA incompatible.
- Cuántos apuntan a un ID **contradictorio** (no generan pistas).
- Cuántos de esos productos ya tienen marca Ecomm.
- Cuántas filas compatibles apuntan a productos sin marca histórica, y cuántos **IDs Ecomm distintos** quedan con pista y una única marca EDIMA/ML.
- Se excluyen las marcas contradictorias entre publicaciones del mismo ID, datos de presentación evidentemente conflictivos y MLA históricos incompatibles.
- Muestras limitadas a 12 pistas para revisar y hasta 12 descartes por contradicción con MLA, SKU, GTIN y origen de marca.

**Importante:** una pista no es un vínculo, no demuestra que el GTIN sea correcto ni confirma que la marca corresponda al producto exacto. Un SKU coincidente pero sin ID de variante de ML no prueba variantes reales. Los combos y las diferencias de presentación requieren verificación humana.

No se modifica la lógica de decisión original `unique_brand_review_leads`, que puede seguir en cero; las pistas de GTIN compartido son un bloque diagnóstico **separado** y todas llevan `NEEDS_HUMAN_VERIFICATION`.

## Resguardos

- Fuentes: snapshots existentes Ecomm histórico, API de inventario Ecomm, ML API y EDIMA.
- **Cero escrituras** de marcas, alias, stock, precios, EAN, decisiones, publicaciones ML/TN o datos operativos.
- Sin nuevas llamadas a terceros ni claves ni IA.
- El análisis es a demanda, después de hacer clic en *Investigar marcas de Mercado Libre*, y no sincroniza fuentes en vivo.

## Prueba tras merge + Render Live

1. Abrir `https://kiki-tech-web.onrender.com/imports`.
2. Comparar la copia API Ecomm con el Excel histórico y desplegar *Buscar marcas en Mercado Libre y EDIMA*.
3. Hacer clic en *Investigar marcas de Mercado Libre (solo lectura)*.
4. Abrir *Analizar GTIN compartidos: ¿el SKU ayuda a identificar la publicación?*.
5. Revisar cifras de SKU único, variantes únicas, contradicciones, fichas ya con marca y **IDs con pista para revisar**. No se promete una cifra previa al test real.
6. Abrir *Ver posibles marcas para investigar* y capturar un par de ejemplos con SKU, MLA y GTIN. Verificar que todos son **sin confirmar**, sin botones de guardar o aprobar.
7. No cambiar fuente de inventario ni proceder a publicación.

Con esta evidencia decidiremos si integrar futuras sugerencias al sistema existente de revisión humana, o si necesitamos consultas de ML con `variation_id` genuino.
