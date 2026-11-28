import { useEffect, useRef, useState } from "react";
import { captureDate, request } from "./catalog-adapter";
import { canWrite, production } from "./runtime";

type Report = {
  ecomm_id: string;
  source: "TIENDANUBE_API";
  state: "DISABLED" | "NOT_CAPTURED" | "CAPTURED";
  external_writes_enabled: false;
  identity_verified: false;
  products?: number;
  variants?: number;
  fresh?: boolean;
  captured_at?: string;
  match_state?: string;
  matches_total?: number;
  summary?: Record<string, number>;
  matches?: { product_id: number; variant_id: number; name: string; sku: string; visibility: string | null }[];
};
const labels: Record<string, string> = {
  MISSING_SKU: "Sin SKU",
  AMBIGUOUS_ECOMM: "SKU repetido en Ecomm-App",
  DUPLICATE_TN: "SKU repetido en Tiendanube",
  UNIQUE_SKU_CANDIDATE: "Coincidencia por SKU · Revisar identidad",
  NO_SKU_MATCH_IN_CAPTURE: "Sin coincidencia por SKU en captura",
};

export function TiendanubeCatalogPanel({ id, csrf }: { id: string; csrf: string }) {
  const [report, setReport] = useState<Report>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<AbortController>();
  async function load(refresh: boolean) {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError("");
    try {
      const base = "/api/ecomm-app/workspace/tiendanube/catalog";
      const response = await request(refresh ? base + "/refresh" : base + "/" + encodeURIComponent(id), {
        method: refresh ? "POST" : "GET",
        ...(refresh ? { headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({ ecomm_id: id }) } : {}),
        signal: controller.signal,
      });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "No se pudo leer el catálogo.");
      if (value.ecomm_id !== id || value.source !== "TIENDANUBE_API" ||
          value.external_writes_enabled !== false || value.identity_verified !== false ||
          !["DISABLED", "NOT_CAPTURED", "CAPTURED"].includes(value.state)) throw new Error("Respuesta incompatible.");
      if (!controller.signal.aborted) setReport(value);
    } catch (err) {
      if (!controller.signal.aborted) setError((err as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  useEffect(() => {
    setReport(undefined);
    if (production) void load(false);
    return () => active.current?.abort();
  }, [id]);
  if (!production) return null;
  const current = report?.ecomm_id === id ? report : undefined;
  return (
    <section className="k-channel-card k-channel-tn" aria-label="Catálogo Tiendanube por API">
      <h4>Catálogo Tiendanube · API</h4>
      {current?.state === "CAPTURED" ? <>
        <strong>{labels[current.match_state || ""] || "Requiere revisión"}</strong>
        <span>{current.products} productos · {current.variants} variantes</span>
        <small>{captureDate(current.captured_at || null)} · {current.fresh ? "Captura reciente" : "Captura vencida"}</small>
        <small>{current.matches_total} coincidencias por SKU. No confirman identidad ni ausencia de publicación.</small>
        <details><summary>Ver comparación y datos</summary>
          <p>Coincidencias únicas: {current.summary?.UNIQUE_SKU_CANDIDATE || 0} · SKU repetidos en tienda: {current.summary?.DUPLICATE_TN || 0}</p>
          <p>Sin SKU: {current.summary?.MISSING_SKU || 0} · Sin coincidencia Ecomm-App: {current.summary?.NO_ECOMM_SKU_MATCH || 0} · SKU ambiguos Ecomm-App: {current.summary?.AMBIGUOUS_ECOMM || 0}</p>
          {current.matches?.map(row => <p key={row.variant_id}>{row.name || "Sin nombre"} · SKU {row.sku} · ID {row.product_id}/{row.variant_id} · {row.visibility || "Visibilidad sin verificar"}</p>)}
        </details>
      </> : <p>{current?.state === "DISABLED" ? "Lectura API deshabilitada" : "Todavía sin captura API guardada"}</p>}
      {error && <p role="alert">{error} {current?.state === "CAPTURED" ? "Se muestra la última captura disponible." : ""}</p>}
      <button type="button" disabled={busy || !canWrite() || current?.state === "DISABLED"} onClick={() => void load(true)}>
        {busy ? "Consultando catálogo…" : "Actualizar catálogo desde Tiendanube"}
      </button>
      <small>Solo lectura. El CSV histórico se conserva por separado.</small>
    </section>
  );
}
