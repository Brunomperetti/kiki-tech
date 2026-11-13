# Etapa 2N — Dashboard único conectado al backend aislado

Base comprobada: `feature/kiki-tech-2-dashboard`,
`17903a5fd6233d1a999fa3685f12b136646a0661`, árbol inicialmente limpio.

Esta entrega implementa el catálogo, búsqueda, paginación, indicadores/filtros y
editor con historial dentro del dashboard. **Sólo se conecta al FastAPI y
PostgreSQL descartables ya existentes. No se habilita un modo productivo.**

## Una interfaz y dos fuentes explícitas

`prototype/CatalogView.tsx` contiene la estructura visual compartida: navegación,
encabezado, aviso de modo, indicadores, tabla, buscador y contenedor del panel.
`Dashboard.tsx` conserva el controlador de demostración y `IntegrationCatalog.tsx`
el controlador autenticado. La vista compartida no importa fixtures, elige
fuentes, abre conexiones ni implementa otro editor.

- **Demostración:** entrada habitual, productos ficticios en memoria y red
  bloqueada. Conserva las operaciones de muestra y rutas anteriores.
- **Conectado de pruebas:** entrada `integration.html`, mismo espacio visual,
  sesión/CSRF reales contra el FastAPI aislado y datos explícitamente sintéticos
  persistidos en PostgreSQL descartable. No requiere ni admite credenciales reales.

Los controladores no mezclan productos, estados o acciones entre modos. Un error
de autenticación, captura o cola elimina filas/contadores y muestra el error;
nunca activa la demostración. La integración sigue requiriendo build explícito,
meta `local-synthetic`, origen `https://127.0.0.1:8443` y cabecera de entorno.
El build normal mantiene el demo aislado. No se agregó un selector de backend,
interruptor de producción, rewrite ni lector independiente de Ecomm-App.

## Contratos existentes reutilizados

| Método/ruta | Uso |
| --- | --- |
| GET `/api/auth/me`, POST `/api/auth/login`, POST `/api/auth/logout` | Sesión y CSRF del entorno de pruebas |
| GET `/api/ecomm-app/stage/catalog?q=&page=&limit=` | Calidad, integridad y fechas de captura, sin fallback a Excel |
| GET `/api/ecomm-app/workspace/queue?filter=&q=&page=&limit=&sort=capture` | Filas paginadas, estado editorial, búsqueda y contadores globales calculados en servidor |
| GET `/api/ecomm-app/workspace/{ecomm_id}` | Fuente original, los 18 campos comerciales, versión e historial |
| POST `/api/ecomm-app/workspace/{ecomm_id}` | Guardado interno existente con CSRF y `expected_version` |

No se creó un endpoint de catálogo, editor o historial equivalente. El historial
ya forma parte de la respuesta de workspace; no necesita otro almacenamiento.

La cola recibió dos extensiones aditivas: `source` con la proyección original de
cada variante y `sort=capture`. El orden por prioridad sigue siendo el valor por
defecto de los consumidores anteriores. Se reutiliza `api_variant_row` para
proyectar una misma identidad en catálogo, cola y editor.

Las dos lecturas del dashboard se validan juntas: fuente, integridad, fechas,
totales, paginación, eco de filtros, IDs únicos y coherencia de variantes comunes.
Si las capturas difieren, no se mezclan. La tabla usa las filas ya filtradas y
paginadas por el backend, no descarga el catálogo completo al navegador.

## Tabla, indicadores y navegación

- Una fila por Ecomm ID obtenido de la variante API, sin claves por SKU o EAN.
  Los dos registros sintéticos con SKU repetido siguen separados por presentación.
- Nombre original y título/marca guardados en KIKI se distinguen. Una marca
  editada no se presenta como marca oficial obtenida del proveedor.
- Presentación, stock y fecha son los de la captura. No se muestran precios
  inventados ni se presenta ese stock como información en vivo.
- Se conservan `barcode`, `gtin_raw`, ambos indicadores de combo y bloqueos de
  identidad. `gtin` mantiene su semántica combinada anterior para compatibilidad;
  la UI nueva muestra los códigos originales por separado.
- IDs nulos, vacíos, booleanos, no positivos y placeholders como `None`/`null`
  se rechazan. Una discrepancia barcode/GTIN se muestra y bloquea decisiones y
  guardado tanto en la UI como en el servicio existente (409).
- `is_combo=False` no demuestra la cantidad de unidades. La UI conserva
  desconocidos y pide verificar cantidad/composición. No aplica familias por SKU
  como decisiones de identidad, ni fusiona registros.
