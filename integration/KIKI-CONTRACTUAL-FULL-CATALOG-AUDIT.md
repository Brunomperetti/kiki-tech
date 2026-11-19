# KIKI — Auditoría integral de entrega comercial

## Fuente contractual y objetivo

La propuesta Brunito septiembre 2026 (página 3) exige herramientas que procesen
el catálogo en volumen: títulos, descripciones, atributos, categorías y SEO,
EAN/SKU como pistas para investigar, excepciones y validación. **No exige ni
incluye cargar manualmente cada producto**. La página 5 requiere una revisión
general al menos mensual; no una auditoría individual manual de cada SKU.

El pedido mínimo adicional del cliente incluye textos cortos/largos, detalles,
presentaciones, imágenes, videos, jerarquía de categorías/subcategorías y
contenido comercial de calidad **con fuente de origen válida**.

**Esta PR es la medición integral del trabajo pendiente**, no el cierre del
contenido comercial ni una garantía de que un EAN certifique fabricante.

## Auditoría sobre el 100% de la captura Ecomm-App API

Desde `Mi catálogo → Planificar lotes de investigación verificable →
Auditoría comercial integral`:

- **Auditar catálogo completo**: clasificación de cada variante del snapshot
  completo `ECOMM_APP_API_STAGE` (hasta 10.000), sin consultar proveedores,
  sin cambiar la base ni consumir IA.
- **Exportar pendientes (CSV)**: una fila por Ecomm ID y SKU, nombre,
  presentación, barcode API de búsqueda, fecha de captura, estado editorial,
  cantidad de documentos, originales revisados, hechos aprobados cuya versión
  y huella de documento continúan vigentes, imágenes/videos registrados,
  revisión mensual vencida y lista de excepciones.
- Contadores de fuentes, identidad, aptitud de investigación por barcode,
  hechos aprobados, completitud editorial, categoría, SEO, imágenes, videos,
  derechos multimedia y revisión de fichas vencida.
- La cifra `internal_fiches_complete` solo refleja completitud editorial
  y estado `READY_FOR_CHANNELS`. **No certifica** autenticidad del fabricante,
  permisos de uso, GTIN, actualización de canales o publicación.
- Para contar un hecho documental se exige su documento de origen en versión
  y huella actuales, original real en archivo parseado y fuente revisada. La
  auditoría no reemplaza la comprobación profunda del expediente ni verifica
  criptográficamente todos los bytes originales.
- Videos son cobertura deseable, no se exige inventarlos en productos
  cuyos fabricantes no los publiquen o no permitan reutilizarlos. Las
  imágenes y sus URL **no constituyen derechos de uso**: se reporta el
  bloqueo de verificación de licencias.
- Fecha de auditoría significa **reporte generado**, no revisión firmada.
  La frecuencia mensual todavía requiere ejecución y acta de revisión.

## Seguridad y rendimiento

- Lectura de la cola API existente con captura completa validada: no Excel
  Ecomm-App ni inferencia de datos en vivo.
- Consulta compacta de `Document` (IDs, huellas, estados JSON) sin transferir
  HTML/base64; `Dossier` solo metadatos de hechos.
- CSV con BOM UTF-8 y protección de fórmulas Excel. Ningún archivo se envía
  a terceros; el cliente autenticado lo descarga.
- No migra tablas ni agrega tareas periódicas, variables, credenciales,
  consultas a OpenAI o escrituras en Ecomm/ML/Tiendanube.
- Rutas autenticadas de solo lectura:
  `GET /api/ecomm-app/workspace/audit/contractual`
  y `GET /api/ecomm-app/workspace/audit/contractual.csv`.

## Criterios para la entrega del sistema completo

1. Captura Ecomm-App API completa, con auditoría sin IDs duplicados.
2. Investigación de productos recuperable por lotes, con fuentes permitidas y
   original verificable por SKU/EAN y presentación; excepciones explícitas.
3. Hechos documentados sujetos a control y aprobación del operador.
4. Fichas completas con título, título corto, textos cortos/largos, detalles,
   atributos, presentación, fabricante, categoría y subcategoría.
5. SEO verificable, imágenes/videos útiles cuando existan, con licencias
   acreditadas. No afirmar derechos por mera URL.
6. Flujo de revisión/aprobación/preparación por canal sin publicación
   automática sin autorización.
7. Auditoría general y seguimiento de cambios al menos una vez por mes,
   trazabilidad y medición de reducción de trabajo manual.
8. Piloto integral con fuentes reales aceptado por el cliente antes de
   masificar a miles de variantes.

Esta PR aborda **medición y exportación a escala de estos ocho criterios**.
No da por cumplidos los hitos de investigación/medios/generación masiva.
