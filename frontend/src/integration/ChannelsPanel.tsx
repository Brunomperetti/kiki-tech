import { environmentText } from "./runtime";
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
}: {
  id: string;
  csrf: string;
  blocked: boolean;
  onBusy: (v: boolean) => void;
  onReviewed: () => void;
}) {
  const [data, setData] = useState<ChannelReport>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, reload] = useState(0);
  const [notes, setNotes] = useState<Record<string, string>>({}),
    [quantities, setQuantities] = useState<Record<string, string>>({}),
    [checks, setChecks] = useState<Record<string, string[]>>({});
  useEffect(() => {
    onBusy(busy);
    return () => onBusy(false);
  }, [busy, onBusy]);
  useEffect(() => {
    if (isAuxiliaryPilot(id)) return;
    const c = new AbortController();
    setData(undefined);
    setError("");
    loadChannels(id, c.signal)
      .then((v) => {
        if (!c.signal.aborted) setData(v);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
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
      <h3>Mercado Libre y Tiendanube</h3>
      <p className="r-notice">
        Ecomm ID {id}.{" "}
        {environmentText(
          "Lectura de copias y decisiones internas de prueba. Las capturas y el CSV de este escenario son explícitamente sintéticos.",
          "Lectura de capturas existentes y revisión interna por variante.",
        )}{" "}
        Sin consultas en vivo, sincronización ni publicaciones. Compartir SKU o
        EAN no vincula variantes.
      </p>
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
      <button disabled={busy} onClick={() => reload((v) => v + 1)}>
        Volver a consultar canales
      </button>
      {data && (
        <details className="r-reference">
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
            >
              <h4>{channel === "ml" ? "Mercado Libre" : "Tiendanube · CSV"}</h4>
              <strong>{channelLabels[c.evidence_state]}</strong>
              <p>{c.note}</p>
              <p>
                Origen: {c.source} ·{" "}
                {channel === "ml" ? "Captura" : "Importación"}:{" "}
                {captureDate(c.snapshot_at)}.{" "}
                {c.snapshot_available
                  ? `Revisión de vigencia: ${c.freshness.review_after_hours} horas.`
                  : "No hay una captura disponible."}
              </p>
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
              {c.candidates.map((row) => {
                const key = channel + row.id;
                return (
                  <article
                    className="r-fact"
                    key={row.id}
                    data-channel-row={row.id}
                  >
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
                      Barcode: {row.barcode || "Sin dato"} · GTIN:{" "}
                      {row.gtin || "Sin dato"} · Estado en captura:{" "}
                      {row.listing_status || "No informado"}
                    </p>
                    <p>
                      {row.identity_verified
                        ? "Vínculo con revisión vigente"
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
                      <fieldset disabled={blocked || busy || !!error}>
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
                  </article>
                );
              })}
            </section>
          );
        })}
    </section>
  );
}
