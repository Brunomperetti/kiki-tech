import { CatalogError, request, validVariantId } from "./catalog-adapter";
import { channelLabels } from "./channel-labels";
export { channelLabels } from "./channel-labels";
export type ChannelCandidate = {
  id: string;
  slug?: string | null;
  token: string;
  match_reasons?: string[];
  discrepancies?: string[];
  comparison?: Record<string, string | number | null>;
  title: string | null;
  sku: string | null;
  barcode: string | null;
  gtin: string | null;
  brand: string | null;
  listing_status: string | null;
  quantity_in_title: number | null;
  identity_verified: boolean;
  review_state: string | null;
  review_current: boolean;
  revision: number;
  blockers: string[];
  can_review: boolean;
  history: {
    at: string;
    actor: string;
    decision: string;
    ecomm_id: string;
    quantity_commercial: number;
    reason: string;
  }[];
};
export type ChannelEvidence = {
  source: string;
  snapshot_available: boolean;
  snapshot_at: string | null;
  status: string;
  comparison_state?: string;
  evidence_state: string;
  note: string;
  confirmed_listing: boolean;
  identity_verified: boolean;
  candidates: ChannelCandidate[];
  candidates_total: number;
  no_candidates_reason?: string | null;
  candidates_truncated?: boolean;
  freshness: {
    fresh: boolean;
    age_hours: number | null;
    review_after_hours: number;
  };
  legacy_decisions_ignored: number;
};
export type ChannelReport = {
  identity: {
    ecomm_id: string;
    sku: string | null;
    barcode: string | null;
    gtin_raw: string | null;
    brand: string | null;
    brand_origin: string;
    variant_description: string | null;
    is_combo: boolean | null;
    parent_is_combo: boolean | null;
    captured_at: string | null;
  };
  ecomm_id: string;
  ml: ChannelEvidence;
  tn: ChannelEvidence;
  external_writes_enabled: false;
  scope: string;
};
export const channelPath = (id: string) =>
  `/api/ecomm-app/workspace/${id}/channels`;
export async function loadChannels(
  id: string,
  signal?: AbortSignal,
  init?: RequestInit,
): Promise<ChannelReport> {
  if (!validVariantId(id)) throw new Error("Ecomm ID inválido.");
  const data = (await (
    await request(channelPath(id) + (init ? "/review" : ""), {
      ...init,
      signal,
    })
  ).json()) as ChannelReport;
  if (
    data.ecomm_id !== id ||
    data.identity?.ecomm_id !== id ||
    (data.identity.is_combo !== null &&
      typeof data.identity.is_combo !== "boolean") ||
    (data.identity.parent_is_combo !== null &&
      typeof data.identity.parent_is_combo !== "boolean") ||
    data.external_writes_enabled !== false ||
    data.scope !== "API_VARIANT_CAPTURE_REVIEW" ||
    [data.ml, data.tn].some(
      (c) =>
        !c ||
        !(c.evidence_state in channelLabels) ||
        !Array.isArray(c.candidates) ||
        typeof c.confirmed_listing !== "boolean" ||
        !Array.isArray(c.candidates) ||
        c.candidates.some(
          (r) =>
            typeof r.id !== "string" ||
            (!r.id && r.can_review) ||
            !/^[a-f0-9]{64}$/.test(r.token) ||
            !Number.isSafeInteger(r.revision) ||
            !Array.isArray(r.blockers) ||
            !Array.isArray(r.history),
        ),
    ) ||
    data.tn.confirmed_listing !== false
  )
    throw new CatalogError(
      0,
      "La evidencia de canales no corresponde a esta variante o no acredita su alcance. No se aplicaron datos alternativos.",
    );
  return data;
}
