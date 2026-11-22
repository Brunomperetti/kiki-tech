# KIKI 2.0 — Relevo para Codex (22/11/2026)

## Fuentes textuales completas
- `integration/CODEX-ISSUE-174-CUERPO-INTEGRO.md`: **cuerpo íntegro** de GitHub issue #174 tal como se recuperó con el conector el 22/11/2026, sin modificar ni reducir. No incorpora todos los comentarios del issue.
- `integration/CODEX-PLAN-MAESTRO-2026-11-19-TEXTO.txt`: transcripción de texto **sin resumir** del documento Word de cinco páginas `KIKI_Tech_2_0_Plan_Maestro_de_Ejecucion_2026-11-19(1).docx`. Conserva marcadores de página de la extracción; el DOCX sigue siendo el original para formato/tablas.

## Importante: los estados históricos de esas fuentes están desactualizados
La rama se creó sobre `main` en el commit `05e9f97556373e7a0eba2cc2217088ec62f6a0b1` (PR #205 fusionada y desplegada en API y web). La PR #194 está fusionada; #173 cerrada como obsoleta; #201 integrada; #203 (reconfirmación de procedencia), #204 (revisión conjunta de hechos) y #205 (consulta rápida de canales) están fusionadas y desplegadas. CI de main 4/4 aprobada.

Producción verificada mediante SQL de **solo lectura**, 22/11:
- Captura API Ecomm del 21/11: **2.234 variantes distintas** (no confundir con 2.784 del Excel histórico).
- 3 fichas comerciales iniciadas, las 3 en **DRAFT**, **0** READY_FOR_CHANNELS.
- 2 documentos originales archivados, 4 expedientes, 1 lote editorial.
- Natural Seed Ecomm ID 7518949, SKU 9995: documento v3 con procedencia revisada y equivalencia humana actualizada; 3 hechos aprobados; ficha comercial **DRAFT v6** (SEO editado). Código EAN de Ecomm sin certificación independiente del fabricante; foto sin licencia de uso registrada.
- Canales: Mercado Libre muestra candidato desde captura vencida, no vinculación vigente; Tiendanube CSV muestra `GTIN_CONFLICT` y `SALE_TYPE_CONFLICT`, no aprobar.
- En PostgreSQL 18.6 productivo **NO existe** `kiki_source_intake_jobs`, por lo que la cola reanudable no está activa. La etapa 1 se **cerró operativamente POR EXCEPCIÓN**: restauración real de respaldo pendiente; esta excepción NO autoriza migrar ni encender flags.
- Flags efectivos de fabricante siguen sin certificarse por falta de lectura de valores desde el conector, **no afirmar que están apagados en producción** simplemente porque sus defaults estén apagados en código.

## Encargo prioritario
Completar conforme a la lista contractual de #174 y las etapas 2–6 del Plan Maestro. Exigir evidencia de aceptación real. La definición de 100% es **100% de funcionalidad contractualmente probada y 100% de variantes clasificadas en estado explicable**, no 100% de fichas con fabricante/medios certificadas sin fuentes.

Avanzar con PR pequeñas de funcionalidad real, pruebas backend/frontend/PostgreSQL y criterios de aceptación; no duplicar las funciones integradas. Separar TODO bloqueo por fabricante/permiso/backup/usuarios. No activar servicios externos o IA de pago, no hacer DDL sobre PostgreSQL, no actualizar variables, credenciales, stock, precios o productos, no fusionar ni desplegar ni publicar sin permiso explícito del responsable.

## Recomendación de eficiencia
Leer los dos archivos por ruta, sin consultar la API de issues. Comparar contra código actual y repartir por frentes de desarrollo sin solaparse: (a) ingestión documental/cola, (b) fichas/taxonomía/multimedia, (c) revisión mensual/expresiones de salida, (d) pruebas/aceptación. No gastar ciclos reabriendo debates ni pidiendo al responsable repetir capturas de funciones ya verificadas.
