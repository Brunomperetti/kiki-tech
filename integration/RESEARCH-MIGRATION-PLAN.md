# Plan de migración documental — sólo para revisión posterior

**Este plan no autoriza ni ejecuta una migración productiva.** El código actual
crea únicamente `kiki_research_test` en PostgreSQL descartable después de validar
su destino. No modifica modelos existentes, datos ni tablas productivas.

## Reversión del prototipo

La reversión habitual es apagar el proyecto Docker: desaparece el PostgreSQL
tmpfs. Si se necesitara una reversión selectiva dentro de esa misma base de
pruebas, validar primero nombre de base, usuario, conexión Unix y comentario
`KIKI_LOCAL_SYNTHETIC_2B`, igual que el preflight. Exportar evidencia de prueba
si se desea conservarla, detener únicamente el harness y eliminar el esquema
`kiki_research_test` con sus tres tablas. Nunca copiar esta instrucción a una
base productiva ni ejecutarla como parte de tests comunes.

Los modelos de `app.database.models.Base` no tienen dependencias ni claves
foráneas a este esquema; quitarlo no altera catálogo, overlays, OAuth, tokens,
decisiones de canales ni historiales previos.

## Antes de proponer una migración real

1. Obtener autorización explícita y una base de ensayo independiente restaurada
   desde un respaldo permitido. No introducir credenciales en este repositorio.
2. Diseñar un esquema normalizado independiente: variantes referenciadas por
   Ecomm ID, documentos/versiones inmutables, hechos versionados, decisiones
   append-only y eventos de invalidación. No reciclar SKU/EAN como PK.
3. Definir FK, unicidad por variante/documento/ubicación, unidades, tamaño de
   evidencia, índices, retención y la identidad real del operador. Versionar
   el contrato y planificar privacidad/roles antes de conectarlo.
4. Sustituir el mutex global por bloqueo específico con orden documentado,
   manteniendo CAS e invariantes entre documento, identidad y decisiones.
5. Preparar una migración aditiva revisable y una reversión ensayada. Los fixtures
   de esta etapa jamás se copian como datos reales ni como evidencia verificada.
6. Validar en PostgreSQL de ensayo: doble decisión, cambio de documento durante
   revisión, cambio de identidad, fallos/reintentos, exportación/restauración,
   rollback y ausencia de modificaciones a fichas/canales existentes.
7. Mantener lectura/escritura deshabilitadas hasta revisar el resultado concreto.
   La aplicación a campos comerciales, investigación externa, descarga de
   documentos, IA y publicación son capacidades independientes que requieren
   autorización y pruebas propias.

No se generó ni ejecutó DDL de producción, no se hizo backfill y no se modificó
Render ni ninguna variable productiva.
