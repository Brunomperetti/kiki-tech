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
// The classic application is retired. Every legacy URL uses the same v2
// application and session; legacy code is never imported into production.
if (location.pathname !== "/v2/")
  history.replaceState(null, "", "/v2/" + location.search + location.hash);
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Suspense fallback={<p role="status">Cargando KIKI Tech…</p>}>
      <BrowserRouter basename="/v2">
        <Catalog />
      </BrowserRouter>
    </Suspense>
  </React.StrictMode>,
);
