# KIKI — Manifiesto de URLs exactas para investigación reanudable

**Objetivo de entrega acelerada:** poder preparar fuentes para 20 variantes
de **un mismo fabricante** sin exigir sitemap XML, sin copiar manualmente
el contenido y sin perder el avance por cierres del navegador.

## Proceso del operador

1. En el catálogo Ecomm-App API, seleccionar hasta 20 variantes distintas.
2. En `Operaciones → Fuentes de fabricantes → URLs exactas`, pegar
   `Ecomm ID;URL HTTPS exacta;nota de procedencia` por línea.
3. Confirmar que cada URL es de **ese producto y presentación**. El
   manifiesto solo se guarda, **no realiza un GET todavía**.
4. `Procesar siguiente fuente`: una consulta por clic con comprobación
   de DNS público, TLS/hostname, allowlist de fabricante, robots.txt, no
   redirects, HTML UTF-8 ≤ 4 MiB, cuota de una descarga por variante y
   día, y control del SKU/EAN API/tipo de venta.
5. Una fuente archivada queda **PENDING**; revisar identidad y procedencia,
   aprobar hechos individuales y generar propuesta documental en el módulo
   editorial existente. No equivale a una publicación ni a datos certificados.
6. Si un producto falla, los demás continúan; hasta 3 intentos por variante,
   cancelación de pendientes, historial de acción y recuperación tras
   interrupción.

## Lo que esta PR resuelve y lo que NO

La PR combina el motor de URL exacta (#190) con la cola reanudable
(#186), sin nuevo esquema ni cambios al catálogo. Reutiliza la tabla
`kiki_source_intake_jobs` **que falta crear en producción**.

No hace búsqueda autónoma ni 2600 consultas a fabricantes. El usuario
debe conseguir y revisar las URLs de cada producto; esta fase hace
**eficiente, trazable y reanudable** su incorporación. La automatización
de investigación masiva y el enriquecimiento editorial completo siguen
pendientes de fuente válida y revisiones.

No hay aprobación automática, guardado de fichas, multimedia, IA paga,
cambios de precios/stock ni publicación a Ecomm, Mercado Libre o Tiendanube.

## Activación controlada posterior a PR y backup

La producción mantiene todos estos flags desactivados por defecto:

- `KIKI_DOCUMENT_RESUMABLE_INTAKE_ENABLED=true`
- `KIKI_DOCUMENT_EXPLICIT_URL_INTAKE_ENABLED=true`
- `KIKI_DOCUMENT_PARSER_KERNEL_REQUIRED=true`
- `KIKI_DOCUMENT_SOURCE_FETCH_HOSTS=<lista exacta autorizada>`

También requiere la infraestructura documental existente y aplicar
expresamente `backend/app/services/documental/source_intake_migration.py`
tras **backup restaurable y ensayo en PG18**. Sin esa tabla, la UI no
muestra el módulo y la API responde error cerrado.

No activar estos flags ni agregar hosts solo porque el sitio sea público:
comprobar términos, permisos de acceso y el producto exacto antes de la
primera captura. Los cinco productos analizados el 18/11 mostraron 0
hechos aprobados; no son una muestra de contenido enriquecido.

## Manifiestos candidatos para un piloto — no autorizados ni aprobados

Separar estos casos por dominio de fabricante y verificar identidad, EAN
y presentación en Ecomm-App, especialmente porque las páginas no muestran
necesariamente el código de barras de la variante:

- Natufarma Carotenos 30 comprimidos, Ecomm `6754660`:
  `https://www.tiendanatufarma.com.ar/productos/carotenos-x-30-comprimidos/`
- Biosa Natural 500 ml, Ecomm `6951967`:
  `https://tienda.biosalatam.com/producto/vitabiosa-probiotico-bebible-sabor-natural/`
- Biosa Naranja 500 ml, Ecomm `9534747`:
  `https://tienda.biosalatam.com/producto/vitabiosa-probiotico-bebible-sabor-naranja/`

Estas URLs son **pistas**, no una certificación del fabricante ni una
licencia para copiar imágenes o claims de salud. El acceso de
`robots.txt` sigue sin confirmarse desde el entorno de consulta.
El capturador bloqueará el intento si el sitio lo deniega.

## Validación técnica

- Pruebas de manifiestos sintéticos: 20 máximo, un dominio, identidad
  Ecomm, idempotencia, no refetch, fallos aislados, reintentos, CAS.
- Se mantienen CI backend/frontend y PostgreSQL 18, sin migraciones en el
  arranque ni inserción de contenido en producción.
- Después de integrar: probar un documento auténtico y una ficha
  comercial completamente revisada, no solo que Render responda 200.
