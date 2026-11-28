import { useEffect, useRef, useState } from "react";
import { request } from "./catalog-adapter";
import { canWrite, production } from "./runtime";

type Submission = {
  id: number; ecomm_id: string; state: string; revision: number;
  operation: "CREATE_HIDDEN" | "UPDATE_CONTENT";
  preview_fingerprint: string; blockers: string[];
  target_product_id?: string; target_variant_id?: string;
  payload_preview: Record<string, unknown>;
  error_code?: string; provider_calls: number;
  product_admin_url?: string; optional_fields_notice?: string;
  history: { action: string; at: string }[];
};
const base = "/api/ecomm-app/workspace/channels/tn/submissions";
const stateLabels: Record<string, string> = {
  FAILED: "Tiendanube rechazó el envío; revisá el motivo antes de preparar otro",
  PREVIEW: "Pendiente de confirmación", BLOCKED: "Requiere revisión",
  RUNNING: "Envío iniciado; consultar antes de repetir", UNKNOWN: "Resultado incierto; revisar en Tiendanube",
  SUCCEEDED: "Contenido enviado con confirmación",
};
const errorLabels: Record<string, string> = {
  REMOTE_DUPLICATE_OR_INCOMPLETE_IDENTITY: "Se encontró un posible duplicado o un registro sin identidad suficiente. No se creó ningún producto.",
  REMOTE_PREFLIGHT_FAILED: "No se pudo completar la comprobación de duplicados. No se envió el producto.",
  LOCAL_EVIDENCE_CHANGED: "La ficha cambió durante la revisión. Volvé a previsualizar antes de enviar.",
  LOCAL_CAPTURE_CHANGED: "La captura del canal cambió. Revisá nuevamente antes de enviar.",
  PROVIDER_OUTCOME_UNKNOWN: "No se pudo confirmar la respuesta. Revisá la tienda antes de repetir: el producto podría haberse creado.",
  PROVIDER_HTTP_401: "Tiendanube rechazó la autorización. Pedí al administrador revisar la conexión; no se renuevan credenciales automáticamente.",
  PROVIDER_HTTP_403: "La aplicación no tiene permiso para crear productos en esta tienda. El administrador debe verificar los alcances de autorización.",
  PROVIDER_HTTP_422: "Tiendanube rechazó los datos del producto. Revisá los campos y los requisitos de la tienda.",
  PROVIDER_HTTP_429: "Tiendanube limitó las solicitudes. No se reintentará automáticamente.",
};
const labels = { brand: "Marca", name: "Nombre exacto", presentation: "Presentación", quantity: "Cantidad comercial", pack: "Unidad, pack o combo", barcode: "EAN/GTIN y sus límites" };

