# Cierre para Guillermo — viernes 13/11/2026

Base comprobada: `feature/kiki-tech-2-dashboard`,
`96a7f36c8970cce7c497da52daec25c3a4a89fd5`, árbol limpio antes del cierre.
No se inició otra etapa de desarrollo ni se modificó el diseño de 2R.

## Qué se puede mostrar

Una sola aplicación con búsqueda/filtros, identidad Ecomm ID, 18 campos, cinco
pestañas, revisión por campo, guardado versionado, historial y cola autónoma.
`up --presentation` prepara **un único escenario**: seis variantes sintéticas,
capturas ML/CSV TN sintéticos, documento inventado de chía y folleto auténtico
Hileret ya disponible localmente. Reutiliza los servicios actuales; no agrega
catálogo, editor, generador, base, migración o integración comercial.

Los documentos empiezan **sin hechos aprobados**. La preparación automática no
simula una aprobación humana. Las aprobaciones de Playwright se identifican como
recorridos automatizados de prueba, no decisiones del cliente.

| Capacidad | Estado exacto para presentar |
| --- | --- |
| Catálogo y variantes | Backend existente, con captura sintética en esta demostración. No catálogo real conectado. |
| Ficha, aprobación por campo e historial | Operativos y persistidos en PostgreSQL descartable. Identidad/versiones/CSRF conservados. |
| Evidencias | Importación, original, hash, extracción, citas, revisión y contradicciones operativos. La extracción no aprueba. |
| Hileret | PDF auténtico local de 6.232.081 bytes; SHA-256 `bd99c29548cbf683e57b1fd6f2973f37ccef76477e2f6bc45379017a63599291`. Página 2: EAN individual y DUN logístico separados. Unidad, pack x6 y caja x9 no se fusionan; Ecomm ID auténtico pendiente. Sin ingredientes/nutrición/certificaciones inferidos. |
| Propuestas completas respaldadas | Generador **determinista**, sin OpenAI. Título, descripciones, características y SEO sólo cuando hay hechos aprobados suficientes; pendientes explícitos. |
| Canales | Servicios actuales sobre capturas/CSV sintéticos. Candidato no equivale a publicado; CSV antiguo no acredita publicación actual. |
| Lotes y revisiones | Cola 2Q/ejecutor 2R existentes, revisión cada 30 días, tareas y propuestas para revisión; sin aprobación/publicación automática. |
| Investigación externa | Recorrido asistido probado con DNS/HTTP simulados; búsqueda web real y descarga externa desactivadas. |

## OpenAI original: comprobado en código, sin consultar producción

`EcommAiEditor` (`backend/app/services/ecomm_ai_editor_service.py`) ya expone:

- `GET /api/ecomm-app/workspace/ai/{ecomm_id}/latest`: consulta sin proveedor.
- `POST /api/ecomm-app/workspace/ai/{ecomm_id}/suggest`: generación histórica,
  autenticación/CSRF, `expected_version`, identidad, caché por huella y persistencia
  en `KikiAiEditorialDraft`; **bloqueada en el entorno de demostración**.
- Proveedor existente: `https://api.openai.com/v1/chat/completions`;
  `KIKI_AI_MODEL`, valor predeterminado en código `gpt-4.1-mini`.
  No se verificó ni cambió el modelo/configuración efectivos de producción.
- Diez intentos Ecomm por día UTC, con reserva persistida antes del consumo y
  unicidad de slot contra concurrencia. Fallos consumen intento; salida hasta
  450 tokens, temperatura 0,1, JSON, timeout 22 s, controles de cantidades/packs.
- El piloto Tiendanube existente tiene otra cuota: un intento diario UTC y 300
  tokens. No es un contrato de fichas completas por variante API.

La pestaña IA ahora **consulta el servicio original en lectura**, muestra estado,
cuota disponible y, si existe, su sugerencia histórica. Rechaza otra identidad.
No permite convertir una sugerencia histórica sin citas en evidencia aprobada ni
aplicarla automáticamente. La única ampliación de permisos del arnés es GET
`latest` para los seis IDs sintéticos; POST `suggest` sigue prohibido en frontend,
gateway y backend aislado. No se modificó el proveedor ni su lógica productiva.

**Límite comercial pendiente:** el servicio histórico sólo devuelve título,
descripción y preguntas desde datos declarados; no los 18 campos con citas por
afirmación. Los controles monetarios USD y la reserva por precio/modelo requeridos
por `kiki-evidence-generation-v1` aún son un contrato de preparación desactivado,
no una implementación de presupuesto monetario comprobada. En este código hay
cuotas y límites de tokens; no se encontró un tope monetario global implementado.
No se inspeccionó la configuración de facturación externa ni se utilizó una clave.
Por eso no se activa una generación paga como si ya cumpliera ese contrato.

## Investigación automática: alcance y autorización futura

`EnrichmentExternalResearchService` conserva investigación y decisiones manuales;
no es un buscador web. `assisted_research.py` prepara contexto EAN/marca/presentación
y usa el recolector **simulado** separado. El parser y los servicios documentales
ya extraen hechos y citas. El PDF Hileret demuestra extracción de documentación
auténtica, no una búsqueda ni descarga automática realizada en esta entrega.

`https_connector.py` ya tiene TLS, dominio autorizado, resolución/IP pública y
pinning del destino, límites de tamaño/tiempo/solicitudes, control de contenido y
redirecciones. Está probado mediante transportes simulados y protegido por el
cerrojo de release `REAL_NETWORK_ENABLED = False`. No hay un motor de búsqueda
general ni una ruta productiva que lo utilice. **No basta con poner una variable
de entorno o agregar un dominio para disponer de investigación automática real.**

