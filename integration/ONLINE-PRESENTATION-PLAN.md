# Presentación por Chrome: opción preparada, sin despliegue

Estado al 12/11/2026: **no hay enlace nuevo al backend conectado**. No se creó ningún servicio, puerto público, túnel, credencial, dominio ni despliegue. El usuario confirmó que su interfaz de Codex no ofrece Desktop. Las capturas automatizadas se obtienen con Chromium dentro del entorno; eso no publica la aplicación.

## Lo que se puede abrir ahora

La URL facilitada por el usuario, <https://kiki-tech-2-demo.onrender.com>, corresponde a una **demostración visual estática con datos ficticios** de una versión publicada anteriormente. No se actualizó con este trabajo. Este entorno recibió un rechazo del proxy (CONNECT 403) al intentar verificar sus encabezados; no se puede concluir que el sitio esté caído.

El build estático preparado aquí permite cinco vistas comerciales, filtros, las cinco pestañas y edición del formulario original en memoria. Sus operaciones y trabajos son simulados. No usa PostgreSQL ni investigación u OpenAI reales. Compartir ese enlace no demuestra que ya estén publicados estos cambios.

## Opción mínima para la versión conectada (requiere autorización)

Reutilizar el arnés actual en **un único host Linux independiente y temporal**, existente si está disponible, con Docker. El usuario y Guillermo sólo necesitan Chrome. No utilizar los servicios `kiki-tech-api`, `kiki-tech-web`, el Blueprint ni PostgreSQL de producción. No crear un segundo backend comercial: ejecutar la misma imagen FastAPI y el mismo PostgreSQL descartable ya probados.

Arquitectura propuesta:

```text
Chrome → HTTPS con certificado válido → proxy de entrada del host aislado
       → pasarela local (TLS loopback y rutas permitidas)
       → socket Unix de FastAPI existente → socket Unix PostgreSQL de pruebas
       → lector/recolector sin red y ejecutor editorial existentes
```

El proxy sería el único punto de entrada. PostgreSQL y los contenedores mantienen `network_mode: none`, sin puertos, credenciales productivas ni salida a proveedores. Documentos y datos exclusivamente de demostración; Hileret conserva su PDF original público y un expediente de prueba, nunca un Ecomm ID inventado. Sesiones aisladas del sitio KIKI productivo. Sin acceso del público a documentos ajenos ni a operaciones de sincronización.

**No basta copiar compose.yaml a Render o cambiar una variable.** El frontend conectado, la pasarela y las cookies validan un origen literal de loopback. Antes de publicar hay que preparar una adaptación explícita al único dominio HTTPS elegido, conservar defaults cerrados y probar:

1. Host, origen y CSRF correctos; rechazo de otros dominios, forwarded headers no confiables y redirecciones.
2. Login propio del entorno temporal, cookies Secure/HttpOnly/SameSite, cierre de sesiones y protección de entrada. Los usuarios/contraseñas públicos de las pruebas locales no deben ser el acceso público del sitio temporal.
3. CSP, límites de cuerpos/tiempo y rutas de la pasarela; exportación autenticada. PostgreSQL y servicios internos sin publicación de puertos.
4. Negación de Internet en backend/lector/recolector y de imágenes externas en Chrome; ninguna variable o fichero de producción montado.
5. Recuperación/reinicio del ejecutor, persistencia temporal y política de borrado. El PostgreSQL actual es descartable: retirar el contenedor elimina sus datos.
6. Recorrido de aceptación desde Chrome externo, escritorio/celular, sin instalar nada en Windows.

No se implementó una excepción al origen ni se desactivaron las protecciones para simular que este alojamiento ya está disponible.

## Decisiones necesarias antes de ejecutar

- Autorizar **host y dominio HTTPS concretos**, duración y eventual costo. Si no existe un host independiente, autorizar su creación con presupuesto explícito; no hay alta automática de servicios.
- Autorizar publicación del commit de desarrollo y despliegue **sólo de la demostración independiente**. La autorización anterior de push para `7b903eee` no publica estos cambios.
- Autorizar la configuración de acceso temporal por un canal seguro, sin reutilizar credenciales productivas ni pegarlas en documentación.
- Revisar la adaptación de origen y el acceso externo contra las pruebas anteriores. Después entregar una URL probada; hasta entonces no prometer un enlace funcional a la aplicación conectada.

No requiere instalar WSL o Docker en la computadora de Guillermo. Docker corresponde al host independiente, administrado separadamente. Render puede seguir alojando el demo estático actual sin modificar producción; no se propone crear servicios Render sin permiso.

## Recorrido preparado para el host aislado

El mismo escenario local se inicia con `python3 integration/run.py build` y `python3 integration/run.py up --presentation`, accediendo **desde el propio host** a `https://127.0.0.1:8443`. Ese localhost no es accesible desde Windows remoto. Login y confianza del certificado local están documentados en `integration/PRESENTACION-GUILLERMO.md`; no se utilizan como un acceso público.

Para la presentación online conectada se autorizará primero la adaptación anterior. Como alternativa inmediata sigue disponible el demo estático previamente publicado, con sus limitaciones claramente visibles.
