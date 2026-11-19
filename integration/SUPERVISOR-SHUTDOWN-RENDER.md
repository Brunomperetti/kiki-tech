# KIKI Tech 2.0 — corrección del apagado del supervisor (19/11/2026)

## Incidencia real en Render

El 19/11, a las 13:32:34 UTC, el servicio `kiki-tech-api` registró
`PermissionError: [Errno 1] Operation not permitted` en
`/app/start.py`, al intentar `terminate()` sobre un proceso de otro UID.
El servicio conserva dos dominios: API UID 10000 y lector aislado UID
10001 bajo chroot/seccomp. En producción no se debe exigir `CAP_KILL`.

## Reparación de código (pendiente de despliegue)

- Los launchers registran `PR_SET_PDEATHSIG=SIGTERM` **después** del
  cambio de UID: el kernel avisa al hijo cuando muere el supervisor. El
  proceso exige el PID padre esperado y falla cerrado si el supervisor
  desapareció o el kernel no permite registrar el mecanismo.
- El supervisor mantiene un cierre normal por señales cuando tiene
  permiso. Si no puede señalar a otro UID, no lanza traceback ni se
  queda esperando sobre ese proceso: salir hace que el kernel entregue
  SIGTERM al hijo protegido. No rebaja la separación de usuarios, no
  ejecuta lector dentro de API y no pide capacidades privilegiadas.
- Si el lector no supera su chequeo inicial y tampoco puede detenerse,
  el supervisor aborta el arranque, en lugar de exponer un lector fuera
  de control. La salida del supervisor activa el mismo resguardo.
- El launcher API continúa usando Uvicorn y la configuración previa.
  El lector conserva chroot, seccomp y entorno restringido.

## Verificaciones necesarias antes de aprobar merge/despliegue

1. CI backend, frontend y PostgreSQL 18 en verde.
2. Revisar diff y confirmar que Docker utiliza `python /app/start.py`.
3. Ensayar imagen productiva **sin CAP_KILL** en contenedor aislado:
   arranque, `/health`, socket del lector, SIGTERM del supervisor y
   ausencia de hijos supervivientes o `PermissionError`.
4. Repetir con `KIKI_DOCUMENT_PARSER_ENABLED=false` para asegurar
   continuidad de API; no consultar proveedores, IA ni clientes.
5. Antes de desplegar, respaldo auténtico restaurado en un entorno
   separado; verificaciones de compatibilidad, rollback de artefacto y
   servicios con auto-deploy apagado.
6. Fusionar y desplegar solo con permisos explícitos y separados.

**Esto no autoriza una migración PostgreSQL, un deploy ni cambios a
Render, Ecomm-App, Tiendanube, Mercado Libre o variables de entorno.**
