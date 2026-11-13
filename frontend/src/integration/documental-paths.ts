import { isAuxiliaryPilot } from "./hileret-pilot";
import { validVariantId } from "./catalog-adapter";
export function documentalPath(
  id: string,
  kind: "evidence" | "proposals" | "documents",
) {
  if (!validVariantId(id))
    throw new Error("Ecomm ID inválido; no se consultó documentación.");
  if (isAuxiliaryPilot(id)) {
    const old = {
      evidence: "research",
      proposals: "proposals",
      documents: "documents",
    }[kind];
    return `/api/test-${old}/${id}`;
  }
  return `/api/ecomm-app/workspace/${id}/${kind}`;
}
