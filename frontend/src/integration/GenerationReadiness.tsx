import { proposalPath } from "./proposal-adapter";
import { useState } from "react";
import { request } from "./catalog-adapter";

type Contract = {
  schema_version: string;
  ecomm_id: string;
  context_hash: string;
  workspace_version: number;
  facts: {
    id: string;
    field: string;
    quote: string;
    location: string;
    document_id: string;
  }[];
  provider: { enabled: boolean; calls: number; model: string | null };
  controls: {
    max_cost_usd: string;
    max_calls_per_proposal: number;
    automatic_retries: number;
  };
};
export function GenerationReadiness({ id }: { id: string }) {
  const [context, setContext] = useState<Contract>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    setError("");
    try {
      const v = (await (
        await request(`${proposalPath(id)}/generation-context`)
      ).json()) as Contract;
      if (
        v.schema_version !== "kiki-evidence-generation-v1" ||
        v.ecomm_id !== id ||
        v.provider.enabled !== false ||
        v.provider.calls !== 0 ||
        v.controls.max_cost_usd !== "0.00" ||
        !Array.isArray(v.facts)
      )
        throw new Error(
          "Contrato de generación incompatible; no se invocó ningún proveedor.",
        );
      setContext(v);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="r-document">
      <summary>Preparación avanzada para IA real · Desactivada</summary>
      <p>
        El contrato sólo reúne hechos aprobados vigentes con citas y versiones.
        OpenAI no está conectado; presupuesto autorizado: USD 0,00. Consultarlo
        no genera ni guarda contenido.
      </p>
      <button disabled={busy} onClick={() => void load()}>
        Ver contrato de hechos aprobados
      </button>
      {error && <p role="alert">{error}</p>}
      {context && (
        <section aria-label="Contrato de generación respaldada">
          <p>
            {context.facts.length}{" "}
            {context.facts.length === 1 ? "hecho aprobado" : "hechos aprobados"}{" "}
            · Versión de ficha {context.workspace_version} · Llamadas externas:{" "}
            {context.provider.calls}
          </p>
          <p>
            Huella del contexto: <code>{context.context_hash}</code>
          </p>
          {context.facts.map((f) => (
            <p key={f.id}>
              <strong>{f.field}</strong> · Documento {f.document_id} ·{" "}
              <code>{f.location}</code>
              <br />«{f.quote}»
            </p>
          ))}
          <p>
            Antes de habilitar IA: modelo y precios aprobados, reserva de
            presupuesto, validación de afirmaciones y revisión humana. No hay
            reintentos automáticos.
          </p>
        </section>
      )}
    </details>
  );
}
