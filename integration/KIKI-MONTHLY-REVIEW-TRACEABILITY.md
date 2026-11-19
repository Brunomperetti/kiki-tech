# KIKI 2.0 — revisión mensual verificable (ciclo de 30 días)

## Fallo observado y reparación
La función existente `confirm_monthly_review` registra la decisión del
operador con el evento `REVIEW_CONFIRMED` y control de versión, pero
`review_schedule` solo contemplaba eventos con `new_status=READY_FOR_CHANNELS`
sin diferenciar **confirmaciones** de **guardados**. En la práctica,
guardar un campo podía correr silenciosamente el vencimiento mensual
y una confirmación no quedaba claramente diferenciada como constancia.

La corrección:
1. Toma como revisión inicial el cambio explícito desde un estado
   no listo a `READY_FOR_CHANNELS`.
2. Usa cada `REVIEW_CONFIRMED` posterior como nuevo punto de partida
   para los siguientes **30 días**.
3. Si se edita el contenido mientras la ficha sigue lista, muestra
   **`CONTENT_CHANGED` y `review_due=true`** hasta una nueva confirmación,
   aunque no hayan pasado 30 días.
4. Guardados sin cambios, estados borrador y fechas inválidas no
   pueden crear confirmaciones ni aplazar vencimientos.
5. Conserva todos los eventos originales en el historial; no altera
   la fecha de un documento o del contenido de Ecomm-App.

## Alcance de la auditoría
`Mi catálogo → Planificar lotes → Auditoría comercial integral` distingue:
- Fichas listas y revisadas dentro de los últimos 30 días.
- Fichas vencidas por fecha.
- Fichas modificadas después de su revisión.
- Fichas listas que no contienen constancia de revisión.
- Variantes que aún no tienen ficha lista (no tratarlas como
  ficticiamente revisadas o vencidas por el ciclo editorial).

El CSV de pendientes incorpora tres columnas por variante:
`ultima_revision_documentada`, `proxima_revision` y
`estado_revision`.

La **auditoría es de solo lectura**. Generar el informe no firma,
aprueba ni actualiza productos. El operador conserva el botón
`Confirmar revisión mensual` en cada ficha y debe verificar la
fuente real antes de usarlo.

## Limitación de entrega
Esta mejora hace correcto el cálculo y exportación del control mensual,
pero **no programa por sí sola** una inspección autónoma de proveedores
o cambios en cada web. El paso siguiente para cubrir el ciclo
completo debe automatizar la captura de origen autorizada,
clasificar las variantes con excepciones y establecer una constancia
global de revisión del catálogo; no se debe inventar que una ficha
sin fuente fue contrastada.

Sin nuevos servicios, tablas, migraciones, credenciales, IA o
escrituras a Ecomm-App, Mercado Libre y Tiendanube.
