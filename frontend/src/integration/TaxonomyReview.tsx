import { useEffect, useRef, useState } from "react";
import { request } from "./catalog-adapter";

type Channel = "KIKI" | "ECOMM" | "ML" | "TN";
type Pair = {
  id: string;
  category: string;
  subcategory: string;
  state: "ACTIVE" | "RETIRED";
};
type Mapping = Pair & { pair_id: string; channel: Exclude<Channel, "KIKI"> };
type Catalog = {
  version: number;
  revision: string;
  fingerprint: string;
  entries: Pair[];
  mappings: Mapping[];
  external_writes_enabled: false;
};
type Item = {
  ecomm_id: string;
  name: string;
  expected_version: number;
  expected_workspace_version: number;
  evidence_fingerprint: string;
  can_approve: boolean;
  state: string;
  mapping_version: number;
  exception: string | null;
  reason: string;
  source_pair: { category: string; subcategory: string } | null;
  proposal?: {
    state: string;
    pair_id: string | null;
    reason: string;
    evidence_ids: string[];
    automatic_assignment: false;
  };
  classification_evidence: {
    field: string;
    value: string;
    evidence_id: string;
  }[];
  record: null | {
    decision: "APPROVED" | "REVOKED";
    taxonomy_revision: string;
    internal_pair_id?: string;
    target_pair: { category: string; subcategory: string };
  };
};
type Preview = {
  mode: "TAXONOMY_BATCH_REVIEW";
  channel: Channel;
  total: number;
  selection_fingerprint: string;
  items: Item[];
  catalog: Catalog;
  external_writes_enabled: false;
};
type Choice = {
  decision: "SKIP" | "APPROVED" | "REVOKED";
  pair: string;
  checked: boolean;
};
const names: Record<Channel, string> = {
  KIKI: "KIKI",
  ECOMM: "Ecomm-App",
  ML: "Mercado Libre",
  TN: "Tiendanube",
};
const base = "/api/ecomm-app/workspace/taxonomy";

async function json<T>(path: string, csrf: string, body?: unknown): Promise<T> {
  const response = await request(
    path,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify(body),
        },
  );
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      value.detail ||
        "La operación no pudo completarse. Recuperá la versión actual.",
    );
  if (value.external_writes_enabled !== false)
    throw new Error("Respuesta de clasificación incompatible.");
  return value as T;
}