- Los contadores de identidad por revisar, sin trabajar, borradores, listos para
  revisión, ficha completa y packs filtran la misma tabla. Sus valores pertenecen
  al catálogo completo, no al número de filas de la página ni a sumas de tareas
  que pueden superponerse. Se ofrecen páginas de 3, 6, 25 o 50 variantes.
- La búsqueda admite ID, SKU, nombre, presentación, códigos y marca/título KIKI
  cuando constan en la cola. Estado, búsqueda y página pueden combinarse.
- Los canales muestran sólo lo que informa su servicio: una coincidencia sigue
  siendo candidata; falta de evidencia no significa ausencia de publicación.
  Confirmaciones/preparación por canal sin fuente integrada dicen «Sin datos
  disponibles», sin ceros o porcentajes inventados.
- `q`, `filter`, `page`, `limit`, `product`, `tab` viven en la URL. Se validan
  parámetros, duplicados y placeholders antes de consultar negocio. Atrás,
  adelante y recarga conservan el contexto. Un enlace a una variante fuera de
  la página usa el GET workspace existente por ID, sin buscar un sustituto por SKU.

Los pilotos MAMA/Hileret permanecen separados y debajo del catálogo; no alteran
sus contadores. Hileret conserva ID real pendiente, originales/evidencias y origen
de las decisiones de pruebas. No se vincula ni transfiere ninguna aprobación.

## Editor y cinco pestañas

Se reutiliza `PersistentWorkspace` con `CommercialBackofficeFields`, los 18
campos originales, reglas de completitud, arrays de atributos/medios/fuentes y
almacenamiento `ecomm_api_product_edits`. No se creó una segunda ficha.

Ficha permite editar, guardar, cerrar, volver a abrir y recuperar de PostgreSQL.
Historial muestra versiones y diferencias antes/después. Al guardar se vuelve a
consultar la cola para actualizar los indicadores y la tabla, conservando el
panel aunque la variante deje de cumplir el filtro activo.

El editor mantiene cambios sin guardar, avisos al salir, reautenticación y
comparación de versiones. Dos operadores sobre la misma versión obtienen un
guardado y un conflicto 409; no se reintenta ni se sobrescribe silenciosamente.
Cambios incompatibles de identidad bloquean el guardado. Reemplazar una ficha
marcada como completa requiere confirmación incluso al guardar como borrador;
cancelar conserva los valores PostgreSQL y la edición local.

Las otras pestañas conservan su alcance:

- **Evidencias:** documentos, originales, citas y revisión del arnés 2E–2K.
  No se presentan como un módulo documental productivo ya migrado. Las decisiones
  quedan deshabilitadas si la identidad está bloqueada.
- **IA:** propuestas documentadas deterministas existentes del entorno de pruebas;
  no se agregaron funciones ni llamadas OpenAI reales.
- **Canales:** estado explicativo y datos de lectura disponibles; no hay nueva
  preparación, vinculación ni publicación. Las herramientas históricas todavía
  requieren adaptación de origen a Ecomm ID API.

Imágenes/videos se guardan como URLs de texto; su carga externa continúa bloqueada.

## Inicio y aislamiento

Con los requisitos de integración existentes (Docker local, Linux/WSL2, Node y
dependencias instaladas), desde la raíz del repositorio:

```bash
python3 integration/run.py build
python3 integration/run.py up
```

Abrir `https://127.0.0.1:8443/` **en la máquina que ejecuta ese entorno**, con su
certificado local de pruebas. No es un enlace público accesible desde otro equipo.
Usar únicamente el usuario sintético documentado en [README.md](README.md).
Ctrl+C elimina los contenedores y datos descartables. La persistencia demostrada
es entre lecturas, recargas y sesiones mientras vive esa base, no tras descartarla.

Se mantiene el preflight de URL, identidad/rol y marcador PostgreSQL antes de
importar el engine o crear tablas. Los cuatro contenedores siguen sin red, con
raíz readonly, sin puertos publicados ni credenciales de proveedores. La única
ampliación de superficie es GET autenticado de queue; POST de IA real, captura,
OAuth, sincronización y publicación continúan bloqueados. Algunos GET actualizan
la actividad de sesión exclusivamente en la base de pruebas, como estaba previsto.

No se modificaron clientes de proveedores, captura/actualización de Ecomm-App,
OAuth ML, Tiendanube, configuración Render, credenciales o modelos de producción.
Sí se ampliaron los serializadores de lectura y guardas del editor en la rama
local, sin despliegue ni efectos sobre la aplicación que utiliza KIKI.

## Validación

```bash
python3 integration/run.py test
python3 integration/run.py legacy-test
python3 integration/run.py browser-test
cd frontend
npm run typecheck
npm run build
npm run build:integration
npm test
```

