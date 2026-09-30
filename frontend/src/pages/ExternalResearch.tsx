import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {
  ExternalResearchConfidence,
  ExternalResearchItem,
  ExternalResearchPayload,
  ExternalResearchQueue,
  ExternalResearchStatus,
} from '../types/catalog';
import '../external-research.css';

type Draft = {
  proposed_brand:string;
  proposed_ean:string;
  source_name:string;
  source_url:string;
  confidence:ExternalResearchConfidence|'';
  notes:string;
};

function emptyDraft(item:ExternalResearchItem):Draft{
  return {
    proposed_brand:item.proposed_brand||'',
    proposed_ean:item.proposed_ean||'',
    source_name:item.source_name||'',
    source_url:item.source_url||'',
    confidence:item.confidence||'',
    notes:item.notes||'',
  };
}

function statusLabel(status:ExternalResearchStatus){
  if(status==='READY_FOR_REVIEW')return 'Lista para revisar';
  if(status==='EVIDENCE_ACCEPTED')return 'Evidencia aceptada';
  if(status==='REJECTED')return 'Descartada';
  return 'Borrador';
}

function confidenceLabel(value:ExternalResearchConfidence|''|null|undefined){
  if(value==='HIGH')return 'Alta';
  if(value==='MEDIUM')return 'Media';
  if(value==='LOW')return 'Baja';
  return 'Sin definir';
}

