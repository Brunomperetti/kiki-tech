# Etapa 2L — Auditoría de identidad y preparación de vinculación Hileret

Base verificada: `feature/kiki-tech-2-dashboard`,
`559fbdd1536d8138ae25e6a7e30a0248467e5c3d`, árbol inicialmente limpio.

**Resultado: vinculación real pendiente, no ejecutada.** No se consultó Ecomm-App
productivo, Render, Mercado Libre o Tiendanube; no se cargaron credenciales reales,
ni se habilitó OpenAI ni se implementó otra pantalla, editor o flujo de vinculación.
El único cambio de esta etapa es este informe para revisión. Los dos expedientes
de pruebas existentes no se sustituyen por nuevos IDs sintéticos.

## 1. Contratos reutilizables y procedencia de los campos

Fuentes auditadas:

- [Cliente de inventario](../backend/app/integrations/ecomm_app/public_api.py),
  especialmente `_fetch`, `_preview_items`, `_requested_sku_diagnosis` y
  `EcommAppInventoryClient`.
- [Captura API](../backend/app/integrations/ecomm_app/catalog_stage.py),
  [consulta de la captura](../backend/app/integrations/ecomm_app/api_catalog_browser.py)
  y [rutas KIKI](../backend/app/api/routes/ecomm_app.py).
- [Editor existente](../backend/app/services/ecomm_api_product_workspace_service.py),
  [marcas sugeridas](../backend/app/services/ecomm_api_brand_hints_service.py) y
  [autenticación](../backend/app/core/security.py).

| Dato | Contrato real del código | Precaución para Hileret |
| --- | --- | --- |
| Ecomm ID único | `data.items[].variants[].id` en la respuesta de inventario; se conserva como `ecomm_id` en las filas API | No es SKU, código del producto madre, ID de depósito, ID de snapshot KIKI ni identificador del expediente. Preservar valor y cuenta de origen, sin pasar por Excel o punto flotante |
| SKU | `variant.sku`; el diagnóstico de lookup exige coincidencia literal | Se usa para localizar/contrastar, nunca para autorizar por sí solo una vinculación. No se conoce el SKU auténtico de Hileret en esta auditoría |
| Nombre | `parent.description` en el navegador/editor; preview admite `description` o `name` del padre | Nombre del padre no equivale a identidad única de variante |
| Presentación | `variant.variant_description` o `variant.description` | Exigir evidencia explícita de 200 ml/200 cc y cantidad de unidades comerciales; no inferirla del nombre o sufijo del SKU |
| EAN | La captura retiene `variant.barcode` y `variant.gtin` | Conservar ambos campos originales y bloquear si discrepan. El EAN compartido por las filas 27/28 no distingue unidad y pack |
| Marca | El navegador/captura no conserva una marca nativa del proveedor | No confundir marca editada en KIKI o sugerida por snapshots ML/TN con una marca recibida de Ecomm-App. Revisar respuesta original o referencia autorizada del maestro si existe ese dato |
| Unidad/pack | `variant.is_combo` y `parent.is_combo`, por separado, booleanos o desconocidos | `False` no demuestra por sí solo una unidad; `True` no demuestra seis componentes; `None` no equivale a `False`. La presentación/cantidad debe ser explícita |
| Stock | `variant.total_stock`, depósitos y fecha de captura | Stock, cantidades de depósito y disponibilidad no son cantidad de unidades de un pack ni contenido neto |

### Lecturas existentes y efectos que no deben confundirse

