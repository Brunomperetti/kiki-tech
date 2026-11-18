# KIKI — Cola reanudable de incorporación documental

Alcance de la fase: convertir el piloto de incorporación de uno o dos archivos
por clic en una **cola persistente** de hasta 20 variantes por fabricante,
con progreso recuperable al cerrar el navegador y bloqueos por variante.
No es una búsqueda autónoma de fabricantes ni una publicación automática.

## Proceso del operador

1. Seleccionar hasta 20 variantes Ecomm-App API de un mismo fabricante.
2. En Operaciones, consultar un sitemap de producto HTTPS expresamente
   autorizado en el servidor.
3. Revisar las URLs candidatas y confirmar **Preparar lote**. KIKI rechaza
   URL ambiguas, packs, ausencia de SKU y duplicados ya archivados.
4. KIKI crea un lote persistente, **sin descargar aún las páginas**.
5. Pulsar **Procesar siguiente fuente**. Una sola variante por solicitud:
   revalida el sitemap y el Ecomm ID, recupera y archiva el HTML original
   mediante el lector aislado (máximo 4 MiB), registra URL+SHA-256.
6. Cada elemento queda `IMPORTED` (pendiente de revisión documental) o
   `BLOCKED` con error concreto; los demás siguen disponibles.
7. Al cerrar la pestaña, Operaciones recupera los 20 lotes más recientes.
   Reintentos limitados a tres, controles CAS de revisión y cancelación de
   fuentes pendientes, conservando las ya incorporadas.

## Recuperación y protección

- Cada claim se persiste antes de la llamada a la fuente. Solamente un
  paso activo por lote; token de dueño y vencimiento conservador de 10 minutos.
- Si un proceso falla después de persistir el HTML pero antes de informar
  al navegador, el siguiente paso, **tras vencer la lease**, coteja URL
  y Ecomm ID contra documentos archivados para evitar doble descarga.
- Cambios de nombre, SKU, presentación, EAN API o tipo de venta bloquean
  el paso antes de contactar al fabricante.
- Aprobación de fuente/identidad/hechos y publicación están FUERA de esta fase.
  Tampoco hay IA, workers, cron ni llamadas al proveedor Ecomm-App.
- Los registros de lotes no incluyen HTML, credenciales ni fichas editoriales.

## Nuevas piezas

- Tabla aditiva `kiki_source_intake_jobs`. Migración explícita:
  `backend/app/services/documental/source_intake_migration.py`.
  **No se ejecuta automáticamente durante el arranque.**
- Flag separado, desactivado por defecto:
  `KIKI_DOCUMENT_RESUMABLE_INTAKE_ENABLED=false`.
- Requiere además el lector documental, allowlist de dominios y los flags
  de descubrimiento/importación de fuentes ya existentes.
- Endpoints autenticados, con CSRF para mutaciones:
  `GET /api/ecomm-app/workspace/sources/intake-jobs`;
  `GET /api/ecomm-app/workspace/sources/intake-jobs/{id}`;
  `POST /api/ecomm-app/workspace/sources/intake-jobs`,
  `/{id}/step`, `/{id}/retry`, `/{id}/cancel`.
- Se reutiliza el resguardo documental original de PR #185.
- Pruebas offline: idempotencia, CAS, recuperación tras cierre o interrupción,
  identidad Ecomm modificada, error de fuente aislado, reintento, cancelación.
  Sin red ni credenciales.

## Para habilitar en producción, más adelante

1. Confirmar un sitemap real compatible con robots/TLS/HTML. No asumir
   que Geonat o Natural Seed publican el formato exacto.
2. Probar migración y rollback en PostgreSQL 18 descartable. Respaldar y
   comprobar restauración de la base KIKI, aplicar migración expresamente.
3. Autorizar allowlist, flags y piloto de máximo 2 productos auténticos.
4. Verificar que los documentos originales quedan `PENDING` y nunca
   alimentan automáticamente propuestas o canales.
5. Medir errores, repetición, tiempos y cobertura antes de aumentar el
   alcance. El eventual procesamiento programado necesita límites de
   proveedor, consentimiento operativo y controles independientes.

## Limitación contractual vigente

Todavía faltan extracción generalizada de atributos, clasificación
de taxonomía, generación SEO con IA sobre hechos aprobados, derechos
de gráficos y videos y auditoría mensual. Esta cola resuelve la
**durabilidad de la incorporación**, no la validación automática de hechos.
