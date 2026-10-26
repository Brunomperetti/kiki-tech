# KIKI Tech — renovación automática del catálogo Ecomm-App por API

## Objetivo
El usuario no necesita pulsar «Consultar API» por cada variante. La fuente
única de Ecomm-App es la API oficial de lectura. No se admite XLSX.

## Funcionamiento
- El workflow de GitHub Actions `.github/workflows/ecomm-api-refresh.yml`
  ejecuta dos capturas completas cada día a las 11:25 y 19:25 UTC
  (08:25 y 16:25 de Argentina, UTC-3). GitHub puede retrasar los eventos
  programados, por lo que el intervalo no es una garantía de ejecución.
- Se usa `GET /api/v3/public/inventario/productos` con paginación de 50
  productos/página, tres páginas por paso.
- `POST /api/ecomm-app/stage/auto/start` deja vacía SOLO la captura
  provisional `ECOMM_APP_API_REFRESH`, no la vigente.
- `POST /api/ecomm-app/stage/auto/step` trae y valida tres páginas. Cuando
  se comprueba el último bloque y las variantes conservan IDs seguros,
  se publica la copia COMPLETA como `ECOMM_APP_API_STAGE` **en la misma
  transacción**, sin ninguna copia parcial visible al usuario.
- Si falla la API, cambia la paginación, hay IDs duplicados o faltantes,
  queda intacto `ECOMM_APP_API_STAGE` y los datos comerciales
  en `ecomm_api_product_edits`.
- Es **captura programada, no stock en tiempo real** ni sincronización
  de Mercado Libre/Tiendanube. No hay operación de escritura en
  Ecomm-App ni publicación.
- Si el SKU de un ID de variante cambia, el editor existente evita
  guardar silenciosamente con la identidad anterior.
- En «Catálogo por API» se muestra fecha de captura, si hay una nueva
  captura en curso y si la programación está configurada. Desaparece
  el botón individual «Consultar API» del listado operativo.
- El operador autenticado puede usar «Actualizar catálogo ahora» (con CSRF
  y confirmación). La tarea continúa en el backend y la UI lee el progreso
  guardado en PostgreSQL, aun si se cierra la pestaña.
- Actualización manual y programada comparten un bloqueo persistente.
  La nueva captura sustituye la vigente solamente después de validarse
  completa. Las fichas y borradores editoriales permanecen separados.
  Ante un fallo o reinicio del proceso, se mantiene la última copia válida;
  una tarea interrumpida puede reiniciarse pasados 45 minutos.

## Configuración obligatoria (no incluida automáticamente en el despliegue)
1. Crear **una clave aleatoria de al menos 32 caracteres**, diferente del
   token de Ecomm-App y de las contraseñas de los operadores.
2. Guardar el MISMO valor como `KIKI_REFRESH_TOKEN` en:
   - Render → `kiki-tech-api` → Environment
   - GitHub → repositorio KIKI → Settings → Secrets and variables →
     Actions → New repository secret.
3. Confirmar que Render ya tiene `ECOMM_APP_API_TOKEN` válido y que
   `kiki-tech-api` está correctamente enlazado a PostgreSQL persistente.
4. Guardar y desplegar `kiki-tech-api`, y desplegar el frontend.
5. En GitHub → Actions → «Ecomm-App — renovación automática del catálogo API»
   → Run workflow: ejecutar UNA vez manualmente para comprobar que termina
   en «Catálogo API actualizado». La activación inicial del cron no se
   considera operativa hasta completar esta verificación.
6. Abrir el catálogo y revisar la fecha nueva y la cantidad de variantes;
   corroborar también un borrador previamente guardado.
7. Revisar el histórico de ejecuciones de GitHub Actions y su resultado
   periódicamente. Los cron pueden retrasarse y Render free puede dormirse;
   si no termina el job, se sigue mostrando la copia previa.

## Riesgos y pasos antes de dar acceso operativo
- **Respaldos**: verificar un backup recuperable de PostgreSQL y una prueba
  de restauración. Esto no lo cubre la nueva sincronización y es obligatorio
  antes de que múltiples personas editen durante varios días.
- **Cuentas y roles**: el actual login administrativo puede ser compartido.
  Antes del uso multioperador auditado se recomiendan cuentas por operador
  con roles y usuario identificado en el historial.
- **Origen comercial**: el endpoint autorizado es `inventario:leer`,
  no incluye necesariamente precios, costos, marcas ni GTIN. No inferirlos.
- **Publicación**: guardar borradores es interno KIKI; no modifica
  Ecomm-App, Mercado Libre ni Tiendanube.
- **Frecuencia**: respetar cuota del proveedor y coste/ejecuciones antes
  de subir a capturas horarias; hoy se limita a dos por día.

## Actualización manual desde la interfaz
1. En `/pilot` pulsar **Actualizar catálogo ahora** y confirmar.
2. El backend crea un trabajo registrado en PostgreSQL; obtiene tres páginas
   por lote y publica la copia únicamente al completar todas las páginas.
3. El navegador consulta periódicamente `/api/ecomm-app/stage/auto/status`,
   mostrando páginas y resultado. Salir de la página no cancela el trabajo
   mientras el proceso backend siga en ejecución.
4. Si hay otra captura en curso (manual o programada), el servidor responde
   HTTP 409 y NO inicia una segunda copia.
5. Si el backend se reinicia, la tarea puede quedar interrumpida. La copia
   anterior no se reemplaza. Luego del plazo de seguridad se puede reintentar.
6. Verificar la fecha y cantidad de variantes, y corroborar que el borrador
   guardado continúa intacto. No modifica Ecomm, Mercado Libre ni Tiendanube.
