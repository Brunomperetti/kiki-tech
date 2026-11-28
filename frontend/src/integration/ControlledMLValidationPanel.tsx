import { useEffect, useRef, useState } from "react";
import { request } from "./catalog-adapter";
import { canWrite, production } from "./runtime";
import { loadResearch, type ResearchFact } from "./research-adapter";

type Validation = { id: number; ecomm_id: string; state: string; revision: number; preview_fingerprint: string; payload_preview: Record<string, unknown>; blockers: string[]; error_code?: string; official_payload_validated: boolean; publication_created: false; history: { action: string; at: string }[] };
const base = "/api/ecomm-app/workspace/channels/ml/validations";
const fields = { seller_id: "ID del vendedor autorizado", category_id: "ID oficial de categoría", price: "Precio real (sólo para validar)", currency_id: "Moneda", available_quantity: "Cantidad real (sólo para validar)", condition: "Condición oficial", buying_mode: "Modalidad de venta", listing_type_id: "Modalidad de publicación oficial" };
const states: Record<string, string> = { PREVIEW: "Pendiente de confirmación", BLOCKED: "Requiere revisión", RUNNING: "Validación iniciada; consultar antes de repetir", VALIDATED: "HTTP 204: este contenido fue validado", REJECTED: "El canal rechazó la validación", UNKNOWN: "Respuesta incierta; sin reintento automático" };

