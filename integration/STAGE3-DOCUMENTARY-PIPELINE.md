# Etapa 3 — implementación de #221

Base: `main` `3ad68a7`. Alcance: #221, #216 y etapa 3 del Plan Maestro #174.
No ejecuta el piloto productivo ni cierra su aceptación humana.

## Recorrido disponible

1. En `/v2/`, seleccionar de 1 a 20 variantes API y abrir **Operaciones**.
2. Registrar una URL HTTPS exacta autorizada por variante y su procedencia.
   La selección humana de URL no aprueba al fabricante ni sus afirmaciones.
3. Confirmar **Procesar lote autorizado**. El navegador solicita un paso por
   vez. **Pausar** o cerrar el panel detiene los pasos siguientes; el trabajo
   ya solicitado puede terminar. La cola persiste, pero **no hay worker ni
   ejecución autónoma cuando el navegador está cerrado**.
4. Cada original válido conserva bytes, SHA-256, URL, identidad y versiones.
   El extractor existente crea hechos **PENDING** con ubicación y cita literal.
   Los bloqueos de identidad y acceso quedan por variante, sin aprobación.
5. Abrir **Revisar esta variante y sus evidencias** para revisar procedencia, identidad y
   hechos con los controles existentes. Una revisión de procedencia cambia
   versión: **Completar extracción local** exige confirmación y CAS de esa
   versión, conservando exactamente bytes, identidad y citas. Una sustitución
   de contenido requiere nueva investigación; no transfiere aprobaciones.
6. El informe prepara campos deterministas únicamente desde hechos APPROVED
   vigentes. READY significa que hay campos propuestos respaldados; no que los
   18 campos estén completos, guardados o listos para publicar. Taxonomía,
   multimedia y afirmaciones sin respaldo siguen pendientes.
7. La revisión por campo y el guardado DRAFT reutilizan Proposals y el editor
   versionado. El procesamiento documental nunca guarda una ficha por sí solo.

## Recuperación y límites

- Misma tabla `kiki_source_intake_jobs`, sin migración ni nueva configuración
  productiva. Metadatos aditivos dentro de JSON; lotes antiguos sin identidad
  completa requieren selección humana nueva.
- Máximo 20 variantes, un paso activo global y tres intentos por variante/lote;
  cuota documental diaria existente conservada. Errores transitorios permiten
  reintento explícito; robots, identidad y restricciones requieren revisión.
- Lease de diez minutos, token de propiedad y revisión CAS. Recuperar un lease
  vencido completa sólo trabajo local; nunca inicia la variante siguiente.
- La misma identidad y original se reutilizan sin redescarga ni duplicados.
  SHA, SKU, códigos crudos, presentación, familia y flags de combo quedan
  fijados; compartir SKU/GTIN no autoriza compartir evidencia.
- Historial operativo acotado a 512 eventos con marcador de truncamiento.
  Originales, versiones y decisiones conservan su historial documental propio.
- GET `.../sources/intake-jobs/{id}/report` recalcula cobertura y citas bajo
  los controles existentes. CSV `.../{id}/exceptions.csv` exige revisión y
  fingerprint actuales; invalida exportaciones tras cambios documentales.
- OpenAI desconectado en este recorrido: cero solicitudes y USD 0 de IA.
  Se informan intentos, bytes, duración y solicitudes medidas cuando existe
  recibo. No se inventa consumo para solicitudes interrumpidas sin recibo.
- La obtención automática reutilizada admite páginas HTML, hasta 4 MiB;
  rechaza otros formatos. Los PDF conservan su incorporación manual y lector
  existente con sus límites; no se añadió un descargador PDF ni navegación web.

## Ensayo aislado reproducible

Con UID 1000 y Docker local, usando exclusivamente datos inventados:

```sh
cd frontend
npm ci
npm run build:production
cd ..
python integration/run.py build
python integration/run.py browser-test --stage3
```

El perfil reutiliza el Dockerfile productivo y `start.py --reader-only` para
validar chroot/seccomp reales. Los cuatro contenedores carecen de red y puertos
publicados. Sólo el transporte HTTP/DNS del fabricante se reemplaza por dobles
locales; FastAPI, autenticación, CSRF, PostgreSQL, parser y React son reales.
El parser no recibe secretos ni el socket PostgreSQL. No se falsea su health.

CI conserva cuatro jobs; el de PG18 ejecuta el nuevo
`python -m integration_sandbox.ci_stage3_pipeline_smoke`. Su modo local
`--local-synthetic` exige primero socket, rol sin privilegios y marcador de
base sintética. El ensayo PG usa parser puro para comprobar reglas y SQL;
el navegador y el smoke del supervisor comprueban el aislamiento del lector.

Validación local de la implementación: 1.006 pruebas pytest de backend y Ruff;
13 pruebas PostgreSQL 18.7; 6 Playwright del recorrido nuevo y sus contratos,
en escritorio y móvil; 58 Playwright de la demo estática. TypeScript y los
builds demo, producción e integración aprobados. Imagen productiva probada
con red deshabilitada, lector protegido y cierre limpio sin CAP_KILL.
Además: 18 comprobaciones Playwright de `/v2/`, 72 regresiones de catálogo,
URL y propuestas reejecutadas tras corregir las incidencias encontradas, y dos
recorridos con el PDF auténtico Hileret. La regresión PostgreSQL heredada y
los reinicios manual/autónomo existentes conservaron datos y versiones;
se recuperaron 1.000 tareas sin escrituras comerciales.
Estos resultados locales no sustituyen el estado observado de CI remoto.

## Aceptación y pasos que requieren autorización posterior

| Requisito #221 | Implementación / comprobación |
| --- | --- |
| Selección API y URL exacta por variante | Manifiesto existente + identidad completa fijada |
| Original → candidatos con citas | LocalDocuments + Research.extract, sin aprobación |
| Hasta 20, pausa y recuperación | Cola existente, lease/CAS, caché y finalización local |
| Propuesta determinista por campo | Proposals + Context, citas y motivos de bloqueo |
| Cobertura, consumo y excepciones | Informe vivo + CSV protegido por fingerprint |
| PostgreSQL18 y navegador sintético | Smoke reutilizable + escenario `--stage3` |
| Piloto real de 4–10 variantes | Pendiente de URLs, permisos y autorización específica |

Antes del piloto real: responsable autoriza variantes exactas, fabricante,
dominios, condiciones/robots y cantidad. Revisar flags existentes sin cambiar
cuotas ni permisos desde esta PR; validar primero cuatro a diez variantes,
pausar, recuperar y revisar excepciones. Aprobación humana y guardado se
aceptan aparte. El HTTP401 de OpenAI registrado en #221 no se oculta ni se
repara aquí. Sin merge, despliegue, publicaciones o cambios productivos.
