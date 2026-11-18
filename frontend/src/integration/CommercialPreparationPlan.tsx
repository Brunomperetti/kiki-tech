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
  CONFLICTING_APPROVED_FACTS: "La fuente aprobada contiene categorías contradictorias",
  SAVED_SOURCE_MISMATCH: "Categoría guardada diferente a la documentada",
  ALREADY_SAVED: "Categoría y subcategoría ya guardadas en la ficha",
  INCOMPLETE_SAVED: "La categoría de la ficha está incompleta",
  NO_APPROVED_CATEGORY: "Falta una categoría con evidencia aprobada",
  NO_APPROVED_SUBCATEGORY: "Falta una subcategoría con evidencia aprobada",
  NO_REVIEWED_PAIRS: "Sin categorías internas revisadas para comparar",
  EXACT_REVIEWED_PAIR: "Coincidencia exacta con una categoría interna existente",
  NEEDS_MAPPING: "Revisar equivalencia entre categoría del fabricante y KIKI",
};
const seoText: Record<string, string> = {
  EVIDENCE_BACKED: "Propuesta respaldada disponible",
  ALREADY_SAVED: "Guardado en ficha",
  REVALIDATE: "Requiere revalidación",
  NEEDS_EVIDENCE: "Sin respaldo suficiente",
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
};
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
    !report || report.mode !== "READ_ONLY_COMMERCIAL_EVIDENCE_PLAN" ||
    report.external_writes_enabled !== false || report.provider_calls !== 0 ||
    report.ai_requests !== 0 || report.facts_approved !== 0 ||
    report.automatic_publications !== 0 ||
    report.taxonomy_reference !== "KIKI_EDITORIAL_READY_FOR_CHANNELS_ONLY" ||
    !Number.isSafeInteger(report.reviewed_internal_pairs) ||
    !Array.isArray(report.items) || report.total !== report.items.length ||
    report.total < 1 || report.total > 20 ||
    report.items.some(item =>
      !selected.has(item.ecomm_id) || !taskText[item.next_task] ||
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
      Object.keys(seoLabels).some(k => !seoText[item.seo_fields[k]])
    )
  ) throw new Error("El resultado comercial no corresponde a esta selección.");
  return report;
}

export function CommercialPreparationPlan({
  ids, csrf, disabled, onOpen,
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
  useEffect(() => { setPlan(undefined); setError(""); }, [selectionKey]);

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
      const data = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(data.detail || "No se pudo auditar la selección.");
      setPlan(checked(data, selected));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al revisar los productos.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="b-detail" aria-label="Plan de fichas comerciales verificadas">
    <h3>Plan comercial desde evidencias</h3>
    <p>Analizá hasta 20 variantes antes de generar propuestas. KIKI compara categorías documentadas y aprobadas con las fichas internas marcadas listas para canales. Solo coincidencias exactas; no guarda ni asigna categorías, no usa IA y no publica.</p>
    <div className="b-actions">
      <button type="button" onClick={() => void inspect()}
        disabled={disabled || busy || ids.size < 1 || ids.size > 20}>
        {busy ? "Analizando evidencias…" : `Analizar ${ids.size} variantes`}
      </button>
      {ids.size > 20 && <p>Seleccioná hasta 20 variantes para este diagnóstico.</p>}
    </div>
    {error && <p role="alert">{error}</p>}
    {plan && <div role="region" aria-label="Resultado del plan comercial">
      <p><strong>{plan.total} variantes analizadas</strong> · {plan.counts.GENERATE || 0} con propuestas respaldadas posibles · {plan.counts.FIND_SOURCE || 0} sin documentación · {plan.counts.APPROVE_FACTS || 0} por validar.</p>
      <p>{plan.reviewed_internal_pairs} jerarquías internas marcadas listas para canales · {plan.taxonomy_counts.EXACT_REVIEWED_PAIR || 0} coincidencias exactas para revisión · {plan.taxonomy_counts.NEEDS_MAPPING || 0} equivalencias pendientes.</p>
      {plan.items.map(item => <article key={item.ecomm_id} className="b-detail">
        <strong>{item.name || `Ecomm ${item.ecomm_id}`}</strong>
        <p>Ecomm ID {item.ecomm_id} · {taskText[item.next_task]}</p>
        <p>{item.approved_facts} hechos aprobados vigentes · {item.fields_supported.length} campos comerciales respaldados para completar</p>
        <p><strong>Taxonomía:</strong> {taxonomyText[item.taxonomy_alignment.state]}</p>
        {item.taxonomy_alignment.exact_internal_reference && <p>
          Coincidencia interna para revisar: <strong>{item.taxonomy_alignment.exact_internal_reference.category} / {item.taxonomy_alignment.exact_internal_reference.subcategory}</strong>
          {" "}({item.taxonomy_alignment.reference_fiches} fichas marcadas listas). No se asignó ninguna categoría.
        </p>}
        <details>
          <summary>Ver campos y motivos</summary>
          <p><strong>Propuestas posibles:</strong> {item.fields_supported.join(", ") || "Ninguna por ahora"}</p>
          <p><strong>Sin respaldo suficiente:</strong> {item.fields_needing_support.join(", ") || "Sin campos faltantes detectados"}</p>
          <p><strong>Fuente aprobada:</strong> {item.taxonomy_alignment.source_approved.category || "Sin categoría"} / {item.taxonomy_alignment.source_approved.subcategory || "Sin subcategoría"}.</p>
          <p><strong>Ficha actual:</strong> {item.taxonomy_alignment.existing_editorial.category || "Sin categoría"} / {item.taxonomy_alignment.existing_editorial.subcategory || "Sin subcategoría"} ({item.taxonomy_alignment.existing_editorial.status}).</p>
          <p><strong>Evidencias de taxonomía:</strong> {item.taxonomy_alignment.source_evidence_ids.join(", ") || "Sin hechos aprobados"}</p>
          <p><strong>SEO:</strong> {Object.entries(seoLabels).map(([key, label]) => `${label}: ${seoText[item.seo_fields[key]]}`).join(" · ")}</p>
          {item.review_due && <p>Revisión mensual vencida o pendiente.</p>}
          {item.reasons.map((reason, i) => <p key={i}>{reason}</p>)}
        </details>
        <div className="b-actions">
          <button type="button" disabled={disabled || busy}
            onClick={() => onOpen(item.ecomm_id, "Evidencias")}>Revisar fuentes</button>
          <button type="button" disabled={disabled || busy}
            onClick={() => onOpen(item.ecomm_id, "Ficha")}>Abrir ficha</button>
        </div>
      </article>)}
    </div>}
  </section>;
}
