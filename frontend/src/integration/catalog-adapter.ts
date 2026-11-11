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
  channels?: Record<"ml" | "tn", { status: string; note: string }>;
  reason?: string;
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
      /^\/api\/(?:ecomm-app\/workspace|test-research|test-proposals|test-documents|test-discovery|test-commercial-pilot)\//.test(
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
} as const;
export type QueueFilter = keyof typeof queueFilters;
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
        (filter !== "all" && !row.flags.includes(filter))
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
          (v.confirmed_listing !== undefined && v.confirmed_listing !== false)
        )
          throw new Error("Canal no verificable");
        return {
          status: String(v.status),
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
    return { ...capture, items, matches, summary: counts };
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
