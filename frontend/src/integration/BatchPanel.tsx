import { useEffect, useRef, useState } from "react";
import { request, captureDate, validVariantId } from "./catalog-adapter";
import "./batches.css";
const root = "/api/ecomm-app/editorial-batches";
const labels: Record<string, string> = {
  PREVIEW: "Previsualización",
  PENDING: "Pendiente",
  RUNNING: "En proceso",
  COMPLETED: "Completado",
  BLOCKED: "Bloqueado",
  CONFLICT: "Conflicto",
  ERROR: "Error",
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
  const [batch, setBatch] = useState<Batch>();
  const [jobs, setJobs] = useState<Batch[]>([]);
  const [jobsPage, setJobsPage] = useState(1),
    [jobsTotal, setJobsTotal] = useState(0);
  const [operation, setOperation] = useState("GENERATE_PROPOSALS");
  const [busy, setBusy] = useState(false),
    [running, setRunning] = useState(false),
    [error, setError] = useState("");
  const pause = useRef(false),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      pause.current = true;
    };
  }, []);
  async function list(page = jobsPage) {
    const response = await request(root + `?page=${page}&limit=5`);
    const data = await response.json();
    if (!Array.isArray(data.items))
      throw new Error("No se pudo recuperar la cola.");
    setJobs(data.items);
    setJobsTotal(data.total);
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
  async function run(start: boolean) {
    if (!batch) return;
    const id = batch.id;
    pause.current = false;
    setRunning(true);
    await act(async () => {
      let next = batch;
      if (start) {
        next = await api(`/${id}/start`, csrf, {
          confirm: true,
          expected_revision: batch.revision,
          preview_hash: batch.preview_hash,
          idempotency_key: crypto.randomUUID(),
        });
        setBatch(next);
      }
      let first = true;
      while (
        !pause.current &&
        mounted.current &&
        (next.counts.PENDING || next.counts.RUNNING)
      ) {
        next = await api(`/${id}/step`, csrf, {
          resume_interrupted: first && !start,
        });
        first = false;
        if (mounted.current) setBatch(next);
      }
      if (mounted.current) {
        await detail(id);
        await list();
      }
    });
    if (mounted.current) setRunning(false);
  }
  const locked = busy || disabled;
  return (
    <section className="b-work" aria-label="Trabajo por lotes">
      <div className="b-heading">
        <div>
          <h3>Trabajo por lotes</h3>
          <p>
            Prepará propuestas respaldadas o tareas de revisión. Cada ficha se
            aprueba y guarda individualmente; no se publica.
          </p>
        </div>
        <strong data-testid="selected-count">
          {ids.size} variantes seleccionadas
        </strong>
      </div>
      <div className="b-actions">
        <button disabled={locked} onClick={onPage}>
          Seleccionar esta página
        </button>
        <button disabled={locked || !ids.size} onClick={onClear}>
          Quitar selección
        </button>
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
            <option value="REVIEW_TASKS">Crear tareas de revisión</option>
          </select>
        </label>
        <button disabled={locked || !ids.size} onClick={() => preview(false)}>
          Previsualizar selección
        </button>
        <button disabled={locked || !matches} onClick={() => preview(true)}>
          Previsualizar {matches} resultados filtrados
        </button>
      </div>
      <p>
        Entorno aislado: productos y aprobaciones de prueba, sin decisiones
        comerciales del cliente. Presupuesto de IA real: USD 0.
      </p>
      {error && <p role="alert">{error}</p>}
      <details>
        <summary>Lotes guardados ({jobsTotal})</summary>
        <p>
          Recargar o reiniciar no ejecuta trabajos automáticamente. Abrí un lote
          y elegí Reanudar.
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
              {labels[job.state]}
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
      {batch && (
        <div className="b-detail" role="region" aria-label="Detalle del lote">
          <div className="b-heading">
            <h3>
              {batch.state === "PREVIEW"
                ? "Revisá antes de iniciar"
                : "Resultados del lote"}
            </h3>
            <strong role="status">
              {labels[batch.state]} · {batch.total} variantes exactas
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
            Resumen calculado al previsualizar ({captureDate(batch.created_at)}
            ). Los resultados por variante muestran la revalidación posterior.
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
            Los grupos pueden superponerse. Tener respaldo para algunos campos
            no significa tener una ficha completa. Se conservarán todos los
            campos ya completados.
          </p>
          <p data-testid="batch-progress">
            {Object.entries(batch.counts)
              .map(([s, n]) => `${labels[s]}: ${n}`)
              .join(" · ")}
          </p>
          <div className="b-actions">
            {batch.state === "PREVIEW" ? (
              <button
                className="d-primary"
                disabled={locked}
                onClick={() => run(true)}
              >
                Confirmar e iniciar lote
              </button>
            ) : (
              !["COMPLETED", "CANCELLED"].includes(batch.state) && (
                <button
                  className="d-primary"
                  disabled={
                    locked || !(batch.counts.PENDING || batch.counts.RUNNING)
                  }
                  onClick={() => run(false)}
                >
                  Reanudar lote
                </button>
              )
            )}
            {running && (
              <button
                onClick={() => {
                  pause.current = true;
                }}
              >
                Pausar después de este paso
              </button>
            )}
            {!["COMPLETED", "CANCELLED"].includes(batch.state) && (
              <button
                disabled={locked}
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
            Autorizado por: {batch.authorized_by ?? "Todavía no autorizado"}.
            Sin guardado automático, OpenAI ni publicación externa.
          </p>
          <div className="b-items">
            {batch.items?.map((item) => (
              <article key={item.ecomm_id} data-batch-ecomm={item.ecomm_id}>
                <div>
                  <strong>
                    {item.result.preview?.name || `Ecomm ID ${item.ecomm_id}`}
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
                        Tarea preparada para revisión humana; la ficha no fue
                        modificada.
                      </p>
                      <small>
                        {item.result.task.review_schedule?.review_due
                          ? "Revisión mensual vencida"
                          : "Próxima revisión mensual"}
                        :{" "}
                        {captureDate(
                          item.result.task.review_schedule?.next_review_at ??
                            null,
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
                          Documentación modificada: revisar la versión y sus
                          citas.
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
                  onClick={() => onOpen(item.ecomm_id, item.result.proposal_id)}
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
            <button disabled={locked} onClick={() => setBatch(undefined)}>
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
    </section>
  );
}
