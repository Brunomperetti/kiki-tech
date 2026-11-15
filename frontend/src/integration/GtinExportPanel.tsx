import { useEffect, useState } from "react";
import { request } from "./catalog-adapter";
import { canWrite, production } from "./runtime";

type Summary = {
  available: boolean;
  current?: boolean;
  variants?: number;
  api_variants?: number;
  valid_unique?: number;
  valid_repeated?: number;
  pack_review?: number;
  invalid?: number;
  missing?: number;
  source_filename?: string;
  imported_at?: string;
  note?: string;
};
type Evidence = {
  available: boolean;
  current?: boolean;
  gtin?: string | null;
  status?: string;
  is_combo?: boolean;
  imported_at?: string;
  note?: string;
};
const date = (s?: string) => s ? new Date(s).toLocaleString("es-AR") : "—";

export function GtinExportPanel({
  csrf,
  onImported,
}: {
  csrf: string;
  onImported?: () => void;
}) {
  const [summary, setSummary] = useState<Summary>();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!production) return;
    const controller = new AbortController();
    request("/api/ecomm-app/workspace/gtin-export/summary", { signal: controller.signal })
      .then(r => r.json()).then(setSummary)
      .catch(e => { if (!controller.signal.aborted) setError(String(e?.message || e)); });
    return () => controller.abort();
  }, []);
  if (!production) return null;

  async function importFile() {
    if (!file || !canWrite() || busy) return;
    if (!window.confirm(
      "¿Incorporar solamente Ecomm ID, SKU y GTIN del Excel como evidencia interna de KIKI? " +
      "No cambiará stock, precios, fichas editoriales ni publicaciones externas."
    )) return;
    setError("");
    setMessage("");
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const next = await request("/api/ecomm-app/workspace/gtin-export", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body,
      }).then(r => r.json()) as Summary;
      setSummary(next);
      setMessage("Excel incorporado y cotejado por Ecomm ID + SKU. GTIN disponibles para consulta interna.");
      setFile(null);
      onImported?.();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBusy(false);
    }
  }

  return <section className="k-gtin-import" aria-label="GTIN de exportación Ecomm-App">
    <div className="k-gtin-head">
      <div><strong>GTIN de Ecomm-App</strong>
        <p>Exportación manual, asociada por Ecomm ID y SKU. No modifica canales ni el inventario original.</p>
      </div>
      <span>{summary?.current ? "Captura cotejada" : summary?.available ? "Captura desactualizada" : "Sin archivo incorporado"}</span>
    </div>
    {summary?.available && <div className="k-gtin-numbers">
      <div><b>{summary.variants?.toLocaleString("es-AR") ?? "—"}</b><small>Variantes en exportación</small></div>
      <div><b>{summary.valid_unique?.toLocaleString("es-AR") ?? "—"}</b><small>GTIN únicos, no combos</small></div>
      <div><b>{(summary.valid_repeated ?? 0) + (summary.pack_review ?? 0)}</b><small>Repetidos / packs por revisar</small></div>
      <div><b>{(summary.invalid ?? 0) + (summary.missing ?? 0)}</b><small>Inválidos / ausentes</small></div>
    </div>}
    {summary?.available && <p className="k-gtin-note">Archivo: {summary.source_filename} · Incorporado: {date(summary.imported_at)}. {summary.note}
      {summary.current === false && <strong> La API actual cambió: no se usan estos GTIN hasta recotejar otra exportación.</strong>}
    </p>}
    <details className="k-gtin-upload">
      <summary>{summary?.available ? "Actualizar exportación GTIN" : "Incorporar Excel GTIN de Ecomm-App"}</summary>
      <p>Descargá el inventario desde Ecomm-App con «Código de barra» marcado. Se validará que los IDs y SKU coincidan exactamente con el catálogo API.</p>
      <input aria-label="Excel GTIN de Ecomm-App" type="file" accept=".xlsx" disabled={busy || !canWrite()}
        onChange={event => { setFile(event.currentTarget.files?.[0] ?? null); setError(""); }} />
      <button type="button" onClick={() => void importFile()} disabled={busy || !file || !canWrite()}>
        {busy ? "Validando Excel…" : "Validar e incorporar GTIN"}
      </button>
      {!canWrite() && <p>Para incorporar el Excel, la edición interna debe estar habilitada.</p>}
    </details>
    {error && <p role="alert" className="k-gtin-error">{error}</p>}
    {message && <p role="status" className="k-gtin-success">{message}</p>}
  </section>;
}

const states: Record<string, string> = {
  VALID_UNIQUE: "Código válido y único en la exportación (pendiente de cotejar con fabricante)",
  VALID_REPEATED: "Código repetido en distintas variantes: requiere revisión",
  PACK_REVIEW: "Pack o combo: verificar que tenga GTIN propio",
  INVALID: "El código no pasa la validación GTIN",
  MISSING: "Código no informado",
};
export function GtinExportEvidence({ ecommId, revision }: { ecommId: string; revision?: number }) {
  const [value, setValue] = useState<Evidence>();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!production || !/^[1-9]\d*$/.test(ecommId)) return;
    const controller = new AbortController();
    setValue(undefined);
    request("/api/ecomm-app/workspace/gtin-export/" + encodeURIComponent(ecommId), { signal: controller.signal })
      .then(r => r.json()).then(setValue)
      .catch(e => { if (!controller.signal.aborted) setError(String(e?.message || e)); });
    return () => controller.abort();
  }, [ecommId, revision]);
  if (!production || (!value && !error)) return null;
  return <section className="k-gtin-evidence" aria-label="GTIN de la exportación">
    <strong>GTIN del inventario exportado de Ecomm-App</strong>
    {error && <p role="alert">{error}</p>}
    {value && (value.available ? (value.current ?
      <><div className="k-gtin-code">{value.gtin || "Sin código"}</div>
        <p>{states[value.status || ""] || "Revisar evidencia"}</p>
        <small>Fuente: Excel de inventario Ecomm-App, incorporado {date(value.imported_at)}. No es un GTIN certificado por la API.</small></>
      : <p>La captura API cambió. Los GTIN del archivo quedaron suspendidos hasta recotejar.</p>)
      : <p>El GTIN todavía no se incorporó. Cargá el Excel desde el resumen de catálogo.</p>)}
  </section>;
}