| Operación | Lee proveedor | Escribe KIKI | Uso en la consulta futura |
| --- | --- | --- | --- |
| Proveedor `GET /api/v3/public/inventario/productos` | Sí, inventario | No, si se usa cliente independiente sin engine | Opción propuesta, acotada por barcode y presupuesto de solicitudes |
| Proveedor `POST /api/v3/public/inventario/productos/consulta`, `{"skus":[...]}` | Sí, consulta documentada de stock; no mutación de inventario | No desde el cliente puro | Alternativa sólo con SKU auténticos ya conocidos/autorizados; cliente existente limita a 1–3 SKU |
| KIKI `GET /api/ecomm-app/stage/catalog?q=...&page=1&limit=25` | No; consulta una captura API completa en PostgreSQL | El lector del catálogo no escribe catálogo, pero `require_session` actualiza la sesión | No usar el backend productivo para el requisito estricto de cero escrituras. Una búsqueda es descubrimiento, no confirmación de identidad |
| KIKI `GET /api/ecomm-app/workspace/{ecomm_id}` | No; fuente API capturada y overlay editorial | `get()` no guarda ficha, pero la autenticación sí escribe sesión | Reutilizar como contrato del editor en pruebas, no como consulta productiva sin efectos |
| KIKI `POST /api/ecomm-app/lookup` o `/preview` | Sí | Autenticación actualiza sesión; no son escrituras de catálogo por sí mismas | Evitarlos en producción para este piloto; además devuelven previews incompletos para una auditoría de identidad |
| `/stage/next`, `/stage/manual/start`, `/stage/auto/start` y `/stage/auto/step` | Sí | Sí: captura, avance/trabajo y eventual promoción de snapshot | Excluidos. Una lectura del proveedor no convierte estas rutas en operaciones sin escrituras |

El scope del proveedor es `inventario:leer`, host fijo
`https://admin.ecomm-app.com`; el cliente actual usa Bearer sólo desde servidor,
timeout de 12 s, máximo 2 MiB por respuesta y mensajes de error saneados. Sus
operaciones no incluyen publicaciones, facturación, cambios de productos o stock.
Estas son propiedades del código/contrato documentado, no una verificación de una
cuenta o respuesta productiva realizada en esta etapa.

## 2. Hallazgos que bloquean el uso directo para vincular

1. **No existe una operación de vinculación real.**
   [La referencia Hileret](../backend/integration_sandbox/hileret_reference.py)
   devuelve `authentic_ecomm_id: null`. El [editor del harness](../backend/integration_sandbox/workspace.py)
   admite sus aliases explícitos sólo como borradores. La política local no admite
   IDs reales arbitrarios. No alcanza con cambiar una constante o ampliar un regex.
2. **Los GET autenticados de KIKI no son cero escrituras de PostgreSQL.**
   `require_session` actualiza `AdminSession.last_seen_at` y hace `commit`; elimina
   sesiones vencidas. No se utilizará una ruta del backend productivo, ni siquiera
   de catálogo, para prometer una consulta sin escrituras.
3. **El transporte actual no bloquea explícitamente redirecciones.**
   `_fetch` usa `urllib.request.urlopen` estándar. Un control negativo puramente
   en memoria confirmó que `HTTPRedirectHandler.redirect_request` puede conservar
   `Authorization` al construir una redirección a otro origen. No se enviaron
   solicitudes ni tokens reales. Es un riesgo del camino de código, no evidencia
   de que el proveedor haya redirigido o de una fuga ocurrida. Antes de cualquier
   lectura autenticada hacen falta rechazo de redirecciones y destino HTTPS exacto.
4. **ID faltante puede atravesar un guardado de referencia como texto `"None"`.**
   `_source_pages` exige captura completa y ausencia de IDs duplicados, pero no
   rechaza todos los avisos de calidad. `_source` compara `str(variant.id)` con el
   parámetro. Un contraejemplo sin DB ni nuevas identidades mostró que un ID nulo,
   con SKU presente, puede coincidir con `"None"`. El futuro validador debe rechazar
   nulos, vacíos, booleanos y representaciones placeholder antes de llamar al editor.
   Los aliases actuales del harness siguen acotados; no se modificó la integración.
5. **EAN y preview no tienen la misma prioridad de campos.**
   Preview elige `barcode or gtin`; navegador/editor eligen `gtin or barcode`. El
   control negativo confirmó la divergencia cuando los dos valores difieren. No
   tomar un valor combinado como resolución de esa contradicción.
