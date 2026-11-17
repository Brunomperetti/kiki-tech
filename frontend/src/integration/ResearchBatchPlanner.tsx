import { useState } from "react";
import { request } from "./catalog-adapter";

type Candidate = {
  ecomm_id: string;
  sku: string;
  name: string;
  presentation_original: string;
  gtin_lookup_hint: string;
  editorial_status: string;
  next_step: string;
};
type Plan = {
  mode: "READ_ONLY_RESEARCH_BATCH_PLAN";
  total_variants: number;
  classified_variants: number;
  eligible_total: number;
  batch_size: number;
  next_offset: number | null;
  offset: number;
  buckets: Record<string, number>;
  items: Candidate[];
  network_requests: 0;
  ai_requests: 0;
  external_writes_enabled: false;
  can_auto_fetch: false;
};
const labels: Record<string, string> = {
  identity_review: "Identidad para revisar",
  pack_review: "Packs y combos",
  name_missing: "Falta nombre de origen",
  presentation_missing: "Falta presentación",
  gtin_lookup_unavailable: "Sin código único válido en API",
  research_candidate: "Candidatos para investigar",
};

export function ResearchBatchPlanner({
  onSearch,
}: {
  onSearch: (sku: string) => void;
}) {
  const [plan, setPlan] = useState<Plan>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load(offset: number) {
    setBusy(true);
    setError("");
    try {
      const response = await request(
        `/api/ecomm-app/workspace/research/plan?limit=10&offset=${offset}`,
      );
      const result = (await response.json()) as Plan;
      if (
        result.mode !== "READ_ONLY_RESEARCH_BATCH_PLAN" ||
        result.network_requests !== 0 ||
        result.ai_requests !== 0 ||
        result.external_writes_enabled !== false ||
        result.can_auto_fetch !== false ||
        result.classified_variants !== result.total_variants ||
        Object.values(result.buckets).reduce((a, b) => a + b, 0) !==
          result.total_variants
      ) {
        throw new Error("El plan no refleja el catálogo completo y seguro.");
      }
      setPlan(result);
    } catch (exc) {
      setPlan(undefined);
      setError(
        exc instanceof Error ? exc.message : "No se pudo cargar el plan.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="k-research-plan">
      <summary>Planificar lotes de investigación verificable</summary>
      <p>
        Clasifica todas las variantes de Ecomm-App. Separa casos con identidad
        ambigua, packs y GTIN no conciliables. No consulta fabricantes, no
        consume IA ni guarda fichas.
      </p>
      <button type="button" disabled={busy} onClick={() => void load(0)}>
        {busy ? "Preparando lote…" : "Ver próximo lote de 10 productos"}
      </button>
      {error && <p role="alert">{error}</p>}
      {plan && (
        <section aria-label="Plan de investigación documental">
          <p role="status">
            <strong>{plan.classified_variants}</strong> de{" "}
            <strong>{plan.total_variants}</strong> variantes clasificadas.
            {" "}{plan.eligible_total} candidatas para comenzar búsquedas,
            sin fuentes oficiales todavía comprobadas.
          </p>
          <ul>
            {Object.entries(labels).map(([key, label]) => (
              <li key={key}>
                {label}: <strong>{plan.buckets[key] ?? 0}</strong>
              </li>
            ))}
          </ul>
          <p>
            Lote {plan.offset + 1}–{plan.offset + plan.batch_size} de{" "}
            {plan.eligible_total} productos investigables.
          </p>
          <ul>
            {plan.items.map((item) => (
              <li key={item.ecomm_id}>
                <strong>{item.name}</strong> · SKU {item.sku} · Ecomm{" "}
                {item.ecomm_id} · {item.presentation_original}.
                <small>
                  {" "}Código API para búsqueda: {item.gtin_lookup_hint}.
                  Pendiente encontrar y validar fabricante.
                </small>{" "}
                <button
                  type="button"
                  onClick={() => onSearch(item.sku)}
                >
                  Ver producto en catálogo
                </button>
              </li>
            ))}
          </ul>
          {plan.next_offset !== null && (
            <button type="button" disabled={busy}
              onClick={() => void load(plan.next_offset!)}>
              Próximos 10
            </button>
          )}
          {plan.offset > 0 && (
            <button type="button" disabled={busy}
              onClick={() => void load(Math.max(0, plan.offset - 10))}>
              Anteriores 10
            </button>
          )}
          <p>
            El código API no certifica fabricante. La búsqueda de fabricante y
            los textos comerciales necesitan original, citas y revisión.
          </p>
        </section>
      )}
    </details>
  );
}
