import { useEffect, useRef, useState } from "react";
import { canWrite, production, capabilities } from "./runtime";
import { captureDate, request } from "./catalog-adapter";

type RefreshJob = {
  status: "RUNNING" | "SUCCESS" | "FAILED" | "INTERRUPTED";
  origin: "MANUAL" | "SCHEDULED";
  pages_saved: number;
  expected_pages: number | null;
  message: string;
};
type RefreshState = {
  mode: "SCHEDULED_AND_MANUAL_API_ONLY";
  last_successful_complete: boolean;
  last_successful_capture_at: string | null;
  last_successful_variants: number;
  refresh_in_progress: boolean;
  refresh_job: RefreshJob | null;
  external_writes_enabled: false;
};

function parseStatus(input: unknown): RefreshState {
  const state = input as RefreshState | undefined;
  const job = state?.refresh_job;
  const integer = (value: unknown): value is number =>
    Number.isSafeInteger(value) && (value as number) >= 0;
  if (
    !state ||
    state.mode !== "SCHEDULED_AND_MANUAL_API_ONLY" ||
    state.external_writes_enabled !== false ||
    typeof state.last_successful_complete !== "boolean" ||
    typeof state.refresh_in_progress !== "boolean" ||
    !integer(state.last_successful_variants) ||
    !(
      state.last_successful_capture_at === null ||
      (typeof state.last_successful_capture_at === "string" &&
        Number.isFinite(Date.parse(state.last_successful_capture_at)))
    ) ||
    (job !== null && (
      !job ||
      !["RUNNING", "SUCCESS", "FAILED", "INTERRUPTED"].includes(job.status) ||
      !["MANUAL", "SCHEDULED"].includes(job.origin) ||
      !integer(job.pages_saved) ||
      !(job.expected_pages === null || integer(job.expected_pages)) ||
      typeof job.message !== "string"
    )) ||
    state.refresh_in_progress !== (job?.status === "RUNNING")
  )
    throw new Error("Estado de actualización incompatible; operación bloqueada.");
  return state;
}

function newerCapture(a: string | null, b?: string | null): boolean {
  if (!a) return false;
  const newer = Date.parse(a);
  if (!Number.isFinite(newer)) return false;
  // An absent or failed initial catalogue load is not evidence that the
  // latest completed snapshot has already been rendered in the table.
  if (!b || !Number.isFinite(Date.parse(b))) return true;
  return newer > Date.parse(b);
}

export function EcommManualRefresh({
  csrf,
  actionsAllowed,
  displayedCaptureAt,
  editing,
  onReload,
}: {
  csrf: string;
  actionsAllowed: boolean;
  displayedCaptureAt?: string | null;
  editing: boolean;
  onReload: () => void;
}) {
  const [state, setState] = useState<RefreshState>();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const startingRef = useRef(false);
  const permitted = actionsAllowed && canWrite() && (!production || capabilities?.connections === true);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    async function poll() {
      controller = new AbortController();
      let interval = 15000;
      try {
        const response = await request("/api/ecomm-app/stage/auto/status", {
          signal: controller.signal,
        });
        const next = parseStatus(await response.json());
        if (!active) return;
        setState(next);
        setError("");
        if (next.refresh_in_progress) interval = 2500;
      } catch (exc) {
        if (active && (exc as Error).name !== "AbortError") {
          setState(undefined); // Never enable the button with untrusted status.
          setError((exc as Error).message);
        }
      } finally {
        if (active) timer = setTimeout(poll, interval);
      }
    }
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [csrf]);

  async function start() {
    if (startingRef.current || !state || state.refresh_in_progress || !permitted)
      return;
    if (!window.confirm(
      "¿Actualizar ahora el catálogo desde Ecomm-App? Se consultará la API real y se renovará la copia interna únicamente al finalizar. Las fichas editadas se conservarán; si hay otra actualización en curso, no se iniciará una segunda."
    )) return;
    startingRef.current = true;
    setStarting(true);
    setError("");
    setNotice("");
    try {
      const response = await request("/api/ecomm-app/stage/manual/start", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
      });
      const result = await response.json() as {
        status?: string;
        external_writes_enabled?: boolean;
      };
      if (result.status !== "RUNNING" || result.external_writes_enabled !== false)
        throw new Error("El servidor no confirmó un inicio seguro.");
      setNotice("Actualización solicitada. Podés seguir trabajando; la copia anterior permanece disponible.");
      // Both automatic and manual triggers share the same server-side lock.
      // Show a provisional in-progress state until the next validated GET.
      setState(prev => prev ? {
        ...prev, refresh_in_progress: true,
        refresh_job: {
          status: "RUNNING", origin: "MANUAL",
          pages_saved: 0, expected_pages: null,
          message: "Iniciando captura completa por API.",
        },
      } : prev);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      startingRef.current = false;
      setStarting(false);
    }
  }

  const running = state?.refresh_in_progress === true;
  const updated = state?.last_successful_complete &&
    newerCapture(state.last_successful_capture_at, displayedCaptureAt);

  return (
    <section className="i-ecomm-refresh" aria-label="Actualización de Ecomm-App">
      <div className="i-ecomm-refresh-main">
        <button
          type="button"
          className="d-primary"
          disabled={!state || !permitted || starting || running}
          onClick={() => void start()}
        >
          {starting ? "Solicitando actualización…" :
            running ? "Ecomm-App actualizando…" : "Actualizar desde Ecomm-App"}
        </button>
        <small>Automática: 08:25 y 16:25 (Argentina) · Manual cuando necesites</small>
      </div>
      {!permitted && (
        <p role="status">
          Actualización manual no habilitada para esta interfaz.
          Se respetan los permisos de Conexiones y edición de KIKI.
        </p>
      )}
      {running && state?.refresh_job && (
        <p role="status">
          {state.refresh_job.origin === "SCHEDULED"
            ? "Actualización programada"
            : "Actualización manual"} en curso:{" "}
          {state.refresh_job.pages_saved}/
          {state.refresh_job.expected_pages ?? "?"} páginas.
          La copia anterior sigue disponible.
        </p>
      )}
      {!running && state?.refresh_job?.status === "SUCCESS" && (
        <p role="status">
          Última actualización completada:{" "}
          {captureDate(state.last_successful_capture_at)}.
        </p>
      )}
      {!running && ["FAILED", "INTERRUPTED"].includes(state?.refresh_job?.status ?? "") && (
        <p role="alert">{state?.refresh_job?.message} La captura anterior se conserva.</p>
      )}
      {updated && (
        <div className="i-ecomm-refresh-ready" role="status">
          <span>Hay una nueva captura completa disponible.</span>
          <button type="button" disabled={editing} onClick={onReload}>
            Refrescar tabla e indicadores
          </button>
          {editing && <small>Guardá o descartá la edición antes de refrescar.</small>}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