6. **El preview puede omitir al candidato o sus atributos.**
   Muestra hasta cinco padres y cinco variantes por padre. El diagnóstico SKU sí
   recorre hermanos, pero sus coincidencias compactas no incluyen todos los campos
   de marca/EAN. La futura revisión debe conservar el registro original completo
   del candidato y los hermanos relevantes, no sólo `samples`.
7. **Captura completa no significa vigente ni identidad comprobada.**
   La captura descarta campos fuera de su proyección, no garantiza un instante
   consistente de todo el inventario y expone avisos de calidad. `is_combo`, marca,
   presentación, cambios del SKU y frescura requieren revisión adicional. El editor
   bloquea cambio de SKU y concurrencia, pero eso no demuestra que todos los demás
   atributos identitarios sigan iguales.
8. **El adaptador de investigación sigue siendo de pruebas.**
   La rama general de `Research.reference` tiene fallbacks de marca/fabricante y
   referencias de fixture. No puede usarse para identidad real simplemente
   permitiendo otro ID. La referencia real futura debe proceder exclusivamente de
   los datos autorizados, con desconocidos explícitos y sin fallbacks sintéticos.

No se corrigieron estas rutas productivas ni se activó un nuevo transporte en esta
auditoría. Se documentan las condiciones previas a una implementación y lectura
expresamente autorizadas. Las recomendaciones históricas de configurar Render en
otros documentos no autorizan hacerlo en 2L.

## 3. Consulta read-only exacta propuesta, todavía no autorizada

### Alternativa sin acceso de Codex al proveedor

El titular puede suministrar una exportación autorizada de la respuesta API o una
referencia verificable del maestro que contenga ID de variante, contexto de cuenta,
SKU, presentación, cantidad comercial, banderas de combo, EAN/campos originales y
marca si está disponible. Se revisaría localmente sin incorporar el Excel como
catálogo. No se aceptaría una lista de SKU/EAN sin identificador y procedencia.

### Lectura acotada por Codex, sólo después de autorización explícita

Alcance propuesto para aprobar: **hasta dos GET** al recurso de inventario, filtro
por `barcode=7794940000796`, posibles variantes hermanas devueltas por Ecomm-App,
sin consultar otras APIs, depósitos, servicios KIKI/Render ni bases productivas.

Contrato de la primera solicitud (no ejecutada):

```http
GET https://admin.ecomm-app.com/api/v3/public/inventario/productos?barcode=7794940000796&page=1&limit=50&sort=sku_asc
Authorization: Bearer <credencial de sólo lectura gestionada fuera del chat>
Accept: application/json
```

Segunda solicitud: exactamente el mismo host, path y filtro con `page=2`, **sólo
si** la primera respuesta reconoce paginación y declara esa segunda página. Si
existen más de dos páginas, datos contradictorios, forma desconocida o error:
detenerse, registrar la insuficiencia y solicitar un alcance nuevo. Cero reintentos
automáticos. Cero coincidencias no demuestra ausencia del producto: no ampliar
automáticamente a búsqueda por nombre, otros EAN ni catálogo sin filtrar.

Requisitos previos y procedimiento:

1. Obtener autorización del titular para cuenta, filtro, campos necesarios y
   presupuesto anterior. No hay SKU ni Ecomm ID Hileret inventados en el pedido.
2. Disponer de credencial con **sólo `inventario:leer`** mediante un mecanismo
   seguro y separado. No pegar tokens en chat, comandos, frontend, capturas o Git;
   no copiar `.env` productivos ni modificar Render. No se ha configurado ni usado
   esa credencial en esta etapa. Su disponibilidad y alcance real están pendientes.
3. Mantener FastAPI/PostgreSQL/lector documental offline. El lector de inventario
   debe ser un proceso independiente sin engine, `get_settings()`, sesión KIKI,
   OAuth ML/TN, planificador ni conexión a PostgreSQL. El módulo puro `public_api`
   y su punto de inyección `requester` permiten reutilizar el contrato; no se debe
   importar `app.main`, la sesión DB ni ejecutar el cliente HTTP por defecto sin
   resolver el hallazgo de redirecciones.
