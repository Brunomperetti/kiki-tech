import type { ChannelComparison, QueueFilter } from "./catalog-adapter";
import "./commercial-views.css";

type Channel = "ml" | "tn";

/** A short, actionable business summary. Historical capture absence ≠ unpublished today. */
export function ChannelGapSummary({
  comparison,
  onForward,
  onReverse,
  filter,
  view,
  linkage,
}: {
  comparison?: Record<Channel, ChannelComparison>;
  onForward: (channel: Channel) => void;
  onReverse: (channel: Channel) => void;
  filter: QueueFilter;
  view: string;
  linkage: string;
}) {
  const cards = [
    {
      key: "ml" as const,
      label: "En Ecomm-App, sin coincidencia en Mercado Libre",
      value: comparison?.ml.variant_states.no_match,
      detail: "Variantes Ecomm no encontradas en la captura ML",
      action: () => onForward("ml"),
      active: filter === "ml_comparison_no_match",
      primary: true,
    },
    {
      key: "tn" as const,
      label: "En Ecomm-App, sin coincidencia en Tiendanube",
      value: comparison?.tn.variant_states.no_match,
      detail: "Variantes Ecomm no encontradas en el CSV TN",
      action: () => onForward("tn"),
      active: filter === "tn_comparison_no_match",
      primary: true,
    },
    {
      key: "ml-reverse" as const,
      label: "En Mercado Libre, sin candidato en Ecomm-App",
      value: comparison?.ml.records_without_candidate,
      detail: "Registros ML sin variante Ecomm candidata",
      action: () => onReverse("ml"),
      active: view === "ml" && linkage === "no_match",
      primary: false,
    },
    {
      key: "tn-reverse" as const,
      label: "En Tiendanube, sin candidato en Ecomm-App",
      value: comparison?.tn.records_without_candidate,
      detail: "Registros TN sin variante Ecomm candidata",
      action: () => onReverse("tn"),
      active: view === "tn" && linkage === "no_match",
      primary: false,
    },
  ];
  return (
    <section className="k-business-gaps" aria-label="Diferencias principales entre catálogos">
      <div className="k-business-gaps-title">
        <div>
          <h2>Productos para revisar por canal</h2>
          <p>Dos direcciones, sin mezclar productos Ecomm con publicaciones o registros de canales.</p>
        </div>
      </div>
      <div className="k-business-gaps-grid">
        {cards.map(card => (
          <button
            key={card.key}
            type="button"
            className={"k-business-gap-card" + (card.primary ? " k-business-gap-primary" : "")}
            aria-pressed={card.active}
            onClick={card.action}
          >
            <span>{card.label}</span>
            <strong>{card.value === undefined ? "—" : card.value.toLocaleString("es-AR")}</strong>
            <small>{card.detail}</small>
            <b>Ver lista →</b>
          </button>
        ))}
      </div>
      <p className="k-business-gaps-note">
        Son <strong>diferencias detectadas en capturas históricas</strong>, no prueba de productos
        actualmente sin publicar. Las capturas de ML y Tiendanube deben actualizarse para
        verificar el estado actual.
      </p>
    </section>
  );
}
