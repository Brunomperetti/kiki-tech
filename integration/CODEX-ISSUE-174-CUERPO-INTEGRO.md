# Alcance contractual y criterio de cierre — KIKI Tech 2.0
**Referencia:** pedido textual de KIKI Market en noviembre de 2026 + propuesta comercial de Brunito, septiembre 2026, sección **02 Catálogo y Backoffice** (PDF aportado por el responsable). **No cerrar hasta demostrar cada criterio.**

## Objetivo no negociable
Backoffice **WEB** para gestionar el catálogo comercial real, por variante Ecomm ID + SKU y presentación: **titulación corta y larga, descripciones cortas y largas, detalles, características, presentaciones, imágenes y videos; posicionamiento SEO, categorías y subcategorías**. El dato debe ser trazable a **fuentes de fabricante, etiqueta u otra fuente verificable**, con revisión humana por excepciones y **revisión general mínima mensual**. No inventar atributos: **fuente válida primero, IA después**. El flujo esperado es **detectar → investigar → procesar → validar → preparar/publicar con autorización**. Debe operar en lotes; no convertirlo en data entry permanente.

## Estado técnico verificado en Render (lectura del 16–17/11/2026)
- PostgreSQL 18.6. La cifra **2.784** corresponde a un Excel histórico Ecomm-App y **no es el inventario operativo**. La captura API del 17/11/2026 registra **2.667 variantes**, 2.613 con barcode y 54 sin código API informado. La consulta directa al SKU 6317 devolvió barcode 7793396000039.
- Excel GTIN archivado: **no se utiliza para ninguna decisión operativa** desde PR #183. El resumen actual API clasifica **1.546 códigos únicos válidos en variantes no pack, 1.058 repetidos, 7 inválidos, 2 packs y 0 conflictos barcode/GTIN**; esto **no certifica identidades de fabricante**.
- Estado documental actual (17/11): **3 fichas editoriales iniciadas**, **2 documentos originales de fabricante incorporados** y **3 hechos documentales registrados**; **0** listas para canales. Los tres hechos del piloto Natural Seed requieren revalidación (`STALE`). Estas cifras NO acreditan fichas comerciales terminadas ni calidad del catálogo completo.
- API y web V2 activas en Render, autodeploy apagado. Documental/lotes: faltan 6 tablas en BD productiva. El ensayo sintético PostgreSQL 18 de PR #172 pasó; falta restauración protegida y aislada de respaldo real y habilitación controlada.

