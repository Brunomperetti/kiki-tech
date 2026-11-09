import { useEffect, useRef } from "react";
export function SettingsDialog({
  advanced,
  showPrices,
  onAdvanced,
  onPrices,
  onClose,
}: {
  advanced: boolean;
  showPrices: boolean;
  onAdvanced: (v: boolean) => void;
  onPrices: (v: boolean) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      className="s-settings"
      ref={ref}
      aria-label="Configuración del catálogo"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <h2>Configuración del catálogo</h2>
      <p>Preferencias de esta sesión. No cambian tus productos.</p>
      <label>
        <input
          type="checkbox"
          checked={showPrices}
          onChange={(e) => onPrices(e.target.checked)}
        />
        Mostrar precios en la tabla
      </label>
      <label>
        <input
          type="checkbox"
          checked={advanced}
          onChange={(e) => onAdvanced(e.target.checked)}
        />
        Mostrar filtros y detalles avanzados
      </label>
      <p className="o-warning">
        Modo demostración: datos simulados y conexiones bloqueadas. No se
        necesitan credenciales.
      </p>
      <button className="d-primary" onClick={onClose}>
        Volver a Mi catálogo
      </button>
    </dialog>
  );
}
