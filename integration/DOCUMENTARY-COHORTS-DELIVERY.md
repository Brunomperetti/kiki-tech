# KIKI — Lotes documentales planificados sin red (entrega 22/11/2026)

Este componente es parte del Plan Maestro #174, puntos 1, 2, 6 y 9. No reemplaza
`kiki_source_intake_jobs`, ni habilita búsquedas automáticas o editoriales.

## Cómo usar desde KIKI V2

1. Abrir `Mi catálogo → Auditoría comercial integral` y ejecutar
   **Auditar catálogo completo** con la última captura Ecomm-App.
2. Desplegar **Preparar lotes documentales por marca mencionada**.
3. Pulsar **Preparar lotes de hasta 20**. El backend reutiliza la misma
   auditoría de todas las variantes, clasifica solo `FIND_ORIGINAL` y excluye
   los códigos que no están habilitados como pistas de investigación.
4. Consultar los lotes P001, P002, etc. y **Exportar estos lotes (CSV)**.
   CSV y vista incluyen huella SHA-256 calculada de identidades de la captura.
   Si se actualizó Ecomm en el medio, la descarga bloquea una huella distinta.
5. Verificar el fabricante y la presentación de los candidatos de forma
   independiente y resolver URL, robots, permisos y derecho de uso antes de
   **incorporar** un original. Los campos de fuentes/URL verificadas son
   nulos/falsos: no hay aprobación por agruparlos.

## Qué significa «marca mencionada»

La herramienta identifica frases exactas (ignorando tildes/puntuación) dentro
del nombre de origen en la API: Natural Seed, Saint Gottard, Dimax, Vitamin Way,
Sri Sri, Yin Yang, Natier, Granix, Geonat, El Castillo, Graal, Natufarma,
Hileret, Laur, Juan Valdez y Prama. **No afirma que sean fabricantes de esos
productos**, no asigna marcas a la ficha y no infiere fabricantes por prefijo
EAN. Coincidencias múltiples, nombre sin la frase o sospechas de combo/pack se
separan como excepción; no se fuerza un grupo con dudas. Una marca no
reconocida sigue como «sin atribuir» hasta revisar otra evidencia.

Cada cohorte tiene como máximo 20 variantes; solo se seleccionan nombres,
presentación, SKU, Ecomm ID y barcode elegible de la captura API vigente.
**GTIN = pista de búsqueda, nunca prueba de fabricante.** Una ficha que ya
tiene original, como Natural Seed SKU 9995, queda fuera de `FIND_ORIGINAL`.

## Límites y seguridad

- Planificación solo lectura: **0 consultas externas, 0 IA, 0 escrituras DB o canales**.
- No requiere nueva tabla, variables, conexiones ni costos.
- No habilita automáticamente la cola persistente ni guarda un lote;
  `kiki_source_intake_jobs` continúa pendiente de migración con respaldo
  verificado, permiso expreso y flag controlado.
- Los datos de captura son mutables. Comparar la huella e identidad antes de
  preparar un manifiesto, nunca aplicar datos de una captura vieja.
- Los nombres se exportan con escape contra fórmulas de planillas.
- Si la auditoría no cubre el 100% de los Ecomm IDs únicos se bloquea la vista.
- La prueba de aceptación se realiza sin red ni productos reales, y no
  sustituye la revisión de fabricantes/identidad por una persona.

## Siguiente paso para finalizar el producto

1. Aceptar esta planificación con SKU reales, sin confundir marca con fuente.
2. Conciliar altas, bajas y cambios de identidad entre capturas (el 20/11 las
   2.533 variantes del primer informe fueron reemplazadas por otra captura
   con 2.414; no hay evidencia suficiente para identificar qué 119 faltan).
3. Validar backup restaurable en PostgreSQL 18 aislado; autorizar migración
   aditiva de la cola reanudable y permisos limitados para piloto P01.
4. Solo con original auténtico aprobado: extraer hechos, componer ficha
   completa, revisar taxonomía y SEO, solicitar permisos multimedia y
   registrar revisión mensual. Nada se publica en canales sin autorización.
