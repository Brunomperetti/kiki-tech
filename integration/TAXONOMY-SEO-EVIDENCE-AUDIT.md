# KIKI — Conciliación de taxonomía y auditoría SEO por lote

## Motivo

Las categorías de una ficha de fabricante no son necesariamente las
categorías comerciales internas de KIKI, y ninguna etiqueta de un **borrador**
debe propagarse como clasificación validada. La versión anterior del
endpoint `/taxonomy` permite consultar nombres escritos por operadores,
incluidos los de borradores; es útil para autocompletar, no para aprobar
asignaciones masivas.

## Flujo implementado

En **Mi catálogo → Operaciones → Plan comercial desde evidencias**, KIKI
evalúa hasta 20 Ecomm IDs de la captura **ECOMM_APP_API_STAGE**, reutilizando
el expediente documental y su evaluación de hechos `APPROVED` vigentes.

Para cada variante compara:

1. Categoría y subcategoría **documentales aprobadas** con sus IDs de hecho.
2. Categoría/subcategoría ya guardadas en el editor interno.
3. Pares exactos presentes en fichas internas previamente marcadas
   `READY_FOR_CHANNELS`. Los borradores `DRAFT` y
   `READY_FOR_REVIEW` nunca sirven como vocabulario de referencia.

Estados posibles incluyen conflicto documental, identidad o revisión
vencida, jerarquía guardada diferente de la fuente, categoría/subcategoría
ausente, vocabulario inexistente, coincidencia exacta y equivalencia
manual requerida.

Solo una coincidencia normalizada por espacios y mayúsculas/minúsculas
muestra los nombres de una jerarquía interna **como referencia sugerida**.
No hay similitud semántica, IA ni creación de categorías inexistentes.
Incluso las fichas marcadas `READY_FOR_CHANNELS` no certifican por sí
solas el fabricante ni los IDs de categoría en Ecomm, ML o Tiendanube.
**La clasificación requiere decisión humana y no se guarda en esta vista.**

## SEO

Para `seo_title`, `seo_description` y `seo_keywords`:
- `ALREADY_SAVED`: existe texto en el editor interno; no implica validación.
- `EVIDENCE_BACKED`: el generador determinista puede proponerlo usando
  hechos vigentes y aprobados; la propuesta todavía requiere aceptación.
- `NEEDS_EVIDENCE`: sin respaldo suficiente.
- `REVIEW_TAXONOMY`: las palabras clave contienen categorías del fabricante
  cuya equivalencia interna todavía necesita revisión. No presentarlas como
  listas para usar por lote.
- `REVALIDATE`: conflicto de identidad o revisión vencida; no recomendar
  nuevos textos hasta resolver el bloqueo.

Ninguna palabra clave o afirmación de salud puede inferirse por similitud
con productos de terceros. Una categoría de fabricante aprobada no se
transforma automáticamente en taxonomía de canal. El generador documental
anterior sigue pudiendo incluir nombres de categoría aprobados por fuente
en **borradores sujetos a revisión**, porque cambiar su formato rompería
el control de coherencia de fichas ya revisadas para canales. El nuevo
plan de Operaciones retira esos campos de su lista de propuestas listas
para usar si falta equivalencia aprobada; tampoco guarda o publica nada.

## Seguridad

- Endpoint existente de previsualización documental (CSRF y sesión).
- Solo lectura; no realiza DDL ni llama a proveedores, IA, ni a canales.
- No modifica el esquema de PostgreSQL ni activa la cola de descargas.
- No copia categorías de borradores ni genera identificadores externos.
- No modifica stock, precios, imágenes, videos ni fichas.

## Validación y próximos pasos

Pruebas en `backend/tests/test_documental_taxonomy_alignment.py` para
referencias `READY_FOR_CHANNELS`, exclusión de DRAFT, pares exactos,
ausencias, discrepancias y conflicto documental. CI backend, frontend y
PG18.

Sigue pendiente el **mapeo aprobado persistente** entre taxonomía de KIKI
y categorías de cada canal, con versionado y confirmación humana; luego
se podrán generar propuestas de SEO masivas basadas en esos mapeos sin
cambiar publicaciones automáticamente.
