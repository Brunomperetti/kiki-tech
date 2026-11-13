import { useEffect, useState } from "react";
import { request } from "./catalog-adapter";

type Status = {
  schema_version: string;
  network_enabled: boolean;
  release_locked: boolean;
  authorized_products: string[];
  authorized_domains: string[];
  openai_enabled: boolean;
  message: string;
};
export function PilotReadiness() {
  const [status, setStatus] = useState<Status>();
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    request("/api/test-discovery/pilot-status", { signal: controller.signal })
      .then((r) => r.json())
      .then((v: Status) => {
        if (
          v.schema_version !== "kiki-pilot-v1" ||
          v.network_enabled !== false ||
          v.release_locked !== true ||
          v.openai_enabled !== false ||
          !Array.isArray(v.authorized_products) ||
          !Array.isArray(v.authorized_domains)
        )
          throw new Error(
            "Estado de aislamiento incompatible; no se habilitó acceso externo.",
          );
        setStatus(v);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <section
      className="r-document"
      aria-label="Preparación del piloto documental"
    >
      <h3>Piloto con documentación auténtica</h3>
      <p>
        <strong>Consulta externa desactivada · IA externa desactivada</strong>
      </p>
      {error && <p role="alert">{error}</p>}
      {status && (
        <>
          <p>{status.message}</p>
          <p>
            Productos auténticos autorizados:{" "}
            {status.authorized_products.length} · Dominios autorizados:{" "}
            {status.authorized_domains.length}
          </p>
        </>
      )}
      <p>
        <strong>A. Documento suministrado:</strong> usá «Incorporar archivo
        local o referencia oficial» más abajo. Registrá cómo lo obtuviste y
        revisá identidad, procedencia y cada dato por separado. No se descarga
        la URL.
      </p>
      <p>
        <strong>B. Fuente oficial en Internet:</strong> pendiente de
        autorización de productos y dominios, revisión de condiciones del sitio
        y habilitación posterior del conector aislado.
      </p>
      <button disabled>
        Obtener documento desde una fuente oficial · No habilitado
      </button>
      <p>
        El recorrido de demostración que sigue utiliza exclusivamente fuentes
        simuladas; no constituye un piloto con productos reales.
      </p>
    </section>
  );
}
