import "./commercial-views.css";
import { useEffect, useState } from "react";
import {
  request,
  captureDate,
  validVariantId,
  comparisonStates,
  type ChannelComparison,
  type QueueFilter,
} from "./catalog-adapter";
import { channelLabels } from "./channel-labels";

export const commercialViews = {
  ecomm: "Catálogo Ecomm-App",
  ml: "Publicaciones Mercado Libre",
  tn: "Registros Tiendanube",
  ml_unconfirmed: "Variantes sin publicación confirmada · ML",
  tn_unconfirmed: "Variantes sin publicación confirmada · TN",
} as const;
export type CommercialView = keyof typeof commercialViews;
export type ListingRow = {
  position: number;
  id: string | null;
  title: string | null;
  sku: string | null;
  ecomm_ids: string[];
  candidate_ecomm_ids?: string[];
  candidate_variants_total?: number;
  identity_ambiguous?: boolean;
  listing_status: string | null;
  evidence_state: string;
  captured_at: string | null;
  confirmed_listing: boolean;
};
export type Listings = {
  channel: "ml" | "tn";
  available: boolean;
  captured_at: string | null;
  total_records: number;
  distinct_publications: number;
  matches: number;
  page: number;
  limit: number;
  items: ListingRow[];
  policy: string;
  scope: string;
  external_writes_enabled: false;
  query?: string;
  linkage?: string;
};
export async function loadListings(
  channel: "ml" | "tn",
  q = "",
  page = 1,
  limit = 6,
  linkage = "all",
  signal?: AbortSignal,
): Promise<Listings> {
  const p = new URLSearchParams({
    channel,
    q,
    page: String(page),
    limit: String(limit),
    linkage,
  });
  const value = (await (
    await request("/api/ecomm-app/workspace/channels/listings?" + p, { signal })
  ).json()) as Listings;
  if (
    value.channel !== channel ||
    value.scope !== "CAPTURED_CHANNEL_RECORDS" ||
    value.external_writes_enabled !== false ||
    typeof value.available !== "boolean" ||
    !Array.isArray(value.items) ||
    !Number.isSafeInteger(value.matches) ||
    value.matches < 0 ||
    !Number.isSafeInteger(value.total_records) ||
    value.total_records < value.matches ||
    !Number.isSafeInteger(value.distinct_publications) ||
    value.distinct_publications > value.total_records ||
    value.query !== q.trim() ||
    value.linkage !== linkage ||
    value.distinct_publications < 0 ||
    value.items.length > limit ||
    new Set(value.items.map((r) => r.position)).size !== value.items.length ||
    value.page !== page ||
    value.limit !== limit ||
    value.items.some(
      (r) =>
        !Number.isSafeInteger(r.position) ||
        r.position < 0 ||
        (r.id !== null && typeof r.id !== "string") ||
        (r.title !== null && typeof r.title !== "string") ||
        (r.sku !== null && typeof r.sku !== "string") ||
        !Array.isArray(r.ecomm_ids) ||
        r.ecomm_ids.some((id) => !validVariantId(id)) ||
        !Object.prototype.hasOwnProperty.call(
          channelLabels,
          r.evidence_state,
        ) ||
        typeof r.confirmed_listing !== "boolean" ||
        (r.evidence_state === "CONFIRMED_CAPTURE") !== r.confirmed_listing ||
        (r.confirmed_listing &&
          (channel !== "ml" ||
            r.evidence_state !== "CONFIRMED_CAPTURE" ||
            !r.ecomm_ids.length)),
    )
  )
    throw new Error(
      "Registros de canal incompatibles; no se sustituyeron por datos simulados.",
    );
  return value;
}
export function CommercialViews({
  value,
  counts,
  onChange,
}: {
  value: CommercialView;
  counts: Partial<Record<CommercialView, number>>;
  onChange: (v: CommercialView) => void;
}) {
  return (
    <nav className="k-commercial-views" aria-label="Vistas comerciales">
      {Object.entries(commercialViews).map(([key, label]) => (
        <button
          type="button"
          key={key}
          data-testid={key === "ecomm" ? "total" : undefined}
          data-metric={key === "ecomm" ? "all" : undefined}
          aria-pressed={value === key}
          onClick={() => onChange(key as CommercialView)}
        >
          {label} <strong>{counts[key as CommercialView] ?? "—"}</strong>
        </button>
      ))}
    </nav>
  );
}
export function ChannelListings({
  channel,
  q,
  page,
  limit,
  linkage,
  onChange,
  onOpen,
  local,
}: {
  channel: "ml" | "tn";
  q: string;
  page: number;
  limit: number;
  linkage: string;
  onChange: (v: Record<string, string>) => void;
  onOpen: (id: string) => void;
  local?: Listings;
}) {
  const [data, setData] = useState<Listings>(),
    [error, setError] = useState("");
  useEffect(() => {
    setError("");
    setData(undefined);
    if (local) {
      setData(local);
      return;
    }
    const c = new AbortController();
    loadListings(channel, q, page, limit, linkage, c.signal)
      .then((v) => {
        if (!c.signal.aborted) setData(v);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [channel, q, page, limit, linkage, local]);
  return (
    <section
      className="k-listings"
      aria-label={`Registros ${channel === "ml" ? "Mercado Libre" : "Tiendanube"}`}
    >
      <h3>{commercialViews[channel]}</h3>
      <p>
        Registros propios del canal, incluidos los que no tienen Ecomm ID
        validado. El catálogo maestro conserva sus identidades.
      </p>
      <label>
        Vinculación{" "}
        <select
          aria-label="Vinculación del canal"
          value={linkage}
          onChange={(e) =>
            onChange({
              linkage: e.target.value,
              page: "",
              product: "",
              tab: "",
            })
          }
        >
          <option value="all">Todos los registros</option>
          <option value="unlinked">Sin Ecomm ID validado</option>
          <option value="verified">Con vinculación validada</option>
          <option value="candidates">Con variantes candidatas</option>
          <option value="conflicts">Conflictos o ambigüedades</option>
          <option value="no_match">Sin variante candidata en captura</option>
          <option value="stale">Captura desactualizada</option>
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Consultando captura del canal…</p>}
      {data && (
        <>
          {!data.available && (
            <p>
              Sin captura disponible: todavía no se puede conocer el total de
              este canal.
            </p>
          )}
          <p>
            {data.total_records} registros · {data.distinct_publications}{" "}
            publicaciones distintas · Captura:{" "}
            {data.available ? captureDate(data.captured_at) : "No disponible"}
          </p>
          <p>{data.policy}</p>
          <div className="k-listings-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Publicación / registro",
                    "SKU",
                    "Estado de captura",
                    "Vinculación Ecomm-App",
                    "Acción",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.position} data-channel-record={r.position}>
                    <td>
                      <strong>{r.title || "Nombre no informado"}</strong>
                      <small>ID del canal: {r.id || "No informado"}</small>
                    </td>
                    <td>{r.sku || "No informado"}</td>
                    <td>
                      {
                        channelLabels[
                          r.evidence_state as keyof typeof channelLabels
                        ]
                      }
                      <small>
                        {r.listing_status || "Estado actual no acreditado"}
                      </small>
                      <small>{captureDate(r.captured_at)}</small>
                    </td>
                    <td>
                      {r.ecomm_ids.length
                        ? r.ecomm_ids.join(", ")
                        : "Sin Ecomm ID validado"}
                    </td>
                    <td>
                      {r.ecomm_ids.map((id) => (
                        <button key={id} onClick={() => onOpen(id)}>
                          Ver variante {id}
                        </button>
                      ))}
                      {(r.candidate_ecomm_ids || [])
                        .filter((id) => !r.ecomm_ids.includes(id))
                        .map((id) => (
                          <button key={id} onClick={() => onOpen(id)}>
                            Revisar candidato {id}
                          </button>
                        ))}
                      {!!r.candidate_variants_total && (
                        <small>
                          {r.candidate_variants_total} variantes candidatas; no
                          son vínculos aprobados.
                        </small>
                      )}
                      {!r.ecomm_ids.length && (
                        <span>
                          Revisar identidad; no se crea una variante ficticia.
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.items.length && (
            <p>
              No hay registros para estos filtros. No demuestra ausencia de
              publicación.
            </p>
          )}
          <footer>
            <span>{data.matches} resultados</span>
            <button
              disabled={page <= 1}
              onClick={() => onChange({ page: String(page - 1) })}
            >
              Anterior
            </button>
            <span>Página {page}</span>
            <button
              disabled={page * limit >= data.matches}
              onClick={() => onChange({ page: String(page + 1) })}
            >
              Siguiente
            </button>
          </footer>
        </>
      )}
    </section>
  );
}

export function ChannelComparisonMatrix({
  comparison,
  filter,
  onFilter,
}: {
  comparison?: Record<"ml" | "tn", ChannelComparison>;
  filter: string;
  onFilter: (value: QueueFilter) => void;
}) {
  const labels = {
    verified: "Vínculos verificados",
    candidates: "Coincidencias pendientes",
    conflicts: "Conflictos o ambigüedades",
    no_match: "Sin coincidencia en captura",
    insufficient: "Evidencia insuficiente",
    stale: "Captura desactualizada",
  };
  return (
    <section
      className="i-channel-comparison"
      aria-label="Matriz de comparación de catálogos"
    >
      <h3>Comparación por variante Ecomm-App</h3>
      <p>
        Sin confirmación no significa «no publicado». Las coincidencias
        requieren revisión humana. Las seis categorías de cada canal suman el
        catálogo maestro; los registros capturados son entidades distintas.
      </p>
      {!comparison ? (
        <p>
          Comparación detallada no disponible en este backend. No se estiman
          coincidencias a partir de los totales.
        </p>
      ) : (
        <div className="i-comparison-grid">
          {(["ml", "tn"] as const).map((channel) => {
            const c = comparison[channel];
            return (
              <section key={channel} data-comparison-channel={channel}>
                <h4>
                  {channel === "ml"
                    ? "Mercado Libre · API"
                    : "Tiendanube · CSV"}
                </h4>
                <p>
                  {c.captured_records} registros · {c.distinct_publications}{" "}
                  {channel === "ml"
                    ? "publicaciones distintas"
                    : "productos distintos"}
                </p>
                <p>
                  Captura: {captureDate(c.snapshot_at)} ·{" "}
                  {c.freshness.age_hours === null
                    ? "Antigüedad desconocida"
                    : `${c.freshness.age_hours} h de antigüedad`}{" "}
                  ·{" "}
                  {c.freshness.fresh
                    ? "Dentro del plazo de revisión"
                    : "Sin vigencia para confirmar el estado actual"}
                </p>
                {!c.freshness.fresh && c.snapshot_at && (
                  <p>
                    La fuente no tiene vigencia para ninguna de las {c.variants}{" "}
                    variantes. En las categorías se priorizan los conflictos;
                    «Captura desactualizada» cuenta las restantes.
                  </p>
                )}
                <p>
                  {c.records_without_sku} registros sin SKU ·{" "}
                  {c.records_without_valid_gtin} sin GTIN válido
                </p>
                <div className="k-quality-metrics">
                  {comparisonStates.map((state) => {
                    const value =
                      `${channel}_comparison_${state}` as QueueFilter;
                    return (
                      <button
                        key={state}
                        aria-pressed={filter === value}
                        onClick={() => onFilter(value)}
                      >
                        {labels[state]}{" "}
                        <strong>{c.variant_states[state]}</strong>
                      </button>
                    );
                  })}
                </div>
                <p>
                  {c.variants} variantes clasificadas ·{" "}
                  {c.variants_with_candidates} con candidatos (pueden incluir
                  conflictos o información vencida).
                </p>
                <p>
                  {c.records_with_candidates} registros con candidatos +{" "}
                  {c.records_without_candidate} sin candidato ={" "}
                  {c.valid_records} registros válidos
                  {c.invalid_records
                    ? `; ${c.invalid_records} inválidos`
                    : ""}. {c.verified_records} registros vinculados y vigentes.
                </p>
                <p>
                  {channel === "ml"
                    ? `${c.confirmed_publications} publicaciones distintas activas con vínculo verificado en captura; no es una consulta en vivo.`
                    : "El CSV no demuestra publicación actual, incluso con vínculo revisado."}
                </p>
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}
