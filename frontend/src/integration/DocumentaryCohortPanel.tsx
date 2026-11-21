import { useState } from "react";
import { request } from "./catalog-adapter";
import { downloadReviewCsv } from "./csv-download";

type CohortItem = {
  ecomm_id: string;
  sku: string;
  name: string;
  presentation: string;
  gtin_lookup_hint: string;
  captured_at: string | null;
  source_url: null;
  next_step: "REVISAR_FABRICANTE_Y_URL_OFICIAL";
};
type Cohort = {
  id: string;
  brand_phrase: string;
  brand_verified: false;
  manufacturer_verified: false;
  source_urls_verified: 0;
  count: number;
  items: CohortItem[];
};
type CohortPlan = {
  mode: "READ_ONLY_DOCUMENTARY_COHORTS";
  source: "ECOMM_APP_API_STAGE";
  capture_fingerprint: string;
  plan_fingerprint: string;
  total_variants: number;
  eligible_to_look_up: number;
  grouped_variants: number;
  cohort_count: number;
  unattributed: number;
  ambiguous_brand_mentions: number;
  pack_text_suspects: number;
  barcode_not_eligible_for_research: number;
  other_quality_stages: number;
  max_per_cohort: 20;
  network_requests: 0;
  ai_requests: 0;
  db_writes: 0;
  external_writes_enabled: false;
  can_auto_fetch: false;
  brand_hints_verified: false;
  cohorts: Cohort[];
};

const whole = (x: unknown) => Number.isSafeInteger(x) && Number(x) >= 0;
const validCohortPlan = (p: CohortPlan): boolean => {
  if (
    p.mode !== "READ_ONLY_DOCUMENTARY_COHORTS" ||
    p.source !== "ECOMM_APP_API_STAGE" ||
    !/^[a-f0-9]{64}$/.test(p.capture_fingerprint || "") ||
    !/^[a-f0-9]{64}$/.test(p.plan_fingerprint || "") ||
    p.max_per_cohort !== 20 ||
    p.network_requests !== 0 || p.ai_requests !== 0 || p.db_writes !== 0 ||
    p.external_writes_enabled !== false || p.can_auto_fetch !== false ||
    p.brand_hints_verified !== false ||
    ![
      p.total_variants, p.eligible_to_look_up, p.grouped_variants,
      p.cohort_count, p.unattributed, p.ambiguous_brand_mentions,
      p.pack_text_suspects, p.barcode_not_eligible_for_research,
      p.other_quality_stages,
    ].every(whole) ||
    !Array.isArray(p.cohorts) || p.cohort_count !== p.cohorts.length ||
    p.eligible_to_look_up !==
      p.grouped_variants + p.unattributed + p.ambiguous_brand_mentions +
      p.pack_text_suspects ||
    p.total_variants !==
      p.eligible_to_look_up + p.barcode_not_eligible_for_research +
      p.other_quality_stages
  ) return false;
  const ids = new Set<string>();
  let count = 0;
  for (const group of p.cohorts) {
    if (
      !group.id || !group.brand_phrase ||
      group.brand_verified !== false || group.manufacturer_verified !== false ||
      group.source_urls_verified !== 0 ||
      !whole(group.count) || group.count < 1 || group.count > 20 ||
      !Array.isArray(group.items) || group.items.length !== group.count
    ) return false;
    for (const item of group.items) {
      if (
        !item.ecomm_id || !item.sku || !item.name || !item.presentation ||
        !item.gtin_lookup_hint || item.source_url !== null ||
        item.next_step !== "REVISAR_FABRICANTE_Y_URL_OFICIAL" ||
        ids.has(item.ecomm_id)
      ) return false;
      ids.add(item.ecomm_id);
      count++;
    }
  }
  return count === p.grouped_variants;
};

