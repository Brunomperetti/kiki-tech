import { environmentText } from "./runtime";
import "./channel-cards.css";
import { TiendanubePreviewPanel } from "./TiendanubePreviewPanel";
import { MercadoLibrePreviewPanel } from "./MercadoLibrePreviewPanel";
import { useEffect, useState } from "react";
import { captureDate } from "./catalog-adapter";
import {
  channelLabels,
  loadChannels,
  type ChannelReport,
  type ChannelCandidate,
} from "./channel-adapter";
import { isAuxiliaryPilot } from "./hileret-pilot";

export function ChannelsPanel({
  id,
  csrf,
  blocked,
  onBusy,
  onReviewed,
  productTitle,
  productSku,
  editorialLabel,
  editorialReady,
  onOpenFicha,
}: {
  id: string;
  csrf: string;
  blocked: boolean;
  onBusy: (v: boolean) => void;
  onReviewed: () => void;
  productTitle: string;
  productSku: string;
  editorialLabel: string;
  editorialReady: boolean;
  onOpenFicha: () => void;
}) {
  const [view, setView] = useState<"overview" | "ml" | "tn" | "identity">("overview");
  const [channelData, setData] = useState<ChannelReport>(),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [revision, reload] = useState(0);
  const [notes, setNotes] = useState<Record<string, string>>({}),
    [quantities, setQuantities] = useState<Record<string, string>>({}),
    [checks, setChecks] = useState<Record<string, string[]>>({});
  // Never display an earlier variant's channel data after product switching.
  const data = channelData?.ecomm_id === id ? channelData : undefined;
  useEffect(() => {
    onBusy(busy);
    return () => onBusy(false);
  }, [busy, onBusy]);
  useEffect(() => {
    if (isAuxiliaryPilot(id)) return;
    const c = new AbortController();
    setLoading(true);
    setData((current) => current?.ecomm_id === id ? current : undefined);
    setError("");
    loadChannels(id, c.signal)
      .then((v) => {
        if (!c.signal.aborted) setData(v);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [id, revision]);
  if (isAuxiliaryPilot(id))
    return (
      <p>
        Ecomm ID auténtico pendiente. El expediente auxiliar no se vincula a
        canales ni transfiere aprobaciones.
      </p>
    );
  const labels = {
    name: "Nombre",
    brand: "Marca",
    presentation: "Presentación",
    quantity: "Cantidad comercial",
    sale_type: "Unidad, pack o combo",
    codes: "Códigos disponibles y sus límites",
  };
  async function review(
    channel: "ml" | "tn",
    row: ChannelCandidate,
    decision: "APPROVED" | "REVOKED",
  ) {
    const key = channel + row.id;
    if (
      !window.confirm(
        decision === "APPROVED"
          ? environmentText(
              "¿Registrar esta vinculación interna por Ecomm ID? No publica ni modifica datos del canal. La revisión de prueba no es una aprobación auténtica del cliente.",
              "¿Registrar esta vinculación interna al Ecomm ID exacto tras contrastar identidad y presentación? No publica ni modifica datos del canal.",
            )
          : "¿Revocar esta vinculación interna? Se conserva el historial; no modifica la publicación.",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      setData(
        await loadChannels(id, undefined, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({
            channel,
            listing_id: row.id,
            expected_fingerprint: row.token,
            expected_revision: row.revision,
            decision,
            checks: checks[key] || [],
            quantity_commercial: Number(quantities[key]),
            reason: notes[key] || "",
          }),
        }),
      );
      onReviewed();
    } catch (e) {
      setError((e as Error).message);
      try {
        setData(await loadChannels(id));
      } catch {
        /* keep prior data for comparison; never confirm it */
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="r-research c-panel"
      aria-label="Canales por variante API"
    >
      {view === "overview" && (
        <div className="k-channel-overview" data-testid="channel-overview">
          <div className="k-channel-product">
            <span className="k-channel-eyebrow">Estado comercial</span>
            <h3>{productTitle}</h3>
            <span className="k-channel-meta">SKU {productSku || "Sin dato"}</span>
            <div className="k-channel-ficha">
              <span>Ficha comercial</span>
              <strong>{editorialLabel}</strong>
            </div>
          </div>
          <div className="k-channel-grid">
            {(["ml", "tn"] as const).map((channel) => {
              const c = data?.[channel];
              const stale = c && (!c.freshness.fresh || !c.snapshot_available);
              const label = !c || error ? "Sin verificar"
                : c.comparison_state === "no_match" ? "Sin coincidencia en captura"
                : c.identity_verified && c.freshness.fresh ? "Identidad revisada"
                : c.candidates_total ? "Requiere revisión" : "Sin verificar";
              return (
                <article key={channel} className={"k-channel-card k-channel-" + channel}>
                  <div className="k-channel-brand">
                    <span className="k-channel-mark" aria-hidden="true">{channel === "ml" ? "ML" : "TN"}</span>
                    <h4>{channel === "ml" ? "Mercado Libre" : "Tiendanube"}</h4>
                  </div>
                  <strong className="k-channel-status">{loading ? "Consultando…" : label}</strong>
                  <span className="k-channel-meta">{c ? c.candidates_total + " coincidencias en captura" : "Sin datos de comparación"}</span>
                  {stale && <span className="k-channel-stale">Captura desactualizada</span>}
                  <button type="button" disabled={busy} onClick={() => setView(channel)}>
                    {channel === "ml" ? "Ver Mercado Libre" : "Ver Tiendanube"}
                  </button>
                </article>
              );
            })}
          </div>
          <div className="k-channel-next">
            <span className="k-channel-eyebrow">Siguiente paso</span>
            <h4>{editorialReady ? "Revisar los canales" : "Completar y revisar la ficha"}</h4>
            <p>{editorialReady ? "Consultá cada canal antes de preparar el envío." : "Completá la información comercial y sus evidencias antes de preparar el envío."}</p>
            {!editorialReady && <button type="button" className="d-primary" disabled={busy} onClick={onOpenFicha}>Ir a la ficha comercial</button>}
            <span className="k-channel-meta">Envíos externos no habilitados.</span>
          </div>
          {blocked && <p role="alert">Resolvé los cambios pendientes o bloqueos de la ficha antes de validar.</p>}
          {error && <p role="alert">{error}</p>}
          <div className="k-channel-tools">
            <button type="button" disabled={busy || loading} onClick={() => reload((v) => v + 1)}>{loading ? "Consultando capturas…" : "Volver a consultar canales"}</button>
            <button type="button" disabled={busy} onClick={() => setView("identity")}>Ver información técnica</button>
          </div>
        </div>
      )}
      <div className="k-channel-detail" hidden={view === "overview"}>
      <button type="button" disabled={busy} onClick={() => setView("overview")}>← Volver al resumen de canales</button>
      <h3>{view === "ml" ? "Mercado Libre" : view === "tn" ? "Tiendanube" : "Información técnica"}</h3>
      <div hidden={view !== "tn"}><TiendanubePreviewPanel key={id} id={id} csrf={csrf} blocked={blocked || busy} /></div>
      <div hidden={view !== "ml"}><MercadoLibrePreviewPanel key={"ml-" + id} id={id} csrf={csrf} blocked={blocked || busy} /></div>
      <div hidden={view !== "identity"}>
      <p className="r-notice">
        Ecomm ID {id}.{" "}
        {environmentText(
          "Lectura de copias y decisiones internas de prueba. Las capturas y el CSV de este escenario son explícitamente sintéticos.",
          "Lectura de capturas existentes y revisión interna por variante.",
        )}{" "}
        Sin consultas en vivo, sincronización ni publicaciones. Compartir SKU o
        EAN no vincula variantes.
      </p>
      </div>
      {blocked && (
        <p role="alert">
          Guardá o descartá los cambios de ficha y resolvé la identidad antes de
          validar vínculos.
        </p>
      )}
      {error && (
        <p role="alert">
          {error} La última información visible requiere nueva consulta antes de
          decidir.
        </p>
      )}
      <button disabled={busy || loading} onClick={() => reload((v) => v + 1)}>
        {loading ? "Consultando capturas…" : "Volver a consultar canales"}
      </button>
      {loading && (
        <p role="status" className="r-notice">
          {data
            ? "Actualizando comparación. Se muestran los resultados anteriores hasta terminar la consulta; no se pueden validar vínculos mientras se actualiza."
            : "Consultando capturas internas de Mercado Libre y Tiendanube. No sincroniza ni publica productos."}
        </p>
      )}
      {!loading && !data && !error && (
        <p role="status">No hay resultados para mostrar. Volvé a consultar canales.</p>
      )}
      {data && (
        <details className="r-reference" hidden={view !== "identity"}>
          <summary>Identidad API utilizada en esta revisión · {id}</summary>
          <p>
            Captura Ecomm-App: {captureDate(data.identity.captured_at)}. Datos
            de esa copia, no consulta en vivo.
          </p>
          <dl>
            {[
              ["SKU", data.identity.sku],
              ["Barcode", data.identity.barcode],
              ["GTIN", data.identity.gtin_raw],
              ["Marca", data.identity.brand],
              [
                "Origen de marca",
                data.identity.brand_origin === "KIKI_EDITORIAL"
                  ? "Edición KIKI; no verificación oficial automática"
                  : data.identity.brand_origin === "API_CAPTURE"
                    ? "Captura API"
                    : "Sin dato",
              ],
              ["Presentación", data.identity.variant_description],
              [
                "Combo de variante",
                data.identity.is_combo === null
                  ? "Desconocido"
                  : data.identity.is_combo
                    ? "Sí"
                    : "No",
              ],
              [
                "Combo de producto",
                data.identity.parent_is_combo === null
                  ? "Desconocido"
                  : data.identity.parent_is_combo
                    ? "Sí"
                    : "No",
              ],
            ].map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v || "Sin dato"}</dd>
              </div>
            ))}
          </dl>
          <p>
            La cantidad comercial se declara expresamente al revisar; no se
            obtiene del SKU ni se presupone por la marca de combo.
          </p>
        </details>
      )}
      {data &&
        (["ml", "tn"] as const).map((channel) => {
          const c = data[channel];
          return (
            <section
              className="r-document"
              key={channel}
              data-channel-panel={channel}
              hidden={view !== channel}
            >
              <h4>{channel === "ml" ? "Mercado Libre" : "Tiendanube · CSV"}</h4>
              <strong>
                {c.comparison_state === "no_match"
                  ? "Sin coincidencia en esta captura"
                  : channelLabels[c.evidence_state]}
              </strong>
              <p>{!c.freshness.fresh && c.snapshot_available
                ? "Datos desactualizados · Actualizar captura antes de validar."
                : c.comparison_state === "no_match"
                  ? "Sin publicación verificada."
                  : c.note}</p>
              <details className="r-reference" data-channel-details={channel}>
                <summary>Ver detalles del canal ({c.candidates_total} coincidencias)</summary>
              <p>{c.note}</p>
              <p>
                Origen: {c.source} ·{" "}
                {channel === "ml" ? "Captura" : "Importación"}:{" "}
                {captureDate(c.snapshot_at)}.{" "}
                {c.snapshot_available
                  ? `Revisión de vigencia: ${c.freshness.review_after_hours} horas.`
                  : "No hay una captura disponible."}
              </p>
              {!c.freshness.fresh && c.snapshot_available && (
                <p role="note">
                  Captura vencida o sin fecha vigente. Los candidatos se
                  conservan para revisión; no se acredita publicación actual ni
                  se habilitan nuevas validaciones.
                </p>
              )}
              {channel === "tn" && (
                <p>
                  Un registro de CSV, incluso con vínculo revisado, no demuestra
                  que siga publicado actualmente. Este contrato no informa un
                  estado de publicación verificable.
                </p>
              )}
              <p>
                {c.candidates_total} filas candidatas en esta copia;{" "}
                {c.candidates.length} visibles.{" "}
                {c.legacy_decisions_ignored > 0 &&
                  `${c.legacy_decisions_ignored} decisiones históricas no se aplicaron automáticamente al catálogo API.`}
              </p>
              {!c.candidates_total && (
                <p>
                  {c.no_candidates_reason ||
                    "No hay candidatos en esta captura. No implica que no esté publicado."}
                </p>
              )}
              {c.candidates_truncated && (
                <p>
                  Se muestran hasta ocho candidatos iniciales y las filas con
                  decisiones previas. Hay más coincidencias: no se selecciona
                  ninguna automáticamente.
                </p>
              )}
              {c.candidates.map((row, index) => {
                const key = channel + row.id;
                return (
                  <article
                    className="r-fact"
                    key={row.id + row.token + index}
                    data-channel-row={row.id}
                  >
                    <details data-candidate-details>
                      <summary>{row.title || "Nombre no informado"} · {row.sku || "Sin SKU"} · {row.identity_verified ? "Identidad revisada" : "Por revisar"}</summary>
                    <h4>{row.title || "Nombre no informado"}</h4>
                    <p>
                      {channel === "ml"
                        ? `ID de publicación ML: ${row.id}`
                        : `Identificador URL del CSV: ${row.slug || "No informado"}`}
                      {channel === "tn" && (
                        <small>
                          {" "}
                          · Clave interna de fila CSV: {row.id}. No es un ID de
                          producto Tiendanube.
                        </small>
                      )}{" "}
                      · SKU: {row.sku || "Sin dato"} · Marca:{" "}
                      {row.brand || "Sin dato"}
                    </p>
                    <p>
                      Motivo de coincidencia:{" "}
                      {(row.match_reasons || [])
                        .map(
                          (reason) =>
                            ({
                              SKU_EXACT: "SKU exacto",
                              VALID_GTIN_EXACT: "EAN/GTIN válido coincidente",
                              TITLE_EXACT: "Nombre exacto",
                              BRAND_AND_TITLE_WORDS:
                                "Marca y palabras del nombre",
                              PREVIOUS_MANUAL_REVIEW: "Decisión manual previa",
                            })[reason] || reason,
                        )
                        .join(" · ") || "Consultar evidencia"}
                      . No confirma identidad.
                    </p>
                    {row.comparison && (
                      <dl>
                        {Object.entries(row.comparison).map(([key, value]) => (
                          <div key={key}>
                            <dt>
                              {{
                                ecomm_title: "Nombre Ecomm-App",
                                channel_title: "Nombre de canal",
                                ecomm_sku: "SKU Ecomm-App",
                                ecomm_brand: "Marca Ecomm-App",
                                ecomm_gtin: "GTIN Ecomm-App",
                                ecomm_presentation: "Presentación Ecomm-App",
                                ecomm_quantity: "Cantidad Ecomm-App",
                                channel_quantity: "Cantidad de canal",
                              }[key] || key}
                            </dt>
                            <dd>{value ?? "No informado"}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {!!row.discrepancies?.length && (
                      <p>Discrepancias: {row.discrepancies.join(" · ")}</p>
                    )}
                    <p>
                      Barcode: {row.barcode || "Sin dato"} · GTIN:{" "}
                      {row.gtin || "Sin dato"} · Estado en captura:{" "}
                      {row.listing_status || "No informado"}
                    </p>
                    <p>
                      {row.identity_verified
                        ? "Identidad revisada en esta captura"
                        : "Vínculo sin revisión vigente"}{" "}
                      · Revisión {row.revision} · Ecomm ID {id}
                    </p>
                    {!!row.blockers.length && (
                      <ul className="r-error">
                        {row.blockers.map((b) => (
                          <li key={b}>{b}</li>
                        ))}
                      </ul>
                    )}
                    <details>
                      <summary>
                        Revisar identidad y registrar decisión interna
                      </summary>
                      <p>
                        Contrastá los datos del canal con la ficha y la
                        presentación exacta. La cantidad debe verificarse
                        expresamente; «no combo» no demuestra por sí solo una
                        unidad.
                      </p>
                      <fieldset disabled={blocked || busy || loading || !!error}>
                        <legend>Datos contrastados</legend>
                        {Object.entries(labels).map(([k, label]) => (
                          <label className="r-check" key={k}>
                            <input
                              type="checkbox"
                              checked={(checks[key] || []).includes(k)}
                              onChange={(e) =>
                                setChecks({
                                  ...checks,
                                  [key]: e.target.checked
                                    ? [...(checks[key] || []), k]
                                    : (checks[key] || []).filter(
                                        (x) => x !== k,
                                      ),
                                })
                              }
                            />
                            {label}
                          </label>
                        ))}
                        <label>
                          Cantidad comercial verificada
                          <input
                            aria-label={`Cantidad ${key}`}
                            type="number"
                            min="1"
                            max="1000"
                            value={quantities[key] || ""}
                            onChange={(e) =>
                              setQuantities({
                                ...quantities,
                                [key]: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          Motivo de revisión
                          <textarea
                            aria-label={`Motivo ${key}`}
                            minLength={20}
                            maxLength={600}
                            value={notes[key] || ""}
                            onChange={(e) =>
                              setNotes({ ...notes, [key]: e.target.value })
                            }
                          />
                        </label>
                        <button
                          disabled={
                            !row.can_review ||
                            (checks[key] || []).length !== 6 ||
                            Number(quantities[key]) < 1 ||
                            (notes[key] || "").trim().length < 20
                          }
                          onClick={() => void review(channel, row, "APPROVED")}
                        >
                          Validar vínculo interno
                        </button>
                        <button
                          disabled={
                            row.review_state !== "APPROVED" ||
                            (notes[key] || "").trim().length < 20 ||
                            !quantities[key]
                          }
                          onClick={() => void review(channel, row, "REVOKED")}
                        >
                          Revocar vínculo interno
                        </button>
                      </fieldset>
                    </details>
                    <details>
                      <summary>
                        Historial de vinculación ({row.history.length})
                      </summary>
                      {row.history.map((h, i) => (
                        <div key={i}>
                          <p>
                            {captureDate(h.at)} · {h.actor} · {h.decision} ·
                            Ecomm ID {h.ecomm_id}
                          </p>
                          <p>
                            Cantidad declarada por operador:{" "}
                            {h.quantity_commercial}. {h.reason}
                          </p>
                        </div>
                      ))}
                    </details>
                    </details>
                  </article>
                );
              })}
              </details>
            </section>
          );
        })}
      </div>
    </section>
  );
}
