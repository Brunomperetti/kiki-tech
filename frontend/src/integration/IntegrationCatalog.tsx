import {
  production,
  capabilities,
  configureRuntime,
  canWrite,
  availableFeature,
  environmentText,
} from "./runtime";
import { SettingsDialog } from "../prototype/SettingsDialog";
import { ConnectionCenter } from "./ConnectionCenter";
import { useConnections } from "./connections";
import { recommendedAction } from "./product-actions";
import { SavedHistory } from "./SavedHistory";
import {
  CommercialViews,
  ChannelComparisonMatrix,
  ChannelListings,
  commercialViews,
  type CommercialView,
} from "./CommercialViews";
import { BatchPanel } from "./BatchPanel";
import { channelLabels } from "./channel-labels";
import {
  CatalogFrame,
  CatalogTable,
  CatalogMetrics,
  CatalogSearch,
  ProductDrawer,
} from "../prototype/CatalogView";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { KikiIcon as Icon } from "../components/KikiIcon";
import {
  CatalogError,
  type CatalogPage,
  captureDate,
  loadDashboard,
  adaptVariant,
  validVariantId,
  queueFilters,
  validQueueFilter,
  qualityFilterKeys,
  type QueueFilter,
  type Variant,
  request,
  unavailable,
} from "./catalog-adapter";
import "./integration.css";
import { PersistentWorkspace } from "./PersistentWorkspace";
import { stateLabels, getWorkspace } from "./workspace-adapter";
import { MamaPilotLauncher } from "./MamaPilot";
import { mamaPilotId, type MamaReport } from "./mama-pilot";
import { HileretPilotLauncher } from "./HileretPilot";
import { isAuxiliaryPilot, type HileretReport } from "./hileret-pilot";
import type { EcommApiProductEdit } from "../types/ecomm-app";

