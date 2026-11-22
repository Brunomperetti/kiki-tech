import { useEffect, useState } from "react";
import { request } from "./catalog-adapter";

const ENDPOINT = "/api/ecomm-app/workspace/commercial-plan/preview";

const taskText: Record<string, string> = {
  REVIEW_IDENTITY: "Revisar identidad o datos contradictorios",
  FIND_SOURCE: "Buscar documentación del producto",
  REVALIDATE: "Revalidar evidencia o revisión vencida",
  APPROVE_FACTS: "Revisar y aprobar hechos de la fuente",
  REVIEW_TAXONOMY: "Revisar equivalencia entre categorías de fabricante y KIKI",
  GENERATE: "Preparar propuesta comercial documentada",
  REVIEW_EDITORIAL: "Completar revisión editorial y multimedia",
};

const taxonomyText: Record<string, string> = {
  BLOCKED_EVIDENCE: "Revisar identidad o vigencia antes de clasificar",
  CONFLICTING_APPROVED_FACTS:
    "La fuente aprobada contiene categorías contradictorias",
  SAVED_SOURCE_MISMATCH: "Categoría guardada diferente a la documentada",
  ALREADY_SAVED: "Categoría y subcategoría ya guardadas en la ficha",
  INCOMPLETE_SAVED: "La categoría de la ficha está incompleta",
  NO_APPROVED_CATEGORY: "Falta una categoría con evidencia aprobada",
  NO_APPROVED_SUBCATEGORY: "Falta una subcategoría con evidencia aprobada",
  NO_REVIEWED_PAIRS: "Sin categorías internas revisadas para comparar",
  EXACT_REVIEWED_PAIR:
    "Coincidencia exacta con una categoría interna existente",
  NEEDS_MAPPING: "Revisar equivalencia entre categoría del fabricante y KIKI",
  REVIEWED_INTERNAL_MAPPING:
    "Equivalencia interna revisada por una persona y versionada",
};
const seoText: Record<string, string> = {
  EVIDENCE_BACKED: "Propuesta respaldada disponible",
  ALREADY_SAVED: "Guardado en ficha",
  REVALIDATE: "Requiere revalidación",
  NEEDS_EVIDENCE: "Sin respaldo suficiente",
  REVIEW_TAXONOMY: "Revisar categorías antes de utilizar estas palabras clave",
};
const seoLabels: Record<string, string> = {
  seo_title: "Título SEO",
  seo_description: "Meta-descripción",
  seo_keywords: "Palabras clave",
};

type TaxonomyAlignment = {
  state: string;
  label: string;
  source_approved: { category: string | null; subcategory: string | null };
  source_evidence_ids: string[];
  existing_editorial: { category: string; subcategory: string; status: string };
  exact_internal_reference: { category: string; subcategory: string } | null;
  reference_fiches: number;
  operator_review_required: true;
  mapping_saved: false;
  external_category_ids: null;
  reviewed_mapping?: TaxonomyState;
};
type TaxonomyState = {
  ecomm_id: string;
  channel: "KIKI" | "ECOMM" | "ML" | "TN";
  state: "NONE" | "APPROVED" | "REVOKED" | "STALE" | "BLOCKED";
  mapping_version: number;
  expected_version: number;
  expected_workspace_version: number;
  evidence_fingerprint: string;
  can_approve: boolean;
  source_pair: { category: string; subcategory: string } | null;
  record: null | {
    decision: "APPROVED" | "REVOKED";
    taxonomy_revision: string;
    target_pair: { category: string; subcategory: string };
    reviewer: string;
  };
  external_writes_enabled?: false;
  official_external_category_verified: false;
};