4. Preparar y validar antes de la consulta un transporte GET cerrado al host/path,
   TLS estricto, **cero redirecciones**, sin proxies o destinos de fallback no
   revisados, sin DNS privado/rebinding, timeout/bytes/solicitudes acotados. El
   transporte aún no está implementado ni habilitado. La autorización no debe
   abrir Internet al backend offline ni a su recolector. Si el entorno no puede
   aislar transporte/credencial, detenerse y usar la exportación del titular.
5. Ejecutar únicamente el GET aprobado y la segunda página condicional. El POST
   de consulta por SKU es contractualmente de lectura, pero **no está incluido**
   en este alcance: faltan SKU auténticos y autorización específica para usarlo.
6. Conservar respuesta original autorizada en área local restringida con SHA-256,
   timestamp de lectura, cuenta/origen autorizados, filtro, paginación y estado;
   nunca cabeceras Bearer/cookies. No volcar inventario completo a logs. Extraer
   para revisión todos los campos relevantes del candidato y hermanos, sin
   truncarlos al preview ni inventar ausencias.
7. No escribir snapshots de KIKI productivo ni llamar a rutas de captura. Una
   respuesta filtrada no es un catálogo completo: no promoverla como
   `ECOMM_APP_API_STAGE` ni sustituir el maestro con una captura parcial.
8. Finalizar la conexión y revisar la identidad offline. Una consulta autorizada
   no autoriza por sí misma la vinculación, traslado de fichas o publicación.

La configuración actual del harness bloquea esa conexión y no se cambió. Se
espera autorización antes de preparar acceso real o enviar la primera solicitud.

## 4. Procedimiento de vinculación: diseño, no ejecución

### Puerta de identidad

El operador debe poder comparar dentro del panel lateral existente:

| Comprobación | Condición para proponer unidad 200 ml |
| --- | --- |
| Origen | Respuesta o referencia autorizada, cuenta correcta, hash y fecha, sin procedencia de fixtures/Excel |
| Variante | `variants[].id` auténtico, no nulo/placeholder/booleano, sin ambigüedad o duplicados en la evidencia recibida; conservar su representación exacta |
| Jerarquía | Padre y variante identificados por separado; no confundir código padre/depósito con ID único |
| SKU | Valor exacto de la variante y relación con el padre; sólo contraste, no identidad suficiente |
| EAN | Revisar `barcode` y `gtin` originales y su relación con el documento. Contradicción, falta o multiplicidad no se resuelve copiando el EAN del PDF al maestro |
| Presentación/cantidad | Evidencia explícita de unidad individual y 200 ml/200 cc; distinguir pack x6 y logística x9. `is_combo` desconocido o composición ausente bloquea la decisión hasta aclarar |
| Marca | Contrastar Hileret con el dato del maestro si existe; si no existe, reconocer esa ausencia y obtener una referencia autorizada suficiente. El nombre, el PDF o un hint de canal no sustituyen por sí solos la identidad del maestro |
| Coherencia | Múltiples atributos independientes compatibles, todas las discrepancias resueltas y confirmación humana del candidato correcto. Un único match de EAN/SKU/nombre jamás alcanza |

Si sólo se conoce EAN/nombre o faltan cantidad/presentación/origen, seguir como
`PENDIENTE`, con Ecomm ID auténtico nulo. No asignar otro número de pruebas. No
inferir componentes por prefijo, sufijo `_m`, stock de depósito ni caja del fabricante.

### Preservación y concurrencia de una decisión futura

1. Congelar una referencia de consulta candidata con su hash, cuenta y timestamp;
   mostrar comparación contra la unidad y el pack del expediente en el dashboard
   actual. No crear dashboard o navegación paralela.
2. Conservar originales y versiones de `Document`, citas, decisiones de prueba,
   historial de `Dossier`, editor de 18 campos y propuestas. No renombrar la PK
   sintética, editar JSON de asociación o reemplazar IDs mediante SQL.
