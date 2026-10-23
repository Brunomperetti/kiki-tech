# KIKI Tech — Simulación de ficha híbrida sin cambios operativos

**Contexto:** API pública de Ecomm-App, alcance `inventario:leer`, copia independiente `ECOMM_APP_API_STAGE`, cruzada con `ECOMM_APP` Excel histórico.

La etapa anterior (#120) confirmó **3.028 registros por ID estable**, con 3.016 SKU exactos, 10 diferencias de escritura y 2 códigos sustancialmente distintos (ambos combos: Vitamina C Sundance 9183101 y Aceto Balsámico 9211791).

## Pregunta que valida esta PR

**¿Podemos conservar los datos comerciales del Excel y cotejar stock de la API sin afectar Mercado Libre ni Tiendanube?**

Esta PR **simula** el enfoque, **no** lo activa. La respuesta incluye los datos con su origen indicado en columnas separadas:

- Excel histórico: nombre, SKU anterior, marca, precio de lista, costo, EAN y stock de la fecha del Excel.
- API copiada: código de producto padre, SKU de variante, flag `is_combo`, stock total y stock por depósito.
- Clave primaria de lectura: **ID interno de variante**, únicamente si aparece una vez en cada fuente.
- Sin identificación segura: histórico-only, API-only, ninguno o ID duplicado; no se completa la otra columna por parecido de SKU.

## Experiencia

En `/imports` > «Crear una copia completa de prueba» > «Comparar con el Excel histórico» se muestra **«Simular una ficha híbrida por ID»**. Los primeros dos IDs vienen precargados automáticamente a partir de los cambios sustanciales del cruce; se admiten hasta cinco IDs distintos por consulta. La API de KIKI se llama con un POST de **solo lectura**, sesión y CSRF.

**No se realizan consultas nuevas a Ecomm-App:** este endpoint consulta exclusivamente los dos snapshots ya guardados en PostgreSQL. La fecha de captura de la API se muestra explícitamente; no afirmar que el stock sea en vivo.

La cobertura del Excel anterior también se informa: entre los 3.028 ID reconocidos, cuántos tienen precio de lista, costo, marca y EAN, y cuántos tienen valor de stock en el snapshot de API.

## Bloqueos antes de activar esta fuente

- La API `inventario:leer` no garantiza precios, costos ni vínculos comerciales; esos campos se mantienen históricos hasta contar con una fuente válida.
- Los códigos de combos no se renumeran automáticamente; las familias y alias siguen sujetos a revisión.
- La copia API paginada corresponde a una fecha concreta; nunca usarla como “stock actual” para sincronizar automáticamente.
- Pendiente: 99 variantes API-only, un producto histórico sin ID coincidente, dos cambios sustanciales de SKU.
- Para un uso operativo futuro es necesario validar stock reciente, precios/costos, idempotencia, actualizaciones periódicas, consistencia de snapshot y rollback. Requiere aprobación explícita.

**No modifica ningún snapshot ni tabla de decisiones y no publica a canales.**
