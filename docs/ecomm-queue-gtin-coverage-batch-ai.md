# KIKI Tech — Cobertura GTIN y piloto IA por lotes

## Interpretación del catálogo (hallazgo en producción)
El usuario confirmó 3.127 variantes API, 3.126 sin borrador KIKI,
1 borrador persistente (SKU 2500400), 790 packs y que los 3.127 aparecen sin
GTIN en la copia. **Esto no demuestra ausencia de EAN del catálogo original**:
el stage Ecomm-App preserva únicamente las claves de variante `gtin` y
`barcode`; si el proveedor entrega EAN en otro campo o endpoint, no se ve aquí.

La cola ahora expone `gtin_data_quality` con recuentos encontrados/no
disponibles en la copia API y advertencia cuando la cobertura es cero.
El filtro se denomina «GTIN no disponible en copia API». Está prohibido
usar el contador para generar códigos, declarar incumplimiento o decidir
publicación. Verificar DTO/endpoint real de Ecomm con documentación/soporte
antes de intentar enriquecer GTIN.

## Primera automatización acotada
- La selección múltiple funciona **solo sobre la página visible**.
- Los CSV siguen siendo solo informes, sin aprobaciones.
- El piloto IA admite **1 a 3 variantes simples por operación**; bloquea
  packs, combos, IDs o SKUs inseguros y cambios de identidad o versión.
- «Preparar selección · sin costo IA» consulta el editor y los borradores
  existentes. Es una operación de lectura: calcula propuestas reutilizables
  y solicitudes nuevas y muestra el cupo diario restante.
- Solo otro botón y confirmación explícita del operador inician las
  llamadas de pago, ejecutadas secuencialmente.
- Cada propuesta generada queda persistida en el historial de propuestas
  KIKI AI existente por ID Ecomm. No cambia títulos/descripciones en
  `ecomm_api_product_edits` y no publica en Ecomm, ML o Tiendanube.
- Reutiliza propuestas vigentes sin nuevos cargos, aplica todas las reglas
  y alertas de calidad existentes y sigue sujeto al tope global actual de
  10 intentos por día UTC. Si falla un producto se muestra el error y se
  conservan las propuestas anteriores.
- La aplicación web no necesita un nuevo endpoint, usa
  `GET /api/ecomm-app/workspace/{id}`,
  `GET /api/ecomm-app/workspace/ai/{id}/latest` y
  `POST /api/ecomm-app/workspace/ai/{id}/suggest`.

## Validación en Render
1. Comprobar Render `kiki-tech-api` y `kiki-tech-web` Live.
2. En `/queue`, el contador total debe seguir en 3.127 y verse el
   aviso GTIN no disponible en la captura API.
3. En filtro «Borradores» debe quedar el 2500400; no alterar su guardado.
4. Seleccionar **un pack** y pulsar «Preparar selección»: debe rechazarlo
   sin consumir IA.
5. Seleccionar **un producto simple** y «Preparar selección»: ver ID/SKU,
   cupo, propuestas a reutilizar y cantidad de solicitudes nuevas.
6. La primera generación paga requiere el segundo botón y confirmación
   explícita. **No es necesario efectuarla para demostrar el UI**.
7. Tras ejecutar una generación autorizada, el resultado debe mostrar
   enlace a «Mejorar productos», donde se revisa campo por campo.
8. Comprobar que no se afectó el módulo IA de Tiendanube.

## Pendiente antes de usar IA con todo el catálogo
- Respaldo verificado de PostgreSQL.
- Auditoría del DTO/endpoint de EAN/GTIN del proveedor Ecomm-App.
- Límites de gasto/presupuesto por sesión/lote y reanudación robusta
  de trabajos en servidor, con auditoría multioperador y filtros basados
  en evidencia.
- Aprobación en lote separada de generación IA, sin aceptar por defecto
  propuestas con datos insuficientes.
- Integración a ML/TN para escribir solo después de validaciones y
  autorizaciones específicas de los canales.