3. Registrar una relación/decisión de identidad **append-only** que apunte al
   expediente previo y a la referencia auténtica, con actor, motivo y versiones.
   Reutilizar el mecanismo de historial existente; el contrato de esa operación
   aún debe implementarse y revisarse, no existe hoy un endpoint `/bind`.
4. Antes de confirmar, revalidar identidad, frescura y exclusividad de destino
   dentro de una transacción, con versiones esperadas de expediente/ficha y
   bloqueo/chequeo de la referencia. Dos operadores sobre la misma decisión:
   uno confirma, el otro recibe 409, sin vinculación ni ficha parcialmente movidas.
5. Los hechos vinculados a la identidad nueva deben reextraerse/contrastarse con
   las mismas citas/original, pero arrancar **pendientes de revisión**, con IDs y
   huella de identidad apropiados. Nunca copiar `APPROVED`, `verified`, firmas de
   verificación, decisiones de propuesta aceptadas ni aprobación editorial a la
   identidad real. Mantener una referencia al hecho previo como trazabilidad,
   no como autorización.
6. Etiquetar el origen de las revisiones de forma inequívoca. Los motivos/actores
   actuales dicen que son automatizadas de prueba; `APPROVED` aislado no prueba
   aprobación humana. Un contexto desconocido o de pruebas no puede promoverse
   a cliente real. El protocolo futuro debe validar ese origen explícitamente.
7. Revisar fuente y cada hecho con operador humano; generar y comparar de nuevo
   mediante el generador existente, aceptando sólo hechos autorizados para la
   identidad actual. Guardar con `expected_version` y conservar los campos no
   seleccionados. Esto sigue siendo edición interna de pruebas, no publicación.

Las comprobaciones actuales ya invalidan hechos cuando cambia su huella de
identidad/documento, rechazan documentos de otro expediente y conservan historial.
**No prueban una migración real de identidad**: esa operación no está desarrollada
ni autorizada. La rama general de investigación con fallbacks sintéticos tampoco
debe habilitarse para referencias reales como atajo.

## 5. Auditoría documental y propuesta escalable

Original preservado: **6.232.081 bytes**, 4 páginas, SHA-256
`bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291`.
Se comprobó nuevamente su hash sin reescribirlo. Véase
[el recorrido auténtico 2K](HILERET-AUTHENTIC.md) para citas y capturas.

| Capa | Estado auditado | Límite o salvedad |
| --- | --- | --- |
| Selección del perfil | Tamaño exacto **y** SHA-256 de todos los bytes | No por nombre, dominio, marca o parecido. Un byte modificado no obtiene ampliación. No certifica origen/vigencia ni aprueba hechos |
| Otros archivos | 512 KiB de bytes decodificados | Se mantiene; nuevos PDF grandes no quedan autorizados por la excepción |
| Sobre HTTP/base64 | Modelo admite 8.309.444 caracteres; gateway 8.325.828 bytes sólo en importaciones/originales de los dos IDs Hileret | Sí se amplió un sobre de transporte acotado. No afirmar que todas las capas siguen en 512 KiB: un payload rechazado puede asignar memoria antes del chequeo de hash |
| Admisión API | Sesión, CSRF, autorización local, versión y control del original/ID para cargas grandes | Otros IDs no ganan el permiso; ampliar el límite DTO por sí solo no habilita un archivo arbitrario |
| Parser | Firma/MIME, EOF, no cifrado; rechazo de JS/acciones/URI/adjuntos; sin red ni subprocesos | Cotas de objetos, profundidad, arrays, páginas, texto y resultado se mantienen. Se inspecciona la estructura completa |
| Presupuestos del hash especial | 5 MiB/stream, 16 MiB acumulados, 40.000 visitas, 128 entradas de página, 2.000.000 unidades de trabajo | Mayores que el perfil genérico pero finitos y exclusivos de este hash; no se desactivan protecciones |
| Proceso aislado | 192 MiB; CPU 4/5 s; alarma 8 s; resultado hasta 524.288 bytes; contenedor sin red y raíz readonly | No hay OCR, OpenAI o consultas web |
| Extracción | Página 2: fila Stevia y rótulo del envase; cinco ubicaciones nativas | No mezcla Zucra, pesos de pallet, eslóganes, ingredientes o certificaciones. No es un extractor general de tablas |
| Aprobación | Separada de importación/extracción | El hash de una URL no se presenta como hash del PDF. La declaración de fuente oficial no reemplaza revisión |

