import type { Variant } from "./catalog-adapter";

// Presentation only: reuse existing flags/statuses, never approve or alter a record.
export function recommendedAction(product: Variant) {
  const has = (...flags: string[]) =>
    flags.some((f) => product.flags?.includes(f));
  if (product.identityBlockers?.length || has("identity"))
    return {
      label: "Revisar identidad",
      tab: "Evidencias",
      hint: "Compará la variante exacta antes de continuar.",
    };
  if (has("channel_conflicts"))
    return {
      label: "Revisar canales",
      tab: "Canales",
      hint: "Resolver diferencias sin cambiar publicaciones externas.",
    };
  if (has("evidence_revoked", "documents_changed", "review_due", "review_soon"))
    return {
      label: "Revisar evidencias",
      tab: "Evidencias",
      hint: "Comprobá fuentes y vigencia antes de usar la ficha.",
    };
  if (has("proposals_pending"))
    return {
      label: "Revisar propuesta IA",
      tab: "IA",
      hint: "Compará cada campo y su respaldo antes de guardar.",
    };
  if (product.editorialStatus === "READY_FOR_CHANNELS")
    return {
      label: "Verificar preparación",
      tab: "Canales",
      hint: "Ficha completa internamente; falta verificar cada canal.",
    };
  if (product.editorialStatus === "READY_FOR_REVIEW")
    return {
      label: "Revisar ficha",
      tab: "Ficha",
      hint: "Revisión editorial pendiente; no equivale a publicación.",
    };
  if (has("needs_research", "untouched"))
    return {
      label: "Investigar y completar con IA",
      tab: "IA",
      hint: "Revisá primero la disponibilidad y los hechos documentales.",
    };
  if (has("needs_completion", "commercial_incomplete"))
    return {
      label: "Completar ficha",
      tab: "Ficha",
      hint: "Revisá los faltantes del formulario existente.",
    };
  if (has("channel_candidates", "channel_stale"))
    return {
      label: "Revisar canales",
      tab: "Canales",
      hint: "Compará coincidencias y fechas; no prueban publicación actual.",
    };
  return { label: "Ver ficha", tab: "Ficha", hint: product.reason };
}
