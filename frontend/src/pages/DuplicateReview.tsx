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
  const [familyFilter,setFamilyFilter]=useState<''|'FAMILY_CANDIDATE'|'REVIEW_REQUIRED'>('');
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
      if(familyFilter&&group.family_diagnosis?.status!==familyFilter)return false;
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
  },[queue,search,decisionFilter,familyFilter]);

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
      <div className="kiki-duplicate-instructions"><strong>KIKI reconoce familias comerciales de SKU</strong>
      <p>Según la regla del negocio, pueden pertenecer a la misma familia si tienen el mismo SKU, comparten los primeros 4 o 3 dígitos, o comparten los primeros 2 y alguno presenta una terminación especial de tres números repetidos (111, 222, 999) o número seguido de 00 (100, 200, 300…).</p>
      <p><strong>Familia compatible no significa variante confirmada.</strong> Puede tratarse de un combo, precio especial o varias ofertas. La regla numérica no cubre SKU alfanuméricos como sabores VAINILLA/CHOCOLATE: pueden ser variantes válidas. Para guardar «Son variantes» revisá la presentación real; GTIN y publicaciones ML se verifican por separado.</p></div>
      <div className="review-filters">
        <input placeholder="Buscar SKU, EAN, producto o publicación ML" value={search} onChange={event=>setSearch(event.target.value)}/>
        <select value={decisionFilter} onChange={event=>setDecisionFilter(event.target.value as DuplicateReviewDecision|'')}>
          <option value="">Todos los estados</option>
          <option value="PENDING">Pendientes</option>
          <option value="DUPLICATE_CONFIRMED">Duplicado confirmado</option>
          <option value="DISTINCT_PRODUCTS">Productos distintos</option>
          <option value="VARIANTS">Variantes</option>
        </select>
        <select aria-label="Filtrar por familia SKU" value={familyFilter} onChange={e=>setFamilyFilter(e.target.value as ''|'FAMILY_CANDIDATE'|'REVIEW_REQUIRED')}>
          <option value="">Todas las coincidencias de familia</option>
          <option value="FAMILY_CANDIDATE">Familia comercial posible</option>
          <option value="REVIEW_REQUIRED">Sin coincidencia numérica (revisar)</option>
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
        const outsideNumericPattern=Boolean(group.family_diagnosis?.pairs.some(pair=>pair.rule==='NOT_NUMERIC'));
        const overlappingMlIds=group.products.length>1
          ? group.products[0].matched_listing_ids.filter(id=>id&&group.products.slice(1).every(p=>p.matched_listing_ids.includes(id)))
          : [];
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

          {group.family_diagnosis&&<section className={`kiki-sku-family ${group.family_diagnosis.status==='FAMILY_CANDIDATE'?'is-family':outsideNumericPattern?'is-outside-rule':'needs-review'}`} aria-label="Diagnóstico de familia SKU">
            <strong>{group.family_diagnosis.status==='FAMILY_CANDIDATE'?'Familia comercial posible':outsideNumericPattern?'Fuera de la regla numérica; no significa error':'Sin coincidencia numérica de familia'}</strong>
            <p>{group.family_diagnosis.headline}</p>
            <details>
              <summary>Ver por qué KIKI relaciona estos SKU ({group.family_diagnosis.matches}/{group.family_diagnosis.comparisons} coincidencias)</summary>
              <div className="kiki-sku-family-pairs">{group.family_diagnosis.pairs.map((pair,i)=><div key={i} className={pair.related?'is-compatible':'is-unconfirmed'}>
                <span>{pair.sku_a||'Sin SKU'} ↔ {pair.sku_b||'Sin SKU'}</span>
                <small>{pair.explanation}</small>
              </div>)}</div>
            </details>
            <small>{group.family_diagnosis.policy}</small>
          </section>}
          {overlappingMlIds.length>0&&<div className="kiki-shared-ml-warning" role="note">
            <strong>Las mismas publicaciones ML aparecen asociadas a todas estas fichas</strong>
            <p>Identificadores compartidos en el snapshot: <code>{overlappingMlIds.join(' · ')}</code></p>
            <p>Podrían ser variaciones bajo una publicación compartida, o asociaciones ambiguas por alias de SKU. Confirmá en Mercado Libre el SKU y la variante de cada publicación antes de vincular inventario. KIKI no cambiará ninguna asociación automáticamente.</p>
          </div>}
          {group.ml_evidence&&<details className="kiki-ml-identification" aria-label="Investigar publicaciones y variantes ML">
            <summary>Investigar MLA y SKU de cada publicación ({group.ml_evidence.rows.length} registros)</summary>
            <div className="kiki-ml-identification-body">
              <p><strong>Fuente:</strong> {group.ml_evidence.source==='MERCADOLIBRE_API'?'Snapshot de API ML':'Excel de publicaciones ML'} · <strong>Fecha:</strong> {dateLabel(group.ml_evidence.snapshot_at)||'Desconocida'}</p>
              {group.ml_evidence.changed_since_run&&<p className="kiki-ml-source-stale"><strong>Atención:</strong> el snapshot cambió después de la conciliación. Recargá la conciliación antes de tomar cualquier decisión.</p>}
              <p>{group.ml_evidence.reason}</p>
              {group.ml_evidence.available&&group.ml_evidence.summary&&<p>Publicaciones MLA: <strong>{group.ml_evidence.summary.mlas}</strong> · Candidatos por SKU exacto: <strong>{group.ml_evidence.summary.exact_sku_candidate_rows}</strong> · Posibles coincidencias por escritura del SKU: <strong>{group.ml_evidence.summary.normalized_sku_candidate_rows||0}</strong> · Sin candidato único: <strong>{group.ml_evidence.summary.ambiguous_rows}</strong> · Filas con ID de variación: <strong>{group.ml_evidence.summary.with_variation_id}</strong></p>}
              {group.ml_evidence.rows.length>0&&<div className="kiki-ml-identification-list">
                {group.ml_evidence.rows.map((entry,i)=><article key={entry.mla+'|'+entry.sku+'|'+i} className="kiki-ml-identification-row">
                  <div className="kiki-ml-identification-head">
                    <strong>{entry.mla}</strong>
                    <span>{entry.classification==='ONE_EXACT_SKU_CANDIDATE'?'Candidato por SKU exacto':entry.classification==='NORMALIZED_SKU_CANDIDATE'?'Posible coincidencia por escritura':entry.classification==='SHARED_NORMALIZED_SKU'?'Coincidencia ambigua al normalizar':entry.classification==='SHARED_ALIAS'?'Alias compartido':entry.classification==='SHARED_EXACT_SKU'?'SKU duplicado entre productos':entry.classification==='ALIAS_CANDIDATE'?'Solo alias, revisar':entry.classification==='NOT_IN_SNAPSHOT'?'No está en el snapshot':'Sin identidad comprobada'}</span>
                  </div>
                  {entry.title&&<p>{entry.title}</p>}
                  <p><strong>SKU en ML:</strong> {entry.sku||'No disponible'} · <strong>ID de variación:</strong> {entry.variation_id||'No disponible'}</p>
                  <p><strong>Estado importado:</strong> {entry.listing_status||'—'} · <strong>Precio importado:</strong> {entry.price!=null?Number(entry.price).toLocaleString('es-AR',{style:'currency',currency:'ARS'}):'—'}</p>
                  {entry.candidates.length>0&&<p><strong>Candidatos Ecomm:</strong> {entry.candidates.map(item=>item.name||item.key).join(' / ')}</p>}
                  <small>{entry.explanation}</small>
                </article>)}
              </div>}
              <p className="kiki-ml-readonly-note">Diagnóstico de lectura. Las posibles coincidencias por escritura ignoran únicamente espacios y diferencias de mayúsculas/minúsculas: NO confirman identidad ni desbloquean productos. Un MLA no equivale a un ID de variación. No se autoriza vinculación ni sincronización de stock sin comprobación de la variante real.</p>
            </div>
          </details>}
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

          <div className="duplicate-explanation"><strong>Qué hay que decidir:</strong> si estas fichas son duplicados reales, productos distintos o variantes físicas verificadas. Si solo confirmaste que pertenecen a una familia comercial de combos u ofertas, <strong>dejá este grupo pendiente</strong>: eso no autoriza a marcarlo como variante ni a liberar controles.</div>
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
