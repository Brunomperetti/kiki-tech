# Primera carga oculta desde KIKI

Se reutilizan el editor versionado, el cliente Tiendanube, la lectura completa del
catálogo y el registro `TN_CONTROLLED` en `import_jobs`. Sin tablas, migraciones,
credenciales ni servicios nuevos. La interfaz anterior y la preparación editorial
avanzada se conservan.

## Recorrido

1. Catálogo Ecomm-App → Ficha: editar y **Guardar borrador**.
2. Canales → Ver Tiendanube → **Cargar producto en Tiendanube**.
3. Revisar identidad y marcar la única confirmación de datos.
4. **Previsualizar para Tiendanube**: comprobar contenido y campos omitidos.
5. **Enviar a Tiendanube** y aceptar la confirmación: comprobar duplicados en
   todo el catálogo remoto y crear una única variante con `published: false`.
6. Consultar el resultado persistente, los IDs y el enlace al administrador.
   Un resultado incierto/interrumpido exige inspección humana de la tienda;
   nunca se reenvía automáticamente.

## Requisitos y campos

| Dato | Tratamiento en esta corrección |
| --- | --- |
| Nombre guardado | Obligatorio; no se inventa desde una ficha vacía |
| SKU único y Ecomm ID exacto | Obligatorios para la identidad KIKI |
| Descripción, marca, SEO | Opcionales; se envían si están guardados |
| EAN | Opcional, exclusivamente original API válido, sin contradicciones ni repetición entre variantes |
| Presentación/cantidad | Se contrastan con la variante; el operador revisa su inclusión en el nombre |
| Categoría/subcategoría | No se convierten nombres locales en IDs externos; preparación avanzada conservada |
| Imágenes/videos | No se transfieren URLs sin un flujo de permisos y contrato nativo verificado; no bloquean esta creación básica |
| Precio, stock, peso, dimensiones | No hay valores autorizados y vigentes en este contrato del editor; se omiten, sin ceros inventados |

La ficha puede seguir en DRAFT. No exige IA, fuentes documentales, taxonomía ni
aprobación de los 18 campos. No aprueba hechos, publica ni transfiere decisiones.
Packs/combos, SKU repetidos y EAN compartidos permanecen bloqueados en este envío
unitario: requieren resolver identidad, no marcarlos como unidades.

## Habilitación y primera prueba real (requiere autorización posterior)

- Revisar/merge/desplegar esta PR sólo con autorización; aquí no se hace.
- Verificar las opciones **existentes** `KIKI_V2_ENABLED`,
  `KIKI_V2_WRITES_ENABLED`, `KIKI_CHANNEL_WORKSPACE_ENABLED`,
  `KIKI_TIENDANUBE_READ_ENABLED`, `KIKI_TIENDANUBE_WRITES_ENABLED` y la conexión
  de la tienda correcta. No se habilitan ni cambian variables durante desarrollo.
- La comprobación de conexión existente sólo demuestra lectura. No certifica
  `write_products`: el administrador debe comprobar el alcance de la autorización
  configurada. No inspeccionar/copiar tokens ni renovar OAuth automáticamente.
- El cliente existente utiliza `/2025-03/{store}/products`. Esta red rechazó
  acceder a la documentación oficial (`CONNECT 403`); las pruebas simuladas no
  certifican contrato vigente, permisos efectivos ni requisitos particulares de
  la tienda. Verificarlos antes de autorizar el primer POST auténtico, incluida
  la aceptación de un producto oculto sin precio/stock y la ruta del administrador.
- Mercedes selecciona **una unidad** auténtica, revisa sus datos y el contenido
  omitido. Autorizar expresamente esa creación oculta, nunca una publicación.
- Confirmar respuesta, ID remoto, visibilidad oculta y recuperación del registro.
  Ante 401/403 no renovar credenciales; ante timeout/UNKNOWN/RUNNING consultar la
  tienda y reconciliar el ID antes de cualquier nuevo intento.

## Pruebas reproducibles

Backend: `pytest -q tests/test_tiendanube_manual_submission.py
 tests/test_tiendanube_controlled_submission.py tests/test_tiendanube_connection.py
 tests/test_tiendanube_catalog_capture.py tests/test_ecomm_api_product_workspace.py`.

Playwright reutiliza el perfil privado PG18 `--stage4`: antes de iniciarlo,
crear `.integration-runtime/api/tn-submission-mode` con `offline-hidden-only`.
Sólo el bootstrap sintético instala el doble local; ejecutar
`KIKI_TN_SUBMISSION_SCENARIO=offline-hidden-only npm run test:integration --
 tiendanube-manual-send.spec.ts` con la pasarela local existente y después retirar
el archivo y los contenedores/volumen descartables. Sin red en contenedores.
