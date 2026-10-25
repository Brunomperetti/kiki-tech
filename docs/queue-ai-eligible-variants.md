# KIKI Tech — Productos simples aptos para IA

## Motivo
En producción la cola prioriza 790 packs/combos. Como la vista «Sin trabajar»
mantiene el mismo orden, las primeras páginas muestran packs y no sirven
para probar el piloto de IA con productos simples.

## Cambio
- Nuevo filtro servidor `filter=ai_eligible` que encuentra únicamente
  variantes de la copia Ecomm-App API sin marca de combo, con SKU e ID
  propios, SKU no ambiguo y sin desplazamiento de identidad desde el
  borrador guardado en KIKI.
- La cola presenta un chip `Simples aptos para IA` con contador total
  independiente de la página actual.
- En la sección «Preparar propuestas IA para varios productos» se incorporan:
  «Ver solo productos simples aptos para IA» y
  «Elegir 3 simples de esta página».
- El segundo botón selecciona un máximo de tres filas visibles, y
  respeta la regla ya implementada de previsualización gratuita y
  confirmación separada antes de consumir OpenAI.
- El nuevo filtro **no** certifica datos comerciales ni autoriza
  publicación en Ecomm-App, ML o Tiendanube.
- La operación no genera IA, no guarda fichas y no edita datos.
- Tests de casos simples, combos, búsqueda, paginación,
  identidad modificada y SKU ambiguo.

## Prueba
1. Abrir `https://kiki-tech-web.onrender.com/queue` y Ctrl+F5
   cuando ambos servicios estén Live.
2. Seleccionar «Simples aptos para IA» y verificar que los primeros
   resultados no son packs.
3. «Elegir 3 simples de esta página» debe marcar solo 3.
4. «Preparar selección · sin costo IA» debe mostrar costo/reuso.
5. **No** pulsar «Generar propuestas» hasta aceptar el consumo.
