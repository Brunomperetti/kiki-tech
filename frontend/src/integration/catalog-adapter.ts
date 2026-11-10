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
      /^\/api\/(?:ecomm-app\/workspace|test-research)\//.test(path) &&
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
    const items = data.items.map((raw): Variant => {
      const row = object(raw),
        id = text(row.ecomm_id);
      if (!id || !/^[A-Za-z0-9_-]{1,120}$/.test(id) || ids.has(id))
        throw new Error("Identidad inválida");
      ids.add(id);
      const stock = row.stock_at_capture ?? null;
      if (
        stock !== null &&
        (typeof stock !== "number" || !Number.isFinite(stock))
      )
        throw new Error("Stock inválido");
      return {
        id,
        name: text(row.product_name),
        sku: text(row.sku),
        presentation: text(row.variant_description),
        stock,
        capturedAt: date(row.captured_at),
        gtin: text(row.gtin),
        isCombo: typeof row.is_combo === "boolean" ? row.is_combo : null,
      };
    });
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
