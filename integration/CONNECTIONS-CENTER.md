# Centro de conexiones del dashboard

Base verificada: `17621a624e2ca414c267c575f7f9d0be0b5fbb3b`, rama `feature/kiki-tech-2-dashboard`, árbol inicialmente limpio. Entrega local, sin push ni cambios en Render, credenciales o PostgreSQL productivos.

## Interfaz y contratos reutilizados

Configuración conserva las preferencias y la exportación de fichas. Ahora contiene tres tarjetas y un cierre accesible durante el desplazamiento. El encabezado del dashboard ofrece **Conexiones**, con aviso de actualización en curso o nueva copia disponible. La búsqueda, selección, filtros, paginación y las cinco pestañas se conservan.

| Fuente | Lectura del estado | Acción existente |
|---|---|---|
| Ecomm-App | `ecomm_app_status`, `ecomm_app_auto_status`, `job_status` y captura API completa | `POST /api/ecomm-app/stage/manual/start` → `run_manual_refresh` → `EcommAppStageService` |
| Mercado Libre | `MercadoLibreService.status`, conexión y capturas existentes | `POST /api/mercadolibre/auth-url`, `POST /api/mercadolibre/sync`; servicios OAuth y transporte originales |
| Tiendanube | `CatalogRepository.snapshot_record("TIENDANUBE")`; fecha, productos por slug y filas | `POST /api/tiendanube/import-csv` → `TiendanubeCsvService.import_csv`, con su parser y validaciones |

La única adaptación del backend habitual es **`GET /api/connections/status`**, una proyección autenticada y sin consultas a proveedores. Se registra en `app/main.py`. No reemplaza contratos de actualización ni crea un catálogo, integración, coordinador de trabajos, tabla o migración. Los archivos de servicios, integraciones y modelos productivos permanecen intactos.

Los errores específicos de esos cuatro POST se muestran usando el detalle seguro del contrato existente: por ejemplo, actualización ya iniciada, reconexión requerida o CSV inválido. No se reintentan escrituras automáticamente.

## Significado de los estados

- **Ecomm-App:** credencial configurada no equivale a autorización vigente comprobada. La tarjeta informa esta limitación, última captura completa, variantes y trabajo persistente. El proceso manual comparte el bloqueo original con `SCHEDULED`; la captura completa se promociona mediante el servicio existente. Los errores conservan la anterior y las fichas editadas no se sobrescriben.
- **Programación:** el workflow existente sigue a las 08:25 y 16:25 de Argentina (`11:25` y `19:25` UTC). Se calculan los próximos dos horarios, incluso al pasar de día. No se consultó GitHub Actions ni se asegura que el workflow esté habilitado o ejecute puntualmente. La configuración de la credencial programada se distingue de esa verificación.
- **ML:** cuenta, vencimiento y autorización registrados en KIKI; sin prueba en vivo. El token de acceso vencido puede renovarse con el servicio original al actualizar, sin obligar a repetir OAuth. La reconexión de una cuenta vigente queda en opciones secundarias. Las publicaciones distintas se cuentan por identificador MLA padre; las variantes siguen siendo filas separadas. La captura se muestra incluso si ya no hay una cuenta conectada; no confirma la vinculación con ninguna variante Ecomm-App.
- **TN:** importación CSV, no API activa. Productos por identificador de URL y filas son cantidades diferentes. La fecha corresponde a la importación pasada y no demuestra publicación actual. La API directa se identifica como futura y sin botón engañoso.
- **Errores:** fallo de lectura/captura/importación no es fallo de publicación. No se ejecutan publicaciones ni se inventa evidencia de un intento. Las reglas comerciales anteriores y la identidad por Ecomm ID se conservan.

Ecomm-App continúa en el backend aunque se cierre Configuración o el navegador. La vista consulta progreso, sin ejecutar un bucle de descarga desde el navegador. Al detectar otra captura o completar ML/CSV ofrece **Refrescar indicadores y tabla**; no reemplaza automáticamente el contexto de trabajo y bloquea ese refresco si hay cambios de ficha sin guardar. El estado se consulta a 1,5 s durante el trabajo y a 15 s mientras Configuración está abierta; la consulta en reposo se detiene al cerrarla. El contador no hace peticiones por fila. Reutiliza cálculos globales cuyo costo crece con las capturas; no se hizo una medición concurrente de rendimiento productivo.

## Separación y límites de autorización