export function ExternalResearch(){
  const [queue,setQueue]=useState<ExternalResearchQueue|null>(null);
  const [drafts,setDrafts]=useState<Record<string,Draft>>({});
  const [search,setSearch]=useState('');
  const [status,setStatus]=useState<ExternalResearchStatus|''>('');
  const [busy,setBusy]=useState('');
  const [message,setMessage]=useState('');
  const [success,setSuccess]=useState('');

  async function load(){
    try{
      const data=await api.externalResearchQueue();
      setQueue(data);
      setDrafts(current=>{
        const next={...current};
        for(const item of data.items){if(!next[item.product_key])next[item.product_key]=emptyDraft(item)}
        return next;
      });
      setMessage('');
    }catch(error){
      setMessage(error instanceof Error?error.message:'No pudimos cargar la investigación externa.');
    }
  }

  useEffect(()=>{void load()},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (queue?.items||[]).filter(item=>{
      if(status&&item.research_status!==status)return false;
      if(!term)return true;
      return [
        item.product.sku,
        item.product.name,
        item.internal_evidence.brand_candidate,
        item.proposed_brand,
        item.proposed_ean,
        item.source_name,
      ].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[queue,search,status]);

  function setField(productKey:string,field:keyof Draft,value:string){
    setDrafts(current=>({
      ...current,
      [productKey]:{...(current[productKey]||{proposed_brand:'',proposed_ean:'',source_name:'',source_url:'',confidence:'',notes:''}),[field]:value},
    }));
  }

  async function save(item:ExternalResearchItem,nextStatus:ExternalResearchStatus){
    const draft=drafts[item.product_key]||emptyDraft(item);
    setBusy(item.product_key);
    setMessage('');
    setSuccess('');
    try{
      const payload:ExternalResearchPayload={
        product_key:item.product_key,
        status:nextStatus,
        proposed_brand:draft.proposed_brand||undefined,
        proposed_ean:draft.proposed_ean||undefined,
        source_name:draft.source_name||undefined,
        source_url:draft.source_url||undefined,
        confidence:draft.confidence||undefined,
        notes:draft.notes||undefined,
      };
      await api.saveExternalResearch(payload);
      setSuccess(nextStatus==='EVIDENCE_ACCEPTED'?'Evidencia aceptada dentro de KIKI Tech. No se modificó ningún sistema externo.':'Investigación guardada.');
      await load();
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo guardar la investigación.');
    }finally{
      setBusy('');
    }
  }

  async function copyQuery(item:ExternalResearchItem){
    const brand=item.internal_evidence.brand_candidate||'';
    const query=[item.product.name,brand,'EAN GTIN marca fabricante presentación exacta'].filter(Boolean).join(' ');
    try{await navigator.clipboard.writeText(query);setSuccess('Consulta de investigación copiada.')}catch{setMessage('No se pudo copiar la consulta.')}
  }

  if(message&&!queue)return <><header><div><p className="eyebrow">INVESTIGACIÓN EXTERNA</p><h1>Fuentes y propuestas</h1></div></header><div className="notice warning">{message}</div></>;
  if(!queue)return <div className="auth-loading">Preparando investigación externa…</div>;
  const s=queue.summary;

  return <>
    <header><div><p className="eyebrow">MVP3.6 · INVESTIGACIÓN EXTERNA ASISTIDA</p><h1>Fuentes y propuestas verificables</h1><p>Documentá marca, EAN/GTIN y evidencia antes de convertir una pista en un dato utilizable.</p></div></header>
    {message&&<div className="notice warning">{message}</div>}
    {success&&<div className="notice success">{success}</div>}
    <div className="notice warning"><strong>No modifica Ecomm-App ni Mercado Libre.</strong> “Evidencia aceptada” significa que la fuente quedó validada dentro de KIKI Tech. La escritura externa seguirá requiriendo una etapa posterior de preview y confirmación.</div>

    <section className="cards external-cards">
      <article><span>En investigación</span><strong>{s.total.toLocaleString('es-AR')}</strong></article>
      <article><span>Borradores</span><strong>{s.DRAFT.toLocaleString('es-AR')}</strong></article>
      <article><span>Listas para revisar</span><strong>{s.READY_FOR_REVIEW.toLocaleString('es-AR')}</strong></article>
      <article><span>Evidencia aceptada</span><strong>{s.EVIDENCE_ACCEPTED.toLocaleString('es-AR')}</strong></article>
      <article><span>Descartadas</span><strong>{s.REJECTED.toLocaleString('es-AR')}</strong></article>
    </section>

    <section className="panel external-guide">
      <h2>Qué cuenta como evidencia</h2>
      <p>Priorizá fabricante oficial, GS1 o ficha oficial del producto. También podés registrar un distribuidor confiable cuando la presentación coincida exactamente. No uses un EAN de otra presentación, de una unidad para un pack ni una marca inferida solo por parecido.</p>
    </section>

    <section className="panel">
      <div className="filters external-filters">
        <input placeholder="Buscar SKU, producto, marca, EAN o fuente" value={search} onChange={event=>setSearch(event.target.value)}/>
        <select value={status} onChange={event=>setStatus(event.target.value as ExternalResearchStatus|'')}>
          <option value="">Todos los estados</option>
          <option value="DRAFT">Borradores</option>
          <option value="READY_FOR_REVIEW">Listas para revisar</option>
          <option value="EVIDENCE_ACCEPTED">Evidencia aceptada</option>
          <option value="REJECTED">Descartadas</option>
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> de {s.total.toLocaleString('es-AR')} productos en investigación</p>

      {s.total===0&&<div className="external-empty"><strong>No hay productos enviados a investigación externa.</strong><p>Desde Enriquecimiento elegí un producto y tocá “Investigar afuera”. Va a aparecer acá automáticamente.</p></div>}

      <div className="external-list">{items.map(item=>{
        const draft=drafts[item.product_key]||emptyDraft(item);
        const isBusy=busy===item.product_key;
        const ev=item.internal_evidence;
        return <article className="external-item" key={item.product_key}>
          <div className="external-item-head">
            <div><span className={`external-status ${item.research_status}`}>{statusLabel(item.research_status)}</span><h2>{item.product.name||'Producto sin nombre'}</h2><p>SKU {item.product.sku||'—'} · Stock {item.product.stock??'—'} · {item.nature_label||'Sin tipo'}</p></div>
            <div className="external-head-actions"><button className="secondary" onClick={()=>void copyQuery(item)}>Copiar búsqueda sugerida</button>{item.history_count>0&&<small>{item.history_count} movimiento{item.history_count===1?'':'s'}</small>}</div>
          </div>

          <div className="external-evidence"><strong>Pista interna</strong><span>{ev.brand_candidate||ev.candidate_brands.join(' · ')||'Sin marca candidata'}</span><small>{ev.reason}</small>{ev.related_name&&<small>Relacionado: {ev.related_name}{ev.related_ean?` · EAN ref. ${ev.related_ean}`:''}</small>}</div>

          <div className="external-form">
            <label>Marca propuesta<input value={draft.proposed_brand} placeholder={ev.brand_candidate||'Ej. Natufarma'} onChange={e=>setField(item.product_key,'proposed_brand',e.target.value)}/></label>
            <label>EAN / GTIN propuesto<input value={draft.proposed_ean} inputMode="numeric" placeholder="Solo dígitos" onChange={e=>setField(item.product_key,'proposed_ean',e.target.value)}/></label>
            <label>Fuente<input value={draft.source_name} placeholder="Fabricante, GS1, distribuidor…" onChange={e=>setField(item.product_key,'source_name',e.target.value)}/></label>
            <label>URL de evidencia<input value={draft.source_url} type="url" placeholder="https://…" onChange={e=>setField(item.product_key,'source_url',e.target.value)}/></label>
            <label>Confianza<select value={draft.confidence} onChange={e=>setField(item.product_key,'confidence',e.target.value)}><option value="">Sin definir</option><option value="HIGH">Alta</option><option value="MEDIUM">Media</option><option value="LOW">Baja</option></select></label>
            <label className="external-notes">Observaciones<textarea value={draft.notes} placeholder="Por qué coincide la presentación, advertencias, pack/unidad, etc." onChange={e=>setField(item.product_key,'notes',e.target.value)}/></label>
          </div>

          {item.source_url&&<p className="external-saved-source">Fuente guardada: <a href={item.source_url} target="_blank" rel="noreferrer">{item.source_name||item.source_url}</a> · Confianza {confidenceLabel(item.confidence)}</p>}

          <div className="external-actions">
            <button className="secondary" disabled={isBusy} onClick={()=>void save(item,'DRAFT')}>Guardar borrador</button>
            <button disabled={isBusy} onClick={()=>void save(item,'READY_FOR_REVIEW')}>Lista para revisar</button>
            <button className="accept" disabled={isBusy} onClick={()=>void save(item,'EVIDENCE_ACCEPTED')}>Aceptar evidencia</button>
            <button className="ghost danger" disabled={isBusy} onClick={()=>void save(item,'REJECTED')}>Descartar investigación</button>
          </div>
        </article>;
      })}</div>
      <p className="evidence-note">{queue.policy.description}</p>
    </section>
  </>;
}
