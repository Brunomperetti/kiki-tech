import { useEffect, useRef } from "react";
export function SettingsDialog({
  advanced,
  showPrices,
  onAdvanced,
  onPrices,
  onClose,
  connected = false,
}: {
  advanced: boolean;
  showPrices: boolean;
  onAdvanced: (v: boolean) => void;
  onPrices: (v: boolean) => void;
  onClose: () => void;
  connected?: boolean;
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
      {!connected && (
        <label>
          <input
            type="checkbox"
            checked={showPrices}
            onChange={(e) => onPrices(e.target.checked)}
          />
          Mostrar precios en la tabla
        </label>
      )}
      <label>
        <input
          type="checkbox"
          checked={advanced}
          onChange={(e) => onAdvanced(e.target.checked)}
        />
        Mostrar filtros y detalles avanzados
      </label>
      <p className="o-warning">
        {connected
          ? "Backend aislado con autenticación de prueba. OpenAI real e investigación externa desactivados. Estas preferencias no modifican integraciones, credenciales ni presupuestos."
          : "Modo demostración: datos simulados y conexiones bloqueadas. No se necesitan credenciales."}
      </p>
      {connected && (
        <a
          href="/api/ecomm-app/workspace/master-export"
          download="fichas-kiki-pruebas.json"
          data-kiki-download="master-export"
        >
          Descargar fichas guardadas · JSON
        </a>
      )}
      <button className="d-primary" onClick={onClose}>
        Volver a Mi catálogo
      </button>
    </dialog>
  );
}