**Demo pública:** información explícitamente sintética, calculada a partir de los fixtures existentes. Botones e importación deshabilitados, sin OAuth, credenciales, tareas ni llamadas API. No se inventó una cantidad de productos CSV donde el fixture sólo modela registros; se muestra «—». Tampoco se inventó una fecha de captura maestra.

**Conectado aislado habitual:** mantiene origen literal `https://127.0.0.1:8443`, marcador `local-synthetic`, autenticación, CSRF y las protecciones previas. La nueva consulta permite ver los estados guardados. Las acciones permanecen cerradas por defecto.

**Escenario explícito `--connections`:** utiliza exactamente el mismo FastAPI, PostgreSQL descartable, rutas y procesos originales. Sólo después del preflight, el bootstrap instala dobles locales de inventario y del transporte ML, más una cuenta sintética con tokens ficticios cifrados. No se cargan variables ni secretos productivos. Los dobles no implementan HTTP ni DNS y rechazan cualquier ruta no prevista. No los importa `app.main` ni el código productivo.

Hay tres límites independientes: capacidades validadas por el frontend, lista exacta de cuatro POST en la pasarela y lista correspondiente en FastAPI, además de la autenticación/CSRF originales. Las listas sólo se habilitan con el marcador local explícito del arnés. Los endpoints de cron, consultas arbitrarias, callback OAuth, publicación y sincronizaciones ajenas siguen rechazados. `network_mode: none`, sockets Unix, contenedores sin privilegios y raíz de sólo lectura se conservan. La excepción multipart del CSV se limita a su ruta y al límite vigente de 15 MB más el sobre; no amplía límites de otras rutas ni del lector PDF.

**OAuth externo permanece bloqueado.** La acción prepara la URL con el servicio original y valida HTTPS/dominio, pero no navega, no abre una ventana ni afirma que se vinculó una cuenta. El intercambio, consumo de state una sola vez y renovación se prueban con el transporte local. La autenticación auténtica y su retorno al dashboard requieren autorización posterior y revisión de origen/retorno: el callback histórico `/channels?mercadolibre=connected` no se modificó. Esta entrega no habilita un modo productivo ni cambia el alojamiento.

ML/CSV conservan sus operaciones síncronas existentes. La interfaz evita dobles envíos de una misma operación; el bloqueo global manual/programado probado es el de Ecomm-App. No se añadieron trabajos durables paralelos para ML/CSV, ni historial persistente nuevo de sus errores; esos errores se conservan en la sesión del dashboard. No se promete su recuperación después de una recarga.

## Validación

Resultados confirmados:

| Pruebas | Resultado |
|---|---|
| Aislamiento base y PostgreSQL | 19 aprobadas |
| Servicios de conexiones sobre PostgreSQL | 10 aprobadas: autenticación, CSRF, ausencia de proveedores/credenciales reales, programación, concurrencia manual/programada, copia anterior, editor intacto, OAuth, token vencido y CSV |
| Backend heredado | 484 aprobadas, 2 advertencias de dependencias |
| Demo completa | 58 aprobadas, escritorio/celular; sin solicitudes API ni externas |
| Centro conectado | 12 aprobadas, escritorio/celular; incluye actualización en segundo plano, contexto, autorización, errores visibles y CSV |
| Catálogo y editor conectados del perfil habitual | 58 aprobadas: navegación, búsqueda, identidad, versiones, errores, concurrencia y conservación del contexto |
| Pasarela local | 8 aprobadas: TLS, origen/host, rutas, autenticación/CSRF y límites conservados |
| Presentación y Configuración | 14 aprobadas: exportación, calidad, cinco pestañas, evidencias, revisión e historial |
| Ruff | Aprobado, sin caché y con raíz de sólo lectura, sobre `app` e `integration_sandbox` |
| TypeScript y builds | Aprobados; demo e integración |
| Integración ampliada y seguridad, por módulos | 232 casos cubiertos: incluye los 19 base, los 10 de conexiones y los 8 de pasarela ya indicados; no sumar esos subconjuntos nuevamente |
| Recuperación real de procesos | Scripts existentes de reinicio del backend, recuperación de leases con dos ejecutores y 1.000 tareas sin duplicaciones aprobados |

