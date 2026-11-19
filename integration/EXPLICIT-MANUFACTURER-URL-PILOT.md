# KIKI — incorporar documentación por URL exacta sin sitemap

## Problema de la entrega
El piloto de sitemaps (#181, #185, #186) depende de un sitemap XML de
productos permitido por cada fabricante. Muchos comercios publican fichas
auténticas sin disponer de ese índice. Eso no debe obligar al operador a
copiar los textos y tampoco autoriza un crawler indiscriminado.

## Nueva operación
**Mi catálogo → Ficha → Evidencias → Incorporar archivo o referencia.**
Si el piloto está habilitado, aparece **Incorporar una URL exacta sin sitemap**.

1. El operador identifica la variante por Ecomm ID y contrasta a mano
   marca, presentación y nombre con la página propuesta.
2. Pega la **URL HTTPS exacta** de una única ficha pública, deja una nota
   de cómo encontró la fuente y marca la autorización de consulta.
3. Confirma el GET. KIKI comprueba dominio exacto permitido, resolución
   DNS pública, TLS con SNI, `robots.txt`, no-redirect, noarchive y
   UTF-8. Límite de HTML original: **4 MiB**; lector aislado.
4. KIKI contrasta nuevamente Ecomm ID, SKU, presentación, barcode de
   captura API y tipo de unidad después de la red. Bloquea si hubo cambios
   de identidad o versión, si ya se había guardado la URL o si hubo una
   consulta automatizada ese día.
5. Conserva original, hash, URL, fecha y comprobante de consulta.
   La fuente queda **PENDING**; no se aprueban identidad ni atributos.
6. La revisión humana de procedencia, identidad y cada hecho continúa en
   la misma pestaña, antes de cualquier propuesta comercial/SEO.

## Activación
Configuración nueva, apagada por defecto:
`KIKI_DOCUMENT_EXPLICIT_URL_INTAKE_ENABLED=false`.

Para un piloto real se requiere, además:
- `KIKI_DOCUMENT_WORKSPACE_ENABLED=true` y tablas documentales existentes.
- `KIKI_DOCUMENT_PARSER_KERNEL_REQUIRED=true` y lector aislado operativo.
- `KIKI_DOCUMENT_SOURCE_FETCH_HOSTS` con los dominios exactos autorizados
  separados por comas (sin comodines ni subdominios implícitos).
- Autorización previa del responsable para configurar esos dominios,
  consulta externa y verificación de derechos del contenido.

**No se activó ninguna variable ni se accedió a proveedores al desarrollar
este cambio.** No se requieren nuevas tablas ni migración de PostgreSQL.

## Pistas reales de la selección 18/11 — NO verificadas en KIKI
| Ecomm ID | Variante mostrada | Página candidata exacta |
|---|---|---|
| 6754660 | Natufarma Carotenos vitaminas A, C y E × 30 comp. | https://www.tiendanatufarma.com.ar/productos/carotenos-x-30-comprimidos/ |
| 6951967 | Vita Biosa Natural 500 ml | https://tienda.biosalatam.com/producto/vitabiosa-probiotico-bebible-sabor-natural/ |
| 9534747 | Vita Biosa Naranja 500 ml | https://tienda.biosalatam.com/producto/vitabiosa-probiotico-bebible-sabor-naranja/ |

Páginas descubiertas por consulta pública del 18/11/2026. **No hay
comprobación del EAN en esas páginas ni del vínculo comercial exacto con
la variante Ecomm.** Las coincidencias de nombre/presentación son solo
pistas y no constituyen aprobación de fuente. El acceso automatizado a
`robots.txt` y sitemaps **no pudo verificarse desde el entorno de
investigación**. Por eso el nuevo botón permanece apagado.

Los otros productos de la selección se mantienen `FIND_SOURCE` hasta
tener un documento auténtico. Ninguna página de terceros ni búsqueda
general suplanta una fuente verificable.

## Restricciones contractuales que se conservan
- **Ecomm-App solo API**, no se consume ni importa Excel Ecomm-App.
- Sin IA paga, propagación de atributos sin respaldo o publicación
  automática a Ecomm-App, ML o Tiendanube.
- No se sobreescriben fichas, precios, stock o históricos.
- Error de robots/noarchive/HTTPS/lectura deja la variante pendiente.
  El operador puede incorporar un HTML original guardado manualmente
  con fecha, URL y revisión de procedencia independiente, sin simular
  que la consulta directa fue autorizada.
- Este piloto es **una URL por acción humana**. La etapa siguiente debe
  integrar manifiestos de URLs aprobadas a la cola reanudable (#186),
  aplicar previamente su migración pendiente tras backup restaurable y
  luego habilitar lotes con cuotas reales y evaluación de excepciones.
