# KIKI Tech — Auditoría de calidad comercial antes de usar la API como fuente principal

## Qué sabemos al 23/10/2026

- Se completó una copia aislada de Ecomm-App: 63 páginas, 3.121 productos padre y 3.127 variantes.
- 3.028 de los 3.029 registros del Excel tienen un **ID interno único** coincidente con una variante en la copia API.
- El primer diagnóstico superficial señaló precios y costos *informados* en 3.028 registros, pero eso **no certifica que sus importes sean positivos ni vigentes**.
- La marca está informada en 1.257 de las 3.028 fichas históricas evaluadas por ese primer diagnóstico. Esto **no implica** que los otros productos carezcan de marca en TN/ML, fabricante o evidencias aprobadas en KIKI.

## Qué cambia con esta PR

Se agrega una inspección **de lectura, solicitada explícitamente**: Importaciones → copia Ecomm → Comparar con Excel → **«Auditar marcas, precios y costos del Excel histórico»**.

El reporte observa **solo IDs únicos presentes en ambas fuentes**, sin asumir correspondencias por parecido de SKU:
- Marca: informada / vacía / marcador genérico.
- Precio de lista histórico: número positivo / cero / vacío / negativo / inválido.
- Costo histórico: los mismos cinco estados.
- EAN: informado (sin afirmar que sea válido) / en blanco.
- Combos identificados por la API y cuántos de esos tienen marca histórica vacía o genérica.
- Muestras acotadas de hasta ocho casos por categoría de marca, precio y costo, con ID y SKU; suficientes para comprobar por qué aparecen en la auditoría sin volcar miles de fichas.

**Cero** en precio o costo se expone para revisar; **no se transforma en faltante** ni se corrige automáticamente. Los precios y costos positivos se clasifican como *presentes*, **nunca como verificados al día**.

## Resguardos

- No se consulta Ecomm-App externamente: el endpoint inspecciona las copias existentes `ECOMM_APP` y `ECOMM_APP_API_STAGE`.
- Reporte solo de lectura, autenticado, sin endpoint de escritura, sin nuevas credenciales.
- No se asigna automáticamente una marca por su presencia en el título. No se modifica `ECOMM_APP`, `ECOMM_APP_RAW`, `ECOMM_APP_API_STAGE` ni módulos ML/TN, decisiones, stock, precios, GTIN o reglas de combos.
- Los datos en otras fuentes (TN/ML y sugerencias de marcas revisadas) **todavía no se cruzan** en este módulo. Sería el paso siguiente, con evidencia de fabricante y revisión humana.
- El diagnóstico no permite activar sincronización.
- Corrige además la presentación de la hora de la última consulta puntual Ecomm, mostrando horario **de Córdoba en 24 horas** para evitar confusión con AM/PM.

## Pruebas después del merge y Render Live

1. Ir a `/imports` > copia completa > **Comparar con el Excel histórico**.
2. Abrir **«Auditar marcas, precios y costos del Excel histórico»** y pulsar **«Revisar cobertura comercial (solo lectura)»**.
3. La cantidad de IDs incluidos debe ser **3.028** mientras ambas copias no cambien.
4. Verificar cuántos tienen **marca informada o vacía** y cuánto del precio y del costo es **mayor que cero**, no simplemente no nulo.
5. Abrir ejemplos de marcas faltantes, importes cero o inválidos. **No corregir automáticamente**.
6. Si ya ejecutó una consulta puntual de stock, verificar que la hora se muestre en 24 horas (Córdoba) y no aparente ser de madrugada.

Próxima etapa: contrastar marcas sugeridas y fuentes de producto/retail disponibles en KIKI, sin tratar una coincidencia de nombre como prueba suficiente para sobrescribir datos.
