import { channelLabels } from "./channel-labels";
import { production, capabilities, environmentText } from "./runtime";
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
    {
      status: string;
      note: string;
      evidenceState?: string;
      candidatesTotal?: number;
      snapshotAt?: string | null;
      comparisonState?: string;
      fresh?: boolean;
      matchesPreview?: {
        id: string | null;
        slug?: string | null;
        title: string | null;
        identity_verified: boolean;
        match_reasons: string[];
        discrepancies: string[];
      }[];
    }
  >;
  reason?: string;
  flags?: string[];
};
export const comparisonStates = [
  "verified",
  "candidates",
  "conflicts",
  "no_match",
  "insufficient",
] as const;
export type ComparisonState = (typeof comparisonStates)[number];
export type ChannelComparison = {
  variants: number;
  matching_independent_of_freshness: true;
  stale_variants: number;
  variant_states: Record<ComparisonState, number>;
  captured_records: number;
  valid_records: number;
  invalid_records: number;
  distinct_publications: number;
  records_without_sku: number;
  records_without_valid_gtin: number;
  candidate_pairs: number;
  records_with_candidates: number;
  records_without_candidate: number;
  verified_records: number;
  confirmed_publications: number;
  variants_with_candidates: number;
  variants_with_pending_candidates: number;
  snapshot_at: string | null;
  freshness: {
    fresh: boolean;
    age_hours: number | null;
    review_after_hours: number;
  };
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
    comparison?: Record<"ml" | "tn", ChannelComparison>;
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
    if (production) {
      const url = new URL(path, location.origin);
      if (
        !path.startsWith("/api/") ||
        url.origin !== location.origin ||
        url.username ||
        url.password ||
        url.hash ||
        url.pathname.startsWith("/api/test-")
      )
        throw new Error("Destino no permitido");
      const method = (options.method || "GET").toUpperCase();
      if (!["GET", "POST"].includes(method))
        throw new Error("Método no autorizado");
      if (
        method === "POST" &&
        !["/api/auth/login", "/api/auth/logout"].includes(url.pathname) &&
        !capabilities?.writes
      )
        throw new Error("Interfaz de sólo lectura");
      const headers = new Headers(options.headers);
      headers.set("X-Kiki-UI", "v2");
      options = {
        ...options,
        headers,
        credentials: "same-origin",
        redirect: "error",
        cache: "no-store",
      };
    }
    response = await fetch(path, options);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new CatalogError(
      0,
      environmentText(
        "No pudimos comunicarnos con el backend de pruebas. No se cargaron datos de demostración.",
        "No pudimos completar la solicitud al backend de KIKI. No se cargan datos alternativos; revisá la sesión y los permisos.",
      ),
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
      (production && response.status >= 500
        ? "El backend de KIKI no está disponible."
        : messages[response.status]) ||
        environmentText(
          "El backend de pruebas no está disponible.",
          "El backend de KIKI no está disponible.",
        ),
    );
  }
  if (
    production
      ? response.headers.get("X-Kiki-UI-Contract") !== "kiki-same-origin-v2-1"
      : response.headers.get("X-Kiki-Environment") !== "local-synthetic"
  )
    throw new CatalogError(
      0,
      environmentText(
        "Respuesta rechazada: el backend no acredita el entorno sintético.",
        "Respuesta rechazada: contrato del backend 2.0 no acreditado.",
      ),
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
  ml_pending_candidates: "Candidatos por revisar · ML",
  tn_pending_candidates: "Candidatos por revisar · TN",
  ml_found: "Coincidencias encontradas en ML",
  tn_found: "Coincidencias encontradas en TN",
  ml_comparison_verified: "Vínculos verificados · ML",
  ml_comparison_candidates: "Coincidencias sin conflicto · ML",
  ml_comparison_conflicts: "Conflictos o ambigüedades · ML",
  ml_comparison_no_match: "Sin coincidencia en captura · ML",
  ml_comparison_insufficient: "Evidencia insuficiente · ML",
  ml_comparison_stale: "Captura desactualizada · ML",
  tn_comparison_verified: "Vínculos verificados · TN",
  tn_comparison_candidates: "Coincidencias sin conflicto · TN",
  tn_comparison_conflicts: "Conflictos o ambigüedades · TN",
  tn_comparison_no_match: "Sin coincidencia en captura · TN",
  tn_comparison_insufficient: "Evidencia insuficiente · TN",
  tn_comparison_stale: "Captura desactualizada · TN",
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
          candidatesTotal: count(v.candidates_total ?? 0),
          snapshotAt: date(v.snapshot_at),
          fresh:
            typeof object(v.freshness).fresh === "boolean"
              ? Boolean(object(v.freshness).fresh)
              : undefined,
          matchesPreview: (Array.isArray(v.matches_preview)
            ? v.matches_preview
            : []
          ).map((raw: unknown) => {
            const c = object(raw);
            if (
              (c.id !== null && typeof c.id !== "string") ||
              (c.title !== null && typeof c.title !== "string") ||
              typeof c.identity_verified !== "boolean" ||
              !Array.isArray(c.match_reasons) ||
              !Array.isArray(c.discrepancies)
            )
              throw new Error("Coincidencia de canal incompatible");
            return c as {
              id: string | null;
              title: string | null;
              identity_verified: boolean;
              match_reasons: string[];
              discrepancies: string[];
            };
          }),
          comparisonState:
            typeof v.comparison_state === "string"
              ? v.comparison_state
              : undefined,
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
    const comparison =
      overview.comparison === undefined
        ? undefined
        : (() => {
            const raw = object(overview.comparison);
            const read = (channel: "ml" | "tn") => {
              const c = object(raw[channel]);
              const states = object(c.variant_states);
              const totals = Object.fromEntries(
                comparisonStates.map((k) => [k, count(states[k])]),
              );
              if (
                count(c.variants_with_pending_candidates) >
                  count(c.variants_with_candidates) ||
                count(c.variants_with_candidates) > capture.total ||
                c.matching_independent_of_freshness !== true ||
                count(c.stale_variants) > capture.total ||
                count(c.variants) !== capture.total ||
                Object.values(totals).reduce((a, b) => a + b, 0) !==
                  capture.total
              )
                throw new Error("Totales por variante incompatibles");
              for (const k of [
                "captured_records",
                "valid_records",
                "invalid_records",
                "distinct_publications",
                "records_without_sku",
                "records_without_valid_gtin",
                "candidate_pairs",
                "records_with_candidates",
                "records_without_candidate",
                "verified_records",
                "confirmed_publications",
                "variants_with_candidates",
                "variants_with_pending_candidates",
              ])
                count(c[k]);
              if (
                Number(c.valid_records) + Number(c.invalid_records) !==
                  c.captured_records ||
                Number(c.records_with_candidates) +
                  Number(c.records_without_candidate) !==
                  c.valid_records
              )
                throw new Error("Registros de canal incompatibles");
              const freshness = object(c.freshness);
              if (typeof freshness.fresh !== "boolean")
                throw new Error("Vigencia no informada");
              return { ...c, variant_states: totals } as ChannelComparison;
            };
            return { ml: read("ml"), tn: read("tn") };
          })();
    return {
      ...capture,
      items,
      matches,
      summary: counts,
      channelOverview: {
        validated: coverage.api_validation_enabled === true,
        comparison,
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
