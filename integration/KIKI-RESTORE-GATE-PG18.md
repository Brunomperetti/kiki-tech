# KIKI Tech 2.0 — compuerta de restauración y migración documental PG18

**Alcance del permiso de noviembre de 2026:** preparar/verificar sin mutar la
base PostgreSQL de Render, sin crear servicios pagos y sin activar fabricantes,
IA ni publicaciones. PR de seguridad y pruebas; NO fusionar ni desplegar sin
autorización posterior.

## 1. Opciones disponibles — qué demuestra cada una

| Alternativa | Precio / datos reales | Evidencia | Decisión |
| --- | --- | --- | --- |
| **CI GitHub existente** con servicio descartable `postgres:18` | No crea servicios Render ni usa backup real. Consume los minutos de CI normales | Valida `UP`, guarda trabajo de prueba, falla `DOWN` si no está vacía; además genera y restaura un respaldo **sintético** con `pg_dump -Fd`/`pg_restore` | **Ejecutar ahora en la PR** |
| Inspección local del `.dir.tar.gz` real | Sin Docker, PostgreSQL, proveedores ni carga de archivos a GitHub | Tamaño, SHA-256, integridad tar/gzip y presencia de `toc.dat` | **Preparada con el PowerShell offline** |
| Restauración privada del respaldo real en PostgreSQL 18 aislado | Requiere que el archivo real y PG18 estén disponibles en un equipo/entorno local confiable; **no se provisiona nada** con esta PR | Única comprobación de que el backup del operador es restorable y de que la migración convive con sus datos reales | **Pendiente hasta contar con el archivo + entorno** |
| Nueva base Render, herramientas remotas, carga del backup a CI | Puede facturar o transferir datos privados | No necesaria para preparar pruebas | **No autorizada** |

La exportación Render `2026-11-19T19_28Z.dir.tar.gz` fue mostrada por
el operador en una captura y examinada por un script local anterior. Esa
captura **no equivale a restauración demostrada**. Este repositorio no incluye
ni debe incluir la exportación privada, las credenciales ni sus datos.

## 2. Preflight local, sin instalar Docker ni tocar Render

Abrir PowerShell en el equipo que guarda la exportación y ejecutar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\integration\KIKI_Validar_Archivo_Backup.ps1 -BackupPath "$env:USERPROFILE\Downloads\2026-11-19T19_28Z.dir.tar.gz"
```

Si el nombre difiere, pasar **la ruta real**, no copiarla de esta guía.
El script solo lee ese archivo y calcula SHA-256, comprueba tar/gzip y
`toc.dat`; **no dice que la restauración pasó**, no lo publica y no requiere
Docker. Guardar hash, tamaño, fecha y resultado en acta privada, no subir el
archivo a GitHub. Si falla, no seguir.

## 3. Compuerta de restauración del backup REAL (pendiente)

Realizar únicamente cuando exista **un PostgreSQL 18 descartable y
aislado**, preferiblemente sin red ni puertos externos, que **no tenga
credenciales ni rutas a Render**. No ejecutar comandos de este bloque contra
`kiki-tech-db` ni usar una URL de producción. Un rol/equipo distinto del
operador de producción debe validar los parámetros del destino.

1. Verificar PG18 en destino, identidad de la base **`kiki_restore`**, cero
   tablas preexistentes, espacio libre y acceso exclusivo.
2. Extraer el `.dir.tar.gz` validado en un directorio temporal seguro,
   revisar `toc.dat` y `pg_restore --list`. Confirmar su hash SHA-256 antes y
   después de copiarlo al entorno aislado.
3. Restaurar usando pg_restore **18** en la base vacía:
   `pg_restore --format=directory --no-owner --no-acl --exit-on-error -d kiki_restore <DIR_CON_TOC_DAT>`.
   Si hay un error, resultado **NO PASÓ**. Conservar logs técnicos sin datos
   personales.
4. Consultar `SELECT current_database(), current_setting('server_version')`,
   y validar presencia y conteos de `catalog_snapshots`,
   `ecomm_api_product_edits`, `kiki_evidence_documents`,
   `kiki_evidence_dossiers`, `kiki_editorial_batches`; comparar
   identificadores y cantidades del momento del backup.
5. Comprobar `to_regclass('public.kiki_source_intake_jobs')`. Si ya existe,
   **detener** y conciliar versión antes de aplicar un SQL nuevo.
6. Ejecutar `UP` de
   `backend/app/services/documental/source_intake_migration.py`
   **solo en la copia**, con transacción y `lock_timeout = '5s'`. No
   mantener otro archivo de DDL que pueda diferir de la fuente.
7. Comprobar 12 columnas, índice, unicidad de `request_key`, JSON, inserción
   y lectura de un trabajo **sintético**; reconectar para acreditar
   persistencia. Recontar tablas originales: ninguna perdió registros.
8. Ejecutar `DOWN` en una transacción de prueba con el trabajo sintético
   presente: **debe bloquearse por `KIKI_INTAKE_DOWN_BLOCKED_NONEMPTY`**.
   Borrar **solo el trabajo sintético de la copia** y volver a probar `DOWN`;
   debe borrar solamente la tabla de cola, sin modificar tablas anteriores.
9. Destruir **solo la copia descartable**. Conservar backup original,
   huella SHA-256 y acta con `PASS/FAIL`, número de tablas/filas y versiones.
   No incorporar originales de fabricantes, ni iniciar workers, ni activar
   banderas por el resultado de esta prueba.

**No se considera superada la compuerta con el CI sintético solamente**.

## 4. Reversión y seguridad

- **Antes de cualquier migración productiva futura**: un nuevo backup
  independiente, restaurado y validado, ventana acordada y aprobación
  explícita. Registrar commit backend/web y versión PostgreSQL.
- **Si fallara una futura implementación**: apagar únicamente la funcionalidad
  de cola/consultas externas (si hubiera estado autorizada), volver a la
  versión anterior de código **API y web en orden compatible**, comprobar
  `/health` y operaciones previas. **Conservar la tabla**
  `kiki_source_intake_jobs` y el historial generado.
- Nunca ejecutar `DROP TABLE` ni `DELETE` para resolver un fallo en
  producción. `DOWN` ahora tiene un bloqueo atómico con
  `ACCESS EXCLUSIVE` y rechaza borrar si hay una sola fila. El rollback de
  *esquema* solo se ensaya en la copia y con autorización separada.
- **No restaurar la exportación antigua sobre la base productiva**: borraría
  cambios realizados después de la fecha del backup. Cualquier recuperación
  productiva real requiere una decisión de desastre y revisión de RPO/RTO.

## 5. Criterios de cierre / lo que falta aprobar

- [x] SQL `UP` aditivo conocido; la tabla NO se crea al arrancar KIKI.
- [x] Tests PostgreSQL 18 sin datos reales ya existentes en CI.
- [x] Protección de `DOWN` no destructivo en esta rama de preparación.
- [x] Restauración y migración con backup **sintético** añadidas a la CI.
- [ ] Archivo `.dir.tar.gz` real: hash/TOC verificados sobre los bytes reales.
- [ ] Restauración del archivo real **completada** en PG18 descartable.
- [ ] Validación de conteos y migración/rollback sobre la copia real.
- [ ] Autorización separada para cualquier migración productiva/flags o
      investigación de un fabricante real.

**La cola reanudable no queda habilitada al fusionar estas pruebas**.
Su activación futura sigue requiriendo configuración, dominios/robots,
identidad, cuotas y permisos explícitos. PR de seguridad != lanzamiento.
