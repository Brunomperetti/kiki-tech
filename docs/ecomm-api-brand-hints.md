# KIKI Tech — marca sugerida sin llamadas de IA

## Por qué
El cliente quiere automatizar la revisión de marcas sin completar ficha por
ficha ni introducir datos inventados. Los cruces de marca antiguos utilizaban
la planilla histórica de Ecomm como ancla y no sirven para el nuevo flujo
exclusivamente por API.

## Implementación
- La identidad proviene **solo** de `ECOMM_APP_API_STAGE` (Ecomm API).
- Exige un único ID propietario del **SKU exacto** entre todas las variantes.
  No interpreta prefijos de familia, inventa componentes de packs ni une
  IDs por GTIN.
- Lee marcas declaradas por otras fuentes, **sin autorizar cambios**:
  `MERCADOLIBRE_API` (copia API) y `TIENDANUBE` (CSV).
- Solo considera SKU propio de la variación ML cuando existe `#variant_id`.
  No usa el SKU del producto madre para identificar variaciones.
- Rechaza marcas vacías/placeholder, múltiples productos TN con mismo SKU,
  presentaciones ML incompatibles y discrepancias de marca entre canales.
- Si encuentra exactamente una marca no contradictoria, muestra una
  propuesta y cada evidencia con publicación/ficha y fecha de captura.
  La marca **no se autoguarda**: «Usar marca» la copia al formulario y
  el operador debe verificar el envase y guardar.
- **No lee `ECOMM_APP` ni `ECOMM_APP_RAW` para identificar productos**;
  no hace cambios en Ecomm, ML, Tiendanube, precios, GTIN o stock.
- Endpoint: `GET /api/ecomm-app/workspace/brand-hints/{ecomm_id}`.

## Demostración
Abrir `/workspace?id=7214195`, revisar sección «Marca sugerida por
evidencia», observar si existen fuentes y cuál es su fecha.
Si no hay marca o existe contradicción, KIKI lo debe comunicar claramente
en vez de inventarla. El operador puede luego generar sugerencias de título
y descripción con KIKI AI usando la marca guardada en la ficha.

## Límite
Las copias de Mercado Libre y Tiendanube pueden estar desactualizadas.
Una marca declarada por un marketplace **no sustituye la verificación del
producto o su fabricante**. Nunca aprobar masivamente sin evidencia clara.
