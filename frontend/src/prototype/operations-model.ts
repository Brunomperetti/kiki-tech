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
      features: "Material y medidas pendientes de verificación.",
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
      prepared: { ml: false, tn: false },
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
export function nextAction(p: Item) {
  return p.conflict
    ? "Resolver conflicto"
    : p.ai?.state === "Pendiente"
      ? "Revisar IA"
      : p.status === "Preparada"
        ? "Preparar canal"
        : "Completar ficha";
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
