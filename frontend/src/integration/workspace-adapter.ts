import type {
  EcommApiProductEdit,
  EcommEditableFields,
  EcommEditStatus,
} from "../types/ecomm-app";
import { CatalogError, request, type Variant } from "./catalog-adapter";

export const textFields = [
  "brand",
  "manufacturer",
  "title",
  "short_title",
  "short_description",
  "description",
  "details",
  "presentation",
  "category",
  "subcategory",
  "seo_title",
  "seo_description",
  "seo_keywords",
  "proposed_gtin",
  "note",
] as const;
export const fieldKeys = [
  ...textFields,
  "attributes",
  "media",
  "sources",
] as const;
export const stateLabels: Record<string, string> = {
  NOT_STARTED: "Sin editar",
  DRAFT: "Borrador",
  READY_FOR_REVIEW: "Lista para revisión",
  READY_FOR_CHANNELS: "Lista para canales (interno)",
};
export const workspacePath = (id: string) =>
  `/api/ecomm-app/workspace/${encodeURIComponent(id)}`;
export const cloneFields = (fields: EcommEditableFields): EcommEditableFields =>
  structuredClone(fields);

function adapt(value: unknown, id: string): EcommApiProductEdit {
  const data = value as EcommApiProductEdit;
  const fields = data?.fields;
  if (
    !data ||
    data.ecomm_id !== id ||
    data.source?.ecomm_id !== id ||
    typeof data.source.sku !== "string" ||
    typeof data.source_sku_changed !== "boolean" ||
    data.saved_in !== "KIKI_POSTGRESQL_INTERNAL_ONLY" ||
    data.external_writes_enabled !== false ||
    typeof data.available !== "boolean" ||
    !Number.isSafeInteger(data.version) ||
    data.version < 0 ||
    !(data.status in stateLabels) ||
    !fields ||
    Object.keys(fields).sort().join() !== [...fieldKeys].sort().join() ||
    textFields.some((key) => typeof fields[key] !== "string") ||
    !Array.isArray(fields.attributes) ||
    fields.attributes.some(
      (x) => !x || typeof x.name !== "string" || typeof x.value !== "string",
    ) ||
    !Array.isArray(fields.media) ||
    fields.media.some(
      (x) =>
        !x ||
        !["IMAGE", "VIDEO"].includes(x.kind) ||
        [x.url, x.alt, x.source_url].some((v) => typeof v !== "string"),
    ) ||
    !Array.isArray(fields.sources) ||
    fields.sources.some(
      (x) =>
        !x ||
        !["FABRICANTE", "ETIQUETA", "DISTRIBUIDOR", "OTRO"].includes(x.kind) ||
        typeof x.verified !== "boolean" ||
        [x.name, x.url, x.note].some((v) => typeof v !== "string"),
    ) ||
    !data.readiness ||
    typeof data.readiness.ready !== "boolean" ||
    !Array.isArray(data.readiness.missing) ||
    !Array.isArray(data.history) ||
    data.history.some(
      (x) =>
        !x ||
        !Number.isSafeInteger(x.version) ||
        typeof x.at !== "string" ||
        !x.changes ||
        x.external_writes !== false,
    )
  ) {
    throw new CatalogError(
      0,
      "La ficha recibida no coincide con el contrato completo. No se omitió ni reemplazó ningún campo.",
    );
  }
  return data;
}
export async function getWorkspace(id: string, signal?: AbortSignal) {
  return adapt(await (await request(workspacePath(id), { signal })).json(), id);
}
export async function saveWorkspace(
  id: string,
  fields: EcommEditableFields,
  status: EcommEditStatus,
  version: number,
  csrf: string,
) {
  return adapt(
    await (
      await request(workspacePath(id), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ expected_version: version, status, fields }),
      })
    ).json(),
    id,
  );
}
export function sameIdentity(
  a: EcommApiProductEdit["source"],
  b: EcommApiProductEdit["source"],
) {
  return (
    a.ecomm_id === b.ecomm_id &&
    a.sku === b.sku &&
    a.variant_description === b.variant_description &&
    a.is_combo === b.is_combo &&
    a.gtin === b.gtin &&
    a.product_name === b.product_name
  );
}
export function compatibleWithRow(
  record: EcommApiProductEdit,
  variant: Variant,
) {
  return (
    !record.source_sku_changed &&
    record.ecomm_id === variant.id &&
    record.source.sku === variant.sku &&
    record.source.variant_description === variant.presentation &&
    record.source.product_name === variant.name &&
    record.source.gtin === variant.gtin &&
    record.source.is_combo === variant.isCombo
  );
}
