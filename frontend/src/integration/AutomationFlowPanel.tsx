import { useEffect, useRef, useState } from "react";
import { request, validVariantId } from "./catalog-adapter";
const root = "/api/ecomm-app/workspace/research/automation";
const stateText: Record<string,string> = {
 PENDING:"Pendiente", RUNNING:"En proceso", COMPLETED:"Incorporación documental terminada · ficha por revisar",
 CANCELLED:"Cancelado", BLOCKED:"Requiere intervención", FAILED:"Error de investigación",
 IMPORTED:"Original incorporado", ALREADY_PRESENT:"Original reutilizado", READY:"Respaldo disponible · requiere revisión",
 RESEARCH:"Investigación pendiente", REVIEW_REQUIRED:"Revisión necesaria",
 EVIDENCE_REVIEW_REQUIRED:"Revisar y aprobar hechos documentales", PROPOSAL_REVIEW_REQUIRED:"Revisar campos de la propuesta",
 DRAFT_SAVED:"Borrador interno guardado · sin publicación", COMPLETED_WITH_BLOCKS:"Incorporación terminada con excepciones",
};
const statusText = (state:string) => stateText[state] || "Estado pendiente de revisión";

type Job = {
  id: string;
  revision: number;
  state: string;
  total: number;
  items: {
    ecomm_id: string;
    state: string;
    public_state?: string;
    url?: string;
    error?: unknown;
    automation?: { proposal_id?: number; [key: string]: unknown };
  }[];
  external_writes_enabled: false;
  manual_steps_only?: boolean;
};
type Capabilities = {
  enabled: boolean;
  search_configured: boolean;
  download_authorized: boolean;
  max_items: number;
  provider: string;
  external_writes_enabled: false;
};
export function AutomationFlowPanel({
  ids,
  csrf,
  disabled,
  onOpen,
}: {
  ids: Set<string>;
  csrf: string;
  disabled: boolean;
  onOpen: (id: string) => void;
}) {
  const [cap, setCap] = useState<Capabilities>();
  const [job, setJob] = useState<Job>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [sourceReasons, setSourceReasons] = useState<Record<string, string>>(
    {},
  );
  const [busy, setBusy] = useState(false),
    [running, setRunning] = useState(false),
    [confirmed, setConfirmed] = useState(false),
    [error, setError] = useState("");
  const pause = useRef(true);
  const alive = useRef(true);
  const requestKey = useRef(crypto.randomUUID());
  const selectionKey = [...ids].sort().join(",");
  const selectionRef = useRef(selectionKey);
  selectionRef.current = selectionKey;
  useEffect(() => {
    alive.current = true;
    return () => {
      pause.current = true;
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    pause.current = true;
    setJob(undefined);
    setConfirmed(false);
    requestKey.current = crypto.randomUUID();
  }, [selectionKey]);
  async function api(path: string, body?: unknown) {
    const response = await request(
      root + path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": csrf,
            },
            body: JSON.stringify(body),
          },
    );
    return response.json();
  }
  function checked(value: Job, expected?: Job | Set<string>): Job {
    if (
      !value ||
      !/^[a-f0-9-]{36}$/.test(value.id) ||
      !Number.isSafeInteger(value.revision) ||
      value.total < 1 ||
      value.total > 20 ||
      !Array.isArray(value.items) ||
      value.items.length !== value.total ||
      new Set(value.items.map((i) => i.ecomm_id)).size !== value.total ||
      value.items.some((i) => !validVariantId(i.ecomm_id)) ||
      value.external_writes_enabled !== false
    )
      throw new Error(
        "El resultado no corresponde a un lote documental interno.",
      );
    if (expected) {
      const expectedIds =
        expected instanceof Set
          ? [...expected].sort()
          : expected.items.map((i) => i.ecomm_id).sort();
      if (
        expectedIds.join(",") !==
          value.items
            .map((i) => i.ecomm_id)
            .sort()
            .join(",") ||
        (!(expected instanceof Set) &&
          (value.id !== expected.id || value.revision < expected.revision))
      ) {
        throw new Error(
          "La respuesta cambió el lote, su selección o su versión. Se detuvo el procesamiento.",
        );
      }
    }
    return value;
  }
  async function inspect() {
    setBusy(true);
    setError("");
    try {
      const c = (await api("/capabilities")) as Capabilities;
      if (c.external_writes_enabled !== false || c.max_items !== 20)
        throw new Error("Configuración de automatización incompatible.");
      setCap(c);
      const list = await api("");
      setJobs(
        Array.isArray(list.items) ? list.items.map((j: Job) => checked(j)) : [],
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function execute(current: Job) {
    pause.current = false;
    setRunning(true);
    setError("");
    try {
      let next = current;
      for (let count = 0; count < 20 && !pause.current; count++) {
        if (!next.items.some((i) => i.state === "PENDING")) break;
        next = checked(
          await api(`/${next.id}/step`, {
            expected_revision: next.revision,
            confirm: true,
          }),
          next,
        );
        if (alive.current) setJob(next);
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      pause.current = true;
      if (alive.current) setRunning(false);
    }
  }
  async function create() {
    if (
      !confirmed ||
      !cap?.enabled ||
      !cap.search_configured ||
      !cap.download_authorized ||
      disabled
    )
      return;
    setBusy(true);
    setError("");
    const createdForSelection = selectionKey;
    const expectedIds = new Set(ids);
    try {
      const value = checked(
        await api("", {
          request_key: requestKey.current,
          ecomm_ids: [...ids],
          confirm: true,
        }),
        expectedIds,
      );
      if (selectionRef.current !== createdForSelection)
        throw new Error(
          "Cambió la selección. El lote permanece guardado; recuperalo antes de continuar.",
        );
      setJob(value);
      setConfirmed(false);
      await execute(value);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function candidates(
    item: Job["items"][number],
  ): { url: string; title: string; source_kind: string }[] {
    const search = item.automation?.search as { results?: unknown } | undefined;
    if (!Array.isArray(search?.results)) return [];
    return search.results
      .filter(
        (r): r is { url: string; title: string; source_kind: string } =>
          !!r &&
          typeof r.url === "string" &&
          typeof r.title === "string" &&
          typeof r.source_kind === "string",
      )
      .slice(0, 10);
  }
  async function selectSource(id: string, url: string) {
    if (
      !job ||
      busy ||
      running ||
      disabled ||
      (sourceReasons[id] || "").trim().length < 20
    )
      return;
    if (
      !window.confirm(
        "¿Seleccionar esta URL candidata para el lote? La selección no acredita fabricante, identidad ni hechos; las comprobaciones y la revisión documental siguen vigentes.",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const next = checked(
        await api(`/${job.id}/select-source`, {
          expected_revision: job.revision,
          ecomm_id: id,
          url,
          reason: sourceReasons[id],
          confirm: true,
        }),
        job,
      );
      setJob(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function action(
    name: "recover" | "retry" | "cancel" | "proposals",
    id?: string,
  ) {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      setJob(
        checked(
          await api(`/${job.id}/${name}`, {
            expected_revision: job.revision,
            ...(id ? { ecomm_id: id } : {}),
            confirm: true,
          }),
          job,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details aria-label="Investigar y completar productos" className="i-source">
      <summary>Investigar y completar · fuentes verificables primero</summary>
      <p>
        Hasta 20 variantes del catálogo API. Busca fuentes candidatas, incorpora
        solo documentación autorizada y conserva las citas. Los hechos nuevos
        quedan pendientes: revisalos antes de generar propuestas. No se guarda
        ni publica contenido automáticamente.
      </p>
      <button
        disabled={busy || running || disabled}
        onClick={() => void inspect()}
      >
        Comprobar disponibilidad y recuperar lotes
      </button>
      {cap && (
        <p>
          Buscador {cap.provider}:{" "}
          {cap.search_configured ? "configurado" : "sin configurar"}. Descarga:{" "}
          {cap.download_authorized
            ? "autorizada según dominios y permisos"
            : "bloqueada"}
          .{" "}
          {cap.enabled
            ? "Automatización disponible bajo confirmación."
            : "Automatización deshabilitada; no se consultarán proveedores."}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          disabled={disabled || busy || running || !ids.size || ids.size > 20}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        Autorizo investigar estas {ids.size} variantes con los proveedores y
        límites configurados. Revisaré las excepciones y los campos antes de
        guardarlos.
      </label>
      <button
        disabled={
          !confirmed ||
          disabled ||
          busy ||
          running ||
          !cap?.enabled ||
          !cap.search_configured ||
          !cap.download_authorized ||
          !ids.size ||
          ids.size > 20
        }
        onClick={() => void create()}
      >
        Investigar y completar {ids.size} productos
      </button>
      <p>Se aplican límites de consultas por lote y por día. El proveedor de búsqueda puede tener costo; no se estima un importe cuando su tarifa no está acreditada. Este circuito usa propuestas deterministas respaldadas, sin consumir OpenAI automáticamente.</p>
      <p>
        El navegador solicita pasos secuenciales. Pausar o cerrar detiene los
        siguientes pasos; la cola y sus resultados permanecen guardados. El paso
        ya iniciado termina con sus límites de tiempo.
      </p>
      {jobs.map((j) => (
        <button
          key={j.id}
          disabled={busy || running}
          onClick={() =>
            void api(`/${j.id}`)
              .then((v) => setJob(checked(v, j)))
              .catch((e) => setError(e.message))
          }
        >
          Recuperar lote {j.id.slice(0, 8)}
        </button>
      ))}
      {job && (
        <button
          disabled={busy || running || disabled}
          onClick={() => {
            requestKey.current = crypto.randomUUID();
            setJob(undefined);
            setConfirmed(false);
          }}
        >
          Nuevo lote para esta selección
        </button>
      )}
      {job && (
        <section aria-label="Resultado de investigación">
          <h3>
            Lote {job.id.slice(0, 8)} · {statusText(job.state)}
          </h3>
          <p>
            {job.total -
              job.items.filter(
                (i) => i.state === "PENDING" || i.state === "RUNNING",
              ).length}{" "}
            / {job.total} pasos resueltos.
          </p>
          {running ? (
            <button
              onClick={() => {
                pause.current = true;
              }}
            >
              Pausar después del paso actual
            </button>
          ) : (
            <button
              disabled={
                busy ||
                disabled ||
                !job.items.some((i) => i.state === "PENDING")
              }
              onClick={() => void execute(job)}
            >
              Reanudar investigación
            </button>
          )}
          <button
            disabled={busy || running || disabled}
            onClick={() => void action("proposals")}
          >
            Preparar propuestas desde hechos revisados
          </button>
          <button
            disabled={busy || running || disabled}
            onClick={() => void action("recover")}
          >
            Recuperar interrupciones
          </button>
          <button
            disabled={busy || running || disabled}
            onClick={() => void action("cancel")}
          >
            Cancelar pendientes
          </button>
          {job.items.map((i) => (
            <article key={i.ecomm_id}>
              <strong>
                Ecomm {i.ecomm_id} · {statusText(i.public_state || i.state)}
              </strong>
              <p>{i.url || "Fuente exacta pendiente"}</p>
              {Boolean(i.error) && (
                <pre>
                  {typeof i.error === "string"
                    ? i.error
                    : JSON.stringify(i.error)}
                </pre>
              )}
              {candidates(i).length > 0 && (
                <details>
                  <summary>
                    Revisar fuentes candidatas ({candidates(i).length})
                  </summary>
                  <p>
                    Las referencias y sus fragmentos no son evidencia aprobada.
                    Elegí una fuente exacta y documentá por qué corresponde a
                    esta presentación.
                  </p>
                  <label>
                    Motivo de selección de fuente Ecomm {i.ecomm_id}
                    <input
                      value={sourceReasons[i.ecomm_id] || ""}
                      maxLength={600}
                      disabled={busy || running || disabled}
                      onChange={(e) =>
                        setSourceReasons((prev) => ({
                          ...prev,
                          [i.ecomm_id]: e.target.value,
                        }))
                      }
                    />
                  </label>
                  {candidates(i).map((candidate) => (
                    <div key={candidate.url}>
                      <strong>{candidate.title}</strong>
                      <p>{candidate.url}</p>
                      <p>
                        {candidate.source_kind === "OFFICIAL_CANDIDATE"
                          ? "Dominio autorizado candidato · identidad sin aprobar"
                          : "Referencia secundaria · no acredita fuente oficial"}
                      </p>
                      <button
                        disabled={
                          busy ||
                          running ||
                          disabled ||
                          candidate.source_kind !== "OFFICIAL_CANDIDATE" ||
                          [
                            "RUNNING",
                            "IMPORTED",
                            "ALREADY_PRESENT",
                            "CANCELLED",
                          ].includes(i.state) ||
                          (sourceReasons[i.ecomm_id] || "").trim().length < 20
                        }
                        onClick={() =>
                          void selectSource(i.ecomm_id, candidate.url)
                        }
                      >
                        Elegir esta fuente candidata
                      </button>
                    </div>
                  ))}
                </details>
              )}
              <button disabled={running} onClick={() => onOpen(i.ecomm_id)}>
                Revisar evidencia y propuesta
              </button>
              {["FAILED", "BLOCKED"].includes(i.state) && (
                <button
                  disabled={busy || running || disabled}
                  onClick={() => void action("retry", i.ecomm_id)}
                >
                  Reintentar con los límites vigentes
                </button>
              )}
            </article>
          ))}
        </section>
      )}
    </details>
  );
}
