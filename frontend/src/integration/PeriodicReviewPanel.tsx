import { useState } from "react";
import { request } from "./catalog-adapter";

type Settings = {
  enabled: boolean;
  interval_days: number;
  evidence_max_age_days: number;
  soon_days: number;
};
type Policy = {
  version: number;
  settings: Settings;
  editorial_signoff_max_days: 30;
  background_worker_enabled: boolean;
  external_writes_enabled: false;
  history: { at: string; actor: string; reason: string; version: number }[];
};
type Task = {
  task_id: string;
  ecomm_id: string;
  sku: string;
  name: string;
  presentation: string | null;
  state: "HUMAN_REVIEW_REQUIRED";
  reasons: string[];
  actions: string[];
  automatic_changes: 0;
};
type Tasks = {
  schema_version: "kiki-periodic-review-v1";
  policy: Policy;
  total_variants: number;
  total_tasks: number;
  page: number;
  limit: number;
  items: Task[];
  last_general_review_at: string | null;
  next_general_review_at: string | null;
  schedule_due: boolean;
  schedule_soon: boolean;
  execution: "ON_REQUEST_REVIEW_TASKS_NO_BACKGROUND_WORKER";
  source_changes_scope: "ARCHIVED_DOCUMENT_VERSIONS_NOT_LIVE_WEB";
  external_writes_enabled: false;
  commercial_changes: 0;
  facts_approved: 0;
};
const base = "/api/ecomm-app/workspace/reports/periodic";
const isCount = (value: unknown) =>
  Number.isSafeInteger(value) && Number(value) >= 0;

function checkPolicy(value: unknown): Policy {
  const policy = value as Policy;
  if (
    !policy ||
    !isCount(policy.version) ||
    !policy.settings ||
    typeof policy.settings.enabled !== "boolean" ||
    policy.settings.interval_days > 30 ||
    ![
      policy.settings.interval_days,
      policy.settings.evidence_max_age_days,
    ].every((n) => Number.isSafeInteger(n) && n >= 1 && n <= 365) ||
    !Number.isSafeInteger(policy.settings.soon_days) ||
    policy.settings.soon_days < 0 ||
    policy.settings.soon_days > 30 ||
    typeof policy.background_worker_enabled !== "boolean" ||
    policy.external_writes_enabled !== false ||
    policy.editorial_signoff_max_days !== 30 ||
    !Array.isArray(policy.history)
  )
    throw new Error(
      "La programación no conserva el contrato seguro de revisión.",
    );
  return policy;
}
function date(value: string | null) {
  if (!value) return "Sin constancia registrada";
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return "Fecha pendiente de verificar";
  return new Intl.DateTimeFormat("es-AR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Argentina/Buenos_Aires",
  }).format(parsed);
}

