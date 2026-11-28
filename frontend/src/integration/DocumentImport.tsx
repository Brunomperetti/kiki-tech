import { environmentText, production, capabilities } from "./runtime";
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
  const [kind, setKind] = useState(
      production && !capabilities?.document_upload ? "URL" : "FILE",
    ),
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
  const [webSnapshot, setWebSnapshot] = useState(false);
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
      if (kind === "FILE" && webSnapshot && (
        !file?.name.toLowerCase().endsWith(".html") ||
        !url.startsWith("https://") || !consultedDate
      )) throw new Error("La página guardada necesita archivo .html, URL HTTPS y fecha de consulta.");
      let encoded = "";
      if (kind === "FILE") {
        const savedOriginalHtml = webSnapshot && !!file?.name.toLowerCase().endsWith(".html");
        const largeOriginalLimit = 4 * 1024 * 1024;
        const hileretOriginal = (isHileret(id) || production) &&
          file?.size === hileretOriginalSize;
        if (
          !file ||
          !file.size ||
          (savedOriginalHtml && file.size > largeOriginalLimit) ||
          (file.size > 524288 && !savedOriginalHtml && !hileretOriginal)
        )
          throw new Error(
            savedOriginalHtml
              ? "El HTML original debe tener como máximo 4 MiB. No se importó."
              : "El documento debe tener como máximo 512 KiB (salvo excepción Hileret).",
          );
        const bytes = new Uint8Array(await file.arrayBuffer());
        if (file.size > 524288 && !savedOriginalHtml) {
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
          web_snapshot: kind === "FILE" && webSnapshot,
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
        environmentText(
          "Documento incorporado en PostgreSQL de pruebas. La procedencia y cada dato requieren revisión independiente.",
          "Documento incorporado en KIKI PostgreSQL. La procedencia y cada dato requieren revisión independiente.",
        ),
      );
    });
  }
  async function fetchManufacturerSource() {
    if (!authorized || !url.startsWith("https://") || note.trim().length < 10)
      return onError("La consulta requiere URL HTTPS, motivo y autorización.");
    if (!window.confirm(
      "¿Consultar UNA página pública del fabricante? KIKI validará el dominio, robots.txt y TLS, archivará el HTML, y dejará TODOS los datos pendientes de revisión. No publica ni modifica canales."
    )) return;
    await perform(async () => {
      const value = await changeResearch(
        id,
        `${basePath(id)}/fetch-manufacturer`,
        {
          expected_version: data.version,
          reference_url: url,
          provenance_note: note,
          authorized_local_processing: true,
        },
        csrf,
      );
      setAuthorized(false);
      onResult(
        value,
        "HTML original obtenido por HTTPS y archivado en KIKI. Revisá identidad, procedencia y cada hecho antes de generar una ficha."
      );
    });
  }
  async function fetchExactReviewedURL() {
    if (!authorized || !url.startsWith("https://") || note.trim().length < 10) {
      onError("Indicá la URL HTTPS exacta, cómo identificaste la fuente y autorizá su consulta.");
      return;
    }
    if (!window.confirm(
      "¿Incorporar esta única URL de fabricante? KIKI comprobará dominio autorizado, robots.txt, HTTPS y redirecciones; archivará el HTML como PENDIENTE. Debés revisar identidad y cada hecho. No utiliza IA ni publica productos."
    )) return;
    await perform(async () => {
      const value = await changeResearch(
        id, `${basePath(id)}/fetch-reviewed-url`,
        {
          expected_version: data.version,
          reference_url: url.trim(),
          provenance_note: note.trim(),
          authorized_local_processing: true,
        },
        csrf,
      );
      setAuthorized(false);
      onResult(
        value,
        "HTML original incorporado como evidencia PENDIENTE. Revisá procedencia, identidad y cada dato antes de generar la ficha."
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
          texto (máximo 10 páginas), TXT UTF-8, HTML pasivo o captura HTML
          guardada de una página web, y JSON estructurado. Máximo 512 KiB
          para documentos comunes; HTML original guardado desde navegador:
          hasta 4 MiB, con procesamiento aislado y límites de complejidad.
          No navega Internet, no ejecuta scripts ni verifica la autenticidad.
        </p>
        {(isHileret(id) || production) && (
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
            <option
              value="FILE"
              disabled={production && !capabilities?.document_upload}
            >
              Archivo local
            </option>
            <option value="URL">Referencia URL · sin descargar</option>
          </select>
        </label>
        {production && !capabilities?.document_upload && (
          <p role="status">
            Carga de archivos bloqueada: falta el lector documental aislado.
            Podés registrar una referencia URL sin descargar; no acredita hechos
            ni procedencia oficial.
          </p>
        )}
        {kind === "FILE" && (
          <label className="r-check">
            <input
              type="checkbox"
              disabled={busy}
              checked={webSnapshot}
              onChange={(e) => setWebSnapshot(e.target.checked)}
            />
            El archivo es una página web HTML original que guardé desde el navegador
            (no es transcripción). Se conserva su SHA-256; la URL y su
            autenticidad requieren revisión humana.
          </label>
        )}
        {kind === "FILE" && webSnapshot && (
          <p role="note">
            Para una página guardada son obligatorios la URL HTTPS y la fecha de
            consulta. El lector aislado ignora scripts y recursos externos.
            Extrae candidatos, nunca hechos aprobados.
          </p>
        )}
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
            (kind === "FILE" ? (!file || (webSnapshot && (!url.startsWith("https://") || !consultedDate))) : !url)
          }
          onClick={incorporate}
        >
          Incorporar documentación
        </button>
        {capabilities?.document_explicit_url_intake === true && (
          <div className="r-document" role="group" aria-label="Incorporar URL exacta de fabricante">
            <h4>Incorporar una URL exacta sin sitemap</h4>
            <p>
              Para fabricantes sin índice XML disponible: ingresá la página específica
              de esta variante y confirmá su consulta. Se comprueban HTTPS,
              robots.txt y dominio permitido. Se guarda como fuente pendiente,
              nunca como ficha aprobada. Máximo una nueva descarga automática
              por variante al día. Si está bloqueada, podés cargar el HTML
              original guardado manualmente.
            </p>
            <button
              type="button"
              disabled={busy || !authorized || note.trim().length < 10
                || !url.startsWith("https://")}
              onClick={() => void fetchExactReviewedURL()}
            >
              Consultar y archivar esta URL
            </button>
          </div>
        )}
        {capabilities?.document_fetch === true && (
          <div className="r-document" role="group" aria-label="Consulta puntual de fabricante">
            <h4>Obtener una página del fabricante (piloto)</h4>
            <p>
              Solo para la variante piloto y dominios habilitados. KIKI comprueba
              robots.txt y TLS, no sigue redirecciones y conserva el HTML
              original. No busca masivamente, no certifica EAN, no aprueba
              hechos ni publica. Si la web bloquea el acceso, usá la carga manual.
            </p>
            <button
              type="button"
              disabled={busy || !authorized || note.trim().length < 10
                || !url.startsWith("https://")}
              onClick={() => void fetchManufacturerSource()}
            >
              Consultar y archivar página autorizada
            </button>
          </div>
        )}
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
          {document.body.source?.capture_mode === "USER_SAVED_WEB_HTML" && (
            <p role="note">
              Captura HTML guardada por un operador. El sistema no comprobó la
              descarga ni autenticó el dominio. Se conserva el archivo original;
              revisar citas, identidad y procedencia antes de aprobar.
            </p>
          )}
          {document.body.source?.capture_mode === "ALLOWLISTED_HTTPS_FETCH" && (
            <p role="note">
              Página obtenida por KIKI mediante HTTPS y dominio autorizado.
              Se comprobó el permiso de robots.txt y la identidad TLS,
              y se archivó el original con SHA-256. Esto NO confirma que
              corresponda al SKU: la identidad, procedencia y hechos todavía
              requieren revisión humana.
            </p>
          )}
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
          {production && ["INSUFFICIENT_DATA", "TEXT_EXTRACTED"].includes(document.body.parse_status || "") &&
            (!document.body.identity?.name || !document.body.identity?.presentation) &&
            !data.facts.some((fact) => fact.document_id === document.id) &&
            document.body.source?.capture_mode === "USER_SAVED_WEB_HTML" &&
            document.body.source?.review_state === "PENDING" && (
              <button
                disabled={busy}
                onClick={() => {
                  if (!window.confirm(
                    "¿Volver a leer el HTML original guardado? No se descarga, no se consume IA y no se aprueban hechos.",
                  )) return;
                  void perform(async () => {
                    const value = await changeResearch(
                      id, `${basePath(id)}/${document.id}/reparse-saved-html`,
                      { expected_version: data.version,
                        document_version: document.version, confirm: true },
                      csrf,
                    );
                    onResult(value, "Original releído. Revisá procedencia, identidad y hechos candidatos.");
                  });
                }}
              >
                Volver a leer original guardado
              </button>
            )}

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
