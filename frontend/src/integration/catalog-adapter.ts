import { channelLabels } from "./channel-labels";
export const catalogPath = "/api/ecomm-app/stage/catalog";
export const captureSource = "ECOMM_APP_API_STAGE";
export const unavailable = "Sin datos disponibles";
export type Variant = {
  id: string;
  name: string | null;
  sku: string | null;
  presentation: string | null;
  stock: number | null;
  capturedAt: string | null;
  gtin: string | null;
  isCombo: boolean | null;
  parentIsCombo?: boolean | null;
  barcode?: string | null;
  gtinRaw?: string | null;
  identityBlockers?: string[];
  brand?: string | null;
  commercialName?: string | null;
  editorialStatus?: string;
  editVersion?: number;
  channels?: Record<
    "ml" | "tn",
    { status: string; note: string; evidenceState?: string }
  >;
  reason?: string;
  flags?: string[];
};
export type CatalogPage = {
  items: Variant[];
  total: number;
  matches: number;
  page: number;
  pageSize: number;
  firstAt: string | null;
  lastAt: string | null;
  source: typeof captureSource;
  summary?: Record<string, number>;
  channelOverview?: {
    validated: boolean;
    confirmedMlListings: number;
    sources: Record<
      "ml" | "tn",
      { available: boolean; updatedAt: string | null }
    >;
  };
};
export class CatalogError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
const messages: Record<number, string> = {
  401: "La sesión venció. Ingresá nuevamente para consultar el catálogo.",
  403: "No tenés permiso para consultar este catálogo.",
  409: "Captura incompleta o no disponible. No se mostrará un catálogo parcial.",
  500: "El backend de pruebas no pudo responder. Intentá nuevamente.",
};
export async function request(path: string, options: RequestInit = {}) {
  let response: Response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new CatalogError(
      0,
      "No pudimos comunicarnos con el backend de pruebas. No se cargaron datos de demostración.",
    );
  }
  if (!response.ok) {
    if (
      [
        "/api/ecomm-app/stage/manual/start",
        "/api/mercadolibre/sync",
        "/api/mercadolibre/auth-url",
        "/api/tiendanube/import-csv",
      ].includes(path)
    ) {
      const body = await response.json().catch(() => null);
      throw new CatalogError(
        response.status,
        typeof body?.detail === "string"
          ? body.detail.slice(0, 600)
          : "No se pudo completar la actualización de la copia interna.",
      );
    }
    if (
      /^\/api\/(?:ecomm-app\/(?:workspace|editorial-batches)|test-research|test-proposals|test-documents|test-discovery|test-commercial-pilot)\//.test(
        path,
      ) &&
      [409, 422].includes(response.status)
    ) {
      const body = await response.json().catch(() => null);
      throw new CatalogError(
        response.status,
        typeof body?.detail === "string"
          ? body.detail.slice(0, 600)
          : "Revisá el formato y los límites de los campos de la ficha.",
      );
    }
    throw new CatalogError(
      response.status,
      messages[response.status] || "El backend de pruebas no está disponible.",
    );
  }
  if (response.headers.get("X-Kiki-Environment") !== "local-synthetic")
    throw new CatalogError(
      0,
      "Respuesta rechazada: el backend no acredita el entorno sintético.",
    );
  return response;
}
const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Objeto inválido");
  return value as Record<string, unknown>;
};
const count = (value: unknown): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new Error("Cantidad inválida");
  return value;
};
const text = (value: unknown): string | null => {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string") throw new Error("Texto inválido");
  return value;
};
const date = (value: unknown) => {
  const result = text(value);
  if (result !== null && !Number.isFinite(Date.parse(result)))
    throw new Error("Fecha inválida");
  return result;
};
export function validVariantId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[A-Za-z0-9_-]{1,120}$/.test(value) &&
    !/^(?:none|null|undefined|nan|inf|infinity)$/i.test(value) &&
    (!/^-?\d+$/.test(value) || /^[1-9]\d*$/.test(value))
  );
}

