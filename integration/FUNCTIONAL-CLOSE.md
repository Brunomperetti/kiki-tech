# Cierre funcional para la presentación a Guillermo

Fecha de trabajo: 12/11/2026. Presentación prevista: 13/11/2026. Rama `feature/kiki-tech-2-dashboard`, base comprobada `7b903eeeaf69a54b409855b5868dcaaf68c955d3`, inicialmente limpia. Desarrollo local, sin push ni despliegue. La aplicación productiva no fue consultada ni modificada.

## Resultado y alcance

Se amplió el dashboard existente, sin otro catálogo, editor o motor de jobs. No se agregaron tablas ni migraciones: se reutilizan CatalogSnapshot, el editor/versionado, los drafts, las evidencias y la cola persistente existentes; las proyecciones nuevas son de lectura. Las cinco vistas comerciales funcionan tanto en el build conectado al backend aislado como en el demo visual, con alcances explícitamente diferentes:

| Vista | Qué cuenta y muestra | Qué nunca supone |
|---|---|---|
| Catálogo Ecomm-App | Variantes exactas de la captura API maestra, por Ecomm ID | Que el Excel o un SKU constituyan la identidad |
| Mercado Libre | Filas de captura y publicaciones distintas; estado, fecha y vínculo validado si existe | Que una coincidencia SKU sea una publicación confirmada |
| Tiendanube | Todos los registros CSV y sus identificadores/fecha, incluso sin vínculo | Que sigan activos actualmente por aparecer en un CSV |
| Sin confirmación ML | Variantes del maestro sin confirmación suficiente en esa captura | Que esté probada su ausencia en el canal |
| Sin confirmación TN | Variantes del maestro sin confirmación actual suficiente | Que no estén publicadas |

Las filas externas sin vinculación no crean productos en Ecomm-App ni identificadores ficticios. El selector de vinculación y la búsqueda operan sobre registros del canal; sólo una vinculación revisada permite abrir una variante. Las capturas corruptas producen un error y una captura maestra incompleta impide derivar vínculos. Nunca se reemplazan por fixtures automáticamente.

La tabla mantiene búsqueda, paginación, cinco pestañas, selección y contexto en URL. El encabezado es compacto y las cinco vistas comerciales aparecen primero. Los indicadores secundarios están plegados para dar prioridad a la tabla. Los filtros de la cola pueden combinar hasta dos condiciones explícitas (`filter=ean_repeated+images_missing`), más búsqueda; la misma selección se reutiliza para lotes.

## Calidad y ficha

Se calculan faltantes de EAN, repeticiones EAN/SKU, posibles duplicados, familias SKU candidatas, conflicto barcode/GTIN, título, descripción corta/larga, categoría/subcategoría, atributos, imágenes, SEO y completitud. «Sin video» exige revisar aplicabilidad; no bloquea todas las fichas. Se conservan además los filtros existentes de investigación, evidencia aprobada/revocada, revisión vencida/próxima, documentos modificados y conflictos de canales. La métrica de propuestas pendientes corresponde a la última propuesta **documental**, pendiente de revisión o revisada aún sin aplicar; la bandeja histórica de OpenAI conserva su servicio original y no se cuenta como integrada completa.

Las reglas numéricas de familias reutilizan `compare_family_skus`; códigos repetidos sólo sugieren revisión. La fuente EAN es la captura original, no el GTIN sugerido en la ficha. Los filtros comerciales consultan los 18 campos del editor mediante proyecciones SQL de presencia, sin cargar los documentos ni sus originales por fila. La completitud interna no verifica por sí sola autenticidad o publicación.

El demo estático ahora usa el **mismo componente `CommercialBackofficeFields`** del editor de 18 campos, dentro de la ficha lateral. Conserva sus controles resumidos sincronizados con el mismo borrador e historial en memoria; no hay un segundo almacén ni persistencia PostgreSQL ficticia. En el build conectado se mantiene el guardado real en PostgreSQL descartable, con expected_version, CSRF y conflictos.

