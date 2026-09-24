# KIKI Tech — Catalog Reconciler

Plataforma interna de KIKI Market para automatizar, de forma trazable y segura, procesos entre **Ecomm-App**, **Mercado Libre** y, en etapas futuras, Tiendanube. Este MVP compara exportaciones XLSX y clasifica productos; **no publica, edita ni elimina información en sistemas externos**.

## Problema que resuelve

El inventario y las publicaciones viven en ecosistemas distintos. Catalog Reconciler crea un modelo interno común, normaliza identificadores que Excel suele deformar, valida calidad, aplica matching por niveles y deja los casos ambiguos para revisión humana.

## Arquitectura

```text
backend/app/
├── api/routes/              # Contrato HTTP y errores amigables
├── catalog/                 # Dominio puro: modelos, normalización, validación, matching
├── integrations/            # Adaptadores XLSX y límites para integraciones futuras
├── services/                # Orquestación y logging
├── repositories/            # Persistencia desacoplada
└── database/                # SQLAlchemy 2
frontend/src/
├── components/              # Layout, tabla y estados reutilizables
├── pages/                   # Dashboard, Productos, Revisión, Importaciones
├── services/                # Cliente HTTP
└── types/                   # Contratos TypeScript
```

La propuesta original se ajustó separando los modelos Pydantic del dominio de las entidades ORM. El reconciliador no conoce Excel, FastAPI ni PostgreSQL y se prueba completamente en memoria. Los adaptadores convierten cada origen al modelo único `Product` / `ChannelListing`; el repositorio conserva snapshots, auditoría y ejecuciones.

### Estrategia de conciliación

1. SKU normalizado exacto (`confidence=1.0`).
2. EAN/GTIN exacto (`confidence=0.98`).
3. Título normalizado similar (`confidence` calculada): siempre `REVIEW_REQUIRED`.
4. Sin match: `CANDIDATE_TO_PUBLISH`.

Múltiples coincidencias o SKU repetidos se clasifican como `POSSIBLE_DUPLICATE`. Las validaciones poseen severidad `ERROR`, `WARNING` o `INFO`; un EAN ausente es advertencia y no bloquea automáticamente una candidatura.

## Instalación local

Requiere Python 3.12 y Node.js 20+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cp .env.example .env
# Para una prueba rápida, use DATABASE_URL=sqlite:///./kiki.db
cd frontend && npm install
```

Para PostgreSQL local: `docker compose up -d db` y use la URL incluida en `.env.example` cambiando el password a `kiki-local`.

## Variables de entorno

| Variable | Uso |
|---|---|
| `DATABASE_URL` | URL SQLAlchemy de PostgreSQL (SQLite es el fallback de desarrollo) |
| `CORS_ORIGINS` | Orígenes frontend separados por coma |
| `MAX_UPLOAD_MB` | Límite por XLSX |
| `VITE_API_URL` | URL pública del backend para el build frontend |
| `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `ML_REDIRECT_URI` | Reservadas para MVP 2; no se usan ahora |

Nunca registre ni confirme secretos reales.

## Ejecución

```bash
# desde backend/
uvicorn app.main:app --reload
# desde frontend/
npm run dev
```

API: `http://localhost:8000`; documentación OpenAPI: `/docs`; frontend: `http://localhost:5173`.

## Importación y uso

1. Abrir **Importaciones** y cargar un `.xlsx` de Ecomm-App.
2. Cargar el `.xlsx` de Mercado Libre.
3. Revisar columnas desconocidas informadas (se ignoran de forma segura).
4. Volver al Dashboard y pulsar **Analizar catálogo**.
5. Consultar Productos con búsqueda/filtros y los casos accionables en Revisión.

La fila de encabezados se detecta por la mejor combinación de aliases conocidos, sin depender de una posición: funcionan tanto planillas simples como exportaciones con filas informativas. Ecomm-App requiere al menos SKU de producto, SKU de variante o EAN; Mercado Libre acepta además número de publicación. Los códigos se leen como identificadores string. Para preservar ceros iniciales, el archivo fuente debe almacenarlos como texto: Excel no permite recuperar ceros que ya eliminó antes de exportar.

Cuando existen ambos SKU, el **SKU de variante** representa el artículo concreto y se usa como `sku_effective`; si está vacío, se usa el **SKU de producto**. Se conservan ambos valores y `sku_source` registra la decisión por fila. El dashboard muestra filas leídas, aceptadas y descartadas, fila de encabezado, columnas reconocidas/ignoradas y advertencias de cada última importación.

### Canonicalización de Ecomm-App

La importación conserva primero cada fila como una asociación de canal (`EcommChannelRow`) y genera después los productos canónicos contra los que se ejecuta la conciliación. Una fila de canal conserva marketplace, tienda, publicación, estado, `marketplace_price`, `list_price`, costo, stock y ambos SKU; por eso varias publicaciones del mismo artículo no se consideran automáticamente productos duplicados.

