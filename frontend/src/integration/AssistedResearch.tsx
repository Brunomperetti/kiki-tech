import { useEffect, useRef, useState } from "react";
import { captureDate } from "./catalog-adapter";
import {
  changeResearch,
  loadResearch,
  type Dossier,
  type AssistedCandidate,
} from "./research-adapter";

const labels: Record<string, string> = {
  ean: "EAN",
  brand: "Marca",
  manufacturer: "Fabricante",
  name: "Nombre",
  presentation: "Presentación",
  net_weight: "Contenido neto",
  is_combo: "Tipo de venta",
};
const show = (v: string | boolean | null, k: string) =>
  v === null
    ? "No disponible"
    : k === "is_combo"
      ? v
        ? "Pack"
        : "Unidad"
      : String(v);
export function AssistedResearch({
  id,
  csrf,
  data,
  workspaceVersion,
  autoStart,
  onStarted,
  busy,
  onBusy,
  onResult,
  onError,
}: {
  id: string;
  csrf: string;
  data: Dossier;
  workspaceVersion: number;
  autoStart: number;
  onStarted: () => void;
  busy: boolean;
  onBusy: (v: boolean) => void;
  onResult: (v: Dossier, message: string) => void;
  onError: (v: string) => void;
}) {
  const [notes, setNotes] = useState<Record<string, string>>({});
  const consumed = useRef(false);
  const run = data.assisted;
  async function action(path: string, body: unknown, message: string) {
    onBusy(true);
    onError("");
    try {
      onResult(await changeResearch(id, path, body, csrf), message);
    } catch (err) {
      onError((err as Error).message);
      try {
        onResult(
          await loadResearch(id),
          "La decisión local se conserva; no se reintentó automáticamente.",
        );
      } catch {
        /* keep original error */
      }
    } finally {
      onBusy(false);
    }
  }
  async function start() {
    await action(
      `/api/test-discovery/${id}/start`,
      {
        expected_version: data.version,
        expected_workspace_version: workspaceVersion,
      },
      "Investigación simulada registrada. Ninguna fuente ni dato se aprobó automáticamente.",
    );
  }
  useEffect(() => {
    if (autoStart > 0 && !consumed.current) {
      consumed.current = true;
      onStarted();
      void start();
    }
  }, [autoStart]);
  async function decide(c: AssistedCandidate, decision: string) {
    if (!run) return;
    await action(
      `/api/test-discovery/${id}/candidates/${c.id}/decision`,
      {
        expected_version: data.version,
        run_id: run.run_id,
        expected_candidate_version: c.version,
        decision,
        reason: notes[c.id] || "",
      },
      decision === "SELECTED"
        ? "Fuente seleccionada para revisión. Su procedencia sigue sin comprobarse."
        : "Fuente rechazada con motivo e historial.",
    );
  }
  async function acquire(c: AssistedCandidate) {
    if (
      !run ||
      !window.confirm(
        "¿Incorporar el documento de esta fuente SIMULADA para revisar? No visita Internet, no comprueba su procedencia y no modifica la ficha comercial.",
      )
    )
      return;
    await action(
      `/api/test-discovery/${id}/candidates/${c.id}/acquire`,
      {
        expected_version: data.version,
        run_id: run.run_id,
        expected_candidate_version: c.version,
      },
      "Documento simulado incorporado mediante el lector existente. Revisá procedencia e identidad, extraé los hechos y aprobá cada dato por separado.",
    );
  }
  return (
    <section
      className="a-research"
      aria-label="Investigación asistida de fabricantes"
    >
      <h3>Investigar producto</h3>
      <div className="r-notice">
        <strong>Demostración con fuentes simuladas · Sin Internet</strong>
        <p>
          Busca candidatos usando la información disponible de esta variante.
          Una coincidencia de EAN no verifica el producto ni la fuente. No se
          fusionan variantes.
        </p>
      </div>
      <button className="d-primary" disabled={busy} onClick={start}>
        Iniciar investigación simulada
      </button>
      {run && (
        <>
          <p>
            Ecomm ID {id} · Investigación {run.run_id} ·{" "}
            {captureDate(run.created_at)} · {run.actor}
          </p>
          {!run.current && (
            <p className="r-error" role="note">
              {run.stale_reason ||
                "Investigación desactualizada. Iniciá otra antes de incorporar fuentes."}
            </p>
          )}
          <details className="r-document">
            <summary>Datos utilizados y campos no disponibles</summary>
            {Object.entries(labels).map(([k, label]) => (
              <p key={k}>
                <strong>
                  {label}: {show(run.query_context.query[k], k)}
                </strong>
                <br />
                {run.query_context.provenance[k] || "No disponible"}
              </p>
            ))}
            <p>
              SKU no se utiliza como identidad ni para fusionar resultados. Los
              datos ausentes no se completan con valores de los fixtures.
            </p>
          </details>
          <p>
            {run.candidates.length} fuentes candidatas. Orden: sitio del
            fabricante, ficha técnica, etiqueta, catálogo y documento comercial.
            Las otras fuentes sólo son pistas.
          </p>
          {!run.candidates.length && (
            <p>
              No se localizaron candidatos en el catálogo sintético. No se
              recurrió a Internet.
            </p>
          )}
          <div className="a-candidates">
            {run.candidates.map((c) => (
              <article
                className="r-document a-candidate"
                data-source-id={c.source_id}
                data-candidate-id={c.id}
                key={c.id}
              >
                <h4>{c.title}</h4>
                <span className="r-state">Fuente SIMULADA</span>
                <p>
                  {c.declared_official
                    ? "Oficial declarada · Procedencia sin comprobar"
                    : "Pista pública · No clasificada como oficial"}
                </p>
                <p>{c.url}</p>
                <p>
                  {c.identity_state === "MISMATCH"
                    ? "Discrepancias detectadas: requiere revisión; la coincidencia de EAN no las resuelve."
                    : c.identity_state === "INCOMPLETE"
                      ? "Contraste incompleto: faltan referencias verificables."
                      : "Sin discrepancias detectadas en las referencias disponibles; falta verificación humana."}
                </p>
                <details>
                  <summary>Contrastar identidad y presentación</summary>
                  {Object.entries(c.comparisons).map(([k, v]) => (
                    <p key={k}>
                      <strong>
                        {labels[k]}:{" "}
                        {
                          {
                            MATCH: "Coincide como referencia",
                            MISMATCH: "Discrepancia",
                            UNKNOWN: "Sin información suficiente",
                          }[v.status]
                        }
                      </strong>
                      <br />
                      Variante: {show(v.expected, k)} · Candidato:{" "}
                      {show(v.found, k)}
                    </p>
                  ))}
                </details>
                <p>
                  Decisión:{" "}
                  {{
                    PENDING: "Sin decidir",
                    SELECTED: "Seleccionada para revisión",
                    REJECTED: "Rechazada",
                    TRANSFERRED: "Documento incorporado, no aprobado",
                  }[c.decision] || c.decision}{" "}
                  · Versión {c.version}
                </p>
                <label>
                  Motivo de selección o rechazo
                  <textarea
                    aria-label={`Motivo de fuente ${c.id}`}
                    value={notes[c.id] || ""}
                    maxLength={600}
                    onChange={(e) =>
                      setNotes({ ...notes, [c.id]: e.target.value })
                    }
                  />
                </label>
                <div className="r-actions">
                  <button
                    disabled={
                      busy ||
                      !run.current ||
                      !!c.document_id ||
                      (notes[c.id]?.trim().length || 0) < 10
                    }
                    onClick={() => decide(c, "SELECTED")}
                  >
                    Seleccionar para revisión
                  </button>
                  <button
                    disabled={
                      busy ||
                      !run.current ||
                      !!c.document_id ||
                      (notes[c.id]?.trim().length || 0) < 10
                    }
                    onClick={() => decide(c, "REJECTED")}
                  >
                    Rechazar fuente
                  </button>
                  <button
                    className="d-primary"
                    disabled={
                      busy ||
                      !run.current ||
                      !!c.document_id ||
                      c.decision !== "SELECTED"
                    }
                    onClick={() => acquire(c)}
                  >
                    Incorporar documento simulado
                  </button>
                </div>
                {c.document_id && (
                  <p>
                    Documento asociado: {c.document_id}. Se conserva con los
                    demás documentos de este mismo expediente.
                  </p>
                )}
                <details>
                  <summary>
                    Decisiones anteriores de la fuente ({c.history.length})
                  </summary>
                  {c.history.map((h, i) => (
                    <p key={i}>
                      v{h.version} · {h.decision} · {h.actor} ·{" "}
                      {captureDate(h.at)} · {h.reason}
                    </p>
                  ))}
                </details>
              </article>
            ))}
          </div>
          <details className="r-document">
            <summary>Control técnico de la búsqueda simulada</summary>
            <pre>{JSON.stringify(run.search_trace, null, 2)}</pre>
            <p>
              No hay transporte HTTP real ni resolución DNS real habilitados.
            </p>
          </details>
        </>
      )}
    </section>
  );
}
