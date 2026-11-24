import { useEffect, useRef, useState } from "react";
import { request } from "./catalog-adapter";
import { capabilities } from "./runtime";
import { ManufacturerPipelineSummary, verifiedManufacturerReport } from "./ManufacturerPipelineReport";

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
  complete_available?: boolean;
  processing?: { phase: string; candidate_count?: number };
};
type Job = {
  pipeline_schema_version?: "kiki-documental-pipeline-v1";
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
      (row.pipeline_schema_version !== undefined && row.pipeline_schema_version !== "kiki-documental-pipeline-v1") ||
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
  const [processingBatch, setProcessingBatch] = useState(false);
  const [batchMessage, setBatchMessage] = useState("");
  const mounted = useRef(true);
  const operationRunning = useRef(false);
  const pauseRequested = useRef(false);
  const executionAllowed = useRef(executionEnabled && !disabled);
  executionAllowed.current = executionEnabled && !disabled;
  const rootName = "Fuentes de fabricantes · cola reanudable";

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      pauseRequested.current = true;
    };
  }, []);

  function displayJob(next: Job) {
    if (!mounted.current) return;
    setCurrent(next);
    setJobs(previous => [next, ...previous.filter(job => job.id !== next.id)].slice(0, 20));
  }

  async function loadJob(id: string): Promise<Job> {
    const response = await request(`${endpoint}/${id}`);
    const next = verified(await response.json());
    if (!response.ok || next.id !== id) throw new Error("El servidor no confirmó el lote seleccionado.");
    displayJob(next);
    return next;
  }

  async function refresh() {
    const response = await request(endpoint);
    const data = await response.json() as { mode?: string; items?: unknown[]; detail?: string };
    if (!response.ok || data.mode !== "MANUAL_RESUMABLE_SOURCE_INTAKE" ||
        !Array.isArray(data.items)) throw new Error(data.detail || "No se pudo leer la cola.");
    const safe = data.items.map(verified);
    if (mounted.current) {
      setJobs(safe);
      setCurrent(old => old ? safe.find(job => job.id === old.id) || old : safe[0]);
    }
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
    displayJob(next);
    return next;
  }

  async function run(operation: () => Promise<void>) {
    if (operationRunning.current || busy || disabled) return;
    operationRunning.current = true;
    setError("");
    setBusy(true);
    try {
      await operation();
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : "No se completó la operación.");
        await refresh().catch(() => undefined);
      }
    } finally {
      operationRunning.current = false;
      if (mounted.current) setBusy(false);
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

  function processBatch() {
    if (!executionAllowed.current || !current) return;
    const id = current.id;
    void run(async () => {
      // Resume always reads the persisted revision. Browser state is never
      // an authorization to repeat a step already committed by another tab.
      let job = await loadJob(id);
      if (!mounted.current || !executionAllowed.current) return;
      const pending = job.items.filter(item => item.state === "PENDING");
      if (job.state === "CANCELLED" || job.items.some(item => item.state === "RUNNING"))
        throw new Error("El lote está cancelado o tiene un paso activo. Actualizá o recuperá su estado.");
      if (!pending.length) throw new Error("No hay fuentes pendientes para procesar.");
      if (!window.confirm(
        `¿Procesar ${pending.length} fuentes PENDIENTES de ${job.source_host}? ` +
        `${job.counts.IMPORTED + job.counts.ALREADY_PRESENT} ya incorporadas no se repetirán; ` +
        `${job.counts.BLOCKED} bloqueadas quedan para revisión. ` +
        "Se procesarán secuencialmente, como máximo 20 pasos y sin reintentos automáticos. " +
        "Podés pausar antes del próximo paso. No se aprueban hechos ni se publican productos."
      )) return;
      if (!mounted.current || !executionAllowed.current) return;
      const allowed = new Set(pending.map(item => item.ecomm_id));
      const membership = JSON.stringify(job.items.map(item => [item.ecomm_id, item.url]));
      pauseRequested.current = false;
      setProcessingBatch(true);
      setBatchMessage(`Procesando hasta ${pending.length} fuentes autorizadas…`);
      let completed = 0;
      try {
        for (let step = 0; step < pending.length && step < 20; step++) {
          if (!mounted.current || pauseRequested.current || !executionAllowed.current) break;
          if (job.id !== id || JSON.stringify(job.items.map(item => [item.ecomm_id, item.url])) !== membership)
            throw new Error("Cambió la selección del lote; detené y revisá las variantes.");
          if (job.state === "CANCELLED" || job.items.some(item => item.state === "RUNNING"))
            throw new Error("El lote tiene un paso activo o fue cancelado; no se inició otra descarga.");
          const item = job.items.find(row => row.state === "PENDING");
          if (!item) break;
          if (!allowed.delete(item.ecomm_id))
            throw new Error("Una fuente requiere una autorización nueva; no se reintentó automáticamente.");
          const previousRevision = job.revision;
          const next = await mutation(`/${id}/step`, {
            expected_revision: previousRevision, confirm: true,
          });
          const updated = next.items.find(row => row.ecomm_id === item.ecomm_id);
          if (next.id !== id || next.revision <= previousRevision ||
              JSON.stringify(next.items.map(row => [row.ecomm_id, row.url])) !== membership ||
              !updated || ["PENDING", "RUNNING"].includes(updated.state) ||
              next.items.some(row => row.state === "RUNNING"))
            throw new Error("El servidor no confirmó el avance del lote; revisá el estado antes de continuar.");
          job = next;
          completed++;
          if (mounted.current) setBatchMessage(`${completed} de ${pending.length} pasos terminados. Las excepciones requieren revisión.`);
        }
      } finally {
        if (mounted.current) {
          setProcessingBatch(false);
          if (pauseRequested.current || !executionAllowed.current)
            setBatchMessage(`Lote pausado tras ${completed} pasos. El avance está guardado; al reanudar se consultará la versión actual.`);
        }
      }
    });
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

  function completeLocal(ecommId: string) {
    if (!current) return;
    const job = current;
    void run(async () => {
      const response = await request(`${endpoint}/${job.id}/report`);
      const report = verifiedManufacturerReport(await response.json(), job.id, job.revision, job.items);
      const source = report.items.find(item => item.ecomm_id === ecommId);
      if (!source || !Number.isSafeInteger(source.document_version) ||
          !/^[a-f0-9]{64}$/.test(source.document_digest || "") ||
          !/^[a-f0-9]{64}$/.test(source.document_sha256 || ""))
        throw new Error("No hay una versión íntegra del original para completar localmente.");
      if (!window.confirm(
        `¿Completar localmente Ecomm ${ecommId} con el original v${source.document_version}, SHA-256 ${source.document_sha256}? ` +
        "Confirmás que revisaste la procedencia y los cambios de metadatos. El servidor rechazará otra identidad o bytes diferentes. " +
        "No descargará páginas ni aprobará hechos: los candidatos nuevos quedarán PENDIENTES y las fichas no se modificarán."
      )) return;
      await mutation(`/${job.id}/complete`, {
        expected_revision: job.revision, ecomm_id: ecommId, confirm: true,
        expected_document_version: source.document_version,
        expected_document_digest: source.document_digest,
      });
    });
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
    <p>Conserva el avance en KIKI aunque cierres el navegador. Podés autorizar el lote completo o avanzar por fuente; los documentos quedan pendientes de revisar. Cerrar este panel detiene los siguientes pasos.</p>
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
      <select aria-label="Seleccionar lote de fuentes" disabled={busy} value={current?.id || ""} onChange={event => {
        setCurrent(jobs.find(job => job.id === event.target.value));
      }}>
        {jobs.map(job => <option key={job.id} value={job.id}>
          {job.id.slice(0, 8)} · {job.state} · {job.total} fuentes · {job.selection_mode === "EXACT_OPERATOR_URL" ? "URLs revisadas" : "Sitemap"}
        </option>)}
      </select>
    </label>}
    {current && <div role="region" aria-label="Progreso de fuentes del fabricante">
      <p><strong>{current.state}</strong> · {current.counts.IMPORTED || 0} de {current.total} incorporadas · {current.counts.BLOCKED || 0} bloqueadas · {current.counts.PENDING || 0} pendientes.</p>
      <p>Dominio revisado: <strong>{current.source_host}</strong>. Se procesan únicamente las fuentes PENDIENTES; las incorporadas y bloqueadas no se reintentan.</p>
      {current.coverage && <p role="status">
        Cobertura documental: {current.coverage.documents_recorded} de {current.total}
        {" "}con incorporación registrada · {current.coverage.without_recorded_document}
        {" "}sin documento registrado · {current.coverage.cancelled} canceladas.
        {" "}No acredita hechos aprobados ni fichas completas.
      </p>}
      <div className="b-actions">
        <button type="button" disabled={busy || disabled || !executionEnabled || running ||
          current.state === "CANCELLED" || !current.items.some(item => item.state === "PENDING")}
          onClick={processBatch}>Procesar lote autorizado</button>
        {processingBatch && <button type="button" onClick={() => {
          pauseRequested.current = true;
          setBatchMessage("Pausa solicitada: el paso actual puede terminar y guardarse; no se iniciará otro.");
        }}>Pausar después del paso actual</button>}
        <button type="button" disabled={busy || disabled || !executionEnabled || !canStep || running}
          onClick={process}>Procesar siguiente fuente</button>
        <button type="button" disabled={busy || disabled || !current.recoverable_items}
          onClick={recover}>Recuperar pasos vencidos sin descargar</button>
        <button type="button" disabled={busy || disabled || running ||
          current.state === "CANCELLED" || !current.items.some(i => i.state === "PENDING")}
          onClick={cancel}>Cancelar pendientes</button>
      </div>
      {batchMessage && <p role="status">{batchMessage}</p>}
      {current.pipeline_schema_version === "kiki-documental-pipeline-v1" && <ManufacturerPipelineSummary
        jobId={current.id} revision={current.revision} busy={busy || disabled}
        expectedItems={current.items.map(item => ({ ecomm_id: item.ecomm_id, url: item.url }))}
        onOpen={onOpen}
      />}
      {current.items.map(item => <article key={item.ecomm_id} className="b-detail">
        <p><strong>Ecomm {item.ecomm_id}</strong> · {item.state} · intentos {item.attempts}</p>
        {item.state === "RUNNING" && <p>
          Plazo del paso: {item.claim_until || "No disponible"}.
          {" "}{item.recoverable ? "Puede recuperarse sin descargar." : "Actualizá estados al vencer el plazo; no se interrumpe un paso activo."}
        </p>}
        <p>{item.error || (["IMPORTED", "ALREADY_PRESENT"].includes(item.state)
          ? "Original archivado. La procedencia, los hechos y las propuestas se revisan por separado en el informe documental."
          : "Fuente pendiente de incorporación y comprobación de identidad y procedencia.")}</p>
        {item.processing && <p>
          Extracción local: {item.processing.phase}
          {typeof item.processing.candidate_count === "number" && ` · ${item.processing.candidate_count} candidatos registrados`}.
          {" "}Esta operación no aprueba hechos ni modifica fichas.
        </p>}
        {item.complete_available === true && <button type="button"
          disabled={busy || disabled || running || current.state === "CANCELLED"}
          onClick={() => completeLocal(item.ecomm_id)}>
          Completar extracción local sin descargar
        </button>}
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
