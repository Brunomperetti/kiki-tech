# KIKI AI — Validación semántica de packs (25/10/2026)

## Incidente observado
En la prueba real del SKU 2500400 (ID 7214195), la IA creó una
propuesta de título con "sabor sin sabor" y una descripción indicando que
el pack contenía dos frascos de 60 cápsulas **cada uno**.
El texto visible de Ecomm-App ("Pack X 2 ... 60 Cápsulas")
no prueba ni el formato de envase ni el contenido por unidad.
La IA incluso pidió confirmar esa afirmación.

## Corrección
- Instrucciones mejoradas: no derivar cantidades por unidad, envases ni
  composición de packs desde la etiqueta "pack xN".
- Validación del backend de afirmaciones sobre frascos, botellas, envases,
  potes, cajas, sobres y expresiones por unidad ("cada uno",
  "por frasco", "c/u").
- Si la cantidad o presentación no figura expresamente en los textos
  de Ecomm-App, el backend **omite toda la descripción generada** y la
  sustituye por advertencia + pregunta de verificación. No la aprueba.
- Corrige títulos con la expresión redundante "sabor sin sabor":
  conserva "sin sabor" solo si aparece en la fuente textual,
  en caso contrario elimina la frase.
- Los dígitos de **SKU, ID de Ecomm y versión interna ya no se pueden
  usar como prueba de cantidades comerciales**. Solo vale el nombre
  del producto y la descripción de variante que llegaron por API.
- También revalida **propuestas ya existentes** en cada consulta y
  reutilización, sin hacer otra llamada paga ni modificar el historial
  original de propuestas.
- El frontend destaca las alertas por separado, sin permitir copiar
  una descripción vacía.

## Límites
Este chequeo reduce un tipo de alucinación, pero no certifica marcas,
fabricantes, ingredientes, componentes de combos ni propiedades de salud.
**Ninguna propuesta de IA se publica automáticamente**. La persona
debe cotejar fuente/envase, aceptar lo correcto y guardar dentro de KIKI
PostgreSQL. El token Ecomm-App sigue siendo de lectura.

## Criterios de aceptación
- Cargar el borrador IA #2 en `/workspace?id=7214195` después de
  Render Live: la descripción con "dos frascos ... cada uno 60" no debe
  mostrarse como copiable; la pantalla debe explicar el bloqueo.
- No consumir una nueva solicitud IA para revalidar ese borrador.
- Pack con presentación por unidad *explícita* en el origen: permitir
  descripción coherente, siempre para revisión humana.
- Propuesta con número derivado solo del SKU o ID: rechazar.
- Backoffice, ficha editable, borrador manual, listado guardados y
  Tiendanube deben seguir funcionando igual.