| Validación | Resultado |
| --- | --- |
| Backend/PostgreSQL/aislamiento/documentos y gateway existentes | 138 aprobadas, incluidas 6 nuevas de dashboard |
| Regresiones heredadas del backend, contenedor sin red | 484 aprobadas |
| Playwright conectado, escritorio y celular | 130 aprobadas, incluidas 24 nuevas |
| Playwright piloto Hileret con PDF auténtico local | 2 aprobadas |
| Playwright demostración, escritorio/celular/tablet | 46 aprobadas |
| TypeScript y builds demo/integración | Aprobados |
| Ruff y formato de frontend | Aprobados |

La comprobación de escala utiliza 5.000 variantes inventadas, respuesta de 25
filas y contadores globales coherentes (0,205 s en esta ejecución; medición local,
no garantía de rendimiento productivo). Se mantiene la captura JSON y los
servicios existentes, sin una nueva base o infraestructura de índices.

La inspección visual detectó una regla CSS heredada que ocultaba el texto del
siguiente paso en la sexta columna. Se corrigió sólo para el modo conectado.
Se repitió el recorrido de guardado/capturas en escritorio y celular sobre ese
estilo final: ambos casos aprobaron. El JavaScript conserva SHA-256
`478e0cc9999e7b8b1cefd84146ed32c8bf097e6252a6b8eb4a571d2a3eed8892`
de la regresión completa. La prueba visual espera ficha y campos cargados antes
de capturar, y verifica que el siguiente paso esté visible.

Los avisos previos de AnyIO en pytest y de tamaño de bundle del demo no impidieron
la validación. No se modificaron cuotas o procesos de proveedores para las pruebas.
Al terminar se retiraron los cuatro contenedores y el volumen del entorno
descartable. Las capturas históricas regeneradas se restauraron sin cambios.

## Capturas

Datos exclusivamente sintéticos obtenidos del FastAPI/PostgreSQL aislados:

- [Dashboard escritorio](../frontend/artifacts/dashboard-2n-desktop.png).
- [Dashboard celular](../frontend/artifacts/dashboard-2n-mobile.png).
- [Editor escritorio](../frontend/artifacts/editor-2n-desktop.png).
- [Editor celular](../frontend/artifacts/editor-2n-mobile.png).

## Archivos y alcance pendiente

- UI compartida: `frontend/src/prototype/CatalogView.tsx`, `Dashboard.tsx`.
- Modo conectado: `frontend/src/integration/{IntegrationCatalog,PersistentWorkspace}.tsx`,
  `{catalog-adapter,workspace-adapter,isolation}.ts`, `integration.css`,
  `frontend/src/types/ecomm-app.ts`.
- Contratos existentes: `backend/app/integrations/ecomm_app/api_catalog_browser.py`,
  `backend/app/services/{ecomm_api_work_queue_service,ecomm_api_product_workspace_service}.py`,
  `backend/app/api/routes/ecomm_api_workspace.py`.
- Pruebas y aislamiento: `backend/integration_sandbox/{policy,dashboard_checks}.py`,
  `integration/run.py`, `frontend/integration-tests/{catalog,dashboard-connected}.spec.ts`.
- Evidencia: este informe y las cuatro capturas 2N. Las capturas históricas
  regeneradas por otras suites no forman parte de la entrega.

Pendiente, sin habilitar en esta etapa:

1. Configuración y autorización para que esta interfaz use el backend existente
   con productos auténticos. No necesita lectores separados ni exportaciones;
   usaría los mismos contratos y la captura API disponible, con revisión de
   integridad/frescura. El arnés sintético no se convierte en un entorno real
   cargándole variables productivas ni retirando sus protecciones.
2. Formalizar en el backend habitual la persistencia/documentos/citas y revisión
   probadas en 2E–2K; siguen en rutas/esquema exclusivos del entorno de pruebas.
3. Conectar el servicio IA existente a hechos aprobados para fichas completas,
   conservando costos, revisiones y versiones. No activar llamadas reales ahora.
4. Adaptar canales, vinculaciones y herramientas históricas a la identidad API,
   revalidando evidencia y decisiones. Preparado, candidato y publicado siguen
   siendo estados distintos; compartir SKU/EAN no los convierte en equivalentes.
5. Extender posteriormente la selección/cola existente a lotes persistentes con
   previsualización, presupuesto, resultados y reanudación. No se agrega ese
   procesamiento en 2N ni se autorizan publicaciones.

No se solicitaron APIs productivas ni se accedió a una base productiva. No se agregaron
migraciones, lectores, servicios paralelos, push, PR, merge o despliegue.
