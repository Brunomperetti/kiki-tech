import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {
  FinalPublicationQueueItem,
  FinalPublicationQueueReport,
  FinalPublicationQueueStatus,
  PrepublicationCheckStatus,
  PrepublicationReport,
} from '../types/catalog';
import '../prepublication.css';

function checkLabel(status:PrepublicationCheckStatus){
  if(status==='PASSED')return 'OK';
  if(status==='WAITING_IMAGE_DATA')return 'Faltan imágenes';
  if(status==='WAITING_ML_CONNECTION')return 'Esperando conexión ML';
  if(status==='READY_TO_VALIDATE')return 'Listo para validar';
  return 'Bloqueado';
}

function finalStatusLabel(status:FinalPublicationQueueStatus){
  if(status==='READY_FOR_FINAL_REVIEW')return 'Listo para aprobación final';
  if(status==='APPROVED_FOR_PUBLICATION')return 'Aprobado para lote';
  if(status==='STALE_APPROVAL')return 'Cambió · volver a aprobar';
  return 'Todavía bloqueado';
}

function money(value?:number|null){
  if(value===null||value===undefined)return '—';
  return new Intl.NumberFormat('es-AR',{style:'currency',currency:'ARS',maximumFractionDigits:2}).format(value);
}

function csvCell(value:unknown){
  return `"${String(value??'').replace(/"/g,'""')}"`;
}