**Conclusión:** no se amplió la admisión general de archivos decodificados. La
excepción es acotada y válida para este piloto; no constituye una política escalable
de procesamiento de PDFs ni un permiso de producción.

Propuesta futura, **sin implementar en 2L**:

- Recepción autenticada por streaming con límite de bytes antes de leer todo el
  cuerpo, cálculo incremental de hash y cuarentena local/restringida. Evitar
  multiplicar grandes buffers base64 en gateway, API y worker.
- Original inmutable identificado por hash, separado de versiones de extracción,
  procedencia y decisiones. El almacenamiento JSON/base64 actual repite originales
  en historial y carga cuerpos completos; conservarlo ahora, revisar ese coste
  antes de procesamiento masivo. Reutilizar editor, dossier e historial existentes,
  sin otra aplicación o sistema comercial paralelo.
- Perfiles versionados por formato y presupuesto, con máximos duros de bytes,
  páginas, expansión, objetos, tokens, píxeles si se procesa imagen y tiempo/memoria.
  Los tamaños nuevos requieren mediciones/pruebas, no un límite global ilimitado.
- Workers sin Internet/credenciales, concurrencia y cuotas por usuario/trabajo;
  preadmisión antes de la lectura grande, resultado acotado, cancelación y sin
  reintentos infinitos. OCR, si se autoriza, local y con presupuesto propio.
- Selección verificable de página/región/producto, citas con coordenadas y control
  de ambigüedad entre tablas. Un PDF complejo no debe convertirse en texto plano
  sin trazabilidad ni un recorte reemplazar el original.
- Cambio de bytes, extractor, región o identidad: nueva versión/huella y revisión
  explícita, sin heredar aprobaciones. El SHA reconoce contenido; el origen oficial,
  la vigencia y la correspondencia con el producto requieren controles aparte.

## 6. Comparación comercial para el operador

| Capa | Información disponible | Estado y siguiente decisión |
| --- | --- | --- |
| Maestro Ecomm-App real | Ningún ID/registro Hileret consultado en esta etapa | Pendiente de lectura/referencia autorizada. No hay vinculación |
| Excel auxiliar informado | Fila 28: unidad 200 cc; fila 27: pack x6 de 200 ml; EAN declarado compartido | Dos registros comerciales; no sustituye maestro ni prueba identidad real. No se inventan SKU/celdas no suministrados |
| Fabricante, original adjunto | Hileret Stevia 200 ml, EAN `7794940000796`; caja x9 y DUN `97794940000799`, citas de página 2 | Respaldo documental local, no una consulta web ni información completa de composición |
| Sistema de pruebas | Siete hechos con revisiones explícitas simuladas por operador automatizado | Preservar su origen de prueba; cero transferencia automática de aprobación a identidad real |
| Ficha propuesta/guardada en pruebas | Marca Hileret; presentación 200 ml; títulos/SEO `Hileret Stevia · 200 ml`; descripción `Hileret Stevia · 200 ml.` y `Contenido neto: 200 ml.`; atributo de volumen | Borrador interno recuperado de PostgreSQL en 2K. No publicado, no listo para canales, no aprobación humana efectiva |
| Pack x6 | No respaldado por folleto de unidad/caja x9 | Mantener separado; sus hechos no resultan aprobables con ese documento |
| Pendientes | Ecomm ID, fabricante legal, categoría/subcategoría, palabras clave, imágenes/videos y fuente primaria en la ficha comercial | Información no completada automáticamente; revisión del operador |
| Pendientes técnicos/comerciales | Ingredientes, alérgenos, nutrición, certificaciones, beneficios de salud y «sin gluten» | Documentación específica y vigente; no inferir desde el folleto ni sus imágenes |
| Aprobación humana | Falta confirmación efectiva del cliente de fuente, identidad, hechos y ficha | Las marcas `verified` de la ejecución automatizada no la sustituyen |

