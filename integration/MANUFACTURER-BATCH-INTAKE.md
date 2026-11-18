# KIKI — Captura asistida de fuentes por fabricante (piloto de lotes)

**Alcance de esta fase:** ahorrar descargas/subidas manuales de páginas HTML
originales de fabricantes **ya seleccionadas por el operador** desde el
resultado de un sitemap autorizado. No es una IA de investigación completa
ni una importación masiva sin supervisión.

## Operación

1. En **Mi catálogo → Operaciones**, seleccionar entre 1 y 20 variantes de
   **un único fabricante**. El catálogo y sus barcode provienen solo de
   Ecomm-App API.
2. Introducir el sitemap XML de productos del fabricante, previamente
   autorizado en la allowlist del servidor. **Buscar fuentes**.
3. KIKI muestra posibles URLs. Solo las coincidencias **únicas, no ambiguas,
   con SKU estable y unidad no pack** se pueden incorporar en este piloto.
4. El operador confirma cada paso de hasta **dos** fuentes desde la misma
   pantalla. KIKI reconsulta el sitemap y exige **SHA-256 inalterado**.
5. Las páginas seleccionadas se obtienen individualmente, con verificación
   robots.txt, DNS público, HTTPS/TLS con IP fijada y sin redirecciones.
   Cada original HTML puede pesar hasta **4 MiB**; los archivos los analiza
   el lector aislado y se guardan juntos en una única transacción.
6. Se preservan la URL, el SHA-256, el HTML original, los metadatos de
   adquisición y la variante Ecomm ID. Estado inicial **PENDING**.
7. Abrir **Evidencias** para revisar nombre, fabricante, presentación,
   procedencia y afirmaciones individuales. Los archivos incorporados
   no son fuentes oficiales ni hechos aprobados por el mero procesamiento.

## Seguridad, límites y fallos

- **Flag nuevo:** `KIKI_DOCUMENT_BATCH_SOURCE_IMPORT_ENABLED=false`, siempre
  apagado por defecto; requiere también
  `KIKI_DOCUMENT_SITEMAP_DISCOVERY_ENABLED=true`,
  `KIKI_DOCUMENT_PARSER_KERNEL_REQUIRED=true`, esquema documental y
  `KIKI_DOCUMENT_SOURCE_FETCH_HOSTS` con dominios exactos autorizados.
- Control de sesión, CSRF y confirmación expresa del operador.
- 1–2 productos por solicitud; no jobs de navegador, no scheduler,
  no consumo OpenAI, no escrituras a Ecomm-App/ML/Tiendanube.
- Se rechazan URL distintas del sitemap, sitemap modificado,
  coincidencias múltiples, packs, SKU ausentes, identidades Ecomm
  cambiadas, documentos ya incorporados y versiones concurrentes.
- Una falla antes del guardado no archiva nada; una falla de un
  producto durante el guardado revierte toda la transacción del paso.
- Sitios que bloqueen el acceso por robots, requieran cookies, usen
  JavaScript para renderizar productos o excedan los límites quedan
  como excepciones con explicación. No se eluden restricciones.
- **No activar esta función sin aprobación explícita del responsable**
  y validación en el dominio real que la utilizará.

## Limitaciones antes de escalar

La coincidencia de URL es solo una **pista**, no una validación de producto.
La investigación sobre EAN/categorías, la extracción de propiedades
comerciales, los textos SEO y medios originales todavía requieren
probar el flujo con fuentes documentales verificadas. La revisión
de identidades y hechos sigue siendo manual. Para procesar cientos de
productos sin clics repetidos harán falta tareas de backend reanudables,
con límites de dominio y auditoría de consumos, sobre las mismas garantías.

## Pruebas automatizadas

- `backend/tests/test_documental_manufacturer_batch_intake.py`:
  sitemap inmutable, rechazo de ambigüedad, persistencia atómica de dos
  originales, parseo fallido sin guardado y flag desactivado.
- `backend/tests/test_documental_source_fetch.py`:
  robots, TLS, DNS, tipo de contenido, tamaño y ausencia de redirects.

**No se hicieron solicitudes reales a fabricantes durante el desarrollo.**
