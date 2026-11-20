# KIKI Tech 2.0 — tres niveles de calidad y priorización por SKU

Referencia: Plan Maestro #174 (alcance contractual). Este cambio prepara una
**auditoría completa y de solo lectura**; no valida productos automáticamente.

## Tres niveles que no deben confundirse

1. **Campos cargados (0–100 %)**: presencia/estructura de titulación, descripciones,
   taxonomía, SEO, presentación, atributos, imagen con URL y fuente declarada.
   No acredita autenticidad, derechos, fabricante, código EAN ni calidad expresiva.
   Puede indicar 100 % mientras la ficha permanece `DRAFT`.
2. **Evidencia documental**: documento original, versión, integridad, procedencia
   revisada y afirmaciones individuales aprobadas. Un hecho de características
   no reemplaza nombre y presentación. El conteo de auditoría es preliminar y
   no sustituye los controles transaccionales del expediente documental.
3. **Aptitud comercial/canales**: evaluación adicional y confirmación humana de
   derechos de imagen, taxonomía, exactitud de presentación, código y capturas
   vigentes. El análisis masivo **nunca certifica** publicación ni autorizaciones.

`internal_fiches_complete` se conserva por compatibilidad: requiere que un
operador haya puesto estado interno `READY_FOR_CHANNELS` y estén cargados
los campos. Nuevo `fields_complete` cuenta por separado borradores completos,
sin atribuirles aprobación.

## Etapa prioritaria exclusiva por variante

La auditoría asigna **exactamente una** etapa a cada Ecomm ID, en este orden:

- `REVIEW_IDENTITY`: identificador/variante/SKU ambiguo
- `FIND_ORIGINAL`: conseguir fuente original del producto
- `REVIEW_ORIGINAL`: revisar procedencia e identidad
- `REVIEW_FACTS`: exigir hechos documentales de nombre y presentación
- `REVIEW_TAXONOMY`: resolver categoría y subcategoría ausentes
- `REVIEW_SEO`: completar campos SEO ausentes
- `COMPLETE_FIELDS`: completar campos editoriales restantes
- `ADD_IMAGE`: incorporar imagen trazable si no hay ninguna
- `REVIEW_MEDIA_AND_CHANNEL`: resto de validaciones **pendientes**, incluidas
  licencias multimedia, conciliación de canal, vencimiento y publicación

El último estado **no significa READY ni publicación habilitada**.
`classified_variants == total` se exige, incluso si todas las variantes
necesitan intervención. Es cobertura diagnóstica, no enriquecimiento del 100 %.

## Escala operativa y límites

- El reporte consolida cada categoría y exporta columnas por SKU para agrupar
  trabajo: `campos_completos_sin_certificar`, `porcentaje_campos`,
  `etapa_siguiente`. No modifica los campos ya guardados.
- Mantiene la fuente **ECOMM_APP_API_STAGE** y las incidencias EAN, packs,
  duplicados, derechos, revisiones mensuales y notas de evidencia.
- No consulta fabricantes ni proveedores, no genera IA, no escribe en canales,
  no actualiza stock, costos ni precios y no aplica migraciones.
- Los lotes de investigación reanudables existentes necesitan restauración
  de respaldo y tabla `kiki_source_intake_jobs` con aprobación separada antes
  de habilitar la incorporación documental automática.
- La ficha piloto Natural Seed (Ecomm 7518949, SKU 9995) puede mostrar
  100 % de campos cargados y 3 hechos aprobados, **sin** estar certificada
  para canales: todavía falta resolver derechos de imagen, taxonomía
  verificada, EAN del fabricante y conflictos TN/capturas vencidas.

## Pruebas de aceptación

- 100 % de las variantes auditadas tienen una sola etapa, que se exporta.
- Un borrador estructuralmente completo se cuenta en `fields_complete`,
  pero NO en `internal_fiches_complete` ni como certificado.
- Una característica aprobada sin nombre/presentación obliga a `REVIEW_FACTS`.
- Las discrepancias de identidad tienen prioridad sobre cualquier contenido.
- Suite backend, frontend, PostgreSQL de pruebas y Docker. Ninguna prueba
  sintética acredita productos reales de KIKI.