## Entregables y criterios de aceptación (única lista de prioridades)
- [x] **0. Inventario de origen operativo**: exclusivamente API pública Ecomm-App para Ecomm ID, SKU, barcode y demás campos capturados. Excel/CSV Ecomm-App desactivados para operación, conservados solo como histórico. Captura, búsqueda, filtros y comprobación directa de barcode reales. **Pendiente investigar** diferencias de cobertura histórica (121 ID ausentes del Excel vs API, 4 nuevos y 1 SKU cambiado) sin asumir eliminaciones.
- [ ] **1. Identidad y fuentes:** detectar único/repetido/pack/missing; priorizar lotes elegibles y dar motivo de exclusión. Investigación sobre **fuentes públicas y fabricante reales**, registro de URL, fecha, presentación, fragmento, versión y reputación; bloqueo de código contradictorio. Documento sin EAN no bloquea por sí solo si marca/presentación coinciden; tampoco autoriza declarar EAN certificado.
- [ ] **2. Expediente verificable por variante:** hechos individuales con cita comprobable, revisiones y revocación en cascada. Ninguna afirmación sin respaldo, especialmente ingredientes, alérgenos, nutrición, certificaciones o claims de salud; las ausencias se indican claramente.
- [ ] **3. Ficha comercial COMPLETA:** títulos largo/corto, descripción larga/corta, detalles, características, presentación, marca/fabricante, SEO title/description/keywords; sin rellenar con texto genérico. Guardado de borrador, diferencias por campo, versión 409, historial y recuperación.
- [ ] **4. Taxonomía/posicionamiento:** categorías y subcategorías coherentes con el catálogo y canales; sugerencias masivas revisables, sin asignaciones inventadas ni campos faltantes escondidos.
- [ ] **5. Gráficas y videos:** sugerir/adjuntar recursos auténticos por producto con URL, fuente, derechos/uso autorizado, descripción alternativa, presentación correcta. Nunca usar imágenes de otra variante o generar material falso como foto de producto real.
- [ ] **6. Lotes escalables:** selección de cohortes, límites de consumo/costos, previsualización, estados por producto, reintento idempotente, pausa, conflictos y revisión humana SOLO en excepciones; sin exigir completar 2.784 fichas una a una.
- [ ] **7. Revisión mensual:** informe general automático de fuentes vencidas, nuevos/alterados, fichas listas y bloqueadas, faltantes y prioridades; recordatorio/cola y confirmación humana con historial. Sin equiparar una revisión mensual de sistema a validación manual de cada producto.
- [ ] **8. Salida comercial controlada:** exportación por canal y/o preparación/publicación según accesos y autorizaciones, con mapeo de campos e identidad, previsualización y confirmación; NO sobrescribir stock, costos, precios ni publicar por defecto.
- [ ] **9. Pruebas reales end-to-end:** PDF/fuente oficial, una unidad y un pack, GTIN único y repetido, identidad cambiada, fuente revocada, web móvil/escritorio, restauración segura, control de concurrencia y persistencia; sin consumir proveedores/IA sin permiso.
- [ ] **10. Validación de usuario:** Guillermo/Mercedes completan desde la web el recorrido y pueden recuperar lo guardado, sin vocabulario técnico ni soporte permanente. Aceptación explícita del responsable.

## Definición estricta de «100%»
**100% del alcance funcional probado** y **100% del catálogo clasificado en un estado explicable** (ficha validada / en investigación / bloqueada por falta de evidencia / pack ambiguo / excepción documentada). **NO** declarar que 100% de los productos tienen fichas completas si faltan fuentes válidas. No reportar progreso con tarjetas o tests sintéticos como si fueran resultados comerciales reales.

