import { useEffect, useState } from "react";
import { request } from "./catalog-adapter";

const ENDPOINT = "/api/ecomm-app/workspace/commercial-plan/preview";

const taskText: Record<string, string> = {
  REVIEW_IDENTITY: "Revisar identidad o datos contradictorios",
  FIND_SOURCE: "Buscar documentación del producto",
  REVALIDATE: "Revalidar evidencia o revisión vencida",
  APPROVE_FACTS: "Revisar y aprobar hechos de la fuente",
  GENERATE: "Preparar propuesta comercial documentada",
  REVIEW_EDITORIAL: "Completar revisión editorial y multimedia",
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
  reasons: string[];
  review_due: boolean;
  human_review_required: true;
  commercial_fiche_saved: false;
};
type CommercialPlan = {
  mode: "READ_ONLY_COMMERCIAL_EVIDENCE_PLAN";
  total: number;
  counts: Record<string, number>;
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
    !Array.isArray(report.items) || report.total !== report.items.length ||
    report.total < 1 || report.total > 20 ||
    report.items.some(item =>
      !selected.has(item.ecomm_id) || !taskText[item.next_task] ||
      !Array.isArray(item.fields_supported) ||
      !Array.isArray(item.fields_needing_support) ||
      item.human_review_required !== true ||
      item.commercial_fiche_saved !== false
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
    <p>Analizá hasta 20 variantes antes de generar propuestas. KIKI muestra qué campos tienen respaldo vigente y qué tarea falta en cada producto. No guarda fichas, no usa IA y no publica.</p>
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
      {plan.items.map(item => <article key={item.ecomm_id} className="b-detail">
        <strong>{item.name || `Ecomm ${item.ecomm_id}`}</strong>
        <p>Ecomm ID {item.ecomm_id} · {taskText[item.next_task]}</p>
        <p>{item.approved_facts} hechos aprobados vigentes · {item.fields_supported.length} campos comerciales respaldados para completar</p>
        <details>
          <summary>Ver campos y motivos</summary>
          <p><strong>Propuestas posibles:</strong> {item.fields_supported.join(", ") || "Ninguna por ahora"}</p>
          <p><strong>Sin respaldo suficiente:</strong> {item.fields_needing_support.join(", ") || "Sin campos faltantes detectados"}</p>
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