export function DocumentaryCohortPanel() {
  const [plan, setPlan] = useState<CohortPlan>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    if (busy) return;
    setBusy(true);
    setError("");
    setPlan(undefined);
    try {
      const response = await request("/api/ecomm-app/workspace/research/documentary-cohorts");
      const value = await response.json() as CohortPlan & {detail?: string};
      if (!response.ok) throw new Error(value.detail || "No se pudieron preparar los lotes.");
      if (!validCohortPlan(value))
        throw new Error("El plan no clasifica todas las variantes; no se muestran lotes parciales.");
      setPlan(value);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo preparar el plan.");
    } finally {
      setBusy(false);
    }
  }

  async function exportCsv() {
    if (busy || !plan) return;
    setBusy(true);
    setError("");
    try {
      const response = await request("/api/ecomm-app/workspace/research/documentary-cohorts.csv");
      if (!response.ok) throw new Error("No se pudo exportar la selección.");
      if (response.headers.get("X-Kiki-Source-Fingerprint") !== plan.capture_fingerprint)
        throw new Error("La captura de Ecomm cambió; prepará nuevamente los lotes antes de exportar.");
      if (response.headers.get("X-Kiki-Cohort-Plan-Fingerprint") !== plan.plan_fingerprint)
        throw new Error("Cambió la selección de productos o sus documentos; prepará nuevamente los lotes.");
      if (response.headers.get("X-Kiki-Documentary-Cohorts") !== String(plan.cohort_count))
        throw new Error("Los lotes cambiaron; repetí la planificación.");
      downloadReviewCsv(await response.blob(), "kiki-lotes-documentales-no-verificados.csv");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de exportación.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details>
      <summary>Preparar lotes documentales por marca mencionada (sin consultar fabricantes)</summary>
      <p>
        Agrupa hasta 20 variantes por lote usando únicamente el nombre de la
        última captura Ecomm-App. La marca es una <strong>pista sin verificar</strong>.
        No descarga fuentes, no crea trabajos persistentes ni modifica productos.
      </p>
      <div className="b-actions">
        <button type="button" disabled={busy} onClick={() => void load()}>
          {busy ? "Clasificando…" : "Preparar lotes de hasta 20"}
        </button>
        <button type="button" disabled={busy || !plan} onClick={() => void exportCsv()}>
          Exportar estos lotes (CSV)
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {plan && <div role="region" aria-label="Lotes documentales candidatos">
        <p role="status">
          <strong>{plan.grouped_variants}</strong> variantes en{" "}
          <strong>{plan.cohort_count}</strong> lotes de hasta 20 ·{" "}
          {plan.eligible_to_look_up} elegibles para buscar fuente con código API.
        </p>
        <p>
          Sin marca textual atribuible: {plan.unattributed} ·{" "}
          marcas ambiguas: {plan.ambiguous_brand_mentions} ·{" "}
          posibles packs: {plan.pack_text_suspects} ·{" "}
          códigos no aptos para investigación: {plan.barcode_not_eligible_for_research}.
        </p>
        <p>
          Huella de captura: <code>{plan.capture_fingerprint.slice(0, 12)}</code> ·{" "}
          huella de selección: <code>{plan.plan_fingerprint.slice(0, 12)}</code>.
          Si actualizás Ecomm, prepará de nuevo los lotes. Una pista de marca
          no acredita fabricante, EAN, URL ni derechos de uso.
        </p>
        {plan.cohorts.slice(0, 16).map(cohort => (
          <details key={cohort.id}>
            <summary>
              {cohort.id} · {cohort.brand_phrase} (sin verificar) ·{" "}
              {cohort.count} variantes
            </summary>
            <ul>
              {cohort.items.map(item => (
                <li key={item.ecomm_id}>
                  SKU {item.sku} · Ecomm {item.ecomm_id} · {item.name} ·{" "}
                  {item.presentation}
                </li>
              ))}
            </ul>
          </details>
        ))}
        {plan.cohort_count > 16 && (
          <p>Hay {plan.cohort_count - 16} lotes adicionales en el CSV.</p>
        )}
        <p>
          Paso siguiente: revisar fabricante, URL oficial y presentación;
          incorporar un original solo con autorización y permisos verificables.
          No se aprobaron datos ni se publicaron productos.
        </p>
      </div>}
    </details>
  );
}