export function Prepublication(){
  const [report,setReport]=useState<PrepublicationReport|null>(null);
  const [finalQueue,setFinalQueue]=useState<FinalPublicationQueueReport|null>(null);
  const [search,setSearch]=useState('');
  const [source,setSource]=useState('');
  const [finalStatus,setFinalStatus]=useState<FinalPublicationQueueStatus|''>('');
  const [finalBusy,setFinalBusy]=useState('');
  const [finalMessage,setFinalMessage]=useState('');
  const [error,setError]=useState('');

  useEffect(()=>{
    Promise.all([api.prepublication(),api.finalPublicationQueue()])
      .then(([prepublication,queue])=>{setReport(prepublication);setFinalQueue(queue);setError('')})
      .catch(err=>setError(err instanceof Error?err.message:'No se pudo cargar pre-publicación.'));
  },[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (report?.items||[]).filter(item=>{
      if(source&&item.core_source!==source)return false;
      if(!term)return true;
      return [item.product.sku,item.product.name,item.verified_core_data.brand,item.verified_core_data.ean,item.verified_core_data.source_name].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[report,search,source]);

  const finalItems=useMemo(
    ()=>(finalQueue?.items||[]).filter(item=>!finalStatus||item.queue_status===finalStatus),
    [finalQueue,finalStatus],
  );

  const approvedItems=useMemo(
    ()=>(finalQueue?.items||[]).filter(item=>item.queue_status==='APPROVED_FOR_PUBLICATION'),
    [finalQueue],
  );

  async function saveFinalApproval(item:FinalPublicationQueueItem,action:'APPROVE'|'REVOKE'){
    setFinalBusy(item.product_key);
    setFinalMessage('');
    try{
      const saved=await api.saveFinalPublicationApproval(
        item.product_key,
        action,
        action==='APPROVE'
          ? 'Aprobado humanamente para la futura publicación masiva en Mercado Libre.'
          : 'Retirado manualmente de la cola final.',
      );
      setFinalQueue(current=>{
        if(!current)return current;
        const previous=item.queue_status;
        const next=saved.queue_status;
        const summary={...current.summary};
        summary[previous]=Math.max(0,summary[previous]-1);
        summary[next]+=1;
        return {
          ...current,
          summary,
          items:current.items.map(candidate=>candidate.product_key===saved.product_key?saved:candidate),
        };
      });
      setFinalMessage(action==='APPROVE'
        ? 'Producto aprobado y agregado a la cola final de Mercado Libre.'
        : 'Producto retirado de la cola final.');
    }catch(err){
      setFinalMessage(err instanceof Error?err.message:'No se pudo guardar la aprobación final.');
    }finally{
      setFinalBusy('');
    }
  }

  function exportApprovedBatch(){
    if(!approvedItems.length)return;
    const rows=[
      ['SKU','Producto','Marca','GTIN','Precio','Stock','Categoría ML','ID categoría','Imágenes','Atributos','Aprobado'],
      ...approvedItems.map(item=>[
        item.preview.sku||'',
        item.preview.title||'',
        item.preview.brand||'',
        item.preview.gtin||'',
        item.preview.price??'',
        item.preview.stock??'',
        item.preview.category_name||'',
        item.preview.category_id||'',
        item.preview.image_urls.length,
        item.preview.attributes.length,
        item.approved_at?new Date(item.approved_at).toLocaleString('es-AR'):'',
      ]),
    ];
    const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=`kiki-cola-final-mercado-libre-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  if(error&&!report)return <><header><div><p className="eyebrow">PRE-PUBLICACIÓN</p><h1>Validación final</h1></div></header><div className="notice warning">{error}</div></>;
  if(!report||!finalQueue)return <div className="auth-loading">Preparando pre-publicación…</div>;
  const s=report.summary;
  const fq=finalQueue.summary;

  return <>
    <header><div><p className="eyebrow">MVP3.8 · PRE-PUBLICACIÓN</p><h1>Validación final antes de Mercado Libre</h1><p>Ordena los controles y arma la cola que en el futuro alimentará la publicación masiva.</p></div></header>
    <div className="notice warning"><strong>No publica nada todavía.</strong> Aprobar un producto solo lo agrega a la cola interna final de KIKI Tech.</div>

    <section className="cards prepub-cards">
      <article><span>En pre-publicación</span><strong>{s.total.toLocaleString('es-AR')}</strong></article>
      <article><span>Desde Ecomm validado</span><strong>{s.from_ecomm_core.toLocaleString('es-AR')}</strong></article>
      <article><span>Desde evidencia aceptada</span><strong>{s.from_accepted_evidence.toLocaleString('es-AR')}</strong></article>
      <article><span>Imágenes aprobadas</span><strong>{s.approved_images.toLocaleString('es-AR')}</strong></article>
      <article><span>Esperando imágenes</span><strong>{s.waiting_images.toLocaleString('es-AR')}</strong></article>
      <article><span>Listos para preview</span><strong>{s.ready_for_preview.toLocaleString('es-AR')}</strong></article>
    </section>

    <section className="panel prepub-roadmap">
      <h2>Camino hasta la publicación</h2>
      <div className="prepub-flow"><span className="done">Datos centrales ✓</span><b>→</b><span>Imágenes</span><b>→</b><span>Categoría ML</span><b>→</b><span>Atributos</span><b>→</b><span>Preview</span><b>→</b><span>Aprobación final</span><b>→</b><span>Publicación masiva futura</span></div>
      <p>{report.mercadolibre_connected?'Mercado Libre está conectado: categoría y atributos pueden validarse.':'Mercado Libre todavía no está conectado; podemos seguir preparando todo lo demás.'}</p>
    </section>

    <section className="panel final-ml-queue">
      <div className="panel-title-row">
        <div><p className="eyebrow">COLA FINAL MERCADO LIBRE</p><h2>Productos preparados para el futuro lote de publicación</h2><p>Solo los aprobados acá formarán parte del lote masivo cuando habilitemos escritura en Mercado Libre.</p></div>
        <button onClick={exportApprovedBatch} disabled={!approvedItems.length}>Exportar lote CSV ({approvedItems.length})</button>
      </div>

      <div className="final-queue-summary">
        <button className={!finalStatus?'active':''} onClick={()=>setFinalStatus('')}>Todos <strong>{fq.total}</strong></button>
        <button className={finalStatus==='READY_FOR_FINAL_REVIEW'?'active':''} onClick={()=>setFinalStatus('READY_FOR_FINAL_REVIEW')}>Para aprobar <strong>{fq.READY_FOR_FINAL_REVIEW}</strong></button>
        <button className={finalStatus==='APPROVED_FOR_PUBLICATION'?'active':''} onClick={()=>setFinalStatus('APPROVED_FOR_PUBLICATION')}>Aprobados <strong>{fq.APPROVED_FOR_PUBLICATION}</strong></button>
        <button className={finalStatus==='STALE_APPROVAL'?'active':''} onClick={()=>setFinalStatus('STALE_APPROVAL')}>Cambió información <strong>{fq.STALE_APPROVAL}</strong></button>
        <button className={finalStatus==='BLOCKED'?'active':''} onClick={()=>setFinalStatus('BLOCKED')}>Bloqueados <strong>{fq.BLOCKED}</strong></button>
      </div>

      {finalMessage&&<div className="notice">{finalMessage}</div>}
      {finalItems.length===0?<div className="prepub-empty"><strong>No hay productos en este estado.</strong></div>:<div className="final-queue-list">{finalItems.map(item=><article className="final-queue-item" key={item.product_key}>
        <div className="final-queue-head">
          <div><h3>{item.preview.title||'Producto sin nombre'}</h3><p>SKU {item.preview.sku||'—'} · GTIN {item.preview.gtin||'—'}</p></div>
          <span className={`final-status ${item.queue_status}`}>{finalStatusLabel(item.queue_status)}</span>
        </div>
        <div className="final-preview-grid">
          <div><small>Marca</small><strong>{item.preview.brand||'—'}</strong></div>
          <div><small>Precio</small><strong>{money(item.preview.price)}</strong></div>
          <div><small>Stock</small><strong>{item.preview.stock??'—'}</strong></div>
          <div><small>Categoría ML</small><strong>{item.preview.category_name||'—'}</strong></div>
          <div><small>Imágenes</small><strong>{item.preview.image_urls.length}</strong></div>
          <div><small>Atributos cargados</small><strong>{item.preview.attributes.length}</strong></div>
        </div>
        {item.queue_status==='BLOCKED'&&<p className="final-blockers"><strong>Falta:</strong> {item.blockers.join(' · ')||'Controles pendientes'}</p>}
        {item.queue_status==='STALE_APPROVAL'&&<p className="final-blockers"><strong>Atención:</strong> cambió información desde la aprobación anterior. Revisá el preview y volvé a aprobar.</p>}
        <div className="final-queue-actions">
          {(item.queue_status==='READY_FOR_FINAL_REVIEW'||item.queue_status==='STALE_APPROVAL')&&<button onClick={()=>void saveFinalApproval(item,'APPROVE')} disabled={finalBusy===item.product_key}>{finalBusy===item.product_key?'Guardando…':'Aprobar para lote ML'}</button>}
          {item.queue_status==='APPROVED_FOR_PUBLICATION'&&<><span>✓ Aprobado {item.approved_at?new Date(item.approved_at).toLocaleString('es-AR'):''}</span><button className="danger-outline" onClick={()=>void saveFinalApproval(item,'REVOKE')} disabled={finalBusy===item.product_key}>Quitar del lote</button></>}
        </div>
      </article>)}</div>}
      <p className="evidence-note">{finalQueue.policy.description}</p>
    </section>

    <section className="panel">
      <div className="filters prepub-filters">
        <input placeholder="Buscar SKU, producto, marca o EAN" value={search} onChange={e=>setSearch(e.target.value)}/>
        <select value={source} onChange={e=>setSource(e.target.value)}><option value="">Todos los orígenes</option><option value="ECOMM_CORE">Ecomm validado</option><option value="ACCEPTED_EVIDENCE">Evidencia aceptada</option></select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> de {s.total.toLocaleString('es-AR')} productos</p>
      {items.length===0&&<div className="prepub-empty"><strong>Todavía no hay productos para mostrar con este filtro.</strong></div>}
      <div className="prepub-list">{items.map(item=><article className="prepub-item" key={item.product_key}>
        <div className="prepub-head"><div><h2>{item.product.name||'Producto sin nombre'}</h2><p>SKU {item.product.sku||'—'} · Stock {item.product.stock??'—'}</p></div><span className={`prepub-source ${item.core_source}`}>{item.core_source_label}</span></div>
        <div className="prepub-core"><div><small>Marca validada</small><strong>{item.verified_core_data.brand||'—'}</strong></div><div><small>EAN / GTIN</small><strong>{item.verified_core_data.ean||'—'}</strong></div><div><small>Fuente</small>{item.verified_core_data.source_url?<a href={item.verified_core_data.source_url} target="_blank" rel="noreferrer">{item.verified_core_data.source_name||'Ver evidencia'}</a>:<strong>{item.verified_core_data.source_name||'Ecomm-App'}</strong>}</div></div>
        <div className="prepub-checks"><span className={item.checks.core_data}>{checkLabel(item.checks.core_data)}<small>Datos centrales</small></span><span className={item.checks.images}>{checkLabel(item.checks.images)}<small>Imágenes</small></span><span className={item.checks.category}>{checkLabel(item.checks.category)}<small>Categoría ML</small></span><span className={item.checks.attributes}>{checkLabel(item.checks.attributes)}<small>Atributos</small></span><span className={item.checks.preview}>{checkLabel(item.checks.preview)}<small>Preview</small></span></div>
      </article>)}</div>
      <p className="evidence-note">{report.policy.description}</p>
    </section>
  </>;
}
