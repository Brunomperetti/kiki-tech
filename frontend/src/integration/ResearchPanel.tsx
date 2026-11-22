import { production, environmentText } from "./runtime";
import { useEffect, useRef, useState } from "react";
import { CatalogError, captureDate, request } from "./catalog-adapter";
import {
  changeResearch,
  evidenceLabels,
  loadResearch,
  researchPath,
  type Dossier,
  type ResearchFact,
} from "./research-adapter";
import "./research.css";
import { DocumentImport } from "./DocumentImport";
import { AssistedResearch } from "./AssistedResearch";
import { MamaPilotSummary } from "./MamaPilot";
import { mamaPilotId } from "./mama-pilot";
import { HileretPilotSummary } from "./HileretPilot";
import { isHileret } from "./hileret-pilot";

export function ResearchSummary({
  id,
  revision,
  onOpen,
}: {
  id: string;
  revision: number;
  onOpen: () => void;
}) {
  const [data, setData] = useState<Dossier>();
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setData(undefined);
    setError("");
    loadResearch(id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [id, revision]);
  return (
    <section className="r-summary" aria-label="Respaldo documental de la ficha">
      <h3>Respaldo documental</h3>
      {data ? (
        <>
          <p>
            {data.facts.filter((f) => f.verified).length} hechos con aprobación
            vigente{production ? "" : " de prueba"}. Ninguno se aplica
            automáticamente a la ficha.
          </p>
          <ul>
            {data.facts
              .filter((f) => f.verified)
              .map((f) => (
                <li key={f.id}>
                  {f.label}: {f.value} {f.unit || ""} · {f.document_id} v
                  {f.document_version}
                </li>
              ))}
          </ul>
          <p>
            {data.missing.length
              ? `Falta respaldo aprobado: ${data.missing.join(", ")}.`
              : "Todos los datos documentales del ejemplo tienen revisión vigente."}
          </p>
        </>
      ) : (
        <p>
          {error ||
            environmentText(
              "Consultando evidencia de prueba…",
              "Consultando evidencias…",
            )}
        </p>
      )}
      <button onClick={onOpen}>Investigar y revisar fuentes</button>
    </section>
  );
}

