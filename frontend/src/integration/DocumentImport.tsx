import { documentalPath } from "./documental-paths";
import { useState } from "react";
import { request, captureDate } from "./catalog-adapter";
import {
  isHileret,
  hileretOriginalSha,
  hileretOriginalSize,
} from "./hileret-pilot";
import {
  changeResearch,
  type Dossier,
  type ResearchDocument,
} from "./research-adapter";

const basePath = (id: string) => documentalPath(id, "documents");
export function DocumentImport({
  id,
  csrf,
  data,
  document,
  busy,
  onBusy,
  onResult,
  onError,
}: {
  id: string;
  csrf: string;
  data: Dossier;
  document?: ResearchDocument;
  busy: boolean;
  onBusy: (v: boolean) => void;
  onResult: (value: Dossier, message: string) => void;
  onError: (value: string) => void;
}) {
  const [kind, setKind] = useState("FILE"),
    [file, setFile] = useState<File>();
  const [note, setNote] = useState(""),
    [url, setUrl] = useState("");
  const [official, setOfficial] = useState(false),
    [authorized, setAuthorized] = useState(false);
  const [replace, setReplace] = useState(false),
    [reason, setReason] = useState("");
  const [originalInfo, setOriginalInfo] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [consultedDate, setConsultedDate] = useState("");
  const local = document?.body.synthetic === false;
  async function perform(action: () => Promise<void>) {
    onBusy(true);
    onError("");
    try {
      await action();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      onBusy(false);
    }
  }
  async function incorporate() {
    await perform(async () => {
      if (!authorized)
        throw new Error(
          "Autorizá expresamente el procesamiento local de este archivo o referencia.",
        );
      let encoded = "";
      if (kind === "FILE") {
        if (
          !file ||
          !file.size ||
          (file.size > 524288 &&
            !(isHileret(id) && file.size === hileretOriginalSize))
        )
          throw new Error("Elegí un archivo no vacío de hasta 512 KiB.");
        const bytes = new Uint8Array(await file.arrayBuffer());
        if (file.size > 524288) {
          const hash = Array.from(
            new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
          )
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("");
          if (hash !== hileretOriginalSha)
            throw new Error(
              "El PDF no coincide con el SHA-256 autorizado para este piloto. No se amplía el límite general de 512 KiB.",
            );
        }
        const chunks: string[] = [];
        for (let offset = 0; offset < bytes.length; offset += 32768)
          chunks.push(
            String.fromCharCode(...bytes.subarray(offset, offset + 32768)),
          );
        encoded = btoa(chunks.join(""));
      }
      const value = await changeResearch(
        id,
        `${basePath(id)}/import`,
        {
          kind,
          expected_version: data.version,
          filename: kind === "FILE" ? file!.name : "",
          content_type:
            kind === "FILE"
              ? file!.type ||
                {
                  pdf: "application/pdf",
                  txt: "text/plain",
                  html: "text/html",
                  json: "application/json",
                }[file!.name.split(".").pop()!.toLowerCase()] ||
                ""
              : "",
          content_base64: encoded,
          provenance_note: note,
          reference_url: url,
          declared_official: official,
          declared_manufacturer: manufacturer,
          declared_consulted_at: consultedDate
            ? `${consultedDate}T00:00:00Z`
            : null,
          authorized_local_processing: true,
          ...(replace && local
            ? {
                document_id: document!.id,
                expected_document_version: document!.version,
              }
            : {}),
        },
        csrf,
      );
      setAuthorized(false);
      setReplace(false);
      setOriginalInfo("");
      onResult(
        value,
        "Documento incorporado en PostgreSQL de pruebas. La procedencia y cada dato requieren revisión independiente.",
      );
    });
  }
  async function review(decision: string) {
    if (
      !document ||
      !window.confirm(
        "¿Registrar esta revisión de procedencia? No aprueba datos ni certifica autenticidad. Se invalidarán las evidencias de la versión anterior.",
      )
    )
      return;
    await perform(async () =>
      onResult(
        await changeResearch(
          id,
          `${basePath(id)}/${document.id}/provenance`,
          {
            expected_document_version: document.version,
            decision,
            reason,
          },
          csrf,
        ),
        "Revisión de procedencia registrada. Extraé y revisá los hechos de esta versión; no se aplicaron campos comerciales.",
      ),
    );
  }
  return (
    <div className="r-upload">
      <details className="r-document">
        <summary>Incorporar archivo local o referencia oficial</summary>
        <label>
          Fabricante declarado por quien suministra el documento (opcional)
          <input
            value={manufacturer}
            maxLength={180}
            onChange={(e) => setManufacturer(e.target.value)}
          />
        </label>
        <label>
          Fecha de consulta informada por el usuario (opcional)
          <input
            type="date"
            value={consultedDate}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setConsultedDate(e.target.value)}
          />
        </label>
        <p>
          Procesamiento local aislado. No se envían archivos a terceros. PDF con
          texto (máximo 10 páginas), TXT UTF-8, HTML pasivo sin atributos o JSON
          estructurado; hasta 512 KiB. Sin OCR ni búsquedas web.
        </p>
        {isHileret(id) && (
          <p>
            Excepción acotada: sólo el folleto Hileret original de 6.232.081
            bytes, identificado por SHA-256, admite su tamaño completo y
            extracción de página 2. No se aprueba automáticamente.
          </p>
        )}
        <label>
          Origen a incorporar
          <select
            aria-label="Origen a incorporar"
            value={kind}
            disabled={busy}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="FILE">Archivo local</option>
            <option value="URL">Referencia URL · sin descargar</option>
          </select>
        </label>
        {kind === "FILE" && (
          <label>
            Archivo documental
            <input
              type="file"
              aria-label="Archivo documental"
              accept=".pdf,.txt,.html,.json"
              disabled={busy}
              onChange={(e) => setFile(e.target.files?.[0])}
            />
          </label>
        )}
        <label>
          Cómo obtuve la documentación
          <textarea
            aria-label="Cómo obtuve la documentación"
            maxLength={600}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <label>
          URL de referencia (sin acceder)
          <input
            aria-label="URL de referencia (sin acceder)"
            type="url"
            maxLength={1000}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <label className="r-check">
          <input
            type="checkbox"
            checked={official}
            onChange={(e) => setOfficial(e.target.checked)}
          />
          Declaro que la fuente es oficial; todavía no está verificada
        </label>
        {local && (
          <label className="r-check">
            <input
              type="checkbox"
              checked={replace}
              onChange={(e) => setReplace(e.target.checked)}
            />
            Reemplazar el documento local seleccionado y conservar su historial
          </label>
        )}
        <label className="r-check">
          <input
            type="checkbox"
            checked={authorized}
            onChange={(e) => setAuthorized(e.target.checked)}
          />
          Autorizo expresamente el procesamiento local de este documento o
          referencia
        </label>
        <button
          disabled={
            busy ||
            !authorized ||
            note.trim().length < 10 ||
            (kind === "FILE" ? !file : !url)
          }
          onClick={incorporate}
        >
          Incorporar documentación
        </button>
      </details>
      {local && document && (
        <section
          className="r-document"
          aria-label="Procedencia del documento local"
        >
          <h4>Procedencia y original conservado</h4>
          {document.body.retrieval?.simulated && (
            <p className="r-notice">
              <strong>Fuente SIMULADA</strong> · Transferencia de prueba, no
              documentación auténtica. La revisión de procedencia es humana
              sobre este ejemplo.
              <br />
              URL inicial: {document.body.retrieval.requested_url}
              <br />
              Destino final simulado: {document.body.retrieval.final_url} ·{" "}
              {captureDate(document.body.retrieval.acquired_at)}
            </p>
          )}
          <details>
            <summary>
              Identidad extraída y ubicación · Sin aprobación automática
            </summary>
            {Object.entries(document.body.identity_evidence || {}).map(
              ([key, evidence]) => (
                <p key={key}>
                  <strong>
                    {{
                      name: "Nombre",
                      brand: "Marca",
                      manufacturer: "Fabricante",
                      ean: "EAN",
                      presentation: "Presentación",
                      sale_type: "Tipo de venta",
                    }[key] || key}
                    : {evidence.value}
                  </strong>
                  <br />
                  <code>{evidence.location}</code> · «{evidence.quote}»
                </p>
              ),
            )}
          </details>
          <p>
            {document.body.source!.declared_official
              ? "Fuente declarada como oficial"
              : "Fuente local sin declaración oficial"}
            . Esa declaración no prueba autenticidad.
          </p>
          <p>
            Procedencia:{" "}
            <strong>
              {{
                PENDING: "Pendiente de revisión",
                REVIEWED: "Revisada por una persona",
                REJECTED: "Rechazada",
                REVOKED: "Revisión revocada",
              }[document.body.source!.review_state] ||
                document.body.source!.review_state}
            </strong>
          </p>
          <p>{document.body.source!.note}</p>
          <p>
            Fabricante declarado:{" "}
            {document.body.source!.declared_manufacturer || "No informado"} ·
            Fabricante extraído:{" "}
            {document.body.identity.manufacturer || "No identificado"}
          </p>
          <p>
            Dominio de referencia:{" "}
            {document.body.source!.reference_url
              ? new URL(document.body.source!.reference_url).hostname
              : "Sin dominio informado"}
            <br />
            Fecha de consulta declarada:{" "}
            {document.body.source!.declared_consulted_at
              ? document.body
                  .source!.declared_consulted_at.slice(0, 10)
                  .split("-")
                  .reverse()
                  .join("/")
              : "No informada; no se supone a partir de la carga"}
          </p>
          <p>
            {document.body.source!.reference_url || "Sin URL declarada"} · No
            consultada por el navegador
          </p>
          <p>
            Registrado por {document.body.source!.registered_by} ·{" "}
            {captureDate(document.body.source!.registered_at)}
          </p>
          {document.body.source!.reviewer && (
            <p>
              Revisado por {document.body.source!.reviewer} ·{" "}
              {captureDate(document.body.source!.reviewed_at)} ·{" "}
              {document.body.source!.review_reason}
            </p>
          )}
          <p>
            Lectura:{" "}
            {
              {
                TEXT_EXTRACTED:
                  "Texto accesible y datos identificados; sin aprobar",
                NEEDS_OCR:
                  "Requiere OCR u otro procesamiento: PDF sin texto accesible",
                INSUFFICIENT_DATA:
                  "Información insuficiente: no se identificaron datos",
                REFERENCE_ONLY: "Sólo referencia: sin descarga ni extracción",
              }[document.body.parse_status!]
            }
          </p>
          {document.body.parser_warnings?.map((v) => (
            <p role="note" key={v}>
              {v}
            </p>
          ))}
          <p>
            Original:{" "}
            {document.body.original!.filename || "Referencia URL reproducible"}{" "}
            · {document.body.original!.size} bytes
            <br />
            {document.body.origin_kind === "URL"
              ? "SHA-256 de la URL (no del PDF)"
              : "SHA-256 del archivo"}
            : <code>{document.body.original!.sha256}</code>
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const value = await (
                  await request(
                    `${basePath(id)}/${document.id}/original/${document.version}`,
                  )
                ).json();
                const bytes =
                  document.body.origin_kind === "FILE"
                    ? Uint8Array.from(atob(value.content_base64), (c) =>
                        c.charCodeAt(0),
                      )
                    : new TextEncoder().encode(value.reference_url);
                const actualHash = Array.from(
                  new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
                )
                  .map((byte) => byte.toString(16).padStart(2, "0"))
                  .join("");
                if (
                  value.ecomm_id !== id ||
                  value.version !== document.version ||
                  actualHash !== document.body.original!.sha256 ||
                  (document.body.origin_kind === "FILE" &&
                    bytes.length !== document.body.original!.size) ||
                  value.original.sha256 !== document.body.original!.sha256
                )
                  throw new Error(
                    "El original recuperado no coincide con esta versión.",
                  );
                setOriginalInfo(
                  `Original v${value.version} recuperado desde PostgreSQL · ${value.original.size} bytes · ${value.original.sha256}`,
                );
              })
            }
          >
            Comprobar original conservado
          </button>
          {originalInfo && <p role="status">{originalInfo}</p>}
          <label>
            Motivo de revisión de procedencia
            <textarea
              aria-label="Motivo de revisión de procedencia"
              maxLength={600}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className="r-actions">
            <button
              disabled={busy || reason.trim().length < 10}
              onClick={() => review("REVIEWED")}
            >
              Registrar revisión de procedencia
            </button>
            <button
              disabled={busy || reason.trim().length < 10}
              onClick={() => review("REJECTED")}
            >
              Rechazar procedencia
            </button>
            <button
              disabled={
                busy ||
                reason.trim().length < 10 ||
                document.body.source!.review_state !== "REVIEWED"
              }
              onClick={() => review("REVOKED")}
            >
              Revocar procedencia
            </button>
          </div>
          <details>
            <summary>
              Versiones anteriores del documento ({document.history.length})
            </summary>
            {document.history.map((h) => (
              <div className="r-history" key={h.version}>
                <strong>
                  Versión {h.version} · {h.action}
                </strong>
                <p>
                  {h.actor} · {captureDate(h.at)}
                </p>
                <p>Original SHA-256: {h.body.original?.sha256}</p>
                <p>Procedencia: {h.body.source?.review_state}</p>
                {Object.entries(h.body.sections).map(([loc, text]) => (
                  <p key={loc}>
                    <code>{loc}</code> · {text}
                  </p>
                ))}
              </div>
            ))}
          </details>
        </section>
      )}
    </div>
  );
}
