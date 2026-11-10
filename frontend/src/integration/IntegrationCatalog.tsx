import { FormEvent, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { KikiIcon as Icon } from "../components/KikiIcon";
import {
  CatalogError,
  type CatalogPage,
  captureDate,
  loadCatalog,
  request,
  unavailable,
} from "./catalog-adapter";
import "./integration.css";

type Session = { username: string; csrf_token: string };
const tabs = ["Ficha", "Evidencias", "IA", "Canales", "Historial"];
const blocked =
  "Esta operación todavía no está conectada. Sólo lectura en etapa 2C.";
function sessionData(value: unknown): Session {
  const data = value as Record<string, unknown> | null;
  if (
    !data ||
    data.authenticated !== true ||
    typeof data.username !== "string" ||
    typeof data.csrf_token !== "string" ||
    !/^[a-f0-9]{64}$/.test(data.csrf_token)
  )
    throw new CatalogError(0, "La respuesta de autenticación no es válida.");
  return { username: data.username, csrf_token: data.csrf_token };
}
export function IntegrationCatalog() {
  const [params, setParams] = useSearchParams();
  const [session, setSession] = useState<Session | null>();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [data, setData] = useState<CatalogPage>();
  const [error, setError] = useState<CatalogError>();
  const [loading, setLoading] = useState(false);
  const [revision, retry] = useState(0);
  const q = params.get("q") || "";
  const rawPage = params.get("page") || "1",
    rawSize = params.get("limit") || "6";
  const page = Number(rawPage),
    pageSize = Number(rawSize);
  const invalid =
    q.length > 80 ||
    !/^[1-9]\d*$/.test(rawPage) ||
    page > 100000 ||
    ![3, 6, 25].includes(pageSize) ||
    String(pageSize) !== rawSize ||
    ["q", "page", "limit", "product", "tab"].some(
      (key) => params.getAll(key).length > 1,
    ) ||
    Array.from(params.keys()).some(
      (key) => !["q", "page", "limit", "product", "tab"].includes(key),
    ) ||
    (params.has("tab") && !tabs.includes(params.get("tab")!)) ||
    (params.has("product") &&
      !/^[A-Za-z0-9_-]{1,120}$/.test(params.get("product")!));
  const [search, setSearch] = useState(q);
  const selected = data?.items.find(
    (item) => item.id === params.get("product"),
  );
  const tab = tabs.includes(params.get("tab") || "")
    ? params.get("tab")!
    : "Ficha";
  const closeRef = useRef<HTMLButtonElement>(null);
  const originRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  function update(values: Record<string, string>) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      Object.entries(values).forEach(([key, value]) =>
        value ? next.set(key, value) : next.delete(key),
      );
      return next;
    });
  }
  function close() {
    update({ product: "", tab: "" });
    originRef.current?.focus();
  }
  useEffect(() => {
    setSearch(q);
  }, [q]);
  useEffect(() => {
    let active = true;
    request("/api/auth/me")
      .then((response) => response.json())
      .then((value) => {
        if (active) setSession(sessionData(value));
      })
      .catch((err) => {
        if (!active) return;
        setSession(null);
        if (!(err instanceof CatalogError && err.status === 401))
          setAuthError(err.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    setData(undefined);
    setError(undefined);
    if (!session || invalid) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    loadCatalog(q, page, pageSize, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        const failure =
          err instanceof CatalogError
            ? err
            : new CatalogError(
                0,
                "No se pudo interpretar el catálogo del backend.",
              );
        if (failure.status === 401) {
          setSession(null);
          setAuthError(failure.message);
        } else setError(failure);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [session, q, page, pageSize, invalid, revision]);
  useEffect(() => {
    if (!selected) return;
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
      if (event.key === "Tab") {
        const controls = panelRef.current?.querySelectorAll<HTMLButtonElement>(
          "button:not(:disabled)",
        );
        if (!controls?.length) return;
        const first = controls[0],
          last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [selected?.id]);
  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setAuthError("");
    try {
      const response = await request("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      setSession(sessionData(await response.json()));
      setPassword("");
    } catch (err) {
      setAuthError(
        err instanceof CatalogError && err.status === 401
          ? "Usuario o contraseña de prueba incorrectos."
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    if (!session) return;
    setBusy(true);
    try {
      await request("/api/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": session.csrf_token },
      });
      setSession(null);
      setData(undefined);
      setAuthError("");
    } catch (err) {
      if (err instanceof CatalogError && err.status === 401) {
        setSession(null);
        setData(undefined);
        setAuthError(err.message);
      } else setError(err as CatalogError);
    } finally {
      setBusy(false);
    }
  }
  if (session === undefined)
    return (
      <main className="login-page" role="status">
        Verificando sesión de prueba…
      </main>
    );
  if (!session)
    return (
      <main className="login-page">
        <section className="login-card">
          <p className="eyebrow">KIKI TECH 2.0 · INTEGRACIÓN AISLADA</p>
          <h1>Ingresá al catálogo de prueba</h1>
          <p>
            FastAPI y PostgreSQL descartable. Sólo productos sintéticos; sin
            proveedores externos.
          </p>
          <form className="login-form" onSubmit={login}>
            <label>
              Usuario de prueba
              <input
                required
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label>
              Contraseña de prueba
              <input
                required
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {authError && <p role="alert">{authError}</p>}
            <button disabled={busy}>
              {busy ? "Verificando…" : "Ingresar"}
            </button>
          </form>
          <small>
            Este acceso no admite cuentas productivas. No ingreses credenciales
            reales.
          </small>
        </section>
      </main>
    );
  return (
    <div className="d-app i-app">
      <aside className="d-sidebar">
        <a href="/" className="d-brand">
          <span>k.</span>
          <strong>
            KIKI<span>TECH 2.0</span>
          </strong>
        </a>
        <div className="d-workspace">
          <span className="d-avatar">K</span>
          <div>
            KIKI Market<small>Integración de prueba</small>
          </div>
        </div>
        <small className="d-nav-label">TU ESPACIO DE TRABAJO</small>
        <nav aria-label="Navegación del catálogo">
          <button
            className="d-active"
            onClick={() =>
              document.getElementById("integration-search")?.focus()
            }
          >
            <Icon name="box" />
            Mi catálogo
          </button>
          <button disabled title={blocked}>
            <Icon name="clock" />
            Historial
          </button>
          <button disabled title={blocked}>
            <Icon name="layers" />
            Configuración
          </button>
        </nav>
        <div className="d-sidebar-bottom">
          <Icon name="shield" />
          <strong>Entorno aislado</strong>
          <p>Datos inventados. Ninguna operación comercial está habilitada.</p>
          <span>Etapa 2C · Sólo lectura</span>
        </div>
      </aside>
      <div className="d-body">
        <header className="d-topbar">
          <span>
            Espacio de trabajo / <strong>Mi catálogo</strong>
          </span>
          <div>
            <span className="d-demo-dot" />
            Integración sintética{" "}
            <button onClick={logout} disabled={busy}>
              Cerrar sesión
            </button>
          </div>
        </header>
        <main className="d-main">
          <div className="d-heading">
            <div>
              <div className="d-eyebrow">TU CATÁLOGO CENTRAL</div>
              <h1>
                Tu catálogo, en un solo lugar<span>.</span>
              </h1>
              <p>
                Consultá las variantes del backend de pruebas sin modificar tus
                sistemas.
              </p>
            </div>
          </div>
          <div className="d-demo">
            <Icon name="shield" />
            <span>
              <strong>Modo integración · Sólo lectura.</strong> Variantes
              sintéticas guardadas en PostgreSQL descartable. Sin conexión a
              proveedores.
            </span>
          </div>
          <section
            className="d-metrics i-metrics"
            aria-label="Resumen del catálogo"
          >
            <div className="d-metric c-central" data-testid="total">
              <span>Variantes Ecomm-App</span>
              <strong>{data?.total ?? "—"}</strong>
              <small>Total informado por el backend</small>
            </div>
            <div className="d-metric" data-testid="shown">
              <span>Registros mostrados</span>
              <strong>{data ? data.items.length : "—"}</strong>
              <small>
                {data ? `${data.matches} resultados de búsqueda` : unavailable}
              </small>
            </div>
            <div className="d-metric" data-testid="capture">
              <span>Estado de captura</span>
              <strong className="i-text-metric">
                {data
                  ? "Completa"
                  : error?.status === 409
                    ? "Incompleta o no disponible"
                    : unavailable}
              </strong>
              <small>
                Última actualización: {captureDate(data?.lastAt ?? null)}
              </small>
            </div>
          </section>
          <section
            className="i-coverage"
            aria-label="Indicadores sin fuente integrada"
          >
            {[
              "Publicaciones Mercado Libre",
              "Publicaciones Tiendanube",
              "Cobertura confirmada",
              "Preparación por canal",
              "Necesitan revisión",
            ].map((label) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{unavailable}</strong>
              </div>
            ))}
          </section>
          <section className="d-catalog" aria-label="Catálogo Ecomm-App">
            <div className="i-catalog-heading">
              <div>
                <h2>Mi catálogo</h2>
                <p>
                  Una fila por variante. El SKU puede repetirse; el Ecomm ID
                  conserva la identidad.
                </p>
              </div>
              <button
                onClick={() => retry((value) => value + 1)}
                disabled={loading}
              >
                Volver a consultar
              </button>
            </div>
            <form
              className="d-filters i-filters"
              onSubmit={(event) => {
                event.preventDefault();
                update({ q: search.trim(), page: "", product: "", tab: "" });
              }}
            >
              <label className="d-search">
                <Icon name="search" />
                <input
                  id="integration-search"
                  aria-label="Buscar productos"
                  placeholder="Nombre, SKU, presentación o Ecomm ID"
                  maxLength={80}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <button className="d-primary">Buscar</button>
              <label>
                Por página
                <select
                  aria-label="Variantes por página"
                  value={pageSize}
                  onChange={(event) =>
                    update({
                      limit: event.target.value,
                      page: "",
                      product: "",
                      tab: "",
                    })
                  }
                >
                  {[3, 6, 25].map((size) => (
                    <option key={size}>{size}</option>
                  ))}
                </select>
              </label>
              {q && (
                <button
                  type="button"
                  onClick={() =>
                    update({ q: "", page: "", product: "", tab: "" })
                  }
                >
                  Limpiar búsqueda
                </button>
              )}
            </form>
            {invalid && (
              <div className="i-message" role="alert">
                <h3>Filtros de URL inválidos</h3>
                <p>
                  No se consultó el backend. Revisá la búsqueda y la paginación.
                </p>
                <button onClick={() => setParams({})}>
                  Restablecer filtros
                </button>
              </div>
            )}
            {loading && (
              <p className="i-message" role="status">
                Consultando catálogo de prueba…
              </p>
            )}
            {error && (
              <div className="i-message" role="alert">
                <h3>No se pudo cargar el catálogo</h3>
                <p>{error.message}</p>
                <p>
                  No se utilizan cifras ni productos de demostración como
                  reemplazo.
                </p>
                <button onClick={() => retry((value) => value + 1)}>
                  Reintentar
                </button>
              </div>
            )}
            {data && (
              <>
                <div className="d-table-scroll">
                  <table className="d-table i-table">
                    <thead>
                      <tr>
                        <th>Producto</th>
                        <th>SKU / Ecomm ID</th>
                        <th>Presentación</th>
                        <th>Stock de captura</th>
                        <th>Estados comerciales</th>
                        <th>Acción</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((item) => (
                        <tr key={item.id} data-ecomm-id={item.id}>
                          <td data-label="Producto">
                            <strong>
                              {item.name ?? "Nombre no disponible"}
                            </strong>
                            <small>Catálogo Ecomm-App · Datos sintéticos</small>
                          </td>
                          <td data-label="Identidad">
                            <strong>{item.sku ?? unavailable}</strong>
                            <small>Ecomm ID: {item.id}</small>
                          </td>
                          <td data-label="Presentación">
                            {item.presentation ?? unavailable}
                          </td>
                          <td data-label="Stock de captura">
                            {item.stock ?? unavailable}
                            <small>{captureDate(item.capturedAt)}</small>
                          </td>
                          <td data-label="Estados comerciales">
                            <small>Editorial: {unavailable}</small>
                            <small>ML: {unavailable}</small>
                            <small>TN: {unavailable}</small>
                          </td>
                          <td data-label="Acción">
                            <button
                              onClick={(event) => {
                                originRef.current = event.currentTarget;
                                update({ product: item.id, tab: "Ficha" });
                              }}
                            >
                              Ver ficha
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!data.items.length && (
                  <div className="i-message" role="status">
                    <h3>
                      {data.total === 0 ? "Catálogo vacío" : "Sin resultados"}
                    </h3>
                    <p>
                      {data.total === 0
                        ? "La captura no contiene variantes."
                        : "No encontramos variantes para esta búsqueda o página. Conservamos tus filtros."}
                    </p>
                  </div>
                )}
                <footer className="d-table-footer i-pagination">
                  <span>
                    {data.items.length} mostrados · {data.matches} resultados ·{" "}
                    {data.total} variantes en la captura
                  </span>
                  <div>
                    <button
                      disabled={page <= 1 || loading}
                      onClick={() =>
                        update({ page: String(page - 1), product: "", tab: "" })
                      }
                    >
                      Anterior
                    </button>
                    <span>
                      Página {page} de{" "}
                      {Math.max(1, Math.ceil(data.matches / pageSize))}
                    </span>
                    <button
                      disabled={page * pageSize >= data.matches || loading}
                      onClick={() =>
                        update({ page: String(page + 1), product: "", tab: "" })
                      }
                    >
                      Siguiente
                    </button>
                  </div>
                </footer>
              </>
            )}
            {data && params.get("product") && !selected && (
              <p role="alert" className="i-message">
                La variante seleccionada no está en esta página. No se sustituyó
                por un producto con el mismo SKU.
                <button onClick={close}>Volver a la tabla</button>
              </p>
            )}
          </section>
          <p className="d-footnote">
            <Icon name="help" />
            Origen: {data?.source ?? unavailable}. El stock corresponde a la
            captura, no está en vivo.
          </p>
        </main>
      </div>
      {selected && (
        <>
          <div className="d-backdrop" onClick={close} />
          <section
            ref={panelRef}
            className="d-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={`Ficha ${selected.id}`}
          >
            <div className="d-drawer-top">
              <span>CONSULTA DE VARIANTE</span>
              <button ref={closeRef} onClick={close} aria-label="Cerrar ficha">
                ×
              </button>
            </div>
            <div className="d-drawer-title">
              <span className="d-thumbnail">
                <Icon name="box" size={32} />
              </span>
              <div>
                <h2>{selected.name ?? "Nombre no disponible"}</h2>
                <p>
                  Ecomm ID: {selected.id} ·{" "}
                  {selected.presentation ?? unavailable}
                </p>
              </div>
            </div>
            <div className="d-drawer-status">
              <span className="d-pill">Sólo lectura</span>
              <span>Datos del backend sintético</span>
            </div>
            <div
              className="d-tabs"
              role="tablist"
              aria-label="Detalle de la variante"
            >
              {tabs.map((label) => (
                <button
                  role="tab"
                  key={label}
                  aria-selected={tab === label}
                  aria-controls="integration-tab"
                  onClick={() => update({ tab: label })}
                >
                  {label}
                </button>
              ))}
            </div>
            <div
              className="d-tab-content"
              role="tabpanel"
              id="integration-tab"
              aria-label={tab}
            >
              {tab === "Ficha" ? (
                <>
                  <h3>Datos disponibles</h3>
                  <dl className="i-details">
                    {[
                      ["Nombre original", selected.name],
                      ["Ecomm ID", selected.id],
                      ["SKU", selected.sku],
                      ["Presentación", selected.presentation],
                      ["Stock de captura", selected.stock],
                      ["Fecha de captura", captureDate(selected.capturedAt)],
                      ["EAN informado", selected.gtin],
                      ["Marca", null],
                      ["Precio", null],
                      ["Imágenes y videos", null],
                    ].map(([label, value]) => (
                      <div key={String(label)}>
                        <dt>{label}</dt>
                        <dd>{value ?? unavailable}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              ) : tab === "Evidencias" ? (
                <>
                  <h3>Origen de la consulta</h3>
                  <p>{data?.source}</p>
                  <p>Captura: {captureDate(selected.capturedAt)}</p>
                  <p>
                    Esta captura sintética no acredita publicaciones, fuentes
                    oficiales ni información vigente en canales.
                  </p>
                </>
              ) : (
                <>
                  <h3>
                    {tab === "IA"
                      ? "Propuestas de IA"
                      : tab === "Canales"
                        ? "Mercado Libre y Tiendanube"
                        : "Historial y decisiones"}
                  </h3>
                  <p>
                    {unavailable}. Esta función todavía no tiene una fuente
                    integrada en este modo.
                  </p>
                </>
              )}
              <div
                className="i-disabled-actions"
                aria-label="Operaciones no conectadas"
              >
                {[
                  "Editar ficha",
                  "Generar con IA",
                  "Aprobar cambios",
                  "Preparar por canal",
                ].map((label) => (
                  <button key={label} disabled title={blocked}>
                    {label}
                  </button>
                ))}
              </div>
              <p>{blocked}</p>
              <button onClick={close}>Volver a la tabla</button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
