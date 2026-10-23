# Ecomm-App API: plan de incorporación sin modificar datos

La API pública de inventario ya fue validada (23/10/2026) con una copia aislada:
- 3.121 productos padre, 3.127 variantes, 63/63 páginas.
- Cruce con 3.029 productos del Excel: 3.028 IDs estables coincidentes.
- De estos: 3.016 mantienen SKU idéntico, 10 tienen diferencia solo de formato y 2 tienen cambios sustanciales de SKU.
- 1 producto histórico no aparece por ID en la API (Geonat Omega 3, ID 6963979, SKU 4744).
- 99 variantes API sin ID histórico: 32 marcadas combo por la API, 67 no combo.
- 1.132 stocks diferentes entre capturas: *diferencias de fecha*, no errores ni órdenes para actualizar.

## Qué hace la pantalla

En **Importaciones > Ecomm-App > Crear una copia completa de prueba > Comparar con el Excel histórico**, el nuevo plan:
1. Separa identidad por ID de SKU, precio, stock y vínculos comerciales.
2. Prioriza 2 cambios de SKU sustanciales, 1 producto histórico no reconocido por ID y 99 variantes API sin correspondencia histórica; las 10 diferencias de escritura quedan informativas.
3. Desglosa las 99 variantes según `is_combo` real, sin confundir el sufijo `_m` con una confirmación.
4. Enumera controles de corte: integridad de snapshot, excepciones de identidad, disponibilidad de precios/costos y vínculos de canal, actualizaciones consistentes y reversión.

**No se habilita la activación de la fuente desde esta pantalla.** El resultado incluye `activation_allowed: false` por diseño, aun si todas las coincidencias por ID y SKU fueran perfectas.

## Por qué no reemplazamos el Excel todavía

El scope `inventario:leer` confirma productos, variantes y stock por depósito; **no garantiza por sí mismo precios/costos ni asignaciones de publicaciones a ML/Tiendanube**. El snapshot paginado tampoco garantiza una captura transaccional inmutable del catálogo durante el barrido. Los módulos actuales de KIKI usan también esa información comercial.

Para cualquier cambio operativo futuro necesitaremos demostrar cobertura de datos, revisar excepciones, probar reconciliaciones sin efectos, prever rollback y obtener aprobación humana separada.

Toda esta PR es **diagnóstico sobre dos snapshots ya guardados**; no hace nuevas consultas a Ecomm-App ni modifica bases, productos, publicaciones o decisiones.
