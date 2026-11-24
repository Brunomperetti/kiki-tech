import { useEffect, useState } from "react";
import { request, captureDate } from "./catalog-adapter";
import { downloadReviewCsv } from "./csv-download";

const states = [
  "READY",
  "RESEARCH",
  "REVIEW_REQUIRED",
  "BLOCKED",
  "FAILED",
] as const;
type PipelineState = (typeof states)[number];
type Citation = {
  fact_id: string;
  document_id: string;
  document_version: number;
  quote: string;
  location: string;
  url?: string | null;
  document_sha256?: string | null;
};
type Claim = Citation & {
  field: string;
  value: string;
  unit: string | null;
  state: string;
  verified: boolean;
  blockers?: string[];
};
type PlannedField = {
  value: unknown;
  evidence_ids: string[];
  citations: Citation[];
};
export type ManufacturerPipelineReport = {
  mode: "SOURCE_INTAKE_PIPELINE_REPORT";
  schema_version: "kiki-documental-pipeline-v1";
  job_id: string;
  revision: number;
  fingerprint: string;
  total: number;
  summary: Record<PipelineState, number>;
  metrics: {
    processed: number;
    pending_facts: number;
    without_source: number;
    failed: number;
    attempts_total: number;
    ai_requests: 0;
    publication_writes: 0;
    duration_ms?: number;
  };
  items: {
    ecomm_id: string;
    sku: string | null;
    barcode: string | null;
    state: PipelineState;
    legacy_state: string;
    url: string;
    document_id: string | null;
    document_sha256: string | null;
    document_version?: number | null;
    document_digest?: string | null;
    processing_status: string;
    source_state?: string | null;
    claims: Claim[];
    plan: { fields: Record<string, PlannedField>; blocked_reasons: string[] };
    blockers: string[];
  }[];
  external_writes_enabled: false;
  history?: Array<{ action: string; at: string; by: string }>;
  quota?: {
    max_variants: number;
    max_attempts_per_item: number;
    source_daily_limit: string;
    ai: string;
  };
};

const labels: Record<PipelineState, string> = {
  READY: "Propuesta respaldada disponible",
  RESEARCH: "Requiere investigación",
  REVIEW_REQUIRED: "Candidatos por revisar",
  BLOCKED: "Bloqueado",
  FAILED: "Con fallo",
};
const fieldLabels: Record<string, string> = {
  title: "Título comercial",
  short_title: "Título corto",
  short_description: "Descripción corta",
  description: "Descripción larga",
  details: "Detalles",
  attributes: "Atributos",
  presentation: "Presentación",
  brand: "Marca",
  manufacturer: "Fabricante",
  category: "Categoría",
  subcategory: "Subcategoría",
  seo_title: "Título SEO",
  seo_description: "Descripción SEO",
  seo_keywords: "Palabras clave SEO",
};
const claimLabels: Record<string, string> = {
  ...fieldLabels,
  product_name: "Nombre documentado",
  ingredients: "Ingredientes",
  allergens: "Alérgenos",
  net_weight: "Contenido neto",
  characteristics: "Características",
  formulation: "Formulación",
  storage_conditions: "Conservación",
  commercial_claim: "Declaración comercial documentada",
  ean: "EAN documentado",
};
const claimStates: Record<string, string> = {
  PENDING: "Candidato pendiente de revisión",
  APPROVED: "Hecho con aprobación vigente",
  REJECTED: "Hecho rechazado",
  REVOKED: "Verificación revocada",
  STALE: "Verificación sin vigencia",
};
const count = (value: unknown): value is number =>
  Number.isSafeInteger(value) && Number(value) >= 0;
