import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {
  EnrichmentItem,
  EnrichmentNature,
  EnrichmentPriority,
  EnrichmentReport,
  EnrichmentReviewItem,
  EnrichmentReviewQueue,
  EnrichmentReviewStatus,
  InternalEvidenceConfidence,
} from '../types/catalog';
import '../enrichment.css';

function csvCell(value:unknown){
  const text=String(value??'').replace(/"/g,'""');
  return `"${text}"`;
}

function matchesSearch(item:EnrichmentItem,term:string){
  if(!term)return true;
  return [
    item.product.sku,
    item.product.ean,
    item.product.brand,
    item.product.name,
    item.nature_label,
    item.internal_evidence.brand_candidate,
    item.internal_evidence.related_name,
  ].some(value=>String(value||'').toLowerCase().includes(term));
}

function evidenceLabel(confidence:InternalEvidenceConfidence){
  if(confidence==='HIGH')return 'Alta';
  if(confidence==='MEDIUM')return 'Media';
  return 'Sin evidencia fuerte';
}

function reviewLabel(status:EnrichmentReviewStatus){
  if(status==='APPROVED_PROPOSAL')return 'Aprobada como propuesta';
  if(status==='REJECTED')return 'Pista rechazada';
  if(status==='EXTERNAL_RESEARCH')return 'Investigar afuera';
  return 'Pendiente';
}

function priorityShort(code:EnrichmentPriority){
  if(code==='P1_HIGH')return 'P1 · Alta';
  if(code==='P2_MEDIUM')return 'P2 · Media';
  if(code==='P3_AMBIGUOUS')return 'P3 · Ambigua';
  return 'P4 · Externa';
}

export function Enrichment(){
  const [report,setReport]=useState<EnrichmentReport|null>(null);
  const [reviewQueue,setReviewQueue]=useState<EnrichmentReviewQueue|null>(null);
  const [search,setSearch]=useState('');
  const [missing,setMissing]=useState('');
  const [nature,setNature]=useState<EnrichmentNature|''>('');
  const [evidence,setEvidence]=useState('');
  const [reviewSearch,setReviewSearch]=useState('');
  const [reviewStatus,setReviewStatus]=useState<EnrichmentReviewStatus|''>('');
  const [reviewPriority,setReviewPriority]=useState<EnrichmentPriority|''>('');
  const [busyKey,setBusyKey]=useState('');
  const [message,setMessage]=useState('');

  async function load(){
    try{
      const [pilot,queue]=await Promise.all([api.enrichmentPilot(20),api.enrichmentReviewQueue()]);
      setReport(pilot);
      setReviewQueue(queue);
      setMessage('');
    }catch(error){
      setMessage(error instanceof Error?error.message:'No pudimos cargar enriquecimiento.');
    }
  }

  useEffect(()=>{void load()},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (report?.items||[]).filter(item=>{
      if(!matchesSearch(item,term))return false;
      if(missing==='EAN'&&!item.missing_fields.includes('EAN/GTIN'))return false;
      if(missing==='BRAND'&&!item.missing_fields.includes('Marca'))return false;
      if(missing==='BOTH'&&item.missing_fields.length!==2)return false;
      if(nature&&item.nature_code!==nature)return false;
      if(evidence==='CANDIDATE'&&!item.internal_evidence.brand_candidate)return false;
      if(evidence==='HIGH'&&item.internal_evidence.confidence!=='HIGH')return false;
      if(evidence==='MEDIUM'&&item.internal_evidence.confidence!=='MEDIUM')return false;
      if(evidence==='AMBIGUOUS'&&(item.internal_evidence.brand_candidate||item.internal_evidence.candidate_brands.length<2))return false;
      if(evidence==='NONE'&&(item.internal_evidence.brand_candidate||item.internal_evidence.candidate_brands.length>0))return false;
      return true;
    });
  },[report,search,missing,nature,evidence]);

  const reviewItems=useMemo(()=>{
    const term=reviewSearch.trim().toLowerCase();
    return (reviewQueue?.items||[]).filter(item=>{
      if(reviewStatus&&item.review_status!==reviewStatus)return false;
      if(reviewPriority&&item.priority_code!==reviewPriority)return false;
      if(!term)return true;
      const ev=item.internal_evidence;
      return [item.product.sku,item.product.name,ev.brand_candidate,...ev.candidate_brands,ev.related_name]
        .some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[reviewQueue,reviewSearch,reviewStatus,reviewPriority]);

  async function decide(item:EnrichmentReviewItem,status:EnrichmentReviewStatus){
    setBusyKey(item.product_key);
    setMessage('');
    try{
      await api.saveEnrichmentDecision(item.product_key,status);
      const queue=await api.enrichmentReviewQueue();
      setReviewQueue(queue);
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo guardar la decisión.');
    }finally{
      setBusyKey('');
    }
  }

  if(message&&!report)return <><header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Clasificación y evidencia interna</h1></div></header><div className="notice warning">{message}</div></>;
  if(!report||!reviewQueue)return <div className="auth-loading">Preparando clasificación, evidencia y cola de revisión…</div>;

  const s=report.summary;
  const internal=report.internal_evidence_summary;
  const q=reviewQueue.summary;

  function exportPilot(){
    const rows=[
      ['SKU','Producto','EAN actual','Marca actual','Stock','Precio','Faltantes','Tipo detectado','Base de clasificación','Estrategia sugerida','Marca candidata interna','Confianza evidencia interna','Método evidencia interna','Razón evidencia interna','SKU relacionado','Producto relacionado','EAN relacionado - referencia','Estado investigación','EAN propuesto','Marca propuesta','Fuente','URL fuente','Confianza','Observaciones'],
      ...report!.items.map(item=>[
        item.product.sku||'',item.product.name||'',item.product.ean||'',item.product.brand||'',item.product.stock??'',item.product.price??'',item.missing_fields.join(' | '),item.nature_label,item.nature_basis,item.research_strategy,item.internal_evidence.brand_candidate||'',evidenceLabel(item.internal_evidence.confidence),item.internal_evidence.method,item.internal_evidence.reason,item.internal_evidence.related_sku||'',item.internal_evidence.related_name||'',item.internal_evidence.related_ean||'','Pendiente','','','','','','',
      ]),
    ];
    const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=`kiki-enriquecimiento-evidencia-interna-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
  }

  return <>
    <header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Clasificación + evidencia interna</h1><p>Usa lo que KIKI ya sabe de su propio catálogo para orientar la investigación sin completar datos automáticamente.</p></div></header>
    {message&&<div className="notice warning">{message}</div>}
    <div className="notice warning"><strong>No modifica Ecomm-App ni Mercado Libre.</strong> “Aprobada como propuesta” significa únicamente que la pista queda aceptada dentro de KIKI Tech para una etapa posterior. Todavía necesita una fuente verificable antes de convertirse en dato final.</div>

    <section className="cards enrichment-cards">
      <article><span>Productos elegibles</span><strong>{s.total_eligible.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta EAN/GTIN</span><strong>{s.missing_ean.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta marca</span><strong>{s.missing_brand.toLocaleString('es-AR')}</strong></article>
      <article><span>Faltan ambos</span><strong>{s.missing_both.toLocaleString('es-AR')}</strong></article>
      <article><span>Piloto actual</span><strong>{s.pilot_size.toLocaleString('es-AR')}</strong><small>de {s.pilot_limit}</small></article>
    </section>

    <section className="panel">
      <h2>Evidencia del propio catálogo</h2>
      <p className="classification-help">KIKI Tech compara cada faltante con productos y marcas que ya están identificados. No copia esos datos: los usa para decidir qué conviene investigar primero.</p>
      <div className="evidence-grid">
        <article><span>Marcas conocidas</span><strong>{s.known_brands_in_catalog.toLocaleString('es-AR')}</strong><small>marcas ya presentes en otros productos</small></article>
        <article><span>Marca candidata interna</span><strong>{s.internal_brand_candidates.toLocaleString('es-AR')}</strong><small>casos con una pista única suficientemente fuerte</small></article>
        <article><span>Evidencia alta</span><strong>{internal.high.toLocaleString('es-AR')}</strong><small>marca presente en título o similitud muy fuerte</small></article>
        <article><span>Evidencia media</span><strong>{internal.medium.toLocaleString('es-AR')}</strong><small>producto interno parecido; necesita validación</small></article>
        <article><span>Internamente ambiguos</span><strong>{s.internal_evidence_ambiguous.toLocaleString('es-AR')}</strong><small>más de una marca posible: no se elige ninguna</small></article>
      </div>
      <p className="evidence-note">{internal.description}</p>
    </section>

    <section className="panel review-workflow">
      <div className="review-heading"><div><p className="eyebrow">MVP3.5 · REVISIÓN PERSISTENTE</p><h2>Cola de revisión de propuestas</h2><p>Las decisiones quedan guardadas aunque cierres sesión o Render se reinicie. Se registra historial, pero ninguna acción escribe en sistemas externos.</p></div><span className="review-total">{q.queue_total.toLocaleString('es-AR')} casos</span></div>
      <div className="review-cards">
        <article><span>Pendientes</span><strong>{q.PENDING.toLocaleString('es-AR')}</strong></article>
        <article><span>Aprobadas como propuesta</span><strong>{q.APPROVED_PROPOSAL.toLocaleString('es-AR')}</strong></article>
        <article><span>Investigación externa</span><strong>{q.EXTERNAL_RESEARCH.toLocaleString('es-AR')}</strong></article>
        <article><span>Pistas rechazadas</span><strong>{q.REJECTED.toLocaleString('es-AR')}</strong></article>
        <article><span>Sin evidencia interna</span><strong>{q.without_internal_evidence.toLocaleString('es-AR')}</strong><small>siguiente etapa de investigación externa</small></article>
      </div>
      <div className="priority-strip">{reviewQueue.priority_summary.map(group=><button key={group.code} className={reviewPriority===group.code?'active':''} onClick={()=>setReviewPriority(current=>current===group.code?'':group.code)}><span>{group.label}</span><strong>{group.count.toLocaleString('es-AR')}</strong></button>)}</div>
      <div className="filters review-filters">
        <input placeholder="Buscar SKU, producto, marca candidata o relacionado" value={reviewSearch} onChange={event=>setReviewSearch(event.target.value)}/>
        <select value={reviewStatus} onChange={event=>setReviewStatus(event.target.value as EnrichmentReviewStatus|'')}>
          <option value="">Todos los estados</option><option value="PENDING">Pendientes</option><option value="APPROVED_PROPOSAL">Aprobadas como propuesta</option><option value="EXTERNAL_RESEARCH">Investigación externa</option><option value="REJECTED">Pistas rechazadas</option>
        </select>
        <select value={reviewPriority} onChange={event=>setReviewPriority(event.target.value as EnrichmentPriority|'')}>
          <option value="">Todas las prioridades</option><option value="P1_HIGH">P1 · Evidencia alta</option><option value="P2_MEDIUM">P2 · Evidencia media</option><option value="P3_AMBIGUOUS">P3 · Ambigua</option><option value="P4_EXTERNAL">P4 · Externa</option>
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{reviewItems.length.toLocaleString('es-AR')}</strong> de {q.queue_total.toLocaleString('es-AR')} casos en cola</p>
      <div className="table-wrap"><table className="review-table"><thead><tr><th>Prioridad</th><th>Producto</th><th>Evidencia</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>
        {reviewItems.map(item=>{
          const ev=item.internal_evidence;
          const busy=busyKey===item.product_key;
          return <tr key={item.product_key}>
            <td><span className={`priority-badge ${item.priority_code}`}>{priorityShort(item.priority_code)}</span></td>
            <td><strong>{item.product.name||'—'}</strong><small className="review-meta">SKU {item.product.sku||'—'} · Stock {item.product.stock??'—'} · {item.nature_label}</small></td>
            <td className="evidence-cell">{ev.brand_candidate?<><strong className="evidence-candidate">{ev.brand_candidate}</strong><span className={`evidence-badge ${ev.confidence.toLowerCase()}`}>{evidenceLabel(ev.confidence)}</span></>:<><strong>Varias posibles</strong><span className="evidence-badge ambiguous">{ev.candidate_brands.join(' · ')}</span></>}<small className="evidence-detail">{ev.reason}</small>{ev.related_name&&<small className="evidence-related">Relacionado: {ev.related_sku?`${ev.related_sku} · `:''}{ev.related_name}{ev.related_ean?` · EAN ref. ${ev.related_ean}`:''}</small>}</td>
            <td><span className={`review-status ${item.review_status}`}>{reviewLabel(item.review_status)}</span>{item.proposed_brand&&<small className="review-proposal">Propuesta: {item.proposed_brand}</small>}{item.history_count>0&&<small className="review-meta">{item.history_count} movimiento{item.history_count===1?'':'s'}</small>}</td>
            <td><div className="review-actions">
              {ev.brand_candidate&&item.review_status!=='APPROVED_PROPOSAL'&&<button disabled={busy} onClick={()=>void decide(item,'APPROVED_PROPOSAL')}>Aprobar propuesta</button>}
              {item.review_status!=='EXTERNAL_RESEARCH'&&<button className="secondary" disabled={busy} onClick={()=>void decide(item,'EXTERNAL_RESEARCH')}>Investigar afuera</button>}
              {item.review_status!=='REJECTED'&&<button className="ghost danger" disabled={busy} onClick={()=>void decide(item,'REJECTED')}>Descartar pista</button>}
              {item.review_status!=='PENDING'&&<button className="ghost" disabled={busy} onClick={()=>void decide(item,'PENDING')}>Volver a pendiente</button>}
            </div></td>
          </tr>;
        })}
      </tbody></table></div>
      <p className="evidence-note">{reviewQueue.policy.description}</p>
    </section>

    <section className="panel">
      <h2>Tipos detectados en los {s.total_eligible.toLocaleString('es-AR')} elegibles</h2>
      <p className="classification-help">La naturaleza del producto sigue siendo independiente de la marca candidata. Un pack continúa siendo pack aunque encontremos una marca relacionada.</p>
      <div className="nature-grid">{report.classification_summary.map(group=><button key={group.code} className={`nature-card ${nature===group.code?'active':''}`} onClick={()=>setNature(current=>current===group.code?'':group.code)}><span>{group.label}</span><strong>{group.count.toLocaleString('es-AR')}</strong><small>{group.strategy}</small></button>)}</div>
      {nature&&<button className="text-button" onClick={()=>setNature('')}>Limpiar filtro por tipo</button>}
    </section>

    <section className="panel enrichment-plan"><div><h2>Prueba controlada: {s.pilot_size} productos</h2><p>El piloto sigue sirviendo para inspeccionar naturaleza + evidencia interna. La cola persistente de arriba es la que usamos para tomar decisiones.</p></div><button onClick={exportPilot}>Exportar piloto con evidencia</button></section>

    <section className="panel">
      <div className="filters enrichment-filters evidence-filters">
        <input placeholder="Buscar por SKU, producto, marca candidata o relacionado" value={search} onChange={event=>setSearch(event.target.value)}/>
        <select value={missing} onChange={event=>setMissing(event.target.value)}><option value="">Todos los faltantes</option><option value="EAN">Falta EAN/GTIN</option><option value="BRAND">Falta marca</option><option value="BOTH">Faltan ambos</option></select>
        <select value={nature} onChange={event=>setNature(event.target.value as EnrichmentNature|'')}><option value="">Todos los tipos</option>{report.classification_summary.map(group=><option value={group.code} key={group.code}>{group.label}</option>)}</select>
        <select value={evidence} onChange={event=>setEvidence(event.target.value)}><option value="">Toda evidencia interna</option><option value="CANDIDATE">Con marca candidata</option><option value="HIGH">Confianza alta</option><option value="MEDIUM">Confianza media</option><option value="AMBIGUOUS">Varias marcas posibles</option><option value="NONE">Sin evidencia interna</option></select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> del piloto</p>
      <div className="table-wrap"><table><thead><tr><th>SKU</th><th>Producto</th><th>Stock</th><th>Tipo detectado</th><th>Evidencia interna</th><th>Estrategia</th></tr></thead><tbody>
        {items.map((item,index)=>{const ev=item.internal_evidence;return <tr key={`${item.product.sku||item.product.name||'item'}-${index}`}><td className="mono">{item.product.sku||'—'}</td><td>{item.product.name||'—'}<div className="missing-tags compact">{item.missing_fields.map(field=><span key={field}>{field}</span>)}</div></td><td>{item.product.stock??'—'}</td><td><span className={`nature-badge ${item.nature_code}`}>{item.nature_label}</span><small className="nature-basis">{item.nature_basis}</small></td><td className="evidence-cell">{ev.brand_candidate?<><strong className="evidence-candidate">{ev.brand_candidate}</strong><span className={`evidence-badge ${ev.confidence.toLowerCase()}`}>{evidenceLabel(ev.confidence)}</span></>:ev.candidate_brands.length>1?<><strong>Varias posibles</strong><span className="evidence-badge ambiguous">Revisar</span></>:<span className="evidence-none">Sin evidencia fuerte</span>}<small className="evidence-detail">{ev.reason}</small>{ev.related_name&&<small className="evidence-related">Relacionado: {ev.related_sku?`${ev.related_sku} · `:''}{ev.related_name}{ev.related_ean?` · EAN ref. ${ev.related_ean}`:''}</small>}</td><td className="strategy-cell">{item.research_strategy}</td></tr>})}
      </tbody></table></div>
    </section>

    <section className="panel"><h2>Regla de seguridad</h2><p><strong>Las decisiones son internas y reversibles.</strong> “Aprobar propuesta” no valida el EAN ni modifica la marca en el catálogo. Solo registra que esa pista merece avanzar. Antes de cualquier futura escritura se seguirá exigiendo evidencia externa, vista previa y confirmación.</p></section>
  </>;
}
