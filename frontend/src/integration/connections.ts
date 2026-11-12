import { production, capabilities, canWrite, environmentText } from "./runtime";
import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "./catalog-adapter";
import { setConnectionActionsEnabled } from "./isolation";

export type ConnectionStatus = {
  external_writes_enabled: false;
  synthetic: boolean;
  actions_enabled: boolean;
  external_oauth_allowed: boolean;
  max_csv_bytes: number;
  ecomm: {
    api_configured: boolean;
    configured: boolean;
    live_authorization_verified: boolean;
    last_successful_capture_at: string | null;
    last_successful_complete: boolean;
    last_successful_variants: number;
    refresh_in_progress: boolean;
    refresh_job: null | {
      status: "RUNNING" | "SUCCESS" | "FAILED" | "INTERRUPTED";
      started_at: string;
      pages_saved: number;
      expected_pages: number | null;
      message: string;
      origin: "MANUAL" | "SCHEDULED";
    };
    schedule_times: string[];
    schedule_timezone: string;
    next_updates: string[];
    github_schedule_verified: boolean;
  };
  ml: {
    connected: boolean;
    user_id: string | null;
    token_expired: boolean;
    token_expiration: string | null;
    last_sync: string | null;
    listing_count: number | null;
    publication_count: number | null;
  };
  tn: {
    source: "TIENDANUBE_CSV";
    available: boolean;
    imported_at: string | null;
    records: number;
    products: number | null;
    current_publication_verified: false;
  };
};
const number = (v: unknown) => Number.isSafeInteger(v) && Number(v) >= 0;
const date = (v: unknown) =>
  v === null || (typeof v === "string" && Number.isFinite(Date.parse(v)));
export function connectionStatus(value: unknown): ConnectionStatus {
  const d = value as ConnectionStatus;
  if (
    !d ||
    d.external_writes_enabled !== false ||
    (production ? typeof d.synthetic !== "boolean" : d.synthetic !== true) ||
    (production
      ? typeof d.external_oauth_allowed !== "boolean"
      : d.external_oauth_allowed !== false) ||
    typeof d.actions_enabled !== "boolean" ||
    !number(d.max_csv_bytes) ||
    d.max_csv_bytes > 20 * 1024 * 1024 ||
    !d.ecomm ||
    !d.ml ||
    !d.tn ||
    [
      d.ecomm.api_configured,
      d.ecomm.configured,
      d.ecomm.last_successful_complete,
      d.ecomm.refresh_in_progress,
      d.ml.connected,
      d.ml.token_expired,
      d.tn.available,
    ].some((v) => typeof v !== "boolean") ||
    d.ecomm.live_authorization_verified !== false ||
    d.ecomm.github_schedule_verified !== false ||
    ![d.ecomm.last_successful_variants, d.tn.records, d.tn.products].every(
      number,
    ) ||
    ![d.ml.listing_count, d.ml.publication_count].every(
      (v) => v === null || number(v),
    ) ||
    ![
      d.ecomm.last_successful_capture_at,
      d.ml.last_sync,
      d.ml.token_expiration,
      d.tn.imported_at,
    ].every(date) ||
    !(d.ml.user_id === null || typeof d.ml.user_id === "string") ||
    (d.ml.connected && (!d.ml.user_id?.trim() || !d.ml.token_expiration)) ||
    d.tn.source !== "TIENDANUBE_CSV" ||
    d.tn.current_publication_verified !== false ||
    d.ecomm.schedule_timezone !== "America/Argentina/Buenos_Aires" ||
    JSON.stringify(d.ecomm.schedule_times) !==
      JSON.stringify(["08:25", "16:25"]) ||
    !Array.isArray(d.ecomm.next_updates) ||
    d.ecomm.next_updates.length !== 2 ||
    !d.ecomm.next_updates.every(date) ||
    (d.ecomm.refresh_job &&
      (!["RUNNING", "SUCCESS", "FAILED", "INTERRUPTED"].includes(
        d.ecomm.refresh_job.status,
      ) ||
        !["MANUAL", "SCHEDULED"].includes(d.ecomm.refresh_job.origin) ||
        !number(d.ecomm.refresh_job.pages_saved) ||
        !(
          d.ecomm.refresh_job.expected_pages === null ||
          number(d.ecomm.refresh_job.expected_pages)
        ) ||
        !date(d.ecomm.refresh_job.started_at) ||
        typeof d.ecomm.refresh_job.message !== "string")) ||
    d.ecomm.refresh_in_progress !== (d.ecomm.refresh_job?.status === "RUNNING")
  )
    throw new Error(
      "Estado de conexiones incompatible. No se habilitaron operaciones.",
    );
  return d;
}

