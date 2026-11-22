import { useEffect, useState } from "react";
import { request } from "./catalog-adapter";
import { capabilities } from "./runtime";

const endpoint = "/api/ecomm-app/workspace/sources/intake-jobs";
type Candidate = {
  ecomm_id: string;
  name: string;
  state: string;
  ambiguous: boolean;
  candidate_count: number;
  candidates: { url: string }[];
};
type Sitemap = {
  receipt: { sitemap_url: string; sitemap_sha256: string };
  items: Candidate[];
};
type JobItem = {
  ecomm_id: string;
  url: string;
  state: "PENDING" | "RUNNING" | "IMPORTED" | "ALREADY_PRESENT" | "BLOCKED" | "CANCELLED";
  attempts: number;
  document_id: string | null;
  error: string | null;
  next_action: string | null;
  claim_until?: string | null;
  recoverable?: boolean;
  retry_available?: boolean;
};
type Job = {
  mode: "MANUAL_RESUMABLE_SOURCE_INTAKE";
  id: string;
  revision: number;
  state: string;
  total: number;
  counts: Record<string, number>;
  coverage?: {
    total_variants: number;
    documents_recorded: number;
    without_recorded_document: number;
    cancelled: number;
    completed_steps: number;
    facts_approved_by_operation: 0;
    commercial_fields_saved: 0;
  };
  recoverable_items?: number;
  max_attempts?: number;
  items: JobItem[];
  sitemap_url: string;
  selection_mode: "EXACT_OPERATOR_URL" | "REVIEWED_SITEMAP";
  source_host: string;
  external_writes_enabled: false;
  manual_steps_only: true;
  ai_requests: 0;
  claims_approved: 0;
};

function verified(value: unknown): Job {
  const row = value as Job;
  const states = ["PENDING", "RUNNING", "IMPORTED", "ALREADY_PRESENT", "BLOCKED", "CANCELLED"];
  if (!row || row.mode !== "MANUAL_RESUMABLE_SOURCE_INTAKE" ||
      row.external_writes_enabled !== false || row.manual_steps_only !== true ||
      row.ai_requests !== 0 || row.claims_approved !== 0 ||
      !["EXACT_OPERATOR_URL", "REVIEWED_SITEMAP"].includes(row.selection_mode) ||
      !/^[a-f0-9-]{36}$/.test(row.id) ||
      !Number.isSafeInteger(row.revision) || row.revision < 1 || !Array.isArray(row.items) ||
      row.total !== row.items.length || row.total < 1 || row.total > 20 ||
      new Set(row.items.map(item => item.ecomm_id)).size !== row.total ||
      !row.counts || states.some(state =>
        !Number.isSafeInteger(row.counts[state]) || row.counts[state] < 0 ||
        row.counts[state] !== row.items.filter(item => item.state === state).length) ||
      (row.recoverable_items !== undefined &&
        (!Number.isSafeInteger(row.recoverable_items) ||
          row.recoverable_items !== row.items.filter(item => item.recoverable === true).length)) ||
      row.items.some(item => !/^[1-9][0-9]*$/.test(item.ecomm_id) ||
        !Number.isSafeInteger(item.attempts) || item.attempts < 0 ||
        (item.recoverable === true && item.state !== "RUNNING") ||
        !states.includes(item.state))) {
    throw new Error("Respuesta de cola incompatible; no se procesó otra variante.");
  }
  if (row.coverage && (
    row.coverage.total_variants !== row.total ||
    row.coverage.documents_recorded !== row.counts.IMPORTED + row.counts.ALREADY_PRESENT ||
    row.coverage.without_recorded_document !== row.counts.PENDING + row.counts.RUNNING + row.counts.BLOCKED ||
    row.coverage.cancelled !== row.counts.CANCELLED ||
    row.coverage.completed_steps !== row.coverage.documents_recorded + row.coverage.cancelled ||
    row.coverage.facts_approved_by_operation !== 0 ||
    row.coverage.commercial_fields_saved !== 0
  )) throw new Error("La cobertura del lote no coincide con sus variantes.");
  return row;
}

