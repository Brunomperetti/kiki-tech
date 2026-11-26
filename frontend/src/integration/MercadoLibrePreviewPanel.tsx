import { useEffect, useRef, useState } from "react";
import { request } from "./catalog-adapter";
import { canWrite, production } from "./runtime";

type Preview = {
  ecomm_id: string;
  sku: string;
  workspace_version: number;
  commercial_preview: { title: string; description: string; brand: string };
  local_blockers: string[];
  channel_checks_pending: string[];
  official_category_verified: false;
  official_payload_validated: false;
  external_writes_enabled: false;
  provider_calls: 0;
};

export function MercadoLibrePreviewPanel({
  id, csrf, blocked,
}: { id: string; csrf: string; blocked: boolean }) {
  const [preview, setPreview] = useState<Preview>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const active = useRef<AbortController>();
  useEffect(() => {
    setPreview(undefined);
    setError("");
    setBusy(false);
    return () => active.current?.abort();
  }, [id, blocked]);
  async function load() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setPreview(undefined);
    setError("");
    try {
      const response = await request("/api/ecomm-app/workspace/mercadolibre/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ ecomm_id: id }),
        signal: controller.signal,
      });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "No se pudo revisar el producto.");
      if (value.ecomm_id !== id || value.external_writes_enabled !== false ||
          value.provider_calls !== 0 || value.official_category_verified !== false ||
          value.official_payload_validated !== false ||
          !Array.isArray(value.local_blockers) || !Array.isArray(value.channel_checks_pending) ||
          !value.commercial_preview) {
        throw new Error("Respuesta de previsualización incompatible.");
      }
      if (!controller.signal.aborted) setPreview(value);
    } catch (err) {
      if (!controller.signal.aborted) setError((err as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  if (!production) return null;
  return (
    <section className="r-notice" aria-label="Preparar producto para Mercado Libre">
      <h4>Mercado Libre · Preparar envío</h4>
      <p>Revisión comercial interna. No consulta Mercado Libre ni valida una publicación oficial.</p>
      <button type="button" disabled={blocked || busy || !canWrite()} onClick={() => void load()}>
        {busy ? "Revisando ficha…" : "Previsualizar producto para Mercado Libre"}
      </button>
      {error && <p role="alert">{error}</p>}
      {!blocked && preview?.ecomm_id === id && (
        <div>
          <p role="status"><strong>{preview.local_blockers.length ? "Ficha requiere revisión" : "Ficha revisada localmente"}</strong> · Envío no habilitado</p>
          <details>
            <summary>Ver requisitos pendientes y previsualización</summary>
          <p><strong>SKU:</strong> {preview.sku} · Ficha v{preview.workspace_version}</p>
          <p><strong>Título:</strong> {preview.commercial_preview.title || "Pendiente"}</p>
          <p><strong>Marca:</strong> {preview.commercial_preview.brand || "Pendiente"}</p>
          <p><strong>Descripción:</strong> {preview.commercial_preview.description || "Pendiente"}</p>
          {preview.local_blockers.length ? (
            <ul>{preview.local_blockers.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
          ) : <p>Controles locales superados. No equivale a una aprobación del canal.</p>}
          <h5>Validaciones oficiales pendientes</h5>
          <ul>{preview.channel_checks_pending.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
          </details>
        </div>
      )}
      <button type="button" disabled>Enviar producto a Mercado Libre (pendiente de habilitación)</button>
    </section>
  );
}
