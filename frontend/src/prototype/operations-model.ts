import { products, type Product } from "./data";
export type Editorial = {
  name: string;
  description: string;
  features: string;
  image: string;
  alt: string;
  seo: string;
  price: number;
  stock: number;
};
export type Version = {
  date: string;
  actor: string;
  action: string;
  reason: string;
  snapshot: Editorial;
};
export type Decision = {
  state: "Pendiente" | "Aceptada" | "Rechazada";
  reason: string;
};
export type Item = Product &
  Editorial & {
    family: string;
    conflict: boolean;
    decisions: Record<"ml" | "tn", Decision>;
    prepared: Record<"ml" | "tn", boolean>;
    history: Version[];
    ai: { text: string; state: "Pendiente" | "Aceptada" | "Descartada" } | null;
  };
export const now = () =>
  new Date().toLocaleString("es-AR", { timeZone: "America/Buenos_Aires" });
export function snapshot(p: Editorial): Editorial {
  const { name, description, features, image, alt, seo, price, stock } = p;
  return { name, description, features, image, alt, seo, price, stock };
}
export function createCatalog(): Item[] {
  return products.map((p) => {
    const editorial = {
      ...p,
      description: `${p.name}, una opción de ${p.brand} para el uso cotidiano. Texto de demostración.`,
      features: "Ingredientes, origen y alérgenos pendientes de verificación.",
      image: "Vista frontal de muestra",
      alt: `Vista de ${p.name}`,
      seo: p.name,
    };
    return {
      ...editorial,
      family: p.id === "DEMO-1006" ? "FAM-1001" : `FAM-${p.id.slice(5)}`,
      conflict: p.status === "Conflicto",
      decisions: {
        ml: { state: "Pendiente", reason: "" },
        tn: { state: "Pendiente", reason: "" },
      },
      prepared: {
        ml: p.status === "Preparada",
        tn:
          p.status === "Preparada" &&
          !["DEMO-1005", "DEMO-1004"].includes(p.id),
      },
      ai: null,
      history: [
        {
          date: "09/11/2026, 12:00",
          actor: "Equipo demo",
          action: "Versión inicial sintética",
          reason: "Fixture local; no proviene de un servicio real.",
          snapshot: snapshot(editorial),
        },
      ],
    };
  });
}
export function change(
  p: Item,
  patch: Partial<Item>,
  action: string,
  reason = "Decisión de demostración",
): Item {
  const next = { ...p, ...patch };
  return {
    ...next,
    history: [
      ...p.history,
      {
        date: now(),
        actor: "Operador demo",
        action,
        reason,
        snapshot: snapshot(next),
      },
    ],
  };
}
export type WorkState = "attention" | "preparing" | "ready" | "published";
export const workLabels: Record<WorkState, string> = {
  attention: "Necesita atención",
  preparing: "En preparación",
  ready: "Listo para publicar",
  published: "Publicado",
};
export function confirmedPublications(p: Item, c: "ml" | "tn") {
  return p.evidence[c].freshness === "current"
    ? p.evidence[c].publications.filter(
        (link) => link.id.trim() && link.proof.trim() && link.capturedAt.trim(),
      )
    : [];
}
export function isConfirmed(p: Item, c: "ml" | "tn") {
  return confirmedPublications(p, c).length > 0;
}
export function isReady(p: Item, c: "ml" | "tn") {
  return (
    !isConfirmed(p, c) &&
    p.evidence[c].freshness === "current" &&
    p.status === "Preparada" &&
    p.prepared[c] &&
    requirements(p).length === 0 &&
    (c !== "tn" || !!p.seo.trim())
  );
}
export function channelState(p: Item, c: "ml" | "tn") {
  if (isConfirmed(p, c)) return "Publicado con evidencia";
  if (p.evidence[c].freshness === "stale") return "Información desactualizada";
  if (p.evidence[c].freshness === "unknown") return "Información desconocida";
  if (isReady(p, c)) return "Listo para publicar";
  if (p[c] === "SKU coincidente" && p.decisions[c].state === "Pendiente")
    return "Vinculación por revisar";
  return "Sin publicación confirmada";
}
export function channelDetail(p: Item, c: "ml" | "tn") {
  if (isConfirmed(p, c))
    return `${new Set(confirmedPublications(p, c).map((v) => v.id)).size} publicación(es) con evidencia de muestra vigente`;
  if (p.evidence[c].freshness !== "current")
    return "Revisar vigencia; no permite concluir si está publicado.";
  if (isReady(p, c))
    return "Preparación interna. Revisar vigencia antes de publicar.";
  return p.decisions[c].state === "Rechazada"
    ? "Candidato descartado; no prueba ausencia de publicación."
    : p.decisions[c].state === "Aceptada"
      ? "Vinculación revisada; publicación aún no confirmada."
      : p[c] === "SKU coincidente"
        ? "Comparar presentación e identidad; no confirma publicación."
        : "Falta evidencia; no significa que no esté publicado.";
}
export function channelMatches(p: Item, c: "ml" | "tn", filter: string) {
  return (
    !filter ||
    (filter === "confirmed"
      ? isConfirmed(p, c)
      : filter === "unconfirmed"
        ? !isConfirmed(p, c)
        : filter === "ready"
          ? isReady(p, c)
          : filter === "candidate"
            ? p[c] === "SKU coincidente" && p.decisions[c].state === "Pendiente"
            : filter === "stale"
              ? p.evidence[c].freshness === "stale"
              : filter === "unknown"
                ? p.evidence[c].freshness === "unknown"
                : false)
  );
}
export function coverage(rows: Item[], c: "ml" | "tn") {
  return {
    publications: new Set(
      rows.flatMap((p) => confirmedPublications(p, c).map((link) => link.id)),
    ).size,
    variants: new Set(rows.filter((p) => isConfirmed(p, c)).map((p) => p.id))
      .size,
    unconfirmed: new Set(
      rows.filter((p) => !isConfirmed(p, c)).map((p) => p.id),
    ).size,
    ready: new Set(rows.filter((p) => isReady(p, c)).map((p) => p.id)).size,
  };
}
export function inWorkState(p: Item, state: string) {
  const attention =
    p.conflict ||
    requirements(p).length > 0 ||
    (["ml", "tn"] as const).some((c) => p.evidence[c].freshness !== "current");
  if (state === "attention") return attention;
  if (state === "published")
    return isConfirmed(p, "ml") || isConfirmed(p, "tn");
  if (state === "ready")
    return (["ml", "tn"] as const).some(
      (c) => channelState(p, c) === "Listo para publicar",
    );
  if (state === "preparing")
    return (
      !attention &&
      (p.status !== "Preparada" ||
        (["ml", "tn"] as const).some(
          (c) =>
            !isConfirmed(p, c) && channelState(p, c) !== "Listo para publicar",
        ))
    );
  return true;
}
export function editorialState(p: Item) {
  return p.conflict
    ? "Revisión necesaria"
    : requirements(p).length
      ? "Datos incompletos"
      : p.status === "Preparada"
        ? "Ficha aprobada"
        : "Borrador";
}
export function nextAction(p: Item) {
  if (p.conflict) return "Resolver conflicto";
  if (
    (["ml", "tn"] as const).some((c) => p.evidence[c].freshness !== "current")
  )
    return "Revisar evidencia";
  if (requirements(p).length) return "Completar ficha";
  if (p.ai?.state === "Pendiente") return "Revisar IA";
  if (p.status !== "Preparada") return "Revisar ficha";
  if (
    (["ml", "tn"] as const).some(
      (c) => !isConfirmed(p, c) && channelState(p, c) !== "Listo para publicar",
    )
  )
    return "Preparar canal";
  if (inWorkState(p, "ready")) return "Verificar antes de publicar";
  return "Revisar publicaciones";
}
export function actionTab(p: Item) {
  const action = nextAction(p);
  return p.conflict || action === "Revisar evidencia"
    ? "Evidencias"
    : action === "Revisar IA"
      ? "IA"
      : ["Completar ficha", "Revisar ficha"].includes(action)
        ? "Ficha"
        : "Canales";
}
export function requirements(p: Item): string[] {
  return [
    ...(!p.name.trim() ? ["Nombre"] : []),
    ...(!p.description.trim() ? ["Descripción"] : []),
    ...(!p.image.trim() || !p.alt.trim() ? ["Imagen y texto alternativo"] : []),
    ...(p.price <= 0 ? ["Precio válido"] : []),
    ...(p.conflict ? ["Conflicto de identidad"] : []),
  ];
}
export const tools = [
  "Actualización de catálogo",
  "Familias SKU y duplicados",
  "Conciliación de canales",
  "Evidencias y conflictos",
  "Propuestas IA",
  "Preparación por lotes",
  "Trabajos y resultados",
  "Diagnóstico operativo",
] as const;
export type Tool = (typeof tools)[number];
export type Job = {
  id: string;
  tool: Tool;
  date: string;
  ids: string[];
  result: string;
};

export function candidateCount(p: Item) {
  return (["ml", "tn"] as const).filter(
    (c) => p[c] === "SKU coincidente" && p.decisions[c].state === "Pendiente",
  ).length;
}
