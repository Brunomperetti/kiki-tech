import { useEffect, useRef, useState } from "react";
import type { KikiMedia } from "../types/ecomm-app";
import { captureDate, request } from "./catalog-adapter";
import { isAuxiliaryPilot } from "./hileret-pilot";

type PermissionState =
  | "NO_PERMISSION"
  | "APPROVED_CURRENT"
  | "REJECTED"
  | "REVOKED"
  | "STALE";
type Permission = {
  kind: "IMAGE" | "VIDEO";
  url: string;
  source_url: string;
  alt: string;
  state: PermissionState;
  current: boolean;
  ecomm_id: string;
  stage4_ready: boolean;
  metadata_complete: boolean;
  preview_allowed: boolean;
  document_id: string | null;
  document_version: number | null;
  document_hash: string | null;
  original_sha256: string | null;
  reviewed_at: string | null;
  valid_until: string | null;
  presentation: string | null;
  source_presentation: string | null;
  reviewer: string | null;
  location: string | null;
  quote: string | null;
  blockers: string[];
};
type PermissionDocument = {
  id: string;
  version: number;
  digest: string;
  sha256: string | null;
  title: string | null;
  source_url: string | null;
  review_state: string;
  source_reviewed_at: string | null;
  identity_compatible: boolean;
  sections: { location: string; text: string; truncated: boolean }[];
  sections_truncated: boolean;
};
type Registry = {
  mode: "MEDIA_REVIEW_REGISTRY";
  ecomm_id: string;
  dossier_version: number;
  workspace_version: number;
  presentation: string;
  entries: Permission[];
  documents: PermissionDocument[];
  external_writes_enabled: false;
  remote_resources_loaded: 0;
};

const labels: Record<PermissionState, string> = {
  NO_PERMISSION: "Pendiente de permiso comercial",
  APPROVED_CURRENT: "Permiso vigente",
  REJECTED: "Recurso rechazado",
  REVOKED: "Permiso revocado",
  STALE: "Permiso o identidad por revalidar",
};

function navigable(value: string) {
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      !url.username &&
      !url.password &&
      (!url.port || url.port === "443") &&
      url.hostname.includes(".") &&
      !url.hostname.includes(":") &&
      !/^[\d.]+$/.test(url.hostname) &&
      !url.hostname
        .split(".")
        .every((label) => /^(?:0x[0-9a-f]+|\d+)$/i.test(label)) &&
      !/(^|\.)(localhost|local|internal)$/i.test(url.hostname)
    );
  } catch {
    return false;
  }
}

