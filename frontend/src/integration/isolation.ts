import { isPermittedCsvDownload } from "./csv-download";
declare const __KIKI_INTEGRATION__: boolean;
export const gatewayOrigin = "https://127.0.0.1:8443";
const allowed = new Set([
  "GET /api/auth/me",
  "GET /api/connections/status",
  "POST /api/auth/login",
  "POST /api/auth/logout",
  "GET /api/ecomm-app/stage/catalog",
  "GET /api/ecomm-app/stage/auto/status",
  "GET /api/ecomm-app/workspace/queue",
  "GET /api/ecomm-app/workspace/research/documentary-cohorts",
  "GET /api/ecomm-app/workspace/research/documentary-cohorts.csv",
  "GET /api/ecomm-app/workspace/channels/listings",
  "GET /api/ecomm-app/workspace/channels/differences.csv",
  "GET /api/ecomm-app/workspace/saved",
  "GET /api/ecomm-app/workspace/master-export",
  "GET /api/test-discovery/pilot-status",
  "GET /api/test-commercial-pilot/mama-350",
  "POST /api/test-commercial-pilot/mama-350/prepare",
  "GET /api/test-commercial-pilot/hileret-200",
  "POST /api/test-commercial-pilot/hileret-200/prepare",
]);
const connectionActions = new Set([
  "POST /api/ecomm-app/stage/manual/start",
  "POST /api/mercadolibre/auth-url",
  "POST /api/mercadolibre/sync",
  "POST /api/tiendanube/import-csv",
]);
let connectionActionsEnabled = false;
export function setConnectionActionsEnabled(value: boolean) {
  connectionActionsEnabled = value;
}

// Finite acceptance fixtures only; production uses its authenticated same-origin
// transport. No supplier, arbitrary-ID, image, video or redirect origin is allowed.
const commercialFixtureIds = new Set([
  ...Array.from({length: 6}, (_, i) => String(900001+i)),
  ...Array.from({length: 20}, (_, i) => String(9104001+i)),
  "9104091", "9104092", "9104093", "7518949",
]);
function commercialReviewRequest(method: string, path: string): boolean {
  const root = "/api/ecomm-app/workspace/";
  if (method === "GET" && (path === root+"taxonomy/catalog" || /^\/api\/ecomm-app\/workspace\/(?:research\/automation(?:\/(?:capabilities|[a-f0-9-]{36}))?|reports\/periodic\/(?:policy|tasks|automation))$/.test(path))) return true;
  if (method === "POST" && /^\/api\/ecomm-app\/workspace\/(?:research\/automation(?:\/[a-f0-9-]{36}\/(?:step|recover|retry|cancel|proposals|select-source))?|reports\/periodic\/policy)$/.test(path)) return true;
  if (method === "POST" && ["commercial-review/preview", "commercial-review/apply", "taxonomy/catalog", "taxonomy/review-preview", "taxonomy/review-batch", "exports/commercial/preview", "exports/commercial/download"].some(s => path===root+s)) return true;
  if (!path.startsWith(root)) return false;
  const [id,...parts] = path.slice(root.length).split("/");
  if (!commercialFixtureIds.has(id)) return false;
  const suffix = parts.join("/");
  if (method === "GET") return ["", "evidence", "proposals", "proposals/generation-context", "taxonomy-review", "media-review", "commercial-coverage", "channels"].includes(suffix);
  return method === "POST" && (["", "taxonomy-review", "proposals/generate", "evidence/extract", "evidence/facts/review-batch"].includes(suffix) || /^(?:documents\/local-[a-f0-9]{32}\/(?:media-rights|provenance)|proposals\/[1-9][0-9]{0,9}\/review|evidence\/facts\/[a-f0-9]{24}\/review)$/.test(suffix));
}