La clave de agrupación se elige de forma conservadora, en este orden:

1. **ID interno**, por sí solo, cuando existe. Todas las filas con ese ID forman un único producto canónico aunque hayan cambiado SKU, canal, publicación o precio.
2. Sin ID interno, SKU de variante.
3. Sin ID interno ni SKU de variante, SKU de producto.
4. EAN como último fallback.

Nunca se agrupa por nombre. Todos los SKU y EAN observados bajo un ID se conservan en `sku_aliases` y `ean_aliases`; los cambios se exponen como conflictos, pero no crean productos artificiales ni duplicados por sí solos. Dos IDs internos diferentes permanecen como productos canónicos diferentes; si comparten un alias que debería ser único, la validación los marca como duplicados reales. Al agrupar, se conserva la primera ocurrencia no vacía de cada campo canónico y se exponen todas las diferencias sin eliminar las filas originales.

El matching prueba primero cualquiera de los SKU del producto, después cualquiera de sus EAN y finalmente el título, que siempre requiere revisión. Un único alias exacto implica evidencia de publicación; si aliases distintos apuntan a publicaciones diferentes, el resultado es `REVIEW_REQUIRED` en vez de inventar otro producto o elegir una publicación arbitrariamente.

El precio canónico es exclusivamente `Precio Lista`, porque representa el valor del producto. `Precio Marketplace` pertenece a cada canal y permanece en la fila asociada; nunca se promueve implícitamente a precio canónico. Ambos precios y el costo se conservan. El dashboard separa filas Ecomm importadas, productos únicos, filas asociadas, publicaciones ML y resultados de conciliación, y el diagnóstico informa productos creados, filas agrupadas y conflictos calculados.

Un modelo explícito `Product → ProductVariant` queda como decisión arquitectónica futura para el publicador. No se implementa en este MVP: esta etapa solamente reconcilia de forma read-only el catálogo existente y no incorpora API, OAuth ni publicación en Mercado Libre.

## Estados

- `ALREADY_PUBLISHED`: match exacto por SKU/EAN.
- `CANDIDATE_TO_PUBLISH`: no existe asociación y los datos mínimos son utilizables.
- `REVIEW_REQUIRED`: posible match textual, nunca asociación definitiva.
- `POSSIBLE_DUPLICATE`: identificador o match múltiple.
- `INCOMPLETE_DATA`: nombre/precio/stock obligatorio inválido.
- `INVALID_SKU` / `INVALID_EAN`: identificador ausente o inválido.
- `UNMATCHED_ML_LISTING`: publicación sin producto claro.

## Tests y calidad

```bash
cd backend && pytest
cd backend && ruff check app tests
cd frontend && npm run build
```

La suite cubre normalización de SKU/EAN, matching exacto, no-match, revisión textual, duplicados, datos incompletos, archivos inválidos y aliases alternativos.

Cada pull request ejecuta GitHub Actions en dos jobs independientes: backend con Python 3.12 (`pip install`, `ruff` y `pytest`) y frontend con Node.js 22 LTS (`npm ci` y build). Las dependencias frontend usan versiones exactas y `package-lock.json`; cualquier actualización debe regenerar y confirmar el lockfile para mantener instalaciones reproducibles.

## Docker y Render

Backend local: `docker build -t kiki-api backend && docker run --env-file .env -p 8000:8000 kiki-api`.

`render.yaml` define backend Docker, sitio estático y PostgreSQL. En Render configure `DATABASE_URL` desde la base administrada, `CORS_ORIGINS` con el dominio del frontend y `VITE_API_URL` con el dominio del API. Build frontend: `cd frontend && npm ci && npm run build`; start backend: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. No se realiza deployment automático desde este repositorio.

## Limitaciones actuales

- Solo XLSX; cada nueva importación reemplaza el snapshot vigente del origen, conservando el historial del job.
- No hay autenticación ni migraciones Alembic todavía.
- La similitud textual es deliberadamente conservadora y requiere validación humana.
- No existe escritura hacia Ecomm-App, Mercado Libre o Tiendanube, ni Selenium, n8n o agentes de IA.

## Roadmap (no implementado)

1. **MVP 2:** API real de Mercado Libre.
2. **MVP 3:** Product Readiness Engine (SKU, EAN, precio, stock, imágenes, categoría y atributos).
3. **MVP 4:** preview de publicación.
4. **MVP 5:** publicador Mercado Libre.
5. **MVP 6:** verificación de publicación.
6. **MVP 7:** vinculación con Ecomm-App.
7. **MVP 8:** Tiendanube.
8. **MVP 9:** n8n, webhooks y automatizaciones.

El próximo paso recomendado es validar aliases con exportaciones reales anonimizadas, agregar Alembic/autenticación y recién después construir el cliente **read-only** de Mercado Libre para MVP 2.
