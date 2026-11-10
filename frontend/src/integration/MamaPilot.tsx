import { useEffect, useState } from "react";
import { loadMama, type MamaReport } from "./mama-pilot";

export function MamaPilotLauncher({
  csrf,
  disabled,
  onLoaded,
  onOpen,
}: {
  csrf: string;
  disabled: boolean;
  onLoaded: (v: MamaReport) => void;
  onOpen: (v: MamaReport) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    loadMama(controller.signal)
      .then((v) => {
        if (!controller.signal.aborted) onLoaded(v);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <section className="r-document" aria-label="Piloto comercial MAMA">
      <strong>Primer piloto comercial · MAMA 350 g / 10 mm</strong>
      <p>
        Referencia auxiliar del cliente. Ecomm ID real pendiente; no forma parte
        del catálogo maestro ni modifica sus indicadores.
      </p>
      <button
        disabled={disabled || busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            onOpen(await loadMama(undefined, csrf));
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Abrir expediente MAMA de pruebas
      </button>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
const labels: Record<string, string> = {
  title: "Título comercial",
  short_description: "Descripción corta",
  description: "Descripción larga",
  details: "Características",
  presentation: "Presentación",
  category: "Categoría",
  subcategory: "Subcategoría",
  seo_title: "Título SEO",
  seo_description: "Descripción SEO",
  note: "Nota del operador",
};
export function MamaPilotSummary({ revision = 0 }: { revision?: number }) {
  const [data, setData] = useState<MamaReport>();
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    loadMama(controller.signal)
      .then((v) => {
        if (!controller.signal.aborted) setData(v);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [revision]);
  if (error) return <p role="alert">{error}</p>;
  if (!data?.available)
    return <p role="status">Consultando expediente MAMA…</p>;
  const excel = data.references.excel,
    candidate = data.references.manufacturer_candidate;
  return (
    <section
      className="r-document"
      aria-label="Expediente comercial MAMA 350 g"
    >
      <h3>MAMA 350 g / 10 mm · Piloto aislado</h3>
      <p className="r-notice">
        <strong>Identificador SINTÉTICO de pruebas: {data.test_id}</strong>
        <br />
        Ecomm ID auténtico: pendiente. Sin vinculación por SKU o EAN. Sólo
        borradores locales.
      </p>
      <details open>
        <summary>Datos de identificación y procedencia</summary>
        <p>
          {excel.file_name}, fila {excel.row} · {excel.source}. No se recibió el
          archivo original: sin hash del Excel.
        </p>
        <p>
          Nombre: {excel.name} · Marca declarada: {excel.brand}
        </p>
        <p>
          EAN declarado: {excel.declared_ean} · Comprobación matemática:{" "}
          {excel.ean_checksum_valid ? "válida" : "inválida"}. Correspondencia
          oficial con esta variante: pendiente.
        </p>
        <p>
          SKU del archivo: {excel.file_sku} · Sólo referencia; no identifica ni
          vincula la variante.
        </p>
        <p>
          Presentación declarada: {excel.declared_presentation} · Ancho
          declarado: {excel.declared_width}.
        </p>
        <p>
          Peso logístico: {excel.logistic_weight}. No es contenido neto
          verificado.
        </p>
      </details>
      <details open>
        <summary>Referencia oficial candidata · Sin descargar</summary>
        <p>
          {candidate.manufacturer} · {candidate.catalog_item_reported}
        </p>
        <p style={{ overflowWrap: "anywhere" }}>{candidate.url}</p>
        <p>
          {candidate.source}. Sin fecha de consulta ni hash de documento. No
          confirma EAN, ingredientes, alérgenos, nutrientes ni «sin gluten».
        </p>
      </details>
      <p>
        <strong>{data.approved_fact_count} hechos aprobados.</strong>{" "}
        {data.approved_fact_count === 0 &&
          "Propuesta comercial bloqueada: faltan documentos auténticos específicos y revisión de hechos."}
      </p>
      <details open>
        <summary>Evidencia pendiente y siguientes pasos</summary>
        <ul>
          {data.references.missing_evidence.map((v) => (
            <li key={v}>{v}</li>
          ))}
        </ul>
        <p>
          En Evidencias podés incorporar una copia local auténtica y autorizada
          mediante el lector existente. Una referencia URL no contiene un
          documento para extraer.
        </p>
      </details>
      <details>
        <summary>Comparación inicial / guardado local</summary>
        {Object.entries(labels).map(([key, label]) => (
          <p key={key}>
            <strong>{label}</strong>
            <br />
            Inicial:{" "}
            {String(
              data.initial_fields[key as keyof typeof data.initial_fields] ||
                "Sin completar",
            )}
            <br />
            Guardado:{" "}
            {String(
              data.current_fields[key as keyof typeof data.current_fields] ||
                "Sin completar",
            )}
            {data.blocked_fields.includes(key) && " · Sin propuesta respaldada"}
          </p>
        ))}
      </details>
    </section>
  );
}
