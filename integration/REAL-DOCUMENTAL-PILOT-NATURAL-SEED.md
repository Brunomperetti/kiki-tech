# Piloto documental real KIKI 2.0 — preparación segura, sin cambios de producción

Fecha de verificación: 2026-11-16. Esta etapa **no declara una ficha aprobada**, no
crea propuestas ni escribe en Ecomm-App, Mercado Libre o Tiendanube. Los documentos
se investigaron por lectura pública y no se cargaron en PostgreSQL.

## Identidad elegida en el catálogo auténtico

Consulta **de solo lectura** a los snapshots Ecomm API y Excel importado en KIKI:

- Ecomm ID de variante: `7518949`
- SKU Ecomm: `9995`
- Nombre y presentación de captura: `Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr`
- GTIN de exportación: `7798180790097`
- Estado de GTIN en Excel: `VALID_UNIQUE`
- La variante debe volver a validarse como **no combo** y contra la captura vigente
  al ejecutar el piloto. El GTIN del Excel **no es una certificación de fabricante**.
- **Discrepancia nominal a resolver:** la captura Ecomm usa `Mix Semillas P/ Ensaladas Sopas Natural Seed X 250gr` mientras la página oficial muestra `Mix Ensaladas y Sopas`. Coinciden la finalidad y la presentación declarada, pero **no es igualdad textual ni validación automática**. El operador debe contrastar la etiqueta/presentación auténtica antes de aprobar vínculos, atributos y nombres editoriales.

## Fuentes públicas encontradas

1. **Página de la marca/fabricante Natural Seed**:
   https://naturalseed.com.ar/producto/mix-ensaladas-y-sopas/
   - Menciona «Mix Ensaladas y Sopas» y presentación 250 g.
   - Describe contenido general como mezcla de frutos secos y semillas al oreganato.
   - **No se localizó allí el GTIN 7798180790097.**
   - Afirmaciones nutricionales o de salud del sitio deben tratarse como declaración
     de la marca, *no* como alegación comercial automática validada.
2. **Ficha comercial de un minorista (New Garden)**:
   https://newgarden.com.ar/mix-ensaladas-y-sopas-natural-seed-x-250-g-sin-tacc.html
   - Menciona la marca, presentación 250 g y el código 7798180790097 como SKU.
   - Es apoyo para búsqueda de identidad, **no reemplaza ficha técnica, etiqueta
     ni documentación oficial**.

## Matriz de hechos del piloto (relectura pública 16/11/2026)

Esta es una **preselección documental**, no una aprobación ni una ficha escrita
en KIKI. Las URLs siguen siendo fuentes externas: registrar fecha, fragmento
y versión antes de aceptar cualquier dato.

| Campo candidato | Respaldo hallado | Decisión segura |
| --- | --- | --- |
| Nombre comercial | Sitio Natural Seed: «Mix Ensaladas y Sopas» | Candidato a contraste con el nombre de Ecomm, nunca sustitución automática |
| Presentación | Sitio Natural Seed: «Peso 250 g» | Candidato para esta presentación, sujeto a identidad Ecomm ID+SKU |
| Descripción general | Sitio Natural Seed: mezcla de tres frutos secos y tres semillas al oreganato | Solo dato descriptivo acotado; contrastar etiqueta antes de precisar composición |
| GTIN/EAN `7798180790097` | Excel Ecomm + SKU visible en New Garden | **Solo pista**, no GTIN certificado por fabricante |
| Ingredientes específicos | Listado en New Garden, no detallado en la página oficial consultada | **No aprobar** como especificación de fabricante sin etiqueta/ficha técnica |
| «Sin TACC» o «libre de gluten» | Declaración de New Garden | **No aprobar certificación/claim** sin respaldo documental específico vigente |
| Beneficios nutricionales o de salud | Alegaciones comerciales en los sitios | **No generar automáticamente** alegaciones de salud o valores nutricionales |

Ningún campo de esta matriz fue ingresado, aprobado, publicado ni exportado.
La próxima prueba aislada debe demostrar que el sistema conserva la fuente
y el fragmento por campo, diferencia candidatura de hecho aprobado, bloquea
contradicciones y deja un borrador interno recuperable tras recargar.

**Estado:** `PENDIENTE_VERIFICACION`. Es un buen primer caso porque el catálogo
tiene ID y SKU exactos y existen una página de la marca y otra con código.
No se verificó una correspondencia oficial inequívoca del código con el fabricante.
No se aprobaron ingredientes, alérgenos, certificaciones ni propiedades de salud.
El operador deberá comparar documentación y la etiqueta de esta presentación.

## Orden del piloto después de la habilitación documental

1. Restaurar respaldo de PostgreSQL en **ambiente aislado**, excluir secretos y
   validar la restauración; no usar el servidor productivo como ensayo.
2. Aplicar migración documental explícita y reversible en esa copia con
   `app.services.v2_schema`; comprobar `kiki_evidence_control`,
   `kiki_evidence_documents` y `kiki_evidence_dossiers` e índices.
3. Mantener canales, OpenAI y publicación desactivados. Habilitar documentos
   únicamente en la copia; autenticar un operador autorizado.
4. Abrir exactamente Ecomm ID `7518949`, registrar las fuentes con fecha,
   ubicación/fragmento y documento original autorizado; el sitio oficial no
   certifica por sí solo procedencia hasta ser revisada.
5. Comparar identidad, marca, presentación, GTIN y tipo de unidad; registrar
   discrepancias antes de extraer hechos. Aprobar individualmente solo
   afirmaciones comprobables y con cita. Los campos sin respaldo quedan vacíos.
6. Generar propuesta determinista desde hechos aprobados, decidir por campo,
   guardar **únicamente borrador interno** con versión esperada y revisar
   persistencia e historial tras recargar.
7. Revocar una fuente y verificar que los hechos y propuestas asociados queden
   suspendidos. Ensayar cambio de SKU, GTIN o presentación, un intento
   concurrente de guardado y restauración de respaldos.
8. Solo luego evaluar generación IA con presupuesto y consentimiento operativo,
   sin aceptar citas fabricadas, y procesamiento por lotes con límites.

**Criterios de aceptación:** ninguna característica sin cita, ningún hecho de
otra variante, ninguna importación/consulta externa no autorizada, ninguna
publicación automática y ningún cambio de stock/precio. Revisión editorial y
vigencia de fuentes al menos cada 30 días.
