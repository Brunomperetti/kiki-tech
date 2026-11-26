import { useEffect, useRef, useState } from "react";
import { request } from "./catalog-adapter";
import { canWrite, production } from "./runtime";

type Preview = {
  ecomm_id: string;
  sku: string;
  workspace_version: number;
  payload_preview: {
    name: { es: string };
    description: { es: string };
    visibility: "hidden";
    variants: { sku: string }[];
  };
  local_blockers: string[];
  remote_duplicate_check: "NOT_RUN";
  external_writes_enabled: false;
  provider_calls: 0;
};

export function TiendanubePreviewPanel({
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
      const response = await request("/api/ecomm-app/workspace/tiendanube/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ ecomm_id: id }),
        signal: controller.signal,
      });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "No se pudo preparar el producto.");
      if (value.ecomm_id !== id || value.external_writes_enabled !== false ||
          value.provider_calls !== 0 || value.remote_duplicate_check !== "NOT_RUN" ||
          value.payload_preview?.visibility !== "hidden" ||
          !Array.isArray(value.local_blockers)) {
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
    <section className="r-notice" aria-label="Preparar producto para Tiendanube">
      <h4>Tiendanube · Preparar envío</h4>
      <p>Previsualización local de un producto oculto. No consulta ni modifica la tienda.</p>
      <button type="button" disabled={blocked || busy || !canWrite()} onClick={() => void load()}>
        {busy ? "Revisando ficha…" : "Previsualizar producto para Tiendanube"}
      </button>
      {error && <p role="alert">{error}</p>}
      {!blocked && preview?.ecomm_id === id && (
        <div>
          <p><strong>SKU:</strong> {preview.sku} · Ficha v{preview.workspace_version}</p>
          <p><strong>Título:</strong> {preview.payload_preview.name.es || "Pendiente"}</p>
          <p><strong>Descripción:</strong> {preview.payload_preview.description.es || "Pendiente"}</p>
          <p>Visibilidad prevista: Oculto</p>
          {preview.local_blockers.length ? (
            <ul>{preview.local_blockers.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
          ) : <p>Controles locales superados. Aún requiere verificación remota.</p>}
          <p>Duplicados remotos: sin comprobar. Conexión y registro de envío pendientes.</p>
        </div>
      )}
      <button type="button" disabled>Enviar producto a Tiendanube (pendiente de habilitación)</button>
    </section>
  );
}
