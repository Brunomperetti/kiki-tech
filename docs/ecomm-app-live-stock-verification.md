# Ecomm-App — Prueba puntual de stock actual (solo lectura)

## Evidencia que motivó la prueba (23/10/2026)

La PR #121 confirmó que una ficha histórica puede alinearse por ID de variante con una copia de la API, **sin sustituir los datos comerciales**.

Casos reales:
- Pack x2 Vitamina C Sundance, ID `9183101`, SKU Excel `VITAMINACSUNDANCE100`, SKU API `6102100`. Stock histórico **40** vs snapshot API **26** (depósitos 21+5).
- Aceto Balsámico Lauri Millán, ID `9211791`, SKU Excel `6166`, SKU API `5345000`. Stock histórico **5** vs snapshot API **375** (depósitos 365+10).
- Cobertura previa: 3.028 IDs estables emparejados, 3.028 con precio y costo históricos presentes (no necesariamente válidos ni actuales), solo 1.257 con marca informada. Las 1.771 marcas históricas faltantes requieren examen independiente; no significan que no exista marca en KIKI.

## Implementación PR #122

En `/imports` > copia completa > comparación histórica > ficha híbrida:

1. Primero se comparan 1-5 IDs entre los dos snapshots: `ECOMM_APP` (Excel) y `ECOMM_APP_API_STAGE` (copia API).
2. Solo después de un **segundo clic explícito**, `Consultar stock actual (solo lectura)`, se consulta **una vez** el POST oficial `/api/v3/public/inventario/productos/consulta` con los SKU exactos de las variantes almacenadas. Ese POST **solo lee stock**.
3. Se inspeccionan todas las variantes hermanas devueltas; únicamente se acepta para diagnóstico un **SKU literal único** y un **ID interno de variante que coincida exactamente** con el solicitado.
4. Se exige `total_stock` numérico y depósitos con stocks numéricos cuya suma sea igual al total. El stock cero se considera válido, pero un campo ausente nunca se transforma a cero.
5. Si falta el SKU exacto, cambió el ID, hay duplicidad, falta stock/depósitos o la suma no coincide, KIKI devuelve **estado no verificado**. No selecciona un candidato arbitrario.
6. Se muestran tres columnas conceptuales de fecha/stock: Excel histórico, snapshot API previo y lectura puntual reciente, junto con el momento UTC de consulta y el desglose por depósito.

**No se añade ningún cron ni sincronización recurrente.** El endpoint está sujeto a sesión+CSRF, máximo 5 IDs, un clic, una solicitud remota secuencial y acceso a la misma clave existente `ECOMM_APP_API_TOKEN` con scope `inventario:leer`. No se persisten resultados ni credenciales y no se modifica ningún snapshot, publicación ni dato operativo.

### Precauciones operativas

- Una respuesta comprobada muestra estado **en el instante de consulta**, no reserva existencias ni garantiza su valor minutos después.
- Los combos pueden calcularse por componentes y sus reglas requieren inspección independiente: un total consistente **no autoriza publicar o descontar stock**.
- Si el origen cambió el SKU y reutilizó el anterior, la coincidencia por SKU sin el mismo ID se **rechaza**.
- Se deben validar fuentes de precios/costos, integraciones de canales, reglas de combos, recargas y reversión antes de cualquier cambio de fuente principal.
