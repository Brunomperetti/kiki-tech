# KIKI — Reextracción de evidencias ya revisadas por selección

## Motivo de la entrega
El piloto Natural Seed (Ecomm ID `7518949`, SKU `9995`) cuenta con un
original de fabricante revisado, pero los tres hechos existentes siguen
`STALE`. No se pueden usar para completar una ficha hasta que el operador
concilie la identidad del producto y apruebe las afirmaciones.

La captura masiva de páginas de fabricante continúa condicionada por
allowlist, robots, permisos y la migración de la cola reanudable. Esta mejora
agiliza lo que **sí** se puede preparar inmediatamente: los datos de
originales que KIKI ya tiene incorporados, una vez que un operador haya
revisado identidad y procedencia.

## Operación
**Mi catálogo → Seleccionar hasta 20 variantes → Operaciones →
Reextraer hechos de fuentes revisadas.**

- Pide confirmación antes de modificar hechos `PENDING`.
- Consulta únicamente la captura completa Ecomm-App API, jamás Excel.
- Por variante exige **exactamente un documento original real** con
  procedencia `REVIEWED` y texto `TEXT_EXTRACTED`. Si hay dos fuentes
  candidatas, bloquea y pide elegir manualmente en Evidencias.
- Exige que `Research.identity_blockers`, `additional_blockers` y
  `parser_blockers` estén vacíos. Un EAN faltante en la web no se valida
  automáticamente; un EAN contradictorio sigue bloqueado.
- Invoca la **reextracción documental versionada ya existente** de KIKI.
  Las afirmaciones nuevas, cambiadas o previamente caducadas quedan
  `PENDING`. Las verificaciones `APPROVED` que siguen siendo válidas
  conservan estado, versión, responsable e historial.
- Una variante incompatible no bloquea otras. Devuelve motivo y vínculo
  a la pestaña Evidencias para revisión humana.
- No consulta fabricantes, no consume IA, no guarda ni publica fichas,
  no cambia stock/precio/canal y no aprueba hechos.

### Piloto Natural Seed (paso obligatorio del operador)
1. Ecomm ID `7518949`, SKU `9995`. El documento de Naturalseed
   `https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/` tiene
   nombre `Mix Ensaladas y Sopas` y presentación `250 g`; Ecomm-App
   registra `Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr`.
2. Abrir el original y corroborar etiqueta/fabricante/variante real.
   El barcode `7798180790097` **solo proviene de la captura Ecomm API**;
   la página no declara EAN. No se debe afirmar que el fabricante lo certifica.
3. En Evidencias, **Registrar equivalencia revisada** con un motivo
   específico que deje constancia del cotejo. Si no se comprueba la
   correspondencia, NO registrar la equivalencia.
4. Seleccionar esa variante y ejecutar reextracción. Se esperan
   tres hechos `PENDING`: nombre, presentación y características,
   ninguno aprobado automáticamente.
5. Abrir Evidencias y verificar cita, ubicación, valor, contexto
   comercial y si la afirmación tiene condiciones particulares. Aprobar
   **individualmente** lo válido. Sin asumir ingredientes, certificación,
   categoría o autorizaciones multimedia por el texto de la ficha.
6. Desde Ficha/IA: crear propuesta interna de título, título corto,
   descripción, atributos y SEO a partir de hechos `APPROVED`.
   Revisar y guardar manualmente. Se registran campos todavía faltantes.
7. Recién con aprobaciones reales mostrar la ficha piloto al cliente.
   Una propuesta interna todavía NO es una publicación.

## Validación y límites
- Endpoint autenticado y CSRF:
  `POST /api/ecomm-app/workspace/sources/reextract-reviewed`, cuerpo
  `{"ecomm_ids":["7518949"],"confirm":true}`.
- Selección máxima: 20, Ecomm ID único y presente en API completa.
- Sin variables nuevas ni migración. Reutiliza tablas documentales ya
  existentes y el motor Research con CAS de dossier/documento.
- Regresión en SQLite descartable con documento HTML **ficticio**;
  ningún sitio real fue consultado por tests.
- La entrega contractual todavía requiere: multimedia autorizada,
  taxonomía por canal, captación de proveedores con permisos y auditoría
  mensual registrada. El piloto no prueba cobertura de 2.600 productos.