## Orden inmediato (no desviar a mejoras cosméticas ni conexiones innecesarias)
1. Completar PR #172 como **identidad e investigación documental preparatoria**, revisar pruebas y rendimiento. PR #173 es solo mejora CI; no bloquea los requisitos comerciales.
2. Probar restauración de respaldo auténtico en entorno aislado y migración documental; no migrar producción hasta revisión/permiso.
3. Pilotos documentales: **Natural Seed Mix Ensaladas y Sopas 250 g** (Ecomm ID `7518949`, SKU `9995`) y **Geonat Espirulina 500 × 60 comp** (`6856453`). Contrastar el barcode **solo desde la API**; validar por separado la identidad del fabricante, fuentes y citas. Natural Seed tiene datos `STALE` a revalidar. Ambos quedan sin publicación.
4. Habilitar descubrimiento por sitemap de fabricante (PR #181 fusionada pero flag desactivado), adquisición documental acotada, extracción verificable (PR #184 en revisión), propuestas comerciales completas, y lotes reanudables con métricas de cobertura/costo; luego escalar a taxonomía, SEO y medios.
5. Validación final de la experiencia en KIKI `/v2/`, gestión mensual y salida controlada por canal.

**Seguridad:** preservar FastAPI/React/Postgres, Ecomm, ML/TN, credenciales y trabajo ya hecho; no fusionar, desplegar, activar flags, migrar ni generar consumos sin revisión y autorización separadas.

## Avance 17/11/2026 — PR #184 y #185
- PR #184 fusionada y desplegada: el lector de HTML de fabricante reconoce una presentación en unidades cuando H1 único e información visible coinciden; candidatos con cita, pendientes de revisión; sin claims de salud automáticos.
- PR #185 fusionada y desplegada: operador puede incorporar **hasta 2 HTML originales por paso** desde coincidencias únicas de un sitemap con huella verificada, validación de API, robots, TLS, captura atómica y prevención de reimportaciones. **Nuevo flag desactivado por defecto**, sin llamadas externas ni aprobación/publicación automática.
- Ambos servicios Render actualizados al commit `28008fe3`. GitHub CI #185: backend, frontend y PostgreSQL 18 aprobados.
- **No marcar checklist 1/2/6 como terminados:** no se confirmó sitemap real accesible, no se activó captura en producción, falta extracción amplia de hechos, cola reanudable, propuestas SEO/categorías/medios y validación mensual. Mantener evaluación de fuente e identidad antes de aprobar datos.


## Avance 18/11/2026 — PR #186
- PR #186 fusionada: **cola persistente de incorporación documental por fabricante**. Selección de hasta 20 variantes de Ecomm-App API, sitemap/URL revisados, un documento por paso manual, estados individuales, reintentos limitados, recuperación de interrupciones, bloqueo por cambio de identidad y control de revisiones concurrentes.
- Nueva tabla `kiki_source_intake_jobs` (migración explícita **no aplicada a la producción**), flag `KIKI_DOCUMENT_RESUMABLE_INTAKE_ENABLED=false` apagado por defecto; ningún fetch ni IA se habilita por el despliegue.
- Verificados CI backend/frontend y migración de nueva tabla en PostgreSQL 18 descartable. Sigue pendiente restauración de respaldo, confirmación de sitemap de fabricante real, migración de producción, piloto real y validación antes de habilitar la función.
- **No marcar completado el backoffice comercial completo:** todavía no hay pipeline masivo de textos SEO/atributos, taxonomía, multimedia ni auditoría mensual sin intervención.


## Avance 18/11/2026 — PR #187
- PR #187 integrada en `main` (commit `c52761ce`): nuevo **Plan comercial desde evidencias** para hasta 20 variantes API, con tareas individuales priorizadas, hechos aprobados vigentes, campos SEO/comerciales respaldados y brechas antes de generar propuestas. Acceso desde Operaciones a Ficha/Evidencias.
- El generador determinista de propuestas ya permite descripción larga/corta y meta-descripción SEO básicas con **nombre y presentación aprobados**, aun sin atributos adicionales. No inventa certificaciones, beneficios, categorías ni multimedia; continúa sin IA paga.
- CI backend/frontend y PostgreSQL 18 aprobada, sin migraciones nuevas para este cambio. **La planificación no genera ni guarda fichas; los pasos editoriales mantienen aceptación humana.**
- Próximo bloqueo: validar sitemap autorizado y piloto de incorporación; habilitar después cola reanudable y avanzar en cobertura de hechos, taxonomía, multimedia con derechos y revisión mensual.


## Avance 18/11/2026 — PR #188
- PR #188 **fusionada y desplegada** el 18/11/2026 (commit `79d6bc46`): el parser aislado incorpora candidatos de marca, fabricante, ingredientes, conservación, categoría, subcategoría y formulación cuando aparecen literalmente en la **tabla visible de atributos del producto** y hay un H1 único.
- Cada candidato mantiene cita exacta, ubicación, original archivado y los controles documentales existentes: la extracción NO equivale a aprobación; nunca se inventan ingredientes, certificaciones, beneficios ni EAN.
- Regresión nueva: ignora navegación, tablas de productos relacionados, atributos ocultos, datos contradictorios y páginas con más de un título principal.
- CI **3/3 aprobada** (backend, frontend y PG18). Sin migraciones, cambios de credenciales, proveedores, IA paga ni publicaciones. El lector está desplegado; sigue pendiente comprobar permisos de descarga y un piloto de HTML real.
- Próximos hitos del maestro: taxonomía interna validada por categorías/subcategorías, multimedia con derechos, redacción comercial de calidad sobre hechos aprobados y auditoría mensual.


## Avance 18/11/2026 — PR #189
- PR #189 **fusionada y desplegada** (commit `c174d518`): Plan comercial desde evidencias amplía diagnóstico read-only para conciliar categoría/subcategoría documental `APPROVED` y vigente con pares exactos de fichas internas previamente marcadas `READY_FOR_CHANNELS`. Evita usar `DRAFT` y `READY_FOR_REVIEW` como vocabulario para otros productos.
- Reporta por variante: estado de mapeo, referencias internas, IDs de hechos aprobados, discrepancias con categoría ya guardada, y estado individual de título SEO, meta-descripción y keywords.
- Identifica como `REVIEW_TAXONOMY` las categorías sin equivalencia y las keywords dependientes de esa jerarquía; no las marca preparadas para lote, no escribe la ficha y no publica canales.
- Mantiene intacto el contrato de borradores SEO ya usado por el guard documental de canal; su verificación sigue estricta. Sin migraciones, cambios de credenciales ni costos IA. CI final: **backend, frontend y PostgreSQL 18 aprobados (3/3)**. PR #189 **fusionada y desplegada** el 18/11/2026 en la API y la web de Render, commit `c174d518`; CI 3/3 aprobada. Ambos servicios `live`. Validación de salud API `200 OK` posterior al arranque.
- **No cerrar el punto 4**: falta persistencia versionada de mapeos KIKI↔Ecomm/ML/TN, comprobación real con Mercedes/Guillermo y aprobación humana.


## Estado real de adopción — 18/11/2026 (consultas de solo lectura)
- Base productiva: **3 fichas editoriales en DRAFT, 0 READY_FOR_CHANNELS**, **2 documentos originales de fabricante**, **4 expedientes** y **3 hechos documentales registrados**. Esto NO demuestra que los 3 hechos estén aprobados ni que las fichas estén terminadas.
- Tabla de cola reanudable `kiki_source_intake_jobs`: **todavía no existe en producción**, de modo que el código PR #186 y los flags no están habilitados como servicio operativo real. Requiere backup verificado, migración autorizada y piloto.
- Piloto UI de 18/11: selección de 5 variantes reales, **5/5 sin documentación comprobable incorporada, 0 hechos aprobados y 0 campos comerciales respaldados** para esa selección. No extrapolar a todo el catálogo. Diagnóstico de taxonomía: **0 pares internos READY_FOR_CHANNELS**.
- Hallazgo externo: página pública de Natufarma Carotenos ×30 comprimidos accesible en `www.tiendanatufarma.com.ar`; acceso del entorno de consulta a `robots.txt` y sitemap no confirmado. **No autorizar descarga automatizada ni creer que esta página acredita EAN/identidad hasta cotejo exacto con API Ecomm**.
- **Prioridad de entrega:** pilotar documentos auténticos de Natufarma/Biosa, verificar licencia/robots y correspondencia por SKU/presentación, aprobar hechos fuente-específicos; recién después masificar la incorporación en lotes. Probar ciclo completo ficha→fuente→validación→propuesta→revisión antes de taxonomía/canales. Evitar más UI decorativa.


## Avance 18/11/2026 — PR #190
- **Estado PR #190: fusionada y desplegada en API y web Render (commit `a5a44b2b`), CI backend/frontend/PG18 3/3 aprobada.** Añade una segunda ruta de obtención documental **por URL HTTPS exacta autorizada por el operador**, independiente del sitemap XML; backend autenticado/CSRF y opción en Evidencias.
- Controles: allowlist de fabricante, DNS público, HTTPS/TLS con IP fijada, robots.txt/noarchive, sin redirects, HTML original ≤4MiB, parser aislado, revisión de Ecomm ID/SKU/barcode/tipo de venta antes/después de red, versión 409, URL duplicada y cuota de 1 original automático/variante/día.
- **Permisos y hechos nunca se aprueban automáticamente**: captura original como `PENDING`, hash/fecha/URL/recibo. Ninguna publicación, cambio de stock/precio, consumo IA ni nueva migración.
- Independiente y **apagado por defecto**: `KIKI_DOCUMENT_EXPLICIT_URL_INTAKE_ENABLED=false`, no se modificaron credenciales, allowlists ni flags Render.
- Fuentes públicas candidatas para piloto: Natufarma Carotenos Ecomm ID 6754660 y Biosa Natural/Naranja Ecomm ID 6951967/9534747, registradas en `integration/EXPLICIT-MANUFACTURER-URL-PILOT.md`. Solo son coincidencias de texto/presentación públicas, **no EAN ni fabricante certificado**; robots/sitemaps no verificables desde entorno de consulta.
- **No cerrar el contrato**: aún faltan importación real, aprobación de hechos/fichas, cola reanudable en producción (migración aún no aplicada), taxonomía versionada por canal, multimedia con permisos y auditoría mensual. Cierre requiere circuito real de Mercedes/Guillermo y 100% de variantes clasificadas por estado explicable.

- Corrección UI solicitada por Mercedes: la etiqueta «Ver evidencia del canal» ahora será «Ver última captura» cuando no hay candidatos. Integrado en producción con PR #190.


## Verificación de despliegue PR #190 — 18/11/2026
- PR #190 fusionada en main: commit `a5a44b2bc3343db83067e54c8f0d815b1ca09f76`. Render API y web ambos `live`, mismo SHA.
- Logs API: startup completo, 12 llamadas a `/health` HTTP 200, sin errores en ventana consultada. Los flags de consulta a fabricantes siguen apagados por defecto; NO hubo cambios en credenciales, allowlist, productos ni publicación.
- URLs candidatas Natufarma/Biosa siguen accesibles públicamente, pero `robots.txt` de ambos dominios no pudo verificarse por herramientas externas; NO activar descarga automática antes del piloto autorizado.
- Siguiente paso obligatorio: validar origen/titularidad y condiciones técnicas, importar original de un producto auténtico, corroborar identidad/EAN/presentación contra Ecomm-App API, validar hechos y preparar/revisar ficha completa. Sin esos controles no declarar entrega contractual terminada.


## Avance 19/11/2026 — auditoría integral PR #191
- Revisión del PDF contractual septiembre 2026 y pedido mínimo: procesar masivamente, originales verificables antes que IA, no data entry permanente, EAN/SKU como pista (no certificación), categorías/SEO, multimedia con derechos, revisión general al menos mensual. La contratación es hasta 60 horas/mes de dedicación, por período inicial de 3 meses y prioridades flexibles; no se promete enriquecer manualmente todo el catálogo en una semana.
- **PR #191 fusionada y desplegada en Render API+web (commit `d26349ab`) el 18/11/2026, CI 3/3 aprobada:** auditoría de TODO el catálogo desde `ECOMM_APP_API_STAGE` (hasta 10.000 variantes) con diagnóstico separado por SKU: identidad, aptitud de barcode, originales de fabricante, procedencia, hechos aprobados con documento/versión/huella vigentes, completitud de ficha, taxonomía, SEO, imágenes, disponibilidad de video, derechos no acreditados por el informe y revisiones mensuales vencidas.
- Nuevo informe global de cobertura y CSV UTF-8 seguro contra fórmulas, autenticado y sin llamadas a terceros, IA, DDL ni escrituras a productos/canales. Integrado dentro de planificador de lotes existente, no nueva navegación.
- Se diferencia **ficha internamente marcada READY_FOR_CHANNELS** de validez de fuente/medio y publicación. No se certifica que el documento sea válido ni se firma revisión mensual al generar un informe. Videos inexistentes se registran como excepción revisable, no se inventan.
- Pruebas sintéticas de 100% de variantes sin omisiones, cambio de huella/versión que revoca conteo, CSV y fórmula segura, medios y vencimiento mensual. GitHub CI backend, frontend y PostgreSQL 18 aprobados.
- **Siguiente paso para entrega completa:** piloto integrado real de fuente fabricante autorizada→comparación API EAN/SKU/presentación→aprobación de hechos→ficha editorial completa→taxonomía/SEO→derechos multimedia→revisión y salida; activar cola reanudable tras migración y backup, y revisión general mensual evidenciada. No declarar completado el servicio sin prueba integral aceptada por Mercedes/Guillermo.


### Validación de producción PR #191
- PR #191 fusionada mediante squash en `main`, SHA `d26349ab8213bf25ed81201c14e614e8b0a2290b`.
- Render API y Web `live` en el mismo SHA. API startup completo, 6 solicitudes `GET /health` HTTP 200 en la ventana revisada, sin errores detectados.
- El endpoint de auditoría comercial de toda la captura y CSV se incorporaron, pero **no se probó la navegación autenticada ni se ejecutó una auditoría de producción tras desplegar**; validación funcional del usuario pendiente.
- Próximo bloque: piloto real con fuente fabricante permitida, hechos aprobados y ficha completa; no confundir diagnóstico con enriquecimiento completado.


## Sprint de entrega 19/11/2026 — PR #192
- Entrega acelerada: PR #192 `bd6121f90fd2e1ee73ad96571be48f5591e105d3` **lista para integrar, NO fusionada ni desplegada**, CI 3/3 aprobada (backend, frontend, PG18). Permite guardar manifiestos de 1 a 20 Ecomm IDs + URL HTTPS exacta + nota de procedencia **del mismo fabricante**, sin sitemap ni red al crear; pasos reanudables que utilizan importador #190 y controles de identidad/EAN/robots/TLS; hechos siempre pendientes de validación.
- La cola usa `kiki_source_intake_jobs` del PR #186. Inspección de producción de solo lectura: **tabla aún inexistente**; requiere respaldo restaurable, migración explícita y activación independiente de flags/allowlist con autorización para consultar fabricantes. No aplicar startup DDL ni habilitar rastreo masivo.
- Base productiva al 19/11 (solo lectura): 2 originales, 4 expedientes, 0 fichas READY_FOR_CHANNELS. En Natural Seed Ecomm `7518949` el documento original está `REVIEWED` pero sus 3 hechos (nombre, presentación, características) figuran `STALE` y no hay aprobados. La ficha original dice `Mix Ensaladas y Sopas`, 250 g, mientras la identidad API es más extensa y la presentación API no equivale literalmente. No copiar ni aprobar automáticamente: ejecutar equivalencia revisada por operador, reextraer hechos, revisar bloqueos y aprobar cada uno; recién entonces generar propuesta.
- Entrega mañana: demostrar **un ciclo real aceptado** de identidad+original→hechos aprobados→ficha/SEO→revisión, más auditoría completa y exportación de pendientes. No declarar 2.667 fichas enriquecidas ni servicios masivos habilitados sin originales auténticos y permisos. Priorizar fuentes de fabricante de verdad, no navegación adicional.


## PR #192 integrada — 19/11/2026
- **Fusionada** en `main` por squash: SHA `a28bd7c354c515c2cbcf0301bc2f49d95f3346d4`, previa comprobación CI 3/3 (backend/frontend/PG18).
- **Desplegada** en Render: `kiki-tech-api` y `kiki-tech-web` ambos estado `live` en el mismo SHA. API inició sin errores y respondió a cinco comprobaciones `/health` HTTP 200 durante la ventana revisada.
- La cola de manifiestos por URL exacta existe ahora en código, pero **no está activada ni operativa todavía en producción**: `kiki_source_intake_jobs` no existe en la base productiva, no se ejecutó migración, no se cambiaron flags ni allowlist de fabricantes y no se hizo ningún GET externo.
- **Prioridad de aceptación**: backup restaurable + migración con autorización, permitir dominios con permisos verificados, piloto real de una variante con procedencia y equivalencia de identidad revisadas, reextracción y aprobación de hechos (Natural Seed `7518949` figura con 3 hechos `STALE`, 0 aprobados), propuesta editorial/SEO y auditoría mensual. La integración de código no certifica entrega completa.


## Sprint 19/11/2026 — PR #193 reextracción de fuentes revisadas
- PR **#193 fusionada y desplegada en API + web, CI 3/3 aprobada**. Hasta 20 Ecomm IDs por operación manual. Reutiliza el motor `Research.extract` sobre exactamente un original real de procedencia `REVIEWED` y `TEXT_EXTRACTED` vinculado al ID; requiere identidad libre de discrepancias y sin bloqueos del parser.
- La operación extrae hechos únicamente a estado `PENDING`; conserva aprobaciones vigentes, no invoca proveedores, OpenAI, ni modifica ficha, stock, precio o publicación. Salta individualmente productos incompatibles indicando causa y acceso a Evidencias. Backend/Frontend/PG18 aprobados con prueba del flujo de conciliación→reextracción→candidatos pendientes y conservación de aprobaciones.
- Piloto productivo Natural Seed Ecomm `7518949`, SKU `9995`: documento fuente real revisado y 3 hechos `STALE` (nombre, 250 g, características); en el documento no consta EAN mientras que Ecomm API reporta `7798180790097`. La reconciliación de nombre/presentación exige cotejo del operador, por lo tanto NO está autorizada automáticamente. Primero registrar equivalencia revisada, luego reextraer, revisar hechos individualmente y recién entonces generar propuesta comercial/SEO. **0 fichas READY_FOR_CHANNELS** al último control.
- La activación de cola de proveedores #192 sigue pendiente de tabla `kiki_source_intake_jobs` y respaldo recuperable; PR #193 funciona sobre documentos archivados existentes y no depende de esa migración.
- No declarar el contrato completo sin piloto aceptado, validación de multimedia, cobertura de fuentes reales y revisión mensual registrada.


## Despliegue validado PR #193 — 19/11/2026
- PR #193 fusionada por squash en `main`, SHA `8bd6c8b18b9f9984bff6f2a1b7827a4859d1ea48`. Render `kiki-tech-api` y `kiki-tech-web` ambos **live** en el mismo commit.
- CI aprobada: backend, frontend y documental-schema-sandbox (PG18).
- Validación API tras arranque: **9 respuestas de `/health` HTTP 200**, sin errores detectados en la ventana de logs revisada.
- Nuevo control de reextracción de 1–20 variantes en Operaciones con originales ya revisados; no hay autoaprobación de hechos ni publicación o cambios a proveedores.
- **No se ejecutó** reextracción productiva ni se validó el circuito autenticado en navegador. Natural Seed `7518949` sigue necesitando conciliación de identidad autorizada por un operador antes de reextraer los 3 hechos `STALE`.
- La cola de URL fabricante #192 continúa sin activarse: tabla `kiki_source_intake_jobs` y backup restaurable/migración/flags pendientes. No fueron modificados en este despliegue.


## Avance 19/11/2026 — PR #194 trazabilidad mensual
- **PR #194 lista para revisión; NO fusionada ni desplegada. CI backend/frontend/PostgreSQL18 3/3 aprobada.** No hay migraciones ni activación de proveedores.
- Corrección del reloj mensual: `REVIEW_CONFIRMED` como confirmación explícita actualiza la fecha para el próximo control a 30 días; editar cualquier campo comercial mientras la ficha sigue `READY_FOR_CHANNELS` marca revisión pendiente de inmediato, sin trasladar falsamente la fecha por el simple guardado. Una transición inicial hacia READY constituye aceptación inicial; corruptelas de fecha quedan vencidas, no certificadas.
- Auditoría integral por SKU: última revisión, próximo vencimiento y estado (vigente, vencida, modificada, sin firma, no lista); resumen web y exportación CSV. Crear informe no registra ninguna revisión.
- Pruebas aisladas: vencimiento, signoff persistido, invalidación tras cambios, 409 de versión concurrente y seguridad del CSV. Documentación `integration/KIKI-MONTHLY-REVIEW-TRACEABILITY.md`.
- **Todavía falta** programar/verificar el proceso general mensual sobre nuevas capturas y fabricantes, activar cola de proveedores con backup restaurable/tabla `kiki_source_intake_jobs`, y completar piloto real de propuesta comercial/SEO/multimedia aceptada. El control mensual correcto no significa catálogo comercial terminado ni revisado en su conjunto.

