import { useEffect, useState } from "react";
import type { EcommApiProductEdit } from "../types/ecomm-app";
import { loadResearch, type Dossier } from "./research-adapter";

/** Only the real Natural Seed pilot. No product or channel writes. */
export const naturalSeedPilotId = "7518949";
const documentId = "local-e1f4fe6d772845abbec0be982b27ad1c";
const requiredFacts = ["product_name", "presentation", "characteristics"] as const;

export function Stage2PilotSummary({
  record,
  revision,
  onTab,
}: {
  record: EcommApiProductEdit;
  revision: number;
  onTab: (tab: string) => void;
}) {
  const [dossier, setDossier] = useState<Dossier>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setDossier(undefined);
    setError("");
    loadResearch(record.ecomm_id, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setDossier(response);
      })
      .catch((cause: Error) => {
        if (!controller.signal.aborted) setError(cause.message);
      });
    return () => controller.abort();
  }, [record.ecomm_id, revision, retry]);

  const document = dossier?.documents.find((item) => item.id === documentId);
  const reviewedOriginal =
    !!document &&
    document.body.synthetic === false &&
    document.body.source?.review_state === "REVIEWED" &&
    document.body.associated_ecomm_id === record.ecomm_id;
  const identityCurrent =
    reviewedOriginal && document?.identity_reconciliation?.current === true;

  const verifiedFacts = dossier?.facts.filter(
    (fact) =>
      fact.document_id === documentId &&
      fact.document_version === document?.version &&
      fact.verified === true &&
      fact.state === "APPROVED",
  ) ?? [];
  const supported = requiredFacts.filter((field) =>
    verifiedFacts.some((fact) => fact.field === field),
  );
  const media = record.fields.media ?? [];
  const mediaWithRights = media.filter((resource) =>
    dossier?.media_rights?.some(
      (permission) =>
        permission.kind === resource.kind &&
        permission.url === resource.url &&
        permission.source_url === resource.source_url &&
        permission.current === true,
    ),
  ).length;
  const allRights = media.length > 0 && mediaWithRights === media.length;
  const editorComplete = [
    "title", "short_title", "description", "short_description",
    "details", "presentation", "category", "subcategory",
    "seo_title", "seo_description", "seo_keywords",
  ].every((key) => Boolean(record.fields[key as keyof typeof record.fields]));
  const approvedPilot = reviewedOriginal && identityCurrent &&
    supported.length === requiredFacts.length;

  return (
    <section className="r-next-action" aria-label="Cierre de etapa 2 Natural Seed">
      <h3>Etapa 2 · piloto Natural Seed</h3>
      <p>
        Ecomm ID <strong>{record.ecomm_id}</strong> · SKU{" "}
        <strong>{record.source.sku}</strong> · Ficha{" "}
        <strong>{record.status === "DRAFT" ? "Borrador" :
          record.status === "READY_FOR_REVIEW" ? "En revisión" :
          record.status === "READY_FOR_CHANNELS" ? "Lista para canales (interna)" :
          "Sin iniciar"}</strong> · versión {record.version}
      </p>
      {error ? (
        <p role="alert">
          No se pudo comprobar la evidencia: {error}{" "}
          <button type="button" onClick={() => setRetry((value) => value + 1)}>
            Reintentar
          </button>
        </p>
      ) : !dossier ? (
        <p role="status">Verificando evidencias reales guardadas…</p>
      ) : (
        <>
          <ul>
            <li>
              {reviewedOriginal ? "Acreditado" : "Pendiente"} · Original del producto
              {document ? ` v${document.version}` : " no disponible"} y procedencia revisada
            </li>
            <li>
              {identityCurrent ? "Aprobada" : "Pendiente"} · Equivalencia de
              nombre y presentación con Ecomm-App (no certifica el EAN)
            </li>
            <li>
              {supported.length === requiredFacts.length ? "Verificados" : "Pendientes"} ·{" "}
              {supported.length} de {requiredFacts.length} hechos esenciales
              aprobados y vigentes
            </li>
            <li>
              {editorComplete ? "Campos presentes" : "Campos incompletos"} ·
              Títulos, descripciones, presentación, SEO y categorías en borrador;
              todavía requieren revisión comercial
            </li>
            <li>
              {record.fields.manufacturer?.trim() ? "Fabricante informado" : "Pendiente"} ·
              Fabricante acreditado independientemente de la marca comercial
            </li>
            <li>
              {allRights ? "Permisos acreditados" : "Permisos pendientes"} ·{" "}
              {mediaWithRights} de {media.length} recursos con autorización comercial vigente
            </li>
          </ul>
          <p>
            {approvedPilot
              ? "Identidad y hechos documentales confirmados. La aceptación de la etapa 2 por KIKI sigue pendiente."
              : "Hay evidencia o conciliaciones por revisar antes de aceptar el piloto."}{" "}
            El guard documental controla el pase a canales; este resumen no
            aprueba la ficha ni realiza publicaciones.
          </p>
          <div className="r-actions">
            <button type="button" onClick={() => onTab("Evidencias")}>
              Revisar evidencias
            </button>{" "}
            <button type="button" onClick={() => onTab("Historial")}>
              Ver historial guardado
            </button>
          </div>
        </>
      )}
    </section>
  );
}