La etapa 2L cierra la preparación/auditoría, **no el cierre productivo del piloto**.
El original, las evidencias y resultados de 2K permanecen sin cambios. No se
rehicieron capturas ni se alteraron los JSON de decisiones para simular una nueva
revisión. La próxima consulta debe ser aprobada expresamente antes de ejecutarse.

## 7. Validación realizada en 2L

Se ejecutan únicamente pruebas existentes en el entorno descartable sin red,
con sus fixtures de prueba ya definidos. No se crean nuevas identidades para
sustituir la real ni se cargan datos del catálogo productivo. Los contraejemplos
de auditoría son objetos negativos en memoria sin filas persistidas, no candidatos
Hileret ficticios. Antes de probar se contrastaron por hash siete archivos clave
de la imagen contra las fuentes del HEAD (cliente, navegador, captura, editor,
parser, perfil y pruebas auténticas), además de los bytes del PDF original.

| Pruebas existentes ejecutadas | Resultado |
| --- | --- |
| Pytest: API pública, navegador/captura API, editor, combos/GTIN y marcas sugeridas | 46 aprobadas; requester/HTTP simulados, sin llamadas al proveedor |
| Aislamiento/configuración/servicios (`integration_sandbox.verify`) | 19 aprobadas |
| Editor persistente y concurrencia PostgreSQL (`editor_checks`) | 7 aprobadas |
| Identidad, citas, invalidación, revisión e historial (`research_checks`) | 13 aprobadas |
| Seguridad de documentos, originales/versiones (`document_checks`) | 15 aprobadas |
| Unidad/pack/logística e identidad auxiliar (`hileret_checks`) | 8 aprobadas |
| Original auténtico, SHA, propuesta limitada, recuperación y concurrencia (`hileret_authentic_checks`) | 6 aprobadas |
| Gateway HTTPS local, rutas, tamaños, autenticación y bloqueo de destinos (`integration/test_gateway.py`) | 8 aprobadas |
| **Total de suites** | **122 aprobadas** |

Se registró un aviso existente de pytest por importación de `anyio`; no hubo
fallas. No se modificaron tests ni código para obtener estos resultados.

Controles negativos adicionales de auditoría, sin conexiones ni datos persistidos:

- Construcción de redirección estándar entre orígenes: retiene `Authorization`.
  Usó únicamente un texto explícitamente no secreto, nunca un Bearer real.
- Mock de snapshot con ID nulo: captura completa con aviso de calidad y aceptación
  de `"None"` por `_source`, confirmados. No es una variante del cliente.
- Mismo mock con `barcode` y `gtin` diferentes: preview/navegador priorizan valores
  distintos, confirmado. Los valores eran controles no válidos como EAN.

Que las suites existentes pasen no elimina estos hallazgos: no cubren ni autorizan
una vinculación real. Los tests no probaron credenciales, cuenta, filtros o respuesta
de Ecomm-App en vivo, ni un endpoint de vinculación inexistente. Tampoco certifican
el diseño escalable de PDFs, que permanece como propuesta.

Los cuatro contenedores mantuvieron `network_mode:none`, sin puertos públicos ni
privilegios y con raíz de sólo lectura; PostgreSQL fue descartable y validado antes
del engine/DDL. El gateway de pruebas sólo usó HTTPS loopback. Al terminar se
retiraron contenedores y volúmenes; no quedó una base ni gateway encendidos.

Se verificaron enlaces locales del informe, SHA del original y `git diff --check`.
Los artefactos, decisiones, capturas y fuentes de 2K/MAMA permanecen sin cambios.
**Único archivo modificado/agregado en 2L:**
`integration/HILERET-IDENTITY-AUDIT-2L.md`. El commit local sólo documenta esta
auditoría; no implementa ni habilita vinculación o acceso productivo.