export function adaptVariant(raw: unknown, ids = new Set<string>()): Variant {
  const row = object(raw),
    id = text(row.ecomm_id);
  if (!validVariantId(id) || ids.has(id)) throw new Error("Identidad inválida");
  ids.add(id);
  const stock = row.stock_at_capture ?? null;
  if (stock !== null && (typeof stock !== "number" || !Number.isFinite(stock)))
    throw new Error("Stock inválido");
  const barcode = text(row.barcode),
    gtinRaw = text("gtin_raw" in row ? row.gtin_raw : row.gtin);
  const blockers = row.identity_blockers ?? [];
  if (
    !Array.isArray(blockers) ||
    blockers.some((x) => x !== "BARCODE_GTIN_CONFLICT")
  )
    throw new Error("Diagnóstico inválido");
  return {
    id,
    name: text(row.product_name),
    sku: text(row.sku),
    presentation: text(row.variant_description),
    stock,
    capturedAt: date(row.captured_at),
    gtin: text(row.gtin),
    barcode,
    gtinRaw,
    isCombo: typeof row.is_combo === "boolean" ? row.is_combo : null,
    parentIsCombo:
      typeof row.parent_is_combo === "boolean" ? row.parent_is_combo : null,
    identityBlockers: [
      ...new Set([
        ...blockers,
        ...(barcode && gtinRaw && barcode !== gtinRaw
          ? ["BARCODE_GTIN_CONFLICT"]
          : []),
      ]),
    ],
  };
}
export function adaptCatalog(
  payload: unknown,
  query: string,
  page: number,
  pageSize: number,
): CatalogPage {
  try {
    const data = object(payload);
    if (
      data.mode !== "API_CAPTURE_READ_ONLY" ||
      data.source !== captureSource ||
      data.operational_source_activated !== false ||
      data.external_writes_enabled !== false ||
      data.query !== query.trim() ||
      data.page !== page ||
      data.page_size !== pageSize ||
      !Array.isArray(data.items)
    )
      throw new Error("Contrato incompatible");
    const total = count(data.total_variants_in_capture),
      matches = count(data.total_matches);
    const quality = object(data.quality);
    if (
      count(quality.variants) !== total ||
      count(quality.duplicate_variant_ids) !== 0 ||
      count(quality.without_variant_id) !== 0 ||
      count(quality.invalid_variants) !== 0
    )
      throw new Error("Total de captura ambiguo");
    const ids = new Set<string>();
    const items = data.items.map((raw) => adaptVariant(raw, ids));
    if (
      items.length > pageSize ||
      matches > total ||
      items.length > matches ||
      items.length !==
        Math.max(0, Math.min(pageSize, matches - (page - 1) * pageSize))
    )
      throw new Error("Página inconsistente");
    return {
      items,
      total,
      matches,
      page,
      pageSize,
      source: captureSource,
      firstAt: date(data.capture_first_at),
      lastAt: date(data.capture_last_at),
    };
  } catch {
    throw new CatalogError(
      0,
      "Respuesta de catálogo incompatible o ambigua. No se cargaron datos alternativos.",
    );
  }
}

export const queueFilters = {
  ean_missing: "EAN no informado en Ecomm-App",
  ean_repeated: "EAN repetido · revisar presentaciones",
  sku_repeated: "SKU repetido · no confirma duplicados",
  possible_duplicates: "Posibles duplicados · revisar códigos",
  sku_family: "Familias SKU candidatas",
  barcode_gtin_conflict: "Barcode y GTIN contradictorios",
  short_description_missing: "Sin descripción corta",
  long_description_missing: "Sin descripción larga",
  commercial_title_missing: "Sin título comercial",
  category_missing: "Sin categoría",
  subcategory_missing: "Sin subcategoría",
  attributes_missing: "Sin atributos",
  images_missing: "Sin imágenes registradas",
  video_unrecorded: "Sin video · revisar si corresponde",
  seo_missing: "SEO incompleto",
  ml_unconfirmed: "Sin publicación confirmada en ML",
  tn_unconfirmed: "Sin publicación confirmada en TN",
  proposals_pending: "Propuestas pendientes de revisión",
  commercial_incomplete: "Ficha comercial incompleta",

  review_soon: "Próximos a revisión mensual",
  evidence_approved: "Con aprobaciones documentales (verificar vigencia)",
  needs_research: "Requieren investigación",
  evidence_revoked: "Con evidencia revocada",
  documents_changed: "Con documentación modificada",
  all: "Todo el catálogo",
  identity: "Identidad por revisar",
  untouched: "Sin trabajar",
  draft: "En preparación",
  ready: "Listas para revisión",
  ready_for_channels: "Ficha completa (interno)",
  pack: "Packs y combos",
  review_due: "Revisión vencida",
  needs_completion: "Completar ficha",
  ml_candidate: "Candidatos Mercado Libre",
  tn_candidate: "Candidatos Tiendanube",
  channel_review: "Revisar canales",
  missing_gtin: "Código no disponible en la captura",
  ml_confirmed: "Publicación ML confirmada en captura",
  tn_confirmed: "Publicación TN sin contrato verificable",
  tn_verified: "Vínculos TN verificados (no publicación actual)",
  channel_candidates: "Candidatos de canal pendientes",
  channel_conflicts: "Conflictos de identidad en canales",
  channel_no_evidence: "Sin evidencia suficiente de canal",
  channel_stale: "Capturas de canal desactualizadas",
} as const;
export type QueueFilterKey = keyof typeof queueFilters;
export type QueueFilter =
  | QueueFilterKey
  | `${QueueFilterKey}+${QueueFilterKey}`;