type Session = { username: string; csrf_token: string };
const tabs = ["Ficha", "Evidencias", "IA", "Canales", "Historial"];
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
  const [urlParams, setParams] = useSearchParams();
  const [params, setAcceptedParams] = useState(urlParams);
  const [preferences, setPreferences] = useState(false),
    [historyOpen, setHistoryOpen] = useState(false),
    [advanced, setAdvanced] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [dirty, setDirty] = useState(false);
  const [editorBusy, setEditorBusy] = useState(false);
  const [pinned, setPinned] = useState<Variant>();
  const [selectionError, setSelectionError] = useState("");
  const dataRef = useRef<CatalogPage>();
  const [session, setSession] = useState<Session | null>();
  const [runtimeReady, setRuntimeReady] = useState(!production);
  const [runtimeError, setRuntimeError] = useState("");
  useEffect(() => {
    if (!production) return;
    configureRuntime();
    setRuntimeReady(false);
    setRuntimeError("");
    if (!session) return;
    const c = new AbortController();
    request("/api/ui/v2", { signal: c.signal })
      .then((r) => r.json())
      .then((value) => {
        if (!c.signal.aborted) {
          configureRuntime(value);
          setRuntimeReady(true);
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) setRuntimeError(e.message);
      });
    return () => {
      c.abort();
      configureRuntime();
    };
  }, [!!session]);
  const [connectionsOpened, setConnectionsOpened] = useState(false);
  const connections = useConnections(
    !!session && runtimeReady && connectionsOpened,
    session?.csrf_token,
    preferences,
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [data, setData] = useState<CatalogPage>();
  dataRef.current = data;
  const [error, setError] = useState<CatalogError>();
  const [loading, setLoading] = useState(false);
  const [revision, retry] = useState(0);
  const q = params.get("q") || "";
  const filter = (params.get("filter") || "all") as QueueFilter;
  const view = (params.get("view") || "ecomm") as CommercialView;
  const external = view === "ml" || view === "tn";
  const linkage = params.get("linkage") || "all";
  const rawPage = params.get("page") || "1",
    rawSize = params.get("limit") || "6";
  const page = Number(rawPage),
    pageSize = Number(rawSize);
  const invalid =
    q.length > 80 ||
    !validQueueFilter(filter) ||
    !Object.prototype.hasOwnProperty.call(commercialViews, view) ||
    ![
      "all",
      "unlinked",
      "verified",
      "candidates",
      "conflicts",
      "no_match",
      "stale",
    ].includes(linkage) ||
    !/^[1-9]\d*$/.test(rawPage) ||
    page > 100000 ||
    ![3, 6, 25, 50].includes(pageSize) ||
    String(pageSize) !== rawSize ||
    [
      "q",
      "page",
      "limit",
      "product",
      "tab",
      "filter",
      "proposal",
      "view",
      "linkage",
    ].some((key) => params.getAll(key).length > 1) ||
    Array.from(params.keys()).some(
      (key) =>
        ![
          "q",
          "page",
          "limit",
          "product",
          "tab",
          "filter",
          "proposal",
          "view",
          "linkage",
        ].includes(key),
    ) ||
    (params.has("tab") && !tabs.includes(params.get("tab")!)) ||
    (params.has("product") && !validVariantId(params.get("product"))) ||
    (params.has("proposal") &&
      (!/^[1-9]\d{0,9}$/.test(params.get("proposal")!) ||
        !params.has("product")));
  const [search, setSearch] = useState(q);
  const [mama, setMama] = useState<MamaReport>();
  const [hileret, setHileret] = useState<HileretReport>();
  const selected =
    data?.items.find((item) => item.id === params.get("product")) ||
    (pinned?.id === params.get("product") ? pinned : undefined) ||
    (params.get("product") === mamaPilotId && mama?.available
      ? mama.variant
      : undefined) ||
    hileret?.cases.find((c) => c.test_id === params.get("product"))?.variant;
  const tab = tabs.includes(params.get("tab") || "")
    ? params.get("tab")!
    : "Ficha";
  const closeRef = useRef<HTMLButtonElement>(null);
  const originRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const navigationPermit = useRef<string | null>(null);
  const navigationAttempt = useRef<string | null>(null);
  function update(values: Record<string, string>) {
    if (values.filter !== undefined && !("view" in values)) {
      const parts = values.filter.split("+");
      values = {
        ...values,
        view: parts.includes("ml_unconfirmed")
          ? "ml_unconfirmed"
          : parts.includes("tn_unconfirmed")
            ? "tn_unconfirmed"
            : "",
        linkage: "",
      };
    }
    const next = new URLSearchParams(params);
    Object.entries(values).forEach(([key, value]) =>
      value ? next.set(key, value) : next.delete(key),
    );
    if (
      (values.product !== undefined &&
        values.product !== params.get("product")) ||
      (values.tab && values.tab !== "IA")
    ) {
      if (!("proposal" in values)) next.delete("proposal");
    }
    const leaving = [
      "product",
      "q",
      "page",
      "limit",
      "filter",
      "proposal",
      "view",
      "linkage",
    ].some((key) => next.get(key) !== params.get(key));
    // Confirm before pushing history; cancel must not leave a duplicate URL entry.
    if (
      leaving &&
      (editorBusy ||
        (dirty &&
          !window.confirm(
            "Hay cambios sin guardar. ¿Descartarlos y continuar?",
          )))
    )
      return;
    navigationAttempt.current = null;
    navigationPermit.current = next.toString();
    setParams(next);
  }
  function close() {
    update({ product: "", tab: "" });
  }
  useEffect(() => {
    if (urlParams.toString() === params.toString()) {
      navigationPermit.current = null;
      navigationAttempt.current = null;
      return;
    }
    if (navigationAttempt.current === urlParams.toString()) return;
    navigationAttempt.current = urlParams.toString();
    const leaving = [
      "product",
      "q",
      "page",
      "limit",
      "filter",
      "proposal",
      "view",
      "linkage",
    ].some((key) => urlParams.get(key) !== params.get(key));
    if (
      leaving &&
      navigationPermit.current !== urlParams.toString() &&
      (editorBusy ||
        (dirty &&
          !window.confirm(
            "Hay cambios sin guardar. ¿Descartarlos y continuar?",
          )))
    ) {
      setParams(params, { replace: true });
      return;
    }
    setAcceptedParams(urlParams);
    if (leaving) setDirty(false);
  }, [urlParams, params, dirty, editorBusy, setParams]);
  useEffect(() => {
    if (!dirty && !editorBusy) return;
    const protect = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [dirty, editorBusy]);
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
    if (!session || !runtimeReady || invalid) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    loadDashboard(q, page, pageSize, filter, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setPinned(undefined);
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
  }, [!!session, runtimeReady, q, page, pageSize, filter, invalid, revision]);
  useEffect(() => {
    if (pinned?.id !== params.get("product")) setPinned(undefined);
    setSelectionError("");
  }, [params.get("product")]);
  useEffect(() => {
    const id = params.get("product");
    if (
      !id ||
      !session ||
      !runtimeReady ||
      invalid ||
      !data ||
      selected ||
      isAuxiliaryPilot(id)
    )
      return;
    const controller = new AbortController();
    getWorkspace(id, controller.signal)
      .then((record) => {
        if (!controller.signal.aborted)
          setPinned({
            ...adaptVariant(record.source),
            brand: record.fields.brand,
            commercialName: record.fields.title,
            editorialStatus: record.status,
            editVersion: record.version,
          });
      })
      .catch((err) => {
        if (!controller.signal.aborted) setSelectionError(err.message);
      });
    return () => controller.abort();
  }, [params.get("product"), !!session, runtimeReady, invalid, data]);
  useEffect(() => {
    if (!selected) {
      originRef.current?.focus();
      return;
    }
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
      if (event.key === "Tab") {
        const controls = panelRef.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]",
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
          ? environmentText(
              "Usuario o contraseña de prueba incorrectos.",
              "Usuario o contraseña incorrectos.",
            )
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    if (!session) return;
    if (
      editorBusy ||
      (dirty &&
        !window.confirm(
          "Hay cambios sin guardar. ¿Descartarlos y cerrar sesión?",
        ))
    )
      return;
    setBusy(true);
    try {
      await request("/api/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": session.csrf_token },
      });
      setSession(null);
      setData(undefined);
      setPinned(undefined);
      setAuthError("");
    } catch (err) {
      if (err instanceof CatalogError && err.status === 401) {
        setSession(null);
        setData(undefined);
        setPinned(undefined);
        setAuthError(err.message);
      } else setError(err as CatalogError);
    } finally {
      setBusy(false);
    }
  }
  if (session === undefined)
    return (
      <main className="login-page" role="status">
        {environmentText(
          "Verificando sesión de prueba…",
          "Verificando sesión…",
        )}
      </main>
    );
  if (!session)
    return (
      <main className="login-page">
        <section className="login-card">
          <p className="eyebrow">
            {production
              ? "KIKI TECH 2.0"
              : "KIKI TECH 2.0 · INTEGRACIÓN AISLADA"}
          </p>
          <h1>
            {environmentText(
              "Ingresá al catálogo de prueba",
              "Ingresá con tu usuario habitual",
            )}
          </h1>
          <p>
            {environmentText(
              "FastAPI y PostgreSQL descartable. Catálogo y usuarios de prueba; documentos locales autorizados. Sin conexiones a proveedores externos.",
              "Acceso privado a las capturas y fichas existentes de KIKI. No se cargan productos de demostración.",
            )}
          </p>
          <form className="login-form" onSubmit={login}>
            <label>
              {environmentText("Usuario de prueba", "Usuario")}
              <input
                required
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label>
              {environmentText("Contraseña de prueba", "Contraseña")}
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
            {environmentText(
              "Este acceso no admite cuentas productivas. No ingreses credenciales reales.",
              "La sesión y los permisos se verifican con el backend de KIKI.",
            )}
          </small>
        </section>
      </main>
    );
  if (!runtimeReady)
    return (
      <main className="login-page">
        <section
          className="login-card"
          role={runtimeError ? "alert" : "status"}
        >
          <h1>
            {runtimeError
              ? "KIKI Tech 2.0 no disponible"
              : "Verificando disponibilidad de KIKI Tech 2.0…"}
          </h1>
          <p>{runtimeError}</p>
          <a href="/dashboard-classic">Volver a la interfaz anterior</a>
          <button onClick={() => void logout()}>Cerrar sesión</button>
        </section>
      </main>
    );
  return (
    <CatalogFrame
      mode={production ? "production" : "integration"}
      onCatalog={() => document.getElementById("integration-search")?.focus()}
      onHistory={() =>
        selected ? update({ tab: "Historial" }) : setHistoryOpen(true)
      }
      onSettings={() => {
        setConnectionsOpened(true);
        setPreferences(true);
      }}
      connectionStatus={
        connections.data?.ecomm.refresh_in_progress
          ? "Ecomm-App actualizando…"
          : connections.refreshSuggested
            ? "Nueva copia disponible"
            : undefined
      }
      onLogout={logout}
      busy={busy}
    >
      {preferences && (
        <SettingsDialog
          connections={
            <ConnectionCenter
              {...connections}
              onOperate={(kind, file) => {
                void connections.operate(kind, file);
              }}
              onReload={connections.reload}
              refreshBlocked={dirty || editorBusy}
              onRefresh={() => {
                retry((r) => r + 1);
                connections.acknowledge();
              }}
            />
          }
          connected
          advanced={advanced}
          showPrices={false}
          onAdvanced={setAdvanced}
          onPrices={() => {}}
          onClose={() => setPreferences(false)}
        />
      )}
      {historyOpen && (
        <SavedHistory
          onClose={() => setHistoryOpen(false)}
          onOpen={(id) => {
            setHistoryOpen(false);
            update({ product: id, tab: "Historial" });
          }}
        />
      )}
      {production && (
        <p className="n-notice" role="status">
          {capabilities?.synthetic
            ? "VALIDACIÓN AISLADA · datos sintéticos de compatibilidad, no catálogo auténtico."
            : "Catálogo capturado desde el backend de KIKI; no es stock en vivo."}{" "}
          {canWrite()
            ? "Edición interna habilitada; cada guardado requiere revisión."
            : "Sólo lectura: guardados, importaciones, OAuth y consumos bloqueados."}{" "}
          <a href="/dashboard-classic">Volver a la interfaz anterior</a>
        </p>
      )}
      <div className="i-capture-strip" aria-label="Información de captura">
        <span data-testid="shown">
          En esta página: <strong>{data ? data.items.length : "—"}</strong> ·{" "}
          {data ? `${data.matches} resultados` : unavailable}
        </span>
        <span data-testid="capture">
          Captura:{" "}
          <strong>
            {data
              ? "Completa"
              : error?.status === 409
                ? "Incompleta o no disponible"
                : unavailable}
          </strong>{" "}
          · {captureDate(data?.lastAt ?? null)}
        </span>
      </div>
      <section
        aria-label="Cobertura por canal"
        className="i-commercial-overview"
      >
        <CommercialViews
          value={view}
          counts={{
            ecomm: data?.total,
            ml: data?.channelOverview?.sources.ml.available
              ? data.channelOverview.comparison?.ml.distinct_publications
              : undefined,
            tn: data?.channelOverview?.sources.tn.available
              ? data.channelOverview.comparison?.tn.distinct_publications
              : undefined,
            ml_unconfirmed: data?.summary?.ml_unconfirmed,
            tn_unconfirmed: data?.summary?.tn_unconfirmed,
          }}
          onChange={(next) =>
            update({
              view: next === "ecomm" ? "" : next,
              q: next === "ecomm" ? "" : q,
              filter: next.endsWith("unconfirmed") ? next : "",
              linkage: "",
              page: "",
              product: "",
              tab: "",
              proposal: "",
            })
          }
        />
        <ChannelComparisonMatrix
          comparison={data?.channelOverview?.comparison}
          filter={filter}
          onFilter={(value) =>
            update({
              filter: filter === value ? "all" : value,
              view: "",
              page: "",
              product: "",
              tab: "",
            })
          }
        />
        <div className="k-preparation">
          <CatalogMetrics
            label="Preparación por canal"
            cards={(["ml", "tn"] as const).map((channel) => ({
              id: `${channel}-ready`,
              title: `Listos para ${channel === "ml" ? "Mercado Libre" : "Tiendanube"}`,
              value:
                data?.summary?.[`${channel}_ready_without_confirmation`] ?? "—",
              note: "Ficha completa interna, sin confirmación en este canal. Falta verificar identidad y vigencia; no publica.",
              active: filter === `ready_for_channels+${channel}_unconfirmed`,
              onClick: () =>
                update({
                  filter:
                    filter === `ready_for_channels+${channel}_unconfirmed`
                      ? ""
                      : `ready_for_channels+${channel}_unconfirmed`,
                  view: "",
                  page: "",
                  product: "",
                  tab: "",
                }),
            }))}
          />
        </div>
        <details
          className="i-more-metrics i-quality"
          open={advanced}
          onToggle={(e) => setAdvanced(e.currentTarget.open)}
        >
          <summary>Calidad del catálogo</summary>
          <h3>Calidad del catálogo · candidatos para revisión</h3>
          <div
            className="k-quality-metrics"
            role="group"
            aria-label="Indicadores de calidad"
          >
            {qualityFilterKeys
              .filter(
                (key) => !["ml_unconfirmed", "tn_unconfirmed"].includes(key),
              )
              .map((key) => (
                <button
                  type="button"
                  key={key}
                  aria-pressed={filter.split("+").includes(key)}
                  onClick={() => {
                    const base =
                      view === "ml_unconfirmed" || view === "tn_unconfirmed"
                        ? view
                        : "";
                    update({
                      view: base || "",
                      filter: filter.split("+").includes(key)
                        ? base
                        : [base, key].filter(Boolean).join("+"),
                      page: "",
                      product: "",
                      tab: "",
                    });
                  }}
                >
                  {queueFilters[key]}{" "}
                  <strong>{data?.summary?.[key] ?? "—"}</strong>
                </button>
              ))}
          </div>
        </details>
        <details className="i-more-metrics i-secondary">
          <summary>Más indicadores comerciales</summary>
          <CatalogMetrics
            label="Indicadores editoriales adicionales"
            cards={[
              ...(
                [
                  "identity",
                  "untouched",
                  "draft",
                  "ready",
                  "ready_for_channels",
                  "pack",
                ] as const
              ).map((key) => ({
                id: key,
                title: queueFilters[key],
                value: data?.summary?.[key] ?? "—",
                note:
                  key === "ready_for_channels"
                    ? "No confirma publicación en canales"
                    : "Calculado sobre el catálogo completo",
                active: filter === key,
                onClick: () =>
                  update({
                    filter: filter === key ? "" : key,
                    page: "",
                    product: "",
                    tab: "",
                  }),
              })),
            ]}
          />
          <p className="s-count-note">
            Totales del catálogo completo, no sólo de esta página. Una variante
            puede necesitar varias tareas. La ficha editorial y la publicación
            de cada canal son estados distintos.
          </p>
          <CatalogMetrics
            label="Indicadores adicionales de canales"
            cards={[
              ["ml_confirmed", "Variantes con ML confirmado"],
              ["tn_verified", "Vínculos TN verificados"],
              ["channel_candidates", "Candidatos pendientes"],
              ["channel_conflicts", "Conflictos de canal"],
              ["channel_no_evidence", "Sin evidencia suficiente"],
              ["channel_stale", "Capturas desactualizadas"],
            ].map(([key, title]) => ({
              id: key,
              title,
              value:
                data?.channelOverview?.validated &&
                !(
                  key === "ml_confirmed" &&
                  !data.channelOverview.sources.ml.available
                ) &&
                !(
                  key === "tn_verified" &&
                  !data.channelOverview.sources.tn.available
                )
                  ? (data.summary?.[key] ?? "—")
                  : unavailable,
              note:
                key === "ml_confirmed"
                  ? "Publicación en captura ML revisada; no es estado en vivo"
                  : key === "tn_verified"
                    ? "Vínculos revisados; el CSV no confirma publicación actual"
                    : "Variantes únicas; las tareas pueden superponerse",
              active: filter === key,
              onClick: () =>
                update({
                  filter: filter === key ? "" : key,
                  page: "",
                  product: "",
                  tab: "",
                }),
            }))}
          />
          <section
            className="i-coverage"
            aria-label="Alcance de la evidencia de canales"
          >
            <div>
              <span>Publicación Tiendanube</span>
              <strong>Sin dato verificable de publicación</strong>
              <small>
                El contrato CSV no demuestra publicación actual. No se inventa
                un total.
              </small>
            </div>
            <div>
              <span>Publicaciones ML confirmadas en captura</span>
              <strong>
                {data?.channelOverview?.validated &&
                data.channelOverview.sources.ml.available
                  ? (data.channelOverview.comparison?.ml
                      .confirmed_publications ??
                    data.channelOverview.confirmedMlListings)
                  : unavailable}
              </strong>
              <small>Publicaciones y variantes son entidades diferentes.</small>
            </div>
            {(["ml", "tn"] as const).map((c) => (
              <div key={c}>
                <span>
                  {c === "ml"
                    ? "Captura Mercado Libre"
                    : "Importación CSV Tiendanube"}
                </span>
                <strong>
                  {captureDate(
                    data?.channelOverview?.sources[c].updatedAt ?? null,
                  )}
                </strong>
                <small>
                  {data?.channelOverview?.sources[c].available
                    ? "Copia disponible; consultar vigencia por producto"
                    : "Sin captura disponible; no demuestra ausencia de publicación"}
                </small>
              </div>
            ))}
          </section>
        </details>
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
            disabled={loading || editorBusy || dirty}
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
          <CatalogSearch
            id="integration-search"
            value={search}
            onChange={setSearch}
            placeholder="Nombre, marca, SKU, EAN o Ecomm ID"
            maxLength={80}
          />
          <button className="d-primary">Buscar</button>
          <label>
            Estado y siguiente paso
            <select
              aria-label="Filtrar catálogo"
              value={filter.split("+")[0]}
              disabled={external}
              onChange={(event) =>
                update({
                  filter:
                    event.target.value === "all" ? "" : event.target.value,
                  page: "",
                  product: "",
                  tab: "",
                })
              }
            >
              {Object.entries(queueFilters).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {!external && (
            <label>
              Combinar con
              <select
                aria-label="Combinar filtro de catálogo"
                value={filter.split("+")[1] || "all"}
                onChange={(e) =>
                  update({
                    filter:
                      [filter.split("+")[0], e.target.value]
                        .filter((f) => f !== "all")
                        .filter((f, i, a) => a.indexOf(f) === i)
                        .join("+") || "all",
                    page: "",
                    product: "",
                    tab: "",
                  })
                }
              >
                {Object.entries(queueFilters).map(([key, label]) => (
                  <option key={key} value={key}>
                    {key === "all" ? "Sin filtro adicional" : label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {filter !== "all" && (
            <button
              type="button"
              onClick={() =>
                update({ filter: "", page: "", product: "", tab: "" })
              }
            >
              Limpiar filtro
            </button>
          )}

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
              {[3, 6, 25, 50].map((size) => (
                <option key={size}>{size}</option>
              ))}
            </select>
          </label>
          {q && (
            <button
              type="button"
              onClick={() => update({ q: "", page: "", product: "", tab: "" })}
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
            <button onClick={() => setParams({})}>Restablecer filtros</button>
          </div>
        )}
        {loading && (
          <p className="i-message" role="status">
            {environmentText(
              "Consultando catálogo de prueba…",
              "Consultando catálogo capturado…",
            )}
          </p>
        )}
        {error && (
          <div className="i-message" role="alert">
            <h3>No se pudo cargar el catálogo</h3>
            <p>{error.message}</p>
            <p>
              No se utilizan cifras ni productos de demostración como reemplazo.
            </p>
            <button onClick={() => retry((value) => value + 1)}>
              Reintentar
            </button>
          </div>
        )}
        {external && !invalid && (
          <ChannelListings
            channel={view as "ml" | "tn"}
            q={q}
            page={page}
            limit={pageSize}
            linkage={linkage}
            onChange={update}
            onOpen={(id) => update({ product: id, tab: "Canales" })}
          />
        )}
        {data && !external && (
          <>
            <CatalogTable
              className="i-table"
              headings={[
                "Producto / Presentación / Ecomm ID",
                "SKU / Marca / Códigos",
                "Stock de captura",
                "Mercado Libre",
                "Tiendanube",
                "Ficha y siguiente paso",
                "Acción",
              ]}
            >
              {data.items.map((item) => (
                <tr key={item.id} data-ecomm-id={item.id}>
                  <td data-label="Producto">
                    <label className="b-checkbox">
                      <input
                        type="checkbox"
                        aria-label={`Seleccionar ${item.id}`}
                        checked={checked.has(item.id)}
                        disabled={dirty || editorBusy}
                        onChange={(event) =>
                          setChecked((current) => {
                            const next = new Set(current);
                            if (event.target.checked) next.add(item.id);
                            else next.delete(item.id);
                            return next;
                          })
                        }
                      />
                      Seleccionar variante
                    </label>
                    <strong>
                      {item.commercialName ||
                        item.name ||
                        "Nombre no disponible"}
                    </strong>
                    <small>
                      {production && !capabilities?.synthetic
                        ? "Catálogo Ecomm-App · Captura guardada"
                        : "Catálogo Ecomm-App · Datos sintéticos"}
                    </small>
                    <small>Original: {item.name ?? unavailable}</small>
                    <div className="i-presentation">
                      {item.presentation ?? unavailable}
                      <small>
                        {item.isCombo === true || item.parentIsCombo === true
                          ? "Pack / combo: revisar composición"
                          : item.isCombo === false &&
                              item.parentIsCombo === false
                            ? "Sin marca de combo · Cantidad por verificar"
                            : "Condición de combo no informada"}
                      </small>
                    </div>
                  </td>
                  <td data-label="Identidad">
                    <strong>{item.sku ?? unavailable}</strong>
                    <small>Ecomm ID: {item.id}</small>
                    <small>Marca KIKI: {item.brand || unavailable}</small>
                    <small>Barcode: {item.barcode ?? unavailable}</small>
                    <small>GTIN: {item.gtinRaw ?? unavailable}</small>
                    {!!item.identityBlockers?.length && (
                      <strong className="i-identity-warning">
                        Barcode y GTIN contradictorios · Guardado bloqueado
                      </strong>
                    )}
                  </td>

                  <td data-label="Stock de captura">
                    {item.stock ?? unavailable}
                    <small>{captureDate(item.capturedAt)}</small>
                  </td>
                  {(["ml", "tn"] as const).map((channel) => {
                    const state = item.channels?.[channel];
                    const label =
                      state?.comparisonState === "no_match"
                        ? "Sin coincidencia en esta captura"
                        : state?.evidenceState
                          ? channelLabels[state.evidenceState]
                          : !state || state.status === "UNAVAILABLE"
                            ? unavailable
                            : state.status === "NO_EXACT_SKU_IN_SNAPSHOT"
                              ? "Sin publicación confirmada"
                              : state.status === "SKU_CANDIDATE"
                                ? "Vinculación por revisar"
                                : "Revisión necesaria";
                    return (
                      <td
                        key={channel}
                        data-channel={channel}
                        data-label={
                          channel === "ml" ? "Mercado Libre" : "Tiendanube"
                        }
                      >
                        <strong>{label}</strong>
                        {!!state?.candidatesTotal && (
                          <small>
                            {state.candidatesTotal} candidatos · Identidad por
                            revisar
                          </small>
                        )}
                        {state?.snapshotAt && (
                          <small>{captureDate(state.snapshotAt)}</small>
                        )}
                        <button
                          disabled={!availableFeature("channels")}
                          onClick={() =>
                            update({ product: item.id, tab: "Canales" })
                          }
                        >
                          {state?.candidatesTotal
                            ? "Revisar candidatos"
                            : "Ver evidencia del canal"}
                        </button>
                        <small>
                          {state?.note ??
                            "Sin evidencia suficiente. No implica que no esté publicado."}
                        </small>
                      </td>
                    );
                  })}
                  <td data-label="Ficha y siguiente paso">
                    <strong>
                      {stateLabels[item.editorialStatus || ""] ?? unavailable}
                    </strong>
                    <small>{recommendedAction(item).hint}</small>
                  </td>
                  <td data-label="Acción">
                    {recommendedAction(item).label !== "Ver ficha" && (
                      <button
                        className="o-quick"
                        onClick={(event) => {
                          originRef.current = event.currentTarget;
                          update({
                            product: item.id,
                            tab: recommendedAction(item).tab,
                          });
                        }}
                      >
                        {recommendedAction(item).label}
                      </button>
                    )}
                    <button
                      className="k-open-editor"
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
            </CatalogTable>
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
            {availableFeature("batches") ? (
              <BatchPanel
                ids={checked}
                query={q}
                filter={filter}
                matches={data.matches}
                csrf={session.csrf_token}
                disabled={
                  !canWrite() || dirty || editorBusy || loading || !!selected
                }
                onClear={() => setChecked(new Set())}
                onPage={() =>
                  setChecked(
                    (current) =>
                      new Set([...current, ...data.items.map((i) => i.id)]),
                  )
                }
                onOpen={(id, proposal) =>
                  update({
                    product: id,
                    tab: proposal ? "IA" : "Ficha",
                    proposal: proposal ? String(proposal) : "",
                  })
                }
              />
            ) : (
              <p className="n-notice">
                Lotes pendientes de habilitación y esquema validado. No se
                inicia procesamiento.
              </p>
            )}
          </>
        )}
        {data && params.get("product") && !selected && (
          <p role="alert" className="i-message">
            {isAuxiliaryPilot(params.get("product")!)
              ? "Expediente auxiliar de pruebas: Ecomm ID auténtico pendiente. Usá los controles del piloto para abrirlo."
              : selectionError ||
                "Consultando la variante seleccionada por su Ecomm ID, sin cambiar la página ni sustituirla por SKU."}
            <button onClick={close}>Volver a la tabla</button>
          </p>
        )}
      </section>
      {!production && data && (
        <MamaPilotLauncher
          csrf={session.csrf_token}
          disabled={dirty || editorBusy}
          onLoaded={setMama}
          onOpen={(value) => {
            setMama(value);
            update({ product: mamaPilotId, tab: "Ficha" });
          }}
        />
      )}
      {!production && data && (
        <HileretPilotLauncher
          csrf={session.csrf_token}
          disabled={dirty || editorBusy}
          onLoaded={setHileret}
          onOpen={(value, id) => {
            setHileret(value);
            update({ product: id, tab: "Ficha" });
          }}
        />
      )}
      <p className="d-footnote">
        <Icon name="help" />
        Origen: {data?.source ?? unavailable}. El stock corresponde a la
        captura, no está en vivo.
      </p>
      {selected && (
        <ProductDrawer
          id={selected.id}
          title={selected.name ?? "Nombre no disponible"}
          subtitle={
            <>
              {isAuxiliaryPilot(selected.id)
                ? "ID SINTÉTICO de pruebas (sin Ecomm ID real): "
                : "Ecomm ID: "}
              {selected.id} · {selected.presentation ?? unavailable}
            </>
          }
          thumbnail={
            <span className="d-thumbnail">
              <Icon name="box" size={32} />
            </span>
          }
          onClose={close}
          closeRef={closeRef}
          panelRef={panelRef}
          busy={editorBusy}
          caption={
            production && capabilities?.synthetic
              ? "VALIDACIÓN SINTÉTICA · CONSULTA DE VARIANTE"
              : "CONSULTA DE VARIANTE"
          }
        >
          <PersistentWorkspace
            key={selected.id}
            proposalId={
              params.has("proposal")
                ? Number(params.get("proposal"))
                : undefined
            }
            variant={selected}
            csrf={session.csrf_token}
            username={session.username}
            tab={tab}
            onTab={(value) => update({ tab: value })}
            onDirty={setDirty}
            onBusy={setEditorBusy}
            onClose={close}
            onAuthenticated={(value) => setSession(sessionData(value))}
            onChannelsReviewed={() => {
              setPinned(selected);
              retry((value) => value + 1);
            }}
            onRecord={(value: EcommApiProductEdit) => {
              const row = dataRef.current?.items.find(
                (item) => item.id === value.ecomm_id,
              );
              if (row && row.editVersion !== value.version) {
                setPinned(row);
                retry((revision) => revision + 1);
              }
            }}
          />
        </ProductDrawer>
      )}
    </CatalogFrame>
  );
}
