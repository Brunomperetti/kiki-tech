// Defensa adicional al CSP y al servidor sin proxy. No existe un flag de escape.
export function installIsolation() {
  window.fetch = async (input, init) => {
    // Empty synthetic history lets legacy import screens render without a backend.
    const url = new URL(
      input instanceof Request ? input.url : String(input),
      location.origin,
    );
    const method =
      init?.method || (input instanceof Request ? input.method : "GET");
    if (url.pathname === "/api/imports" && method.toUpperCase() === "GET") {
      return new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error("Prototipo aislado: solicitudes deshabilitadas.");
  };
  XMLHttpRequest.prototype.open = function () {
    throw new Error("Prototipo aislado: solicitudes deshabilitadas.");
  };
  window.open = () => null;
  document.addEventListener(
    "click",
    (event) => {
      const anchor =
        event.target instanceof Element
          ? event.target.closest("a[href]")
          : null;
      if (!(anchor instanceof HTMLAnchorElement)) return;
      const url = new URL(anchor.href, location.origin);
      if (
        url.origin !== location.origin ||
        /^\/(api(?:\/|$)|health(?:\/|$))/.test(url.pathname)
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );
  navigator.sendBeacon = () => false;
  window.WebSocket = class {
    constructor() {
      throw new Error("Prototipo aislado: sockets deshabilitados.");
    }
  } as unknown as typeof WebSocket;
  window.EventSource = class {
    constructor() {
      throw new Error("Prototipo aislado: streams deshabilitados.");
    }
  } as unknown as typeof EventSource;
}
