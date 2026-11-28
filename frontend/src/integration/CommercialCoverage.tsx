import { useEffect, useState } from "react";
import { CatalogError, request, validVariantId } from "./catalog-adapter";
import { fieldKeys, workspacePath } from "./workspace-adapter";

type Field = (typeof fieldKeys)[number];
const states = [
  "APPROVED_BACKED",
  "FILLED_UNBACKED",
  "BLOCKED",
  "PENDING_REVIEW",
] as const;
type State = (typeof states)[number];
const stateLabels: Record<State, string> = {
  APPROVED_BACKED: "Con respaldo vigente",
  FILLED_UNBACKED: "Contenido sin respaldo validado",
  BLOCKED: "Bloqueado · revisar",
  PENDING_REVIEW: "Pendiente de completar o revisar",
};
const labels: Record<Field, string> = {
  brand: "Marca",
  manufacturer: "Fabricante",
  title: "Título comercial",
  short_title: "Título corto",
  short_description: "Descripción corta",
  description: "Descripción larga",
  details: "Detalles y características",
  presentation: "Presentación",
  category: "Categoría",
  subcategory: "Subcategoría",
  seo_title: "Título SEO",
  seo_description: "Descripción SEO",
  seo_keywords: "Palabras clave SEO",
  proposed_gtin: "GTIN propuesto",
  note: "Nota interna (opcional)",
  attributes: "Atributos",
  media: "Imágenes y videos",
  sources: "Fuentes",
};
type Citation = {
  fact_id: string | null;
  document_id: string;
  document_version: number;
  document_hash: string;
  document_sha256: string | null;
  quote: string;
  location: string;
  state: "APPROVED";
  current: true;
  evidence_kind?: "MEDIA_RIGHTS";
};
type Row = {
  field: Field;
  state: State;
  filled: boolean;
  evidence_ids: string[];
  citations: Citation[];
  reasons: string[];
  field_review_required: boolean;
  limits: {
    maximum: number;
    length: number;
    unit: "characters" | "items";
    valid: boolean;
    reasons: string[];
  };
  lineage: {
    reviewer?: string;
    draft_id?: number;
    evidence_kind?: string;
  } | null;
};
export type Coverage = {
  schema_version: "kiki-saved-field-coverage-v1";
  ecomm_id: string;
  workspace_version: number;
  total_fields: 18;
  states: Record<State, number>;
  fields: Row[];
  fingerprint: string;
  commercial_completion_certified: false;
  publication_allowed: false;
};
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
const hash = (value: unknown) =>
  typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
/** Fail closed on mixed variant/version, partial coverage or unsupported green rows. */
export function adaptCommercialCoverage(
  value: unknown,
  id: string,
  version: number,
): Coverage {
  const data = value as Coverage;
  const rows = data?.fields;
  const invalid =
    !validVariantId(id) ||
    data?.schema_version !== "kiki-saved-field-coverage-v1" ||
    data.ecomm_id !== id ||
    data.workspace_version !== version ||
    data.total_fields !== 18 ||
    data.commercial_completion_certified !== false ||
    data.publication_allowed !== false ||
    !hash(data.fingerprint) ||
    !Array.isArray(rows) ||
    rows.length !== 18 ||
    new Set(rows?.map((row) => row?.field)).size !== 18 ||
    fieldKeys.some((key) => !rows?.some((row) => row?.field === key)) ||
    states.some(
      (state) =>
        !Number.isSafeInteger(data.states?.[state]) ||
        data.states[state] < 0 ||
        data.states[state] !==
          rows?.filter((row) => row?.state === state).length,
    ) ||
    rows?.some(
      (row) =>
        !row ||
        !states.includes(row.state) ||
        typeof row.filled !== "boolean" ||
        typeof row.field_review_required !== "boolean" ||
        (row.lineage !== null &&
          (!row.lineage ||
            typeof row.lineage !== "object" ||
            (row.lineage.reviewer !== undefined &&
              typeof row.lineage.reviewer !== "string") ||
            (row.lineage.draft_id !== undefined &&
              !Number.isSafeInteger(row.lineage.draft_id)) ||
            (row.lineage.evidence_kind !== undefined &&
              typeof row.lineage.evidence_kind !== "string"))) ||
        !strings(row.evidence_ids) ||
        !strings(row.reasons) ||
        !row.limits ||
        !Number.isSafeInteger(row.limits.length) ||
        row.limits.length < 0 ||
        !Number.isSafeInteger(row.limits.maximum) ||
        row.limits.maximum < 1 ||
        !["characters", "items"].includes(row.limits.unit) ||
        typeof row.limits.valid !== "boolean" ||
        !Array.isArray(row.citations) ||
        row.citations.some(
          (citation) =>
            !citation ||
            citation.state !== "APPROVED" ||
            citation.current !== true ||
            typeof citation.document_id !== "string" ||
            !Number.isSafeInteger(citation.document_version) ||
            citation.document_version < 1 ||
            !hash(citation.document_hash) ||
            (citation.document_sha256 !== null &&
              !hash(citation.document_sha256)) ||
            typeof citation.quote !== "string" ||
            !citation.quote.trim() ||
            typeof citation.location !== "string" ||
            !citation.location.trim() ||
            (citation.fact_id === null
              ? citation.evidence_kind !== "MEDIA_RIGHTS"
              : typeof citation.fact_id !== "string" ||
                !row.evidence_ids.includes(citation.fact_id)),
        ) ||
        row.evidence_ids.some(
          (factId) =>
            !row.citations.some((citation) => citation.fact_id === factId),
        ) ||
        (row.state === "APPROVED_BACKED" &&
          (!row.filled || !row.limits.valid || !row.citations.length)),
    );
  if (invalid)
    throw new CatalogError(
      0,
      "La cobertura recibida no corresponde a los 18 campos y la versión actual de esta variante. Volvé a consultar.",
    );
  return data;
}