Historial general y exportación JSON reutilizan `GET /workspace/saved` y `/workspace/master-export`. La confirmación mensual utiliza `POST /workspace/{ecomm_id}/confirm-review`: exige ficha preparada, sin cambios sin guardar, confirmación explícita, identidad vigente y versión exacta. No modifica el contenido ni publica. Configuración mantiene preferencias de sesión; no edita integraciones, secretos o presupuesto real.

## Investigación → propuesta → revisión → guardado

La acción «Investigar y completar ficha con IA» abre el recorrido integrado, conservando el identificador exacto y las pestañas. En este entorno se identifica **búsqueda simulada y generador determinista**, sin prometer investigación real.

El escenario `--presentation` reutiliza la captura sintética y sus canales, agrega dos registros externos deliberadamente sin vínculo y un documento de chía explícitamente inventado para demostración. Su preparación no aprueba hechos. El recorrido automatizado de aceptación revisa procedencia y hechos con una justificación que dice `RECORRIDO AUTOMATIZADO DE PRUEBA`, consulta el contrato de hechos aprobados y el estado del servicio IA histórico, genera una propuesta determinista, acepta/rechaza campos, muestra citas y guarda en el editor existente. Se recarga desde PostgreSQL y se consulta Historial. Esas decisiones de test no son aprobaciones humanas auténticas del cliente.

Se demuestra también un lote de tareas de revisión: selección, previsualización, confirmación y trabajo persistente del ejecutor backend. Se preservan análisis incremental, idempotencia, leases, recuperación tras reinicio, exclusión mutua, cancelación y límites existentes. La generación documental por lote permanece determinista y nunca aprueba cientos de campos ni publica.

El PDF Hileret auténtico ya incluido en el repositorio se incorpora en el expediente auxiliar de pruebas, con hash `bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291`. Se muestran citas de EAN individual `7794940000796` y DUN logístico `97794940000799` sin equipararlos. Unidad 200 ml, pack comercial x6 y caja logística x9 permanecen distintos. El escenario de presentación mantiene cero aprobaciones automáticas y **Ecomm ID auténtico pendiente**. En la ejecución larga del piloto hubo un rechazo 409 del lector (disponibilidad o límites de recursos; causa exacta no determinada); la comprobación independiente aprobó escritorio y celular con las mismas protecciones. La presentación usa el documento ya incorporado y verificado; no se ampliaron presupuestos de lectura. MAMA permanece como evidencia insuficiente. Ningún expediente auxiliar se convierte en variante auténtica por compartir EAN.

## Estado de OpenAI y de fabricantes

- Se conserva `EcommAiEditor` sin modificar cliente, configuración ni reservas reales. Existen 10 intentos diarios UTC, reserva única por slot, auditoría de fallos, caché por huella y 450 tokens máximos de salida. El piloto Tiendanube tiene su límite separado de 1 intento/día y 300 tokens. El contrato histórico devuelve título, descripción y preguntas, no los 18 campos documentados.
- La pestaña IA permite consultar el estado/cuota del servicio histórico sin generar ni consumir. La propuesta documental reutiliza drafts y guardado existentes, con citas por campo y CAS, usando `deterministic-reviewed-evidence-v1`.
- `generation_context` prepara el contrato de hechos aprobados, versiones, citas, huellas e identidad para futura adaptación al cliente existente. Conserva límites de entrada y exige presupuesto atómico/revisión de modelo antes de habilitar consumo. Los valores `0.00` del contrato de pruebas son un bloqueo, no evidencia del presupuesto real del cliente.
- En el código revisado se encontraron cuotas de intentos/tokens; no se acreditó un techo monetario global por ese código. La configuración efectiva de facturación/productiva no fue consultada. No se modifica ni se afirma que no exista un presupuesto externo configurado.
- El puente final entre generación OpenAI y salida documental completa sigue pendiente de validación offline con el cliente existente, controles de respaldo/costo y autorización posterior. No se presenta como IA real ya operativa en este build.
- La investigación automática de fabricantes **no se ejecuta**. El conector HTTPS existente contempla allowlist, TLS, DNS/destino público fijado, antirrebinding, redirecciones sólo si están expresamente autorizadas en el plan, límites y verificación de contenido. `REAL_NETWORK_ENABLED` permanece falso, sin dominios habilitados. El recolector activo usa simuladores; falta conectar descubrimiento real autorizado y transferencia al lector existente. No se creó otro lector ni se pidió exportar productos manualmente.
- La incorporación local de documentación y su trazabilidad sí funcionan. El perfil especial Hileret sigue acotado al hash exacto; no se ampliaron límites generales para descargar cualquier PDF. Ingredientes, alérgenos, nutrición y certificaciones sólo se completan con documentación específica y aprobación.