export function TaxonomyReview({
  ids,
  csrf,
  disabled,
}: {
  ids: Set<string>;
  csrf: string;
  disabled: boolean;
}) {
  const [channel, setChannel] = useState<Channel>("KIKI");
  const [report, setReport] = useState<Preview>();
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [catalog, setCatalog] = useState<Catalog>();
  const [entries, setEntries] = useState<Pair[]>([]);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [revision, setRevision] = useState("");
  const [catalogReason, setCatalogReason] = useState("");
  const [catalogConfirmed, setCatalogConfirmed] = useState(false);
  const selection = [...ids].sort().join(",");
  const epoch = useRef(0);
  useEffect(() => {
    setCatalogConfirmed(false);
  }, [entries, mappings, revision, catalogReason]);
  useEffect(() => {
    setConfirmed(false);
  }, [reason]);
  useEffect(() => {
    epoch.current++;
    setReport(undefined);
    setChoices({});
    setConfirmed(false);
    setError("");
  }, [selection, channel]);

  async function inspect() {
    if (disabled || busy || ids.size < 1 || ids.size > 20) return;
    const selected = [...ids],
      generation = epoch.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const value = await json<Preview>(`${base}/review-preview`, csrf, {
        ecomm_ids: selected,
        channel,
      });
      if (
        value.mode !== "TAXONOMY_BATCH_REVIEW" ||
        value.total !== selected.length ||
        !Array.isArray(value.items) ||
        value.items.length !== selected.length ||
        value.items.some((item) => !selected.includes(item.ecomm_id)) ||
        new Set(value.items.map((item) => item.ecomm_id)).size !==
          selected.length
      )
        throw new Error(
          "La revisión no corresponde a las variantes seleccionadas.",
        );
      if (generation !== epoch.current) return;
      setReport(value);
      setChoices(
        Object.fromEntries(
          value.items.map((item) => [
            item.ecomm_id,
            {
              decision: "SKIP",
              pair: item.record?.internal_pair_id || "",
              checked: false,
            },
          ]),
        ),
      );
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function target(item: Item) {
    if (!report) return undefined;
    const pair = choices[item.ecomm_id]?.pair;
    return channel === "KIKI"
      ? report.catalog.entries.find(
          (p) => p.id === pair && p.state === "ACTIVE",
        )
      : report.catalog.mappings.find(
          (m) =>
            m.pair_id === pair && m.channel === channel && m.state === "ACTIVE",
        );
  }
  const selectedCount = Object.values(choices).filter(
    (c) => c.decision !== "SKIP",
  ).length;
  const canSave =
    !!report &&
    selectedCount > 0 &&
    confirmed &&
    reason.trim().length >= 20 &&
    report.items.every((item) => {
      const choice = choices[item.ecomm_id];
      return (
        choice?.decision === "SKIP" ||
        (!!choice?.checked &&
          (choice.decision === "REVOKED"
            ? item.record?.decision === "APPROVED"
            : item.can_approve && !!target(item)))
      );
    });
  async function save() {
    if (!report || !canSave || busy || disabled) return;
    setBusy(true);
    setError("");
    try {
      const decisions = report.items.map((item) => {
        const choice = choices[item.ecomm_id];
        if (choice.decision === "SKIP")
          return {
            ecomm_id: item.ecomm_id,
            decision: "SKIP",
            reason: "Excepción pendiente de revisión humana.",
          };
        const destination =
          choice.decision === "REVOKED"
            ? item.record?.target_pair
            : target(item);
        return {
          ecomm_id: item.ecomm_id,
          decision: choice.decision,
          expected_version: item.expected_version,
          expected_workspace_version: item.expected_workspace_version,
          expected_fingerprint: item.evidence_fingerprint,
          reason,
          taxonomy_revision:
            choice.decision === "REVOKED"
              ? item.record?.taxonomy_revision
              : report.catalog.revision,
          target_category: destination?.category,
          target_subcategory: destination?.subcategory,
          ...(choice.decision === "APPROVED"
            ? {
                catalog_version: report.catalog.version,
                catalog_pair_id: choice.pair,
                channel_mapping_id:
                  channel === "KIKI" ? null : (destination as Mapping)?.id,
              }
            : {}),
        };
      });
      await json(`${base}/review-batch`, csrf, {
        ecomm_ids: report.items.map((item) => item.ecomm_id),
        channel,
        expected_selection_fingerprint: report.selection_fingerprint,
        decisions,
        confirm: true,
      });
      setNotice(
        `${selectedCount} decisiones guardadas en el historial. Las fichas y los canales no se modificaron.`,
      );
      setReport(undefined);
      setChoices({});
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function loadCatalog() {
    setBusy(true);
    setError("");
    try {
      const value = await json<Catalog>(`${base}/catalog`, csrf);
      setCatalog(value);
      setEntries(value.entries.map((p) => ({ ...p })));
      setMappings(value.mappings.map((p) => ({ ...p })));
      setRevision("");
      setCatalogConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function saveCatalog() {
    if (
      !catalog ||
      !catalogConfirmed ||
      revision.trim().length < 1 ||
      catalogReason.trim().length < 20
    )
      return;
    setBusy(true);
    setError("");
    try {
      const value = await json<Catalog>(`${base}/catalog`, csrf, {
        expected_version: catalog.version,
        revision,
        entries,
        mappings,
        reason: catalogReason,
        confirm: true,
      });
      setCatalog(value);
      setReport(undefined);
      setCatalogConfirmed(false);
      setRevision("");
      setNotice(
        `Vocabulario guardado, versión ${value.version}. Las sugerencias de versiones anteriores requieren revisión.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function changeChoice(id: string, delta: Partial<Choice>) {
    setChoices((previous) => ({
      ...previous,
      [id]: { ...previous[id], ...delta },
    }));
    setConfirmed(false);
  }

  return (
    <section className="b-detail" aria-label="Clasificación por lotes">
      <h3>Clasificación y equivalencias</h3>
      <p>
        Revisá hasta 20 variantes con sus citas. Una clasificación KIKI no
        acredita la categoría oficial del canal ni publica productos.
      </p>
      <div className="b-actions">
        <label>
          Destino{" "}
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value as Channel)}
            disabled={busy || disabled}
          >
            {Object.entries(names).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void inspect()}
          disabled={disabled || busy || ids.size < 1 || ids.size > 20}
        >
          Revisar clasificación de {ids.size} variantes
        </button>
      </div>
      {ids.size > 20 && (
        <p>Seleccioná como máximo 20 variantes para esta revisión.</p>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {report && (
        <div>
          <p>
            {report.total} variantes ·{" "}
            {report.items.filter((i) => i.exception).length} excepciones ·
            vocabulario {report.catalog.revision || "no preparado"} (versión{" "}
            {report.catalog.version}).
          </p>
          {report.items.map((item) => {
            const choice = choices[item.ecomm_id],
              destination = target(item);
            return (
              <details
                key={item.ecomm_id}
                className="b-detail"
                data-taxonomy-ecomm={item.ecomm_id}
              >
                <summary>
                  {item.name || item.ecomm_id} ·{" "}
                  {item.state === "APPROVED" ? "Revisada" : "Requiere revisión"}
                </summary>
                <p>
                  Ecomm ID {item.ecomm_id} · {item.reason}
                </p>
                {item.proposal && (
                  <p>Propuesta de clasificación: {item.proposal.reason}</p>
                )}
                <p>
                  Categoría documentada en la fuente:{" "}
                  {item.source_pair
                    ? `${item.source_pair.category} / ${item.source_pair.subcategory}`
                    : "No documentada; la clasificación será una decisión comercial humana."}
                </p>
                {item.classification_evidence?.map((f) => (
                  <p key={f.evidence_id}>
                    {f.value} · cita {f.evidence_id}
                  </p>
                ))}
                <label>
                  Decisión{" "}
                  <select
                    value={choice.decision}
                    onChange={(e) =>
                      changeChoice(item.ecomm_id, {
                        decision: e.target.value as Choice["decision"],
                        checked: false,
                      })
                    }
                    disabled={busy || disabled}
                  >
                    <option value="SKIP">Dejar pendiente</option>
                    <option value="APPROVED" disabled={!item.can_approve}>
                      Aprobar clasificación
                    </option>
                    <option
                      value="REVOKED"
                      disabled={item.record?.decision !== "APPROVED"}
                    >
                      Revocar clasificación anterior
                    </option>
                  </select>
                </label>
                {choice.decision === "APPROVED" && (
                  <>
                    <label>
                      Par interno KIKI{" "}
                      <select
                        value={choice.pair}
                        onChange={(e) =>
                          changeChoice(item.ecomm_id, {
                            pair: e.target.value,
                            checked: false,
                          })
                        }
                        disabled={busy || disabled}
                      >
                        <option value="">
                          Elegir categoría y subcategoría
                        </option>
                        {report.catalog.entries
                          .filter((p) => p.state === "ACTIVE")
                          .map((pair) => (
                            <option key={pair.id} value={pair.id}>
                              {pair.category} / {pair.subcategory}
                            </option>
                          ))}
                      </select>
                    </label>
                    <p>
                      Destino {names[channel]}:{" "}
                      {destination
                        ? `${destination.category} / ${destination.subcategory}`
                        : "Sin equivalencia activa para este par; requiere revisión."}
                    </p>
                  </>
                )}
                {choice.decision !== "SKIP" && (
                  <label>
                    <input
                      type="checkbox"
                      checked={choice.checked}
                      onChange={(e) =>
                        changeChoice(item.ecomm_id, {
                          checked: e.target.checked,
                        })
                      }
                    />
                    Revisé esta variante, su presentación y sus citas.
                  </label>
                )}
              </details>
            );
          })}
          <label>
            Motivo de las decisiones seleccionadas{" "}
            <textarea
              value={reason}
              maxLength={600}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Confirmo las {selectedCount} decisiones seleccionadas; las demás
            variantes quedan pendientes.
          </label>
          <button
            type="button"
            disabled={!canSave || busy || disabled}
            onClick={() => void save()}
          >
            Guardar revisiones seleccionadas
          </button>
        </div>
      )}
      <details>
        <summary>Vocabulario interno y equivalencias por canal</summary>
        <p>
          Los pares y equivalencias se registran por decisión humana. Cambiar la
          versión invalida las sugerencias anteriores; no reclasifica productos.
        </p>
        <button
          type="button"
          disabled={busy || disabled}
          onClick={() => void loadCatalog()}
        >
          Recuperar vocabulario
        </button>
        {catalog && (
          <fieldset disabled={busy || disabled}>
            <legend>
              Vocabulario actual: {catalog.revision || "sin registrar"} ·
              versión {catalog.version}
            </legend>
            {entries.map((pair, index) => (
              <div key={pair.id} className="b-actions">
                <label>
                  Categoría {index + 1}
                  <input
                    maxLength={160}
                    value={pair.category}
                    onChange={(e) =>
                      setEntries((old) =>
                        old.map((p) =>
                          p.id === pair.id
                            ? { ...p, category: e.target.value }
                            : p,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  Subcategoría {index + 1}
                  <input
                    maxLength={160}
                    value={pair.subcategory}
                    onChange={(e) =>
                      setEntries((old) =>
                        old.map((p) =>
                          p.id === pair.id
                            ? { ...p, subcategory: e.target.value }
                            : p,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  Estado del par {index + 1}
                  <select
                    value={pair.state}
                    onChange={(e) =>
                      setEntries((old) =>
                        old.map((p) =>
                          p.id === pair.id
                            ? { ...p, state: e.target.value as Pair["state"] }
                            : p,
                        ),
                      )
                    }
                  >
                    <option value="ACTIVE">Disponible</option>
                    <option value="RETIRED">Retirado</option>
                  </select>
                </label>
              </div>
            ))}
            <button
              type="button"
              disabled={entries.length >= 1000}
              onClick={() =>
                setEntries((old) => [
                  ...old,
                  {
                    id: crypto.randomUUID(),
                    category: "",
                    subcategory: "",
                    state: "ACTIVE",
                  },
                ])
              }
            >
              Agregar categoría y subcategoría
            </button>
            {mappings.map((mapping, index) => (
              <div key={mapping.id} className="b-detail">
                <label>
                  Par interno de equivalencia {index + 1}
                  <select
                    value={mapping.pair_id}
                    onChange={(e) =>
                      setMappings((old) =>
                        old.map((m) =>
                          m.id === mapping.id
                            ? { ...m, pair_id: e.target.value }
                            : m,
                        ),
                      )
                    }
                  >
                    <option value="">Elegir par</option>
                    {entries.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.category} / {p.subcategory}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Canal de equivalencia {index + 1}
                  <select
                    value={mapping.channel}
                    onChange={(e) =>
                      setMappings((old) =>
                        old.map((m) =>
                          m.id === mapping.id
                            ? {
                                ...m,
                                channel: e.target.value as Mapping["channel"],
                              }
                            : m,
                        ),
                      )
                    }
                  >
                    {["ECOMM", "ML", "TN"].map((c) => (
                      <option key={c} value={c}>
                        {names[c as Channel]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Categoría destino {index + 1}
                  <input
                    value={mapping.category}
                    maxLength={160}
                    onChange={(e) =>
                      setMappings((old) =>
                        old.map((m) =>
                          m.id === mapping.id
                            ? { ...m, category: e.target.value }
                            : m,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  Subcategoría destino {index + 1}
                  <input
                    value={mapping.subcategory}
                    maxLength={160}
                    onChange={(e) =>
                      setMappings((old) =>
                        old.map((m) =>
                          m.id === mapping.id
                            ? { ...m, subcategory: e.target.value }
                            : m,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  Estado de equivalencia {index + 1}
                  <select
                    value={mapping.state}
                    onChange={(e) =>
                      setMappings((old) =>
                        old.map((m) =>
                          m.id === mapping.id
                            ? { ...m, state: e.target.value as Pair["state"] }
                            : m,
                        ),
                      )
                    }
                  >
                    <option value="ACTIVE">Disponible</option>
                    <option value="RETIRED">Retirada</option>
                  </select>
                </label>
              </div>
            ))}
            <button
              type="button"
              disabled={mappings.length >= 1000}
              onClick={() =>
                setMappings((old) => [
                  ...old,
                  {
                    id: crypto.randomUUID(),
                    pair_id: "",
                    channel: "ML",
                    category: "",
                    subcategory: "",
                    state: "ACTIVE",
                  },
                ])
              }
            >
              Agregar equivalencia de canal
            </button>
            <label>
              Nombre de la nueva revisión
              <input
                value={revision}
                maxLength={100}
                onChange={(e) => setRevision(e.target.value)}
              />
            </label>
            <label>
              Motivo del cambio de vocabulario
              <textarea
                value={catalogReason}
                maxLength={600}
                onChange={(e) => setCatalogReason(e.target.value)}
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={catalogConfirmed}
                onChange={(e) => setCatalogConfirmed(e.target.checked)}
              />
              Revisé los pares internos y las equivalencias declaradas.
            </label>
            <button
              type="button"
              disabled={
                !catalogConfirmed ||
                !revision.trim() ||
                catalogReason.trim().length < 20 ||
                !entries.length
              }
              onClick={() => void saveCatalog()}
            >
              Guardar nueva versión del vocabulario
            </button>
          </fieldset>
        )}
      </details>
    </section>
  );
}
