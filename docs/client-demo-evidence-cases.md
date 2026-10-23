# KIKI Tech — recorrido de demostración con casos reales (API-only)

## Objetivo de negocio
Eliminar correcciones producto por producto; detectar publicaciones ya existentes,
identificar productos faltantes, mejorar calidad de fichas, preparar publicación
masiva hacia Mercado Libre y enriquecer Tiendanube. La preparación/publicación
operativa y el motor principal de decisiones todavía requieren migración a API.

## Para la presentación
1. Abrir **Inicio**: 3.127 variantes Ecomm-App desde API, 2.720 filas de ML
   desde copia API guardada; 2.684 SKU exactos únicos no aprobados.
2. Entrar **Casos para revisar**: filtros reales para 77 discrepancias de
   presentación, 13 packs con posible equivalencia, 29 GTIN ML inválidos,
   15 sin SKU coincidente Ecomm, 21 sin SKU ML, y 2.565 SKU exactos
   sin corroboración adicional de GTIN (sobre copias registradas).
   Estos números son indicativos de la última captura, no valores fijos
   ni fuentes en tiempo real.
3. Elegir un **caso real**. Ver el título de Mercado Libre y la ficha de
   Ecomm-App con ID, SKU, GTIN y bandera `is_combo` lado a lado.
4. Si hay SKU Ecomm, pulsar **Consultar en Ecomm API**: la búsqueda
   prellenada usa exclusivamente el snapshot API Ecomm. Allí se puede
   hacer una consulta puntual en vivo a Ecomm para confirmar SKU/ID,
   sin modificar datos.
5. Opcional: pulsar **Copiar resumen del caso**, que incluye ambos lados,
   motivo y advertencia de antigüedad. No equivale a guardar una decisión.

## Implementación
- Endpoint autenticado:
  `GET /api/ecomm-app/stage/ml-cases?status=...&q=...&page=1&limit=20`
- Usa exactamente el clasificador de `api_ml_reconciliation_preview`.
  No reproduce heurísticas en el frontend, para que resumen y casos
  de una misma copia sean consistentes.
- Búsqueda por MLA, SKU, ID Ecomm, título de ML o producto Ecomm;
  páginas de hasta 50 casos, nunca listado completo indiscriminado.
- No existen escrituras al backend ni a ML/TN. No lee fuentes Excel
  históricas, no cambia decisiones anteriores, no mezcla familia SKU
  con identidad de variante y no permite fusionar inventarios.
- La fuente ML fue capturada el 5/10/2026; la cuenta no aparece
  conectada. No debe inferirse disponibilidad o estado vigente.

## Qué falta para dar uso operativo real
Reautorizar ML por el titular, refrescar fuente; completar mapeo por ID
canónico Ecomm, verificación comercial de GTIN y packs, datos de precio/costo,
migración preservando decisiones históricas y comprobaciones end-to-end de
publicación idempotente antes de habilitar escrituras externas.

## Aceptación técnica
- UI filtros por tipo, paginación, búsqueda, panel lateral, links directos
  a SKU Ecomm y responsive.
- Al buscar SKU 2500400, si hay una publicación ML con dicho SKU en el
  snapshot histórico, el caso debe conducir a ID API 7214195.
- Copia ML ausente: error visible, nunca 0 ni fallback al Excel.
- CI backend: tests de listado, selección, consultas, seguridad e integridad.
- CI frontend: TypeScript + Vite.