**Incidencia de tiempo registrada:** el comando conjunto `python integration/run.py test` se detuvo en una prueba histórica de canales: 15,000 s para 5.000 variantes frente al límite de 12 s. No se presenta ese comando como exitoso. El servicio medido no fue modificado ni se llamó al centro de conexiones en esa medición. Se repitió únicamente ese caso en PostgreSQL fresco, con el mismo límite y sin cambiar recursos/protecciones: aprobó en **1,510 s**, con **6 consultas SQL tanto para 50 como para 5.000 variantes**. Después se ejecutaron y aprobaron los módulos restantes, incluidos los nuevos de conexiones, y los scripts de recuperación. Hay cobertura por módulos de los 232 casos, sin afirmar que hubo una segunda ejecución conjunta completa ni atribuir una causa concreta al pico inicial. No es un SLA productivo ni una medición de carga del nuevo endpoint de estados.

La primera prueba móvil reutilizaba el título de escritorio y esperaba un incremento de versión, aunque el guardado era idéntico. El editor correctamente no creó otra versión. Se separaron los títulos de prueba por dispositivo manteniendo la aserción de versión y la comprobación de conservación; los 12 casos finales aprobaron. Un primer cliente anónimo de unittest arrancaba por segunda vez el ciclo de fixtures; se corrigió el test, sin debilitar la protección que rechaza conexiones desconocidas al iniciar.

La revisión visual identificó que el formato regional podía mostrar la hora de la tarde como «04:25» sin aclaración. El centro ahora fuerza 24 horas para los horarios previstos y la prueba de navegador exige «16:25», además de la comprobación de UTC/Argentina del backend.

El disco local impidió una tanda de Docker. Se retiraron ocho imágenes antiguas del arnés sin etiquetas ni contenedores y caché de compilación sin uso de más de una hora, conservando imágenes etiquetadas y archivos del proyecto. Se recuperó espacio y las pruebas continuaron. Ruff se ejecutó con `--no-cache` en lugar de abrir permisos de escritura del contenedor. No fueron errores ni cambios de producción.

La incidencia previa intermitente del lector PDF sigue documentada en [FUNCTIONAL-VALIDATION.md](FUNCTIONAL-VALIDATION.md). No se alteraron sus límites ni perfiles en esta entrega.

## Reproducción local

En el entorno Linux de integración ya preparado:

```bash
python integration/run.py build
python integration/run.py browser-test --connections
python integration/run.py up --connections
```

El último comando es interactivo, exclusivamente local y sintético. Acceso desde el mismo host: `https://127.0.0.1:8443`; no es un enlace público ni el localhost de Windows remoto. Usuario `operador-prueba`, contraseña pública de fixtures `solo-datos-sinteticos`. No ingresar credenciales reales. Al finalizar el arnés retira contenedores/volúmenes y deshabilita su marcador de acciones. Para volver al perfil anterior, omitir `--connections`. La demostración estática se compila con `cd frontend && npm run build` y conserva el aislamiento sin backend.

## Capturas

| Vista | Escritorio | Celular |
|---|---|---|
| Centro conectado sintético | [Captura](../frontend/artifacts/conexiones-desktop.png) | [Captura](../frontend/artifacts/conexiones-mobile.png) |
| Autorización y vencimiento simulado | [Captura](../frontend/artifacts/conexiones-autorizacion-desktop.png) | [Captura](../frontend/artifacts/conexiones-autorizacion-mobile.png) |
| CSV, cantidades y error de importación | [Captura](../frontend/artifacts/conexiones-csv-desktop.png) | [Captura](../frontend/artifacts/conexiones-csv-mobile.png) |
| Demo pública aislada | [Captura](../frontend/artifacts/conexiones-demo-desktop.png) | [Captura](../frontend/artifacts/conexiones-demo-mobile.png) |

## Archivos

- Backend habitual: `backend/app/main.py`, `backend/app/api/routes/connections.py`.
- Arnés aislado: `backend/integration_sandbox/bootstrap.py`, `policy.py`, `server.py`, `connection_fixtures.py`, `connection_checks.py`; `integration/run.py`, `browser_tests.py`, `gateway.py`.
- Frontend: `frontend/src/integration/IntegrationCatalog.tsx`, `isolation.ts`, `catalog-adapter.ts`, `connections.ts`, `ConnectionCenter.tsx`, `connections.css`; `frontend/src/prototype/CatalogView.tsx`, `Dashboard.tsx`, `SettingsDialog.tsx`, `DemoConnections.tsx`.
- Pruebas de navegador: `frontend/tests/connections.spec.ts`, `frontend/integration-tests/connections-connected.spec.ts`.
- Este informe y las ocho capturas `conexiones-*.png`.
