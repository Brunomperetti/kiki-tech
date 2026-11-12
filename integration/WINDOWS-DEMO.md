# Abrir KIKI Tech 2.0 y presentar el recorrido

## Obtener los archivos actuales

Hace falta el commit local de cierre, no la versión antigua de la rama remota.
La distribución más directa es un push de `feature/kiki-tech-2-dashboard`, **sólo
después de nueva autorización**. No se ejecutó como parte de este cierre.

Después de que esa publicación esté autorizada y realizada, desde WSL2, en un checkout de
desarrollo separado (no el que usa KIKI) se podrá ejecutar:

```bash
git clone --branch feature/kiki-tech-2-dashboard https://github.com/Brunomperetti/kiki-tech.git kiki-tech-demo
cd kiki-tech-demo
git log -1 --oneline
git status --short
```

Verificar contra el commit de cierre informado en la entrega. No reutilizar una
carpeta productiva ni copiar `.env`, tokens, backups o bases reales.

## Windows con WSL2 y Docker Desktop

Requisitos: Windows con WSL2/Ubuntu y Docker Desktop en modo contenedores Linux,
integración WSL activada, usuario Linux UID **1000**, Python **3.11+**, Node **22+**,
npm y Compose v2. Trabajar en el filesystem Linux, por ejemplo `~/kiki-tech-demo`.
No es un inicio nativo desde PowerShell. No cambiar permisos ni el destino Docker
para eludir las guardas. El equipo necesita Internet para paquetes/imágenes durante
la preparación; los procesos de la aplicación quedan sin red a proveedores.

En la terminal WSL:

```bash
id -u
python3 --version
node --version
docker --host=unix:///var/run/docker.sock info --format '{{.ServerVersion}}'
docker --host=unix:///var/run/docker.sock compose version
cd frontend
npm ci
cd ..
python3 integration/run.py build
python3 integration/run.py up --presentation
```

No cargar variables de producción. El runner usa un entorno limpio, archivo Compose
fijo y `--env-file /dev/null`; rechaza destinos alternativos. Esperar al mensaje
de presentación preparada y al gateway. Mantener esa terminal abierta. La URL es
**https://127.0.0.1:8443/** en esa máquina, no `localhost:5173` de Codex.

Otra terminal WSL permite comprobar TLS y salud sin desactivarlos:

```bash
curl --cacert .integration-runtime/api/tls-cert.pem https://127.0.0.1:8443/health
python3 integration/run.py status
```

El certificado local dura dos días y se renueva al iniciar. Para Edge/Chrome de
Windows confiar explícitamente en **ese certificado público local**, nunca en una
clave privada ni desactivando TLS. Copiar sólo `tls-cert.pem` a Descargas como
`kiki-demo.cer`. Desde WSL usar la ruta real de tu usuario Windows:

```bash
cp .integration-runtime/api/tls-cert.pem /mnt/c/Users/TU_USUARIO/Downloads/kiki-demo.cer
```

En PowerShell, para el usuario actual (sin permisos de administrador):

```powershell
$kikiDemoCert = Import-Certificate -FilePath "$env:USERPROFILE\Downloads\kiki-demo.cer" -CertStoreLocation Cert:\CurrentUser\Root
$kikiDemoCert.Thumbprint
Test-NetConnection 127.0.0.1 -Port 8443
Start-Process 'https://127.0.0.1:8443/'
```

Al terminar, retirar únicamente ese certificado temporal por su huella:

```powershell
Remove-Item ("Cert:\CurrentUser\Root\" + $kikiDemoCert.Thumbprint)
```

No se comprobó Windows desde Codex. Se requiere el reenvío localhost estándar de
WSL2; si la comprobación WSL funciona y `Test-NetConnection` falla, el bloqueo es
ese acceso Windows↔WSL. No abrir puertos públicos ni cambiar el gateway a 0.0.0.0.

Acceso de prueba: **operador-prueba / solo-datos-sinteticos**. Son credenciales
públicas exclusivamente sintéticas, sin cuenta o sesión productiva.