export function MediaReview({
  id,
  media,
  presentation,
  csrf,
  disabled = false,
  revision,
  onBusy,
}: {
  id: string;
  media: KikiMedia[];
  presentation: string;
  csrf: string;
  disabled?: boolean;
  revision: number;
  onBusy?: (busy: boolean) => void;
}) {
  const [data, setData] = useState<Registry>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [index, setIndex] = useState("0");
  const [documentId, setDocumentId] = useState("");
  const [location, setLocation] = useState("");
  const [quote, setQuote] = useState("");
  const [reason, setReason] = useState("");
  const [expiry, setExpiry] = useState("");
  const [licence, setLicence] = useState<
    "OWNER_AUTHORIZATION" | "DOCUMENTED_LICENSE"
  >("OWNER_AUTHORIZATION");
  const [confirmed, setConfirmed] = useState(false);
  const generation = useRef(0);
  const auxiliary = isAuxiliaryPilot(id);
  const selected = media[Number(index)];
  const permission = data?.entries.find(
    (item) =>
      item.kind === selected?.kind &&
      item.url === selected?.url &&
      item.source_url === selected?.source_url,
  );
  const document = data?.documents.find((item) => item.id === documentId);

  async function load() {
    const current = ++generation.current;
    setBusy(true);
    onBusy?.(true);
    setError("");
    try {
      const response = await request(
        `/api/ecomm-app/workspace/${encodeURIComponent(id)}/media-review`,
      );
      const value = (await response.json()) as Registry & { detail?: string };
      if (!response.ok)
        throw new Error(
          value.detail || "No se pudo consultar el registro multimedia.",
        );
      if (
        value.mode !== "MEDIA_REVIEW_REGISTRY" ||
        value.ecomm_id !== id ||
        value.external_writes_enabled !== false ||
        value.remote_resources_loaded !== 0 ||
        !Number.isSafeInteger(value.dossier_version) ||
        value.dossier_version < 0 ||
        value.workspace_version !== revision ||
        value.presentation !== presentation ||
        !Array.isArray(value.entries) ||
        value.entries.length > 30 ||
        value.entries.length !== media.length ||
        value.entries.some(
          (entry) =>
            entry.ecomm_id !== id ||
            !Object.prototype.hasOwnProperty.call(labels, entry.state) ||
            [
              entry.current,
              entry.metadata_complete,
              entry.stage4_ready,
              entry.preview_allowed,
            ].some((flag) => typeof flag !== "boolean") ||
            entry.current !== (entry.state === "APPROVED_CURRENT") ||
            !Array.isArray(entry.blockers) ||
            entry.stage4_ready !== (entry.current && entry.metadata_complete),
        ) ||
        !Array.isArray(value.documents) ||
        value.documents.length > 10 ||
        value.documents.some(
          (doc) => !Array.isArray(doc.sections) || doc.sections.length > 100,
        )
      ) {
        throw new Error(
          "El registro no coincide con la ficha guardada; recargá antes de revisar permisos.",
        );
      }
      if (current === generation.current) setData(value);
    } catch (exc) {
      if (current === generation.current) {
        setData(undefined);
        setError((exc as Error).message);
      }
    } finally {
      if (current === generation.current) {
        setBusy(false);
        onBusy?.(false);
      }
    }
  }

  useEffect(() => {
    setData(undefined);
    setMessage("");
    setDocumentId("");
    setLocation("");
    setQuote("");
    setConfirmed(false);
    if (!disabled && !auxiliary) void load();
    return () => {
      generation.current++;
      onBusy?.(false);
    };
  }, [id, revision, disabled, auxiliary]);

  function resetSelection(value: string) {
    setIndex(value);
    setDocumentId("");
    setLocation("");
    setQuote("");
    setReason("");
    setExpiry("");
    setConfirmed(false);
    setMessage("");
  }

  async function review(decision: "APPROVED" | "REJECTED" | "REVOKED") {
    if (!data || !document || !selected || disabled || busy) return;
    setBusy(true);
    onBusy?.(true);
    setError("");
    setMessage("");
    try {
      const response = await request(
        `/api/ecomm-app/workspace/${encodeURIComponent(id)}/documents/${encodeURIComponent(document.id)}/media-rights`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({
            expected_version: data.dossier_version,
            expected_workspace_version: revision,
            document_version: document.version,
            media_kind: selected.kind,
            media_url: selected.url,
            source_url: selected.source_url,
            decision,
            licence_basis: licence,
            location,
            quote,
            reason: reason.trim(),
            alt_text: selected.alt,
            presentation,
            valid_until: expiry ? new Date(expiry).toISOString() : null,
          }),
        },
      );
      if (!response.ok) {
        const value = await response.json();
        throw new Error(
          typeof value.detail === "string"
            ? value.detail
            : "No se pudo registrar la decisión multimedia.",
        );
      }
      setMessage(
        decision === "APPROVED"
          ? "Permiso registrado para este recurso y variante; no se publica ni se descarga contenido externo."
          : decision === "REJECTED"
            ? "Rechazo guardado en el historial de esta variante."
            : "Revocación guardada; el recurso deja de estar autorizado.",
      );
      setConfirmed(false);
      setReason("");
      await load();
    } catch (exc) {
      setError((exc as Error).message);
      setData(undefined);
    } finally {
      setBusy(false);
      onBusy?.(false);
    }
  }

  const canDecide =
    !disabled &&
    !busy &&
    !!csrf &&
    !!data &&
    !!selected &&
    !!document &&
    !!location &&
    quote.length >= 30 &&
    quote.length <= 1500 &&
    reason.trim().length >= 25 &&
    selected.alt.trim().length >= 3 &&
    !!presentation;
  const canApprove =
    canDecide &&
    confirmed &&
    document?.review_state === "REVIEWED" &&
    document.identity_compatible &&
    quote.includes(selected?.url || "") &&
    document.source_url === selected?.source_url;

  if (auxiliary)
    return (
      <section aria-label="Revisión de imágenes y videos">
        <p>
          El permiso comercial requiere una variante auténtica de Ecomm-App.
          Este expediente auxiliar no transfiere autorizaciones a productos del
          catálogo.
        </p>
      </section>
    );

  return (
    <section aria-label="Revisión de imágenes y videos">
      <h4>Imágenes y videos de esta variante</h4>
      <p>
        La URL pública no acredita derechos de uso. El permiso corresponde a
        este Ecomm ID, presentación y recurso exactos; nunca se hereda a otra
        variante o pack.
      </p>
      {disabled && (
        <p role="status">
          Guardá o resolvé los cambios pendientes de la ficha antes de revisar
          multimedia.
        </p>
      )}
      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => void load()}
      >
        {busy ? "Revisando permisos…" : "Actualizar registro multimedia"}
      </button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {!media.length && (
        <p>
          No hay recursos guardados. Agregá la URL, fuente y texto alternativo
          desde la ficha; el permiso seguirá pendiente hasta revisarlo.
        </p>
      )}
      {!!media.length && (
        <>
          <label>
            Recurso multimedia a revisar{" "}
            <select
              value={index}
              disabled={disabled || busy}
              onChange={(event) => resetSelection(event.target.value)}
            >
              {media.map((item, i) => (
                <option key={`${i}-${item.url}`} value={String(i)}>
                  {item.kind === "IMAGE" ? "Imagen" : "Video"} ·{" "}
                  {item.alt || "Sin texto alternativo"}
                </option>
              ))}
            </select>
          </label>
          {selected && (
            <dl>
              <dt>Ecomm ID y presentación</dt>
              <dd>
                {id} · {presentation || "Pendiente"}
              </dd>
              <dt>URL del recurso</dt>
              <dd>{selected.url}</dd>
              <dt>Fuente declarada</dt>
              <dd>{selected.source_url || "Pendiente"}</dd>
              <dt>Texto alternativo guardado</dt>
              <dd>{selected.alt || "Pendiente"}</dd>
            </dl>
          )}
          {permission && (
            <div role="region" aria-label="Estado del recurso multimedia">
              <p role="status">
                <strong>{labels[permission.state]}</strong>
                {permission.current && !permission.metadata_complete
                  ? " · Permiso anterior con metadatos pendientes; no habilita la salida comercial completa."
                  : ""}
              </p>
              <ul>
                {permission.blockers.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
              <details>
                <summary>Procedencia y decisión del recurso</summary>
                <dl>
                  <dt>Original SHA-256</dt>
                  <dd>{permission.original_sha256 || "Pendiente"}</dd>
                  <dt>Documento y versión</dt>
                  <dd>
                    {permission.document_id || "Pendiente"} ·{" "}
                    {permission.document_version ?? "—"}
                  </dd>
                  <dt>Revisión</dt>
                  <dd>
                    {captureDate(permission.reviewed_at)} ·{" "}
                    {permission.reviewer || "Sin revisor"}
                  </dd>
                  <dt>Vencimiento declarado</dt>
                  <dd>
                    {permission.valid_until
                      ? captureDate(permission.valid_until)
                      : "Sin vencimiento declarado; conservar revisión periódica"}
                  </dd>
                  <dt>Cita</dt>
                  <dd>{permission.quote || "Sin permiso documentado"}</dd>
                </dl>
              </details>
              <p>
                Abrir un recurso hará una consulta externa desde tu navegador.
                KIKI no carga imágenes ni videos automáticamente ni actúa como
                proxy.
              </p>
              <button
                type="button"
                disabled={
                  !permission.preview_allowed ||
                  !navigable(permission.url) ||
                  disabled ||
                  busy
                }
                onClick={() => {
                  if (permission.preview_allowed && navigable(permission.url))
                    window.open(
                      permission.url,
                      "_blank",
                      "noopener,noreferrer",
                    );
                }}
              >
                Abrir recurso aprobado en otra pestaña
              </button>
            </div>
          )}
          {data && (
            <details>
              <summary>Revisar permiso de este recurso</summary>
              <label>
                Documento del permiso{" "}
                <select
                  value={documentId}
                  disabled={disabled || busy}
                  onChange={(event) => {
                    setDocumentId(event.target.value);
                    setLocation("");
                    setQuote("");
                    setConfirmed(false);
                  }}
                >
                  <option value="">Seleccioná el original</option>
                  {data.documents.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.title || doc.id} · v{doc.version} ·{" "}
                      {doc.review_state === "REVIEWED"
                        ? "Procedencia revisada"
                        : "Procedencia pendiente"}
                    </option>
                  ))}
                </select>
              </label>
              {document && (
                <>
                  <p>
                    SHA-256: {document.sha256 || "Pendiente"} · Fuente:{" "}
                    {document.source_url || "Pendiente"}.{" "}
                    {document.identity_compatible
                      ? "Identidad documental compatible."
                      : "La identidad o presentación necesita revisión."}
                  </p>
                  <label>
                    Ubicación de la cita del permiso{" "}
                    <select
                      value={location}
                      disabled={disabled || busy}
                      onChange={(event) => {
                        setLocation(event.target.value);
                        setQuote(
                          document.sections.find(
                            (section) =>
                              section.location === event.target.value,
                          )?.text || "",
                        );
                        setConfirmed(false);
                      }}
                    >
                      <option value="">Seleccioná una ubicación</option>
                      {document.sections.map((section) => (
                        <option key={section.location} value={section.location}>
                          {section.location}
                          {section.truncated ? " · fragmento acotado" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  {document.sections_truncated && (
                    <p>
                      La vista de citas está acotada; revisá el original
                      completo desde Evidencias antes de decidir.
                    </p>
                  )}
                </>
              )}
              <label>
                Fragmento del permiso{" "}
                <textarea
                  value={quote}
                  maxLength={1500}
                  disabled={disabled || busy}
                  onChange={(event) => {
                    setQuote(event.target.value);
                    setConfirmed(false);
                  }}
                />
              </label>
              <label>
                Base del derecho de uso{" "}
                <select
                  value={licence}
                  disabled={disabled || busy}
                  onChange={(event) =>
                    setLicence(event.target.value as typeof licence)
                  }
                >
                  <option value="OWNER_AUTHORIZATION">
                    Autorización del titular
                  </option>
                  <option value="DOCUMENTED_LICENSE">
                    Licencia documentada
                  </option>
                </select>
              </label>
              <label>
                Vencimiento del permiso (opcional){" "}
                <input
                  type="datetime-local"
                  value={expiry}
                  disabled={disabled || busy}
                  onChange={(event) => setExpiry(event.target.value)}
                />
              </label>
              <label>
                Justificación de la decisión multimedia{" "}
                <textarea
                  value={reason}
                  minLength={25}
                  maxLength={600}
                  disabled={disabled || busy}
                  onChange={(event) => setReason(event.target.value)}
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={disabled || busy}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />{" "}
                Revisé la identidad y el permiso citado para este recurso
              </label>
              <div className="b-actions">
                <button
                  type="button"
                  disabled={!canApprove}
                  onClick={() => void review("APPROVED")}
                >
                  Aprobar permiso de este recurso
                </button>
                <button
                  type="button"
                  disabled={!canDecide}
                  onClick={() => void review("REJECTED")}
                >
                  Rechazar este recurso
                </button>
                <button
                  type="button"
                  disabled={!canDecide || !permission?.current}
                  onClick={() => void review("REVOKED")}
                >
                  Revocar permiso de este recurso
                </button>
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}