function TaxonomyReviewForm({
  id,
  csrf,
  disabled,
  onSaved,
}: {
  id: string;
  csrf: string;
  disabled: boolean;
  onSaved: () => Promise<void>;
}) {
  const [channel, setChannel] = useState<TaxonomyState["channel"]>("KIKI");
  const [data, setData] = useState<TaxonomyState>();
  const [revision, setRevision] = useState("");
  const [category, setCategory] = useState("");
  const [subcategory, setSubcategory] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setData(undefined);
    setConfirmed(false);
    setError("");
  }, [id, channel]);

  function checkedState(value: unknown): TaxonomyState {
    const result = value as TaxonomyState;
    if (
      !result ||
      result.ecomm_id !== id ||
      result.channel !== channel ||
      !["NONE", "APPROVED", "REVOKED", "STALE", "BLOCKED"].includes(
        result.state,
      ) ||
      !Number.isSafeInteger(result.expected_version) ||
      !Number.isSafeInteger(result.expected_workspace_version) ||
      !/^[a-f0-9]{64}$/.test(result.evidence_fingerprint) ||
      result.external_writes_enabled !== false ||
      result.official_external_category_verified !== false
    )
      throw new Error(
        "La clasificación no corresponde a esta variante y canal.",
      );
    return result;
  }
  async function load() {
    setBusy(true);
    setError("");
    try {
      const response = await request(
        `/api/ecomm-app/workspace/${encodeURIComponent(id)}/taxonomy-review?channel=${channel}`,
      );
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          body.detail || "No se pudo recuperar la clasificación.",
        );
      const state = checkedState(body);
      setData(state);
      setRevision(state.record?.taxonomy_revision || "");
      setCategory(
        state.record?.target_pair.category || state.source_pair?.category || "",
      );
      setSubcategory(
        state.record?.target_pair.subcategory ||
          state.source_pair?.subcategory ||
          "",
      );
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(decision: "APPROVED" | "REVOKED") {
    if (!data || !confirmed || busy || disabled) return;
    setBusy(true);
    setError("");
    try {
      const response = await request(
        `/api/ecomm-app/workspace/${encodeURIComponent(id)}/taxonomy-review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({
            expected_version: data.expected_version,
            expected_workspace_version: data.expected_workspace_version,
            expected_fingerprint: data.evidence_fingerprint,
            channel,
            decision,
            taxonomy_revision: revision,
            target_category: category,
            target_subcategory: subcategory,
            reason,
            confirm: true,
          }),
        },
      );
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          body.detail ||
            "No se guardó la revisión; recuperá la versión actual.",
        );
      setData(checkedState(body));
      setConfirmed(false);
      await onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const valid =
    confirmed &&
    reason.trim().length >= 20 &&
    revision.trim() &&
    category.trim() &&
    subcategory.trim();
  return (
    <details aria-label={`Clasificación versionada ${id}`}>
      <summary>Revisar y guardar clasificación versionada</summary>
      <p>
        La clasificación conserva la fuente del fabricante separada de la
        jerarquía comercial. No cambia la ficha ni publica en canales.
      </p>
      <label>
        Destino de la clasificación{" "}
        <select
          value={channel}
          disabled={busy || disabled}
          onChange={(event) =>
            setChannel(event.target.value as TaxonomyState["channel"])
          }
        >
          <option value="KIKI">KIKI</option>
          <option value="ECOMM">Ecomm-App</option>
          <option value="ML">Mercado Libre</option>
          <option value="TN">Tiendanube</option>
        </select>
      </label>
      <button
        type="button"
        onClick={() => void load()}
        disabled={busy || disabled}
      >
        Recuperar clasificación y evidencias
      </button>
      {error && <p role="alert">{error}</p>}
      {data && (
        <fieldset disabled={busy || disabled}>
          <p>
            Versión {data.mapping_version} ·{" "}
            {data.state === "APPROVED"
              ? "Revisión vigente"
              : data.state === "NONE"
                ? "Sin revisión guardada"
                : data.state === "REVOKED"
                  ? "Revisión revocada"
                  : "Requiere nueva revisión"}
          </p>
          <p>
            Fuente aprobada:{" "}
            {data.source_pair
              ? `${data.source_pair.category} / ${data.source_pair.subcategory}`
              : "Faltan categoría y subcategoría documentales aprobadas vigentes"}
            .
          </p>
          {data.record && (
            <p>
              Revisión anterior: {data.record.reviewer} · vocabulario{" "}
              {data.record.taxonomy_revision}.
            </p>
          )}
          <label>
            Versión del vocabulario revisado{" "}
            <input
              value={revision}
              maxLength={100}
              onChange={(e) => setRevision(e.target.value)}
            />
          </label>
          <label>
            Categoría comercial{" "}
            <input
              value={category}
              maxLength={160}
              onChange={(e) => setCategory(e.target.value)}
            />
          </label>
          <label>
            Subcategoría comercial{" "}
            <input
              value={subcategory}
              maxLength={160}
              onChange={(e) => setSubcategory(e.target.value)}
            />
          </label>
          <label>
            Motivo y comprobación{" "}
            <textarea
              value={reason}
              maxLength={600}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Confirmo que revisé esta variante, su presentación y las citas
            documentales.
          </label>
          <p>
            Los identificadores oficiales de categorías de cada canal requieren
            comprobación independiente. Guardar esta decisión no los verifica.
          </p>
          <button
            type="button"
            disabled={!valid || !data.can_approve}
            onClick={() => void save("APPROVED")}
          >
            Guardar revisión humana
          </button>
          <button
            type="button"
            disabled={!valid || data.record?.decision !== "APPROVED"}
            onClick={() => void save("REVOKED")}
          >
            Revocar revisión
          </button>
        </fieldset>
      )}
    </details>
  );
}
type PlanItem = {
  ecomm_id: string;
  name: string;
  presentation?: string | null;
  next_task: string;
  next_task_label: string;
  approved_facts: number;
  fields_supported: string[];
  fields_needing_support: string[];
  taxonomy_alignment: TaxonomyAlignment;
  seo_fields: Record<string, string>;
  reasons: string[];
  review_due: boolean;
  human_review_required: true;
  commercial_fiche_saved: false;
};
type CommercialPlan = {
  mode: "READ_ONLY_COMMERCIAL_EVIDENCE_PLAN";
  total: number;
  counts: Record<string, number>;
  taxonomy_counts: Record<string, number>;
  reviewed_internal_pairs: number;
  taxonomy_reference: "KIKI_EDITORIAL_READY_FOR_CHANNELS_ONLY";
  items: PlanItem[];
  external_writes_enabled: false;
  provider_calls: 0;
  ai_requests: 0;
  facts_approved: 0;
  automatic_publications: 0;
};

function checked(data: unknown, selected: Set<string>): CommercialPlan {
  const report = data as CommercialPlan;
  if (
    !report ||
    report.mode !== "READ_ONLY_COMMERCIAL_EVIDENCE_PLAN" ||
    report.external_writes_enabled !== false ||
    report.provider_calls !== 0 ||
    report.ai_requests !== 0 ||
    report.facts_approved !== 0 ||
    report.automatic_publications !== 0 ||
    report.taxonomy_reference !== "KIKI_EDITORIAL_READY_FOR_CHANNELS_ONLY" ||
    !Number.isSafeInteger(report.reviewed_internal_pairs) ||
    !Array.isArray(report.items) ||
    report.total !== report.items.length ||
    report.total < 1 ||
    report.total > 20 ||
    report.items.some(
      (item) =>
        !selected.has(item.ecomm_id) ||
        !taskText[item.next_task] ||
        !Array.isArray(item.fields_supported) ||
        !Array.isArray(item.fields_needing_support) ||
        item.human_review_required !== true ||
        item.commercial_fiche_saved !== false ||
        !item.taxonomy_alignment ||
        !taxonomyText[item.taxonomy_alignment.state] ||
        item.taxonomy_alignment.operator_review_required !== true ||
        item.taxonomy_alignment.mapping_saved !== false ||
        item.taxonomy_alignment.external_category_ids !== null ||
        !item.seo_fields ||
        Object.keys(seoLabels).some((k) => !seoText[item.seo_fields[k]]),
    )
  )
    throw new Error("El resultado comercial no corresponde a esta selección.");
  return report;
}

export function CommercialPreparationPlan({
  ids,
  csrf,
  disabled,
  onOpen,
}: {
  ids: Set<string>;
  csrf: string;
  disabled: boolean;
  onOpen: (id: string, tab: "Ficha" | "Evidencias") => void;
}) {
  const [plan, setPlan] = useState<CommercialPlan>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectionKey = [...ids].sort().join(",");
  useEffect(() => {
    setPlan(undefined);
    setError("");
  }, [selectionKey]);

  async function inspect() {
    if (disabled || busy || ids.size < 1 || ids.size > 20) return;
    const selected = new Set(ids);
    setBusy(true);
    setError("");
    setPlan(undefined);
    try {
      const response = await request(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ ecomm_ids: [...selected] }),
      });
      const data = (await response.json()) as { detail?: string };
      if (!response.ok)
        throw new Error(data.detail || "No se pudo auditar la selección.");
      setPlan(checked(data, selected));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Error al revisar los productos.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="b-detail"
      aria-label="Plan de fichas comerciales verificadas"
    >
      <h3>Plan comercial desde evidencias</h3>
      <p>
        Analizá hasta 20 variantes antes de generar propuestas. KIKI compara
        categorías documentadas y aprobadas con las fichas internas marcadas
        listas para canales. La previsualización no modifica fichas. Podés
        registrar por separado una equivalencia humana versionada; no se
        aplica automáticamente ni publica en canales.
      </p>
      <div className="b-actions">
        <button
          type="button"
          onClick={() => void inspect()}
          disabled={disabled || busy || ids.size < 1 || ids.size > 20}
        >
          {busy ? "Analizando evidencias…" : `Analizar ${ids.size} variantes`}
        </button>
        {ids.size > 20 && (
          <p>Seleccioná hasta 20 variantes para este diagnóstico.</p>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {plan && (
        <div role="region" aria-label="Resultado del plan comercial">
          <p>
            <strong>{plan.total} variantes analizadas</strong> ·{" "}
            {plan.counts.GENERATE || 0} con propuestas respaldadas posibles ·{" "}
            {plan.counts.FIND_SOURCE || 0} sin documentación ·{" "}
            {plan.counts.APPROVE_FACTS || 0} por validar.
          </p>
          <p>
            {plan.reviewed_internal_pairs} jerarquías internas marcadas listas
            para canales · {plan.taxonomy_counts.EXACT_REVIEWED_PAIR || 0}{" "}
            coincidencias exactas para revisión ·{" "}
            {plan.taxonomy_counts.NEEDS_MAPPING || 0} equivalencias pendientes.
          </p>
          {plan.items.map((item) => (
            <article key={item.ecomm_id} className="b-detail">
              <strong>{item.name || `Ecomm ${item.ecomm_id}`}</strong>
              <p>
                Ecomm ID {item.ecomm_id} · {taskText[item.next_task]}
              </p>
              <p>
                {item.approved_facts} hechos aprobados vigentes ·{" "}
                {item.fields_supported.length} campos comerciales respaldados
                para completar
              </p>
              <p>
                <strong>Taxonomía:</strong>{" "}
                {taxonomyText[item.taxonomy_alignment.state]}
              </p>
              {item.taxonomy_alignment.reviewed_mapping?.state ===
                "APPROVED" && (
                <p>
                  Clasificación interna revisada:{" "}
                  {
                    item.taxonomy_alignment.reviewed_mapping.record?.target_pair
                      .category
                  }{" "}
                  /{" "}
                  {
                    item.taxonomy_alignment.reviewed_mapping.record?.target_pair
                      .subcategory
                  }
                  {" · "}vocabulario{" "}
                  {
                    item.taxonomy_alignment.reviewed_mapping.record
                      ?.taxonomy_revision
                  }
                  . La categoría del fabricante conserva sus citas originales.
                </p>
              )}
              {item.taxonomy_alignment.exact_internal_reference && (
                <p>
                  Coincidencia interna para revisar:{" "}
                  <strong>
                    {item.taxonomy_alignment.exact_internal_reference.category}{" "}
                    /{" "}
                    {
                      item.taxonomy_alignment.exact_internal_reference
                        .subcategory
                    }
                  </strong>{" "}
                  ({item.taxonomy_alignment.reference_fiches} fichas marcadas
                  listas). No se asignó ninguna categoría.
                </p>
              )}
              <details>
                <summary>Ver campos y motivos</summary>
                <p>
                  <strong>Propuestas posibles:</strong>{" "}
                  {item.fields_supported.join(", ") || "Ninguna por ahora"}
                </p>
                <p>
                  <strong>Sin respaldo suficiente:</strong>{" "}
                  {item.fields_needing_support.join(", ") ||
                    "Sin campos faltantes detectados"}
                </p>
                <p>
                  <strong>Fuente aprobada:</strong>{" "}
                  {item.taxonomy_alignment.source_approved.category ||
                    "Sin categoría"}{" "}
                  /{" "}
                  {item.taxonomy_alignment.source_approved.subcategory ||
                    "Sin subcategoría"}
                  .
                </p>
                <p>
                  <strong>Ficha actual:</strong>{" "}
                  {item.taxonomy_alignment.existing_editorial.category ||
                    "Sin categoría"}{" "}
                  /{" "}
                  {item.taxonomy_alignment.existing_editorial.subcategory ||
                    "Sin subcategoría"}{" "}
                  ({item.taxonomy_alignment.existing_editorial.status}).
                </p>
                <p>
                  <strong>Evidencias de taxonomía:</strong>{" "}
                  {item.taxonomy_alignment.source_evidence_ids.join(", ") ||
                    "Sin hechos aprobados"}
                </p>
                <p>
                  <strong>SEO:</strong>{" "}
                  {Object.entries(seoLabels)
                    .map(
                      ([key, label]) =>
                        `${label}: ${seoText[item.seo_fields[key]]}`,
                    )
                    .join(" · ")}
                </p>
                {item.review_due && (
                  <p>Revisión mensual vencida o pendiente.</p>
                )}
                {item.reasons.map((reason, i) => (
                  <p key={i}>{reason}</p>
                ))}
              </details>
              <TaxonomyReviewForm
                id={item.ecomm_id}
                csrf={csrf}
                disabled={disabled || busy}
                onSaved={inspect}
              />
              <div className="b-actions">
                <button
                  type="button"
                  disabled={disabled || busy}
                  onClick={() => onOpen(item.ecomm_id, "Evidencias")}
                >
                  Revisar fuentes
                </button>
                <button
                  type="button"
                  disabled={disabled || busy}
                  onClick={() => onOpen(item.ecomm_id, "Ficha")}
                >
                  Abrir ficha
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
