import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { KikiIcon as Icon } from "../components/KikiIcon";
import { type Status } from "./data";
import {
  candidateCount,
  channelState,
  inWorkState,
  workLabels,
  editorialState,
  actionTab,
  type WorkState,
  createCatalog,
  nextAction,
  type Item,
  type Job,
} from "./operations-model";
import { OperationalPanel } from "./OperationalPanel";
import { OperationsCenter } from "./OperationsCenter";
import "./dashboard.css";
import "./operations.css";
import "./simple-dashboard.css";
import { SettingsDialog } from "./SettingsDialog";
const tabs = ["Ficha", "Evidencias", "IA", "Canales", "Historial"];
const money = (n: number) =>
  new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
    maximumFractionDigits: 0,
  }).format(n);
function Pill({ value }: { value: string }) {
  return (
    <span
      className={`d-pill ${value === "Preparada" || value === "Verificada" || value === "Publicado" || value === "Ficha aprobada" ? "good" : value === "Conflicto" || value === "Revisión necesaria" || value === "Datos incompletos" ? "bad" : "warm"}`}
    >
      {value === "Verificada" ? "✓ " : value === "Conflicto" ? "! " : ""}
      {value}
    </span>
  );
}
export function PrototypeDashboard() {
  const [urlParams, setParams] = useSearchParams();
  const [params, setAcceptedParams] = useState(urlParams);
  const [rows, setRows] = useState(createCatalog);
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<(() => void) | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [advanced, setAdvanced] = useState(false);
  const [showPrices, setShowPrices] = useState(true);
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
    channel = params.get("channel") || "",
    conflict = params.get("conflict") || "",
    action = params.get("action") || "",
    work = params.get("work") || "";
  function update(values: Record<string, string>) {
    const run = () =>
      setParams((previous) => {
        const next = new URLSearchParams(previous);
        Object.entries(values).forEach(([k, v]) =>
          v ? next.set(k, v) : next.delete(k),
        );
        return next;
      });
    if (dirty) {
      setPending(() => run);
      return;
    }
    run();
  }
  function close() {
    update({ product: "", tab: "" });
    originRef.current?.focus();
  }
  useEffect(() => {
    if (selected) {
      originRef.current = document.activeElement as HTMLElement;
      closeRef.current?.focus();
    }
  }, [selected?.id]);
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (pending) {
        if (e.key === "Escape") setPending(null);
        return;
      }
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key === "Tab") {
        const elements = panelRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled):not([tabindex="-1"]),a,input,textarea,select,[tabindex="0"]',
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
  }, [selected?.id, dirty, pending]);
  const filtered = rows
    .filter(
      (p) =>
        [p.name, p.sku, p.brand, p.id]
          .join(" ")
          .toLocaleLowerCase()
          .includes(q.toLocaleLowerCase()) &&
        (!status ||
          (status === "Conflicto" ? p.conflict : p.status === status)) &&
        inWorkState(p, work) &&
        (!brand || p.brand === brand) &&
        (!channel ||
          (channel === "candidate"
            ? candidateCount(p) > 0
            : (channel === "ml" ? p.ml : p.tn) === "Verificada")) &&
        (!conflict || (conflict === "yes" ? p.conflict : !p.conflict)) &&
        (!action || nextAction(p) === action),
    )
    .sort(
      (a, b) =>
        Number(b.conflict) - Number(a.conflict) ||
        Number(b.status === "Pendiente") - Number(a.status === "Pendiente") ||
        a.id.localeCompare(b.id),
    );
  const count = (s: Status) =>
    rows.filter((p) => (s === "Conflicto" ? p.conflict : p.status === s))
      .length;
  function replaceProduct(p: Item) {
    setRows((old) => old.map((row) => (row.id === p.id ? p : row)));
    setDirty(false);
  }
  useEffect(() => {
    if (urlParams.toString() === params.toString()) return;
    if (dirty) {
      const target = new URLSearchParams(urlParams);
      setParams(params, { replace: true });
      setPending(() => () => {
        setAcceptedParams(target);
        setParams(target);
      });
    } else setAcceptedParams(urlParams);
  }, [urlParams, dirty, params, setParams]);
  useEffect(() => {
    if (!dirty) return;
    const before = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    const click = (e: MouseEvent) => {
      const anchor =
        e.target instanceof Element ? e.target.closest("a[href]") : null;
      if (
        anchor instanceof HTMLAnchorElement &&
        new URL(anchor.href).origin === location.origin
      ) {
        e.preventDefault();
        e.stopImmediatePropagation();
        setPending(() => () => location.assign(anchor.href));
      }
    };
    window.addEventListener("beforeunload", before);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", before);
      document.removeEventListener("click", click, true);
    };
  }, [dirty]);

  useEffect(() => {
    if (params.get("tools") === "1" || params.get("tool"))
      document
        .getElementById("catalog-operations")
        ?.scrollIntoView({ block: "start" });
  }, [params.get("tools"), params.get("tool")]);
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
        <small className="d-nav-label">TU ESPACIO DE TRABAJO</small>
        <nav aria-label="Navegación del prototipo">
          <button
            className="d-active"
            onClick={() => {
              document.getElementById("catalog-search")?.focus();
              document
                .getElementById("catalog")
                ?.scrollIntoView({ block: "start" });
            }}
          >
            <Icon name="box" /> Mi catálogo
          </button>
          <button
            onClick={() =>
              update({ tool: "Trabajos y resultados", tools: "1" })
            }
          >
            <Icon name="clock" /> Historial
          </button>
          <button onClick={() => update({ settings: "1" })}>
            <Icon name="layers" /> Configuración
          </button>
        </nav>
        <div className="d-sidebar-bottom">
          <Icon name="shield" />
          <strong>Tu catálogo, bajo control</strong>
          <p>Vos revisás y decidís cada cambio.</p>
          <span>Etapa 1.2 · Demostración</span>
        </div>
      </aside>
      <div className="d-body">
        <header className="d-topbar">
          <span>
            Espacio de trabajo <b>/</b> <strong>Mi catálogo</strong>
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
              onClick={() =>
                update({
                  work: "attention",
                  status: "",
                  channel: "",
                  conflict: "",
                  action: "",
                })
              }
            >
              Revisar productos <Icon name="arrow-right" size={17} />
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
            {(
              ["attention", "preparing", "ready", "published"] as WorkState[]
            ).map((state) => (
              <button
                key={state}
                aria-pressed={work === state}
                className={`d-metric ${state === "attention" ? "d-metric-conflict" : ""}`}
                onClick={() =>
                  update({
                    work: work === state ? "" : state,
                    status: "",
                    channel: "",
                    conflict: "",
                    action: "",
                    brand: "",
                  })
                }
              >
                <span>
                  {workLabels[state]}
                  <Icon
                    name={
                      state === "attention"
                        ? "alert"
                        : state === "preparing"
                          ? "clock"
                          : state === "ready"
                            ? "check"
                            : "store"
                    }
                    size={18}
                  />
                </span>
                <strong>
                  {rows.filter((p) => inWorkState(p, state)).length}
                </strong>
                <small>
                  {state === "attention"
                    ? "Resolver una revisión o bloqueo"
                    : state === "preparing"
                      ? "Completar o aprobar información"
                      : state === "ready"
                        ? "Preparación interna · revisar vigencia"
                        : "Con evidencia en al menos un canal"}
                </small>
              </button>
            ))}
          </section>
          <p className="s-count-note">
            Contamos variantes de producto. Una puede estar publicada en un
            canal y necesitar trabajo en otro; los indicadores no se suman. Todo
            es una demostración.
          </p>
          <div
            className="s-toolbar"
            role="region"
            aria-label="Resumen del catálogo"
          >
            <span>
              {new Set(rows.map((p) => p.family)).size} productos ·{" "}
              {rows.length} variantes en Ecomm-App
            </span>
            <button
              onClick={() =>
                update({
                  tools: params.get("tools") === "1" ? "" : "1",
                  tool: "",
                })
              }
            >
              Más acciones del catálogo
            </button>
            <button
              onClick={() =>
                update({
                  q: "",
                  work: "",
                  status: "",
                  brand: "",
                  channel: "",
                  conflict: "",
                  action: "",
                })
              }
            >
              Ver todo el catálogo
            </button>
          </div>
          <section className="d-catalog" id="catalog">
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
                <option value="">Todas las fichas</option>
                <option value="Pendiente">Borrador sin aprobar</option>
                <option value="Conflicto">Revisión necesaria</option>
                <option value="Preparada">Ficha aprobada</option>
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
                <option value="candidate">Coincidencias candidatas</option>
              </select>
            </div>
            <details className="s-advanced" open={advanced}>
              <summary
                onClick={(e) => {
                  e.preventDefault();
                  setAdvanced(!advanced);
                }}
              >
                Más filtros y detalles
              </summary>
              <div className="o-extra-filters">
                <label>
                  Conflicto
                  <select
                    aria-label="Conflicto"
                    value={conflict}
                    onChange={(e) => update({ conflict: e.target.value })}
                  >
                    <option value="">Con y sin conflicto</option>
                    <option value="yes">Con conflicto</option>
                    <option value="no">Sin conflicto</option>
                  </select>
                </label>
                <label>
                  Siguiente acción
                  <select
                    aria-label="Siguiente acción"
                    value={action}
                    onChange={(e) => update({ action: e.target.value })}
                  >
                    <option value="">Todas las acciones</option>
                    {[
                      "Resolver conflicto",
                      "Revisar IA",
                      "Completar ficha",
                      "Revisar ficha",
                      "Verificar antes de publicar",
                      "Revisar publicaciones",
                      "Preparar canal",
                    ].map((a) => (
                      <option key={a}>{a}</option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="s-count-note">
                {rows.reduce((n, p) => n + candidateCount(p), 0)} coincidencias
                por revisar. No confirman publicación.
              </p>
            </details>
            {(q ||
              work ||
              status ||
              brand ||
              channel ||
              conflict ||
              action) && (
              <div className="d-active-filters">
                {work
                  ? workLabels[work as WorkState] || "Filtros activos"
                  : "Filtros activos"}{" "}
                <button
                  onClick={() =>
                    update({
                      work: "",
                      q: "",
                      status: "",
                      brand: "",
                      channel: "",
                      conflict: "",
                      action: "",
                    })
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
                    <th>{showPrices ? "Precio / Stock" : "Disponibilidad"}</th>
                    <th>Mercado Libre</th>
                    <th>Tiendanube</th>
                    <th>Ficha y siguiente paso</th>
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
                            <span className="s-mobile-channels">
                              <span>ML · {channelState(p, "ml")}</span>
                              <span>TN · {channelState(p, "tn")}</span>
                            </span>
                          </span>
                        </button>
                      </td>
                      <td>
                        <strong className="d-sku">{p.sku}</strong>
                        <small>{p.brand}</small>
                      </td>
                      <td>
                        {showPrices && <strong>{money(p.price)}</strong>}
                        <small>{p.stock} disponibles</small>
                      </td>
                      <td>
                        <Pill value={channelState(p, "ml")} />
                        <small>
                          {p.ml === "SKU coincidente"
                            ? p.decisions.ml.state === "Rechazada"
                              ? "Coincidencia descartada"
                              : p.decisions.ml.state === "Aceptada"
                                ? "Coincidencia revisada; no confirma publicación"
                                : "Coincidencia por revisar"
                            : p.ml === "Sin evidencia"
                              ? "Falta evidencia; no implica ausencia"
                              : "Evidencia de muestra"}
                        </small>
                      </td>
                      <td>
                        <Pill value={channelState(p, "tn")} />
                        <small>
                          {p.tn === "SKU coincidente"
                            ? p.decisions.tn.state === "Rechazada"
                              ? "Coincidencia descartada"
                              : p.decisions.tn.state === "Aceptada"
                                ? "Coincidencia revisada; no confirma publicación"
                                : "Coincidencia por revisar"
                            : p.tn === "Sin evidencia"
                              ? "Falta evidencia; no implica ausencia"
                              : "Evidencia de muestra"}
                        </small>
                      </td>
                      <td>
                        <Pill value={editorialState(p)} />
                        <small>{nextAction(p)}</small>
                        <button
                          className="o-quick"
                          onClick={() =>
                            update({
                              product: p.id,
                              tab: actionTab(p),
                            })
                          }
                        >
                          {nextAction(p)}
                        </button>
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
                    update({
                      work: "",
                      q: "",
                      status: "",
                      brand: "",
                      channel: "",
                      conflict: "",
                      action: "",
                    })
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
          {(params.get("tools") === "1" || params.get("tool")) && (
            <div id="catalog-operations">
              <button
                className="s-return"
                onClick={() => {
                  document.getElementById("catalog")?.scrollIntoView();
                  document.getElementById("catalog-search")?.focus();
                }}
              >
                Volver a búsqueda y productos ↑
              </button>
              <OperationsCenter
                key={editorEpoch}
                rows={rows}
                active={params.get("tool") || ""}
                onTool={(tool) => update({ tool })}
                onChange={setRows}
                onSelect={(product, tab) => update({ product, tab, tool: "" })}
                jobs={jobs}
                onJob={(job) => setJobs((old) => [...old, job])}
                onDirty={setDirty}
              />
            </div>
          )}
          <p className="d-footnote">
            <Icon name="help" size={15} /> Un SKU coincidente es una pista. Solo
            una evidencia verificada confirma la publicación.
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
              <Pill value={editorialState(selected)} />
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
              <OperationalPanel
                key={`${selected.id}-${editorEpoch}`}
                product={selected}
                tab={tab}
                onChange={replaceProduct}
                onDirty={setDirty}
              />
            </div>
          </section>
        </>
      )}
      {params.get("settings") === "1" && (
        <SettingsDialog
          advanced={advanced}
          showPrices={showPrices}
          onAdvanced={setAdvanced}
          onPrices={setShowPrices}
          onClose={() => update({ settings: "" })}
        />
      )}
      {pending && (
        <div
          className="o-unsaved"
          role="alertdialog"
          aria-modal="true"
          aria-label="Cambios sin guardar"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation();
              setPending(null);
              return;
            }
            if (e.key === "Tab") {
              const buttons = e.currentTarget.querySelectorAll("button");
              if (e.shiftKey && document.activeElement === buttons[0]) {
                e.preventDefault();
                buttons[buttons.length - 1].focus();
              } else if (
                !e.shiftKey &&
                document.activeElement === buttons[buttons.length - 1]
              ) {
                e.preventDefault();
                buttons[0].focus();
              }
            }
          }}
        >
          <h3>Tenés cambios sin guardar</h3>
          <p>
            Podés seguir editando o descartar el trabajo pendiente. El catálogo
            guardado no se modifica.
          </p>
          <button autoFocus onClick={() => setPending(null)}>
            Seguir editando
          </button>
          <button
            onClick={() => {
              const run = pending;
              setDirty(false);
              setEditorEpoch((old) => old + 1);
              setPending(null);
              run();
            }}
          >
            Descartar y continuar
          </button>
        </div>
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
