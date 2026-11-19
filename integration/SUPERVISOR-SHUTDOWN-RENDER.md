# KIKI Tech 2.0 — apagado seguro de API + lector en Render

## Incidencia observada
El 19/11/2026, 13:32:34 UTC, `kiki-tech-api` produjo
`PermissionError: [Errno 1] Operation not permitted` en
`/app/start.py` al intentar `terminate()` sobre otro UID.
El supervisor es **PID 1**, la API usa UID 10000 y el lector
UID 10001 bajo chroot/seccomp. No se debe habilitar `CAP_KILL`.

## Solución segura (PR #195)
1. El supervisor crea un **pipe anónimo heredado por cada hijo** y
   conserva el extremo de escritura. El hijo recibe solamente el FD
   de lectura y el PID esperado del supervisor.
2. Al recibir SIGTERM, el supervisor cierra **ambos** escritores y
   **permanece como PID 1** mientras cada hijo finaliza.
3. Los hilos de vigilancia de API y lector detectan EOF y se envían
   SIGTERM **a sí mismos** (permitido entre el mismo UID).
4. La API ejecuta Uvicorn en el mismo proceso del vigilante, de modo
   que se cumple su `lifespan` normal y `stop_executor()` puede
   cerrar tareas. El lector puede liberar su socket Unix ordenadamente.
5. Como protección de caída *imprevista* del padre, ambos siguen
   armando `PR_SET_PDEATHSIG=SIGTERM` **después** de `setuid` y
   rechazan supervisores incorrectos.
6. Si un hijo no sale en el plazo de cierre, se registra una alerta;
   nunca se agregan permisos privilegiados ni se escriben datos externos.

Esta distinción es esencial: **PDEATHSIG por sí solo no basta cuando
muere PID 1 del namespace**; Linux puede terminar bruscamente los
procesos restantes. Por eso el protocolo cooperativo por pipe ocurre
antes del fin del supervisor.

## Pruebas y criterios de aceptación
- CI backend y frontend, suite PostgreSQL 18 aislada.
- Build del Dockerfile productivo real con `backend/.dockerignore`
  que contiene ambos launchers.
- Arranque sin `CAP_KILL`, `--network none`, sin credenciales ni
  conexión a proveedor, API `/health=200` y lector seccomp válido.
- Al hacer `docker stop`, exigir **ambos** marcadores: Uvicorn
  `Application shutdown complete` y lector
  `KIKI_READER_SHUTDOWN_COMPLETE`. No aceptar un exit 0 sin esas
  evidencias (error detectado en revisión de Codex).
- Verificar modo sin lector, aislamiento, sesiones, versión, rollback
  y ausencia de tareas de captura antes de cualquier despliegue.

## Limitación
Las pruebas de imagen Docker no prueban por sí mismas la configuración
exacta de toda la plataforma Render ni una aplicación autenticada.
**No autoriza fusión, despliegue, flags, migración, proveedores ni
publicación de productos.**
