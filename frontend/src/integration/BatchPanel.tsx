import { environmentText, capabilities } from "./runtime";
import { ManufacturerIntakeQueue } from "./ManufacturerIntakeQueue";
import { CommercialPreparationPlan } from "./CommercialPreparationPlan";
import { ReviewedEvidenceBatch } from "./ReviewedEvidenceBatch";
import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { ProductDrawer } from "../prototype/CatalogView";
import { request, captureDate, validVariantId } from "./catalog-adapter";
import "./batches.css";
const root = "/api/ecomm-app/editorial-batches";
const PILOT_BATCH_LIMIT = 100; // existing Render configuration rejects larger selections.
const labels: Record<string, string> = {
  PREVIEW: "Previsualización",
  PENDING: "Pendiente",
  RUNNING: "Ejecutándose",
  PREPARING: "Preparando previsualización",
  COMPLETED_WITH_BLOCKS: "Completado con bloqueos",
  FAILED: "Fallido",
  CANCELLING: "Cancelación solicitada",
  COMPLETED: "Completado",
  BLOCKED: "Bloqueado",
  CONFLICT: "Conflicto",
  ERROR: "Fallido",
  CANCELLED: "Cancelado",
};
/** Explicit operator-assisted search; never claims manufacturer identity.
 * Do not crawl, fetch, import or publish automatically. The user's click
 * sends the visible Ecomm item title to the search engine in a new tab.
 */