export function PeriodicReviewPanel({
  csrf,
  disabled,
  onOpen,
}: {
  csrf: string;
  disabled: boolean;
  onOpen: (id: string, tab: "Ficha" | "Evidencias") => void;
}) {
  const [policy, setPolicy] = useState<Policy>();
  const [draft, setDraft] = useState<Settings>();
  const [tasks, setTasks] = useState<Tasks>();
  const [automation, setAutomation] = useState<{
    enabled: boolean;
    state: string | null;
    next_due_at: string | null;
    last_run: { report_id: string; completed_at: string } | null;
  }>();
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dirty =
    !!policy &&
    !!draft &&
    JSON.stringify(policy.settings) !== JSON.stringify(draft);
  async function read(path: string) {
    const response = await request(base + path);
    const value = await response.json();
    if (!response.ok)
      throw new Error(value.detail || "No se pudo recuperar la revisión.");
    return value;
  }
  async function loadAutomation() {
    setBusy(true);
    setError("");
    try {
      const body = await (await request(base + "/automation")).json();
      if (
        typeof body.enabled !== "boolean" ||
        body.external_writes_enabled !== false ||
        body.scope !== "ARCHIVED_CAPTURES_ONLY_NO_WEB_OR_HUMAN_APPROVAL"
      )
        throw new Error(
          "No se pudo verificar el estado del diagnóstico automático.",
        );
      setAutomation(body);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadPolicy() {
    if (busy || disabled) return;
    if (
      dirty &&
      !window.confirm(
        "¿Descartar los cambios de programación sin guardar y recuperar la versión actual?",
      )
    )
      return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const value = checkPolicy(await read("/policy"));
      setPolicy(value);
      setDraft({ ...value.settings });
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadTasks(page = 1) {
    if (busy || disabled) return;
    setBusy(true);
    setError("");
    try {
      const value = (await read(`/tasks?page=${page}&limit=20`)) as Tasks;
      checkPolicy(value.policy);
      if (
        value.schema_version !== "kiki-periodic-review-v1" ||
        value.execution !== "ON_REQUEST_REVIEW_TASKS_NO_BACKGROUND_WORKER" ||
        value.source_changes_scope !==
          "ARCHIVED_DOCUMENT_VERSIONS_NOT_LIVE_WEB" ||
        value.external_writes_enabled !== false ||
        value.commercial_changes !== 0 ||
        value.facts_approved !== 0 ||
        !isCount(value.total_variants) ||
        !isCount(value.total_tasks) ||
        value.total_tasks > value.total_variants ||
        value.page !== page ||
        value.limit !== 20 ||
        !Array.isArray(value.items) ||
        value.items.length > 20 ||
        value.items.some(
          (item) =>
            !item.ecomm_id ||
            item.state !== "HUMAN_REVIEW_REQUIRED" ||
            item.automatic_changes !== 0 ||
            !Array.isArray(item.actions),
        )
      )
        throw new Error(
          "Las tareas no corresponden al contrato de revisión del catálogo.",
        );
      setTasks(value);
      if (!policy) {
        setPolicy(value.policy);
        setDraft({ ...value.policy.settings });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function savePolicy() {
    if (
      !policy ||
      !draft ||
      !confirmed ||
      reason.trim().length < 20 ||
      busy ||
      disabled
    )
      return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await request(base + "/policy", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          expected_version: policy.version,
          settings: draft,
          reason,
          confirm: true,
        }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          body.detail ||
            "No se guardó la programación; recuperá la versión actual.",
        );
      const value = checkPolicy(body);
      setPolicy(value);
      setDraft({ ...value.settings });
      setConfirmed(false);
      setTasks(undefined);
      setMessage(
        `Programación guardada, versión ${value.version}. No se modificaron fichas ni se aprobaron hechos.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const valid =
    !!draft &&
    [draft.interval_days, draft.evidence_max_age_days].every(
      (n) => Number.isSafeInteger(n) && n >= 1 && n <= 365,
    ) &&
    draft.interval_days <= 30 &&
    Number.isSafeInteger(draft.soon_days) &&
    draft.soon_days >= 0 &&
    draft.soon_days <= 30;
  return (
    <details className="b-detail" aria-label="Revisión periódica del catálogo">
      <summary>Revisión periódica y pendientes</summary>
      <p>
        Los pendientes se calculan cuando consultás esta vista. Se comparan
        fichas y documentos archivados; no se comprueban sitios web. Los
        informes automáticos requieren activar expresamente el ejecutor
        existente y su opción de revisión periódica.
      </p>
      <div className="b-actions">
        <button
          disabled={busy || disabled}
          onClick={() => void loadAutomation()}
        >
          Ver último diagnóstico automático
        </button>
        <button
          type="button"
          disabled={busy || disabled}
          onClick={() => void loadTasks()}
        >
          Consultar pendientes de revisión
        </button>
        <button
          type="button"
          disabled={busy || disabled}
          onClick={() => void loadPolicy()}
        >
          Recuperar programación
        </button>
      </div>
      {automation && (
        <p>
          {automation.enabled
            ? "Diagnóstico automático habilitado"
            : "Diagnóstico automático deshabilitado"}
          .{" "}
          {automation.last_run
            ? `Último informe: ${automation.last_run.report_id} · ${date(automation.last_run.completed_at)}.`
            : "Todavía no hay informes automáticos."}{" "}
          {automation.next_due_at
            ? `Próximo ciclo: ${date(automation.next_due_at)}.`
            : ""}{" "}
          No acredita revisión humana de los productos.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {policy && draft && (
        <fieldset disabled={busy || disabled}>
          <legend>Programación interna · versión {policy.version}</legend>
          <p>
            {policy.background_worker_enabled
              ? "Ejecutor automático habilitado: diagnóstico de capturas, sin aprobaciones humanas."
              : "Informes automáticos deshabilitados; la consulta manual sigue disponible."}
          </p>
          <p>
            La aprobación editorial mantiene su límite de 30 días. Esta
            programación no lo extiende ni confirma revisiones humanas.
          </p>
          <label>
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => {
                setDraft({ ...draft, enabled: e.target.checked });
                setConfirmed(false);
              }}
            />
            Calcular vencimientos de revisión general
          </label>
          <label>
            Revisión general cada cuántos días
            <input
              type="number"
              min={1}
              max={30}
              value={draft.interval_days}
              onChange={(e) => {
                setDraft({ ...draft, interval_days: Number(e.target.value) });
                setConfirmed(false);
              }}
            />
          </label>
          <label>
            Revisar evidencia a partir de cuántos días
            <input
              type="number"
              min={1}
              max={365}
              value={draft.evidence_max_age_days}
              onChange={(e) => {
                setDraft({
                  ...draft,
                  evidence_max_age_days: Number(e.target.value),
                });
                setConfirmed(false);
              }}
            />
          </label>
          <label>
            Avisar cuántos días antes
            <input
              type="number"
              min={0}
              max={30}
              value={draft.soon_days}
              onChange={(e) => {
                setDraft({ ...draft, soon_days: Number(e.target.value) });
                setConfirmed(false);
              }}
            />
          </label>
          {dirty && <p>Hay cambios de programación sin guardar.</p>}
          <label>
            Motivo de la programación
            <textarea
              maxLength={600}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                setConfirmed(false);
              }}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Confirmo este cambio de programación interna.
          </label>
          <button
            type="button"
            disabled={!valid || !confirmed || reason.trim().length < 20}
            onClick={() => void savePolicy()}
          >
            Guardar programación de revisión
          </button>
          {!!policy.history.length && (
            <details>
              <summary>Historial de programación</summary>
              {policy.history
                .slice(-10)
                .reverse()
                .map((entry) => (
                  <p key={entry.version}>
                    Versión {entry.version} · {date(entry.at)} · {entry.actor}:{" "}
                    {entry.reason}
                  </p>
                ))}
            </details>
          )}
        </fieldset>
      )}
      {tasks && (
        <section aria-label="Pendientes de revisión del catálogo">
          <p>
            {tasks.total_tasks} variantes con tareas entre{" "}
            {tasks.total_variants} variantes Ecomm-App. Una variante puede tener
            varios motivos.
          </p>
          <p>
            Última revisión general: {date(tasks.last_general_review_at)} ·
            Próxima referencia: {date(tasks.next_general_review_at)}.
          </p>
          {tasks.schedule_due && (
            <p>Revisión general pendiente según la programación.</p>
          )}
          {tasks.schedule_soon && (
            <p>La próxima revisión general está cercana.</p>
          )}
          {tasks.items.map((item) => (
            <article
              key={item.task_id}
              className="b-detail"
              data-periodic-ecomm={item.ecomm_id}
            >
              <strong>{item.name || item.ecomm_id}</strong>
              <p>
                SKU {item.sku || "sin informar"} · Ecomm ID {item.ecomm_id} ·{" "}
                {item.presentation || "Presentación pendiente"}
              </p>
              <ul>
                {item.actions.map((action, index) => (
                  <li key={index}>{action}</li>
                ))}
              </ul>
              <button
                type="button"
                disabled={busy || disabled}
                onClick={() =>
                  onOpen(
                    item.ecomm_id,
                    item.reasons.some((r) => /SOURCE|EVIDENCE/.test(r))
                      ? "Evidencias"
                      : "Ficha",
                  )
                }
              >
                Revisar variante
              </button>
            </article>
          ))}
          {!tasks.total_tasks && (
            <p>
              No hay pendientes detectados en los datos archivados. Esto no
              acredita una comprobación actual de proveedores.
            </p>
          )}
          <div className="b-actions">
            <button
              type="button"
              disabled={busy || disabled || tasks.page <= 1}
              onClick={() => void loadTasks(tasks.page - 1)}
            >
              Pendientes anteriores
            </button>
            <span>
              Página {tasks.page} de{" "}
              {Math.max(1, Math.ceil(tasks.total_tasks / tasks.limit))}
            </span>
            <button
              type="button"
              disabled={
                busy ||
                disabled ||
                tasks.page * tasks.limit >= tasks.total_tasks
              }
              onClick={() => void loadTasks(tasks.page + 1)}
            >
              Pendientes siguientes
            </button>
          </div>
        </section>
      )}
    </details>
  );
}
