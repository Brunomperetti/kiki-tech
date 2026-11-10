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
import { isAuxiliaryPilot, isHileret } from "./hileret-pilot";

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
            vigente de prueba. Ninguno se aplica automáticamente a la ficha.
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
        <p>{error || "Consultando evidencia de prueba…"}</p>
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
}: {
  id: string;
  csrf: string;
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
  const [busy, setBusy] = useState(false);
  const [revision, reload] = useState(0);
  const rootRef = useRef<HTMLElement>(null);
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
          if (isAuxiliaryPilot(id))
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
  async function mutate(path: string, body: unknown) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setData(await changeResearch(id, path, body, csrf));
      setMessage(
        "Evidencia guardada en PostgreSQL de pruebas. La ficha comercial no se modificó.",
      );
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
    } finally {
      setBusy(false);
    }
  }
  async function review(fact: ResearchFact, decision: string) {
    if (
      !data ||
      !window.confirm(
        `¿${decision === "APPROVED" ? "Aprobar" : decision === "REVOKED" ? "Revocar" : "Rechazar"} este hecho? La decisión se registra sólo en la investigación de prueba.`,
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
      aria-label="Investigación documental de prueba"
    >
      <h3>Documentos y evidencias</h3>
      <p className="r-notice">
        <strong>Entorno documental aislado.</strong> Fixtures sintéticos y
        archivos locales expresamente autorizados. Sin búsquedas externas,
        scraping ni IA. Extraer datos no los verifica ni cambia tu ficha
        comercial.
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
          ) : (
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
              {["name", "presentation", "ean", "brand", "manufacturer"].map(
                (key) => (
                  <div key={key}>
                    <dt>
                      {
                        {
                          name: "Nombre original",
                          presentation: "Presentación",
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
              onChange={(event) => select(event.target.value)}
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