export function ManufacturerIntakeQueue({
  csrf, selected, sitemap, disabled, onOpen, executionEnabled = true,
}: {
  csrf: string;
  selected: Set<string>;
  sitemap?: Sitemap;
  disabled: boolean;
  executionEnabled?: boolean;
  onOpen: (id: string) => void;
}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [current, setCurrent] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [exactUrls, setExactUrls] = useState("");
  const rootName = "Fuentes de fabricantes · cola reanudable";

  async function refresh() {
    const response = await request(endpoint);
    const data = await response.json() as { mode?: string; items?: unknown[]; detail?: string };
    if (!response.ok || data.mode !== "MANUAL_RESUMABLE_SOURCE_INTAKE" ||
        !Array.isArray(data.items)) throw new Error(data.detail || "No se pudo leer la cola.");
    const safe = data.items.map(verified);
    setJobs(safe);
    setCurrent(old => old ? safe.find(job => job.id === old.id) || old : safe[0]);
  }
  useEffect(() => {
    void refresh().catch(e => setError(e instanceof Error ? e.message : "No se pudo consultar la cola."));
  }, []);

  async function mutation(path: string, data: unknown): Promise<Job> {
    const response = await request(endpoint + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(data),
    });
    const value = await response.json() as { detail?: string };
    if (!response.ok) throw new Error(value.detail || "El servidor no completó la operación.");
    const next = verified(value);
    setCurrent(next);
    setJobs(previous => [next, ...previous.filter(job => job.id !== next.id)].slice(0, 20));
    return next;
  }

  async function run(operation: () => Promise<void>) {
    if (busy || disabled) return;
    setError("");
    setBusy(true);
    try {
      await operation();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se completó la operación.");
      await refresh().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  const candidates = sitemap?.items.filter(row =>
    selected.has(row.ecomm_id) &&
    row.state === "CANDIDATES" &&
    row.ambiguous === false &&
    row.candidate_count === 1 &&
    row.candidates.length === 1
  ) || [];

  function create() {
    if (!executionEnabled || !sitemap || !candidates.length || candidates.length > 20 ||
        !window.confirm(
          `¿Crear un lote reanudable con ${candidates.length} fuentes candidatas? Cada página se descargará únicamente cuando pulses el siguiente paso. No se aprueban hechos ni se publican productos.`
        )) return;
    void run(async () => {
      await mutation("", {
        request_key: crypto.randomUUID(),
        sitemap_url: sitemap.receipt.sitemap_url,
        sitemap_sha256: sitemap.receipt.sitemap_sha256,
        items: candidates.map(row => ({
          ecomm_id: row.ecomm_id, url: row.candidates[0].url,
        })),
        authorized_local_processing: true,
        confirm: true,
      });
    });
  }

  function createExactManifest() {
    if (!executionEnabled) return;
    const entries = exactUrls.trim().split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (!entries.length || entries.length > 20) {
      setError("Ingresá entre 1 y 20 líneas de un mismo fabricante.");
      return;
    }
    let items: { ecomm_id: string; url: string; provenance_note: string }[];
    try {
      items = entries.map((line, i) => {
        const columns = line.split(";");
        if (columns.length !== 3) throw new Error(
          `Línea ${i + 1}: utilizá Ecomm ID;URL HTTPS;motivo documentado.`
        );
        const [ecomm_id, url, provenance_note] = columns.map(x => x.trim());
        if (!/^[1-9][0-9]{0,19}$/.test(ecomm_id) ||
            !selected.has(ecomm_id) ||
            !/^https:\/\/[^/]+\/[^?#]+$/.test(url) ||
            provenance_note.length < 10 || provenance_note.length > 600) {
          throw new Error(
            `Línea ${i + 1}: seleccioná esa variante y completá URL HTTPS exacta y procedencia.`
          );
        }
        return { ecomm_id, url, provenance_note };
      });
      if (new Set(items.map(x => x.ecomm_id)).size !== items.length) {
        throw new Error("No se admite el mismo Ecomm ID dos veces.");
      }
      const hosts = new Set(items.map(x => new URL(x.url).hostname.toLowerCase()));
      if (hosts.size !== 1) {
        throw new Error("Separá Natufarma y Biosa: cada lote admite un solo dominio.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Manifiesto inválido.");
      return;
    }
    if (!window.confirm(
      `¿Crear el lote de ${items.length} URLs? Confirmás que revisaste cada identidad y presentación en Ecomm-App y el fabricante. No se hace ninguna descarga ahora. Cada incorporación queda PENDIENTE de validar.`
    )) return;
    void run(async () => {
      await mutation("/exact-urls", {
        request_key: crypto.randomUUID(),
        items,
        authorized_local_processing: true,
        identity_reviewed_by_operator: true,
        confirm: true,
      });
      setExactUrls("");
    });
  }

  function process() {
    if (!executionEnabled || !current || !window.confirm(
      "¿Capturar una sola página del fabricante en este paso? Guardará su HTML como evidencia pendiente, sin publicar ni aprobar información."
    )) return;
    const job = current;
    void run(async () => { await mutation(
      `/${job.id}/step`, { expected_revision: job.revision, confirm: true },
    ); });
  }

  function retry(ecommId: string) {
    if (!executionEnabled || !current) return;
    const job = current;
    void run(async () => { await mutation(
      `/${job.id}/retry`,
      { expected_revision: job.revision, confirm: true, ecomm_id: ecommId },
    ); });
  }

  function recover() {
    if (!current || !current.recoverable_items || !window.confirm(
      "¿Recuperar los pasos cuyo plazo de ejecución venció? KIKI comprobará sólo los documentos locales. No descargará páginas ni reintentará fuentes; deberás decidir cada siguiente paso."
    )) return;
    const job = current;
    void run(async () => { await mutation(
      `/${job.id}/recover`, { expected_revision: job.revision, confirm: true },
    ); });
  }

  function cancel() {
    if (!current || !window.confirm(
      "¿Cancelar las fuentes pendientes de este lote? La documentación ya incorporada se conservará."
    )) return;
    const job = current;
    void run(async () => { await mutation(
      `/${job.id}/cancel`, { expected_revision: job.revision, confirm: true },
    ); });
  }

  const canStep = current?.items.some(i => i.state === "PENDING" || i.state === "RUNNING") &&
    current?.state !== "CANCELLED";
  const running = current?.items.some(i => i.state === "RUNNING");

  return <section className="b-detail" aria-label={rootName}>
    <h3>{rootName}</h3>
    <p>Conserva el avance en KIKI aunque cierres el navegador. Procesa una variante por clic; los documentos quedan pendientes de revisar.</p>
    {!executionEnabled && <p role="status">
      Descargas deshabilitadas. Podés consultar el avance, recuperar pasos vencidos
      y cancelar pendientes sin acceder a fabricantes.
    </p>}
    {capabilities?.document_exact_url_manifest === true && <details>
      <summary>Preparar lote por URLs exactas (sin sitemap)</summary>
      <p>
        Seleccioná primero hasta 20 variantes en el catálogo. Pegá una línea
        por producto: <code>Ecomm ID;URL HTTPS exacta;procedencia comprobada</code>.
        Solo un dominio por lote. KIKI verifica identidad y restricciones técnicas
        antes de cada descarga. La URL y el EAN no acreditan por sí solos al fabricante.
      </p>
      <textarea rows={5} value={exactUrls}
        onChange={e => setExactUrls(e.target.value)}
        disabled={busy || disabled}
        placeholder={"6754660;https://fabricante.example/producto/abc;Página específica revisada con nombre y presentación"}
        aria-label="Lista de URLs exactas de un fabricante"
      />
      <div className="b-actions">
        <button type="button" disabled={busy || disabled || !exactUrls.trim()}
          onClick={createExactManifest}>
          Guardar manifiesto de investigación
        </button>
      </div>
      <p>
        Guardar el manifiesto no descarga páginas. Procesá cada fuente con
        el botón de avance; los hechos y las fichas requieren aprobación humana.
      </p>
    </details>}
    <div className="b-actions">
      <button type="button" disabled={busy || disabled || !executionEnabled || !candidates.length} onClick={create}>
        Preparar lote con {candidates.length} fuentes
      </button>
      <button type="button" disabled={busy || disabled} onClick={() => void run(refresh)}>
        Actualizar estados
      </button>
    </div>
    {jobs.length > 0 && <label>
      Lotes guardados
      <select aria-label="Seleccionar lote de fuentes" value={current?.id || ""} onChange={event => {
        setCurrent(jobs.find(job => job.id === event.target.value));
      }}>
        {jobs.map(job => <option key={job.id} value={job.id}>
          {job.id.slice(0, 8)} · {job.state} · {job.total} fuentes · {job.selection_mode === "EXACT_OPERATOR_URL" ? "URLs revisadas" : "Sitemap"}
        </option>)}
      </select>
    </label>}
    {current && <div role="region" aria-label="Progreso de fuentes del fabricante">
      <p><strong>{current.state}</strong> · {current.counts.IMPORTED || 0} de {current.total} incorporadas · {current.counts.BLOCKED || 0} bloqueadas · {current.counts.PENDING || 0} pendientes.</p>
      {current.coverage && <p role="status">
        Cobertura documental: {current.coverage.documents_recorded} de {current.total}
        {" "}con incorporación registrada · {current.coverage.without_recorded_document}
        {" "}sin documento registrado · {current.coverage.cancelled} canceladas.
        {" "}No acredita hechos aprobados ni fichas completas.
      </p>}
      <div className="b-actions">
        <button type="button" disabled={busy || disabled || !executionEnabled || !canStep || running}
          onClick={process}>Procesar siguiente fuente</button>
        <button type="button" disabled={busy || disabled || !current.recoverable_items}
          onClick={recover}>Recuperar pasos vencidos sin descargar</button>
        <button type="button" disabled={busy || disabled || running ||
          current.state === "CANCELLED" || !current.items.some(i => i.state === "PENDING")}
          onClick={cancel}>Cancelar pendientes</button>
      </div>
      {current.items.map(item => <article key={item.ecomm_id} className="b-detail">
        <p><strong>Ecomm {item.ecomm_id}</strong> · {item.state} · intentos {item.attempts}</p>
        {item.state === "RUNNING" && <p>
          Plazo del paso: {item.claim_until || "No disponible"}.
          {" "}{item.recoverable ? "Puede recuperarse sin descargar." : "Actualizá estados al vencer el plazo; no se interrumpe un paso activo."}
        </p>}
        <p>{item.error || "Documento pendiente de comprobación de identidad y procedencia"}</p>
        {item.state === "BLOCKED" && item.attempts < (current.max_attempts ?? 3) &&
          item.retry_available !== false && <button type="button"
          disabled={busy || disabled || !executionEnabled} onClick={() => retry(item.ecomm_id)}>Reintentar esta fuente</button>}
        {["IMPORTED", "ALREADY_PRESENT"].includes(item.state) && <button type="button"
          disabled={busy || disabled} onClick={() => onOpen(item.ecomm_id)}>
          Revisar evidencia incorporada
        </button>}
      </article>)}
    </div>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