export function ControlledMLValidationPanel({ id, csrf, blocked }: { id: string; csrf: string; blocked: boolean }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [enabled, setEnabled] = useState(false);
  const [items, setItems] = useState<Validation[]>([]), [selected, setSelected] = useState<Validation>();
  const [values, setValues] = useState<Record<string, string>>({}), [reason, setReason] = useState(""), [error, setError] = useState("");
  const [facts, setFacts] = useState<ResearchFact[]>([]), [attributeIds, setAttributeIds] = useState<Record<string, string>>({});
  const epoch = useRef(0);
  useEffect(() => { epoch.current++; setOpen(false); setItems([]); setSelected(undefined); setEnabled(false); setValues({}); setFacts([]); setAttributeIds({}); setReason(""); setError(""); setBusy(false); return () => { epoch.current++; }; }, [id]);
  async function json(path: string, body?: unknown) {
    const response = await request(path, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body) });
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "No se pudo completar la validación.");
    return value;
  }
  async function run(action: () => Promise<void>) {
    const generation = epoch.current;
    setBusy(true); setError("");
    try { await action(); } catch (e) { if (generation === epoch.current) setError((e as Error).message); } finally { if (generation === epoch.current) setBusy(false); }
  }
  async function load() {
    const generation = epoch.current;
    const [value, evidence] = await Promise.all([json(base + "?ecomm_id=" + encodeURIComponent(id)), loadResearch(id)]);
    if (generation !== epoch.current) return;
    if (evidence.ecomm_id !== id) throw new Error("Las evidencias corresponden a otra variante.");
    const current = evidence.facts.filter(fact => fact.ecomm_id === id && fact.state === "APPROVED" && fact.verified === true && !fact.blockers.length);
    setFacts(current);
    setAttributeIds(prior => Object.fromEntries(Object.entries(prior).filter(([, selectedId]) => current.some(fact => fact.id === selectedId))));
    if (!Array.isArray(value.items) || value.items.some((item: Validation) => item.ecomm_id !== id || item.publication_created !== false)) throw new Error("Registro de validación incompatible.");
    setItems(value.items); setEnabled(value.official_validation_enabled === true);
  }
  async function prepare() {
    const generation = epoch.current;
    const attrs = Object.entries(attributeIds).flatMap(([key, selectedId]) => {
      const fact = facts.find(item => item.id === selectedId && item.ecomm_id === id && item.state === "APPROVED" && item.verified === true);
      return fact ? [{ id: key, value_name: fact.value, fact_id: fact.id }] : [];
    });
    const parameters: Record<string, unknown> = {};
    for (const key of Object.keys(fields)) parameters[key] = values[key]?.trim() || null;
    for (const key of ["price", "available_quantity"]) if (parameters[key] !== null) parameters[key] = Number(parameters[key]);
    parameters.attributes = attrs;
    const value = await json(base + "/preview", { request_key: crypto.randomUUID(), ecomm_id: id, parameters, reason });
    if (generation !== epoch.current) return;
    if (value.ecomm_id !== id || value.publication_created !== false) throw new Error("La validación corresponde a otra identidad.");
    setSelected(value); await load();
  }
  async function validate(item: Validation) {
    if (!enabled || blocked || !canWrite() || item.state !== "PREVIEW") return;
    if (!window.confirm("¿Consultar la validación oficial de este único contenido revisado? Se verificará vendedor, categoría y atributos. No se publicará ni se modificarán precio o stock. No se renovará OAuth.")) return;
    const generation = epoch.current;
    const value = await json(base + "/" + item.id + "/validate", { expected_revision: item.revision, expected_preview_fingerprint: item.preview_fingerprint, confirm: true });
    if (generation !== epoch.current) return;
    if (value.ecomm_id !== id || value.publication_created !== false) throw new Error("Respuesta incompatible; consultá el registro antes de repetir.");
    setSelected(value); await load();
  }
  if (!production) return null;
  return <section className="r-notice" aria-label="Validación oficial controlada Mercado Libre">
    <button type="button" disabled={busy} aria-expanded={open} onClick={() => { setOpen(!open); if (!open) void run(load); }}>Preparar validación oficial de Mercado Libre</button>
    {open && <>
      <p>{enabled ? "Validación oficial habilitada; requiere parámetros auténticos y confirmación." : "Validación oficial deshabilitada. Podés revisar los faltantes sin consultar al proveedor."}</p>
      <p>No publica ni modifica productos. Los datos ausentes se bloquean; no se inventan precio, cantidad, categoría ni vendedor. El resultado acredita únicamente el contenido y momento registrados.</p>
      <fieldset disabled={busy}><legend>Parámetros oficiales autorizados para Ecomm ID {id}</legend>{Object.entries(fields).map(([key, label]) => <label key={key}>{label}<input value={values[key] || ""} onChange={e => setValues({ ...values, [key]: e.target.value })} /></label>)}</fieldset>
      <fieldset disabled={busy}><legend>Elegir datos ya aprobados</legend><p>Seleccionar conserva la cita original; no aprueba hechos nuevos. Si faltan datos, revisalos en Evidencias.</p>{(["BRAND", "GTIN"] as const).map(key => {
        const choices = facts.filter(fact => key === "BRAND" ? fact.field === "brand" : ["ean", "gtin", "barcode"].includes(fact.field));
        const selectedFact = choices.find(fact => fact.id === attributeIds[key]);
        return <div key={key}><label>{key === "BRAND" ? "Marca aprobada para Mercado Libre" : "Código aprobado para Mercado Libre"}<select value={attributeIds[key] || ""} onChange={event => setAttributeIds({ ...attributeIds, [key]: event.target.value })}><option value="">{choices.length ? "Seleccionar hecho aprobado" : "Sin evidencia aprobada disponible"}</option>{choices.map(fact => <option key={fact.id} value={fact.id}>{fact.value} · {fact.presentation}</option>)}</select></label>{selectedFact && <p><q>{selectedFact.quote}</q> · {selectedFact.location}</p>}</div>;
      })}</fieldset>
      <label>Revisión y procedencia de estos parámetros<textarea value={reason} maxLength={600} onChange={e => setReason(e.target.value)} /></label>
      <button type="button" disabled={busy || blocked || !canWrite() || reason.trim().length < 20} onClick={() => void run(prepare)}>Previsualizar validación sin consultas externas</button>
      {selected?.ecomm_id === id && <><h4>#{selected.id} · {states[selected.state] || selected.state}</h4><pre>{JSON.stringify(selected.payload_preview, null, 2)}</pre>{selected.blockers.length > 0 && <ul>{selected.blockers.map((item, index) => <li key={index}>{item}</li>)}</ul>}<button type="button" disabled={busy || blocked || !enabled || !canWrite() || selected.state !== "PREVIEW"} onClick={() => void run(() => validate(selected))}>Confirmar consulta a /items/validate · No publica</button></>}
      <button type="button" disabled={busy} onClick={() => void run(load)}>Consultar historial de validaciones</button>
      <ul>{items.map(item => <li key={item.id}><button type="button" onClick={() => setSelected(item)}>#{item.id} · {states[item.state] || item.state}</button>{item.error_code && <> · {item.error_code}</>}<details><summary>Historial</summary><ul>{item.history.map((event, index) => <li key={index}>{event.at} · {event.action}</li>)}</ul></details></li>)}</ul>
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
