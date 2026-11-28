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
  history: { action: string; at: string }[];
};
const base = "/api/ecomm-app/workspace/channels/tn/submissions";
const stateLabels: Record<string, string> = {
  PREVIEW: "Pendiente de confirmación", BLOCKED: "Requiere revisión",
  RUNNING: "Envío iniciado; consultar antes de repetir", UNKNOWN: "Resultado incierto; revisar en Tiendanube",
  SUCCEEDED: "Contenido enviado con confirmación",
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
      request_key: crypto.randomUUID(), ecomm_id: id, operation, identity_checks: checks, reason,
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
    <button type="button" aria-expanded={open} disabled={busy} onClick={() => { setOpen(!open); if (!open) void run(load); }}>Preparar envío controlado a Tiendanube</button>
    {open && <>
      <p>{enabled ? "Escritura habilitada por configuración; cada envío requiere confirmación." : "Escrituras deshabilitadas. La previsualización local no modifica la tienda."}</p>
      <p>Identidad Ecomm-App: <strong>{id}</strong>. Un envío incierto o interrumpido se reconcilia antes de repetirlo. No se publican productos.</p>
      <label>Operación <select value={operation} disabled={busy} onChange={e => { setOperation(e.target.value as Submission["operation"]); setSelected(undefined); }}><option value="CREATE_HIDDEN">Crear producto oculto</option><option value="UPDATE_CONTENT">Actualizar contenido existente</option></select></label>
      {operation === "UPDATE_CONTENT" && <><label>ID de producto Tiendanube <input value={product} onChange={e => setProduct(e.target.value)} inputMode="numeric" /></label><label>ID de variante Tiendanube <input value={variant} onChange={e => setVariant(e.target.value)} inputMode="numeric" /></label></>}
      <fieldset disabled={busy}><legend>Revisión humana de identidad comercial</legend>{Object.entries(labels).map(([key, label]) => <label key={key}><input type="checkbox" checked={checks.includes(key)} onChange={e => setChecks(e.target.checked ? [...checks, key] : checks.filter(v => v !== key))} />{label}</label>)}</fieldset>
      <label>Conclusión de la revisión <textarea value={reason} maxLength={600} onChange={e => setReason(e.target.value)} /></label>
      <button type="button" disabled={busy || blocked || !canWrite() || checks.length !== 6 || reason.trim().length < 20} onClick={() => void run(prepare)}>Previsualizar y registrar autorización</button>
      {selected?.ecomm_id === id && <><h4>Envío #{selected.id}: {stateLabels[selected.state] || selected.state}</h4><p>{selected.operation} · Producto TN {selected.target_product_id || "pendiente de creación"} · Variante TN {selected.target_variant_id || "pendiente"}</p><pre>{JSON.stringify(selected.payload_preview, null, 2)}</pre>{selected.blockers.length > 0 && <ul>{selected.blockers.map((b, i) => <li key={i}>{b}</li>)}</ul>}<button type="button" disabled={busy || blocked || !canWrite() || !enabled || selected.state !== "PREVIEW"} onClick={() => void run(() => send(selected))}>{selected.operation === "CREATE_HIDDEN" ? "Confirmar creación oculta" : "Confirmar actualización de contenido"}</button></>}
      <button type="button" disabled={busy} onClick={() => void run(load)}>Consultar estado persistente</button>
      <ul>{items.map(item => <li key={item.id}><button type="button" onClick={() => setSelected(item)}>#{item.id} · {item.operation === "CREATE_HIDDEN" ? "Creación oculta" : "Actualización de contenido"} · {stateLabels[item.state] || item.state}</button>{item.target_product_id && <> · Producto TN {item.target_product_id}</>}{item.error_code && <> · {item.error_code}</>}<details><summary>Historial del envío</summary><ul>{item.history.map((event, i) => <li key={i}>{event.at} · {event.action}</li>)}</ul></details></li>)}</ul>
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
