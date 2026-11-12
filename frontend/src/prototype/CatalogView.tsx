import type { ReactNode, Ref } from "react";
import { Link } from "react-router-dom";
import { KikiIcon as Icon } from "../components/KikiIcon";

// Both controllers supply their own data/actions. This view never imports fixtures,
// fetches, authenticates, or chooses a fallback data source.
export function CatalogFrame({
  mode,
  children,
  onCatalog,
  onHistory,
  onSettings,
  onLogout,
  busy,
  action,
  connectionStatus,
}: {
  mode: "demo" | "integration";
  children: ReactNode;
  onCatalog: () => void;
  onHistory?: () => void;
  onSettings?: () => void;
  onLogout?: () => void;
  busy?: boolean;
  action?: ReactNode;
  connectionStatus?: ReactNode;
}) {
  const connected = mode === "integration";
  return (
    <div
      className={`d-app${connected ? " i-app" : ""}`}
      data-dashboard-mode={mode}
    >
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
            KIKI Market
            <small>
              {connected ? "Integración de prueba" : "Espacio de trabajo"}
            </small>
          </div>
        </div>
        <small className="d-nav-label">TU ESPACIO DE TRABAJO</small>
        <nav
          aria-label={
            connected ? "Navegación del catálogo" : "Navegación del prototipo"
          }
        >
          <button className="d-active" onClick={onCatalog}>
            <Icon name="box" /> Mi catálogo
          </button>
          <button
            disabled={!onHistory}
            title={
              onHistory
                ? undefined
                : "Seleccioná una variante para consultar su historial"
            }
            onClick={onHistory}
          >
            <Icon name="clock" /> Historial
          </button>
          <button
            disabled={!onSettings}
            title={
              onSettings
                ? undefined
                : "Configuración de negocio todavía no integrada"
            }
            onClick={onSettings}
          >
            <Icon name="layers" /> Configuración
          </button>
        </nav>
        <div className="d-sidebar-bottom">
          <Icon name="shield" />
          <strong>
            {connected ? "Entorno aislado" : "Tu catálogo, bajo control"}
          </strong>
          <p>
            {connected
              ? "Catálogo sintético y archivos locales autorizados. Sin publicaciones externas."
              : "Vos revisás y decidís cada cambio."}
          </p>
          <span>
            {connected
              ? "Trabajo local · Sin conexión productiva"
              : "Demostración visual · Sin backend"}
          </span>
        </div>
      </aside>
      <div className="d-body">
        <header className="d-topbar">
          <span>
            Espacio de trabajo / <strong>Mi catálogo</strong>
          </span>
          <div>
            {onSettings && (
              <button
                className="n-shortcut"
                onClick={onSettings}
                aria-label="Centro de conexiones"
              >
                {connectionStatus || "Conexiones"}
              </button>
            )}
            <span className="d-demo-dot" />
            {connected
              ? "Conectado · Entorno aislado"
              : "Datos de demostración"}
            {onLogout && (
              <button onClick={onLogout} disabled={busy}>
                Cerrar sesión
              </button>
            )}
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
                Consultá, revisá y prepará tus productos desde el mismo espacio
                de trabajo.
              </p>
            </div>
            {action}
          </div>
          <div className="d-demo">
            <Icon name="shield" />
            <span>
              <strong>
                {connected
                  ? "Modo integración · Conectado a FastAPI de pruebas."
                  : "Modo demostración."}
              </strong>{" "}
              {connected
                ? "Variantes sintéticas guardadas en PostgreSQL descartable. Sin conexión a proveedores."
                : "Productos ficticios, sin conexiones ni cambios en tus sistemas."}
            </span>
            <span className="d-demo-tag">ENTORNO AISLADO</span>
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}

export function CatalogTable({
  headings,
  children,
  className = "",
}: {
  headings: ReactNode[];
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className="d-table-scroll">
      <table className={`d-table ${className}`}>
        <thead>
          <tr>
            {headings.map((heading, index) => (
              <th key={index}>{heading}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export type Metric = {
  id: string;
  title: string;
  value: ReactNode;
  note: ReactNode;
  active?: boolean;
  onClick?: () => void;
  testId?: string;
};
export function CatalogMetrics({
  cards,
  label,
}: {
  cards: Metric[];
  label: string;
}) {
  return (
    <section className="d-metrics c-metrics" aria-label={label}>
      {cards.map((card) => (
        <button
          key={card.id}
          data-metric={card.id}
          data-testid={card.testId}
          className={`d-metric ${card.id === "all" ? "c-central" : ""}`}
          aria-pressed={card.onClick ? !!card.active : undefined}
          disabled={!card.onClick}
          onClick={card.onClick}
        >
          <span>{card.title}</span>
          <strong>{card.value}</strong>
          <small>{card.note}</small>
        </button>
      ))}
    </section>
  );
}

export function CatalogSearch({
  id,
  value,
  onChange,
  placeholder,
  maxLength,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  maxLength?: number;
}) {
  return (
    <label className="d-search">
      <Icon name="search" />
      <input
        id={id}
        aria-label="Buscar productos"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
      />
    </label>
  );
}

export function ProductDrawer({
  id,
  title,
  subtitle,
  thumbnail,
  children,
  onClose,
  closeRef,
  panelRef,
  busy,
  caption = "DETALLE DEL PRODUCTO",
  dialogLabel,
  closeLabel = "Cerrar ficha",
}: {
  id: string;
  title: ReactNode;
  subtitle: ReactNode;
  thumbnail: ReactNode;
  children: ReactNode;
  onClose: () => void;
  closeRef: Ref<HTMLButtonElement>;
  panelRef: Ref<HTMLElement>;
  busy?: boolean;
  caption?: string;
  dialogLabel?: string;
  closeLabel?: string;
}) {
  return (
    <>
      <div className="d-backdrop" onClick={onClose} />
      <section
        className="d-drawer"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={dialogLabel ?? `Ficha ${id}`}
      >
        <div className="d-drawer-top">
          <span>{caption}</span>
          <button
            ref={closeRef}
            onClick={onClose}
            disabled={busy}
            aria-label={closeLabel}
          >
            ×
          </button>
        </div>
        <div className="d-drawer-title">
          {thumbnail}
          <div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
        </div>
        {children}
      </section>
    </>
  );
}
