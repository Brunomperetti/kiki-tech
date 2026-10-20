import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import type {ReadinessItem} from '../types/catalog';

type Issue='EAN_MISSING'|'BRAND_MISSING';
type Entry={key:string;item:ReadinessItem;hasBrandSuggestion:boolean;researchStarted:boolean};
type Props={
  issue:Issue;
  entries:Entry[];
  onResolve:(item:ReadinessItem)=>void;
  busy:boolean;
};

/** Only navigation happens here. All catalog decisions use the existing evidence workflow. */
export function GuidedCoreReview({issue,entries,onResolve,busy}:Props){
  const [postponed,setPostponed]=useState<Set<string>>(()=>new Set());
  const [position,setPosition]=useState(0);
  const remaining=useMemo(()=>entries.filter(entry=>!postponed.has(entry.key)),[entries,postponed]);
  const selectedIndex=Math.min(position,Math.max(0,remaining.length-1));
  const current=remaining[selectedIndex];
  const isBrand=issue==='BRAND_MISSING';

  useEffect(()=>setPosition(p=>Math.min(p,Math.max(remaining.length-1,0))),[remaining.length]);
  if(entries.length===0)return <div className="kiki-core-guide-empty">
    <strong>Sin casos pendientes en este control.</strong>
    <p>Podés pasar al otro tipo de dato o volver al centro de tareas.</p>
  </div>;

  return <section className="kiki-core-guide" aria-label="Resolver datos de a un producto">
    <header className="kiki-core-guide-header">
      <div>
        <p className="eyebrow">PASO A PASO · UN PRODUCTO A LA VEZ</p>
        <h3>{isBrand?'Revisar marca del producto':'Revisar EAN / GTIN'}</h3>
        <p>{remaining.length} pendientes visibles. Los que pospongas se ocultan únicamente durante esta sesión.</p>
      </div>
      <span className="kiki-core-guide-number">{current?`${selectedIndex+1} / ${remaining.length}`:'Sin casos visibles'}</span>
    </header>

    {current?<div className="kiki-core-guide-product" key={current.key}>
      <div>
        <small>PRODUCTO DE ECOMM-APP</small>
        <strong>{current.item.product.name||'Producto sin nombre'}</strong>
        <p>SKU {current.item.product.sku_variant||current.item.product.sku_effective||current.item.product.sku||'—'} · Stock {current.item.product.stock??'—'}</p>
      </div>
      <div className="kiki-core-guide-detail">
        <small>QUÉ DETECTÓ KIKI</small>
        <strong>{isBrand?'Falta confirmar una marca con fuente verificable':'Falta validar el código de la presentación exacta'}</strong>
        <p>{current.item.reasons.filter(Boolean).slice(0,2).join(' · ')||'El análisis requiere una verificación humana antes de continuar.'}</p>
        {isBrand&&current.hasBrandSuggestion&&<p className="kiki-core-guide-suggestion">Hay una marca candidata identificada en el catálogo. Podés revisarla en el asistente de marcas.</p>}
        {current.researchStarted&&<p className="kiki-core-guide-suggestion">Hay una investigación guardada para este producto: podés retomarla.</p>}
      </div>
      <div className="kiki-core-guide-caution">No inventamos códigos de barras, marcas ni certificaciones. La resolución exige una fuente confiable y no modifica automáticamente Mercado Libre ni Tiendanube.</div>
      <div className="kiki-core-guide-actions">
        <button type="button" disabled={busy} onClick={()=>onResolve(current.item)}>{current.researchStarted?'Continuar verificación':'Verificar con fuente'} →</button>
        {isBrand&&current.hasBrandSuggestion&&<Link className="secondary-link" to={`/work/details?focus=brands&q=${encodeURIComponent(current.item.product.sku_variant||current.item.product.sku_effective||current.item.product.sku||current.item.product.name||'')}`}>Ver marca candidata →</Link>}
        <button type="button" className="secondary" disabled={busy} onClick={()=>{setPostponed(set=>new Set(set).add(current.key));setPosition(0)}}>Posponer este caso</button>
      </div>
      <div className="kiki-core-guide-nav">
        <button type="button" className="secondary" disabled={busy||selectedIndex===0} onClick={()=>setPosition(p=>Math.max(0,p-1))}>← Anterior</button>
        <span>{selectedIndex+1} de {remaining.length}</span>
        <button type="button" className="secondary" disabled={busy||selectedIndex===remaining.length-1} onClick={()=>setPosition(p=>Math.min(remaining.length-1,p+1))}>Siguiente →</button>
      </div>
    </div>:<div className="kiki-core-guide-empty">
      <strong>Ya recorriste todos los casos visibles.</strong>
      <p>Los que pospusiste no fueron aprobados ni modificados. Podés volver a mostrarlos para continuar.</p>
    </div>}
    {postponed.size>0&&<div className="kiki-core-guide-foot">
      <span>{postponed.size} pospuestos solo en esta sesión</span>
      <button type="button" className="secondary" onClick={()=>{setPostponed(new Set());setPosition(0)}}>Volver a mostrarlos</button>
    </div>}
  </section>;
}
