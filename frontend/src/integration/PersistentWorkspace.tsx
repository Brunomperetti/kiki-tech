import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  CommercialBackofficeFields,
  assessCommercialReadiness,
} from "../components/CommercialBackofficeFields";
import type {
  EcommApiProductEdit,
  EcommEditableFields,
  EcommEditStatus,
} from "../types/ecomm-app";
import {
  CatalogError,
  captureDate,
  request,
  unavailable,
  type Variant,
} from "./catalog-adapter";
import {
  cloneFields,
  compatibleWithRow,
  fieldKeys,
  getWorkspace,
  sameIdentity,
  saveWorkspace,
  stateLabels,
} from "./workspace-adapter";
import { ResearchPanel, ResearchSummary } from "./ResearchPanel";
import { ProposalPanel } from "./ProposalPanel";

type Props = {
  variant: Variant;
  csrf: string;
  username: string;
  tab: string;
  onTab: (tab: string) => void;
  onDirty: (value: boolean) => void;
  onBusy: (value: boolean) => void;
  onRecord: (record: EcommApiProductEdit) => void;
  onAuthenticated: (value: unknown) => void;
  onClose: () => void;
};
const tabs = ["Ficha", "Evidencias", "IA", "Canales", "Historial"];
const show = (value: unknown) =>
  typeof value === "string" ? value || "Sin valor" : JSON.stringify(value);
