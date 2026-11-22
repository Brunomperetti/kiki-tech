import { useEffect, useState } from "react";
import { request, captureDate } from "./catalog-adapter";
import { downloadReviewCsv } from "./csv-download";
import type { Audit } from "./ContractualCatalogAudit";

const root = "/api/ecomm-app/workspace";
type Channel = "ml" | "tn";
type Preview = {
  mode: "READ_ONLY_COMMERCIAL_REVIEW_PACKAGE";
  preview_fingerprint: string;
  channel: Channel;
  total: number;
  prepared_internal: number;
  blocked: number;
  native_provider_import_file: false;
  external_writes_enabled: false;
  provider_calls: 0;
  ai_requests: 0;
  items: {
    ecomm_id: string;
    sku: string;
    name: string;
    source_presentation: string | null;
    state: string;
    blockers: string[];
    channel_requirements_pending: string[];
    workspace_version: number;
    channel_taxonomy: {
      state: string;
      mapping_version: number;
      taxonomy_revision: string | null;
      target_pair: { category: string; subcategory: string } | null;
    };
  }[];
};
type Receipt = {
  report_id: string;
  revision: number;
  fingerprint: string;
  created_at: string;
  responsible: string;
  review_status: string;
  next_general_review_at: string | null;
  human_acknowledgement: { at: string; reason: string } | null;
  summary: { total: number };
};
type ReportRow = {
  report_id: string;
  revision: number;
  created_at: string;
  responsible: string;
  total: number;
  human_acknowledgement: unknown;
};

async function json(path: string, csrf: string, body?: unknown) {
  const response = await request(
    root + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify(body),
        },
  );
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : "No se pudo completar la operación.",
    );
  return value;
}

export function CommercialExportPanel({
  ids,
  csrf,
}: {
  ids: string[];
  csrf: string;
}) {
  const [channel, setChannel] = useState<Channel>("ml");
  const [preview, setPreview] = useState<Preview>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = ids.join("|");
  useEffect(() => {
    setPreview(undefined);
    setError("");
  }, [key, channel]);

  async function load() {
    setBusy(true);
    setError("");
    setPreview(undefined);
    try {
      const value = (await json("/exports/commercial/preview", csrf, {
        channel,
        ecomm_ids: ids,
      })) as Preview;
      if (
        value.mode !== "READ_ONLY_COMMERCIAL_REVIEW_PACKAGE" ||
        value.channel !== channel ||
        value.external_writes_enabled !== false ||
        value.native_provider_import_file !== false ||
        value.provider_calls !== 0 ||
        value.ai_requests !== 0 ||
        !/^[a-f0-9]{64}$/.test(value.preview_fingerprint) ||
        value.total !== ids.length ||
        value.prepared_internal + value.blocked !== value.total ||
        !Array.isArray(value.items) ||
        value.items.length !== value.total ||
        value.items.some((item) => !ids.includes(item.ecomm_id)) ||
        new Set(value.items.map((item) => item.ecomm_id)).size !== value.total
      )
        throw new Error(
          "Previsualización incompatible; no se habilitó la descarga.",
        );
      setPreview(value);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const response = await request(root + "/exports/commercial/download", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          channel,
          ecomm_ids: ids,
          expected_fingerprint: preview.preview_fingerprint,
          confirm: true,
        }),
      });
      if (!response.ok) {
        const value = await response.json();
        throw new Error(
          typeof value.detail === "string"
            ? value.detail
            : "La previsualización cambió; volvé a revisar.",
        );
      }
      downloadReviewCsv(
        await response.blob(),
        `kiki-comercial-${channel}-revision.csv`,
      );
    } catch (exc) {
      setPreview(undefined);
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details aria-label="Exportación comercial por canal">
      <summary>Preparar salida comercial por canal</summary>
      <p>
        {ids.length} variantes seleccionadas. Seleccioná entre 1 y 20 desde la
        tabla. El archivo es un paquete de revisión comercial, no un formato de
        importación directa ni una orden de publicación.
      </p>
      <label>
        Canal de revisión{" "}
        <select
          value={channel}
          disabled={busy}
          onChange={(event) => setChannel(event.target.value as Channel)}
        >
          <option value="ml">Mercado Libre</option>
          <option value="tn">Tiendanube</option>
        </select>
      </label>
      <button
        type="button"
        disabled={busy || !csrf || ids.length < 1 || ids.length > 20}
        onClick={() => void load()}
      >
        Previsualizar exportación comercial
      </button>
      {error && <p role="alert">{error}</p>}
      {preview && (
        <div role="region" aria-label="Previsualización comercial">
          <p>
            {preview.total} variantes · {preview.prepared_internal} preparadas
            internamente · {preview.blocked} bloqueadas. Todos los recursos y
            equivalencias del canal requieren revisión; no se publica nada.
          </p>
          <ul>
            {preview.items.map((item) => (
              <li key={item.ecomm_id}>
                <strong>
                  {item.sku} · {item.name}
                </strong>{" "}
                · Ecomm ID {item.ecomm_id} ·{" "}
                {item.source_presentation || "Presentación pendiente"} · versión{" "}
                {item.workspace_version}
                <p>
                  {item.state === "BLOCKED"
                    ? "Bloqueada para preparación completa"
                    : "Preparada para revisión humana del canal"}
                </p>
                <p>
                  Clasificación del canal: {item.channel_taxonomy.state} ·
                  versión {item.channel_taxonomy.mapping_version}
                  {item.channel_taxonomy.target_pair
                    ? ` · ${item.channel_taxonomy.target_pair.category} / ${item.channel_taxonomy.target_pair.subcategory}`
                    : " · equivalencia pendiente"}
                  . No acredita identificadores oficiales de publicación.
                </p>
                <ul>
                  {[...item.blockers, ...item.channel_requirements_pending].map(
                    (reason, index) => (
                      <li key={index}>{reason}</li>
                    ),
                  )}
                </ul>
              </li>
            ))}
          </ul>
          <button type="button" disabled={busy} onClick={() => void download()}>
            Confirmar y descargar paquete de revisión
          </button>
        </div>
      )}
    </details>
  );
}