export function ControlledSubmissionPanel({ id, csrf, blocked }: { id: string; csrf: string; blocked: boolean }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false);
  const [items, setItems] = useState<Submission[]>([]), [selected, setSelected] = useState<Submission>();
  const [enabled, setEnabled] = useState(false), [error, setError] = useState("");
  const [operation, setOperation] = useState<Submission["operation"]>("CREATE_HIDDEN");
  const [product, setProduct] = useState(""), [variant, setVariant] = useState(""), [reason, setReason] = useState("");
  const [checks, setChecks] = useState<string[]>([]);
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    setOpen(false); setItems([]); setSelected(undefined); setEnabled(false); setError("");
    setChecks([]); setReason(""); setProduct(""); setVariant(""); setBusy(false);
    return () => { generation.current++; };
  }, [id]);
  async function json(path: string, body?: unknown) {
    const response = await request(path, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "No se pudo completar la operación. Conservá el registro y revisá su estado.");
    return value;
  }
  async function run(action: () => Promise<void>) {
    const epoch = generation.current;
    setBusy(true); setError("");
    try { await action(); } catch (e) { if (epoch === generation.current) setError((e as Error).message); } finally { if (epoch === generation.current) setBusy(false); }
  }
  async function load() {
    const epoch = generation.current;
    const value = await json(base + "?ecomm_id=" + encodeURIComponent(id));
    if (epoch !== generation.current) return;
    if (!Array.isArray(value.items) || value.items.some((item: Submission) => item.ecomm_id !== id)) throw new Error("Registro de envío incompatible con esta variante.");
    setItems(value.items); setEnabled(value.external_writes_enabled === true);
  }
  async function prepare() {
    const epoch = generation.current;
    const value = await json(base + "/preview", {
      request_key: crypto.randomUUID(), ecomm_id: id, operation, identity_checks: checks,
      review_mode: operation === "CREATE_HIDDEN" ? "MANUAL" : "DOCUMENTED",
      reason: operation === "CREATE_HIDDEN" ? "Revisé manualmente nombre, marca, presentación, cantidad, unidad o pack y códigos de esta variante; autorizo preparar un borrador oculto." : reason,
      target_product_id: operation === "UPDATE_CONTENT" ? product : null,
      target_variant_id: operation === "UPDATE_CONTENT" ? variant : null,
    });
    if (epoch !== generation.current) return;
    if (value.ecomm_id !== id || !Array.isArray(value.blockers)) throw new Error("La identidad de la previsualización no coincide.");
    setSelected(value); await load();
  }
  async function send(item: Submission) {
    if (!enabled || item.state !== "PREVIEW" || item.ecomm_id !== id || !canWrite()) return;
    if (!window.confirm(item.operation === "CREATE_HIDDEN" ? "¿Crear este único producto OCULTO en Tiendanube? No se enviarán precios ni stock. Se comprobarán duplicados antes de escribir." : "¿Actualizar únicamente el contenido del producto Tiendanube seleccionado? No se modificarán visibilidad, precios ni stock.")) return;
    const epoch = generation.current;
    // No retry: an uncertain response requires reading the durable ledger.
    const value = await json(base + "/" + item.id + "/send", {
      expected_revision: item.revision, expected_preview_fingerprint: item.preview_fingerprint, confirm: true,
    });
    if (epoch !== generation.current) return;
    if (value.ecomm_id !== id) throw new Error("Registro de otra variante rechazado.");
    setSelected(value); await load();
  }
  if (!production) return null;
  return <section className="r-notice" aria-label="Envíos controlados a Tiendanube">
    <button type="button" aria-expanded={open} disabled={busy} onClick={() => { setOpen(!open); if (!open) void run(load); }}>Cargar producto en Tiendanube</button>
    {open && <>
      <p>{enabled ? "Escritura habilitada por configuración; cada envío requiere confirmación." : "Escrituras deshabilitadas. La previsualización local no modifica la tienda."}</p>
      <p>Guardá primero los cambios en Ficha. La creación oculta sólo exige un nombre y un SKU único; no requiere IA, documentación ni completar los 18 campos. Revisá que el nombre incluya la presentación.</p>
      <p>Identidad Ecomm-App: <strong>{id}</strong>. Un envío incierto o interrumpido se reconcilia antes de repetirlo. No se publican productos.</p>
      <label>Operación <select value={operation} disabled={busy} onChange={e => { setOperation(e.target.value as Submission["operation"]); setSelected(undefined); }}><option value="CREATE_HIDDEN">Crear producto oculto</option><option value="UPDATE_CONTENT">Actualizar contenido existente</option></select></label>
      {operation === "UPDATE_CONTENT" && <><label>ID de producto Tiendanube <input value={product} onChange={e => setProduct(e.target.value)} inputMode="numeric" /></label><label>ID de variante Tiendanube <input value={variant} onChange={e => setVariant(e.target.value)} inputMode="numeric" /></label></>}
      <fieldset disabled={busy}><legend>Revisión del producto</legend>{operation === "CREATE_HIDDEN" ? <label><input type="checkbox" checked={checks.length === 6} onChange={e => { setChecks(e.target.checked ? Object.keys(labels) : []); setSelected(undefined); }} />Revisé nombre, marca, presentación, cantidad, unidad o pack y EAN de esta variante. Los datos guardados son correctos.</label> : Object.entries(labels).map(([key, label]) => <label key={key}><input type="checkbox" checked={checks.includes(key)} onChange={e => setChecks(e.target.checked ? [...checks, key] : checks.filter(v => v !== key))} />{label}</label>)}</fieldset>
      {operation === "UPDATE_CONTENT" && <label>Conclusión de la revisión <textarea value={reason} maxLength={600} onChange={e => setReason(e.target.value)} /></label>}
      <button type="button" disabled={busy || blocked || !canWrite() || checks.length !== 6 || (operation === "UPDATE_CONTENT" && reason.trim().length < 20)} onClick={() => void run(prepare)}>Previsualizar para Tiendanube</button>
      {selected?.ecomm_id === id && <><h4>Envío #{selected.id}: {stateLabels[selected.state] || selected.state}</h4><p>{selected.operation} · Producto TN {selected.target_product_id || "pendiente de creación"} · Variante TN {selected.target_variant_id || "pendiente"}</p><div aria-label="Vista previa del producto oculto"><h4>{(selected.payload_preview.name as { es?: string })?.es}</h4><p>Se creará oculto para revisar antes de publicar.</p><dl>{Object.entries(selected.payload_preview).filter(([key]) => !["name", "published", "visibility"].includes(key)).map(([key, value]) => <div key={key}><dt>{({ description: "Descripción", brand: "Marca", variants: "SKU y EAN", seo_title: "Título SEO", seo_description: "Descripción SEO" } as Record<string, string>)[key] || key}</dt><dd style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{typeof value === "string" ? value : Array.isArray(value) ? value.map(v => `SKU: ${v.sku}${v.barcode ? ` · EAN: ${v.barcode}` : " · EAN no disponible"}`).join("\n") : (value as { es?: string })?.es}</dd></div>)}</dl><p>{selected.optional_fields_notice}</p></div>{selected.blockers.length > 0 && <ul>{selected.blockers.map((b, i) => <li key={i}>{b}</li>)}</ul>}<button type="button" disabled={busy || blocked || !canWrite() || !enabled || selected.state !== "PREVIEW"} onClick={() => void run(() => send(selected))}>{selected.operation === "CREATE_HIDDEN" ? "Enviar a Tiendanube" : "Confirmar actualización de contenido"}</button></>}
      <button type="button" disabled={busy} onClick={() => void run(load)}>Consultar resultado del envío</button>
      <ul>{items.map(item => <li key={item.id}><button type="button" onClick={() => setSelected(item)}>#{item.id} · {item.operation === "CREATE_HIDDEN" ? "Creación oculta" : "Actualización de contenido"} · {stateLabels[item.state] || item.state}</button>{item.target_product_id && <> · Producto TN {item.target_product_id}</>}{item.state === "SUCCEEDED" && item.product_admin_url && <> · <a href={item.product_admin_url} target="_blank" rel="noopener noreferrer">Revisar producto en Tiendanube</a></>}{item.error_code && <> · {errorLabels[item.error_code] || "Tiendanube no confirmó la operación. Consultá el estado antes de repetir."}</>}<details><summary>Historial del envío</summary><ul>{item.history.map((event, i) => <li key={i}>{event.at} · {event.action}</li>)}</ul></details></li>)}</ul>
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
