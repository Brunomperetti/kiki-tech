declare const __KIKI_INTEGRATION__: boolean;
export const gatewayOrigin = "https://127.0.0.1:8443";
const allowed = new Set([
  "GET /api/auth/me",
  "POST /api/auth/login",
  "POST /api/auth/logout",
  "GET /api/ecomm-app/stage/catalog",
]);

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
        (["GET", "POST"].includes(method) &&
          /^\/api\/ecomm-app\/workspace\/90000[1-6]$/.test(url.pathname))
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
      const url = new URL(anchor.href, location.origin);
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
