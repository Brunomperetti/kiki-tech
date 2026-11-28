# Validación oficial de contenido ML, sin publicación

Se reutiliza `MercadoLibreService._client(connection).validate_item(payload)`;
no se utiliza `_run`, renovación OAuth ni `POST /items`. No se ejecutó contra ML.
El registro persistente usa `import_jobs`, `source=ML_VALIDATION`, sin migración.

El flag nuevo `KIKI_ML_OFFICIAL_VALIDATION_ENABLED=false` es independiente del
permiso interno `KIKI_V2_WRITES_ENABLED`; ambos deben autorizarse posteriormente.
Se conserva la conexión OAuth/cifrado existente. Un token vencido o vendedor
incompatible bloquea **antes** de crear el cliente o descifrar su credencial.
No se cambiaron variables reales, credenciales ni presupuesto.

En Canales → ML, preparar una previsualización con vendedor y categoría reales,
precio, moneda, cantidad, condición y modalidad seleccionados por el operador.
No hay valores comerciales predeterminados. El precio/cantidad se envía sólo a
`/items/validate`; no se escribe ni modifica ningún recurso comercial.

La ficha debe superar el paquete revisado: evidencia vigente, identidad por
Ecomm ID exacto, taxonomía versionada y derechos de todas sus imágenes. Los
atributos BRAND/GTIN requieren citas aprobadas del tipo correcto y valor exacto.
Otros atributos obligatorios quedan bloqueados hasta contar con un mapeo
semántico respaldado: una cita de marca no puede acreditar otro atributo.

Tras confirmación explícita se comprueban vendedor, árbol de categoría frente
a la equivalencia aprobada y atributos oficiales mediante tres GET. La cuarta
y última solicitud permitida es `POST /items/validate`. TLS y DNS fijados,
redirecciones rechazadas, respuestas limitadas, ningún reintento automático.
Sólo HTTP 204 acredita la validación de **ese payload en ese momento**; no prueba
publicación actual ni sustituye los controles de una futura publicación.
Se vuelven a comprobar ficha/evidencias/permisos antes y después del POST. Si
cambian durante la consulta, el registro queda bloqueado aunque hubo HTTP 204.

Base interna: `/api/ecomm-app/workspace/channels/ml/validations`.
GET por Ecomm ID consulta historial. POST `/preview` fija payload y fingerprint;
POST `/{id}/validate` exige revisión, fingerprint y `confirm:true`, sesión y CSRF.
Las autorizaciones vencen a los 15 minutos. Resultado incierto o ejecución
interrumpida requieren consultar el registro, sin reintentos automáticos.

La activación exige revisión de infraestructura/backup existente, permisos y
cuenta real, token vigente y parámetros auténticos. Esta implementación no
crea una publicación ML ni agrega un proveedor o servicio pago.