export function installIntegrationIsolation() {
  const nativeFetch = window.fetch.bind(window);
  // Install the deny boundary even if validation fails. No automatic demo fallback.
  let configured = false;
  window.fetch = async (input, init) => {
    const url = new URL(
      input instanceof Request ? input.url : String(input),
      location.origin,
    );
    const method = (
      init?.method || (input instanceof Request ? input.method : "GET")
    ).toUpperCase();
    if (
      !configured ||
      url.origin !== gatewayOrigin ||
      url.username ||
      url.password ||
      !(
        allowed.has(`${method} ${url.pathname}`) ||
        commercialReviewRequest(method, url.pathname) ||
        (connectionActionsEnabled &&
          connectionActions.has(`${method} ${url.pathname}`)) ||
        (method === "POST" &&
          /^\/api\/ecomm-app\/workspace\/90000[1-6]\/confirm-review$/.test(
            url.pathname,
          )) ||
        (method === "GET" &&
          /^\/api\/ecomm-app\/workspace\/ai\/90000[1-6]\/latest$/.test(
            url.pathname,
          )) ||
        (method === "GET" &&
          /^\/api\/ecomm-app\/editorial-batches(?:\/[a-f0-9-]{36})?$/.test(
            url.pathname,
          )) ||
        (method === "POST" &&
          /^\/api\/ecomm-app\/editorial-batches\/(?:preview|[a-f0-9-]{36}\/(?:start|step|cancel|retry))$/.test(
            url.pathname,
          )) ||
        (method === "GET" &&
          /^\/api\/ecomm-app\/workspace\/90000[1-6]\/channels$/.test(
            url.pathname,
          )) ||
        (method === "POST" &&
          /^\/api\/ecomm-app\/workspace\/90000[1-6]\/channels\/review$/.test(
            url.pathname,
          )) ||
        (method === "GET" &&
          /^\/api\/ecomm-app\/workspace\/90000[1-6]\/(?:evidence|proposals(?:\/generation-context)?|documents\/local-[a-f0-9]{32}\/original\/[1-8])$/.test(
            url.pathname,
          )) ||
        (method === "POST" &&
          /^\/api\/ecomm-app\/workspace\/90000[1-6]\/(?:evidence\/(?:extract|facts\/[a-f0-9]{24}\/review)|documents\/(?:import|local-[a-f0-9]{32}\/provenance)|proposals\/(?:generate|[1-9][0-9]{0,9}\/review))$/.test(
            url.pathname,
          )) ||
        (["GET", "POST"].includes(method) &&
          /^\/api\/ecomm-app\/workspace\/(?:90000[1-6]|PILOT-MAMA-350-SYNTHETIC|PILOT-HILERET-200-(?:UNIT|PACK6)-SYNTHETIC)$/.test(
            url.pathname,
          )) ||
        (method === "GET" &&
          /^\/api\/test-research\/(?:90000[1-6]|PILOT-MAMA-350-SYNTHETIC|PILOT-HILERET-200-(?:UNIT|PACK6)-SYNTHETIC)$/.test(
            url.pathname,
          )) ||
        (method === "POST" &&
          /^\/api\/test-discovery\/90000[1-6]\/(?:start|candidates\/[a-f0-9]{24}\/(?:decision|acquire))$/.test(
            url.pathname,
          )) ||
        (method === "GET" &&
          /^\/api\/test-documents\/(?:90000[1-6]|PILOT-MAMA-350-SYNTHETIC|PILOT-HILERET-200-(?:UNIT|PACK6)-SYNTHETIC)\/local-[a-f0-9]{32}\/original\/[1-8]$/.test(
            url.pathname,
          )) ||
        (method === "POST" &&
          /^\/api\/test-documents\/(?:90000[1-6]|PILOT-MAMA-350-SYNTHETIC|PILOT-HILERET-200-(?:UNIT|PACK6)-SYNTHETIC)\/(?:import|local-[a-f0-9]{32}\/provenance)$/.test(
            url.pathname,
          )) ||
        (method === "GET" &&
          /^\/api\/test-proposals\/(?:90000[1-6]|PILOT-MAMA-350-SYNTHETIC|PILOT-HILERET-200-(?:UNIT|PACK6)-SYNTHETIC)(?:\/generation-context)?$/.test(
            url.pathname,
          )) ||
        (method === "POST" &&
          /^\/api\/test-proposals\/(?:90000[1-6]|PILOT-MAMA-350-SYNTHETIC|PILOT-HILERET-200-(?:UNIT|PACK6)-SYNTHETIC)\/(?:generate|[1-9][0-9]{0,9}\/review)$/.test(
            url.pathname,
          )) ||
        (method === "POST" &&
          /^\/api\/test-research\/(?:(?:90000[1-6]|PILOT-MAMA-350-SYNTHETIC|PILOT-HILERET-200-(?:UNIT|PACK6)-SYNTHETIC)\/(?:extract|facts\/[a-z0-9.:%-]{1,200}\/review)|documents\/[a-z0-9-]{1,80}\/revision)$/.test(
            url.pathname,
          ))
      )
    ) {
      throw new Error("Integración aislada: solicitud no autorizada.");
    }
    return nativeFetch(input, {
      ...init,
      credentials: "same-origin",
      mode: "same-origin",
      redirect: "error",
      cache: "no-store",
    });
  };
  XMLHttpRequest.prototype.open = function () {
    throw new Error("Transporte no autorizado.");
  };
  navigator.sendBeacon = () => false;
  window.open = () => null;
  window.WebSocket = class {
    constructor() {
      throw new Error("Sockets bloqueados.");
    }
  } as unknown as typeof WebSocket;
  window.EventSource = class {
    constructor() {
      throw new Error("Streams bloqueados.");
    }
  } as unknown as typeof EventSource;
  document.addEventListener(
    "click",
    (event) => {
      const anchor =
        event.target instanceof Element
          ? event.target.closest("a[href]")
          : null;
      if (!(anchor instanceof HTMLAnchorElement)) return;
      if (isPermittedCsvDownload(anchor)) return;
      const url = new URL(anchor.href, location.origin);
      if (
        url.origin === gatewayOrigin &&
        url.pathname === "/api/ecomm-app/workspace/master-export" &&
        !url.search &&
        anchor.hasAttribute("download") &&
        anchor.dataset.kikiDownload === "master-export"
      )
        return;
      if (url.origin !== gatewayOrigin || url.pathname !== "/") {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );
  const markers = document.querySelectorAll('meta[name="kiki-environment"]');
  if (
    typeof __KIKI_INTEGRATION__ === "undefined" ||
    __KIKI_INTEGRATION__ !== true ||
    location.origin !== gatewayOrigin ||
    markers.length !== 1 ||
    markers[0].getAttribute("content") !== "local-synthetic"
  ) {
    throw new Error(
      "Configuración de integración incompleta o ambigua. No se cargó ningún catálogo.",
    );
  }
  configured = true;
}
