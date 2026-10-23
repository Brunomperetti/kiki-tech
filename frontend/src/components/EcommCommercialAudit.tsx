import {useState} from 'react';
import {api} from '../services/api';
import type {EcommCommercialAudit as Audit} from '../types/ecomm-app';

const caption=(status:string)=>({
  MISSING:'Campo vacío',
  PLACEHOLDER:'Marcador genérico',
  ZERO:'Valor cero',
  NEGATIVE:'Valor negativo',
  INVALID:'Valor no numérico',
}[status]||status);

export function EcommCommercialAudit(){
  const [audit,setAudit]=useState<Audit|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  async function inspect(){
    setBusy(true);setError('');
    try{setAudit(await api.ecommCommercialAudit())}
    catch(e){setError(e instanceof Error?e.message:'No se pudo auditar la información comercial.')}
    finally{setBusy(false)}
  }
  const c=audit?.counts;
  return <details className="kiki-ecomm-commercial-audit">
    <summary>Auditar marcas, precios y costos del Excel histórico</summary>
    <p>Antes de usar la API como fuente de stock necesitamos comprobar la calidad de los datos comerciales que seguirían viniendo del Excel. Esta revisión cruza solo registros identificados por un ID único en ambas fuentes.</p>
    <button type="button" disabled={busy} onClick={()=>void inspect()}>
      {busy?'Revisando campos…':audit?'Actualizar diagnóstico (solo lectura)':'Revisar cobertura comercial (solo lectura)'}
    </button>
    {error&&<p role="alert" className="kiki-ecomm-notice">{error}</p>}
    {c&&<section className="kiki-ecomm-commercial-results">
      <h4>Calidad de los campos históricos · {c.matched_ids} productos por ID</h4>
      <div className="kiki-ecomm-commercial-metrics">
        <div><strong>{c.brand_present}</strong><small>Marca informada en Excel</small></div>
        <div><strong>{c.brand_missing}</strong><small>Sin marca en Excel</small></div>
        <div><strong>{c.brand_placeholder}</strong><small>Marca con marcador genérico</small></div>
        <div><strong>{c.price_positive}</strong><small>Precio numérico mayor que 0</small></div>
        <div><strong>{c.cost_positive}</strong><small>Costo numérico mayor que 0</small></div>
        <div><strong>{c.ean_present}</strong><small>EAN informado (sin validar formato)</small></div>
      </div>
      <p><strong>Precios a revisar:</strong> {c.price_zero} en cero, {c.price_missing} vacíos, {c.price_negative} negativos y {c.price_invalid} no numéricos.</p>
      <p><strong>Costos a revisar:</strong> {c.cost_zero} en cero, {c.cost_missing} vacíos, {c.cost_negative} negativos y {c.cost_invalid} no numéricos.</p>
      <p><strong>EAN en blanco:</strong> {c.ean_blank}. <strong>Combos con marca histórica ausente o genérica:</strong> {c.combo_without_brand} de {c.combo_matched} combos identificados por ID.</p>
      <p className="kiki-ecomm-hint">{audit.note}</p>
      <details>
        <summary>Ver ejemplos de marcas sin informar ({Math.min(c.brand_missing+c.brand_placeholder,audit.sampling_limit)} mostrados como máximo)</summary>
        {audit.samples.without_brand.length===0?<p>No se encontraron casos en este conjunto.</p>:audit.samples.without_brand.map(row=><div className="kiki-ecomm-commercial-row" key={row.ecomm_id}>
          <strong>{row.name||'Sin título'} · ID {row.ecomm_id}</strong>
          <small>SKU histórico: {row.sku||'Sin SKU'} · SKU API: {row.api_sku||'Sin SKU'} · {caption(row.brand_status)} · Combo API: {row.is_combo===true?'Sí':row.is_combo===false?'No':'No informado'}</small>
        </div>)}
      </details>
      <details>
        <summary>Ver ejemplos de precios que necesitan revisión ({Math.min(c.price_zero+c.price_missing+c.price_negative+c.price_invalid,audit.sampling_limit)} máximo)</summary>
        {audit.samples.price_review.length===0?<p>No se encontraron casos en este conjunto.</p>:audit.samples.price_review.map(row=><div className="kiki-ecomm-commercial-row" key={row.ecomm_id}>
          <strong>{row.name||'Sin título'} · ID {row.ecomm_id}</strong>
          <small>SKU: {row.sku||'Sin SKU'} · {caption(row.status)} · Precio guardado: {row.value??'No informado'}</small>
        </div>)}
      </details>
      <details>
        <summary>Ver ejemplos de costos que necesitan revisión ({Math.min(c.cost_zero+c.cost_missing+c.cost_negative+c.cost_invalid,audit.sampling_limit)} máximo)</summary>
        {audit.samples.cost_review.length===0?<p>No se encontraron casos en este conjunto.</p>:audit.samples.cost_review.map(row=><div className="kiki-ecomm-commercial-row" key={row.ecomm_id}>
          <strong>{row.name||'Sin título'} · ID {row.ecomm_id}</strong>
          <small>SKU: {row.sku||'Sin SKU'} · {caption(row.status)} · Costo guardado: {row.value??'No informado'}</small>
        </div>)}
      </details>
      <small>Los ejemplos son una muestra acotada. No se corrigen marcas, precios, costos o EAN ni se publica nada en los canales.</small>
    </section>}
  </details>;
}