export function useConnections(
  enabled: boolean,
  csrf?: string,
  visible = true,
) {
  const [data, setData] = useState<ConnectionStatus>();
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [refreshSuggested, setRefreshSuggested] = useState(false);
  const inFlight = useRef(false);
  const controller = useRef<AbortController>();
  const observedCapture = useRef<string | null | undefined>();
  const alive = useRef(false);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;
  const runningRef = useRef(false);
  const wake = useRef<() => void>();
  const epoch = useRef(0);
  const load = useCallback(async () => {
    const d = connectionStatus(
      await (
        await request("/api/connections/status", {
          signal: controller.current?.signal,
        })
      ).json(),
    );
    if (!alive.current) return;
    setConnectionActionsEnabled(d.actions_enabled);
    runningRef.current = d.ecomm.refresh_in_progress;
    if (
      observedCapture.current !== undefined &&
      d.ecomm.last_successful_capture_at !== observedCapture.current
    )
      setRefreshSuggested(true);
    observedCapture.current = d.ecomm.last_successful_capture_at;
    setData(d);
    setLoadError("");
    return d;
  }, []);
  useEffect(() => {
    if (!enabled || !csrf) return;
    alive.current = true;
    epoch.current += 1;
    const c = new AbortController();
    controller.current = c;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (!visibleRef.current && !runningRef.current) return;
      let running = false;
      try {
        running = !!(await load())?.ecomm.refresh_in_progress;
      } catch (e) {
        if (!c.signal.aborted) {
          setData(undefined);
          setLoadError((e as Error).message);
          setConnectionActionsEnabled(false);
        }
      }
      if (!c.signal.aborted && (visibleRef.current || runningRef.current))
        timer = setTimeout(poll, running ? 1500 : 15000);
    }
    void poll();
    wake.current = () => {
      clearTimeout(timer);
      timer = setTimeout(poll, 500);
    };
    return () => {
      alive.current = false;
      epoch.current += 1;
      c.abort();
      clearTimeout(timer);
      wake.current = undefined;
      setConnectionActionsEnabled(false);
      setData(undefined);
      setBusy("");
      setError("");
      setLoadError("");
      setMessage("");
      observedCapture.current = undefined;
      runningRef.current = false;
      setRefreshSuggested(false);
      inFlight.current = false;
    };
  }, [enabled, csrf, load]);
  useEffect(() => {
    if (visible && enabled) wake.current?.();
  }, [visible, enabled]);
  async function operate(kind: "ecomm" | "ml" | "oauth" | "tn", file?: File) {
    if (
      inFlight.current ||
      !data?.actions_enabled ||
      !csrf ||
      !canWrite() ||
      (production && !capabilities?.connections)
    )
      return;
    if (kind === "ecomm" && data.ecomm.refresh_in_progress) return;
    const prompts = {
      ecomm:
        "¿Actualizar la captura de Ecomm-App en KIKI? Se conserva el catálogo anterior hasta completar la nueva copia y no se sobrescriben fichas. En este entorno sólo se usan respuestas sintéticas.",
      ml: "¿Leer las publicaciones con el servicio existente y guardar una captura en KIKI? Puede renovar la autorización. En este entorno sólo usa el transporte sintético; no publica ni modifica productos.",
      oauth:
        "¿Preparar una autorización para la cuenta correcta? La navegación al proveedor está bloqueada en este entorno; no se conectará una cuenta real.",
      tn: "¿Importar este CSV en KIKI? Reemplaza la copia local de Tiendanube, sin modificar la tienda ni las fichas editadas.",
    };
    if (
      kind === "tn" &&
      (!file ||
        !file.name.toLowerCase().endsWith(".csv") ||
        file.size > data.max_csv_bytes ||
        !file.size)
    ) {
      setError(
        `Seleccioná un CSV no vacío de hasta ${data.max_csv_bytes / 1024 / 1024} MB.`,
      );
      return;
    }
    const realPrompts = {
      ecomm:
        "¿Leer Ecomm-App y renovar la captura interna? Usa el proveedor real, conserva la copia anterior hasta completar y no sobrescribe fichas.",
      ml: "¿Leer Mercado Libre y renovar su captura interna? Puede refrescar el token existente. No publica ni modifica publicaciones.",
      oauth:
        "¿Abrir la autorización oficial de Mercado Libre para vincular la cuenta correcta? La vuelta utiliza el callback histórico de KIKI.",
      tn: prompts.tn,
    };
    if (!window.confirm(production ? realPrompts[kind] : prompts[kind])) return;
    const operationEpoch = epoch.current;
    inFlight.current = true;
    setBusy(kind);
    setError("");
    setMessage("");
    try {
      const paths = {
        ecomm: "/api/ecomm-app/stage/manual/start",
        ml: "/api/mercadolibre/sync",
        oauth: "/api/mercadolibre/auth-url",
        tn: "/api/tiendanube/import-csv",
      };
      const body = kind === "tn" ? new FormData() : undefined;
      if (body && file) body.append("file", file);
      const result = await (
        await request(paths[kind], {
          method: "POST",
          headers: { "X-CSRF-Token": csrf },
          body,
          signal: controller.current?.signal,
        })
      ).json();
      if (!alive.current || operationEpoch !== epoch.current) return;
      if (kind === "oauth") {
        const target = new URL(result.url);
        if (
          target.protocol !== "https:" ||
          target.username ||
          target.password ||
          target.port ||
          ![
            "auth.mercadolibre.com.ar",
            "auth.mercadolibre.com",
            "www.mercadolibre.com.ar",
            "mercadolibre.com.ar",
          ].includes(target.hostname)
        )
          throw new Error(
            "El servidor devolvió un destino OAuth no permitido.",
          );
        if (
          production &&
          data.external_oauth_allowed &&
          capabilities?.connections
        ) {
          location.assign(target.href);
          return;
        }
        // Synthetic mode never opens a provider.
        setMessage(
          "Solicitud OAuth preparada con el servicio existente. Autorización externa bloqueada: no se abrió Mercado Libre ni se vinculó una cuenta.",
        );
      } else if (kind === "ecomm") {
        if (
          result.status !== "RUNNING" ||
          result.external_writes_enabled !== false
        )
          throw new Error("Inicio de captura incompatible.");
        setMessage(
          "Actualización iniciada en segundo plano con el proceso existente. Podés cerrar Configuración y continuar trabajando.",
        );
      } else {
        if (!number(kind === "ml" ? result.listing_count : result.records))
          throw new Error("Resultado de actualización incompatible.");
        setRefreshSuggested(true);
        setMessage(
          environmentText(
            "Copia interna actualizada en el entorno sintético. Podés refrescar la tabla; no se modificaron productos externos.",
            "Captura interna actualizada. Podés refrescar indicadores y tabla; no se modificaron productos externos.",
          ),
        );
      }
      await load();
      wake.current?.();
    } catch (e) {
      if (!alive.current || operationEpoch !== epoch.current) return;
      setError(
        (e as Error).message +
          " No se reintentó automáticamente. Un error de captura no es un error de publicación.",
      );
      try {
        await load();
      } catch {
        setData(undefined);
        setConnectionActionsEnabled(false);
      }
    } finally {
      if (operationEpoch === epoch.current) {
        inFlight.current = false;
        if (alive.current) setBusy("");
      }
    }
  }
  return {
    data,
    error: [loadError, error].filter(Boolean).join(" "),
    message,
    busy,
    refreshSuggested,
    operate,
    reload: () => {
      void load().catch((e) => {
        setData(undefined);
        setConnectionActionsEnabled(false);
        setLoadError((e as Error).message);
      });
    },
    acknowledge: () => setRefreshSuggested(false),
  };
}
