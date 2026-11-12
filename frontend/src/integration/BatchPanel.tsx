import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { ProductDrawer } from "../prototype/CatalogView";
import { request, captureDate, validVariantId } from "./catalog-adapter";
import "./batches.css";
const root = "/api/ecomm-app/editorial-batches";
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
  onOpen: (id: string, proposal?: number) => void;
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
  async function run() {
    if (!batch) return;
    await act(async () => {
      if (!batch.autonomous)
        throw new Error(
          "El backend no tiene habilitada la ejecución autónoma; no se confirmó el lote.",
        );
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
  useEffect(() => {
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
  }, [batch?.id, batch?.state, batch?.page, batch?.cancel_requested, jobsPage]);
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
            subtitle="La ejecución continúa en el backend aunque cierres este panel o el navegador."
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
                  disabled={locked || !ids.size}
                  onClick={() => preview(false)}
                >
                  Previsualizar selección
                </button>
                <button
                  disabled={locked || !matches}
                  onClick={() => preview(true)}
                >
                  Previsualizar {matches} resultados filtrados
                </button>
              </div>
              <p>
                Entorno aislado: productos y aprobaciones de prueba, sin
                decisiones comerciales del cliente. Presupuesto de IA real: USD
                0.
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
                        disabled={locked || !batch.autonomous}
                        onClick={run}
                      >
                        Confirmar e iniciar lote
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
