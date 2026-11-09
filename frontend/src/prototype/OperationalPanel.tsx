import { useEffect, useState } from "react";
import {
  change,
  isConfirmed,
  channelDetail,
  channelState,
  editorialState,
  requirements,
  snapshot,
  type Item,
  type Editorial,
} from "./operations-model";
export function OperationalPanel({
  product: p,
  tab,
  onChange,
  onDirty,
}: {
  product: Item;
  tab: string;
  onChange: (p: Item) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const [draft, setDraft] = useState<Editorial>(snapshot(p));
  const [proposal, setProposal] = useState(p.ai?.text || "");
  const [reason, setReason] = useState("");
  const [confirmedIdentity, setConfirmedIdentity] = useState(false);
  const [channel, setChannel] = useState<"ml" | "tn">("ml");
  const [confirmation, setConfirmation] = useState<{
    title: string;
    run: () => void;
  } | null>(null);
  const [message, setMessage] = useState("");
  const [version, setVersion] = useState<number | null>(null);
  const dirty =
    JSON.stringify(draft) !== JSON.stringify(snapshot(p)) ||
    (tab === "IA" && proposal !== (p.ai?.text || "")) ||
    reason.trim() !== "" ||
    confirmedIdentity;
  useEffect(() => {
    onDirty(dirty);
  }, [dirty, onDirty]);
  useEffect(() => {
    setDraft(snapshot(p));
    setProposal(p.ai?.text || "");
    setConfirmation(null);
  }, [p.id, p.history.length]);
  useEffect(() => {
    setConfirmation(null);
    setReason("");
    setConfirmedIdentity(false);
    setVersion(null);
  }, [tab]);
  useEffect(() => {
    setConfirmation(null);
  }, [draft, reason, channel, confirmedIdentity, proposal]);
  function commit(patch: Partial<Item>, action: string, why?: string) {
    onChange(change(p, patch, action, why));
    setMessage(`${action}. Resultado de demostración, sin escritura externa.`);
    setConfirmation(null);
    setReason("");
    setConfirmedIdentity(false);
  }
  function field<K extends keyof Editorial>(key: K, value: Editorial[K]) {
    setDraft((old) => ({ ...old, [key]: value }));
  }
  const missing = requirements(p);
  const explain = (
    <p className="o-safety">
      Variante {p.id} · datos sintéticos · cambios en esta sesión, sin
      publicación externa.
    </p>
  );
  return (
    <div className="o-panel">
      {explain}
      {tab === "Ficha" && (
        <>
          <h3>Editar ficha de producto</h3>
          <p>Completá los datos y compará antes de guardar un borrador.</p>
          <div className="o-form">
            <label>
              Nombre
              <input
                value={draft.name}
                onChange={(e) => field("name", e.target.value)}
              />
            </label>
            <label>
              Descripción
              <textarea
                aria-label="Descripción"
                value={draft.description}
                onChange={(e) => field("description", e.target.value)}
              />
            </label>
            <label>
              Características
              <textarea
                aria-label="Características"
                value={draft.features}
                onChange={(e) => field("features", e.target.value)}
              />
            </label>
            <div className="o-grid">
              <label>
                Precio de lista
                <input
                  type="number"
                  min="0"
                  value={draft.price}
                  onChange={(e) => field("price", Number(e.target.value))}
                />
              </label>
              <label>
                Stock disponible
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={draft.stock}
                  onChange={(e) => field("stock", Number(e.target.value))}
                />
              </label>
            </div>
            <label>
              Imagen de muestra
              <select
                value={draft.image}
                onChange={(e) => field("image", e.target.value)}
              >
                <option>Vista frontal de muestra</option>
                <option>Vista lateral de muestra</option>
                <option value="">Sin imagen</option>
              </select>
            </label>
            <div
              className={`o-image ${p.color}`}
              role="img"
              aria-label={draft.alt || "Sin descripción de imagen"}
            >
              {draft.image ? `${p.initials} · ${draft.image}` : "Sin imagen"}
            </div>
            <label>
              Texto alternativo de imagen
              <input
                value={draft.alt}
                onChange={(e) => field("alt", e.target.value)}
              />
            </label>
            <label>
              Título para buscadores
              <input
                value={draft.seo}
                onChange={(e) => field("seo", e.target.value)}
              />
            </label>
          </div>
          <details className="o-comparison" open={dirty}>
            <summary>Comparar versión guardada y borrador</summary>
            <table>
              <thead>
                <tr>
                  <th>Campo</th>
                  <th>Guardado</th>
                  <th>Borrador</th>
                </tr>
              </thead>
              <tbody>
                {(Object.keys(draft) as (keyof Editorial)[])
                  .filter((k) => draft[k] !== p[k])
                  .map((k) => (
                    <tr key={k}>
                      <th>
                        {
                          {
                            name: "Nombre",
                            description: "Descripción",
                            features: "Características",
                            image: "Imagen",
                            alt: "Texto alternativo",
                            seo: "Título SEO",
                            price: "Precio",
                            stock: "Stock",
                          }[k]
                        }
                      </th>
                      <td>{p[k] || "Vacío"}</td>
                      <td>{draft[k] || "Vacío"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            {!dirty && <p>No hay diferencias.</p>}
          </details>
          <div className="o-actions">
            <button
              disabled={!dirty}
              onClick={() => {
                setDraft(snapshot(p));
                setProposal(p.ai?.text || "");
              }}
            >
              Revertir edición
            </button>
            <button
              className="d-primary"
              disabled={
                !dirty ||
                !draft.name.trim() ||
                draft.price < 0 ||
                draft.stock < 0 ||
                !Number.isInteger(draft.stock)
              }
              onClick={() =>
                commit(
                  {
                    ...draft,
                    status: "Pendiente",
                    prepared: { ml: false, tn: false },
                  },
                  "Borrador guardado",
                )
              }
            >
              Guardar borrador
            </button>
          </div>
          {dirty && <p className="o-warning">Tenés cambios sin guardar.</p>}
        </>
      )}
      {tab === "Evidencias" && (
        <>
          <h3>Revisar evidencia y resolver identidad</h3>
          <p>
            La publicación se confirma por canal con evidencia vigente. Un SKU
            coincidente o una decisión de vinculación no sustituyen esa
            evidencia.
          </p>
          {(["ml", "tn"] as const).map((c) => (
            <article className="d-evidence" key={c}>
              <h4>{c === "ml" ? "Mercado Libre" : "Tiendanube"}</h4>
              {!isConfirmed(p, c) && <p>Publicación no confirmada.</p>}
              <p>
                <strong>{channelState(p, c)}</strong> · {channelDetail(p, c)}
              </p>
              <p>
                Vigencia:{" "}
                {p.evidence[c].freshness === "current"
                  ? "información vigente de muestra"
                  : p.evidence[c].freshness === "stale"
                    ? "información desactualizada"
                    : "información desconocida"}
              </p>
              {p.evidence[c].publications
                .filter(
                  (pub, index, list) =>
                    list.findIndex((other) => other.id === pub.id) === index,
                )
                .map((pub, i) => (
                  <p key={i}>
                    Referencia: {pub.id} · {pub.proof} · {pub.capturedAt} (hora
                    argentina)
                  </p>
                ))}
              <p>Decisión de vinculación: {p.decisions[c].state}</p>
              <p>
                Fuente: datos sintéticos de{" "}
                {c === "ml" ? "Mercado Libre" : "Tiendanube"}. La vigencia y las
                fechas se muestran por referencia.
              </p>
              <p>
                Variante Ecomm: {p.id}.{" "}
                {p.sku === "ALM-NAT"
                  ? "SKU compartido con otra variante: verificar peso y presentación."
                  : "Comparar marca, peso y presentación."}
              </p>
              {p.decisions[c].reason && (
                <p>Fundamento: {p.decisions[c].reason}</p>
              )}
            </article>
          ))}
          <label>
            Canal de la decisión
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value as "ml" | "tn")}
            >
              <option value="ml">Mercado Libre</option>
              <option value="tn">Tiendanube</option>
            </select>
          </label>
          <label>
            Fundamento de la decisión
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describí qué comparaste y por qué coincide o no coincide"
            />
          </label>
          <label className="o-check">
            <input
              type="checkbox"
              checked={confirmedIdentity}
              onChange={(e) => setConfirmedIdentity(e.target.checked)}
            />
            Comparé Ecomm ID, presentación y atributos; resolví la ambigüedad de
            esta muestra.
          </label>
          <div className="o-actions">
            {(["Rechazada", "Aceptada"] as const).map((state) => (
              <button
                key={state}
                disabled={
                  reason.trim().length < 12 ||
                  (state === "Aceptada" && !confirmedIdentity)
                }
                onClick={() =>
                  setConfirmation({
                    title: `${state === "Aceptada" ? "Aceptar" : "Rechazar"} candidato de ${channel === "ml" ? "Mercado Libre" : "Tiendanube"} para ${p.id}`,
                    run: () =>
                      commit(
                        {
                          conflict: false,
                          status: "Pendiente",
                          decisions: {
                            ...p.decisions,
                            [channel]: { state, reason: reason.trim() },
                          },
                        },
                        `Evidencia ${state.toLowerCase()}`,
                        reason.trim(),
                      ),
                  })
                }
              >
                {state === "Aceptada"
                  ? "Aceptar candidato"
                  : "Rechazar candidato"}
              </button>
            ))}
          </div>
          <p className="o-warning">
            Aceptar resuelve la revisión interna de esta muestra; no confirma ni
            crea una publicación externa.
          </p>
        </>
      )}
      {tab === "IA" && (
        <>
          <h3>Propuesta editorial asistida</h3>
          <p>
            Procedencia: plantilla local KIKI demo. No se ejecuta ningún modelo.
          </p>
          <button
            disabled={dirty}
            onClick={() => {
              const text = `${p.name}. ${p.brand}: propuesta editorial de demostración. Verificar materiales y medidas con un manual antes de usar.`;
              commit(
                { ai: { text, state: "Pendiente" } },
                "Propuesta IA simulada generada",
              );
            }}
          >
            Generar propuesta simulada
          </button>
          {p.ai && (
            <>
              <div className="o-comparison">
                <h4>Original</h4>
                <p>{p.description}</p>
                <label>
                  Propuesta editable
                  <textarea
                    aria-label="Propuesta editable"
                    value={proposal}
                    onChange={(e) => setProposal(e.target.value)}
                  />
                </label>
                <p>Estado: {p.ai.state}</p>
              </div>
              <aside className="o-warning">
                Información no verificada. Referencia futura: manual técnico
                DEMO-MANUAL-{p.id}, pendiente de adjuntar y validar. Esta
                referencia es ilustrativa y no es una fuente consultada.
              </aside>
              <div className="o-actions">
                <button
                  disabled={p.ai.state === "Descartada"}
                  onClick={() =>
                    commit(
                      { ai: { text: proposal, state: "Descartada" } },
                      "Propuesta IA descartada",
                    )
                  }
                >
                  Descartar propuesta
                </button>
                <button
                  disabled={!proposal.trim() || p.ai.state === "Aceptada"}
                  onClick={() =>
                    setConfirmation({
                      title: `Aplicar propuesta al borrador ${p.id}`,
                      run: () =>
                        commit(
                          {
                            description: proposal,
                            ai: { text: proposal, state: "Aceptada" },
                            status: "Pendiente",
                            prepared: { ml: false, tn: false },
                          },
                          "Propuesta IA aceptada",
                          "Revisión manual de texto simulado; información técnica aún no verificada",
                        ),
                    })
                  }
                >
                  Aceptar propuesta
                </button>
              </div>
            </>
          )}
        </>
      )}
      {tab === "Canales" && (
        <>
          <h3>Preparación por canal</h3>
          <p>
            Ficha editorial: {editorialState(p)}. Este estado es independiente
            de las publicaciones.
          </p>
          <p>
            Ecomm-App conserva la identidad {p.id}; las tareas de cada canal se
            revisan por separado.
          </p>
          <article className="d-evidence">
            <h4>Ecomm-App · fuente central</h4>
            <p>
              SKU {p.sku} · Presentación {p.presentation} · Ecomm ID {p.id}.
              Versión de demostración; no sincronizada.
            </p>
          </article>
          {(["ml", "tn"] as const).map((c) => (
            <article className="d-evidence" key={c}>
              <h4>{c === "ml" ? "Mercado Libre" : "Tiendanube"}</h4>
              {!isConfirmed(p, c) && <p>Publicación no confirmada.</p>}
              <p>
                <strong>{channelState(p, c)}</strong> · {channelDetail(p, c)}
              </p>
              <p>
                Vigencia:{" "}
                {p.evidence[c].freshness === "current"
                  ? "información vigente de muestra"
                  : p.evidence[c].freshness === "stale"
                    ? "información desactualizada"
                    : "información desconocida"}
              </p>
              {p.evidence[c].publications
                .filter(
                  (pub, index, list) =>
                    list.findIndex((other) => other.id === pub.id) === index,
                )
                .map((pub, i) => (
                  <p key={i}>
                    Referencia: {pub.id} · {pub.proof} · {pub.capturedAt} (hora
                    argentina)
                  </p>
                ))}
              <p>
                <strong>{channelState(p, c)}</strong>
                {channelState(p, c) === "Listo para publicar"
                  ? " · Preparación interna, sujeta a revisar vigencia y evidencia. No se publicó."
                  : ""}
              </p>
              <p>
                Publicación:{" "}
                {isConfirmed(p, c)
                  ? "Verificada en fixture sintético"
                  : "Publicación no confirmada."}
              </p>
              <p>
                Candidato: {p.decisions[c].state}. Preparación:{" "}
                {p.prepared[c] ? "Preparada internamente" : "Sin preparar"}.
              </p>
              <ul>
                {[
                  "Nombre",
                  "Descripción",
                  "Imagen y texto alternativo",
                  "Precio válido",
                  "Identidad sin conflicto",
                  ...(c === "tn" ? ["Título para buscadores"] : []),
                ].map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {missing.length || (c === "tn" && !p.seo.trim()) ? (
                <p className="o-warning">
                  Falta resolver:{" "}
                  {[
                    ...missing,
                    ...(c === "tn" && !p.seo.trim()
                      ? ["Título para buscadores"]
                      : []),
                  ].join(", ")}
                </p>
              ) : (
                <p>Requisitos internos de muestra completos.</p>
              )}
              {p.evidence[c].freshness !== "current" && (
                <p className="o-warning">
                  Antes de preparar este canal, revisá una copia vigente de la
                  evidencia. No se consulta ningún servicio en esta
                  demostración.
                </p>
              )}
              <button
                disabled={
                  !!missing.length ||
                  p.evidence[c].freshness !== "current" ||
                  (c === "tn" && !p.seo.trim()) ||
                  p.prepared[c]
                }
                onClick={() =>
                  setConfirmation({
                    title: `Preparar ${p.id} para ${c === "ml" ? "Mercado Libre" : "Tiendanube"}`,
                    run: () =>
                      commit(
                        {
                          prepared: { ...p.prepared, [c]: true },
                          status: "Preparada",
                        },
                        `Ficha preparada para ${c === "ml" ? "Mercado Libre" : "Tiendanube"}`,
                      ),
                  })
                }
              >
                {p.prepared[c]
                  ? "Preparada internamente"
                  : `Preparar para ${c === "ml" ? "ML" : "TN"}`}
              </button>
            </article>
          ))}
        </>
      )}
      {tab === "Historial" && (
        <>
          <h3>Versiones y decisiones</h3>
          <p>Fechas en hora argentina. Responsable simulado: Operador demo.</p>
          <ol className="d-timeline">
            {p.history.map((v, i) => (
              <li key={i}>
                <strong>{v.action}</strong>
                <p>
                  {v.date} · {v.actor}
                </p>
                <p>{v.reason}</p>
                <button onClick={() => setVersion(i)}>
                  Consultar versión {i + 1}
                </button>
              </li>
            ))}
          </ol>
          {version !== null && (
            <section className="o-comparison" aria-label="Versión anterior">
              <h4>Versión {version + 1} · solo consulta</h4>
              <p>El estado actual no se reemplaza.</p>
              <dl>
                {Object.entries(p.history[version].snapshot).map(([k, v]) => (
                  <div key={k}>
                    <dt>
                      {
                        (
                          {
                            name: "Nombre",
                            description: "Descripción",
                            features: "Características",
                            image: "Imagen",
                            alt: "Texto alternativo",
                            seo: "Título para buscadores",
                            price: "Precio",
                            stock: "Stock",
                          } as Record<string, string>
                        )[k]
                      }
                    </dt>
                    <dd>{v || "Vacío"}</dd>
                  </div>
                ))}
              </dl>
              <button onClick={() => setVersion(null)}>Cerrar versión</button>
            </section>
          )}
        </>
      )}
      {tab === "Ficha" && (
        <section className="o-prepare">
          <h4>Preparación interna de la ficha</h4>
          <p>
            {missing.length
              ? `Falta resolver: ${missing.join(", ")}`
              : "Datos de muestra completos. Revisá antes de aprobar."}
          </p>
          <button
            className="d-primary"
            disabled={dirty || p.status === "Preparada" || !!missing.length}
            onClick={() =>
              setConfirmation({
                title: `Preparar la ficha ${p.id}`,
                run: () => commit({ status: "Preparada" }, "Ficha preparada"),
              })
            }
          >
            {p.status === "Preparada" ? "Ficha preparada" : "Preparar ficha"}
          </button>
        </section>
      )}
      {confirmation && (
        <div className="o-confirm" role="alert">
          <h4>{confirmation.title}</h4>
          <p>
            Solo se actualizará esta demostración. No se publica ni escribe en
            canales.
          </p>
          <div className="o-actions">
            <button onClick={() => setConfirmation(null)}>Cancelar</button>
            <button className="d-primary" onClick={confirmation.run}>
              Confirmar decisión
            </button>
          </div>
        </div>
      )}
      <p role="status" className="o-result">
        {message}
      </p>
    </div>
  );
}
