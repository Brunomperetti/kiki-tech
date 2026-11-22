import { useState } from "react";
import { request } from "./catalog-adapter";
import { downloadReviewCsv } from "./csv-download";
import { DocumentaryCohortPanel } from "./DocumentaryCohortPanel";
import { CommercialExportPanel, MonthlyReportPanel } from "./CommercialExportPanel";

export type Audit = {
  mode: "READ_ONLY_CONTRACTUAL_CATALOG_AUDIT";
  source: "ECOMM_APP_API_STAGE";
  generated_at: string;
  preview_fingerprint: string;
  total: number;
  internal_fiches_complete: number;
  fields_complete: number;
  classified_variants: number;
  quality_stage_counts: Record<string, number>;
  channel_certified_by_this_audit: 0;
  approved_claims_in_current_originals: number;
  gap_counts: Record<string, number>;
  editorial_status: Record<string, number>;
  monthly_review: {
    ready_current: number;
    ready_overdue: number;
    ready_changed: number;
    ready_without_signoff: number;
    not_ready: number;
    due: number;
    review_actions_performed_by_audit: 0;
  };
  external_writes_enabled: false;
  network_requests: 0;
  ai_requests: 0;
  monthly_review_confirmed: false;
};
const stageLabels: Record<string, string> = {
  REVIEW_IDENTITY: "1. Resolver identidad de variante, pack o SKU",
  FIND_ORIGINAL: "2. Conseguir documentación original",
  REVIEW_ORIGINAL: "3. Revisar procedencia e identidad documental",
  REVIEW_FACTS: "4. Revisar afirmaciones con cita",
  REVIEW_TAXONOMY: "5. Validar categoría y subcategoría",
  REVIEW_SEO: "6. Completar posicionamiento SEO",
  COMPLETE_FIELDS: "7. Completar campos editoriales",
  ADD_IMAGE: "8. Incorporar imagen auténtica",
  REVIEW_MEDIA_AND_CHANNEL: "9. Comprobar permisos y aptitud comercial",
};
const gapLabels: Record<string, string> = {
  IDENTITY_CONFLICT: "Identidad para revisar",
  BARCODE_RESEARCH_NOT_ELIGIBLE: "Aún no apto para investigación por código API",
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

export function ContractualCatalogAudit({ selectedIds = [], csrf = "" }: { selectedIds?: string[]; csrf?: string }) {
  const [report, setReport] = useState<Audit>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function audit() {
    if (busy) return;
    setBusy(true);
    setError("");
    setReport(undefined);
    try {
      const response = await request("/api/ecomm-app/workspace/reports/monthly/preview");
      const value = await response.json() as Audit & { detail?: string };
      if (!response.ok) throw new Error(value.detail || "No se pudo auditar el catálogo.");
      if (value.mode !== "READ_ONLY_CONTRACTUAL_CATALOG_AUDIT" ||
          value.source !== "ECOMM_APP_API_STAGE" ||
          !/^[a-f0-9]{64}$/.test(value.preview_fingerprint || "") ||
          value.external_writes_enabled !== false || value.ai_requests !== 0 ||
          value.network_requests !== 0 || value.monthly_review_confirmed !== false ||
          !Number.isSafeInteger(value.total) || value.total < 0 ||
          !Number.isSafeInteger(value.internal_fiches_complete) ||
          !Number.isSafeInteger(value.fields_complete) ||
          value.fields_complete < 0 || value.fields_complete > value.total ||
          !Number.isSafeInteger(value.classified_variants) ||
          value.classified_variants !== value.total ||
          value.channel_certified_by_this_audit !== 0 ||
          !value.quality_stage_counts ||
          Object.keys(value.quality_stage_counts).some(key => !(key in stageLabels)) ||
          !Object.keys(stageLabels).every(key => Number.isSafeInteger(value.quality_stage_counts[key]) && value.quality_stage_counts[key] >= 0) ||
          Object.values(value.quality_stage_counts).reduce((sum, n) => sum + n, 0) !== value.total ||
          !value.editorial_status || !value.gap_counts ||
          !value.monthly_review ||
          !Object.values(value.monthly_review).every(n => Number.isSafeInteger(n) && n >= 0) ||
          value.monthly_review.review_actions_performed_by_audit !== 0 ||
          value.monthly_review.ready_current + value.monthly_review.ready_overdue +
          value.monthly_review.ready_changed + value.monthly_review.ready_without_signoff +
          value.monthly_review.not_ready !== value.total ||
          value.monthly_review.ready_overdue + value.monthly_review.ready_changed +
          value.monthly_review.ready_without_signoff !== value.monthly_review.due ||
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
      if (!report) throw new Error("Previsualizá el informe antes de descargar.");
      const response = await request("/api/ecomm-app/workspace/reports/monthly/download", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ expected_fingerprint: report.preview_fingerprint, confirm: true }),
      });
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
      <button type="button" disabled={busy || !report || !csrf} onClick={() => void exportCsv()}>
        Confirmar y exportar pendientes (CSV)
      </button>
    </div>
    {error && <p role="alert">{error}</p>}
    {report && <div role="region" aria-label="Cobertura y excepciones">
      <p role="status">
        <strong>{report.total}</strong> variantes clasificadas ·{" "}
        <strong>{report.fields_complete}</strong> con todos los campos cargados
        (sin certificar) ·{" "}
        <strong>{report.internal_fiches_complete}</strong> además marcadas
        internamente como listas para canales ·{" "}
        <strong>{report.approved_claims_in_current_originals}</strong>{" "}
        hechos aprobados asociados a originales vigentes.
      </p>
      <p>
        La completitud de campos no equivale a validación documental, derechos
        de imagen ni aptitud de publicación. Esta auditoría no certifica ninguna
        salida a canales comerciales.
      </p>
      <section aria-label="Próxima acción por variante">
        <h5>Priorización automática del catálogo por excepciones</h5>
        <p>
          Cada variante se asigna a una única etapa prioritaria. Las etapas
          se calculan sobre la captura guardada, sin investigar proveedores,
          generar IA, modificar productos ni certificar identidades.
        </p>
        <ul>
          {Object.entries(stageLabels).map(([key, label]) => <li key={key}>
            {label}: <strong>{report.quality_stage_counts[key]}</strong>
          </li>)}
        </ul>
        <p>
          Cobertura clasificada: {report.classified_variants} de {report.total}.
          El CSV incluye la etapa por SKU para planificar lotes.
        </p>
      </section>
      <p>
        <strong>Revisión mensual:</strong> {report.monthly_review.ready_current} fichas vigentes,{" "}
        {report.monthly_review.due} pendientes de nueva revisión
        ({report.monthly_review.ready_overdue} vencidas por fecha,{" "}
        {report.monthly_review.ready_changed} modificadas después de revisar,{" "}
        {report.monthly_review.ready_without_signoff} sin constancia).
        Hay {report.monthly_review.not_ready} variantes aún sin ficha lista.
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
      <DocumentaryCohortPanel />
      <MonthlyReportPanel report={report} csrf={csrf} />
    </div>}
    <CommercialExportPanel ids={selectedIds} csrf={csrf} />
  </section>;
}