export function MonthlyReportPanel({
  report,
  csrf,
}: {
  report: Audit;
  csrf: string;
}) {
  const [responsible, setResponsible] = useState("");
  const [reason, setReason] = useState("");
  const [receipt, setReceipt] = useState<Receipt>();
  const [history, setHistory] = useState<ReportRow[]>([]);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setReceipt(undefined);
    setReason("");
  }, [report.preview_fingerprint]);
  async function run(operation: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await operation();
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadHistory(next: number) {
    const value = await json(`/reports/monthly?page=${next}&limit=12`, csrf);
    if (!Array.isArray(value.items) || value.external_writes_enabled !== false)
      throw new Error("Historial de informes incompatible.");
    setHistory(value.items);
    setPage(next);
  }
  return (
    <details aria-label="Registro de revisión general mensual">
      <summary>Guardar informe y registrar revisión general mensual</summary>
      <p>
        Guardar el diagnóstico no confirma las fuentes ni aprueba fichas. La
        confirmación humana queda separada del informe automático y no cambia
        las fechas de revisión de cada producto.
      </p>
      <label>
        Responsable de seguimiento{" "}
        <input
          value={responsible}
          maxLength={120}
          disabled={busy}
          onChange={(event) => setResponsible(event.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={busy || !csrf || responsible.trim().length < 2}
        onClick={() =>
          void run(async () => {
            setReceipt(
              await json("/reports/monthly", csrf, {
                expected_fingerprint: report.preview_fingerprint,
                responsible,
                confirm: true,
              }),
            );
            await loadHistory(1);
          })
        }
      >
        Guardar informe general con pendientes
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run(() => loadHistory(1))}
      >
        Recuperar informes anteriores
      </button>
      {error && <p role="alert">{error}</p>}
      {receipt && (
        <section aria-label="Constancia del informe general">
          <p>
            Informe {receipt.report_id} · {captureDate(receipt.created_at)} ·{" "}
            {receipt.summary.total} variantes · Responsable:{" "}
            {receipt.responsible}
          </p>
          <p>
            {receipt.human_acknowledgement
              ? `Revisión general confirmada el ${captureDate(receipt.human_acknowledgement.at)}`
              : "Diagnóstico guardado; revisión humana general pendiente."}
          </p>
          <p>
            La constancia corresponde al informe archivado; no acredita que la
            captura o las fuentes sigan sin cambios.
          </p>
          <button
            type="button"
            disabled={busy || !csrf}
            onClick={() =>
              void run(async () => {
                const response = await request(
                  root + `/reports/monthly/${receipt.report_id}/download`,
                  {
                    method: "POST",
                    headers: {
                      "Content-Type": "application/json",
                      "X-CSRF-Token": csrf,
                    },
                    body: JSON.stringify({
                      expected_fingerprint: receipt.fingerprint,
                      confirm: true,
                    }),
                  },
                );
                if (!response.ok)
                  throw new Error(
                    "El informe archivado no pudo exportarse; recargá su versión.",
                  );
                downloadReviewCsv(
                  await response.blob(),
                  "kiki-auditoria-comercial-mensual.csv",
                );
              })
            }
          >
            Descargar CSV del informe archivado
          </button>
          {receipt.next_general_review_at && (
            <p>
              Próxima revisión general:{" "}
              {captureDate(receipt.next_general_review_at)}. No acredita
              aprobación individual de las fuentes.
            </p>
          )}
          {!receipt.human_acknowledgement && (
            <>
              <label>
                Resultado y excepciones de la revisión general{" "}
                <textarea
                  value={reason}
                  maxLength={600}
                  disabled={busy}
                  onChange={(event) => setReason(event.target.value)}
                />
              </label>
              <button
                type="button"
                disabled={
                  busy ||
                  !csrf ||
                  reason.trim().length < 25 ||
                  receipt.fingerprint !== report.preview_fingerprint
                }
                onClick={() =>
                  void run(async () => {
                    setReceipt(
                      await json(
                        `/reports/monthly/${receipt.report_id}/acknowledge`,
                        csrf,
                        {
                          expected_revision: receipt.revision,
                          expected_fingerprint: receipt.fingerprint,
                          reason,
                          confirm: true,
                        },
                      ),
                    );
                    await loadHistory(page);
                  })
                }
              >
                Confirmar revisión general del informe
              </button>
            </>
          )}
        </section>
      )}
      {!!history.length && (
        <>
          <ul>
            {history.map((item) => (
              <li key={item.report_id}>
                {captureDate(item.created_at)} · {item.total} variantes ·{" "}
                {item.responsible} ·{" "}
                {item.human_acknowledgement
                  ? "Con confirmación general"
                  : "Sin confirmación humana"}{" "}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      setReceipt(
                        await json(`/reports/monthly/${item.report_id}`, csrf),
                      );
                    })
                  }
                >
                  Abrir informe {item.report_id}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            disabled={busy || page === 1}
            onClick={() => void run(() => loadHistory(page - 1))}
          >
            Informes anteriores de la lista
          </button>
          <button
            type="button"
            disabled={busy || history.length < 12}
            onClick={() => void run(() => loadHistory(page + 1))}
          >
            Más informes
          </button>
        </>
      )}
    </details>
  );
}
