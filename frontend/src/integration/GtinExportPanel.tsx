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

  const usable = (summary?.valid_unique ?? 0) + (summary?.valid_repeated ?? 0) + (summary?.pack_review ?? 0);
  const missingOrInvalid = (summary?.invalid ?? 0) + (summary?.missing ?? 0);
  return <section className="k-gtin-import k-gtin-compact" aria-label="Estado de GTIN de Ecomm-App">
    <div className="k-gtin-head">
      <div>
        <strong>GTIN del inventario Ecomm-App</strong>
        <p>{summary?.current
          ? <><b>{usable.toLocaleString("es-AR")} códigos con GTIN válido</b> de {summary.variants?.toLocaleString("es-AR")} variantes · {missingOrInvalid.toLocaleString("es-AR")} sin GTIN válido.</>
          : summary?.available
            ? "La captura API cambió desde que se incorporó el Excel; hay que recotejarlo."
            : "La API no entrega GTIN; podés incorporarlos desde la exportación oficial."}
        </p>
      </div>
      <span>{summary?.current ? "Excel incorporado" : summary?.available ? "Revisar exportación" : "Sin exportación"}</span>
    </div>
    {summary?.current && <small className="k-gtin-note">Dentro de los válidos: {summary.valid_unique?.toLocaleString("es-AR")} únicos no combo · {summary.valid_repeated?.toLocaleString("es-AR")} repetidos · {summary.pack_review?.toLocaleString("es-AR")} packs para revisión. Fuente: Excel Ecomm-App · {date(summary.imported_at)}.</small>}
    <BarcodeApiCheck csrf={csrf} />
    <details className="k-gtin-upload">
      <summary>{summary?.available ? "Ver origen / actualizar GTIN" : "Incorporar Excel de Ecomm-App"}</summary>
      {summary?.available && <p>Archivo: {summary.source_filename}. Los GTIN de exportación no son una confirmación de la API y nunca aprueban publicaciones automáticamente.</p>}
      <p>Descargá Ecomm-App con «Código de barra» marcado. KIKI valida Ecomm ID y SKU contra la captura API completa antes de guardar.</p>
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


type LiveSkuMatch = {
  variant_id: number | string | null;
  variant_sku: string;
  barcode_field_present: boolean;
  barcode: string | number | null;
  gtin_field_present: boolean;
  gtin: string | number | null;
};
type LiveSkuReport = {
  mode: "READ_ONLY_SKU_LOOKUP";
  requested_skus: string[];
  sku_diagnosis: {
    shape_recognized: boolean;
    requested: {
      sku: string;
      status: "UNKNOWN_SHAPE" | "MULTIPLE_EXACT" | "EXACT_SINGLE" | "NO_EXACT";
      matches: LiveSkuMatch[];
    }[];
  };
};

function BarcodeApiCheck({ csrf }: { csrf: string }) {
  const [sku, setSku] = useState("6317");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{
    sku: string;
    identity: string;
    message: string;
    detail: string;
  }>();
  const sampleBarcode = "7793396000039";

  async function verify() {
    const requested = sku.trim();
    if (!requested || requested.length > 128 || busy) return;
    setResult(undefined);
    setError("");
    setBusy(true);
    try {
      const response = await request("/api/ecomm-app/lookup", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf, "Content-Type": "application/json" },
        body: JSON.stringify({ skus: [requested] }),
      });
      const report = await response.json() as LiveSkuReport;
      const found = report.sku_diagnosis?.requested?.[0];
      if (
        report.mode !== "READ_ONLY_SKU_LOOKUP" ||
        report.requested_skus?.length !== 1 ||
        report.requested_skus[0] !== requested ||
        found?.sku !== requested ||
        !Array.isArray(found.matches)
      ) throw new Error("La API respondió con un formato no comprobable.");
      if (found.status !== "EXACT_SINGLE" || found.matches.length !== 1) {
        setResult({
          sku: requested, identity: "Sin variante única confirmada",
          message: found.status === "NO_EXACT"
            ? "La API no encontró el SKU exacto."
            : found.status === "MULTIPLE_EXACT"
              ? "Hay más de una variante con ese SKU. Debemos revisar los Ecomm ID antes de elegir un barcode."
              : "La forma de la respuesta todavía requiere revisión.",
          detail: "No se incorporó ni modificó información de la captura.",
        });
        return;
      }
      const exact = found.matches[0];
      const code = exact.barcode === null || exact.barcode === undefined
        ? "" : String(exact.barcode).trim();
      const expected = requested === "6317" ? sampleBarcode : null;
      setResult({
        sku: requested,
        identity: `Ecomm ID ${exact.variant_id ?? "no informado"}`,
        message: !exact.barcode_field_present
          ? "Ecomm-App todavía no devuelve la clave variants[].barcode para este SKU."
          : !code
            ? "Ecomm-App devuelve barcode: null o vacío para este SKU."
            : expected && code === expected
              ? `Comprobación correcta: la API devuelve barcode ${code}, igual al código esperado.`
              : expected
                ? `Atención: la API devuelve barcode ${code}, distinto del esperado ${expected}.`
                : `La API devuelve barcode ${code} para esta variante.`,
        detail: `Consulta directa a Ecomm-App, sin Excel ni caché de catálogo. Campo gtin: ${exact.gtin_field_present ? String(exact.gtin ?? "null") : "ausente"}. No se guardó ni actualizó ninguna ficha.`,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo consultar Ecomm-App.");
    } finally {
      setBusy(false);
    }
  }

  return <details className="k-gtin-upload" aria-label="Comprobación directa de barcode">
    <summary>Comprobar barcode ahora en la API (solo lectura)</summary>
    <p>Consulta una variante exacta en Ecomm-App con el token existente. No actualiza el catálogo, stock ni publicaciones.</p>
    <label>
      SKU de Ecomm-App
      <input
        aria-label="SKU para comprobar barcode en la API"
        value={sku}
        maxLength={128}
        disabled={busy}
        onChange={event => { setSku(event.target.value); setError(""); setResult(undefined); }}
      />
    </label>
    <button type="button" disabled={busy || !sku.trim() || !canWrite()} onClick={() => void verify()}>
      {busy ? "Consultando API…" : "Comprobar barcode en vivo"}
    </button>
    {result && <div role="status" className="k-gtin-success">
      <strong>{result.sku} · {result.identity}</strong>
      <p>{result.message}</p>
      <small>{result.detail}</small>
    </div>}
    {error && <p role="alert" className="k-gtin-error">{error}</p>}
  </details>;
}
