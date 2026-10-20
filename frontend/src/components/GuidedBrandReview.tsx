import {useEffect,useMemo,useState} from 'react';
import type {EnrichmentReviewItem} from '../types/catalog';

type Props={
  items:EnrichmentReviewItem[];
  busy:boolean;
  onVerify:(item:EnrichmentReviewItem)=>void;
  onKeepCandidate:(item:EnrichmentReviewItem)=>Promise<void>;
};

/** Session-only triage. No commercial data changes without an explicit action. */
export function GuidedBrandReview({items,busy,onVerify,onKeepCandidate}:Props){
  const [deferred,setDeferred]=useState<Set<string>>(()=>new Set());
  const [cursor,setCursor]=useState(0);
  const remaining=useMemo(()=>items.filter(item=>!deferred.has(item.product_key)),[items,deferred]);
  const index=Math.min(cursor,Math.max(remaining.length-1,0));
  const current=remaining[index];
  const total=items.length;
  const hasDeferred=items.some(item=>deferred.has(item.product_key));

  useEffect(()=>setCursor(previous=>Math.min(previous,Math.max(remaining.length-1,0))),[remaining.length]);
  if(!items.length)return <div className="kiki-brand-guide-empty">
    <strong>No hay marcas candidatas pendientes con evidencia interna.</strong>
    <p>Podés revisar los casos sin sugerencia en la sección de datos centrales.</p>
  </div>;

  return <section className="kiki-brand-guide" aria-label="Revisión guiada de marcas">
    <div className="kiki-brand-guide-top">
      <div><p className="eyebrow">REVISIÓN GUIADA · UNA POR VEZ</p>
        <h4>{remaining.length>0?`Candidata ${index+1} de ${remaining.length} disponibles`:'Terminaste los casos visibles en esta sesión'}</h4>
      </div>
      <span className="kiki-brand-guide-count">{total} propuestas en el filtro</span>
    </div>
    {current?<div className="kiki-brand-guide-card">
      <div className="kiki-brand-guide-name">
        <small>PRODUCTO ECOMM-APP</small>
        <strong>{current.product.name||'Producto sin nombre'}</strong>
        <span>SKU {current.product.sku_variant||current.product.sku_effective||current.product.sku||'—'}</span>
      </div>
      <div className="kiki-brand-evidence">
        <small>LO QUE KIKI ENCONTRÓ EN EL CATÁLOGO</small>
        <strong>Marca candidata: {current.internal_evidence.brand_candidate}</strong>
        <p>{current.internal_evidence.reason}</p>
        <div className="kiki-brand-evidence-tags">
          <span>Confianza de coincidencia: {current.internal_evidence.confidence==='HIGH'?'alta':current.internal_evidence.confidence==='MEDIUM'?'media':'no definida'}</span>
          <span>Origen: catálogo interno</span>
          {current.internal_evidence.related_sku&&<span>SKU relacionado: {current.internal_evidence.related_sku}</span>}
        </div>
      </div>
      <div className="kiki-brand-guide-warning">
        <strong>Una coincidencia no verifica la marca.</strong> Para dejar el dato validado, necesitás comprobarlo con una fuente verificable y revisar la presentación exacta.
      </div>
      <div className="kiki-brand-guide-actions">
        <button type="button" disabled={busy} onClick={()=>onVerify(current)}>Verificar con fuente →</button>
        <button type="button" className="secondary" disabled={busy} onClick={()=>void onKeepCandidate(current)}>Guardar como candidata</button>
        <button type="button" className="secondary" disabled={busy} onClick={()=>{setDeferred(old=>new Set(old).add(current.product_key));setCursor(0)}}>Posponer</button>
      </div>
      <div className="kiki-brand-guide-navigation">
        <button type="button" className="secondary" disabled={busy||index===0} onClick={()=>setCursor(previous=>Math.max(0,previous-1))}>← Anterior</button>
        <span>{index+1} / {remaining.length}</span>
        <button type="button" className="secondary" disabled={busy||index>=remaining.length-1} onClick={()=>setCursor(previous=>Math.min(remaining.length-1,previous+1))}>Siguiente →</button>
      </div>
      <small className="kiki-brand-guide-foot">«Guardar como candidata» registra solo una propuesta interna, no una marca verificada ni una publicación. «Posponer» no guarda una decisión.</small>
    </div>:<div className="kiki-brand-guide-empty">
      <strong>No quedan candidatas visibles en esta sesión.</strong>
      <p>Los casos pospuestos siguen pendientes en KIKI. Podés volver a mostrarlos cuando quieras.</p>
    </div>}
    {hasDeferred&&<button type="button" className="secondary kiki-brand-restore" onClick={()=>{setDeferred(new Set());setCursor(0)}}>Volver a mostrar los casos pospuestos</button>}
  </section>;
}
