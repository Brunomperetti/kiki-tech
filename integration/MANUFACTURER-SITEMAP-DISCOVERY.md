# KIKI — Descubrimiento documental por fabricante (primer paso)

**Objetivo:** reemplazar búsquedas producto por producto por una consulta
limitada a un índice oficial del fabricante y cruzarlo con hasta 20 variantes
de la captura Ecomm-App vigente.

## Qué hace

1. El operador selecciona entre 1 y 20 variantes en **Operaciones**.
2. Registra la URL exacta de un **sitemap XML de productos** del fabricante,
   cuyo dominio fue autorizado previamente por el responsable.
3. El servidor valida el dominio exacto, HTTPS/TLS, DNS/IP pública fija y
   robots.txt antes de consultar el sitemap. No sigue redirecciones.
4. Descarga **únicamente** robots.txt y el sitemap XML (máximo 256 KiB),
   sin consultar ninguna página de producto. No sigue sub-sitemaps, y rechaza
   índices recursivos, DTD, entidades y contenido comprimido.
5. Cruza nombres y números explícitos (por ejemplo 500 y 60 comprimidos)
   contra los slugs de páginas de productos del mismo host.
6. Muestra candidatos, múltiples coincidencias, faltantes y motivos de
   bloqueo. Una coincidencia **no** certifica fabricante, EAN ni presentación.

## Activación controlada

Flag nuevo: `KIKI_DOCUMENT_SITEMAP_DISCOVERY_ENABLED`, **false por defecto**.
Requiere esquema documental habilitado y
`KIKI_DOCUMENT_SOURCE_FETCH_HOSTS` con cada hostname explícito.
No cambiar variables de Render ni activar sin revisar CI y piloto
con autorización independiente.

Es una función de lectura que usa los servicios existentes: no requiere
servicios adicionales ni IA, worker permanente o migraciones. **No archiva
documentos, aprueba hechos ni crea fichas.** No reemplaza la revisión de
identidad/procedencia de cada fuente.

No funciona si el sitio publica solo índice de sitemaps, HTML dinámico,
XML muy grande o si robots.txt no autoriza. En ese caso queda como
**bloqueo explicable**, nunca acceso forzado.

## Siguiente paso tras validar el primer fabricante

Introducir un paso explícito y limitado de **capturar solo los candidatos
seleccionados** (robots y TLS por URL, tamaño y cuotas por dominio, lector
aislado), revalidar identidad Ecomm ID+SKU, aplicar el mismo versionado
documental, extraer candidatos verificables y generar borradores de forma
reanudable por lotes. La revisión humana resuelve ambigüedades, claims
sensibles y derechos de imágenes; sin publicaciones externas automáticas.

## Pruebas

`backend/tests/test_documental_sitemap_discovery.py` ensaya sitemap XML
sintético, rechazo de otros hosts, denegación de robots, packs incompatibles,
duplicidad/ambigüedad y ausencia de llamadas a páginas de productos.

**No se probó una consulta real al sitemap de Geonat**: ese dominio necesita
autorización y verificación del sitemap que efectivamente publica.