export function PersistentWorkspace({
  variant,
  csrf,
  username,
  tab,
  onTab,
  onDirty,
  onBusy,
  onRecord,
  onAuthenticated,
  onClose,
}: Props) {
  const [record, setRecord] = useState<EcommApiProductEdit>();
  const [fields, setFields] = useState<EcommEditableFields>();
  const [status, setStatus] = useState<EcommEditStatus>("DRAFT");
  const [remote, setRemote] = useState<EcommApiProductEdit>();
  const [loading, setLoading] = useState(true),
    [saving, setSaving] = useState(false);
  const [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const [identityBlocked, setIdentityBlocked] = useState(false),
    [reauth, setReauth] = useState(false);
  const [password, setPassword] = useState("");
  const [loadRevision, reload] = useState(0);
  const [researchBusy, setResearchBusy] = useState(false);
  const [researchStart, setResearchStart] = useState(0);
  const [proposalBusy, setProposalBusy] = useState(false),
    [proposalDirty, setProposalDirty] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error || remote || reauth) contentRef.current?.scrollTo({ top: 0 });
  }, [error, remote, reauth]);
  const dirty =
    !!record &&
    !!fields &&
    (JSON.stringify(record.fields) !== JSON.stringify(fields) ||
      status !== (record.status === "NOT_STARTED" ? "DRAFT" : record.status));
  useEffect(() => {
    onDirty(dirty || proposalDirty);
    return () => onDirty(false);
  }, [dirty, proposalDirty, onDirty]);
  useEffect(() => {
    onBusy(saving || researchBusy || proposalBusy);
    return () => onBusy(false);
  }, [saving, researchBusy, proposalBusy, onBusy]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getWorkspace(variant.id, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setRecord(value);
        setFields(cloneFields(value.fields));
        setStatus(value.status === "NOT_STARTED" ? "DRAFT" : value.status);
        setIdentityBlocked(!compatibleWithRow(value, variant));
        onRecord(value);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err.message);
          setReauth(
            err instanceof CatalogError && [401, 403].includes(err.status),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [variant.id, loadRevision]);
  function adopt(value: EcommApiProductEdit) {
    setRecord(value);
    setFields(cloneFields(value.fields));
    setStatus(value.status === "NOT_STARTED" ? "DRAFT" : value.status);
    setRemote(undefined);
    setIdentityBlocked(!compatibleWithRow(value, variant));
    onRecord(value);
  }
  async function persist(nextStatus: EcommEditStatus) {
    if (!record || !fields || saving || remote || identityBlocked) return;
    if (
      nextStatus !== "DRAFT" &&
      !window.confirm(
        `¿Guardar como «${stateLabels[nextStatus]}»? Es un estado interno; no publica productos.`,
      )
    )
      return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const current = await getWorkspace(variant.id);
      if (
        !compatibleWithRow(current, variant) ||
        !sameIdentity(record.source, current.source)
      ) {
        setIdentityBlocked(true);
        throw new CatalogError(
          409,
          "La identidad de la variante cambió. Guardado bloqueado; conservamos tu edición para compararla.",
        );
      }
      if (current.version !== record.version) {
        setRemote(current);
        return;
      }
      const saved = await saveWorkspace(
        variant.id,
        fields,
        nextStatus,
        record.version,
        csrf,
      );
      adopt(saved);
      setMessage(
        `Guardado en PostgreSQL de pruebas · Versión ${saved.version}.`,
      );
    } catch (err) {
      const failure = err as CatalogError;
      setError(failure.message);
      if ([401, 403].includes(failure.status)) setReauth(true);
      if (failure.status === 409) {
        try {
          const current = await getWorkspace(variant.id);
          if (
            !compatibleWithRow(current, variant) ||
            !sameIdentity(record.source, current.source)
          )
            setIdentityBlocked(true);
          else if (current.version !== record.version) setRemote(current);
        } catch {
          /* Keep local fields and the original error, never invent a saved result. */
        }
      }
    } finally {
      setSaving(false);
    }
  }
  async function authenticate(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      onAuthenticated(await response.json());
      setPassword("");
      setReauth(false);
      setMessage(
        "Sesión restablecida. Tu edición se conservó; volvé a guardar explícitamente.",
      );
      if (!record) reload((value) => value + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <div className="d-drawer-status">
        <span className="d-pill">
          {record ? stateLabels[record.status] : "Consultando ficha"}
        </span>
        <span>
          Versión {record?.version ?? "—"} ·{" "}
          {dirty || proposalDirty
            ? "Cambios sin guardar"
            : "Sin cambios pendientes"}
        </span>
      </div>
      <div
        className="d-tabs"
        role="tablist"
        aria-label="Detalle de la variante"
      >
        {tabs.map((label) => (
          <button
            role="tab"
            disabled={saving || researchBusy || proposalBusy}
            key={label}
            aria-selected={tab === label}
            onClick={() => onTab(label)}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        ref={contentRef}
        className="d-tab-content i-editor"
        role="tabpanel"
        aria-label={tab}
      >
        {loading && (
          <p role="status">Cargando ficha desde PostgreSQL de pruebas…</p>
        )}
        {error && <p role="alert">{error}</p>}
        {message && (
          <p className="i-message" role="status">
            {message}
          </p>
        )}
        {reauth && (
          <form
            onSubmit={authenticate}
            className="i-reauth"
            aria-label="Restablecer sesión"
          >
            <p>
              Tu edición se conserva. Ingresá nuevamente con la cuenta de
              prueba.
            </p>
            <label>
              Contraseña de prueba
              <input
                type="password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
              />
            </label>
            <button disabled={saving}>Restablecer sesión</button>
          </form>
        )}
        {!loading && !record && !reauth && (
          <button onClick={() => reload((value) => value + 1)}>
            Reintentar carga de ficha
          </button>
        )}
        {record && fields && (
          <>
            {identityBlocked && (
              <div className="i-message" role="alert">
                La identidad de Ecomm-App es incompatible con esta ficha o
                cambió desde la consulta. No se permite guardar. Revisá SKU,
                Ecomm ID y presentación.
              </div>
            )}
            {remote && (
              <section className="i-conflict" aria-label="Comparar versiones">
                <h3>Otra sesión guardó una versión nueva</h3>
                <p>
                  Tu base es la versión {record.version}; PostgreSQL tiene la
                  versión {remote.version}. Tu edición permanece intacta.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Campo</th>
                      <th>Tu base</th>
                      <th>Tu edición</th>
                      <th>Versión nueva</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fieldKeys
                      .filter(
                        (key) =>
                          JSON.stringify(fields[key]) !==
                            JSON.stringify(record.fields[key]) ||
                          JSON.stringify(remote.fields[key]) !==
                            JSON.stringify(record.fields[key]),
                      )
                      .map((key) => (
                        <tr key={key}>
                          <th>{key}</th>
                          <td>{show(record.fields[key])}</td>
                          <td>{show(fields[key])}</td>
                          <td>{show(remote.fields[key])}</td>
                        </tr>
                      ))}
                    <tr>
                      <th>Estado editorial</th>
                      <td>{stateLabels[record.status]}</td>
                      <td>{stateLabels[status]}</td>
                      <td>{stateLabels[remote.status]}</td>
                    </tr>
                  </tbody>
                </table>
                <button
                  onClick={() => {
                    if (
                      window.confirm(
                        "¿Descartar tu edición y usar todos los campos de la versión nueva?",
                      )
                    ) {
                      adopt(remote);
                      setError("");
                      setMessage(
                        "Se recuperó la versión nueva desde PostgreSQL.",
                      );
                    }
                  }}
                >
                  Usar versión nueva
                </button>
                <button
                  onClick={() => {
                    if (
                      window.confirm(
                        "¿Conservar todos tus campos para revisar sobre la nueva versión? Un guardado posterior puede reemplazar sus valores. No se guardará automáticamente.",
                      )
                    ) {
                      setRecord(remote);
                      onRecord(remote);
                      setRemote(undefined);
                      setError("");
                      setMessage(
                        "Tu edición se conservó sobre la nueva base. Compará los campos antes de guardar.",
                      );
                    }
                  }}
                >
                  Conservar mi edición para revisar
                </button>
              </section>
            )}
            {tab === "Ficha" && (
              <>
                <button
                  className="d-primary"
                  disabled={
                    dirty ||
                    saving ||
                    researchBusy ||
                    proposalBusy ||
                    identityBlocked ||
                    reauth ||
                    !!remote
                  }
                  onClick={() => {
                    setResearchStart(1);
                    onTab("Evidencias");
                  }}
                >
                  Investigar producto
                </button>
                <ResearchSummary
                  id={variant.id}
                  revision={record.version}
                  onOpen={() => onTab("Evidencias")}
                />
                <details className="i-source" open>
                  <summary>
                    Datos originales de Ecomm-App · Sólo lectura
                  </summary>
                  <dl className="i-details">
                    {[
                      ["Ecomm ID", record.source.ecomm_id],
                      ["SKU", record.source.sku],
                      ["Nombre original", record.source.product_name],
                      [
                        "Presentación original",
                        record.source.variant_description,
                      ],
                      ["Stock de captura", record.source.stock_at_capture],
                      ["EAN original", record.source.gtin],
                      [
                        "Fecha de captura",
                        captureDate(record.source.captured_at),
                      ],
                    ].map(([key, value]) => (
                      <div key={String(key)}>
                        <dt>{key}</dt>
                        <dd>{value ?? unavailable}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
                <p>
                  Los siguientes campos son información comercial editada en
                  KIKI. No modifican el catálogo Ecomm-App ni publicaciones.
                </p>
                <fieldset
                  disabled={saving || identityBlocked}
                  className="i-editor-fields"
                >
                  <legend>Ficha comercial editable de KIKI</legend>
                  <CommercialBackofficeFields
                    fields={fields}
                    onChange={(key, value) => {
                      setFields((previous) =>
                        previous ? { ...previous, [key]: value } : previous,
                      );
                      setMessage("");
                    }}
                    readiness={assessCommercialReadiness(fields)}
                    categories={[]}
                    allowExternalResources={false}
                  />
                  <label className="i-editor-state">
                    Estado editorial
                    <select
                      aria-label="Estado editorial"
                      value={status}
                      onChange={(event) =>
                        setStatus(event.target.value as EcommEditStatus)
                      }
                    >
                      <option value="DRAFT">Borrador</option>
                      <option value="READY_FOR_REVIEW">
                        Lista para revisión
                      </option>
                      <option value="READY_FOR_CHANNELS">
                        Lista para canales (interno)
                      </option>
                    </select>
                  </label>
                </fieldset>
                <p>
                  Las URLs se guardan como texto. No se abren fuentes, imágenes
                  ni videos en este entorno.
                </p>
              </>
            )}
            {tab === "Evidencias" && (
              <>
                <ResearchPanel
                  id={variant.id}
                  csrf={csrf}
                  onBusy={setResearchBusy}
                  workspaceVersion={record.version}
                  autoStart={researchStart}
                  onStarted={() => setResearchStart(0)}
                />
                <h3>Fuentes registradas en KIKI</h3>
                <p>
                  Origen Ecomm-App: {captureDate(record.source.captured_at)}. La
                  verificación es una declaración del operador, sin
                  investigación automática.
                </p>
                {fields.sources.length ? (
                  fields.sources.map((source, index) => (
                    <div className="i-message" key={index}>
                      <strong>{source.name || "Fuente sin nombre"}</strong>
                      <p>
                        {source.kind} ·{" "}
                        {source.verified
                          ? "Verificada por el operador"
                          : "Sin verificar"}
                      </p>
                      <p>{source.url}</p>
                      <p>{source.note}</p>
                    </div>
                  ))
                ) : (
                  <p>Sin fuentes registradas.</p>
                )}
              </>
            )}
            {tab === "Historial" && (
              <>
                <h3>Historial persistido en KIKI</h3>
                <p>
                  Versión actual guardada: {record.version}.{" "}
                  {dirty &&
                    "Los cambios sin guardar no aparecen en este historial."}
                </p>
                {record.history.length ? (
                  [...record.history].reverse().map((event) => (
                    <details className="i-message" key={event.version}>
                      <summary>
                        Versión {event.version} ·{" "}
                        {stateLabels[event.new_status] || event.new_status} ·{" "}
                        {captureDate(event.at)}
                      </summary>
                      <p>
                        {stateLabels[event.previous_status] ||
                          event.previous_status}{" "}
                        → {stateLabels[event.new_status] || event.new_status}
                      </p>
                      {Object.entries(event.changes).map(([key, value]) => (
                        <div key={key}>
                          <strong>{key}</strong>
                          <p>Antes: {show(value.before)}</p>
                          <p>Después: {show(value.after)}</p>
                        </div>
                      ))}
                    </details>
                  ))
                ) : (
                  <p>Todavía no hay versiones guardadas.</p>
                )}
              </>
            )}
            <div hidden={tab !== "IA"}>
              <ProposalPanel
                record={record}
                csrf={csrf}
                active={tab === "IA"}
                blocked={
                  dirty ||
                  identityBlocked ||
                  !!remote ||
                  reauth ||
                  saving ||
                  researchBusy
                }
                onBusy={setProposalBusy}
                onDirty={setProposalDirty}
                onSaved={adopt}
              />
            </div>
            {tab === "Canales" && (
              <>
                <h3>Mercado Libre y Tiendanube</h3>
                <p>
                  {unavailable}. No se habilitaron generación, preparación ni
                  publicaciones.
                </p>
              </>
            )}
            <div className="i-save-bar">
              <span aria-live="polite">
                {saving
                  ? "Guardando…"
                  : dirty
                    ? "Cambios sin guardar"
                    : `Versión guardada: ${record.version}`}
              </span>
              <button
                className="d-primary"
                disabled={
                  !dirty ||
                  saving ||
                  proposalBusy ||
                  !!remote ||
                  identityBlocked ||
                  reauth
                }
                onClick={() => persist("DRAFT")}
              >
                Guardar borrador
              </button>
              <button
                disabled={
                  !dirty ||
                  saving ||
                  proposalBusy ||
                  !!remote ||
                  identityBlocked ||
                  reauth
                }
                onClick={() => persist(status)}
              >
                Guardar estado editorial
              </button>
            </div>
          </>
        )}
        <div className="i-disabled-actions">
          {["Generar con IA", "Aprobar cambios", "Preparar por canal"].map(
            (label) => (
              <button key={label} disabled>
                {label}
              </button>
            ),
          )}
        </div>
        <button disabled={saving} onClick={onClose}>
          Volver a la tabla
        </button>
      </div>
    </>
  );
}