export function ResearchPanel({
  id,
  csrf,
  onBusy,
  workspaceVersion,
  autoStart,
  onStarted,
  media,
}: {
  id: string;
  csrf: string;
  media: Array<{ kind: "IMAGE" | "VIDEO"; url: string; source_url: string; alt: string }>;
  onBusy: (busy: boolean) => void;
  workspaceVersion: number;
  autoStart: number;
  onStarted: () => void;
}) {
  const [data, setData] = useState<Dossier>();
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selected, select] = useState("alm-tecnica");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [batchSelected, setBatchSelected] = useState<Record<string, boolean>>({});
  const [batchReason, setBatchReason] = useState("");
  const [identityReason, setIdentityReason] = useState("");
  const [mediaUrl, setMediaUrl] = useState("");
  const [mediaLocation, setMediaLocation] = useState("");
  const [mediaReason, setMediaReason] = useState("");
  const [licenceBasis, setLicenceBasis] = useState<"OWNER_AUTHORIZATION" | "DOCUMENTED_LICENSE">("OWNER_AUTHORIZATION");
  const [busy, setBusy] = useState(false);
  const [revision, reload] = useState(0);
  const rootRef = useRef<HTMLElement>(null);
  const identitySectionRef = useRef<HTMLElement>(null);
  const batchSectionRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (error) rootRef.current?.scrollIntoView({ block: "start" });
  }, [error]);
  useEffect(() => {
    onBusy(busy);
    return () => onBusy(false);
  }, [busy, onBusy]);
  useEffect(() => {
    const controller = new AbortController();
    loadResearch(id, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setData(value);
          if (!value.documents.some((doc) => doc.id === selected))
            select((current) =>
              value.documents.some((doc) => doc.id === current)
                ? current
                : value.documents[0]?.id || "",
            );
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [id, revision]);
  const document = data?.documents.find((d) => d.id === selected);
  // Trust the server-side decision bound to document version and API identity.
  // The UI must not infer a valid approval from partial metadata.
  const identityReviewCurrent = document?.identity_reconciliation?.current === true;
  const identityReady = !!document && document.body.source?.review_state === "REVIEWED"
    && (identityReviewCurrent || document.issues.length === 0);
  const pendingInDocument = data?.facts.filter((fact) =>
    fact.document_id === document?.id &&
    fact.document_version === document?.version &&
    fact.state === "PENDING"
  ) || [];
  const selectableFacts = pendingInDocument.filter((fact) => fact.blockers.length === 0);
  const selectedFacts = selectableFacts.filter((fact) => batchSelected[fact.id] === true);
  const selectedMedia = media.find((item) => item.url === mediaUrl) || media[0];
  const mediaGrantHistory = [...(data?.history || [])].reverse().find((event) => {
    if (event.action !== "MEDIA_RIGHTS_REVIEW" || !event.detail || !selectedMedia)
      return false;
    const detail = event.detail as Record<string, unknown>;
    return detail.media_url === selectedMedia.url && detail.kind === selectedMedia.kind;
  });
  async function mutate(path: string, body: unknown) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setData(await changeResearch(id, path, body, csrf));
      setMessage(
        environmentText(
          "Evidencia guardada en PostgreSQL de pruebas. La ficha comercial no se modificó.",
          "Evidencia guardada en KIKI PostgreSQL. La ficha comercial no se modificó.",
        ),
      );
      return true;
    } catch (err) {
      const failure = err as CatalogError;
      setError(failure.message);
      if (failure.status === 409) {
        try {
          setData(await loadResearch(id));
        } catch {
          /* Retain last inspected result, never fabricate new evidence. */
        }
      }
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function review(fact: ResearchFact, decision: string) {
    if (
      !data ||
      !window.confirm(
        `¿${decision === "APPROVED" ? "Aprobar" : decision === "REVOKED" ? "Revocar" : "Rechazar"} este hecho? ${production ? "La decisión se registra en la investigación de esta variante." : "La decisión se registra sólo en la investigación de prueba."}`,
      )
    )
      return;
    await mutate(`${researchPath(id)}/facts/${fact.id}/review`, {
      expected_version: data.version,
      expected_fact_version: fact.version,
      decision,
      reason: notes[fact.id]?.trim() || "",
    });
  }
  async function reviewSelectedFacts() {
    if (
      !production || !data || !document || !identityReady ||
      !selectedFacts.length || batchReason.trim().length < 20
    ) return;
    const selections = [...selectedFacts];
    if (!window.confirm(
      `¿Confirmás que contrastaste individualmente estos ${selections.length} hechos con los fragmentos del documento actual? No se certifica el EAN ni se publica nada.\n\n${selections.map((f) => `• ${f.label}: ${f.value}`).join("\n")}`,
    )) return;
    const ok = await mutate(`${researchPath(id)}/facts/review-batch`, {
      expected_version: data.version,
      document_id: document.id,
      document_version: document.version,
      confirm: true,
      facts: selections.map((fact) => ({
        fact_id: fact.id,
        expected_fact_version: fact.version,
        reason: `${batchReason.trim()} — ${fact.label}`,
      })),
    });
    if (ok) {
      setBatchSelected({});
      setBatchReason("");
    }
  }
  async function reviewIdentity(decision: "APPROVED" | "REVOKED") {
    if (!data || !document || !window.confirm(
      decision === "APPROVED"
        ? "¿Confirmás que revisaste el documento original y que corresponde a esta variante y presentación? No se certifica ningún GTIN ni se publica."
        : "¿Revocar la equivalencia de identidad? Los hechos afectados perderán su aprobación vigente.",
    )) return;
    await mutate(
      `/api/ecomm-app/workspace/${encodeURIComponent(id)}/documents/${encodeURIComponent(document.id)}/identity-review`,
      {
        expected_version: data.version,
        document_version: document.version,
        decision,
        reason: identityReason.trim(),
      },
    );
  }
  async function reviewMediaRights(decision: "APPROVED" | "REVOKED") {
    if (!data || !document || !selectedMedia || !window.confirm(
      decision === "APPROVED"
        ? "¿Revisaste el documento original y comprobaste el permiso explícito de uso comercial para esta URL exacta? Esto registra tu revisión, no publica ni verifica automáticamente la titularidad."
        : "¿Revocar esta autorización de uso? La ficha dejará de cumplir el control para canales.",
    )) return;
    const quote = document.body.sections[mediaLocation] || "";
    await mutate(
      `/api/ecomm-app/workspace/${encodeURIComponent(id)}/documents/${encodeURIComponent(document.id)}/media-rights`,
      {
        expected_version: data.version,
        document_version: document.version,
        media_kind: selectedMedia.kind,
        media_url: selectedMedia.url,
        source_url: selectedMedia.source_url,
        decision,
        licence_basis: licenceBasis,
        location: mediaLocation,
        quote,
        reason: mediaReason.trim(),
      },
    );
  }
  async function reviseDocument() {
    if (
      !document ||
      !window.confirm(
        "¿Simular la siguiente versión sintética? Se invalidarán las verificaciones vinculadas al documento anterior.",
      )
    )
      return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await request(`/api/test-research/documents/${document.id}/revision`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          expected_version: document.version,
          new_version: document.version + 1,
        }),
      });
      setData(await loadResearch(id));
      setMessage(
        "Documento sintético actualizado. Las evidencias anteriores requieren nueva extracción y revisión.",
      );
    } catch (err) {
      setError((err as Error).message);
      reload((v) => v + 1);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      ref={rootRef}
      className="r-research"
      aria-label={environmentText(
        "Investigación documental de prueba",
        "Investigación documental",
      )}
    >
      <h3>Documentos y evidencias</h3>
      <p className="r-notice">
        {environmentText(
          "Entorno documental aislado. Fixtures sintéticos y archivos locales expresamente autorizados. Sin búsquedas externas, scraping ni IA.",
          "Documentos asociados exclusivamente a esta variante. Incorporación y procesamiento local; búsqueda automática externa deshabilitada.",
        )}{" "}
        Extraer datos no los verifica ni cambia tu ficha comercial.
      </p>
      {error && (
        <p role="alert" className="r-error">
          {error} Tu motivo de revisión se conserva. Consultá los cambios antes
          de decidir de nuevo.
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {!data ? (
        <button disabled={busy} onClick={() => reload((v) => v + 1)}>
          Volver a consultar investigación
        </button>
      ) : (
        <>
          {id === mamaPilotId ? (
            <MamaPilotSummary revision={data.version} />
          ) : isHileret(id) ? (
            <HileretPilotSummary id={id} revision={data.version} />
          ) : !production &&
            data.documents.some((doc) => doc.body.synthetic) ? (
            <AssistedResearch
              id={id}
              csrf={csrf}
              data={data}
              workspaceVersion={workspaceVersion}
              autoStart={autoStart}
              onStarted={onStarted}
              busy={busy}
              onBusy={setBusy}
              onError={setError}
              onResult={(value, message) => {
                setData(value);
                setMessage(message);
                if (value.incorporated_document_id)
                  select(value.incorporated_document_id);
              }}
            />
          ) : (
            <p role="note">
              Investigación externa deshabilitada. Incorporá documentación local
              autorizada, revisá su procedencia y aprobá cada hecho. No se
              reutilizan documentos de otras variantes.
            </p>
          )}
          {production && document && (
            <section className="r-next-action" aria-label="Próximo paso de revisión">
              <strong>Próximo paso para esta variante</strong>
              {!identityReady ? (
                <>
                  <p>
                    Revisá primero si el nombre y la presentación del documento
                    corresponden a la variante Ecomm-App. KIKI no aprobará hechos
                    hasta registrar una equivalencia válida para esta versión.
                  </p>
                  <button type="button" onClick={() =>
                    identitySectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
                  }>
                    Ir a conciliar identidad
                  </button>
                </>
              ) : pendingInDocument.length > 0 ? (
                <>
                  <p>
                    Identidad revisada. Hay {pendingInDocument.length} hechos pendientes.
                    Seleccioná únicamente los que hayas cotejado con sus fragmentos.
                  </p>
                  <button type="button" onClick={() =>
                    batchSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
                  }>
                    Ir a revisión de hechos
                  </button>
                </>
              ) : (
                <p>
                  No hay hechos pendientes de este original. Revisá las demás
                  fuentes y los permisos multimedia antes de considerar canales.
                </p>
              )}
            </section>
          )}
          <DocumentImport
            id={id}
            csrf={csrf}
            data={data}
            document={document}
            busy={busy}
            onBusy={setBusy}
            onError={setError}
            onResult={(value, message) => {
              setData(value);
              setMessage(message);
              setError("");
              if (value.incorporated_document_id)
                select(value.incorporated_document_id);
            }}
          />
          <details className="r-reference">
            <summary>
              Identidad y referencias de contraste · Ecomm ID {id}
            </summary>
            <p>
              El Ecomm ID es la identidad canónica. SKU y EAN no vinculan ni
              fusionan variantes.
            </p>
            <dl>
              {["name", "presentation", "presentation_lookup_hint", "ean", "brand", "manufacturer"].map(
                (key) => (
                  <div key={key}>
                    <dt>
                      {
                        {
                          name: "Nombre original",
                          presentation: "Presentación original (sin normalizar)",
                          presentation_lookup_hint: "Medida candidata para investigar",
                          ean: "EAN de contraste",
                          brand: "Marca de contraste",
                          manufacturer: "Fabricante de contraste",
                        }[key]
                      }
                    </dt>
                    <dd>
                      {String(data.identity[key] || "Sin datos")}
                      <small>{data.identity.provenance[key]}</small>
                    </dd>
                  </div>
                ),
              )}
            </dl>
            <p>
              Las referencias de fixture o propuestas KIKI no equivalen a datos
              verificados del fabricante.
            </p>
          </details>
          <p>
            Versión de investigación: {data.version} · Sin respaldo aprobado:{" "}
            {data.missing.join(", ") || "Ninguno"}.
          </p>
          <label>
            Documento disponible
            <select
              aria-label="Documento disponible"
              value={selected}
              disabled={busy}
              onChange={(event) => {
                select(event.target.value);
                setBatchSelected({});
              }}
            >
              {data.documents.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.body.title} · v{doc.version}
                </option>
              ))}
            </select>
          </label>
          {document && (
            <div className="r-document" aria-label="Vista del documento">
              <h4>{document.body.title}</h4>
              <p>
                {document.body.kind} · Versión {document.version} ·{" "}
                {document.body.provenance}
              </p>
              {production && document.body.synthetic === false && (
                <section ref={identitySectionRef} aria-label="Conciliación de identidad del fabricante" className="r-document">
                  <h4>¿Es realmente el mismo producto?</h4>
                  <p>
                    Ecomm-App puede usar una descripción distinta de la del fabricante.
                    Compará el nombre, el tamaño y la etiqueta original antes de
                    registrar equivalencia. Esto no verifica EAN, ingredientes,
                    certificaciones ni permite publicar automáticamente.
                  </p>
                  <p>
                    <strong>Origen Ecomm:</strong> {String(data.identity.name || "Sin datos")}
                    {" · "}{String(data.identity.presentation || "Sin datos")}
                  </p>
                  <p>
                    <strong>Documento:</strong> {String(document.body.identity.name || "Sin datos")}
                    {" · "}{String(document.body.identity.presentation || "Sin datos")}
                  </p>
                  {identityReviewCurrent && (
                    <p role="status">Equivalencia revisada para esta versión del documento.
                      Los demás controles de evidencia siguen vigentes.</p>
                  )}
                  <label>
                    Motivo y comprobación de la identidad
                    <textarea
                      aria-label="Motivo de equivalencia del fabricante"
                      maxLength={600}
                      minLength={20}
                      value={identityReason}
                      onChange={(event) => setIdentityReason(event.target.value)}
                    />
                  </label>
                  <div className="r-actions">
                    {!identityReviewCurrent && (
                      <button type="button" disabled={
                        busy || identityReason.trim().length < 20
                        || document.body.parse_status !== "TEXT_EXTRACTED"
                        || document.body.source?.review_state !== "REVIEWED"
                      } onClick={() => void reviewIdentity("APPROVED")}>
                        Registrar equivalencia revisada
                      </button>
                    )}
                    {identityReviewCurrent && (
                      <button type="button" disabled={busy || identityReason.trim().length < 20}
                        onClick={() => void reviewIdentity("REVOKED")}>
                        Revocar equivalencia
                      </button>
                    )}
                  </div>
                  <small>Si hay EAN contradictorio, pack o atributos incompatibles, el servidor rechazará la conciliación.</small>
                </section>
              )}
              {production && document.body.synthetic === false && media.length > 0 && (
                <section className="r-document" aria-label="Autorizaciones para imágenes y videos">
                  <h4>Permisos de uso multimedia</h4>
                  <p>
                    La presencia de una foto o video en una web pública no concede
                    permiso de reutilización. Seleccioná el archivo comercial y
                    un documento original que autorice expresamente su uso.
                    Es obligatorio conservar el texto literal y justificar la
                    revisión; el permiso se registra para una sola URL y versión.
                  </p>
                  <label>
                    Recurso de esta ficha
                    <select aria-label="Imagen o video para revisar derechos"
                      value={selectedMedia?.url || ""}
                      disabled={busy}
                      onChange={(event) => setMediaUrl(event.target.value)}>
                      {media.map((item) => (
                        <option key={item.kind + item.url} value={item.url}>
                          {item.kind === "IMAGE" ? "Imagen" : "Video"} · {item.url}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Ubicación de la autorización en el documento seleccionado
                    <select aria-label="Fragmento original con permiso de uso"
                      value={mediaLocation} disabled={busy}
                      onChange={(event) => setMediaLocation(event.target.value)}>
                      <option value="">Elegí el fragmento que autoriza el uso</option>
                      {Object.entries(document.body.sections).map(([location, quote]) => (
                        <option key={location} value={location}>
                          {location} · {quote.slice(0, 85)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {mediaLocation && (
                    <blockquote>{document.body.sections[mediaLocation]}</blockquote>
                  )}
                  <label>
                    Base de autorización
                    <select aria-label="Base del permiso multimedia"
                      disabled={busy} value={licenceBasis}
                      onChange={(event) => setLicenceBasis(
                        event.target.value as "OWNER_AUTHORIZATION" | "DOCUMENTED_LICENSE"
                      )}>
                      <option value="OWNER_AUTHORIZATION">Autorización expresa del titular</option>
                      <option value="DOCUMENTED_LICENSE">Licencia documentada para uso comercial</option>
                    </select>
                  </label>
                  <label>
                    Motivo de revisión y alcance del permiso
                    <textarea aria-label="Justificación del permiso multimedia"
                      minLength={25} maxLength={600} value={mediaReason}
                      onChange={(event) => setMediaReason(event.target.value)}
                    />
                  </label>
                  {mediaGrantHistory && (
                    <p role="note">
                      Última decisión registrada para este recurso:{" "}
                      {String((mediaGrantHistory.detail as Record<string, unknown>).decision)}
                      . Puede perder vigencia si cambia el documento, el archivo
                      o la identidad. KIKI comprueba esa vigencia al preparar la ficha.
                    </p>
                  )}
                  <div className="r-actions">
                    <button type="button" disabled={
                      busy || !selectedMedia || !mediaLocation ||
                      mediaReason.trim().length < 25 ||
                      document.body.source?.review_state !== "REVIEWED"
                    } onClick={() => void reviewMediaRights("APPROVED")}>
                      Registrar permiso documentado
                    </button>
                    <button type="button" disabled={
                      busy || !selectedMedia || !mediaLocation ||
                      mediaReason.trim().length < 25 ||
                      !mediaGrantHistory ||
                      (mediaGrantHistory.detail as Record<string, unknown>).decision !== "APPROVED"
                    } onClick={() => void reviewMediaRights("REVOKED")}>
                      Revocar permiso
                    </button>
                  </div>
                </section>
              )}
              {document.issues.length > 0 && (
                <div role="note" className="r-error">
                  <strong>
                    Identidad incompatible: sólo revisión; no se puede aprobar
                    su información.
                  </strong>
                  <ul>
                    {document.issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
              <details>
                <summary>Ver documento y ubicaciones verificables</summary>
                {Object.entries(document.body.sections).map(
                  ([location, text]) => (
                    <div className="r-fragment" key={location}>
                      <code>{location}</code>
                      <blockquote>{text}</blockquote>
                    </div>
                  ),
                )}
                <small>Huella del documento: {document.hash}</small>
              </details>
              <div className="r-actions">
                <button
                  disabled={
                    busy ||
                    [
                      "NEEDS_OCR",
                      "REFERENCE_ONLY",
                      "INSUFFICIENT_DATA",
                    ].includes(document.body.parse_status || "")
                  }
                  onClick={() =>
                    mutate(`${researchPath(id)}/extract`, {
                      expected_version: data.version,
                      document_id: document.id,
                      document_version: document.version,
                    })
                  }
                >
                  Extraer hechos del documento
                </button>
                {document.versions.includes(document.version + 1) && (
                  <button disabled={busy} onClick={reviseDocument}>
                    Simular nueva versión del documento
                  </button>
                )}
              </div>
            </div>
          )}
          {production && document && (
            <section
              className="r-batch-review"
              ref={batchSectionRef}
              aria-label="Revisión rápida y verificable de hechos"
            >
              <h4>Revisión de hechos del documento vigente</h4>
              <p>
                Seleccioná cada hecho que verificaste contra la cita visible. Una
                confirmación registra todas las decisiones seleccionadas con
                control de versión. Ninguna casilla viene marcada de antemano.
              </p>
              {!identityReady && (
                <p className="r-error">
                  Primero registrá la equivalencia de identidad de este original.
                  Las aprobaciones permanecen bloqueadas hasta entonces.
                </p>
              )}
              {pendingInDocument.length === 0 ? (
                <p>No hay hechos pendientes de este documento.</p>
              ) : (
                <>
                  {pendingInDocument.map((fact) => (
                    <label className="r-batch-fact" key={fact.id}>
                      <input
                        type="checkbox"
                        checked={batchSelected[fact.id] === true && fact.blockers.length === 0}
                        disabled={busy || !identityReady || fact.blockers.length > 0}
                        onChange={(event) => setBatchSelected((previous) => ({
                          ...previous,
                          [fact.id]: event.target.checked,
                        }))}
                      />
                      <span>
                        <strong>{fact.label}: {fact.value} {fact.unit || ""}</strong>
                        <small>
                          Documento v{fact.document_version} · {fact.location}
                        </small>
                        <q>{fact.quote}</q>
                        {fact.blockers.length > 0 && (
                          <small>Bloqueado: {fact.blockers.join(" · ")}</small>
                        )}
                      </span>
                    </label>
                  ))}
                  <label>
                    Motivo de revisión de los hechos seleccionados
                    <textarea
                      aria-label="Motivo de la revisión conjunta de hechos"
                      value={batchReason}
                      minLength={20}
                      maxLength={450}
                      onChange={(event) => setBatchReason(event.target.value)}
                      placeholder="Contrasté individualmente los valores, presentaciones y fragmentos del documento original."
                    />
                  </label>
                  <div className="r-actions">
                    <button
                      type="button"
                      disabled={
                        busy || !identityReady || !selectedFacts.length ||
                        batchReason.trim().length < 20
                      }
                      onClick={() => void reviewSelectedFacts()}
                    >
                      Confirmar {selectedFacts.length} hechos revisados
                    </button>
                  </div>
                  <small>
                    Solo guarda evidencias internas. No acredita EAN, licencia
                    de imágenes, identidad de fabricante ni publicación.
                  </small>
                </>
              )}
            </section>
          )}
          <h4>Hechos registrados · Revisión individual</h4>
          {data.facts.length === 0 && (
            <p>
              No se extrajeron hechos. Ningún dato se completará por suposición.
            </p>
          )}
          {data.facts.map((fact) => (
            <article
              className="r-fact"
              key={fact.id}
              data-document={fact.document_id}
              data-field={fact.field}
              aria-label={`${fact.label} · ${fact.document_id}`}
            >
              <h4>
                {fact.label}: {fact.value || "Valor ausente"} {fact.unit || ""}
              </h4>
              <span className={`r-state r-${fact.state.toLowerCase()}`}>
                {evidenceLabels[fact.state]}
              </span>
              <p>
                Ecomm ID {fact.ecomm_id} · {fact.presentation} · Campo
                comercial: {fact.commercial_field} · Evidencia v{fact.version}
              </p>
              <p>
                {fact.document_id} v{fact.document_version} · {fact.provenance}
                <br />
                Consulta: {captureDate(fact.consulted_at)}
                <br />
                Ubicación: <code>{fact.location}</code>
              </p>
              <blockquote>{fact.quote}</blockquote>
              {fact.blockers.length > 0 && (
                <ul className="r-error" aria-label="Bloqueos de evidencia">
                  {fact.blockers.map((issue, index) => (
                    <li key={index}>{issue}</li>
                  ))}
                </ul>
              )}
              {fact.reviewer && (
                <p>
                  Revisión: {fact.reviewer} · {captureDate(fact.reviewed_at)}
                </p>
              )}
              <label>
                Motivo de la decisión
                <textarea
                  aria-label={`Motivo ${fact.id}`}
                  value={notes[fact.id] || ""}
                  minLength={10}
                  maxLength={600}
                  onChange={(event) =>
                    setNotes((previous) => ({
                      ...previous,
                      [fact.id]: event.target.value,
                    }))
                  }
                />
              </label>
              <div className="r-actions">
                <button
                  disabled={
                    busy ||
                    !!fact.blockers.length ||
                    (notes[fact.id]?.trim().length || 0) < 10
                  }
                  onClick={() => review(fact, "APPROVED")}
                >
                  Aprobar hecho
                </button>
                <button
                  disabled={busy || (notes[fact.id]?.trim().length || 0) < 10}
                  onClick={() => review(fact, "REJECTED")}
                >
                  Rechazar hecho
                </button>
                <button
                  disabled={
                    busy ||
                    !fact.verified ||
                    (notes[fact.id]?.trim().length || 0) < 10
                  }
                  onClick={() => review(fact, "REVOKED")}
                >
                  Revocar verificación
                </button>
              </div>
              <details>
                <summary>
                  Decisiones y versiones anteriores ({fact.history.length})
                </summary>
                {[...fact.history].reverse().map((event) => (
                  <div className="r-history" key={event.version}>
                    <strong>
                      v{event.version} · {event.action} · {event.actor}
                    </strong>
                    <p>
                      {captureDate(event.at)} · {event.reason}
                    </p>
                    <p>
                      Antes: {String(event.before.state || "Sin evidencia")} →
                      Después: {String(event.after.state)}
                    </p>
                    <p>
                      Valor anterior: {String(event.before.value ?? "Sin dato")}{" "}
                      · Valor posterior:{" "}
                      {String(event.after.value ?? "Sin dato")}
                    </p>
                    <details>
                      <summary>Respaldo registrado en esa versión</summary>
                      <p>
                        {String(event.after.document_id)} · v
                        {String(event.after.document_version)} ·{" "}
                        {String(event.after.location)}
                      </p>
                      <blockquote>
                        {String(event.after.quote ?? "Sin fragmento")}
                      </blockquote>
                      <small>
                        Huella documental: {String(event.after.document_hash)}
                      </small>
                    </details>
                  </div>
                ))}
              </details>
            </article>
          ))}
          <details>
            <summary>Historial de la investigación</summary>
            {[...data.history].reverse().map((event) => (
              <p key={event.version}>
                v{event.version} · {event.action} · {event.actor} ·{" "}
                {captureDate(event.at)}
              </p>
            ))}
          </details>
          <button disabled={busy} onClick={() => reload((v) => v + 1)}>
            Actualizar evidencias guardadas
          </button>
        </>
      )}
    </section>
  );
}
