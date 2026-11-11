import { useEffect, useState } from "react";
import type { EcommApiProductEdit } from "../types/ecomm-app";
import { captureDate } from "./catalog-adapter";
import { cloneFields, saveWorkspace } from "./workspace-adapter";
import {
  loadProposal,
  mutateProposal,
  type Proposal,
  type ProposalField,
  type Decisions,
} from "./proposal-adapter";
import "./research.css";
import { GenerationReadiness } from "./GenerationReadiness";
import { isAuxiliaryPilot } from "./hileret-pilot";

const labels: Record<string, string> = {
  brand: "Marca",
  manufacturer: "Fabricante",
  title: "Título comercial",
  short_title: "Título corto",
  short_description: "Descripción corta",
  description: "Descripción larga",
  details: "Detalles y características",
  presentation: "Presentación",
  attributes: "Atributos",
  category: "Categoría",
  subcategory: "Subcategoría",
  seo_title: "Título SEO",
  seo_description: "Descripción SEO",
};
const show = (v: unknown) =>
  typeof v === "string" ? v : JSON.stringify(v, null, 2);
export function ProposalPanel({
  record,
  draftId,
  csrf,
  blocked,
  active,
  onBusy,
  onDirty,
  onSaved,
}: {
  record: EcommApiProductEdit;
  draftId?: number;
  csrf: string;
  blocked: boolean;
  active: boolean;
  onBusy: (v: boolean) => void;
  onDirty: (v: boolean) => void;
  onSaved: (v: EcommApiProductEdit) => void;
}) {
  const [data, setData] = useState<Proposal>();
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [changed, setChanged] = useState(false),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(""),
    [message, setMessage] = useState("");
  useEffect(() => {
    onBusy(busy);
    return () => onBusy(false);
  }, [busy, onBusy]);
  useEffect(() => {
    onDirty(changed);
    return () => onDirty(false);
  }, [changed, onDirty]);
  function adopt(value: Proposal) {
    setData(value);
    setChoices(
      Object.fromEntries(
        Object.entries(value.decisions || {}).map(([key, d]) => [
          key,
          d!.decision,
        ]),
      ),
    );
    setTexts(
      Object.fromEntries(
        Object.entries(value.fields || {}).map(([key, p]) => [
          key,
          show(value.decisions?.[key as ProposalField]?.value ?? p!.value),
        ]),
      ),
    );
    setChanged(false);
  }
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    loadProposal(record.ecomm_id, controller.signal, draftId)
      .then((value) => {
        if (!controller.signal.aborted) {
          if (changed) setData(value);
          else adopt(value);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, [record.ecomm_id, record.version, active, draftId]);
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
    } catch (err) {
      setError(
        (err as Error).message +
          " Tu selección local se conserva; no se reintentó el guardado.",
      );
      try {
        setData(await loadProposal(record.ecomm_id, undefined, draftId));
      } catch {
        /* keep original error */
      }
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    if (
      changed &&
      !window.confirm(
        "¿Descartar la revisión local y generar una propuesta nueva?",
      )
    )
      return;
    await act(async () => {
      adopt(
        await mutateProposal(
          record.ecomm_id,
          "/generate",
          { expected_version: record.version },
          csrf,
        ),
      );
      setMessage(
        "Propuesta de prueba generada. Ningún campo comercial fue modificado.",
      );
    });
  }
  async function review() {
    if (!data?.available) return;
    await act(async () => {
      const decisions: Decisions = {};
      for (const [name, choice] of Object.entries(choices)) {
        if (!choice) continue;
        const key = name as ProposalField,
          source = data.fields[key]!;
        const value =
          typeof source.value === "string"
            ? texts[key]
            : JSON.parse(texts[key]);
        decisions[key] = { decision: choice as "ACCEPTED" | "REJECTED", value };
      }
      if (!Object.keys(decisions).length)
        throw new Error("Aceptá o rechazá al menos un campo.");
      adopt(
        await mutateProposal(
          record.ecomm_id,
          `/${data.draft_id}/review`,
          {
            expected_revision: data.revision,
            decisions,
          },
          csrf,
        ),
      );
      setMessage(
        "Revisión registrada en PostgreSQL. La ficha todavía no fue modificada.",
      );
    });
  }
  async function apply() {
    if (
      !data ||
      !window.confirm(
        "¿Guardar únicamente los campos aceptados como borrador? Los campos seleccionados reemplazarán sus valores actuales, incluso si la ficha estaba aprobada. No publica productos.",
      )
    )
      return;
    await act(async () => {
      const fields = cloneFields(data.base_fields);
      for (const [key, decision] of Object.entries(data.decisions)) {
        if (decision?.decision === "ACCEPTED")
          Object.assign(fields, { [key]: decision.value });
      }
      const saved = await saveWorkspace(
        record.ecomm_id,
        fields,
        "DRAFT",
        data.workspace_version,
        csrf,
        { id: data.draft_id, revision: data.revision },
      );
      onSaved(saved);
      setChanged(false);
      setMessage(
        `Selección guardada en PostgreSQL de pruebas · Versión ${saved.version}.`,
      );
      adopt(await loadProposal(record.ecomm_id, undefined, draftId));
    });
  }
  const stale =
    !!data?.available &&
    (!data.source_current ||
      data.state === "STALE" ||
      data.state === "APPLIED");
  const accepted = Object.values(data?.decisions || {}).some(
    (d) => d?.decision === "ACCEPTED",
  );
  return (
    <section
      className="r-research p-panel"
      aria-label="Propuestas comerciales documentadas"
    >
      <h3>Propuesta comercial desde evidencias</h3>
      {draftId && (
        <p>
          Propuesta #{draftId} abierta desde el lote. Se revisa esta versión
          exacta.
        </p>
      )}
      <GenerationReadiness
        key={`${record.ecomm_id}:${record.version}:${active}`}
        id={record.ecomm_id}
      />
      <div className="r-notice">
        <strong>
          {isAuxiliaryPilot(record.ecomm_id)
            ? "Propuesta documental local · Sin IA real"
            : "Demostración determinista · Sin IA real"}
        </strong>
        <p>
          Usa sólo hechos aprobados de documentos{" "}
          {isAuxiliaryPilot(record.ecomm_id)
            ? "suministrados manualmente y revisados; las referencias informadas no bastan"
            : data?.synthetic_only === false
              ? "locales autorizados"
              : "sintéticos"}
          . No representa investigación oficial. No completa datos desconocidos.
        </p>
      </div>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {blocked && (
        <p role="alert">
          Guardá o descartá los cambios del editor antes de revisar propuestas.
          La identidad debe seguir siendo compatible.
        </p>
      )}
      <button
        className="d-primary"
        disabled={busy || blocked || !!draftId}
        onClick={generate}
      >
        Generar propuesta de prueba
      </button>
      <button
        disabled={busy}
        onClick={() => {
          if (
            !changed ||
            window.confirm(
              "¿Descartar la selección local y recuperar la revisión guardada?",
            )
          )
            void act(async () =>
              adopt(await loadProposal(record.ecomm_id, undefined, draftId)),
            );
        }}
      >
        Recuperar propuesta guardada
      </button>
      <details className="r-document">
        <summary>
          Hechos autorizados vigentes ({data?.authorized_facts.length || 0})
        </summary>
        {data?.authorized_facts.map((f) => (
          <p key={f.id}>
            {f.label || f.field}: {f.value} {f.unit} · Ecomm ID {f.ecomm_id} ·{" "}
            {f.presentation} · {f.document_id} v{f.document_version} · evidencia
            v{f.version} · {f.state}
            <br />«{f.quote}» · {f.location}
          </p>
        ))}
      </details>
      {!data?.available && (
        <p>No hay una propuesta generada para esta variante.</p>
      )}
      {data?.available && (
        <>
          <p>
            Propuesta {data.draft_id} · Ecomm ID {data.ecomm_id} · Base de ficha
            v{data.workspace_version} · Revisión {data.revision} ·{" "}
            {captureDate(data.created_at)}
          </p>
          {data.state === "APPLIED" && (
            <p className="r-notice">
              Selección ya guardada. Consultá la ficha y su historial.
            </p>
          )}
          {data.state !== "APPLIED" &&
            data.blockers.map((v, i) => (
              <p role="alert" key={i}>
                {v}
              </p>
            ))}
          <details className="r-document" open>
            <summary>
              Datos que no se generaron y afirmaciones bloqueadas
            </summary>
            <ul>
              {data.missing.map((v) => (
                <li key={v}>{v}</li>
              ))}
            </ul>
          </details>
          <p>
            Compará cada campo. Podés quitar o reordenar frases completas
            respaldadas; un hecho nuevo requiere nueva evidencia. Rechazados y
            campos sin decidir se conservan sin cambios.
          </p>
          {Object.entries(data.fields).map(([name, proposed]) => {
            const key = name as ProposalField;
            return (
              <article
                className="r-fact p-field"
                data-proposal-field={key}
                key={key}
              >
                <h4>{labels[key] || key}</h4>
                <details>
                  <summary>Valor actual al generar</summary>
                  <pre>{show(data.base_fields[key]) || "Sin valor"}</pre>
                </details>
                <label>
                  Texto propuesto · {labels[key] || key}
                  <textarea
                    aria-label={`Propuesta ${key}`}
                    value={texts[key] ?? show(proposed!.value)}
                    disabled={busy || blocked || stale}
                    rows={key === "description" || key === "attributes" ? 6 : 3}
                    onChange={(e) => {
                      setTexts({ ...texts, [key]: e.target.value });
                      setChanged(true);
                    }}
                  />
                </label>
                <details>
                  <summary>
                    Respaldo de este campo ({proposed!.evidence_ids.length})
                  </summary>
                  {proposed!.evidence_ids.map((id) => {
                    const f = data.evidence.find((f) => f.id === id);
                    return (
                      f && (
                        <div className="r-document" key={id}>
                          <strong>
                            {f.field}: {f.value} {f.unit}
                          </strong>
                          <p>
                            Ecomm ID {f.ecomm_id} · {f.presentation} · {f.state}{" "}
                            · evidencia v{f.version} · {f.document_id} v
                            {f.document_version}
                          </p>
                          <blockquote>{f.quote}</blockquote>
                          <p>
                            {f.location} · {f.provenance} ·{" "}
                            {captureDate(f.consulted_at)}
                          </p>
                        </div>
                      )
                    );
                  })}
                </details>
                <label>
                  Decisión · {labels[key] || key}
                  <select
                    aria-label={`Decisión ${key}`}
                    disabled={busy || blocked || stale}
                    value={choices[key] || ""}
                    onChange={(e) => {
                      setChoices({ ...choices, [key]: e.target.value });
                      setChanged(true);
                    }}
                  >
                    <option value="">Sin decidir · conservar ficha</option>
                    <option value="ACCEPTED">Aceptar este cambio</option>
                    <option value="REJECTED">Rechazar este cambio</option>
                  </select>
                </label>
              </article>
            );
          })}
          <div className="r-actions">
            <button
              disabled={busy || blocked || stale || !changed}
              onClick={review}
            >
              Registrar revisión individual
            </button>
            <button
              className="d-primary"
              disabled={
                busy ||
                blocked ||
                stale ||
                changed ||
                data.state !== "REVIEWED" ||
                !accepted
              }
              onClick={apply}
            >
              Guardar selección en ficha
            </button>
          </div>
          <details className="r-document">
            <summary>Historial de la propuesta</summary>
            {[...data.history].reverse().map((h, i) => (
              <div key={i}>
                <strong>{h.event}</strong>
                <p>
                  {captureDate(h.at)} · {h.actor}
                </p>
                {h.decisions && (
                  <pre>{JSON.stringify(h.decisions, null, 2)}</pre>
                )}
                {h.selected_fields && <p>{h.selected_fields.join(", ")}</p>}
                {h.reasons?.map((v) => (
                  <p key={v}>{v}</p>
                ))}
              </div>
            ))}
          </details>
        </>
      )}
    </section>
  );
}
