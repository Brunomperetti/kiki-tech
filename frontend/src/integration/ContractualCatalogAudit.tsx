import { useState } from "react";
import { request } from "./catalog-adapter";
import { downloadReviewCsv } from "./csv-download";

type Audit = {
  mode: "READ_ONLY_CONTRACTUAL_CATALOG_AUDIT";
  source: "ECOMM_APP_API_STAGE";
  generated_at: string;
  total: number;
  internal_fiches_complete: number;
  approved_claims_in_current_originals: number;
  gap_counts: Record<string, number>;
  editorial_status: Record<string, number>;
  external_writes_enabled: false;
  network_requests: 0;
  ai_requests: 0;
  monthly_review_confirmed: false;
};
const gapLabels: Record<string, string> = {
  IDENTITY_CONFLICT: "Identidad para revisar",
  NO_UNIQUE_API_BARCODE: "Sin barcode único verificable de la API",
  NO_MANUFACTURER_DOCUMENT: "Sin documento original",
  SOURCE_NOT_REVIEWED: "Fuentes pendientes de revisión",
  NO_CURRENT_APPROVED_FACTS: "Sin hechos aprobados con original vigente",
  INCOMPLETE_COMMERCIAL_FICHE: "Fichas comerciales incompletas",
  TAXONOMY_MISSING: "Categoría/subcategoría incompleta",
  SEO_MISSING: "SEO incompleto",
  IMAGE_MISSING: "Sin imagen registrada",
  VIDEO_NOT_DOCUMENTED: "Video no documentado (sujeto a disponibilidad)",
  MEDIA_RIGHTS_NOT_VERIFIED: "Derechos multimedia por verificar",
  MONTHLY_REVIEW_DUE: "Revisión de ficha vencida",
  READY_WITHOUT_VERIFIED_DOCUMENTAL_GATE: "Fichas listas que necesitan corroboración documental",
};

export function ContractualCatalogAudit() {
  const [report, setReport] = useState<Audit>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function audit() {
    if (busy) return;
    setBusy(true);
    setError("");
    setReport(undefined);
    try {
      const response = await request("/api/ecomm-app/workspace/audit/contractual");
      const value = await response.json() as Audit & { detail?: string };
      if (!response.ok) throw new Error(value.detail || "No se pudo auditar el catálogo.");
      if (value.mode !== "READ_ONLY_CONTRACTUAL_CATALOG_AUDIT" ||
          value.source !== "ECOMM_APP_API_STAGE" ||
          value.external_writes_enabled !== false || value.ai_requests !== 0 ||
          value.network_requests !== 0 || value.monthly_review_confirmed !== false ||
          !Number.isSafeInteger(value.total) || value.total < 0 ||
          !Number.isSafeInteger(value.internal_fiches_complete) ||
          !value.editorial_status || !value.gap_counts ||
          Object.values(value.editorial_status).reduce((sum, n) => sum + n, 0) !== value.total ||
          !Object.keys(gapLabels).every(key => Number.isSafeInteger(value.gap_counts[key]))) {
        throw new Error("El informe no acredita todo el catálogo; resultado descartado.");
      }
      setReport(value);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Error de auditoría.");
    } finally {
      setBusy(false);
    }
  }

  async function exportCsv() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await request("/api/ecomm-app/workspace/audit/contractual.csv");
      if (!response.ok) throw new Error("La auditoría no pudo exportarse.");
      downloadReviewCsv(await response.blob(), "kiki-auditoria-comercial-mensual.csv");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Error de descarga.");
    } finally {
      setBusy(false);
    }
  }

  return <section aria-label="Auditoría comercial integral">
    <h4>Auditoría comercial integral</h4>
    <p>
      Revisa todas las variantes de la última captura Ecomm-App API: fuentes,
      hechos aprobados, descripciones, taxonomía, SEO, imágenes, videos y
      vencimientos. No consulta datos en vivo ni certifica derechos de uso.
    </p>
    <div className="b-actions">
      <button type="button" disabled={busy} onClick={() => void audit()}>
        {busy ? "Auditando…" : "Auditar catálogo completo"}
      </button>
      <button type="button" disabled={busy} onClick={() => void exportCsv()}>
        Exportar pendientes (CSV)
      </button>
    </div>
    {error && <p role="alert">{error}</p>}
    {report && <div role="region" aria-label="Cobertura y excepciones">
      <p role="status">
        <strong>{report.total}</strong> variantes evaluadas ·{" "}
        <strong>{report.internal_fiches_complete}</strong> fichas completas
        internamente · <strong>{report.approved_claims_in_current_originals}</strong>{" "}
        hechos aprobados asociados a originales vigentes.
      </p>
      <p>
        Informe generado {new Date(report.generated_at).toLocaleString("es-AR")}.
        No acredita una revisión mensual ya realizada. El CSV identifica cada
        SKU y sus pendientes, para priorizar el trabajo por lotes.
      </p>
      <ul>
        {Object.entries(gapLabels).map(([key, label]) => <li key={key}>
          {label}: <strong>{report.gap_counts[key]}</strong>
        </li>)}
      </ul>
    </div>}
  </section>;
}
