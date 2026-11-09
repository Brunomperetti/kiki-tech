import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { KikiIcon as Icon } from "../components/KikiIcon";
import { products, type Status } from "./data";
import "./dashboard.css";
const tabs = ["Ficha", "Evidencias", "IA", "Canales", "Historial"];
const legacy = [
  ["/pilot", "Catálogo por API"],
  ["/workspace", "Backoffice de productos"],
  ["/queue", "Cola de mejoras"],
  ["/propuestas-ia", "Propuestas IA"],
  ["/cases", "Casos"],
  ["/channels", "Canales"],
  ["/products", "Productos"],
  ["/work", "Tareas"],
  ["/work/details", "Detalle de tareas"],
  ["/readiness", "Preparación"],
  ["/enrichment", "Enriquecimiento"],
  ["/external-research", "Investigación"],
  ["/prepublication", "Prepublicación"],
  ["/images", "Imágenes"],
  ["/metadata", "Atributos"],
  ["/review", "Revisión"],
  ["/duplicate-review", "Duplicados"],
  ["/tiendanube", "Tiendanube"],
  ["/imports", "Importaciones"],
  ["/guia", "Guía"],
];
const money = (n: number) =>
  new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
    maximumFractionDigits: 0,
  }).format(n);
function Pill({ value }: { value: string }) {
  return (
    <span
      className={`d-pill ${value === "Preparada" || value === "Verificada" ? "good" : value === "Conflicto" ? "bad" : "warm"}`}
    >
      {value === "Verificada" ? "✓ " : value === "Conflicto" ? "! " : ""}
      {value}
    </span>
  );
}
export function PrototypeDashboard() {
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState(products);
  const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);
  const originRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const selected = rows.find((p) => p.id === params.get("product"));
  const tab = tabs.includes(params.get("tab") || "")
    ? params.get("tab")!
    : "Ficha";
  const q = params.get("q") || "",
    status = params.get("status") || "",
    brand = params.get("brand") || "",
    channel = params.get("channel") || "";
  function update(values: Record<string, string>) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      Object.entries(values).forEach(([k, v]) =>
        v ? next.set(k, v) : next.delete(k),
      );
      return next;
    });
  }
  function close() {
    update({ product: "", tab: "" });
    setConfirm(false);
    originRef.current?.focus();
  }
  useEffect(() => {
    if (selected) {
      originRef.current = document.activeElement as HTMLElement;
      closeRef.current?.focus();
    }
  }, [selected?.id]);
  useEffect(() => {
    setConfirm(false);
  }, [selected?.id, tab]);
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key === "Tab") {
        const elements = panelRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),a,input,[tabindex="0"]',
        );
        if (!elements?.length) return;
        const first = elements[0],
          last = elements[elements.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = old;
    };
  }, [selected?.id, confirm]);
  const filtered = rows.filter(
    (p) =>
      [p.name, p.sku, p.brand, p.id]
        .join(" ")
        .toLocaleLowerCase()
        .includes(q.toLocaleLowerCase()) &&
      (!status || p.status === status) &&
      (!brand || p.brand === brand) &&
      (!channel || (channel === "ml" ? p.ml : p.tn) === "Verificada"),
  );
  const count = (s: Status) => rows.filter((p) => p.status === s).length;
  function approve() {
    if (!selected) return;
    setRows((old) =>
      old.map((p) =>
        p.id === selected.id ? { ...p, status: "Preparada" } : p,
      ),
    );
    setConfirm(false);
    setNotice(`Ficha ${selected.id} preparada en esta demostración.`);
  }
  return (
    <div className="d-app">
      <aside className="d-sidebar">
        <Link to="/" className="d-brand">
          <span>k.</span>
          <strong>
            KIKI<span>TECH 2.0</span>
          </strong>
        </Link>
        <div className="d-workspace">
          <span className="d-avatar">K</span>
          <div>
            KIKI Market<small>Espacio de trabajo</small>
          </div>
          <span>⌄</span>
        </div>
        <small className="d-nav-label">GESTIÓN DEL CATÁLOGO</small>
        <nav aria-label="Navegación del prototipo">
          <Link className="d-active" to="/">
            <Icon name="chart" /> Resumen general
          </Link>
          <button
            onClick={() => document.getElementById("catalog-search")?.focus()}
          >
            <Icon name="box" /> Catálogo central <span>8</span>
          </button>
          <button onClick={() => update({ status: "Pendiente" })}>
            <Icon name="clock" /> Pendientes <span>{count("Pendiente")}</span>
          </button>
          <button onClick={() => update({ status: "Conflicto" })}>
            <Icon name="alert" /> Conflictos <span>{count("Conflicto")}</span>
          </button>
          <button onClick={() => update({ status: "Preparada" })}>
            <Icon name="check" /> Fichas preparadas
          </button>
        </nav>
        <details className="d-legacy">
          <summary>Herramientas anteriores</summary>
          <p>
            Rutas originales conservadas. Las solicitudes están bloqueadas en
            este prototipo.
          </p>
          {legacy.map(([url, label]) => (
            <Link key={url} to={url}>
              {label}
            </Link>
          ))}
        </details>
        <div className="d-sidebar-bottom">
          <Icon name="shield" />
          <strong>Tu catálogo, bajo control</strong>
          <p>Vos revisás y decidís cada cambio.</p>
          <span>Etapa 1 · Prototipo visual</span>
        </div>
      </aside>
      <div className="d-body">
        <header className="d-topbar">
          <span>
            Espacio de trabajo <b>/</b> <strong>Resumen general</strong>
          </span>
          <div>
            <span className="d-demo-dot" /> Datos de demostración{" "}
            <span className="d-avatar">KM</span>
          </div>
        </header>
        <main className="d-main">
          <div className="d-heading">
            <div>
              <div className="d-eyebrow">UNA VISIÓN CLARA DE TU NEGOCIO</div>
              <h1>
                Tu catálogo, en un solo lugar<span>.</span>
              </h1>
              <p>
                Encontrá qué necesita atención y prepará tus productos para cada
                canal.
              </p>
            </div>
            <button
              className="d-primary"
              onClick={() => update({ status: "Pendiente" })}
            >
              Revisar pendientes <Icon name="arrow-right" size={17} />
            </button>
          </div>
          <div className="d-demo">
            <Icon name="shield" size={17} />
            <span>
              <strong>Modo demostración.</strong> Productos ficticios, sin
              conexiones ni cambios en tus sistemas.
            </span>
            <span className="d-demo-tag">ENTORNO AISLADO</span>
          </div>
          <section className="d-metrics" aria-label="Indicadores del catálogo">
            {[
              [
                "Catálogo Ecomm-App",
                rows.length,
                "Variantes · fuente central",
                "box",
                "",
              ],
              [
                "Mercado Libre",
                rows.filter((p) => p.ml === "Verificada").length,
                "Publicaciones verificadas",
                "store",
                "ml",
              ],
              [
                "Tiendanube",
                rows.filter((p) => p.tn === "Verificada").length,
                "Publicaciones verificadas",
                "store",
                "tn",
              ],
              [
                "Pendientes",
                count("Pendiente"),
                "Para completar o revisar",
                "clock",
                "Pendiente",
              ],
              [
                "Conflictos",
                count("Conflicto"),
                "Necesitan tu atención",
                "alert",
                "Conflicto",
              ],
              [
                "Fichas preparadas",
                count("Preparada"),
                "Listas para revisión interna",
                "check",
                "Preparada",
              ],
            ].map(([label, note, sub, icon, filter]) => (
              <button
                key={label}
                className={`d-metric ${filter === "Conflicto" ? "d-metric-conflict" : ""}`}
                onClick={() =>
                  update({
                    status: ["ml", "tn"].includes(String(filter))
                      ? ""
                      : String(filter),
                    channel: ["ml", "tn"].includes(String(filter))
                      ? String(filter)
                      : "",
                  })
                }
              >
                <span>
                  {label}
                  <Icon name={icon as "box"} size={17} />
                </span>
                <strong>{note}</strong>
                <small>{sub}</small>
              </button>
            ))}
          </section>
          <section className="d-insight">
            <span className="d-insight-icon">
              <Icon name="sparkles" />
            </span>
            <div>
              <strong>Un buen catálogo empieza por una ficha completa</strong>
              <p>
                Hay {count("Pendiente")} productos para revisar. Resolvé sus
                datos antes de prepararlos para los canales.
              </p>
            </div>
            <button onClick={() => update({ status: "Pendiente" })}>
              Ver productos <Icon name="arrow-right" size={15} />
            </button>
          </section>
          <section className="d-catalog">
            <div className="d-section-head">
              <div>
                <h2>
                  Catálogo de productos <span>{rows.length} variantes</span>
                </h2>
                <p>
                  Ecomm-App es el origen de cada variante. Los canales aportan
                  evidencia.
                </p>
              </div>
              <span className="d-snapshot">
                <span /> Copia sintética · sin sincronización
              </span>
            </div>
            <div className="d-filters">
              <label className="d-search">
                <Icon name="search" size={19} />
                <input
                  id="catalog-search"
                  aria-label="Buscar productos"
                  placeholder="Buscar por SKU, nombre, marca o Ecomm ID…"
                  value={q}
                  onChange={(e) => update({ q: e.target.value })}
                />
                {q && (
                  <button
                    aria-label="Borrar búsqueda"
                    onClick={() => update({ q: "" })}
                  >
                    ×
                  </button>
                )}
              </label>
              <select
                aria-label="Estado"
                value={status}
                onChange={(e) => update({ status: e.target.value })}
              >
                <option value="">Todos los estados</option>
                {["Pendiente", "Conflicto", "Preparada"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <select
                aria-label="Marca"
                value={brand}
                onChange={(e) => update({ brand: e.target.value })}
              >
                <option value="">Todas las marcas</option>
                {["Monte", "Nexo", "Casa Sur"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
              <select
                aria-label="Canal verificado"
                value={channel}
                onChange={(e) => update({ channel: e.target.value })}
              >
                <option value="">Todos los canales</option>
                <option value="ml">ML verificado</option>
                <option value="tn">TN verificado</option>
              </select>
            </div>
            {(q || status || brand || channel) && (
              <div className="d-active-filters">
                Filtros activos{" "}
                <button
                  onClick={() =>
                    update({ q: "", status: "", brand: "", channel: "" })
                  }
                >
                  Limpiar filtros ×
                </button>
              </div>
            )}
            <div className="d-table-scroll">
              <table className="d-table">
                <thead>
                  <tr>
                    <th>Producto / Ecomm ID</th>
                    <th>SKU / Marca</th>
                    <th>Precio / Stock</th>
                    <th>Mercado Libre</th>
                    <th>Tiendanube</th>
                    <th>Estado de ficha</th>
                    <th>
                      <span className="d-sr">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p) => (
                    <tr
                      key={p.id}
                      className={selected?.id === p.id ? "d-selected" : ""}
                    >
                      <td>
                        <button
                          className="d-product"
                          onClick={() =>
                            update({ product: p.id, tab: "Ficha" })
                          }
                        >
                          <span className={`d-thumbnail ${p.color}`}>
                            {p.initials}
                          </span>
                          <span>
                            <strong>{p.name}</strong>
                            <small>{p.id}</small>
                          </span>
                        </button>
                      </td>
                      <td>
                        <strong className="d-sku">{p.sku}</strong>
                        <small>{p.brand}</small>
                      </td>
                      <td>
                        <strong>{money(p.price)}</strong>
                        <small>{p.stock} disponibles</small>
                      </td>
                      <td>
                        <Pill value={p.ml} />
                      </td>
                      <td>
                        <Pill value={p.tn} />
                      </td>
                      <td>
                        <Pill value={p.status} />
                      </td>
                      <td>
                        <button
                          className="d-open"
                          aria-label={`Abrir ${p.id}`}
                          onClick={() =>
                            update({ product: p.id, tab: "Ficha" })
                          }
                        >
                          <Icon name="arrow-right" size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!filtered.length && (
              <div className="d-empty">
                <Icon name="search" size={30} />
                <h3>No encontramos productos</h3>
                <p>Probá otro nombre o quitá los filtros.</p>
                <button
                  onClick={() =>
                    update({ q: "", status: "", brand: "", channel: "" })
                  }
                >
                  Ver todo el catálogo
                </button>
              </div>
            )}
            <footer className="d-table-footer">
              <span>
                Mostrando {filtered.length} de {rows.length} variantes
              </span>
              <span>Identidad por Ecomm ID · nunca por SKU</span>
            </footer>
          </section>
          <p className="d-footnote">
            <Icon name="help" size={15} /> Un SKU coincidente es una pista. Solo
            una evidencia verificada confirma la publicación.
          </p>
          <p role="status" className="d-notice">
            {notice}
          </p>
        </main>
      </div>
      {selected && (
        <>
          <div className="d-backdrop" onClick={close} />
          <section
            className="d-drawer"
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label={`Ficha ${selected.id}`}
          >
            <div className="d-drawer-top">
              <span>DETALLE DEL PRODUCTO</span>
              <button ref={closeRef} onClick={close} aria-label="Cerrar ficha">
                ×
              </button>
            </div>
            <div className="d-drawer-title">
              <span className={`d-thumbnail ${selected.color}`}>
                {selected.initials}
              </span>
              <div>
                <h2>{selected.name}</h2>
                <p>
                  {selected.brand} · {selected.id}
                </p>
              </div>
            </div>
            <div className="d-drawer-status">
              <Pill value={selected.status} />
              <span>Catálogo central Ecomm-App</span>
            </div>
            <div
              className="d-tabs"
              role="tablist"
              aria-label="Secciones de ficha"
              onKeyDown={(e) => {
                if (
                  ["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)
                ) {
                  e.preventDefault();
                  const i = tabs.indexOf(tab);
                  const next =
                    e.key === "Home"
                      ? 0
                      : e.key === "End"
                        ? tabs.length - 1
                        : (i +
                            (e.key === "ArrowRight" ? 1 : -1) +
                            tabs.length) %
                          tabs.length;
                  update({ tab: tabs[next] });
                  document.getElementById(`tab-${tabs[next]}`)?.focus();
                }
              }}
            >
              {tabs.map((t) => (
                <button
                  key={t}
                  role="tab"
                  tabIndex={tab === t ? 0 : -1}
                  id={`tab-${t}`}
                  aria-controls="product-tabpanel"
                  aria-selected={tab === t}
                  onClick={() => update({ tab: t })}
                >
                  {t}
                </button>
              ))}
            </div>
            <div
              className="d-tab-content"
              id="product-tabpanel"
              role="tabpanel"
              aria-labelledby={`tab-${tab}`}
            >
              {tab === "Ficha" && (
                <>
                  <h3>Información de la variante</h3>
                  <p>
                    La identidad se conserva aunque cambie o se repita el SKU.
                  </p>
                  <dl className="d-fields">
                    <div>
                      <dt>Ecomm ID de variante</dt>
                      <dd>{selected.id}</dd>
                    </div>
                    <div>
                      <dt>SKU</dt>
                      <dd>{selected.sku}</dd>
                    </div>
                    <div>
                      <dt>Marca</dt>
                      <dd>{selected.brand}</dd>
                    </div>
                    <div>
                      <dt>Categoría</dt>
                      <dd>{selected.category}</dd>
                    </div>
                    <div>
                      <dt>Precio de lista</dt>
                      <dd>{money(selected.price)}</dd>
                    </div>
                    <div>
                      <dt>Stock de muestra</dt>
                      <dd>{selected.stock} unidades</dd>
                    </div>
                  </dl>
                  <div className="d-callout">
                    <Icon name="help" />
                    <div>
                      <strong>Antes de preparar la ficha</strong>
                      <p>
                        Revisá la identidad, la información y las evidencias.
                        Este paso no publica el producto.
                      </p>
                    </div>
                  </div>
                </>
              )}
              {tab === "Evidencias" && (
                <>
                  <h3>Qué sabemos de este producto</h3>
                  <p>
                    Ejemplos ficticios de evidencia, sin consultas a canales.
                  </p>
                  {(["ml", "tn"] as const).map((c) => (
                    <article className="d-evidence" key={c}>
                      <h4>{c === "ml" ? "Mercado Libre" : "Tiendanube"}</h4>
                      <Pill value={selected[c]} />
                      <p>
                        {selected[c] === "Verificada"
                          ? `Asociación sintética revisada por ID de variante ${selected.id}. Referencia DEMO-${c}-${selected.id}.`
                          : selected[c] === "SKU coincidente"
                            ? "El SKU coincide, pero la identidad y la presentación aún deben verificarse. Publicación no confirmada."
                            : "No hay evidencia disponible. Esto no significa que el producto no esté publicado."}
                      </p>
                    </article>
                  ))}
                </>
              )}
              {tab === "IA" && (
                <>
                  <span className="d-ai-tag">SUGERENCIA SIMULADA</span>
                  <h3>Una ficha más clara, con tu criterio</h3>
                  <p>
                    Propuesta de título:{" "}
                    <strong>
                      {selected.name} — {selected.brand}
                    </strong>
                  </p>
                  <div className="d-callout">
                    <Icon name="sparkles" />
                    <p>
                      La IA no se ejecuta en este prototipo. Esta propuesta es
                      fija, no valida datos ni se aplica automáticamente.
                    </p>
                  </div>
                  <button
                    onClick={() =>
                      setNotice(
                        "Sugerencia simulada descartada. No se modificó la ficha.",
                      )
                    }
                  >
                    Descartar sugerencia
                  </button>
                </>
              )}
              {tab === "Canales" && (
                <>
                  <h3>Presencia por canal</h3>
                  <p>
                    La preparación interna y la publicación son estados
                    diferentes.
                  </p>
                  <article className="d-evidence">
                    <h4>Ecomm-App</h4>
                    <Pill value="Verificada" />
                    <p>Fuente central sintética · variante {selected.id}</p>
                  </article>
                  {(["ml", "tn"] as const).map((c) => (
                    <article className="d-evidence" key={c}>
                      <h4>{c === "ml" ? "Mercado Libre" : "Tiendanube"}</h4>
                      <Pill value={selected[c]} />
                      <p>
                        {selected[c] === "Verificada"
                          ? "Publicación verificada en el ejemplo sintético."
                          : "Publicación no confirmada. Revisar evidencias."}
                      </p>
                    </article>
                  ))}
                </>
              )}
              {tab === "Historial" && (
                <>
                  <h3>Actividad de la ficha</h3>
                  <ol className="d-timeline">
                    <li>
                      <strong>Variante incorporada</strong>
                      <p>Desde el catálogo sintético Ecomm-App · DEMO</p>
                    </li>
                    <li>
                      <strong>Evidencias de muestra agregadas</strong>
                      <p>Sin conexión con servicios externos.</p>
                    </li>
                    {selected.status === "Preparada" && (
                      <li>
                        <strong>Ficha preparada</strong>
                        <p>
                          Estado interno de demostración. No se publicó en
                          canales.
                        </p>
                      </li>
                    )}
                  </ol>
                  <p>Los cambios de esta sesión se pierden al recargar.</p>
                </>
              )}
            </div>
            <div className="d-drawer-actions">
              {confirm ? (
                <div className="d-confirm" role="alert">
                  <strong>¿Preparar la ficha {selected.id}?</strong>
                  <p>
                    Solo cambiará su estado en esta demostración. Los conflictos
                    de canal seguirán sin verificarse.
                  </p>
                  <div>
                    <button onClick={() => setConfirm(false)}>Cancelar</button>
                    <button className="d-primary" onClick={approve}>
                      Confirmar preparación
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <p>Acción interna · no publica ni modifica canales</p>
                  <button
                    className="d-primary"
                    disabled={selected.status === "Preparada"}
                    onClick={() => setConfirm(true)}
                  >
                    {selected.status === "Preparada"
                      ? "Ficha preparada"
                      : "Preparar ficha"}{" "}
                    <Icon name="check" size={17} />
                  </button>
                </>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
export function LegacyNotice() {
  return (
    <div className="d-legacy-banner">
      Prototipo aislado · La herramienta original se conserva, pero sus
      operaciones de red están deshabilitadas.{" "}
      <a href="/">Volver al dashboard</a>
    </div>
  );
}
