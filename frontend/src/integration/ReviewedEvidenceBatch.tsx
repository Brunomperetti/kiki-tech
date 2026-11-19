import { useEffect, useState } from "react";
import { request } from "./catalog-adapter";

type Item = {
  ecomm_id: string;
  state: "PREPARED" | "NO_CHANGES" | "BLOCKED";
  document_id: string | null;
  document_version: number | null;
  facts_pending: number;
  facts_approved_unchanged: number;
  reasons: string[];
};
type Result = {
  mode: "MANUAL_REEXTRACT_REVIEWED_ORIGINALS";
  total: number;
  counts: Record<"PREPARED" | "NO_CHANGES" | "BLOCKED", number>;
  items: Item[];
  human_fact_approval_required: true;
  facts_approved_by_operation: 0;
  external_writes_enabled: false;
  provider_calls: 0;
  ai_requests: 0;
  product_fields_saved: 0;
  automatic_publications: 0;
};

function verified(data: unknown, selected: Set<string>): Result {
  const row = data as Result;
  if (!row || row.mode !== "MANUAL_REEXTRACT_REVIEWED_ORIGINALS" ||
      row.human_fact_approval_required !== true ||
      row.external_writes_enabled !== false ||
      row.facts_approved_by_operation !== 0 ||
      row.provider_calls !== 0 || row.ai_requests !== 0 ||
      row.product_fields_saved !== 0 || row.automatic_publications !== 0 ||
      !Array.isArray(row.items) || row.total !== row.items.length ||
      row.total !== selected.size ||
      row.items.some(item =>
        !selected.has(item.ecomm_id) ||
        !["PREPARED", "NO_CHANGES", "BLOCKED"].includes(item.state) ||
        !Array.isArray(item.reasons) ||
        !Number.isSafeInteger(item.facts_pending) ||
        !Number.isSafeInteger(item.facts_approved_unchanged)
      )) throw new Error("KIKI no confirmó la reextracción de la selección.");
  return row;
}

const stateLabels = {
  PREPARED: "Hechos listos para revisión individual",
  NO_CHANGES: "Sin cambios: conservar aprobaciones vigentes",
  BLOCKED: "Bloqueado: revisar la identidad o procedencia",
};

export function ReviewedEvidenceBatch({
  ids, csrf, disabled, onOpen,
}: {
  ids: Set<string>;
  csrf: string;
  disabled: boolean;
  onOpen: (id: string) => void;
}) {
  const [report, setReport] = useState<Result>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = [...ids].sort().join(",");
  useEffect(() => {
    setReport(undefined);
    setError("");
  }, [key]);

  async function run() {
    if (disabled || busy || ids.size < 1 || ids.size > 20) return;
    if (!window.confirm(
      `¿Reextraer datos de ${ids.size} variantes? Solo se usarán originales reales con procedencia e identidad previamente revisadas. Los datos nuevos quedarán PENDIENTES. No se aprobará, guardará ni publicará ninguna ficha.`
    )) return;
    const chosen = new Set(ids);
    setBusy(true);
    setError("");
    setReport(undefined);
    try {
      const response = await request(
        "/api/ecomm-app/workspace/sources/reextract-reviewed", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({ ecomm_ids: [...chosen], confirm: true }),
        },
      );
      const data = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(data.detail || "No se pudieron revisar los documentos.");
      setReport(verified(data, chosen));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falló la reextracción documental.");
    } finally {
      setBusy(false);
    }
  }

  return <details className="b-detail" aria-label="Preparar hechos de fuentes revisadas">
    <summary>Reextraer hechos de fuentes revisadas (máximo 20)</summary>
    <p>
      Ahorra repetir «Extraer hechos» en cada ficha. Solo trabaja con
      originales reales ya revisados y relacionados inequívocamente con
      la variante de Ecomm-App. No busca nuevas fuentes ni utiliza IA.
    </p>
    <div className="b-actions">
      <button type="button" disabled={busy || disabled || ids.size < 1 || ids.size > 20}
        onClick={() => void run()}>
        {busy ? "Preparando hechos…" : `Reextraer de ${ids.size} variantes`}
      </button>
      {ids.size > 20 && <small>Seleccioná hasta 20 variantes.</small>}
    </div>
    {error && <p role="alert">{error}</p>}
    {report && <div role="region" aria-label="Resultado de reextracción">
      <p role="status">
        {report.counts.PREPARED} con hechos pendientes · {report.counts.NO_CHANGES}
        {" "}sin cambios · {report.counts.BLOCKED} bloqueadas.
      </p>
      {report.items.map(item => <article key={item.ecomm_id} className="b-detail">
        <strong>Ecomm ID {item.ecomm_id}</strong>
        <p>{stateLabels[item.state]} · {item.facts_pending} hechos pendientes
          {" "}· {item.facts_approved_unchanged} aprobados conservados.</p>
        {item.reasons.map((reason, index) => <p key={index}>{reason}</p>)}
        <button type="button" disabled={busy || disabled}
          onClick={() => onOpen(item.ecomm_id)}>
          Abrir Evidencias y revisar
        </button>
      </article>)}
      <p>
        La extracción no equivale a verificación. Cada dato debe aprobarse
        individualmente antes de generar una propuesta comercial o SEO.
      </p>
    </div>}
  </details>;
}