function validCitation(value: Citation) {
  return (
    value &&
    typeof value.fact_id === "string" &&
    !!value.fact_id &&
    typeof value.document_id === "string" &&
    !!value.document_id &&
    count(value.document_version) &&
    value.document_version >= 1 &&
    typeof value.quote === "string" &&
    !!value.quote &&
    typeof value.location === "string" &&
    !!value.location
  );
}
export function verifiedManufacturerReport(
  value: unknown,
  id: string,
  revision: number,
  expectedItems: Array<{ ecomm_id: string; url: string }>,
): ManufacturerPipelineReport {
  const report = value as ManufacturerPipelineReport;
  const expected = new Map(
    expectedItems.map((item) => [item.ecomm_id, item.url]),
  );
  if (
    !report ||
    report.mode !== "SOURCE_INTAKE_PIPELINE_REPORT" ||
    report.schema_version !== "kiki-documental-pipeline-v1" ||
    report.job_id !== id ||
    report.revision !== revision ||
    !/^[a-f0-9]{64}$/.test(report.fingerprint) ||
    report.external_writes_enabled !== false ||
    !Array.isArray(report.items) ||
    report.items.length < 1 ||
    report.items.length > 20 ||
    report.total !== report.items.length ||
    report.total !== expected.size ||
    expected.size !== expectedItems.length ||
    new Set(report.items.map((item) => item.ecomm_id)).size !== report.total ||
    !report.summary ||
    states.some(
      (state) =>
        !count(report.summary[state]) ||
        report.summary[state] !==
          report.items.filter((item) => item.state === state).length,
    ) ||
    !report.metrics ||
    ![
      report.metrics.processed,
      report.metrics.pending_facts,
      report.metrics.without_source,
      report.metrics.failed,
      report.metrics.attempts_total,
    ].every(count) ||
    report.metrics.processed > report.total ||
    report.metrics.without_source > report.total ||
    report.metrics.failed !== report.summary.FAILED ||
    report.metrics.ai_requests !== 0 ||
    report.metrics.publication_writes !== 0 ||
    (report.metrics.duration_ms !== undefined &&
      !count(report.metrics.duration_ms)) ||
    (report.quota !== undefined &&
      (!count(report.quota.max_variants) ||
        report.quota.max_variants < 1 ||
        report.quota.max_variants > 20 ||
        !count(report.quota.max_attempts_per_item) ||
        report.quota.max_attempts_per_item < 1 ||
        report.quota.max_attempts_per_item > 3 ||
        report.quota.ai !== "DISCONNECTED")) ||
    (report.history !== undefined &&
      (!Array.isArray(report.history) ||
        report.history.length > 512 ||
        report.history.some(
          (event) =>
            typeof event.action !== "string" ||
            typeof event.at !== "string" ||
            typeof event.by !== "string",
        ))) ||
    report.items.some(
      (item) =>
        !/^[1-9][0-9]*$/.test(item.ecomm_id) ||
        expected.get(item.ecomm_id) !== item.url ||
        !states.includes(item.state) ||
        (item.sku !== null && typeof item.sku !== "string") ||
        (item.barcode !== null && typeof item.barcode !== "string") ||
        typeof item.url !== "string" ||
        !item.url.startsWith("https://") ||
        typeof item.legacy_state !== "string" ||
        typeof item.processing_status !== "string" ||
        (item.document_sha256 !== null &&
          !/^[a-f0-9]{64}$/.test(item.document_sha256)) ||
        !Array.isArray(item.blockers) ||
        !Array.isArray(item.claims) ||
        item.claims.some(
          (claim) =>
            !validCitation(claim) ||
            typeof claim.field !== "string" ||
            typeof claim.value !== "string" ||
            typeof claim.state !== "string" ||
            !Object.keys(claimStates).includes(claim.state) ||
            typeof claim.verified !== "boolean" ||
            (claim.verified && claim.state !== "APPROVED"),
        ) ||
        !item.plan ||
        !item.plan.fields ||
        !Array.isArray(item.plan.blocked_reasons) ||
        Object.entries(item.plan.fields).some(
          ([key, field]) =>
            !Object.keys(fieldLabels).includes(key) ||
            !field ||
            !Array.isArray(field.evidence_ids) ||
            field.evidence_ids.length < 1 ||
            !Array.isArray(field.citations) ||
            field.citations.length < 1 ||
            field.citations.some((citation) => !validCitation(citation)) ||
            field.evidence_ids.some(
              (evidenceId) =>
                typeof evidenceId !== "string" ||
                !field.citations.some(
                  (citation) => citation.fact_id === evidenceId,
                ),
            ) ||
            field.citations.some(
              (citation) =>
                !field.evidence_ids.includes(citation.fact_id) ||
                !item.claims.some(
                  (claim) =>
                    claim.fact_id === citation.fact_id &&
                    claim.state === "APPROVED" &&
                    claim.verified === true &&
                    claim.document_id === citation.document_id &&
                    claim.document_version === citation.document_version &&
                    claim.quote === citation.quote &&
                    claim.location === citation.location,
                ),
            ),
        ) ||
        (item.state === "READY" && Object.keys(item.plan.fields).length === 0),
    ) ||
    states.reduce((sum, state) => sum + report.summary[state], 0) !==
      report.total
  ) {
    throw new Error(
      "El informe no coincide con la versión o las variantes del lote. Actualizá los estados antes de continuar.",
    );
  }
  return report;
}

