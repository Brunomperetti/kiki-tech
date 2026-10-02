import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {ReconciliationReviewDecision, ReconciliationReviewItem, ReconciliationReviewQueue} from '../types/reconciliation-review';
import '../review.css';

function decisionLabel(value:ReconciliationReviewDecision){
  if(value==='CONFIRMED_MATCH')return 'Coincidencia confirmada';
  if(value==='NOT_MATCH')return 'No coincide';
  return 'Pendiente';
}

function dateLabel(value?:string|null){
  if(!value)return '';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?value:date.toLocaleString('es-AR');
}

export function Review(){
  const [queue,setQueue]=useState<ReconciliationReviewQueue|null>(null);
  const [search,setSearch]=useState('');
  const [decisionFilter,setDecisionFilter]=useState<ReconciliationReviewDecision|''>('');
  const [notes,setNotes]=useState<Record<string,string>>({});
  const [busy,setBusy]=useState('');
  const [message,setMessage]=useState('');
  const [success,setSuccess]=useState('');

  async function load(){
    try{
      const data=await api.reconciliationReviewQueue();
      setQueue(data);
      setNotes(current=>{
        const next={...current};
        for(const item of data.items){if(next[item.product_key]===undefined)next[item.product_key]=item.note||''}
        return next;
      });
      setMessage('');
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo cargar la revisión de conciliación.');
    }
  }

  useEffect(()=>{void load()},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (queue?.items||[]).filter(item=>{
      if(decisionFilter&&item.review_decision!==decisionFilter)return false;
      if(!term)return true;
      return [
        item.product.sku,
        item.product.ean,
        item.product.name,
        item.listing.external_id,
        item.listing.sku,
        item.listing.title,
        ...(item.matched_listing_ids||[]),
      ].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[queue,search,decisionFilter]);

  async function decide(item:ReconciliationReviewItem,decision:ReconciliationReviewDecision){
    setBusy(item.product_key);
    setMessage('');
    setSuccess('');
    try{
      await api.saveReconciliationReviewDecision(item.product_key,decision,notes[item.product_key]);
      setSuccess(
        decision==='CONFIRMED_MATCH'
          ?'Coincidencia confirmada. Preparación ML la tratará como ya publicada.'
          :decision==='NOT_MATCH'
          ?'Coincidencia descartada. Preparación ML la tratará como candidata y aplicará sus controles.'
          :'Caso devuelto a pendiente.'
      );
      await load();
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo guardar la decisión.');
    }finally{
      setBusy('');
    }
  }

  if(message&&!queue)return <><header><div><p className="eyebrow">CONTROL HUMANO</p><h1>Revisión de coincidencias</h1></div></header><div className="notice warning">{message}</div></>;
  if(!queue)return <div className="auth-loading">Preparando revisión…</div>;

  const s=queue.summary;
  return <>
    <header><div><p className="eyebrow">CONTROL HUMANO</p><h1>Revisión de coincidencias</h1><p>Resolvé los casos donde Ecomm y Mercado Libre se parecen, pero la app no puede asociarlos con certeza.</p></div></header>
    {message&&<div className="notice warning">{message}</div>}
    {success&&<div className="notice success">{success}</div>}
    <div className="notice warning"><strong>No modifica Ecomm-App ni Mercado Libre.</strong> La decisión queda guardada dentro de KIKI Tech y se usa en Preparación ML. Podés revertirla.</div>

    <section className="review-summary">
      <article><span>Total en revisión</span><strong>{s.total.toLocaleString('es-AR')}</strong></article>
      <article><span>Pendientes</span><strong>{s.PENDING.toLocaleString('es-AR')}</strong></article>
      <article><span>Coincidencias confirmadas</span><strong>{s.CONFIRMED_MATCH.toLocaleString('es-AR')}</strong></article>
      <article><span>No coinciden</span><strong>{s.NOT_MATCH.toLocaleString('es-AR')}</strong></article>
    </section>

    <section className="panel">
      <div className="review-filters">
        <input placeholder="Buscar SKU, EAN, producto o publicación ML" value={search} onChange={event=>setSearch(event.target.value)}/>
        <select value={decisionFilter} onChange={event=>setDecisionFilter(event.target.value as ReconciliationReviewDecision|'')}>
          <option value="">Todos los estados</option>
          <option value="PENDING">Pendientes</option>
          <option value="CONFIRMED_MATCH">Coincidencia confirmada</option>
          <option value="NOT_MATCH">No coincide</option>
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> de {s.total.toLocaleString('es-AR')} casos</p>

      {!items.length&&<div className="review-empty">No hay casos para el filtro seleccionado.</div>}
      <div className="reconciliation-review-list">{items.map(item=>{
        const isBusy=busy===item.product_key;
        return <article className="reconciliation-review-item" key={item.product_key}>
          <div className="reconciliation-review-head">
            <div>
              <span className={`review-decision ${item.review_decision}`}>{decisionLabel(item.review_decision)}</span>
              <h2>{item.product.name||'Producto sin nombre'}</h2>
              <p className="reconciliation-review-meta">SKU {item.product.sku||'—'} · EAN {item.product.ean||'—'} · Stock {item.product.stock??'—'}</p>
            </div>
            <div className="reconciliation-review-meta">{item.history_count>0?`${item.history_count} movimiento${item.history_count===1?'':'s'}`:'Sin decisiones previas'}</div>
          </div>

          <div className="review-comparison">
            <div className="review-side">
              <h3>Ecomm-App</h3>
              <strong>{item.product.name||'—'}</strong>
              <p>SKU: {item.product.sku||'—'}</p>
              <p>EAN/GTIN: {item.product.ean||'—'}</p>
              <p>Marca: {item.product.brand||'—'}</p>
            </div>
            <div className="review-side">
              <h3>Mercado Libre encontrado</h3>
              <strong>{item.listing.title||'Publicación sin título disponible'}</strong>
              <p>ID: {item.listing.external_id||item.matched_listing_ids?.[0]||'—'}</p>
              <p>SKU ML: {item.listing.sku||'—'}</p>
              <p>Publicaciones encontradas: {item.matched_listing_count}</p>
              {item.matched_listing_ids.length>1&&<p>IDs: {item.matched_listing_ids.join(' · ')}</p>}
            </div>
          </div>

          <div className="review-reason"><strong>Por qué llegó a revisión:</strong> {item.reason||'Coincidencia ambigua.'}</div>
          <textarea className="review-note" placeholder="Nota opcional para dejar registrado por qué tomaste la decisión" value={notes[item.product_key]||''} onChange={event=>setNotes(current=>({...current,[item.product_key]:event.target.value}))}/>

          <div className="review-actions">
            {item.review_decision!=='CONFIRMED_MATCH'&&<button disabled={isBusy} onClick={()=>void decide(item,'CONFIRMED_MATCH')}>Confirmar coincidencia</button>}
            {item.review_decision!=='NOT_MATCH'&&<button className="danger" disabled={isBusy} onClick={()=>void decide(item,'NOT_MATCH')}>No coincide</button>}
            {item.review_decision!=='PENDING'&&<button className="secondary" disabled={isBusy} onClick={()=>void decide(item,'PENDING')}>Volver a pendiente</button>}
          </div>

          {item.history_count>0&&<details className="review-history"><summary>Ver historial ({item.history_count})</summary><ul>{item.history.slice().reverse().map((entry,index)=><li key={`${entry.at}-${index}`}><strong>{decisionLabel(entry.decision)}</strong> · {dateLabel(entry.at)}{entry.note?` · ${entry.note}`:''}</li>)}</ul></details>}
        </article>
      })}</div>
      <p className="evidence-note">{queue.policy.description}</p>
    </section>
  </>;
}
