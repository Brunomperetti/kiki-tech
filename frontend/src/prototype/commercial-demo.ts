import { assessCommercialReadiness } from "../components/CommercialBackofficeFields";
import type { Item } from "./operations-model";
import { isConfirmed } from "./operations-model";
import type { Listings, ListingRow } from "../integration/CommercialViews";

export function demoListings(
  rows: Item[],
  channel: "ml" | "tn",
  q = "",
  page = 1,
  limit = 6,
  linkage = "all",
): Listings {
  const all: ListingRow[] = [];
  for (const p of rows) {
    for (const r of p.evidence[channel].publications) {
      const linked = isConfirmed(p, channel);
      all.push({
        position: all.length,
        id: r.id,
        title: p.name,
        sku: p.sku,
        ecomm_ids: linked ? [p.id] : [],
        listing_status: channel === "ml" ? "Estado simulado de captura" : null,
        evidence_state:
          p.evidence[channel].freshness !== "current"
            ? "STALE"
            : channel === "ml" && linked
              ? "CONFIRMED_CAPTURE"
              : linked
                ? "VERIFIED_LINK"
                : "PENDING_VALIDATION",
        captured_at: "2026-11-09T15:00:00Z",
        confirmed_listing: channel === "ml" && linked,
      });
    }
    if (
      p[channel] === "SKU coincidente" &&
      !p.evidence[channel].publications.length
    )
      all.push({
        position: all.length,
        id: null,
        title: p.name + " · candidato simulado",
        sku: p.sku,
        ecomm_ids: [],
        listing_status: null,
        evidence_state: "CANDIDATE",
        captured_at: "2026-11-09T15:00:00Z",
        confirmed_listing: false,
      });
  }
  all.push({
    position: all.length,
    id: channel === "ml" ? "DEMO-ML-SIN-VINCULO" : "demo-tn-sin-vinculo",
    title: "Garbanzos de muestra · registro sin vincular",
    sku: "DEMO-EXTERNO",
    ecomm_ids: [],
    listing_status: null,
    evidence_state: "PENDING_VALIDATION",
    captured_at: "2026-11-09T15:00:00Z",
    confirmed_listing: false,
  });
  const filtered = all.filter(
    (r) =>
      (!q ||
        [r.title, r.sku, r.id, ...r.ecomm_ids]
          .join(" ")
          .toLocaleLowerCase()
          .includes(q.toLocaleLowerCase())) &&
      (linkage !== "unlinked" || !r.ecomm_ids.length) &&
      (linkage !== "verified" || r.ecomm_ids.length),
  );
  return {
    channel,
    available: true,
    captured_at: "2026-11-09T15:00:00Z",
    total_records: all.length,
    distinct_publications: new Set(all.filter((r) => r.id).map((r) => r.id))
      .size,
    matches: filtered.length,
    page,
    limit,
    items: filtered.slice((page - 1) * limit, page * limit),
    policy:
      "Escenario exclusivamente sintético en memoria. Sin backend ni publicaciones reales. El CSV Tiendanube no demuestra actividad actual; los candidatos no son vinculaciones confirmadas.",
    scope: "CAPTURED_CHANNEL_RECORDS",
    external_writes_enabled: false,
  };
}
export function demoQuality(p: Item, rows: Item[]): string[] {
  const fields: Record<string, boolean> = {
    ean_missing: !p.ean,
    ean_repeated: !!p.ean && rows.filter((r) => r.ean === p.ean).length > 1,
    sku_repeated: rows.filter((r) => r.sku === p.sku).length > 1,
    sku_family: rows.filter((r) => r.family === p.family).length > 1,
    barcode_gtin_conflict: !!p.barcode && !!p.ean && p.barcode !== p.ean,
    commercial_title_missing: !p.commercial.title.trim(),
    long_description_missing: !p.description.trim(),
    short_description_missing: !p.commercial.short_description.trim(),
    category_missing: !p.category.trim(),
    subcategory_missing: !p.commercial.subcategory.trim(),
    attributes_missing: !p.commercial.attributes.length,
    images_missing: !p.commercial.media.some(
      (m) => m.kind === "IMAGE" && m.url.startsWith("https://"),
    ),
    video_unrecorded: !p.commercial.media.some(
      (m) => m.kind === "VIDEO" && m.url.startsWith("https://"),
    ),
    seo_missing:
      !p.commercial.seo_title.trim() || !p.commercial.seo_description.trim(),
    commercial_incomplete: !assessCommercialReadiness(p.commercial).ready,
    proposals_pending: p.ai?.state === "Pendiente",
  };
  fields.possible_duplicates = fields.ean_repeated || fields.sku_repeated;
  return Object.keys(fields).filter((k) => fields[k]);
}