export function validQueueFilter(value: string): value is QueueFilter {
  const parts = value.split("+");
  return (
    parts.length <= 2 &&
    new Set(parts).size === parts.length &&
    parts.every((p) => Object.prototype.hasOwnProperty.call(queueFilters, p))
  );
}
export const queuePath = "/api/ecomm-app/workspace/queue";

export function adaptQueue(
  payload: unknown,
  capture: CatalogPage,
  q: string,
  page: number,
  limit: number,
  filter: QueueFilter,
): CatalogPage {
  try {
    const data = object(payload),
      summary = object(data.summary);
    if (
      data.source !== captureSource ||
      data.mode !== "KIKI_INTERNAL_READ_ONLY_TRIAGE" ||
      data.external_writes_enabled !== false ||
      data.query !== q.trim() ||
      data.filter !== filter ||
      data.page !== page ||
      data.limit !== limit ||
      data.sort !== "capture" ||
      !Array.isArray(data.items) ||
      date(data.source_snapshot_at) !== capture.lastAt ||
      count(summary.total) !== capture.total
    )
      throw new Error("Capturas incompatibles");
    const counts = Object.fromEntries(
      Object.entries(summary).map(([key, value]) => [key, count(value)]),
    );
    if (
      Object.values(counts).some((n) => n > capture.total) ||
      Object.keys(queueFilters).some((k) => k !== "all" && !(k in counts))
    )
      throw new Error("Indicadores incoherentes");
    const ids = new Set<string>();
    const items = data.items.map((value) => {
      const row = object(value),
        source = object(row.source),
        variant = adaptVariant(source, ids);
      const captured = capture.items.find((item) => item.id === variant.id);
      if (
        captured &&
        [
          "name",
          "sku",
          "presentation",
          "stock",
          "capturedAt",
          "gtin",
          "barcode",
          "gtinRaw",
          "isCombo",
          "parentIsCombo",
        ].some(
          (key) =>
            captured[key as keyof Variant] !== variant[key as keyof Variant],
        )
      )
        throw new Error("Variante cambió entre lecturas");
      if (
        row.ecomm_id !== variant.id ||
        (text(row.sku) ?? "") !== (variant.sku?.trim() ?? "") ||
        (text(row.product_name) ?? "") !== (variant.name?.trim() ?? "") ||
        ![
          "NOT_STARTED",
          "DRAFT",
          "READY_FOR_REVIEW",
          "READY_FOR_CHANNELS",
        ].includes(String(row.status)) ||
        !Array.isArray(row.flags) ||
        !filter
          .split("+")
          .filter((f) => f !== "all")
          .every((f) => (row.flags as unknown[]).includes(f))
      )
        throw new Error("Fila incompatible");
      const channels = object(row.channel_coverage);
      const channel = (key: "ml" | "tn") => {
        const v = object(channels[key]);
        if (
          ![
            "UNAVAILABLE",
            "AMBIGUOUS_API_SKU",
            "NO_EXACT_SKU_IN_SNAPSHOT",
            "MULTIPLE_SKU_ROWS",
            "SKU_CANDIDATE",
            "PACK_REVIEW",
            "PRESENTATION_CONFLICT",
            "GTIN_CONFLICT",
          ].includes(String(v.status)) ||
          (v.evidence_state !== undefined &&
            !(String(v.evidence_state) in channelLabels)) ||
          (v.confirmed_listing === true &&
            (v.evidence_state !== "CONFIRMED_CAPTURE" ||
              key !== "ml" ||
              v.identity_verified !== true))
        )
          throw new Error("Canal no verificable");
        return {
          status: String(v.status),
          evidenceState:
            typeof v.evidence_state === "string" ? v.evidence_state : undefined,
          note: text(v.note) ?? "Sin evidencia suficiente de publicación.",
        };
      };
      return {
        ...variant,
        brand: text(row.proposed_brand),
        commercialName: text(row.proposed_title),
        editorialStatus: String(row.status),
        editVersion: count(row.edit_version),
        channels: { ml: channel("ml"), tn: channel("tn") },
        reason: text(row.reason) ?? undefined,
        flags: (row.flags as unknown[]).filter(
          (v): v is string => typeof v === "string",
        ),
      };
    });
    const matches = count(data.total);
    if (
      !q.trim() &&
      filter === "all" &&
      capture.items.map((x) => x.id).join() !== items.map((x) => x.id).join()
    )
      throw new Error("Páginas de capturas distintas");
    if (
      matches > capture.total ||
      items.length !==
        Math.max(0, Math.min(limit, matches - (page - 1) * limit))
    )
      throw new Error("Página incompatible");
    const coverage = object(data.channel_coverage),
      overview = object(coverage.summary),
      sources = object(coverage.sources);
    const source = (key: "ml" | "tn") => {
      const v = object(sources[key]);
      if (typeof v.available !== "boolean")
        throw new Error("Fuente de canal inválida");
      return { available: v.available, updatedAt: date(v.updated_at) };
    };
    return {
      ...capture,
      items,
      matches,
      summary: counts,
      channelOverview: {
        validated: coverage.api_validation_enabled === true,
        confirmedMlListings: count(overview.confirmed_ml_listings ?? 0),
        sources: { ml: source("ml"), tn: source("tn") },
      },
    };
  } catch {
    throw new CatalogError(
      0,
      "Cola de trabajo incompatible con la captura. No se cargaron datos alternativos.",
    );
  }
}

