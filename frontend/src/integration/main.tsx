import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { PrototypeDashboard } from "../prototype/Dashboard";
import { installIntegrationIsolation } from "./isolation";
import "../styles.css";

const root = ReactDOM.createRoot(document.getElementById("root")!);
try {
  installIntegrationIsolation();
  root.render(
    <React.StrictMode>
      <BrowserRouter>
        <PrototypeDashboard mode="integration" />
      </BrowserRouter>
    </React.StrictMode>,
  );
} catch (error) {
  root.render(
    <main className="login-page">
      <section className="login-card" role="alert">
        <h1>Integración bloqueada</h1>
        <p>
          {error instanceof Error
            ? error.message
            : "Configuración no autorizada."}
        </p>
      </section>
    </main>,
  );
}