## Paridad y camino mínimo

Consultar [matriz de rutas, acciones y endpoints](FUNCTIONAL-PARITY.md). Hay integración funcional del núcleo API, pero **no se declara paridad total** con cada herramienta histórica. Se conservaron los módulos y rutas originales. Importaciones, reportes históricos por ejecución, resolución especializada de duplicados/conciliación, revisión masiva de metadata/imágenes y bandeja histórica OpenAI requieren terminar su traslado controlado. Los mocks visuales no sustituyen esas capacidades. No habilitar sus operaciones productivas en el demo para aparentar acceso.

Orden posterior a esta revisión: (1) autorizar alojamiento independiente/origen HTTPS y acceso temporal para probar en Chrome; (2) autorizar uso de capturas auténticas por la integración existente y validar identidades, sin importarlas como fixtures; (3) terminar el puente documental al cliente IA y presupuestos existentes con transportes simulados, luego autorizar consumo limitado; (4) autorizar fuentes concretas y conectar el HTTPS existente al recolector; (5) trasladar las acciones históricas pendientes con identidad/permiso explícitos. Ninguno de estos accesos externos se realizó.

## Prueba online

La URL estática anterior <https://kiki-tech-2-demo.onrender.com> no se actualizó. Sigue siendo un demo visual de la versión publicada. No hay URL nueva del backend aislado disponible desde Windows. La interfaz de Codex no ofrece Desktop según confirmó el usuario.

[Plan online mínimo preparado](ONLINE-PRESENTATION-PLAN.md): mismo backend y PostgreSQL descartable en un solo host independiente, entrada HTTPS autenticada, sin instalación en Windows. Requiere autorizar host, dominio, eventual costo y despliegue de demo. El arnés actual está fijado a loopback; su exposición exige una adaptación revisada de origen/CSRF/TLS, sin debilitar defaults. No se crearon servicios ni se desplegó.

Para reproducir en un host Linux de pruebas ya disponible:

```bash
python3 integration/run.py build
python3 integration/run.py up --presentation
# En el propio host: https://127.0.0.1:8443
# Retirar datos/servicios al terminar:
python3 integration/run.py down
```

Credenciales únicamente sintéticas y certificado local: ver [guía del escenario](PRESENTACION-GUILLERMO.md). Este procedimiento local no crea un enlace remoto ni exige instalar Docker en Windows para consumir la futura versión online.

## Validación y capturas

Resultados finales: ver `FUNCTIONAL-VALIDATION.md`. Capturas nuevas bajo `frontend/artifacts/functional-*`. Las capturas históricas se conservan, sin sustituirlas por resultados de esta entrega. Los tests bloquean cualquier intento de conexión externa, rechazan la falsa confirmación TN, preservan identidades, guardado, revisión por campo, concurrencia y recuperación de jobs.

No se ejecutaron llamadas productivas, OpenAI, publicaciones ni búsquedas reales. Los contenedores de pruebas no tienen red ni puertos y se retiran con sus datos al finalizar. El código de integración Ecomm-App/ML/TN, Render, main y credenciales productivas permanecen intactos.
