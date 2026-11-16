# Consulta controlada a fabricantes — KIKI 2.0 (piloto no activado)

## Alcance y estado actual
Código de desarrollo en PR #172. El endpoint `POST /api/ecomm-app/workspace/{ecomm_id}/documents/fetch-manufacturer` permite **como máximo una consulta por día para una única variante** y solo a páginas HTML públicas de un dominio de fabricante expresamente configurado.

**No está desplegado ni habilitado**. No se realizan consultas durante el CI; todas las pruebas de red usan transportes y DNS falsos. No es un crawler general, no descubre productos ni ejecuta procesos en segundo plano, no realiza publicaciones ni aprobaciones automáticas.

### Condiciones de habilitación (futuro, tras autorización y copia de seguridad)
1. Migración documental segura y restauración de backup real en entorno aislado; validar operador, historial y guardado del original antes de activar.
2. Contenedor lector documental aislado funcionando y protección de kernel comprobada (`KIKI_DOCUMENT_PARSER_KERNEL_REQUIRED=true`). Si falla, se rechaza antes de consultar la fuente.
3. Validación de la política del dominio y autorización comercial para consultarlo. La consulta real exige `robots.txt` accesible y permisivo, sin `Crawl-delay` positivo. Si no es posible comprobarlo, NO hay consulta: carga manual autorizada.
4. Parámetros **todos apagados en defaults**:
   - `KIKI_DOCUMENT_SOURCE_FETCH_ENABLED=false`
   - `KIKI_DOCUMENT_SOURCE_FETCH_HOSTS=` (CSV de dominios exactos sin comodines)
   - `KIKI_DOCUMENT_SOURCE_FETCH_PILOT_ID=` (Ecomm ID exacto)
5. En el piloto Natural Seed, los valores **potenciales para una futura autorización** serían host `naturalseed.com.ar` e ID `7518949`, **nunca aplicados por esta PR**. El servidor requiere también `KIKI_DOCUMENT_WORKSPACE_ENABLED=true` y los seis objetos de esquema documental presentes y válidos. El front solo enseña el botón si el API declara capacidad `document_fetch=true`.
6. Verificar que se haya autorizado y observado la política de robots real del fabricante; **la URL `/robots.txt` no pudo inspeccionarse con la fuente de navegación usada para la investigación**, por lo que **no tenemos permiso confirmado**. No suponer que la consulta funcionará ni intentar sortear denegaciones.

## Garantías técnicas del piloto
- Acceso HTTPS con TLS y SNI verificando el hostname original; resolución DNS completa: **rechazo si alguna IP es privada, local, multicast, reservada o inválida**. La conexión TCP se fija al IP público validado y se verifica el par remoto.
- Dominios exactos en lista positiva, sin subdominios implícitos, IP literales, credenciales, querystring, fragmentos ni puertos alternativos. No se siguen redirecciones 3xx.
- Dos GET máximos: `/robots.txt` y la ruta exacta del producto. Una consulta por día por Ecomm ID piloto; sesión autorizada y CSRF; control de versión optimista del expediente.
- `robots.txt`: texto UTF-8, reglas reconocidas y permiso explícito según el parser de robots; si no se puede comprobar, no se obtiene el producto. Se rechaza Crawl-delay positivo (no se salta la espera).
- Respuesta de HTML sin compresión, `text/html`, máxima de 512 KiB, sin `noarchive`, UTF-8. Lectura de contenido en el parser aislado sin red ni JS, con límites de memoria/tiempo.
- Se conserva **contenido original completo**, SHA-256, URL, fecha, IP pública fijada, estado robots comprobado, bandera de TLS, estado `source.review_state=PENDING` y `capture_mode=ALLOWLISTED_HTTPS_FETCH`. **No se marca fuente como oficial ni se aprueban hechos automáticamente**, aunque exista TLS.
- Si hay cualquier error o bloqueo se ofrece subir un archivo HTML/PDF original autorizado y revisión manual. Nunca se recurrirá a un sitio sustituto ni se generarán especificaciones plausibles.

## Lo que falta para escalar a 2.784 variantes
Este piloto no es un procesamiento masivo: antes del alcance pleno se requieren (a) descubrimiento de URLs oficiales por marca/producto, (b) deduplicación de originales, (c) colas con cuota global y concurrencia controlada, (d) revisión y revocación por lotes y (e) auditoría de costos y licencias para imágenes/vídeos. No habilitar masivamente la consulta de red ni modificar producción desde esta PR.

**Resultado que define el próximo gate:** con un producto real y autorización legítima, archivar HTML idéntico al original de fabricante; revisarlo; conciliar Ecomm ID+SKU+presentación; aprobar hechos citados; generar ficha `DRAFT` con textos y SEO; persistir y recuperar sin modificar Ecomm-App, ML ni Tiendanube.

Plan contractual: https://github.com/Brunomperetti/kiki-tech/issues/174.
