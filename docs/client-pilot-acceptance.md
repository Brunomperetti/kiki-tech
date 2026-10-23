# KIKI Tech — Piloto API Ecomm-App exclusiva (primera etapa)

## Decisión del cliente
El 23/10/2026 se pidió trabajar con Ecomm-App **solo por API**, sin seguir
utilizando como catálogo vigente el archivo Excel de septiembre.

### Qué está implementado en esta etapa
- `/pilot` muestra el **catálogo Ecomm capturado desde API**, no el Excel.
- `GET /api/ecomm-app/stage/catalog` devuelve un catálogo de variantes
  paginado (máximo 50 por página), filtrado por SKU/ID/descripción/GTIN,
  únicamente desde `ECOMM_APP_API_STAGE`.
- Rechaza la consulta si la copia API no está completa, sin recurrir al Excel.
- Muestra ID de variante, SKU, nombre, bandera `is_combo`, GTIN informado,
  depósitos y stock **al momento de captura**.
- Desde cada variante con SKU permite consultar **en forma puntual y explícita**
  a Ecomm-App mediante el endpoint autorizado de lectura por SKU.
  Solo presenta stock de la respuesta como coincidente si la consulta devuelve
  un SKU exacto único con el **mismo ID** de variante.
- Mercado Libre y Tiendanube se consultan por separado como fuentes de canal,
  sin asumir que fueron conciliadas con el catálogo API.
- La navegación diferencia Catálogo Ecomm API de Productos/Tareas históricos.

### Qué todavía NO está migrado
El reconciliador principal, las decisiones internas, Productos/Tareas históricos
y Preparación ML siguen utilizando `ECOMM_APP` (Excel). Quedan identificados
como históricos en la interfaz y **no deben presentarse como resultados del
nuevo catálogo API**. Esta etapa NO activa escrituras, stock sincronizado ni
publicación masiva.

No se usará `ECOMM_APP` como fallback silencioso de los endpoints API.
Las decisiones existentes se conservan intactas hasta que haya migración
probada por ID de variante y controles de integridad.

## Prueba de aceptación
1. En Render Live, entrar con sesión a `/pilot`. Verificar que Ecomm API
   esté completa, con 63/63 páginas si la captura sigue siendo la misma.
2. Comprobar variantes API (~3.127 en el snapshot de 23/10) en lugar de 3.029
   productos canónicos históricos.
3. Buscar un SKU de combo conocido, por ejemplo `2500400`, y verificar
   que aparece con su **ID de variante propio**; no unificarlo con `2500`.
4. Pulsar **Consultar API** sobre una variante; confirmar que se distingue
   `EXACT_SINGLE` + ID idéntico de los demás casos, sin asignar stock por
   coincidencia aproximada.
5. Intentar una búsqueda sin resultados; debe mostrar cero coincidencias en
   una copia completa, sin recuperarlas silenciosamente del Excel.
6. Si falta copia API, se debe mostrar error y no un catálogo vacío.
7. Verificar que no hubo escrituras en `ECOMM_APP`, snapshots de canales,
   decisiones históricas o publicaciones.

## Requisitos antes de activar la API como fuente operativa general
- Reconfirmar extracción completa y consistencia temporal de las páginas API.
- Cobertura real y vigente de precios, costos, marca y datos por canal; el
  scope `inventario:leer` no garantiza esos campos.
- Revisión de 99 variantes API sin ID histórico, un ID histórico faltante,
  dos cambios sustanciales de SKU y duplicidades de GTIN/combo.
- Migración y trazabilidad de decisiones existentes por **ID estable**,
  evitando decisiones por prefijo de SKU.
- Conciliación ML/TN en modo simulación, métricas comparativas, pruebas,
  puntos de control y reversión antes del cambio definitivo.
- Aprobación explícita del cambio operativo; por defecto sigue bloqueado.

## Regla de negocio
`5028`, `5028000`, `5028999` pueden ser una familia comercial, pero
no demuestran una misma variante física. Nunca fusionar stock, GTIN, marca o
componentes de combo solo por el prefijo.

## Criterio de comunicación
Podemos afirmar: **"Ya podemos buscar y verificar productos exclusivamente
desde la API de Ecomm-App; ahora debemos migrar de forma segura el resto del
sistema para que las decisiones y la conciliación también usen esa fuente."**

No afirmar: "Todos los módulos ya trabajan con API" ni "el stock de la
copia por páginas es en vivo".
