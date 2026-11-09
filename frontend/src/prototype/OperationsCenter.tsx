import { useState, useEffect } from "react";
import {
  tools,
  change,
  requirements,
  now,
  type Item,
  type Job,
  type Tool,
} from "./operations-model";
const guide: Record<Tool, string> = {
  "Actualización de catálogo":
    "Renová una copia sintética. La muestra incrementará una unidad de stock por variante elegida; nunca consulta Ecomm-App.",
  "Familias SKU y duplicados":
    "Compará las variantes con SKU repetido y documentá por qué deben conservar su identidad. Nunca se fusionan por SKU.",
  "Conciliación de canales":
    "Compará candidatos contra la variante central. Este flujo permite descartar candidatos; aceptar una identidad requiere revisión individual en Evidencias.",
  "Evidencias y conflictos":
    "Resolvé revisiones internas después de comparar cada identidad. El resultado no verifica publicaciones externas.",
  "Propuestas IA":
    "Generá propuestas locales para varias variantes y revisalas en la ficha, sin ejecutar modelos ni aplicar textos automáticamente.",
  "Preparación por lotes":
    "Revisá requisitos antes de preparar fichas. Las variantes con conflictos o datos faltantes se omiten y se informa el motivo.",
  "Trabajos y resultados":
    "Consultá el resultado y los Ecomm ID de cada trabajo de esta sesión.",
  "Diagnóstico operativo":
    "Analizá datos de muestra para detectar conflictos, identidades repetidas y requisitos pendientes. No consulta servicios.",
};
export function OperationsCenter({
  rows,
  active,
  onTool,
  onChange,
  onSelect,
  jobs,
  onJob,
  onDirty,
}: {
  rows: Item[];
  active: string;
  onTool: (tool: string) => void;
  onChange: (rows: Item[]) => void;
  onSelect: (id: string, tab: string) => void;
  jobs: Job[];
  onJob: (job: Job) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [reviewed, setReviewed] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [step, setStep] = useState<"select" | "preview" | "result">("select");
  const [result, setResult] = useState("");
  const [jobDetail, setJobDetail] = useState<Job | null>(null);
  const tool = tools.find((t) => t === active);
  useEffect(() => {
    setSelected([]);
    setReviewed([]);
    setReason("");
    setStep("select");
    setResult("");
    setJobDetail(null);
    onDirty(false);
  }, [active]);
  const picked = rows.filter((p) => selected.includes(p.id));
  const eligible = picked.filter((p) => requirements(p).length === 0);
  const needsReview =
    tool === "Familias SKU y duplicados" ||
    tool === "Evidencias y conflictos" ||
    tool === "Conciliación de canales";
  const canConfirm =
    !needsReview ||
    (reason.trim().length >= 12 &&
      picked.every((p) => reviewed.includes(p.id)));
  function execute() {
    if (!tool || !canConfirm) return;
    let changed = rows;
    let summary = "";
    if (tool === "Actualización de catálogo") {
      changed = rows.map((p) =>
        selected.includes(p.id)
          ? change(
              p,
              {
                stock: p.stock + 1,
                status: "Pendiente",
                prepared: { ml: false, tn: false },
              },
              "Copia sintética renovada",
              "Fixture de actualización local: stock +1; sin acceso a Ecomm-App",
            )
          : p,
      );
      summary = `${picked.length} variantes actualizadas desde fixture; stock de muestra +1.`;
    }
    if (
      tool === "Familias SKU y duplicados" ||
      tool === "Evidencias y conflictos"
    ) {
      changed = rows.map((p) =>
        selected.includes(p.id)
          ? change(
              p,
              { conflict: false, status: "Pendiente" },
              "Identidad revisada; variantes conservadas",
              reason,
            )
          : p,
      );
      summary = `${picked.length} revisiones internas resueltas. Ecomm ID conservados; no se fusionaron variantes.`;
    }
    if (tool === "Conciliación de canales") {
      changed = rows.map((p) =>
        selected.includes(p.id)
          ? change(
              p,
              {
                decisions: {
                  ...p.decisions,
                  ml: { state: "Rechazada", reason },
                },
              },
              "Candidato ML descartado",
              reason,
            )
          : p,
      );
      summary = `${picked.length} candidatos ML descartados internamente. Las publicaciones de muestra no se modificaron.`;
    }
    if (tool === "Propuestas IA") {
      changed = rows.map((p) =>
        selected.includes(p.id)
          ? change(
              p,
              {
                ai: {
                  text: `${p.name}, de ${p.brand}. Propuesta de descripción simulada: revisar medidas y materiales con un manual técnico.`,
                  state: "Pendiente",
                },
              },
              "Propuesta IA simulada generada por lote",
            )
          : p,
      );
      summary = `${picked.length} propuestas locales generadas. Pendientes de edición y aprobación individual.`;
    }
    if (tool === "Preparación por lotes") {
      changed = rows.map((p) =>
        eligible.some((e) => e.id === p.id)
          ? change(
              p,
              {
                status: "Preparada",
                prepared: { ml: true, tn: !!p.seo.trim() },
              },
              "Preparación por lote",
              "Requisitos internos de muestra revisados; no se publicó en canales",
            )
          : p,
      );
      summary = `${eligible.length} variantes preparadas internamente; ${picked.length - eligible.length} omitidas por requisitos pendientes. Ninguna publicación externa.`;
    }
    if (tool === "Diagnóstico operativo") {
      summary = `Diagnóstico de ${picked.length} variantes: ${picked.filter((p) => p.conflict).length} con conflictos; ${picked.filter((p) => requirements(p).length > 0).length} con requisitos pendientes; ${new Set(picked.map((p) => p.id)).size} Ecomm ID únicos. No se modificaron fichas.`;
    }
    onChange(changed);
    onJob({
      id: `DEMO-JOB-${jobs.length + 1}`,
      tool,
      date: now(),
      ids: selected,
      result: summary,
    });
    setResult(summary);
    setStep("result");
    onDirty(false);
  }
  return (
    <section className="o-center" aria-label="Centro de operaciones">
      <div className="o-center-heading">
        <div>
          <h2>Centro de operaciones</h2>
          <p>Empezá y terminá tus tareas sin salir del catálogo.</p>
        </div>
        <span className="o-session">
          {jobs.length} trabajos de muestra completados
        </span>
      </div>
      <div className="o-tools">
        {tools.map((t) => (
          <button key={t} aria-pressed={tool === t} onClick={() => onTool(t)}>
            {t}
          </button>
        ))}
      </div>
      {tool && (
        <section className="o-workbench" aria-label={tool}>
          <header>
            <div>
              <h3>{tool}</h3>
              <p>{guide[tool]}</p>
            </div>
            <button onClick={() => onTool("")}>Cerrar herramienta</button>
          </header>
          {tool === "Trabajos y resultados" ? (
            <>
              <p>
                Los trabajos son simulados y se conservan solo durante esta
                sesión.
              </p>
              {!jobs.length ? (
                <p>
                  Todavía no ejecutaste trabajos. Elegí una herramienta para
                  comenzar.
                </p>
              ) : (
                jobs.map((j) => (
                  <article className="o-job" key={j.id}>
                    <strong>{j.id} · Completado (demo)</strong>
                    <p>
                      {j.tool} · {j.date} · Operador demo
                    </p>
                    <button onClick={() => setJobDetail(j)}>
                      Ver resultado {j.id}
                    </button>
                  </article>
                ))
              )}
              {jobDetail && (
                <div className="o-result" role="status">
                  <h4>{jobDetail.tool}</h4>
                  <p>{jobDetail.result}</p>
                  <p>Variantes: {jobDetail.ids.join(", ")}</p>
                  <button onClick={() => setJobDetail(null)}>
                    Volver a trabajos
                  </button>
                </div>
              )}
            </>
          ) : step === "result" ? (
            <div className="o-result" role="status">
              <h4>Trabajo completado · demostración</h4>
              <p>{result}</p>
              {picked.map((p) => (
                <button
                  key={p.id}
                  onClick={() =>
                    onSelect(
                      p.id,
                      tool === "Propuestas IA"
                        ? "IA"
                        : tool === "Preparación por lotes"
                          ? "Canales"
                          : "Historial",
                    )
                  }
                >
                  Revisar {p.id}
                </button>
              ))}
              <div className="o-actions">
                <button
                  onClick={() => {
                    setStep("select");
                    setSelected([]);
                    setReviewed([]);
                  }}
                >
                  Iniciar otra revisión
                </button>
                <button onClick={() => onTool("Trabajos y resultados")}>
                  Ver trabajos y resultados
                </button>
              </div>
            </div>
          ) : (
            <>
              <ol className="o-steps" aria-label="Pasos">
                <li aria-current={step === "select" ? "step" : undefined}>
                  1. Elegir variantes
                </li>
                <li aria-current={step === "preview" ? "step" : undefined}>
                  2. Revisar y confirmar
                </li>
                <li>3. Consultar resultado</li>
              </ol>
              {step === "select" ? (
                <>
                  <p>
                    Elegí las variantes por Ecomm ID. El SKU compartido no las
                    convierte en el mismo producto.
                  </p>
                  <button
                    onClick={() => {
                      setSelected(rows.map((p) => p.id));
                      onDirty(true);
                    }}
                  >
                    Seleccionar las {rows.length} variantes de muestra
                  </button>
                  <div className="o-selection">
                    {rows.map((p) => (
                      <label key={p.id} className="o-check">
                        <input
                          type="checkbox"
                          checked={selected.includes(p.id)}
                          onChange={(e) => {
                            setSelected((old) =>
                              e.target.checked
                                ? [...old, p.id]
                                : old.filter((id) => id !== p.id),
                            );
                            onDirty(true);
                          }}
                        />
                        <span>
                          <strong>
                            {p.id} · {p.name}
                          </strong>
                          <small>
                            SKU {p.sku} · {p.brand} ·{" "}
                            {p.conflict
                              ? "Conflicto pendiente"
                              : "Identidad sin conflicto"}{" "}
                            ·{" "}
                            {requirements(p).length
                              ? "Faltan requisitos"
                              : "Datos completos"}
                          </small>
                        </span>
                      </label>
                    ))}
                  </div>
                  <button
                    className="d-primary"
                    disabled={!picked.length}
                    onClick={() => {
                      setStep("preview");
                      onDirty(true);
                    }}
                  >
                    Revisar selección ({picked.length})
                  </button>
                </>
              ) : (
                <>
                  <h4>Revisión previa · {picked.length} variantes</h4>
                  {picked.map((p) => (
                    <article className="o-job" key={p.id}>
                      <strong>
                        {p.id} · {p.name}
                      </strong>
                      <p>
                        SKU {p.sku} · {p.brand} · ML: {p.ml} · TN: {p.tn}
                      </p>
                      <p>
                        Familia {p.family}. Variantes del mismo SKU:{" "}
                        {rows
                          .filter((other) => other.sku === p.sku)
                          .map((other) => `${other.id} (${other.name})`)
                          .join("; ")}
                        . Identidades conservadas.
                      </p>
                      <p>
                        {tool === "Preparación por lotes"
                          ? requirements(p).length
                            ? `Se omitirá: ${requirements(p).join(", ")}`
                            : "Apta para preparación interna"
                          : tool === "Actualización de catálogo"
                            ? `Stock actual ${p.stock} → muestra ${p.stock + 1}`
                            : "Sin confirmación automática de publicación."}
                      </p>
                      {needsReview && (
                        <label className="o-check">
                          <input
                            type="checkbox"
                            checked={reviewed.includes(p.id)}
                            onChange={(e) =>
                              setReviewed((old) =>
                                e.target.checked
                                  ? [...old, p.id]
                                  : old.filter((id) => id !== p.id),
                              )
                            }
                          />
                          Comparé identidad y presentación de {p.id}
                        </label>
                      )}
                    </article>
                  ))}
                  {needsReview && (
                    <label>
                      Fundamento de la revisión
                      <textarea
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="Indicá la evidencia revisada (mínimo 12 caracteres)"
                      />
                    </label>
                  )}
                  <p className="o-warning">
                    El resultado será exclusivamente de demostración. No escribe
                    en Ecomm-App ni en canales externos.
                  </p>
                  <div className="o-actions">
                    <button onClick={() => setStep("select")}>
                      Volver a selección
                    </button>
                    <button
                      className="d-primary"
                      disabled={!canConfirm}
                      onClick={execute}
                    >
                      Confirmar trabajo simulado
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </section>
      )}
    </section>
  );
}
