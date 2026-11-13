import { useEffect, useState } from "react";
import {
  hileretUnitId,
  hileretPackId,
  loadHileret,
  type HileretReport,
} from "./hileret-pilot";

export function HileretPilotLauncher({
  csrf,
  disabled,
  onLoaded,
  onOpen,
}: {
  csrf: string;
  disabled: boolean;
  onLoaded: (report: HileretReport) => void;
  onOpen: (report: HileretReport, id: string) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    loadHileret(controller.signal)
      .then((v) => {
        if (!controller.signal.aborted) {
          onLoaded(v);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <section className="r-document" aria-label="Piloto comercial Hileret">
      <strong>Piloto documental · Hileret Stevia</strong>
      <p>
        Unidad y pack x6 separados. Ecomm ID real pendiente. No forman parte del
        catálogo maestro ni modifican sus indicadores.
      </p>
      <p>
        Incorporación manual desde Evidencias. Cada expediente muestra el
        original conservado, sus citas y las revisiones pendientes. Una URL no
        equivale a un documento procesado.
      </p>
      {[
        [hileretUnitId, "unidad"],
        [hileretPackId, "pack x6"],
      ].map(([id, label]) => (
        <button
          key={id}
          disabled={disabled || busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              const value = await loadHileret(undefined, csrf);
              onOpen(value, id);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Abrir Hileret {label} de pruebas
        </button>
      ))}
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
export function HileretPilotSummary({
  id,
  revision = 0,
}: {
  id: string;
  revision?: number;
}) {
  const [report, setReport] = useState<HileretReport>(),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setReport(undefined);
    setError("");
    loadHileret(controller.signal)
      .then((v) => {
        if (!controller.signal.aborted) setReport(v);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [id, revision]);
  if (error) return <p role="alert">{error}</p>;
  const data = report?.cases.find((c) => c.test_id === id);
  if (!data) return <p role="status">Consultando expediente Hileret…</p>;
  const { excel, brochure } = data.references;
  return (
    <section className="r-document" aria-label="Expediente comercial Hileret">
      <h3>
        Hileret Stevia ·{" "}
        {data.references.sale_units === 1
          ? "Unidad 200 ml"
          : "Pack comercial x6 de 200 ml"}
      </h3>
      <p className="r-notice" style={{ overflowWrap: "anywhere" }}>
        <strong>Identificador SINTÉTICO de pruebas: {id}</strong>
        <br />
        Ecomm ID auténtico: pendiente. Sin vinculación ni fusión por SKU o EAN.
        Sólo borradores locales.
      </p>
      <details open>
        <summary>Identificación auxiliar del cliente</summary>
        <p>
          productos.xlsx, fila {excel.row}: {excel.name}, {excel.presentation}.
          EAN declarado: {excel.ean_declared}.
        </p>
        <p>
          {excel.source} No se infieren celdas, composición ni correspondencia
          oficial.
        </p>
      </details>
      <details open>
        <summary>
          Folleto oficial informado · Página {brochure.reported_page}
        </summary>
        <p style={{ overflowWrap: "anywhere" }}>{brochure.url}</p>
        <p>Referencia declarada al preparar el expediente: {brochure.source}</p>
        {!data.original_pdf_available ? (
          <p role="status">
            <strong>Bloqueado: PDF original no disponible.</strong> Sin
            descarga, SHA-256 de archivo, extracción ni citas procesadas.
            Incorporá manualmente el PDF auténtico desde Evidencias; no se
            consulta la URL.
          </p>
        ) : (
          <p>
            PDF local incorporado. Revisá original, procedencia, texto y
            ubicaciones en Evidencias antes de aprobar. Tener bytes no confirma
            por sí solo autenticidad ni identidad.
          </p>
        )}
        <p>
          {data.ean_verified_in_test
            ? "Contrastado y aprobado en el recorrido de pruebas; no es aprobación efectiva del cliente:"
            : "Informado por el usuario, pendiente de contraste:"}{" "}
          {brochure.reported_product}, {brochure.reported_unit_volume}, EAN{" "}
          {brochure.reported_unit_ean}.
        </p>
      </details>
      <details open>
        <summary>Unidad, pack y caja logística</summary>
        <ul>
          <li>Unidad individual: 200 ml; referencia del Excel, fila 28.</li>
          <li>
            Pack comercial x6: 6 unidades de 200 ml; referencia distinta, fila
            27. Requiere respaldo específico del pack.
          </li>
          <li>
            Caja logística x9: {brochure.reported_logistic_units} unidades de
            200 ml, según folleto informado; no es el pack x6.
          </li>
          <li>
            DUN logístico {brochure.reported_logistic_dun}: no es el EAN
            individual {brochure.reported_unit_ean}.
          </li>
        </ul>
        <p>
          Compartir EAN no demuestra identidad de variante ni autoriza copiar
          una ficha entre unidad y pack.
        </p>
      </details>
      <p>
        <strong>{data.approved_fact_count} hechos aprobados.</strong>{" "}
        {data.approved_fact_count === 0 &&
          (data.original_pdf_available
            ? "Propuesta bloqueada: identidad y aprobación individual pendientes; incorporar un PDF no aprueba hechos."
            : "Propuesta bloqueada: faltan original, identidad y revisión de evidencias. Ninguna afirmación comercial aprobada.")}
        {data.approved_fact_count > 0 &&
          " Las decisiones del operador de prueba permiten demostrar el flujo; no sustituyen la aprobación humana efectiva del cliente."}
      </p>
      {data.documents
        .filter((d) => d.original)
        .map((d) => (
          <p key={d.id} style={{ overflowWrap: "anywhere" }}>
            {d.original!.filename} · SHA-256: {d.original!.sha256} ·{" "}
            {d.parse_status} · Procedencia: {d.source_review_state}. Ubicaciones
            extraídas: {d.locations.length}.
          </p>
        ))}
      <details>
        <summary>Documentación pendiente</summary>
        <ul>
          {(data.pending_evidence || data.references.missing_evidence).map(
            (v) => (
              <li key={v}>{v}</li>
            ),
          )}
        </ul>
      </details>
      <p>
        Ingredientes, alérgenos, nutrición, certificaciones, beneficios y «sin
        gluten»: pendientes de documentación específica y vigente. El folleto no
        acredita toda la composición.
      </p>
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
