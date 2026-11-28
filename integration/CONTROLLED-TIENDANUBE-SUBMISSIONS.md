# Envíos comerciales controlados a Tiendanube

Implementación preparada; **no se habilitó ni se ejecutó contra proveedores**.
Se reutiliza `TiendanubeClient`, la captura `TIENDANUBE_API`, el paquete comercial
revisado y `import_jobs` como registro de envíos (`source=TN_CONTROLLED`). Sin DDL
ni nuevos servicios. Los registros CSV históricos no autorizan envíos.

## Activación posterior, con autorización

1. Probar en PostgreSQL descartable y con una tienda de prueba; revisar respaldo y
   credencial existente. Nunca poner tokens en el navegador, comandos o informes.
2. Las lecturas existentes requieren `KIKI_TIENDANUBE_READ_ENABLED` y la tienda,
   token y User-Agent configurados. Crear una captura API explícita vigente;
   esta operación no se ejecuta automáticamente al preparar un envío.
3. Para la interfaz se requieren los controles existentes de `/v2/`, Canales,
   Evidencias y escritura interna. El nuevo
   `KIKI_TIENDANUBE_WRITES_ENABLED` es **false por defecto**. La escritura externa
   también requiere `KIKI_V2_WRITES_ENABLED`. No se cambió ninguna variable real.
4. Revisar la ficha, sus hechos/citas aprobados, taxonomía KIKI/canal vigente,
   derechos de recursos y versión. En Canales, seleccionar una sola variante
   Ecomm-App y revisar nombre, marca, presentación, cantidad, pack y código.
   Actualizar requiere IDs exactos del producto y de su única variante TN;
   coincidencias SKU/EAN nunca se convierten automáticamente en vínculos.
5. Crear la previsualización persistida con una clave UUID. La autorización
   vence a los 15 minutos y fija ficha, evidencias, taxonomía, permisos y captura.
   Confirmar explícitamente el único envío después de revisar el payload.
6. Sólo después de revisar la configuración activar el flag externo. El servicio
   relee el catálogo remoto completo antes de escribir y vuelve a validar la
   ficha local. Si hay duplicados, cambios o incertidumbre, bloquea el envío.

## Alcance y límites

- `CREATE_HIDDEN`: POST de nombre, descripción, marca y SKU; visibilidad oculta.
- `UPDATE_CONTENT`: PUT de nombre, descripción y marca del producto exacto.
  No modifica variantes ni visibilidad; no escribe stock, precios o cantidades.
- SEO, categorías, imágenes y videos se conservan en el paquete revisado, pero
  no se envían mediante campos remotos cuyo contrato no fue validado. No se
  inventan IDs oficiales de categorías. Packs/multivariante requieren una
  validación específica y quedan bloqueados en este despacho inicial.
- Una lectura remota puede producir registros internos del proveedor y tiene
  una ventana de carrera: el proveedor no ofrece aquí una transacción conjunta
  inventario+alta. No se afirma garantía absoluta ante otros escritores externos.
- `RUNNING` se persiste **antes** de llamar al proveedor. Tras caída del proceso
  o respuesta incierta, consultar ese registro y reconciliar manualmente con la
  tienda; jamás reintentar automáticamente ni generar otra creación para
  sortearlo. `UNKNOWN` es terminal; `RUNNING` interrumpido también bloquea una
  nueva escritura hasta revisión operativa. No se guarda la respuesta completa,
  excepciones arbitrarias o credenciales.
- La clave idempotente protege repetición de solicitudes; CAS protege doble
  confirmación. PostgreSQL serializa autorizaciones por tienda con advisory lock.
  Un envío exitoso conserva sus IDs externos y bloquea altas duplicadas. La
  actualización posterior exige nueva previsualización con contenido distinto.
- El ledger de envíos no aprueba por sí mismo una vinculación ni modifica
  fichas/editor/historial documental/capturas. El envío no publica productos.
- Mercado Libre conserva su cliente de validación oficial `/items/validate`,
  atributos y preflight existentes: una equivalencia interna no acredita un
  payload oficial. No se publica ni se activa validación remota durante pruebas.

## API interna

Base: `/api/ecomm-app/workspace/channels/tn/submissions`.
`GET ?ecomm_id=…`, `GET /{id}` consultan registro e historial.
`POST /preview` registra `request_key`, `ecomm_id`, operación, IDs de destino
cuando corresponde, seis `identity_checks` y motivo humano.
`POST /{id}/send` exige `expected_revision`, `expected_preview_fingerprint`
y `confirm:true`. Todas las mutaciones usan sesión y CSRF existentes.