function officialSourceSearchUrl(name: string, presentation?: string): string {
  const title = name.replace(/[\x00-\x1f\x7f]/g, " ").trim().slice(0, 140);
  const variant = (presentation || "").replace(/[\x00-\x1f\x7f]/g, " ").trim().slice(0, 70);
  const query = [title, variant, "fabricante sitio oficial producto"].filter(Boolean).join(" ");
  const url = new URL("https://www.google.com/search");
  url.searchParams.set("q", query);
  return url.toString();
}
type Item = {
  ecomm_id: string;
  state: string;
  attempts: number;
  result: {
    preview?: {
      name?: string;
      presentation?: string;
      is_combo?: boolean;
      reasons?: string[];
    };
    proposal_id?: number;
    fields_without_support?: string[];
    task?: {
      requires_human: boolean;
      review_schedule?: { review_due: boolean; next_review_at: string | null };
      revoked?: boolean;
      documents_changed?: boolean;
      reasons?: string[];
    };
  };
  error: { message?: string; reasons?: string[] };
};
type Batch = {
  id: string;
  operation: string;
  state: string;
  public_state: string;
  autonomous: boolean;
  cancel_requested: boolean;
  progress: {
    total: number;
    prepared: number;
    processed: number;
    completed: number;
    blocked: number;
    pending: number;
    running: number;
    failed: number;
    cancelled: number;
  };
  revision: number;
  created_at: string;
  authorized_by: string | null;
  preview_hash: string;
  total: number;
  summary: Record<string, number>;
  counts: Record<string, number>;
  items?: Item[];
  page?: number;
  history: { action: string; at: string; actor: string }[];
  internal_only: true;
  external_writes_enabled: false;
};
type SitemapPreview = {
  mode: "READ_ONLY_MANUFACTURER_SITEMAP_PREVIEW";
  receipt: { sitemap_url: string; sitemap_sha256: string; urls_inspected: number; robots_checked: true };
  items: {
    ecomm_id: string;
    name: string;
    state: "BLOCKED" | "CANDIDATES" | "NOT_FOUND";
    reasons: string[];
    ambiguous: boolean;
    candidate_count: number;
    candidates: {
      url: string;
      matched_tokens: string[];
      verified: false;
      review_required: true;
    }[];
  }[];
};
async function api(path: string, csrf: string, body?: unknown): Promise<Batch> {
  const response = await request(
    root + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify(body),
        },
  );
  const value = (await response.json()) as Batch;
  if (
    !value ||
    value.internal_only !== true ||
    value.external_writes_enabled !== false ||
    !/^[a-f0-9-]{36}$/.test(value.id) ||
    !labels[value.state] ||
    !Number.isSafeInteger(value.total) ||
    value.items?.some((i) => !validVariantId(i.ecomm_id) || !labels[i.state])
  )
    throw new Error("Respuesta de lote inválida; no se procesó otro catálogo.");
  return value;
}
export function BatchPanel({
  ids,
  query,
  filter,
  matches,
  csrf,
  disabled,
  onClear,
  onPage,
  onOpen,
}: {
  ids: Set<string>;
  query: string;
  filter: string;
  matches: number;
  csrf: string;
  disabled: boolean;
  onClear: () => void;
  onPage: () => void;
  onOpen: (id: string, proposal?: number, tab?: "Ficha" | "Evidencias") => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null),
    panelRef = useRef<HTMLElement>(null),
    openRef = useRef<HTMLButtonElement>(null);
  const [batch, setBatch] = useState<Batch>();
  const [jobs, setJobs] = useState<Batch[]>([]);
  const [jobsPage, setJobsPage] = useState(1),
    [jobsTotal, setJobsTotal] = useState(0);
  const [operation, setOperation] = useState("GENERATE_PROPOSALS");
  const [sitemapUrl, setSitemapUrl] = useState("");
  const [sitemapResult, setSitemapResult] = useState<SitemapPreview>();
  const [capturedManufacturerIds, setCapturedManufacturerIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function list(page = jobsPage) {
    const response = await request(root + `?page=${page}&limit=5`);
    const data = await response.json();
    if (!Array.isArray(data.items))
      throw new Error("No se pudo recuperar la cola.");
    if (mounted.current) {
      setJobs(data.items);
      setJobsTotal(data.total);
    }
  }
  useEffect(() => {
    list().catch((e) => setError(e.message));
  }, [jobsPage]);
  async function act(fn: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No se pudo completar la operación.",
      );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function detail(id: string, page = 1) {
    const next = await api(`/${id}?page=${page}&limit=10`, csrf);
    if (mounted.current) setBatch(next);
    return next;
  }
  async function preview(filtered: boolean) {
    const selectedCount = filtered ? matches : ids.size;
    if (selectedCount < 1 || selectedCount > PILOT_BATCH_LIMIT) {
      setError("Seleccioná entre 1 y 100 variantes. Refiná el filtro antes de preparar el lote.");
      setExpanded(true);
      return;
    }
    setExpanded(true);
    await act(async () => {
      const next = await api("/preview", csrf, {
        request_key: crypto.randomUUID(),
        operation,
        selection: filtered
          ? { kind: "FILTER", ids: [], query, filter }
          : { kind: "IDS", ids: [...ids], query: "", filter: "all" },
      });
      setBatch(next);
      await list();
    });
  }
  async function discoverManufacturer() {
    if (!sitemapUrl.startsWith("https://") || ids.size < 1 || ids.size > 20) {
      setError("Seleccioná entre 1 y 20 variantes e ingresá el sitemap HTTPS oficial del fabricante.");
      return;
    }
    await act(async () => {
      const response = await request("/api/ecomm-app/workspace/sources/sitemap-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ sitemap_url: sitemapUrl.trim(), ecomm_ids: [...ids] }),
      });
      const data = (await response.json()) as SitemapPreview & { detail?: string };
      if (!response.ok) throw new Error(data.detail || "No se pudo comprobar el índice oficial.");
      if (
        data.mode !== "READ_ONLY_MANUFACTURER_SITEMAP_PREVIEW" ||
        !Array.isArray(data.items) ||
        data.items.some((item) =>
          !ids.has(item.ecomm_id) ||
          !Array.isArray(item.candidates) ||
          item.candidates.some((candidate) =>
            candidate.verified !== false ||
            candidate.review_required !== true ||
            !candidate.url.startsWith("https://")
          )
        )
      ) throw new Error("La búsqueda devolvió datos incompatibles; no se usaron.");
      if (!/^[a-f0-9]{64}$/.test(data.receipt?.sitemap_sha256 || "")) {
        throw new Error("El fabricante no devolvió un comprobante verificable del índice.");
      }
      setSitemapResult(data);
      setCapturedManufacturerIds([]);
    });
  }
  async function captureManufacturer() {
    if (!sitemapResult || capabilities?.document_batch_source_import !== true) return;
    const chosen = sitemapResult.items.filter((item) =>
      ids.has(item.ecomm_id) &&
      !capturedManufacturerIds.includes(item.ecomm_id) &&
      item.state === "CANDIDATES" &&
      item.ambiguous === false &&
      item.candidate_count === 1 &&
      item.candidates.length === 1
    ).slice(0, 2);
    if (!chosen.length) return;
    if (!window.confirm(
      `¿Incorporar ${chosen.length} documentos originales de fabricante? KIKI guardará HTML y procedencia como PENDIENTES; ningún dato quedará aprobado ni se publicará nada.`
    )) return;
    await act(async () => {
      const response = await request("/api/ecomm-app/workspace/sources/batch-import", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          sitemap_url: sitemapResult.receipt.sitemap_url,
          sitemap_sha256: sitemapResult.receipt.sitemap_sha256,
          items: chosen.map((item) => ({
            ecomm_id: item.ecomm_id,
            url: item.candidates[0].url,
          })),
          authorized_local_processing: true,
          confirm: true,
        }),
      });
      const data = await response.json() as {
        mode?: string;
        detail?: string;
        documents?: {ecomm_id: string; document_id: string; review_state: string; facts_approved: number}[];
        external_catalogue_writes?: number;
        facts_approved?: number;
      };
      if (!response.ok) throw new Error(data.detail || "No se incorporaron las fuentes.");
      if (data.mode !== "EXPLICIT_BATCH_SOURCE_INTAKE" ||
          data.external_catalogue_writes !== 0 ||
          data.facts_approved !== 0 ||
          !Array.isArray(data.documents) ||
          data.documents.length !== chosen.length ||
          data.documents.some((doc) =>
            !chosen.some(item => item.ecomm_id === doc.ecomm_id) ||
            !doc.document_id?.startsWith("local-") ||
            doc.review_state !== "PENDING" ||
            doc.facts_approved !== 0
          )) throw new Error("El resultado no prueba la incorporación segura; revisá antes de reintentar.");
      setCapturedManufacturerIds((old) => [
        ...new Set([...old, ...data.documents!.map((doc) => doc.ecomm_id)])
      ]);
    });
  }
  async function run() {
    if (!batch || !window.confirm(
      "¿Confirmás preparar únicamente propuestas internas de las variantes previsualizadas? Cada ficha seguirá requiriendo aprobación humana y no habrá publicaciones externas.",
    )) return;
    await act(async () => {
      await api(`/${batch.id}/start`, csrf, {
        confirm: true,
        expected_revision: batch.revision,
        preview_hash: batch.preview_hash,
        idempotency_key: crypto.randomUUID(),
      });
      await detail(batch.id);
      await list();
    });
  }
  async function processManualStep() {
    if (!batch || batch.autonomous || batch.state !== "PENDING")
      return;
    await act(async () => {
      // Explicit single bounded backend step. Never starts a browser-side
      // loop or an always-on executor; the operator controls every group.
      await api(`/${batch.id}/step`, csrf, { resume_interrupted: false });
      await detail(batch.id);
      await list();
    });
  }
  useEffect(() => {
    // Never poll the backend every 1.5s when the operator closed the drawer.
    if (!expanded) return;
    const timer = window.setInterval(() => {
      list().catch((e) => {
        if (mounted.current) setError(e.message);
      });
      if (
        batch &&
        (["PREPARING", "PENDING", "RUNNING"].includes(batch.state) ||
          batch.cancel_requested)
      )
        detail(batch.id, batch.page || 1).catch((e) => {
          if (mounted.current) setError(e.message);
        });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [expanded, batch?.id, batch?.state, batch?.page, batch?.cancel_requested, jobsPage]);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    function keys(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setExpanded(false);
        return;
      }
      if (e.key !== "Tab") return;
      const all = Array.from(
        panelRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),select:not(:disabled),input:not(:disabled),summary,[tabindex="0"]',
        ) || [],
      ).filter((el) => el.getClientRects().length);
      if (!all.length) return;
      if (e.shiftKey && document.activeElement === all[0]) {
        e.preventDefault();
        all[all.length - 1].focus();
      } else if (
        !e.shiftKey &&
        document.activeElement === all[all.length - 1]
      ) {
        e.preventDefault();
        all[0].focus();
      }
    }
    document.addEventListener("keydown", keys);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", keys);
      openRef.current?.focus();
    };
  }, [expanded]);
  const locked = busy || disabled;
  return (
    <section className="b-work" aria-label="Trabajo por lotes">
      <div className="b-toolbar">
        <span className="k-operations-caption">
          Centro de operaciones · propuestas IA y revisión por lotes
        </span>
        <strong data-testid="selected-count">
          {ids.size} variantes seleccionadas
        </strong>
        <button disabled={locked} onClick={onPage}>
          Seleccionar esta página
        </button>
        <button disabled={locked || !ids.size} onClick={onClear}>
          Quitar selección
        </button>
        <button
          className="d-primary"
          ref={openRef}
          disabled={locked}
          onClick={() => setExpanded(true)}
        >
          Operaciones
        </button>
        <button disabled={locked} onClick={() => setExpanded(true)}>
          Ver lotes ({jobsTotal})
        </button>
        {batch && (
          <small>
            {labels[batch.public_state || batch.state]} ·{" "}
            {batch.progress?.processed ?? 0}/{batch.total} procesadas
          </small>
        )}
      </div>
      {expanded &&
        createPortal(
          <ProductDrawer
            id="lotes"
            dialogLabel="Lotes editoriales"
            closeLabel="Cerrar lotes"
            title="Trabajo por lotes"
            subtitle="Los pasos manuales se ejecutan solamente cuando pulsás Procesar siguiente grupo. No hay trabajador permanente ni publicaciones automáticas."
            thumbnail={<span className="d-thumbnail">≡</span>}
            caption="OPERACIÓN DEL CATÁLOGO"
            closeRef={closeRef}
            panelRef={panelRef}
            onClose={() => setExpanded(false)}
          >
            <div className="b-drawer-content">
              <p>
                Las propuestas se revisan y guardan individualmente. No se
                aprueban fichas ni se publica automáticamente.
              </p>
              <p>Para tareas sin documentación, «Buscar posible fabricante»
                abre una consulta externa con el nombre de esa variante; sus
                resultados no están verificados. «Investigar y revisar fuente»
                abre Evidencias para registrar y comprobar la identidad y
                procedencia antes de generar contenido.</p>
              <p>Este piloto admite hasta 100 variantes por selección. Cada clic en
                «Procesar siguiente grupo» prepara hasta 5 variantes sin IA paga y
                sin ejecutar trabajo en segundo plano. Se requiere una revisión
                humana independiente antes de guardar cada ficha.</p>
              {capabilities?.documents === true && (
                <ReviewedEvidenceBatch
                  ids={ids}
                  csrf={csrf}
                  disabled={locked}
                  onOpen={(id) => {
                    setExpanded(false);
                    onOpen(id, undefined, "Evidencias");
                  }}
                />
              )}
              {capabilities?.documents === true && (
                <CommercialPreparationPlan
                  ids={ids}
                  csrf={csrf}
                  disabled={locked}
                  onOpen={(id, tab) => {
                    setExpanded(false);
                    onOpen(id, undefined, tab);
                  }}
                />
              )}
              {(capabilities?.document_resumable_intake === true ||
                capabilities?.document_intake_state === true) && (
                <ManufacturerIntakeQueue
                  csrf={csrf}
                  selected={ids}
                  sitemap={sitemapResult}
                  disabled={locked}
                  executionEnabled={capabilities?.document_resumable_intake === true}
                  onOpen={(id) => {
                    setExpanded(false);
                    onOpen(id, undefined, "Evidencias");
                  }}
                />
              )}
              {capabilities?.document_sitemap_discovery === true && (
                <section className="b-detail" aria-label="Descubrimiento de fabricante">
                  <h3>Buscar fuentes oficiales por fabricante</h3>
                  <p>
                    Seleccioná hasta 20 variantes de un mismo fabricante e ingresá
                    una vez la URL exacta de su sitemap de productos. KIKI coteja
                    las páginas publicadas sin descargar fichas ni aprobar datos.
                  </p>
                  <label>
                    Sitemap XML oficial del fabricante
                    <input
                      type="url"
                      aria-label="Sitemap XML oficial del fabricante"
                      placeholder="https://fabricante.com/product-sitemap.xml"
                      value={sitemapUrl}
                      onChange={(event) => {
                        setSitemapUrl(event.target.value);
                        setSitemapResult(undefined);
                        setCapturedManufacturerIds([]);
                      }}
                      disabled={locked}
                    />
                  </label>
                  <div className="b-actions">
                    <button
                      type="button"
                      disabled={locked || !ids.size || ids.size > 20 || !sitemapUrl.startsWith("https://")}
                      onClick={() => void discoverManufacturer()}
                    >
                      Buscar fuentes para {ids.size} variantes
                    </button>
                  </div>
                  {sitemapResult && capabilities?.document_batch_source_import === true &&
                    capabilities?.document_resumable_intake !== true && (
                    <div className="b-actions">
                      <p>
                        La incorporación por lotes conserva hasta 2 HTML originales por paso.
                        Las fuentes quedan pendientes de comprobar. No se aprueban hechos.
                      </p>
                      <button
                        type="button"
                        disabled={locked || !sitemapResult.items.some((item) =>
                          ids.has(item.ecomm_id) &&
                          !capturedManufacturerIds.includes(item.ecomm_id) &&
                          item.state === "CANDIDATES" &&
                          item.ambiguous === false &&
                          item.candidate_count === 1 &&
                          item.candidates.length === 1
                        )}
                        onClick={() => void captureManufacturer()}
                      >
                        Incorporar siguientes 2 fuentes candidatas
                      </button>
                    </div>
                  )}
                  {sitemapResult && (
                    <div role="region" aria-label="Posibles fuentes oficiales">
                      <p>
                        {sitemapResult.receipt.urls_inspected} URLs de producto
                        examinadas. Todas las coincidencias requieren revisión.
                      </p>
                      {sitemapResult.items.map((item) => (
                        <article key={item.ecomm_id}>
                          <strong>{item.name || item.ecomm_id}</strong>
                          <p>
                            {capturedManufacturerIds.includes(item.ecomm_id) ? "Original incorporado; evidencia pendiente de revisión · " : ""}
                            {item.candidate_count} posibles páginas ·
                            {item.ambiguous ? " coincidencia no inequívoca" : " revisar identidad"}
                          </p>
                          {item.reasons.map((reason) => <p key={reason}>{reason}</p>)}
                          {item.candidates.map((candidate) => (
                            <p key={candidate.url}>
                              <a href={candidate.url} target="_blank" rel="noopener noreferrer">
                                Examinar posible fuente del fabricante
                              </a>
                              {" · "}Coincidencias: {candidate.matched_tokens.join(", ")}
                            </p>
                          ))}
                          <button
                            type="button"
                            disabled={locked}
                            onClick={() => {
                              setExpanded(false);
                              onOpen(item.ecomm_id, undefined, "Evidencias");
                            }}
                          >
                            Revisar evidencia de esta variante
                          </button>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              )}
              <div className="b-actions">
                <label>
                  Operación
                  <select
                    aria-label="Operación del lote"
                    disabled={locked}
                    value={operation}
                    onChange={(e) => setOperation(e.target.value)}
                  >
                    <option value="GENERATE_PROPOSALS">
                      Preparar propuestas para campos vacíos
                    </option>
                    <option value="REVIEW_TASKS">
                      Crear tareas de revisión
                    </option>
                  </select>
                </label>
                <button
                  disabled={locked || !ids.size || ids.size > PILOT_BATCH_LIMIT}
                  onClick={() => preview(false)}
                >
                  Previsualizar selección
                </button>
                <button
                  disabled={locked || !matches || matches > PILOT_BATCH_LIMIT}
                  onClick={() => preview(true)}
                >
                  Previsualizar {matches} resultados filtrados
                </button>
              </div>
              <p>
                {environmentText(
                  "Entorno aislado: productos y aprobaciones de prueba, sin decisiones comerciales del cliente. Presupuesto de IA real: USD 0.",
                  "Generador determinista existente, sin consumo OpenAI. Cada propuesta requiere revisión humana individual; no se sobrescriben fichas aprobadas.",
                )}
              </p>
              {error && <p role="alert">{error}</p>}
              {batch && (
                <div
                  className="b-detail"
                  role="region"
                  aria-label="Detalle del lote"
                  data-batch-id={batch.id}
                  data-batch-state={batch.public_state || batch.state}
                >
                  <div className="b-heading">
                    <h3>
                      {batch.state === "PREVIEW"
                        ? "Revisá antes de iniciar"
                        : "Resultados del lote"}
                    </h3>
                    <strong role="status">
                      {labels[batch.public_state || batch.state]} ·{" "}
                      {batch.total} variantes exactas
                    </strong>
                  </div>
                  <small>
                    Lote {batch.id} ·{" "}
                    {batch.operation === "REVIEW_TASKS"
                      ? "Tareas de revisión"
                      : "Propuestas editoriales"}{" "}
                    · {captureDate(batch.created_at)}
                  </small>
                  <p>
                    Resumen calculado al previsualizar (
                    {captureDate(batch.created_at)}
                    ). Los resultados por variante muestran la revalidación
                    posterior.
                  </p>
                  <dl className="b-summary">
                    {Object.entries({
                      sufficient_evidence: "Con hechos aprobados vigentes",
                      no_documentation: "Sin documentación",
                      conflicts: "Con conflictos",
                      stale: "Información desactualizada",
                      eligible: "Pueden recibir propuestas",
                      human_required: "Requieren revisión humana",
                    }).map(([key, label]) => (
                      <div key={key}>
                        <dt>{label}</dt>
                        <dd>{batch.summary[key] ?? 0}</dd>
                      </div>
                    ))}
                  </dl>
                  <p>
                    Los grupos pueden superponerse. Tener respaldo para algunos
                    campos no significa tener una ficha completa. Se conservarán
                    todos los campos ya completados.
                  </p>
                  <p data-testid="batch-progress">
                    Procesadas: {batch.progress?.processed ?? 0}/{batch.total} ·
                    Completadas: {batch.progress?.completed ?? 0} · Bloqueadas:{" "}
                    {batch.progress?.blocked ?? 0} · Pendientes:{" "}
                    {batch.progress?.pending ?? 0}.{" "}
                    {Object.entries(batch.counts)
                      .map(([s, n]) => `${labels[s]}: ${n}`)
                      .join(" · ")}
                  </p>
                  <div className="b-actions">
                    {batch.state === "PREVIEW" && (
                      <button
                        className="d-primary"
                        disabled={locked}
                        onClick={run}
                      >
                        {batch.autonomous ? "Confirmar e iniciar lote" : "Confirmar lote para procesar por pasos"}
                      </button>
                    )}
                    {!batch.autonomous &&
                      batch.state === "PENDING" && (
                        <button
                          className="d-primary"
                          disabled={locked || batch.cancel_requested}
                          onClick={processManualStep}
                        >
                          Procesar siguiente grupo (hasta 5 variantes)
                        </button>
                      )}
                    {batch.state === "PREPARING" && (
                      <p role="status">
                        Analizando {batch.progress.prepared} de {batch.total}{" "}
                        variantes. Podés continuar con el catálogo; todavía no
                        se ejecuta ninguna operación.
                      </p>
                    )}
                    {["PREPARING", "PREVIEW", "PENDING", "RUNNING"].includes(
                      batch.state,
                    ) && (
                      <button
                        disabled={locked || batch.cancel_requested}
                        onClick={() => {
                          if (
                            window.confirm(
                              "¿Cancelar lo pendiente? Las propuestas ya preparadas se conservan.",
                            )
                          )
                            act(async () => {
                              await api(`/${batch.id}/cancel`, csrf, {
                                expected_revision: batch.revision,
                              });
                              await detail(batch.id);
                              await list();
                            });
                        }}
                      >
                        Cancelar lote
                      </button>
                    )}
                    {!!batch.counts.ERROR && batch.state !== "CANCELLED" && (
                      <button
                        disabled={locked}
                        onClick={() =>
                          act(async () => {
                            await api(`/${batch.id}/retry`, csrf, {
                              expected_revision: batch.revision,
                            });
                            await detail(batch.id);
                          })
                        }
                      >
                        Habilitar reintento de errores (máx. 3)
                      </button>
                    )}
                    <button
                      disabled={locked}
                      onClick={() =>
                        act(async () => {
                          await detail(batch.id, batch.page || 1);
                        })
                      }
                    >
                      Recuperar estado guardado
                    </button>
                  </div>
                  <p>
                    Autorizado por:{" "}
                    {batch.authorized_by ?? "Todavía no autorizado"}. Sin
                    guardado automático, OpenAI ni publicación externa.
                  </p>
                  <div className="b-items">
                    {batch.items?.map((item) => (
                      <article
                        key={item.ecomm_id}
                        data-batch-ecomm={item.ecomm_id}
                      >
                        <div>
                          <strong>
                            {item.result.preview?.name ||
                              `Ecomm ID ${item.ecomm_id}`}
                          </strong>
                          <small>
                            Ecomm ID {item.ecomm_id} ·{" "}
                            {item.result.preview?.presentation} ·{" "}
                            {item.result.preview?.is_combo
                              ? "Pack / combo"
                              : "Variante individual; no se fusiona por EAN"}
                          </small>
                          <span>
                            {labels[item.state]} · Intentos {item.attempts}
                          </span>
                          {item.error.message && <p>{item.error.message}</p>}
                          {item.error.reasons?.map((r) => (
                            <p key={r}>{r}</p>
                          ))}
                          {item.result.task && (
                            <div>
                              <p>
                                Tarea preparada para revisión humana; la ficha
                                no fue modificada.
                              </p>
                              <small>
                                {item.result.task.review_schedule?.review_due
                                  ? "Revisión mensual vencida"
                                  : "Próxima revisión mensual"}
                                :{" "}
                                {captureDate(
                                  item.result.task.review_schedule
                                    ?.next_review_at ?? null,
                                )}
                              </small>
                              {item.result.task.revoked && (
                                <p>
                                  Evidencia revocada: corroborar nuevamente las
                                  afirmaciones.
                                </p>
                              )}
                              {item.result.task.documents_changed && (
                                <p>
                                  Documentación modificada: revisar la versión y
                                  sus citas.
                                </p>
                              )}
                              {item.result.task.reasons?.map((reason) => (
                                <p key={reason}>{reason}</p>
                              ))}
                            </div>
                          )}
                          {!!item.result.fields_without_support?.length && (
                            <small>
                              Campos pendientes:{" "}
                              {item.result.fields_without_support.join(", ")}
                            </small>
                          )}
                        </div>
                        <div className="b-actions">
                          <button
                            disabled={locked}
                            onClick={() => {
                              setExpanded(false);
                              onOpen(item.ecomm_id, item.result.proposal_id);
                            }}
                          >
                            {item.result.proposal_id
                              ? `Revisar propuesta #${item.result.proposal_id}`
                              : "Revisar producto"}
                          </button>
                          {!item.result.proposal_id && (
                            <>
                              {item.result.preview?.name && <a
                                href={officialSourceSearchUrl(
                                  item.result.preview?.name || "",
                                  item.result.preview?.presentation,
                                )}
                                target="_blank"
                                rel="noopener noreferrer"
                                title="Abre una búsqueda externa. Los resultados son candidatos, no fuentes verificadas."
                              >
                                Buscar posible fabricante ↗
                              </a>}
                              <button
                                type="button"
                                disabled={locked}
                                onClick={() => {
                                  setExpanded(false);
                                  onOpen(item.ecomm_id, undefined, "Evidencias");
                                }}
                              >
                                Investigar y revisar fuente
                              </button>
                            </>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                  <div className="b-actions">
                    <button
                      disabled={locked || (batch.page || 1) <= 1}
                      onClick={() =>
                        act(async () => {
                          await detail(batch.id, (batch.page || 1) - 1);
                        })
                      }
                    >
                      Resultados anteriores
                    </button>
                    <span>Página {batch.page || 1}</span>
                    <button
                      disabled={locked || (batch.page || 1) * 10 >= batch.total}
                      onClick={() =>
                        act(async () => {
                          await detail(batch.id, (batch.page || 1) + 1);
                        })
                      }
                    >
                      Más resultados
                    </button>
                    <button
                      disabled={locked}
                      onClick={() => {
                        setBatch(undefined);
                        setExpanded(false);
                      }}
                    >
                      Cerrar detalle
                    </button>
                  </div>
                  <details>
                    <summary>Autorización e historial del lote</summary>
                    {batch.history.map((h, i) => (
                      <p key={i}>
                        {captureDate(h.at)} · {h.action} · {h.actor}
                      </p>
                    ))}
                  </details>
                </div>
              )}
              <details>
                <summary>Lotes guardados ({jobsTotal})</summary>
                <p>
                  Los lotes confirmados continúan en el backend. Abrí uno para
                  recuperar su progreso y resultados.
                </p>
                <div className="b-actions">
                  {jobs.map((job) => (
                    <button
                      disabled={locked}
                      key={job.id}
                      onClick={() =>
                        act(async () => {
                          await detail(job.id);
                        })
                      }
                    >
                      {captureDate(job.created_at)} · {job.total} variantes ·{" "}
                      {labels[job.public_state || job.state]}
                    </button>
                  ))}
                </div>
                <div className="b-actions">
                  <button
                    disabled={locked || jobsPage === 1}
                    onClick={() => setJobsPage((p) => p - 1)}
                  >
                    Lotes anteriores
                  </button>
                  <span>Página {jobsPage}</span>
                  <button
                    disabled={locked || jobsPage * 5 >= jobsTotal}
                    onClick={() => setJobsPage((p) => p + 1)}
                  >
                    Más lotes
                  </button>
                  <button disabled={locked} onClick={() => act(() => list())}>
                    Actualizar cola
                  </button>
                </div>
              </details>
            </div>
          </ProductDrawer>,
          document.body,
        )}
    </section>
  );
}
