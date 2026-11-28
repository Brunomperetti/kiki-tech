import { useEffect, useState } from "react";
import { request, validVariantId } from "./catalog-adapter";
import { fieldKeys } from "./workspace-adapter";
import type { EcommEditableFields } from "../types/ecomm-app";

type Field = keyof EcommEditableFields;
type Value = EcommEditableFields[Field];
type Choice = { decision: "ACCEPTED" | "REJECTED"; value: Value };
type Row = {
  ecomm_id: string; sku: string; name: string; presentation: string;
  workspace_version: number; draft_id: number | null; revision: number | null;
  state: "BLOCKED" | "REVIEW_REQUIRED"; reasons: string[];
  fields: Partial<Record<Field, {value: Value; current: Value; evidence_ids: string[]; clauses: string[]}>>;
  evidence: {id: string; document_id: string; location: string; quote: string; state: string}[];
};
type Preview = {
  schema_version: "kiki-commercial-review-v1"; total: number; fingerprint: string;
  items: Row[]; internal_only: true; external_writes_enabled: false;
};
const labels: Partial<Record<Field, string>> = {
  title: "Título comercial", short_title: "Título corto", description: "Descripción larga",
  short_description: "Descripción corta", details: "Detalles y características", attributes: "Atributos",
  brand: "Marca", manufacturer: "Fabricante", presentation: "Presentación", category: "Categoría",
  subcategory: "Subcategoría", seo_title: "Título SEO", seo_description: "Descripción SEO", seo_keywords: "Palabras clave SEO",
};
const display = (value: Value) => typeof value === "string" ? value || "Sin completar" : JSON.stringify(value, null, 2);
export function CommercialBulkReview({ids,csrf,disabled,onOpen}:{
  ids: Set<string>; csrf:string; disabled:boolean; onOpen:(id:string)=>void;
}) {
  const [data,setData] = useState<Preview>();
  const [choices,setChoices] = useState<Record<string,Partial<Record<Field,Choice>>>>({});
  const [confirmed,setConfirmed] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [message,setMessage] = useState("");
  const selection = [...ids].sort().join(",");
  useEffect(()=>{setData(undefined);setChoices({});setConfirmed(false);setMessage("");},[selection]);
  async function preview() {
    setBusy(true);setError("");setMessage("");setConfirmed(false);setChoices({});
    try {
      const response = await request("/api/ecomm-app/workspace/commercial-review/preview",{
        method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({ecomm_ids:[...ids]})
      });
      const value = await response.json() as Preview;
      if(!value || value.schema_version!=="kiki-commercial-review-v1" || value.internal_only!==true || value.external_writes_enabled!==false || !/^[a-f0-9]{64}$/.test(value.fingerprint) || value.total!==ids.size || !Array.isArray(value.items) || value.items.length!==ids.size || new Set(value.items.map(r=>r.ecomm_id)).size!==ids.size || value.items.some(r=>!validVariantId(r.ecomm_id)||!ids.has(r.ecomm_id)||!Array.isArray(r.evidence)||r.evidence.some(f=>f.state!=="APPROVED")||Object.keys(r.fields).some(f=>!fieldKeys.includes(f as Field)))) throw new Error("La comparación no corresponde a las variantes seleccionadas.");
      setData(value);
    } catch(e){setError((e as Error).message);} finally{setBusy(false);}
  }
  function choose(id:string, field:Field, decision:string, value:Value){
    setConfirmed(false);
    setChoices(prev=>{
      const row={...prev[id]};
      if(decision)row[field]={decision:decision as Choice["decision"],value};else delete row[field];
      return {...prev,[id]:row};
    });
  }
  const selected = Object.entries(choices).filter(([,fields])=>Object.keys(fields).length);
  const accepted = selected.reduce((n,[,fields])=>n+Object.values(fields).filter(v=>v?.decision==="ACCEPTED").length,0);
  async function save(){
    if(!data||!confirmed||!selected.length||busy||disabled)return;
    setBusy(true);setError("");setMessage("");
    try{
      const response=await request("/api/ecomm-app/workspace/commercial-review/apply",{
        method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({
          ecomm_ids:data.items.map(r=>r.ecomm_id),expected_fingerprint:data.fingerprint,confirm:true,
          items:selected.map(([id,decisions])=>{
            const row=data.items.find(r=>r.ecomm_id===id)!;
            return {ecomm_id:id,draft_id:row.draft_id,expected_revision:row.revision,expected_workspace_version:row.workspace_version,decisions};
          }),
        })
      });
      const result=await response.json() as {internal_only:boolean;external_writes_enabled:boolean;total:number;items:{ecomm_id:string;state:string;workspace_version:number}[]};
      if(result.internal_only!==true||result.external_writes_enabled!==false||result.total!==selected.length||!Array.isArray(result.items)||result.items.some(r=>!choices[r.ecomm_id]||!["SAVED_DRAFT","REJECTED"].includes(r.state)))throw new Error("El resultado no acredita el guardado interno de la selección.");
      setMessage(`${result.total} variantes revisadas. ${result.items.filter(r=>r.state==="SAVED_DRAFT").length} borradores guardados. No se publicaron productos.`);
      setData(undefined);setChoices({});setConfirmed(false);
    }catch(e){setError((e as Error).message);setConfirmed(false);}finally{setBusy(false);}
  }
  return <details className="i-source" aria-label="Revisión comercial por lotes">
    <summary>Revisar y guardar propuestas · hasta 20 variantes</summary>
    <p>Compará valores y citas. Elegí los campos de cada variante; solo los aceptados se guardarán como borrador. Se conserva el contenido que no selecciones. Preparar propuestas se realiza desde la cola existente.</p>
    <button type="button" disabled={disabled||busy||!ids.size||ids.size>20} onClick={()=>void preview()}>Comparar propuestas de {ids.size} variantes</button>
    {busy&&<p role="status">Comprobando versiones y respaldos…</p>}
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {data&&<section aria-label="Comparación comercial por variantes">
      <p>{data.total} variantes · {data.items.filter(r=>r.state==="REVIEW_REQUIRED").length} con propuestas revisables · {data.items.filter(r=>r.state==="BLOCKED").length} bloqueadas.</p>
      {data.items.map(row=><details key={row.ecomm_id} data-testid={`commercial-review-${row.ecomm_id}`}>
        <summary>{row.name} · {row.presentation} · Ecomm {row.ecomm_id} · SKU {row.sku} · {row.state==="BLOCKED"?"Bloqueado":"Por revisar"}</summary>
        {row.reasons.map(reason=><p key={reason}>{reason}</p>)}
        <button type="button" disabled={busy} onClick={()=>onOpen(row.ecomm_id)}>Abrir ficha y evidencias</button>
        {row.state!=="BLOCKED"&&<div className="b-scroll"><table><thead><tr><th>Campo</th><th>Actual</th><th>Propuesta y respaldo</th><th>Decisión</th></tr></thead><tbody>
          {Object.entries(row.fields).map(([key,value])=>{
            const field=key as Field, proposal=value!, choice=choices[row.ecomm_id]?.[field];
            return <tr key={field}><th>{labels[field]||field}</th><td><pre>{display(proposal.current)}</pre></td><td>
              <pre>{display(proposal.value)}</pre><details><summary>Ver {proposal.evidence_ids.length} citas</summary>
                {proposal.evidence_ids.map(id=>{const fact=row.evidence.find(f=>f.id===id);return <p key={id}>{fact?`${fact.document_id} · ${fact.location}: «${fact.quote}»`:`Cita ${id} no disponible; no aprobar.`}</p>;})}
              </details>
              {choice?.decision==="ACCEPTED"&&typeof choice.value==="string"&&<label>Editar {labels[field]||field}<textarea aria-label={`Editar ${field} ${row.ecomm_id}`} value={choice.value} disabled={busy||disabled} onChange={e=>choose(row.ecomm_id,field,"ACCEPTED",e.target.value)}/><small>Solo quitar o reordenar frases documentadas; agregar datos requiere evidencia.</small></label>}
            </td><td><select aria-label={`Decisión ${field} ${row.ecomm_id}`} disabled={busy||disabled} value={choice?.decision||""} onChange={e=>choose(row.ecomm_id,field,e.target.value,proposal.value)}><option value="">Sin cambio</option><option value="ACCEPTED">Aceptar para borrador</option><option value="REJECTED">Rechazar propuesta</option></select></td></tr>;
          })}
        </tbody></table></div>}
      </details>)}
      <p>{selected.length} variantes con decisiones · {accepted} campos aceptados.</p>
      <label><input type="checkbox" checked={confirmed} disabled={busy||disabled||!selected.length} onChange={e=>setConfirmed(e.target.checked)}/>Revisé los valores y sus citas. Confirmo estas decisiones y el guardado exclusivo como borrador interno.</label>
      <button type="button" disabled={busy||disabled||!confirmed||!selected.length} onClick={()=>void save()}>Guardar selección revisada como borrador</button>
    </section>}
  </details>;
}
