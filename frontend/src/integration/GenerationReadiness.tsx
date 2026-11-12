import { proposalPath } from "./proposal-adapter";
import { useState } from "react";
import { request } from "./catalog-adapter";
import type { EcommAiLatest } from "../types/ecomm-app";
import { isAuxiliaryPilot } from "./hileret-pilot";
import { production, capabilities, canWrite } from "./runtime";

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
export function GenerationReadiness({
  id,
  expectedVersion,
  blocked = false,
}: {
  id: string;
  expectedVersion?: number;
  blocked?: boolean;
}) {
  const [context, setContext] = useState<Contract>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [legacy, setLegacy] = useState<EcommAiLatest>();
  async function generateExisting() {
    if (
      !production ||
      blocked ||
      expectedVersion === undefined ||
      !canWrite() ||
      !capabilities?.openai_generation ||
      !window.confirm(
        "¿Generar título y descripción con el servicio OpenAI original? Consume su cuota y presupuesto existentes; no investiga la web ni aprueba o guarda la ficha.",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const auth = await (await request("/api/auth/me")).json();
      const draft = await (
        await request(
          `/api/ecomm-app/workspace/ai/${encodeURIComponent(id)}/suggest`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": auth.csrf_token,
            },
            body: JSON.stringify({ expected_version: expectedVersion }),
          },
        )
      ).json();
      if (draft.ecomm_id !== id || draft.saved_to_product_fields !== false)
        throw new Error("Propuesta IA incompatible; no se aplicó contenido.");
      await loadExisting();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadExisting() {
    setBusy(true);
    setError("");
    try {
      const value = (await (
        await request(
          `/api/ecomm-app/workspace/ai/${encodeURIComponent(id)}/latest`,
        )
      ).json()) as EcommAiLatest;
      if (
        typeof value.enabled !== "boolean" ||
        typeof value.available !== "boolean" ||
        !Number.isInteger(value.remaining_today) ||
        value.remaining_today < 0 ||
        value.remaining_today > 10 ||
        (value.available && (!value.draft || value.draft.ecomm_id !== id))
      )
        throw new Error(
          "Respuesta OpenAI de otra identidad o contrato inválido.",
        );
      setLegacy(value);
    } catch (e) {
      setLegacy(undefined);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
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
      <summary>
        {production
          ? "Servicios IA existentes y límites"
          : "Preparación avanzada para IA real · Desactivada"}
      </summary>
      <p>
        {production
          ? "El contrato respaldado reúne hechos aprobados con citas y versiones. Su proveedor sigue desactivado (USD 0); el servicio OpenAI histórico de abajo conserva su presupuesto y cuota propios existentes."
          : "El contrato sólo reúne hechos aprobados vigentes con citas y versiones. La generación con OpenAI sigue desactivada; presupuesto autorizado: USD 0,00."}{" "}
        Consultarlo no genera ni guarda contenido.
      </p>
      <button
        disabled={busy || (production && !capabilities?.documents)}
        onClick={() => void load()}
      >
        Ver contrato de hechos aprobados
      </button>
      {!isAuxiliaryPilot(id) && (
        <>
          <p>
            Servicio OpenAI original: título y descripción con cuota diaria. Sus
            sugerencias históricas no equivalen a hechos documentales aprobados
            ni completan los 18 campos con citas.
          </p>
          <button disabled={busy} onClick={() => void loadExisting()}>
            Consultar servicio OpenAI existente (sin generar)
          </button>
          {production && (
            <>
              <p>
                OpenAI histórico:{" "}
                {capabilities?.openai_configured
                  ? "configurado"
                  : "no disponible"}
                . Generación para esta interfaz:{" "}
                {capabilities?.openai_generation && canWrite()
                  ? "habilitada con confirmación y cuota original"
                  : "bloqueada por configuración"}
                . No es investigación web ni una ficha de 18 campos respaldada
                por citas.
              </p>
              <button
                disabled={
                  busy ||
                  blocked ||
                  expectedVersion === undefined ||
                  !canWrite() ||
                  !capabilities?.openai_generation
                }
                onClick={() => void generateExisting()}
              >
                Generar título y descripción con OpenAI existente
              </button>
            </>
          )}
          {legacy && (
            <section aria-label="Servicio OpenAI existente">
              <p>
                {legacy.enabled
                  ? "Configurado en este backend"
                  : "Desactivado en este backend"}{" "}
                · Intentos disponibles hoy: {legacy.remaining_today} de 10.
              </p>
              <p>
                Consulta de sólo lectura. No se invocó OpenAI ni se reservó
                consumo.{" "}
                {production
                  ? "Generar requiere habilitación, cuota disponible y confirmación explícita."
                  : "La generación real sigue bloqueada en este entorno."}
              </p>
              {legacy.available && legacy.draft ? (
                <>
                  <p>
                    Sugerencia histórica sin aprobación documental · Modelo
                    registrado: {legacy.draft.model} ·{" "}
                    {legacy.draft.source_current
                      ? "Fuente vigente"
                      : "Fuente modificada; no utilizar"}
                  </p>
                  <p>Título: {legacy.draft.title}</p>
                  <p>Descripción: {legacy.draft.description}</p>
                  <p>
                    No se aplica ni se convierte automáticamente en una
                    propuesta respaldada.
                  </p>
                </>
              ) : (
                <p>No hay sugerencias históricas para esta variante.</p>
              )}
            </section>
          )}
        </>
      )}
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