export function ManufacturerPipelineSummary({
  jobId,
  revision,
  busy,
  expectedItems,
  onOpen,
}: {
  jobId: string;
  revision: number;
  busy: boolean;
  expectedItems: Array<{ ecomm_id: string; url: string }>;
  onOpen: (id: string) => void;
}) {
  const [report, setReport] = useState<ManufacturerPipelineReport>();
  const [refresh, reload] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const root = `/api/ecomm-app/workspace/sources/intake-jobs/${encodeURIComponent(jobId)}`;
  const selection = JSON.stringify(expectedItems);
  useEffect(() => {
    if (busy) {
      setReport(undefined);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setReport(undefined);
    setError("");
    setLoading(true);
    request(root + "/report", { signal: controller.signal })
      .then((response) => response.json())
      .then((value) => {
        if (!controller.signal.aborted)
          setReport(
            verifiedManufacturerReport(
              value,
              jobId,
              revision,
              JSON.parse(selection),
            ),
          );
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "No se pudo consultar el informe.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [root, jobId, revision, refresh, busy, selection]);

  async function exportExceptions() {
    if (!report || busy || exporting) return;
    setExporting(true);
    setError("");
    try {
      const query = new URLSearchParams({
        expected_revision: String(report.revision),
        expected_fingerprint: report.fingerprint,
      });
      const response = await request(root + "/exceptions.csv?" + query);
      if (
        !response.headers
          .get("Content-Type")
          ?.toLowerCase()
          .startsWith("text/csv")
      )
        throw new Error("La respuesta no es un CSV de excepciones.");
      downloadReviewCsv(
        await response.blob(),
        "kiki-lote-documental-excepciones.csv",
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "No se pudo exportar el informe.",
      );
    } finally {
      setExporting(false);
    }
  }

  return (
    <section
      className="b-detail"
      aria-label="Resultado documental del lote"
      style={{ overflowWrap: "anywhere" }}
    >
      <h4>Fuentes, hechos y propuesta por variante</h4>
      <p>
        Este informe separa incorporación, revisión y generación. READY
        significa que hay una propuesta determinista respaldada para revisar; no
        significa ficha completa ni publicación autorizada. OpenAI no participa
        en esta operación.
      </p>
      <button
        type="button"
        disabled={busy || loading || exporting}
        onClick={() => reload((value) => value + 1)}
      >
        Actualizar informe documental
      </button>
      {busy && (
        <p role="status">
          El informe se actualizará con la versión persistida al terminar o
          pausar los pasos actuales.
        </p>
      )}
      {loading && (
        <p role="status">Comprobando documentos y hechos vigentes…</p>
      )}
      {report && (
        <>
          <dl aria-label="Estados documentales del lote">
            {states.map((state) => (
              <div key={state}>
                <dt>
                  {labels[state]} ({state})
                </dt>
                <dd>{report.summary[state]}</dd>
              </div>
            ))}
          </dl>
          <p role="status">
            {report.metrics.processed} de {report.total} procesadas ·{" "}
            {report.metrics.pending_facts} hechos candidatos por revisar ·{" "}
            {report.metrics.without_source} sin fuente incorporada ·{" "}
            {report.metrics.failed} con fallo.
          </p>
          <p>
            {report.metrics.attempts_total} intentos registrados · 0 solicitudes
            OpenAI · 0 publicaciones. Cada fuente conserva su cuota y límite de
            reintentos; una excepción requiere decisión del operador.
          </p>
          {report.quota && (
            <p>
              Límite del lote: {report.quota.max_variants} variantes ·{" "}
              {report.quota.max_attempts_per_item} intentos como máximo por
              variante. Las cuotas diarias del importador existente siguen
              vigentes.
            </p>
          )}
          <p>
            {typeof report.metrics.duration_ms === "number" &&
            report.metrics.duration_ms > 0
              ? `Tiempo registrado de los pasos: ${report.metrics.duration_ms} ms.`
              : "Duración histórica no disponible; no se estima consumo de infraestructura."}
          </p>
          <button
            type="button"
            disabled={busy || exporting}
            onClick={() => void exportExceptions()}
          >
            Exportar excepciones del lote (CSV)
          </button>
          {exporting && <p role="status">Preparando excepciones…</p>}
          {report.items.map((item) => (
            <details
              key={item.ecomm_id}
              className="b-detail"
              data-pipeline-ecomm-id={item.ecomm_id}
            >
              <summary>
                Ecomm {item.ecomm_id} · SKU {item.sku || "sin SKU"} ·{" "}
                {labels[item.state]}
              </summary>
              <p>
                Estado documental: {item.state} · Incorporación:{" "}
                {item.legacy_state} · Extracción: {item.processing_status}
              </p>
              <p>
                Barcode original API: {item.barcode || "No informado"}. Nunca se
                hereda de otra presentación.
              </p>
              <p>
                URL fuente: <code>{item.url}</code>
              </p>
              <p>
                Procedencia de la fuente:{" "}
                {item.source_state === "REVIEWED"
                  ? "Revisada por una persona"
                  : item.source_state === "REJECTED" ||
                      item.source_state === "REVOKED"
                    ? "Rechazada o revocada"
                    : "Pendiente de revisión humana"}
                .
              </p>
              <p>
                Original: {item.document_id || "Sin documento archivado"} ·
                SHA-256: {item.document_sha256 || "No disponible"}
              </p>
              {item.blockers.map((reason, index) => (
                <p key={index} role="note">
                  {reason}
                </p>
              ))}
              <h5>Hechos con cita ({item.claims.length})</h5>
              {item.claims.length === 0 && (
                <p>No hay hechos documentales extraídos de esta fuente.</p>
              )}
              {item.claims.map((claim) => (
                <div key={claim.fact_id}>
                  <strong>
                    {Object.prototype.hasOwnProperty.call(
                      claimLabels,
                      claim.field,
                    )
                      ? claimLabels[claim.field]
                      : claim.field}
                    : {claim.value} {claim.unit || ""}
                  </strong>
                  <p>
                    {claim.state === "APPROVED" && !claim.verified
                      ? "Aprobación sin vigencia; revisar bloqueos"
                      : claimStates[claim.state] || claim.state}
                    {" · "}
                    {claim.document_id} v{claim.document_version} ·{" "}
                    {claim.location}
                  </p>
                  <blockquote>{claim.quote}</blockquote>
                  <p>
                    Fuente de este hecho:{" "}
                    <code>
                      {claim.url ||
                        "Sin URL declarada; revisar el original archivado"}
                    </code>
                  </p>
                  {claim.blockers?.map((reason, index) => (
                    <p key={index}>{reason}</p>
                  ))}
                </div>
              ))}
              <h5>Plan determinista desde hechos aprobados</h5>
              {Object.keys(item.plan.fields).length === 0 && (
                <p>
                  No hay campos respaldados disponibles para generar; revisá las
                  fuentes y los hechos pendientes.
                </p>
              )}
              {Object.entries(item.plan.fields).map(([field, proposal]) => (
                <details key={field}>
                  <summary>
                    {fieldLabels[field] || field} ·{" "}
                    {proposal.evidence_ids.length} hechos aprobados
                  </summary>
                  <p>
                    {typeof proposal.value === "string"
                      ? proposal.value
                      : JSON.stringify(proposal.value)}
                  </p>
                  {proposal.citations.map((citation) => (
                    <blockquote key={citation.fact_id}>
                      {citation.quote} · {citation.document_id} v
                      {citation.document_version} · {citation.location}
                    </blockquote>
                  ))}
                </details>
              ))}
              {item.plan.blocked_reasons.map((reason, index) => (
                <p key={index}>{reason}</p>
              ))}
              <button
                type="button"
                disabled={busy}
                onClick={() => onOpen(item.ecomm_id)}
              >
                Revisar esta variante y sus evidencias
              </button>
            </details>
          ))}
          {report.history && (
            <details
              className="b-detail"
              aria-label="Historial operativo del lote"
            >
              <summary>
                Eventos operativos conservados ({report.history.length})
              </summary>
              <p>
                Son constancias de procesamiento, no aprobaciones de hechos o
                fichas.
              </p>
              {report.history.map((event, index) => (
                <p key={`${event.at}-${index}`}>
                  {captureDate(event.at)} · {event.action} · {event.by}
                </p>
              ))}
            </details>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
