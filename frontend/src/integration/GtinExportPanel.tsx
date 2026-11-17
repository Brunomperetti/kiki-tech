import { useEffect, useState } from "react";
import { request } from "./catalog-adapter";
import { canWrite, production } from "./runtime";

type ApiSummary = {
  source: "ECOMM_APP_API_STAGE";
  mode: "API_CAPTURE_READ_ONLY";
  total_variants: number;
  barcode_present: number;
  without_api_code: number;
  unique_non_pack_valid: number;
  repeated: number;
  invalid: number;
  pack_review: number;
  conflicts: number;
  source_captured_at: string | null;
  external_writes_enabled: false;
};

type ApiEvidence = {
  source: "ECOMM_APP_API_STAGE";
  mode: "API_CAPTURE_READ_ONLY";
  ecomm_id: string;
  sku: string;
  name: string;
  barcode: string | null;
  gtin: string | null;
  state: string;
  captured_at: string | null;
  manufacturer_verified: false;
  external_writes_enabled: false;
};

const date = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString("es-AR") : "No disponible";

export function GtinExportPanel({ csrf }: { csrf: string; onImported?: () => void }) {
  const [summary, setSummary] = useState<ApiSummary>();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!production) return;
    const controller = new AbortController();
    request("/api/ecomm-app/workspace/api-barcode/summary", { signal: controller.signal })
      .then(r => r.json()).then((data: ApiSummary) => {
        if (data.source !== "ECOMM_APP_API_STAGE" ||
            data.mode !== "API_CAPTURE_READ_ONLY" ||
            data.external_writes_enabled !== false ||
            !Number.isSafeInteger(data.total_variants) ||
            !Number.isSafeInteger(data.barcode_present)) {
          throw new Error("El resumen no proviene de la captura API.");
        }
        setSummary(data);
      })
      .catch(e => { if (!controller.signal.aborted) setError(String(e?.message || e)); });
    return () => controller.abort();
  }, []);
  if (!production) return null;
  return <section className="k-gtin-import k-gtin-compact" aria-label="Barcode de Ecomm-App por API">
    <div className="k-gtin-head">
      <div>
        <strong>Códigos de barras de Ecomm-App · API</strong>
        {summary
          ? <p><b>{summary.barcode_present.toLocaleString("es-AR")} códigos barcode</b> informados de {summary.total_variants.toLocaleString("es-AR")} variantes de la captura API. {summary.without_api_code.toLocaleString("es-AR")} sin código API en ninguno de los dos campos.</p>
          : <p>Consultando solamente la captura API. No se utilizan Excel ni CSV de Ecomm-App.</p>
        }
      </div>
      <span>Origen: API</span>
    </div>
    {summary && <small className="k-gtin-note">
      Captura: {date(summary.source_captured_at)} · {summary.unique_non_pack_valid} códigos únicos válidos en variantes no pack · {summary.repeated} repetidos · {summary.invalid} inválidos · {summary.pack_review} packs · {summary.conflicts} conflictos. Un código presente no certifica fabricante ni presentación.
    </small>}
    <BarcodeApiCheck csrf={csrf} />
    {error && <p role="alert" className="k-gtin-error">{error}</p>}
  </section>;
}

const stateText: Record<string, string> = {
  API_BARCODE_GTIN_CONFLICT: "Barcode y GTIN difieren: verificar identidad.",
  API_CODE_MISSING: "La API no informó código para esta variante.",
  API_CODE_INVALID: "El código API no supera la validación GTIN.",
  API_CODE_REPEATED: "Código compartido por varias variantes; revisar presentación.",
  API_PACK_REVIEW: "Pack o combo: confirmar que tenga código propio.",
  API_UNIQUE_CODE: "Código con formato válido y único en captura API; falta verificación de fabricante.",
};

export function GtinExportEvidence({
  ecommId,
  revision,
}: {
  ecommId: string;
  revision?: number;
}) {
  const [value, setValue] = useState<ApiEvidence>();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!production || !/^[1-9]\d*$/.test(ecommId)) return;
    const controller = new AbortController();
    setValue(undefined);
    setError("");
    request("/api/ecomm-app/workspace/api-barcode/" + encodeURIComponent(ecommId), {
      signal: controller.signal,
    })
      .then(r => r.json())
      .then((result: ApiEvidence) => {
        if (result.source !== "ECOMM_APP_API_STAGE" ||
            result.mode !== "API_CAPTURE_READ_ONLY" ||
            result.ecomm_id !== ecommId ||
            result.external_writes_enabled !== false ||
            result.manufacturer_verified !== false) {
          throw new Error("La evidencia no corresponde al Ecomm ID de la API.");
        }
        if (!controller.signal.aborted) setValue(result);
      })
      .catch(e => { if (!controller.signal.aborted) setError(String(e?.message || e)); });
    return () => controller.abort();
  }, [ecommId, revision]);
  if (!production || (!value && !error)) return null;
  return <section className="k-gtin-evidence" aria-label="Barcode original de API Ecomm-App">
    <strong>Barcode original informado por API Ecomm-App</strong>
    {error && <p role="alert">{error}</p>}
    {value && <>
      <div className="k-gtin-code">{value.barcode || "Barcode no informado por API"}</div>
      {value.gtin && <small>Campo GTIN informado por API: {value.gtin}</small>}
      <p>{stateText[value.state] || "Revisar código de la variante."}</p>
      <small>SKU {value.sku || "no informado"} · Captura {date(value.captured_at)}. Sin Excel, sin certificación de fabricante y sin publicación automática.</small>
    </>}
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
