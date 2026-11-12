import { captureDate } from "./catalog-adapter";
import type { ConnectionStatus } from "./connections";
import "./connections.css";

export function ConnectionCenter({
  data,
  demo = false,
  error,
  message,
  busy = "",
  refreshSuggested = false,
  onOperate,
  onReload,
  onRefresh,
  refreshBlocked = false,
}: {
  data?: ConnectionStatus;
  demo?: boolean;
  error?: string;
  message?: string;
  busy?: string;
  refreshSuggested?: boolean;
  refreshBlocked?: boolean;
  onOperate?: (kind: "ecomm" | "ml" | "oauth" | "tn", file?: File) => void;
  onReload?: () => void;
  onRefresh?: () => void;
}) {
  const enabled = !demo && !!data?.actions_enabled && !!onOperate;
  const e = data?.ecomm,
    ml = data?.ml,
    tn = data?.tn;
  const count = (v?: number | null) =>
    v == null ? "—" : v.toLocaleString("es-AR");
  return (
    <section className="n-center" aria-label="Centro de conexiones">
      <h3>Centro de conexiones</h3>
      <p className="n-notice">
        {demo
          ? "Ejemplos sintéticos de la demo pública. No hay credenciales, tareas programadas ni conexiones reales. Las acciones están deshabilitadas."
          : "Estado registrado en FastAPI de pruebas y PostgreSQL descartable. No se consulta ningún proveedor para mostrar estas tarjetas. Las operaciones usan únicamente dobles locales."}
      </p>
      {!demo && !data && !error && <p role="status">Consultando conexiones…</p>}
      {!demo && data && !data.actions_enabled && (
        <p className="n-notice">
          Acciones bloqueadas en este entorno aislado. Para probarlas se
          requiere el escenario explícito de conexiones con transportes
          sintéticos; no se habilitan proveedores reales.
        </p>
      )}
      {error && (
        <p role="alert" className="n-error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="n-notice">
          {message}
        </p>
      )}
      <div className="n-cards">
        <article aria-label="Conexión Ecomm-App">
          <h4>Ecomm-App</h4>
          <strong className="n-state">
            {demo
              ? "Captura de ejemplo"
              : !e
                ? "Estado no disponible"
                : e.api_configured
                  ? "Lectura API configurada"
                  : "Sin credencial configurada"}
          </strong>
          <p>
            La configuración no acredita por sí sola que la autorización siga
            vigente. No es inventario en vivo.
          </p>
          <dl>
            <dt>Última captura completa</dt>
            <dd>
              {e?.last_successful_complete
                ? captureDate(e.last_successful_capture_at)
                : "Sin captura completa acreditada"}
            </dd>
            <dt>Variantes de la captura</dt>
            <dd>
              {e?.last_successful_complete
                ? count(e.last_successful_variants)
                : "—"}
            </dd>
            <dt>Actualización</dt>
            <dd>
              {busy === "ecomm"
                ? "Solicitando actualización…"
                : e?.refresh_in_progress
                  ? "Actualización en curso"
                  : e?.refresh_job?.status === "FAILED"
                    ? "Error de captura"
                    : e?.refresh_job?.status === "INTERRUPTED"
                      ? "Actualización interrumpida"
                      : e?.refresh_job?.status === "SUCCESS"
                        ? "Última actualización exitosa"
                        : "Sin actualización en curso acreditada"}
            </dd>
          </dl>
          {e?.refresh_job && (
            <div role="status">
              <p>{e.refresh_job.message}</p>
              <p>
                {e.refresh_job.pages_saved} páginas de{" "}
                {e.refresh_job.expected_pages ?? "cantidad por confirmar"} ·{" "}
                {e.refresh_job.origin === "SCHEDULED"
                  ? "Proceso programado"
                  : "Proceso manual"}
              </p>
            </div>
          )}
          <button
            className="d-primary"
            disabled={
              !enabled || !!busy || !e?.api_configured || e.refresh_in_progress
            }
            onClick={() => onOperate?.("ecomm")}
          >
            Actualizar catálogo ahora
          </button>
          <details>
            <summary>Actualizaciones programadas</summary>
            <p>
              Workflow existente: 08:25 y 16:25, hora argentina.{" "}
              {demo
                ? "No se ejecuta en la demo."
                : e?.configured
                  ? "Credencial de programación configurada."
                  : "La configuración de la credencial programada no está acreditada."}
            </p>
            <p>
              Próximos horarios previstos, sujetos a habilitación y
              disponibilidad de GitHub Actions:
            </p>
            <ul>
              {e?.next_updates.map((date) => (
                <li key={date}>
                  {new Date(date).toLocaleString("es-AR", {
                    timeZone: "America/Argentina/Buenos_Aires",
                    hour12: false,
                  })}{" "}
                  (Argentina)
                </li>
              ))}
            </ul>
            <small>
              El estado de activación del workflow no se consulta en GitHub
              desde este centro. Los horarios no garantizan ejecución puntual.
            </small>
          </details>
          <small>
            Comparte el bloqueo con el proceso programado. La copia anterior se
            conserva ante errores y las fichas internas permanecen separadas.
          </small>
        </article>
        <article aria-label="Conexión Mercado Libre">
          <h4>Mercado Libre</h4>
          <strong className="n-state">
            {demo
              ? "Cuenta de ejemplo · sin OAuth real"
              : !ml
                ? "Estado no disponible"
                : !ml.connected
                  ? "Sin cuenta conectada"
                  : ml.token_expired
                    ? "Token de acceso vencido"
                    : "Cuenta vinculada · autorización registrada"}
          </strong>
          <dl>
            <dt>Cuenta vinculada</dt>
            <dd>{ml?.user_id || "Sin cuenta acreditada"}</dd>
            <dt>Vencimiento registrado</dt>
            <dd>{captureDate(ml?.token_expiration ?? null)}</dd>
            <dt>Última captura</dt>
            <dd>{captureDate(ml?.last_sync ?? null)}</dd>
            <dt>Publicaciones distintas en la captura</dt>
            <dd>{count(ml?.publication_count)}</dd>
            <dt>Filas registradas (incluye variantes)</dt>
            <dd>{count(ml?.listing_count)}</dd>
          </dl>
          <p>
            Estado de la autorización guardada, sin verificarla en vivo.{" "}
            {ml?.token_expired &&
              "El servicio existente puede renovarla al actualizar; no exige una reconexión automática."}
          </p>
          <button
            className="d-primary"
            disabled={!enabled || !!busy || !ml?.connected}
            onClick={() => onOperate?.("ml")}
          >
            {busy === "ml"
              ? "Leyendo publicaciones…"
              : "Actualizar publicaciones"}
          </button>
          {ml?.connected && !ml.token_expired ? (
            <details>
              <summary>Opciones de autorización</summary>
              <p>
                Ya hay una cuenta vinculada. No necesitás autorizarla nuevamente
                para consultar la captura.
              </p>
              <button
                disabled={!enabled || !!busy}
                onClick={() => onOperate?.("oauth")}
              >
                Reconectar Mercado Libre
              </button>
            </details>
          ) : (
            <button
              disabled={!enabled || !!busy || !ml}
              onClick={() => onOperate?.("oauth")}
            >
              {ml?.connected
                ? "Reconectar Mercado Libre"
                : "Conectar Mercado Libre"}
            </button>
          )}
          <small>
            OAuth externo bloqueado en el entorno de pruebas: preparar la
            solicitud no conecta una cuenta. Actualizar lee y guarda una copia
            interna; no publica, pausa ni modifica productos.
          </small>
        </article>
        <article aria-label="Importación Tiendanube">
          <h4>Tiendanube</h4>
          <strong className="n-state">
            {demo
              ? "CSV de ejemplo"
              : !tn
                ? "Estado no disponible"
                : tn.available
                  ? "CSV importado en KIKI"
                  : "Sin CSV importado"}
          </strong>
          <dl>
            <dt>Última importación</dt>
            <dd>{captureDate(tn?.imported_at ?? null)}</dd>
            <dt>Productos del CSV</dt>
            <dd>{count(tn?.products)}</dd>
            <dt>Registros del CSV</dt>
            <dd>{count(tn?.records)}</dd>
          </dl>
          <p>
            El CSV acredita una importación pasada, no que el producto siga
            publicado hoy. No es una conexión API activa.
          </p>
          <label className="n-upload">
            <span>Importar / Actualizar CSV de Tiendanube</span>
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={!enabled || !!busy || !tn}
              aria-label="Importar / Actualizar CSV de Tiendanube"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onOperate?.("tn", file);
                event.target.value = "";
              }}
            />
          </label>
          <small>
            {data ? `Máximo ${data.max_csv_bytes / 1024 / 1024} MB. ` : ""}Se
            reutiliza el importador CSV existente. No se vinculan variantes
            automáticamente.
          </small>
          <p>
            API directa: funcionalidad futura, pendiente de autorización. Sin
            acción de conexión disponible.
          </p>
        </article>
      </div>
      {!demo && (
        <div className="n-footer">
          <button disabled={!!busy} onClick={onReload}>
            Volver a consultar estados
          </button>
          {refreshSuggested && (
            <>
              <p>
                Nueva copia disponible. Podés actualizar esta vista cuando
                termines de editar.
              </p>
              <button
                className="d-primary"
                disabled={refreshBlocked || !!busy}
                onClick={onRefresh}
              >
                Refrescar indicadores y tabla
              </button>
              {refreshBlocked && (
                <p>
                  Guardá o descartá los cambios de la ficha antes de refrescar.
                </p>
              )}
            </>
          )}
        </div>
      )}
      <p>
        Publicado con evidencia, sin confirmación, preparado internamente,
        revisión y conflicto de identidad siguen siendo estados diferentes. Un
        error de sincronización no demuestra un intento ni un error de
        publicación.
      </p>
    </section>
  );
}