export async function loadDashboard(
  q: string,
  page: number,
  limit: number,
  filter: QueueFilter,
  signal: AbortSignal,
) {
  const params = new URLSearchParams({
    q: q.trim(),
    page: String(page),
    limit: String(limit),
    filter,
    sort: "capture",
  });
  const [capture, queue] = await Promise.all([
    loadCatalog(q, page, limit, signal),
    request(`${queuePath}?${params}`, { signal }).then((r) => r.json()),
  ]);
  return adaptQueue(queue, capture, q, page, limit, filter);
}
export async function loadCatalog(
  query: string,
  page: number,
  pageSize: number,
  signal: AbortSignal,
) {
  const params = new URLSearchParams({
    q: query.trim(),
    page: String(page),
    limit: String(pageSize),
  });
  const response = await request(`${catalogPath}?${params}`, { signal });
  return adaptCatalog(await response.json(), query, page, pageSize);
}
export function captureDate(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("es-AR", {
        dateStyle: "short",
        timeStyle: "short",
        timeZone: "America/Argentina/Buenos_Aires",
      }).format(new Date(value))
    : unavailable;
}

export const qualityFilterKeys = [
  "ean_missing",
  "ean_repeated",
  "sku_repeated",
  "possible_duplicates",
  "sku_family",
  "barcode_gtin_conflict",
  "short_description_missing",
  "long_description_missing",
  "commercial_title_missing",
  "category_missing",
  "subcategory_missing",
  "attributes_missing",
  "images_missing",
  "video_unrecorded",
  "seo_missing",
  "ml_unconfirmed",
  "tn_unconfirmed",
  "proposals_pending",
  "commercial_incomplete",
] as const;
