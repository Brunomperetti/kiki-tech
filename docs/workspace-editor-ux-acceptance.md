# KIKI Tech — UX operativa: edición persistente de productos

## Objetivo
Evitar pérdidas accidentales de trabajo y permitir que la cantidad de fichas
crezca sin limitarse a los primeros 25 registros.

## Cambios
- En **Mejorar productos → Fichas guardadas**, búsqueda por ID Ecomm,
  SKU, marca, título y nombre de producto.
- Filtro de estado (todos, borradores, listas para revisión interna).
- Paginación real de 25 registros por página, desde el endpoint de fichas
  de PostgreSQL que ya existía. Los tres indicadores superiores siempre
  muestran el total general, independiente del filtro.
- Advertencia ante cambios sin guardar al intentar abrir otra ficha o
  navegar mediante un enlace dentro del sitio. El navegador también
  advierte si se refresca o cierra la pestaña con cambios sin guardar.
- Controles para guardar al pie visibles mientras se edita.
- Selector de productos visible en pantallas grandes para eliminar el
  espacio vacío lateral cuando el formulario es largo.

## Pruebas manuales recomendadas
1. Abrir la ficha 7214195 (SKU 2500400), editar observaciones sin guardar
   y probar cambiar a otro producto: confirmar que al cancelar sigue allí.
2. Con texto nuevo sin guardar, presionar F5: confirmar el aviso del navegador
   y cancelar. Con la ficha limpia, F5 no debe mostrar advertencia.
3. Guardar borrador, abrir pestaña «Fichas guardadas», filtrar por 2500400
   y confirmar que conserva el dato después de recargar.
4. Guardar otro borrador y filtrarlo por estado o marca.
5. Cuando existan más de 25 fichas, comprobar «Siguiente» y «Anterior»;
   los contadores superiores no deben cambiar por pasar de página.
6. Confirmar que ni esta UX ni los filtros modifican fuentes Ecomm/ML/TN.

## Limitaciones que continúan
- Los cambios se guardan únicamente dentro de KIKI en PostgreSQL,
  por ID de variante de Ecomm-App API.
- El permiso actual `inventario:leer` no permite escribir a Ecomm-App.
- No está habilitada la publicación de cambios a Mercado Libre/Tiendanube.
- No confundir «Lista para revisión interna» con «Aprobada para publicación».