El recolector general limita cada documento a 512 KiB. El folleto Hileret de
6.232.081 bytes usa el perfil manual ya aprobado por hash, no una excepción de
descarga HTTPS. Un piloto posterior con PDFs grandes necesita revisar ese alcance.
Los documentos escaneados que requieren OCR siguen bloqueados; no se fingió su extracción.

Para un piloto posterior: autorizar expresamente producto/presentación/Ecomm ID y
fuentes oficiales o proveedores; revisar el plan de `integration/validate_pilot.py`
y el contrato `pilot_policy.py`; aprobar el enlace del recolector independiente al
adaptador y su salida de red mínima; mantener FastAPI/PG sin Internet; validar con
un documento autorizado, registrar procedencia/hash/citas y exigir revisión humana.
Quitar el cerrojo o conectar transporte real requiere revisión y autorización
posteriores. Esta entrega no cambia esa política ni ejecuta consultas externas.

## Recorrido y acceso

Ver [Windows y guion paso a paso](WINDOWS-DEMO.md). No se entregan sólo capturas:
el comando probado inicia la aplicación interactiva y conserva los cambios mientras
esté activo el PostgreSQL descartable. Cerrar/reabrir navegador conserva las fichas.
Ctrl+C elimina la base y reiniciar la demo comienza limpio.

**Distribución pendiente:** los commits nuevos permanecen locales. Para obtener
esta versión desde GitHub hace falta autorizar y efectuar posteriormente un push
de **esta rama**; no se hizo. No se promete que un ZIP o enlace interno de Codex
sea descargable desde ChatGPT. No hay herramienta de publicación de puerto/URL
temporal ofrecida en esta sesión. El estado cloud declara Desktop habilitado,
pero faltan `cua_repl.js` y `open_in_codex`; no se pudo comprobar/controlar ese visor.
`127.0.0.1` de Codex no es `127.0.0.1` de Windows.

Bloqueantes para una presentación **de funciones reales externas**: acceso a los
commits en la máquina del presentador, catálogo auténtico autorizado, generación
OpenAI con respaldo/costos y búsqueda externa autorizada. No bloquean el recorrido
local identificado como demostración. Windows/WSL2 se documenta; la validación
ejecutada aquí es Linux, no una sesión real de Windows.

## Verificación final

**694 pruebas backend/aislamiento aprobadas**: 210 del arnés/gateway (incluidas
las dos nuevas del servicio OpenAI de sólo lectura) y 484 heredadas.
**206 Playwright aprobadas**: 4 de presentación integral, 138 de regresión general,
2 del PDF Hileret auténtico, 8 Canales, 8 lotes y 46 demo sin backend. Los perfiles
específicos del cierre se ejecutaron por separado. No se suman repeticiones como
pruebas adicionales.

TypeScript, builds general/integración, Ruff, formato de los archivos nuevos y
`git diff --check` aprobados. Vite conserva su advertencia de tamaño del bundle y
pytest sus dos advertencias heredadas; no son fallos.

Las métricas quedan en [registro de validación](../frontend/artifacts/presentacion-guillermo-validation.json).
Sin llamadas productivas, OpenAI real, Render, push, PR, merge o despliegue.

| Captura | Escritorio | Celular |
| --- | --- | --- |
| Dashboard | [ver](../frontend/artifacts/presentacion-guillermo-dashboard-desktop.png) | [ver](../frontend/artifacts/presentacion-guillermo-dashboard-mobile.png) |
| Comparación y revisión | [ver](../frontend/artifacts/presentacion-guillermo-propuesta-desktop.png) | [ver](../frontend/artifacts/presentacion-guillermo-propuesta-mobile.png) |
| Lote | [ver](../frontend/artifacts/presentacion-guillermo-lote-desktop.png) | [ver](../frontend/artifacts/presentacion-guillermo-lote-mobile.png) |
| Hileret auténtico, pendiente de aprobación | [ver](../frontend/artifacts/presentacion-guillermo-hileret-desktop.png) | [ver](../frontend/artifacts/presentacion-guillermo-hileret-mobile.png) |

Comando exacto `python3 integration/run.py up --presentation`: **comprobado en Linux**
con TLS validado, login, seis variantes, consulta OpenAI sin consumo, PDF auténtico
sin aprobaciones y guardado/recuperación desde PostgreSQL. Al terminar se retiraron
los contenedores y la base descartable. No se observaron errores bloqueantes en
ese recorrido local; distribución GitHub y comprobación Windows siguen pendientes.

## Archivos del cierre

- `backend/integration_sandbox/documental_workspace_checks.py`
- `backend/integration_sandbox/policy.py`
- `backend/integration_sandbox/presentation_fixtures.py`
- `frontend/artifacts/presentacion-guillermo-dashboard-desktop.png`
- `frontend/artifacts/presentacion-guillermo-dashboard-mobile.png`
- `frontend/artifacts/presentacion-guillermo-hileret-desktop.png`
- `frontend/artifacts/presentacion-guillermo-hileret-mobile.png`
- `frontend/artifacts/presentacion-guillermo-lote-desktop.png`
- `frontend/artifacts/presentacion-guillermo-lote-mobile.png`
- `frontend/artifacts/presentacion-guillermo-propuesta-desktop.png`
- `frontend/artifacts/presentacion-guillermo-propuesta-mobile.png`
- `frontend/artifacts/presentacion-guillermo-validation.json`
- `frontend/integration-tests/presentation-connected.spec.ts`
- `frontend/src/integration/GenerationReadiness.tsx`
- `frontend/src/integration/isolation.ts`
- `integration/PRESENTACION-GUILLERMO.md`
- `integration/README.md`
- `integration/WINDOWS-DEMO.md`
- `integration/browser_tests.py`
- `integration/run.py`
