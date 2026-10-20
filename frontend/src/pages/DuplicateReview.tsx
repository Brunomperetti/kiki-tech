import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {DuplicateReviewDecision, DuplicateReviewGroup, DuplicateReviewQueue} from '../types/duplicate-review';
import '../review.css';
import '../duplicate-review.css';

function decisionLabel(value:DuplicateReviewDecision){
  if(value==='DUPLICATE_CONFIRMED')return 'Duplicado confirmado';
  if(value==='DISTINCT_PRODUCTS')return 'Productos distintos';
  if(value==='VARIANTS')return 'Variantes';
  return 'Pendiente';
}

function dateLabel(value?:string|null){
  if(!value)return '';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?value:date.toLocaleString('es-AR');
}

export function DuplicateReview(){
  const [queue,setQueue]=useState<DuplicateReviewQueue|null>(null);
  const [search,setSearch]=useState('');
  const [decisionFilter,setDecisionFilter]=useState<DuplicateReviewDecision|''>('');
  const [notes,setNotes]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState('');
  const [message,setMessage]=useState('');
  const [success,setSuccess]=useState('');
  const [selectedGroups,setSelectedGroups]=useState<Set<string>>(()=>new Set());
  const [bulkNote,setBulkNote]=useState('');
  const [bulkBusy,setBulkBusy]=useState(false);

  async function load(){
    try{
      const data=await api.duplicateReviewQueue();
      setQueue(data);
      setSelectedGroups(previous=>new Set([...previous].filter(key=>data.items.some(group=>group.group_key===key&&group.review_decision==='PENDING'))));
      setNotes(current=>{
        const next={...current};
        for(const item of data.items){if(next[item.group_key]===undefined)next[item.group_key]=item.note||''}
        return next;
      });
      setMessage('');
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo cargar la revisión de duplicados.');
    }
  }

  useEffect(()=>{void load()},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (queue?.items||[]).filter(group=>{
      if(decisionFilter&&group.review_decision!==decisionFilter)return false;
      if(!term)return true;
      return [
        ...group.shared_identifiers,
        ...group.products.flatMap(item=>[
          item.product.sku,
          item.product.ean,
          item.product.name,
          item.listing.external_id,
          item.listing.sku,
          item.listing.title,
          ...(item.matched_listing_ids||[]),
        ]),
      ].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[queue,search,decisionFilter]);

  async function decide(group:DuplicateReviewGroup,decision:DuplicateReviewDecision){
    setBusy(group.group_key);
    setMessage('');
    setSuccess('');
    try{
      await api.saveDuplicateReviewDecision(group.group_key,decision,notes[group.group_key]);
      setSuccess(
        decision==='DUPLICATE_CONFIRMED'
          ?'Duplicado confirmado. Seguirá bloqueado hasta corregir el catálogo de origen.'
          :decision==='DISTINCT_PRODUCTS'
          ?'Marcados como productos distintos. Ya no se bloquearán por este conflicto.'
          :decision==='VARIANTS'
          ?'Marcados como variantes relacionadas. Ya no se bloquearán por este conflicto.'
          :'Grupo devuelto a pendiente.'
      );
      await load();
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo guardar la decisión.');
    }finally{
      setBusy('');
    }
  }

  async function saveSelectedVariants(){
    if(!queue||bulkBusy||selectedGroups.size===0)return;
    const keys=Array.from(selectedGroups);
    const pending=queue.items.filter(item=>keys.includes(item.group_key)&&item.review_decision==='PENDING');
    if(pending.length!==keys.length){
      setMessage('La selección cambió. Actualizá los grupos y volvé a revisar.');return;
    }
    if(bulkNote.trim().length<15){
      setMessage('Explicá qué verificaste para todos los grupos seleccionados (mínimo 15 caracteres).');return;
    }
    const summary=pending.map(item=>item.products.map(p=>p.product.name||'Sin nombre').slice(0,2).join(' / ')).join('\n• ');
    if(!window.confirm(
      `Confirmás que revisaste individualmente estos ${keys.length} grupos y que TODOS son variantes legítimas del mismo producto base?\n\n• ${summary}\n\nSe guardará una decisión interna con historial, sin modificar Ecomm-App ni Mercado Libre.`
    ))return;
    setBulkBusy(true);setMessage('');setSuccess('');
    try{
      const result=await api.saveDuplicateVariantsBatch(keys,queue.reconciliation_run_id,bulkNote.trim());
      setSelectedGroups(new Set());setBulkNote('');
      await load();
      setSuccess(`Se guardaron ${result.updated} grupos como variantes en KIKI con historial. No se modificaron los canales.`);
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo guardar el lote de variantes.');
    }finally{setBulkBusy(false)}
  }

  function toggleSelected(key:string){
    setSelectedGroups(previous=>{
      const next=new Set(previous);
      if(next.has(key))next.delete(key);else next.add(key);
      return next;
    });
  }

  if(message&&!queue)return <><header><div><p className="eyebrow">CONTROL HUMANO</p><h1>Revisión de duplicados Ecomm</h1></div></header><div className="notice warning">{message}</div></>;
  if(!queue)return <div className="auth-loading">Preparando revisión de duplicados…</div>;

  const s=queue.summary;
  return <>
    <header><div><p className="eyebrow">CONTROL HUMANO</p><h1>Revisión de duplicados Ecomm</h1><p>Resolvé grupos donde productos Ecomm distintos comparten uno o más identificadores.</p><Link className="secondary-link kiki-duplicate-back" to="/work/details?focus=ml">← Volver a las tareas de Mercado Libre</Link></div></header>
    {message&&<div className="notice warning">{message}</div>}
    {success&&<div className="notice success">{success}</div>}
    <div className="notice warning"><strong>No modifica Ecomm-App ni Mercado Libre.</strong> La decisión queda guardada en KIKI Tech. Un duplicado confirmado sigue bloqueado; productos distintos o variantes pueden continuar con los controles normales.</div>

    <section className="review-summary duplicate-summary">
      <article><span>Grupos en revisión</span><strong>{s.groups_total.toLocaleString('es-AR')}</strong></article>
      <article><span>Productos afectados</span><strong>{s.products_affected.toLocaleString('es-AR')}</strong></article>
      <article><span>Pendientes</span><strong>{s.PENDING.toLocaleString('es-AR')}</strong></article>
      <article><span>Duplicados confirmados</span><strong>{s.DUPLICATE_CONFIRMED.toLocaleString('es-AR')}</strong></article>
      <article><span>Productos distintos</span><strong>{s.DISTINCT_PRODUCTS.toLocaleString('es-AR')}</strong></article>
      <article><span>Variantes</span><strong>{s.VARIANTS.toLocaleString('es-AR')}</strong></article>
    </section>

    <section className="panel">
      <div className="kiki-duplicate-instructions"><strong>Primero revisá cada grupo.</strong><p>Un SKU compartido puede representar variantes legítimas, productos diferentes o un duplicado erróneo. Para un lote, marcá solamente los grupos que verificaste: una presentación pack, distinta cantidad o sabor puede exigir otra decisión.</p></div>
      <div className="review-filters">
        <input placeholder="Buscar SKU, EAN, producto o publicación ML" value={search} onChange={event=>setSearch(event.target.value)}/>
        <select value={decisionFilter} onChange={event=>setDecisionFilter(event.target.value as DuplicateReviewDecision|'')}>
          <option value="">Todos los estados</option>
          <option value="PENDING">Pendientes</option>
          <option value="DUPLICATE_CONFIRMED">Duplicado confirmado</option>
          <option value="DISTINCT_PRODUCTS">Productos distintos</option>
          <option value="VARIANTS">Variantes</option>
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> de {s.groups_total.toLocaleString('es-AR')} grupos</p>
      <section className="kiki-duplicate-batch" aria-label="Clasificación grupal supervisada">
        <div className="kiki-duplicate-batch-head"><div><strong>Resolver varios grupos como variantes</strong><p>Seleccioná cada grupo pendiente después de comprobar que sus productos son variantes legítimas. No se seleccionan automáticamente.</p></div><span>{selectedGroups.size} seleccionados</span></div>
        <label>Justificación compartida (obligatoria para todos)
          <textarea rows={2} value={bulkNote} onChange={e=>setBulkNote(e.target.value)} placeholder="Ejemplo: confirmé en el catálogo del fabricante que cada grupo corresponde a distintas presentaciones del mismo producto."/>
        </label>
        <div className="kiki-duplicate-batch-actions"><button type="button" disabled={bulkBusy||selectedGroups.size===0||bulkNote.trim().length<15} onClick={()=>void saveSelectedVariants()}>{bulkBusy?'Guardando…':`Confirmar ${selectedGroups.size} grupos como variantes`}</button><button type="button" className="secondary" disabled={bulkBusy||selectedGroups.size===0} onClick={()=>setSelectedGroups(new Set())}>Limpiar selección</button></div>
        <small>El guardado se realiza como una única operación: si algún grupo cambió o ya fue decidido, se rechaza el lote completo. No vincula ni publica productos.</small>
      </section>

      {!items.length&&<div className="review-empty">No hay grupos para el filtro seleccionado.</div>}
      <div className="reconciliation-review-list">{items.map(group=>{
        const isBusy=busy===group.group_key;
        return <article className="reconciliation-review-item" key={group.group_key}>
          <div className="reconciliation-review-head">
            <div>
              {group.review_decision==='PENDING'&&<label className="kiki-duplicate-select"><input type="checkbox" checked={selectedGroups.has(group.group_key)} onChange={()=>toggleSelected(group.group_key)} disabled={bulkBusy||busy!==''}/> Seleccionar este grupo para clasificarlo como variantes</label>}
              <span className={`review-decision ${group.review_decision}`}>{decisionLabel(group.review_decision)}</span>
              <h2>{group.products.length} productos relacionados</h2>
              <div className="duplicate-identifiers">{group.shared_identifiers.map(identifier=><span className="duplicate-identifier" key={identifier}>Identificador compartido: {identifier}</span>)}</div>
            </div>
            <div className="reconciliation-review-meta">{group.history_count>0?`${group.history_count} movimiento${group.history_count===1?'':'s'}`:'Sin decisiones previas'}</div>
          </div>

          <div className="duplicate-group-products">{group.products.map(item=><div className="review-side" key={item.product_key}>
            <h3>Ecomm-App</h3>
            <strong className="duplicate-product-title">{item.product.name||'Producto sin nombre'}</strong>
            <p>SKU principal: {item.product.sku||'—'}</p>
            <p>Aliases SKU: {item.product.sku_aliases?.length?item.product.sku_aliases.join(' · '):'—'}</p>
            <p>EAN/GTIN: {item.product.ean||'—'}</p>
            <p>Marca: {item.product.brand||'—'}</p>
            <p>Stock: {item.product.stock??'—'} · Precio: {item.product.price!=null?Number(item.product.price).toLocaleString('es-AR',{style:'currency',currency:'ARS'}):'—'}</p>
            <div className="duplicate-product-meta">
              <p>ML asociado: {item.listing.external_id||item.matched_listing_ids?.[0]||'Sin asociar'}</p>
              <p>Publicaciones ML encontradas: {item.matched_listing_count}</p>
              {item.matched_listing_ids.length>1&&<p>IDs ML: {item.matched_listing_ids.join(' · ')}</p>}
            </div>
          </div>)}</div>

          <div className="duplicate-explanation"><strong>Qué hay que decidir:</strong> si estas fichas representan el mismo producto duplicado, productos realmente distintos o variantes legítimas del mismo producto base.</div>
          <textarea className="review-note" placeholder="Nota opcional: por ejemplo, mismo EAN y presentación / sabores diferentes / SKU mal asignado" value={notes[group.group_key]||''} onChange={event=>setNotes(current=>({...current,[group.group_key]:event.target.value}))}/>

          <div className="review-actions duplicate-actions">
            {group.review_decision!=='DUPLICATE_CONFIRMED'&&<button className="danger" disabled={isBusy} onClick={()=>void decide(group,'DUPLICATE_CONFIRMED')}>Duplicado confirmado</button>}
            {group.review_decision!=='DISTINCT_PRODUCTS'&&<button disabled={isBusy} onClick={()=>void decide(group,'DISTINCT_PRODUCTS')}>Son productos distintos</button>}
            {group.review_decision!=='VARIANTS'&&<button className="variant" disabled={isBusy} onClick={()=>void decide(group,'VARIANTS')}>Son variantes</button>}
            {group.review_decision!=='PENDING'&&<button className="secondary" disabled={isBusy} onClick={()=>void decide(group,'PENDING')}>Volver a pendiente</button>}
          </div>

          {group.history_count>0&&<details className="review-history"><summary>Ver historial ({group.history_count})</summary><ul>{group.history.slice().reverse().map((entry,index)=><li key={`${entry.at}-${index}`}><strong>{decisionLabel(entry.decision)}</strong> · {dateLabel(entry.at)}{entry.note?` · ${entry.note}`:''}</li>)}</ul></details>}
        </article>
      })}</div>
      <p className="evidence-note">{queue.policy.description}</p>
    </section>
  </>;
}
