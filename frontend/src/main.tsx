import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./LegacyApp";
import { PrototypeDashboard, LegacyNotice } from "./prototype/Dashboard";
import { installIsolation } from "./prototype/isolation";
installIsolation();
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App
      prototypeSession
      dashboard={<PrototypeDashboard />}
      notice={<LegacyNotice />}
    />
  </React.StrictMode>,
);
