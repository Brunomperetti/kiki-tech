import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "../styles.css";
import "../prototype/dashboard.css";
import "../prototype/operations.css";
import "../prototype/simple-dashboard.css";
import "../prototype/channel-dashboard.css";

// Separate build entry: never imports the demo controller, fixtures or its isolation switch.
const Catalog = lazy(() =>
  import("../integration/IntegrationCatalog").then((m) => ({
    default: m.IntegrationCatalog,
  })),
);
const Legacy = lazy(() =>
  import("../LegacyApp").then((m) => ({ default: m.App })),
);
const v2 = /^\/v2(?:\/|$)/.test(location.pathname);
if (v2 && location.pathname !== "/v2/")
  history.replaceState(null, "", "/v2/" + location.search + location.hash);
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Suspense fallback={<p role="status">Cargando KIKI Tech…</p>}>
      {v2 ? (
        <BrowserRouter basename="/v2">
          <Catalog />
        </BrowserRouter>
      ) : (
        <Legacy
          notice={
            <p className="n-notice">
              <a href="/v2/">Abrir KIKI Tech 2.0</a>
            </p>
          }
        />
      )}
    </Suspense>
  </React.StrictMode>,
);