export function CommercialCoverage({
  data,
  dirty = false,
  onRefresh,
  onReview,
}: {
  data: Coverage;
  dirty?: boolean;
  onRefresh?: () => void;
  onReview?: (tab: string) => void;
}) {
  const [filter, setFilter] = useState<State | "ALL">("ALL");
  return (
    <section
      className="research-card"
      aria-label="Cobertura comercial de 18 campos"
    >
      <h3>Cobertura comercial · 18 campos</h3>
      <p>
        Información guardada y respaldo vigente son distintos. Esta revisión no
        aprueba la ficha completa ni autoriza publicaciones.
      </p>
      {dirty && (
        <p role="status">
          Hay cambios sin guardar. Esta cobertura corresponde a la última
          versión guardada ({data.workspace_version}).
        </p>
      )}
      <div className="research-actions" aria-label="Filtrar cobertura">
        <button
          type="button"
          aria-pressed={filter === "ALL"}
          onClick={() => setFilter("ALL")}
        >
          Todos · 18
        </button>
        {states.map((state) => (
          <button
            key={state}
            type="button"
            aria-pressed={filter === state}
            onClick={() => setFilter(state)}
          >
            {stateLabels[state]} · {data.states[state]}
          </button>
        ))}
      </div>
      <details>
        <summary>Ver campos, límites y evidencias</summary>
        {data.fields
          .filter((row) => filter === "ALL" || row.state === filter)
          .map((row) => (
            <article key={row.field} className="research-card">
              <h4>
                {labels[row.field]} · {stateLabels[row.state]}
              </h4>
              <p>
                {row.filled
                  ? "Con contenido guardado"
                  : "Sin contenido guardado"}{" "}
                · {row.limits.length}/{row.limits.maximum}{" "}
                {row.limits.unit === "characters" ? "caracteres" : "elementos"}
              </p>
              {row.field_review_required && row.state === "APPROVED_BACKED" && (
                <p>
                  Hechos documentales aprobados; conservar la revisión humana de
                  la redacción.
                </p>
              )}
              {row.reasons.map((reason, index) => (
                <p key={index}>{reason}</p>
              ))}
              {row.lineage?.draft_id && (
                <p>
                  Propuesta #{row.lineage.draft_id} · Revisión:{" "}
                  {row.lineage.reviewer}
                </p>
              )}
              {row.lineage?.evidence_kind === "INTERNAL_TAXONOMY_DECISION" && (
                <p>
                  Clasificación interna revisada por{" "}
                  {row.lineage.reviewer || "operador"}; no es una declaración
                  del fabricante.
                </p>
              )}
              {row.citations.map((citation, index) => (
                <blockquote key={index}>
                  <p>{citation.quote}</p>
                  <small>
                    Documento {citation.document_id} · versión{" "}
                    {citation.document_version} · {citation.location}
                    {citation.fact_id
                      ? ` · Hecho ${citation.fact_id}`
                      : " · Permiso de uso"}
                  </small>
                  {citation.document_sha256 && (
                    <p style={{ overflowWrap: "anywhere" }}>
                      SHA-256: {citation.document_sha256}
                    </p>
                  )}
                </blockquote>
              ))}
              {row.state !== "APPROVED_BACKED" && onReview && (
                <button
                  type="button"
                  onClick={() =>
                    onReview(
                      row.filled && row.field !== "media" ? "IA" : "Evidencias",
                    )
                  }
                >
                  Revisar {labels[row.field].toLowerCase()}
                </button>
              )}
            </article>
          ))}
      </details>
      {onRefresh && (
        <button type="button" onClick={onRefresh}>
          Actualizar cobertura guardada
        </button>
      )}
    </section>
  );
}

export function CommercialCoveragePanel({
  id,
  revision,
  dirty,
  onReview,
}: {
  id: string;
  revision: number;
  dirty?: boolean;
  onReview?: (tab: string) => void;
}) {
  const [data, setData] = useState<Coverage>();
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(undefined);
    setError("");
    request(workspacePath(id) + "/commercial-coverage", {
      signal: controller.signal,
    })
      .then((response) => response.json())
      .then((value) => {
        if (!controller.signal.aborted)
          setData(adaptCommercialCoverage(value, id, revision));
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof Error
              ? cause.message
              : "No se pudo consultar la cobertura.",
          );
      });
    return () => controller.abort();
  }, [id, revision, reload]);
  if (data?.ecomm_id === id && data.workspace_version === revision)
    return (
      <CommercialCoverage
        data={data}
        dirty={dirty}
        onReview={onReview}
        onRefresh={() => setReload((value) => value + 1)}
      />
    );
  return (
    <section
      className="research-card"
      aria-label="Cobertura comercial de 18 campos"
    >
      <h3>Cobertura comercial · 18 campos</h3>
      {error ? (
        <>
          <p role="alert">{error}</p>
          <button type="button" onClick={() => setReload((value) => value + 1)}>
            Reintentar cobertura
          </button>
        </>
      ) : (
        <p role="status">Consultando respaldo de la ficha guardada…</p>
      )}
    </section>
  );
}