## Guion de 10 minutos

1. Identificar el aviso de entorno aislado. Los seis productos son inventados.
2. Buscar `DEMO-CHIA`; abrir Semillas de chía, Ecomm ID `900003`. Revisar los
   18 campos de Ficha y la separación de datos de captura y datos editados.
3. En Evidencias, leer el documento sintético ya incorporado, hash y citas.
   Escribir motivo y revisar procedencia; extraer/revisar los hechos uno por uno.
   No aprobar ingredientes, alérgenos o nutrición: el documento no los contiene.
4. En IA, **Generar propuesta de prueba**. Es determinista, no OpenAI real.
   Comparar título, descripción, características y SEO; desplegar sus citas.
   Aceptar algunos campos, rechazar otro y registrar la revisión individual.
5. Guardar la selección en la ficha con confirmación. Recargar y recuperar los
   cambios; comprobar Historial y versiones. No se publica nada.
6. En IA, desplegar Preparación avanzada y consultar el servicio OpenAI existente:
   estado y cuota de sólo lectura. La generación paga permanece bloqueada.
7. En Canales, distinguir candidatos, decisiones históricas y CSV desactualizado.
   Los packs x2/x6 conservan Ecomm IDs propios; compartir SKU/EAN no los fusiona.
8. Cerrar la ficha, seleccionar la variante, abrir Operaciones, elegir tareas de
   revisión, previsualizar y confirmar el lote. Cerrar/reabrir el panel para
   recuperar el resultado. La tarea no guarda ni aprueba automáticamente una ficha.
9. Abrir el piloto Hileret y el documento PDF disponible. Comprobar página 2, EAN
   `7794940000796`, DUN `97794940000799`, unidad 200 ml, pack x6 pendiente y caja x9
   logística. Es auténtico, pero su incorporación no aprueba hechos ni resuelve el
   Ecomm ID real. MAMA continúa como caso de documentación insuficiente.
10. Explicar las tareas por revisión cada 30 días; los filtros pueden tener cero
    resultados en una base recién iniciada. No fingir revisiones vencidas.

## Persistencia, errores y apagado

Guardar/recargar y cerrar/reabrir el navegador conserva datos mientras la demo
está activa. Un conflicto 409 requiere recuperar/comparar versiones; no sobrescribir.
Una fuente sin revisar o sin evidencia bloquea propuestas; no completarla a mano
como si estuviera verificada. Un 401 requiere volver a ingresar, sin usar cuentas reales.

Ctrl+C en la terminal de inicio detiene el proyecto y elimina PostgreSQL descartable.
El siguiente inicio reproduce el escenario limpio, no recupera los datos borrados.
No ejecutar tests en paralelo con la demo: usan el mismo proyecto y lo eliminan.
No se promete persistencia entre apagados completos ni restauración de este escenario
si se reinicia manualmente sólo el backend. No introducir datos reales para conservarlos.

Si Docker no inicia o el UID no es 1000, corregir la instalación WSL/Docker y detener
la demostración; no quitar controles. Si el puerto 8443 está ocupado, detener sólo
la instancia local de esta demo. Para conexión rechazada comprobar primero el proceso
WSL, `/health`, la terminal de errores y luego el reenvío Windows; no usar la URL de Render.

## Diagnóstico del acceso cloud

Entorno observado: `ccarenv_b64_Y2NhcmVudl9lZjEyZDliODk2ZGM4MTkxODE1NWEyZTdkMDU1M2ZlYg`.
Desktop figura habilitado con estado desconocido; no se ofrecieron `cua_repl.js`,
`open_in_codex` ni herramientas de publicación de puertos. Si la interfaz permite
**New tab (+) → Desktop**, ese visor puede conectarse por acción del usuario, pero
no se verificó su disponibilidad interactiva en esta entrega. No se creó un túnel
externo ni se ofrece el loopback remoto como enlace accesible desde Windows.
