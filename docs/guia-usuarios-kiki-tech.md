# KIKI Tech — Guía interactiva para operadores del catálogo

## Para qué sirve
La aplicación ya permite consultar las 3.127 variantes Ecomm-App por API,
generar propuestas IA para productos simples, guardar cambios editoriales en
PostgreSQL y volver a abrirlos. Se necesita una guía accesible dentro de KIKI
mientras continúa el desarrollo, para evitar reprocesos y falsas expectativas
de sincronización con ML/TN.

## Acceso
- Desde el menú lateral: **Guía para usar KIKI** (`/guia`).
- Desde Inicio: tarjeta **Aprender a usar KIKI**.
- Desde cualquier pantalla: botón flotante **¿Necesitás ayuda?** que muestra
  las indicaciones de la pantalla en uso, sin obligar a abandonar el editor.
- Dentro de **Mejorar productos**: «Volver a cola de mejoras» y «Cómo guardar».

## Primera prueba para el cliente (3 acciones)
1. **Canales**: comprobar estado y fecha de Ecomm-App API, Mercado Libre API y Tiendanube CSV.
2. **Cola**: filtrar candidatos en ML/TN o conflictos, revisar SKU, presentación y fuente.
3. **Backoffice**: elegir una ficha, completar información comprobada, guardar borrador,
   salir y regresar para corroborar historial y persistencia.

La guía muestra arriba tres accesos directos para esta prueba sin gasto de IA ni escritura externa.
La IA por lotes es opcional y no reemplaza la revisión humana.

## Recorrido de ocho etapas
1. Entender la copia API y fechas de captura.
2. Buscar, interpretar cobertura por canales y priorizar productos en Cola de mejoras.
3. Preparar la selección para IA sin consumo.
4. Generar propuestas IA conscientemente (máx. 10 intentos/día UTC).
5. Revisar cada campo en Mejorar productos y registrar evidencia.
6. Guardar borrador/mandar a revisión **interna** y comprobar historial.
7. Reabrir fichas desde Fichas guardadas o Borradores.
8. Consultar canales de venta sin confundir copias históricas con stock vivo.

Cada etapa contiene instrucciones, un criterio de comprobación, riesgos y un
acceso directo. Un glosario desplegable explica las pantallas principales.

## El mensaje más importante
**Propuesta IA guardada ≠ ficha comercial guardada.** «Usar este título»
y «Usar esta descripción» colocan datos en el formulario, pero requieren
un clic posterior en «Guardar borrador» o «Enviar a revisión interna».
Solo entonces queda el cambio de ficha en PostgreSQL y su historial.
El progreso visual de la guía NO representa guardados reales.

## Límites y seguridad
- No cambia tablas ni permisos, no reescribe publicaciones, no agrega
  autosave ni sincronizaciones falsas.
- Ecomm-App se usa como identidad de origen por API; ML necesita
  reautorización del titular; TN mantiene copia CSV.
- Ante dudas de pack, GTIN, marca o descripción IA, verificar los datos
  contra envase/fuente comercial antes de guardar para revisión.
- «Lista para revisión interna» no significa aprobado o publicado.

## Comprobación en producción
- Después de desplegar web Live, abrir `/guia`, navegar pasos 1-8,
  y probar los accesos.
- Abrir Ayuda dentro de Cola y de Mejorar productos: mostrar instrucciones
  diferentes. Cerrar con botón o tecla Esc.
- Abrir ficha SKU 2500400 desde Cola, pulsar «Volver a cola»,
  confirmar navegación.
- Si hay cambios sin guardar, el navegador/editor debe advertir antes
  de salir, incluso mediante los nuevos enlaces.
- No hay llamadas a OpenAI por abrir la guía.
- Verificar que los borradores previos permanecen inalterados.

## Reglas para la entrega piloto
- Todas las variantes pueden tener nombre de origen aunque su ficha comercial en KIKI no esté iniciada.
- Candidatos ML/TN por SKU NO confirman publicación; faltantes en una copia NO confirman ausencia real.
- La conexión ML requiere autorización del titular y renovación del snapshot; TN usa el CSV disponible.
- Cada modificación editorial debe guardarse de forma explícita y verificarse después de recargar.
- El piloto no publica ni escribe en Ecomm-App, Mercado Libre o Tiendanube.
