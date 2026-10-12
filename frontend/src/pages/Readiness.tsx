import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {InventoryLinkageCandidate,InventoryLinkageEcommAction,InventoryLinkageItem,InventoryLinkageReport,InventoryLinkageStatus} from '../types/catalog';
import '../readiness.css';

const linkageLabels:Record<InventoryLinkageStatus,string>={
  READY_TO_LINK:'Lista para vincular',
  REVIEW_AMBIGUOUS:'Revisar GTIN ambiguo',
  REVIEW_MULTIPLE_GTIN:'Revisar múltiples GTIN',
  REVIEW_IDENTIFIER_CONFLICT:'Revisar conflicto MLA/GTIN',
  REVIEW_TITLE_CANDIDATE:'Revisar candidato por título',
  REVIEW_OFFLINE_CANDIDATE:'Revisar evidencia offline',
  REVIEW_PRESENTATION_CONFLICT:'Revisar presentación',
  PENDING_ECOMM_CATALOG:'Pendiente de catálogo Ecomm',
  INVALID_GTIN:'GTIN inválido',
  NO_ECOMM_MATCH:'Sin coincidencia Ecomm',
};

function csvCell(value:unknown){
  const text=String(value??'').replace(/"/g,'""');
  return `"${text}"`;
}

const ecommActionLabels:Record<InventoryLinkageEcommAction,string>={
  ECOMM_CREATE_NEW:'Alta nueva',
  ECOMM_CORRECT_EXISTING:'Corregir existente',
  ECOMM_SPECIAL_PRESENTATION:'Pack / presentación',
  ECOMM_KEEP_RESEARCHING:'Seguir investigando',
};

const ecommActionDescriptions:Record<InventoryLinkageEcommAction,string>={
  ECOMM_CREATE_NEW:'El producto correcto no está en Ecomm y habría que darlo de alta.',
  ECOMM_CORRECT_EXISTING:'Creemos que existe en Ecomm, pero sus datos están mal o incompletos.',
  ECOMM_SPECIAL_PRESENTATION:'Es un pack, combo, tamaño o variante que necesita su propio SKU/producto.',
  ECOMM_KEEP_RESEARCHING:'Todavía no hay evidencia suficiente para decidir qué hacer.',
};

function pendingSummaryKey(action?:InventoryLinkageEcommAction|null){
  if(action==='ECOMM_CREATE_NEW')return 'pending_ecomm_create_new' as const;
  if(action==='ECOMM_CORRECT_EXISTING')return 'pending_ecomm_correct_existing' as const;
  if(action==='ECOMM_SPECIAL_PRESENTATION')return 'pending_ecomm_special_presentation' as const;
  if(action==='ECOMM_KEEP_RESEARCHING')return 'pending_ecomm_keep_researching' as const;
  return null;
}

function linkageMethodLabel(method?:string|null){
  if(method==='RECONCILIATION_MLA')return 'MLA conciliado';
  if(method==='ECOMM_MLA')return 'MLA en Ecomm';
  if(method==='GTIN_EXACT')return 'GTIN exacto';
  if(method==='TITLE_EXACT')return 'Título exacto';
  if(method==='TITLE_HIGH_CONFIDENCE')return 'Título sugerido';
  if(method==='HUMAN_CONFIRMED_TITLE')return 'Título confirmado';
  if(method==='HUMAN_CONFIRMED_OFFLINE')return 'Evidencia confirmada';
  if(method==='HUMAN_CONFIRMED_MANUAL')return 'Asignación manual confirmada';
  if(method?.startsWith('OFFLINE_SKU_EXACT'))return 'Control offline · SKU exacto';
  if(method?.startsWith('OFFLINE_TITLE'))return 'Control offline · título';
  if(method?.startsWith('OFFLINE_'))return 'Control offline';
  return method||'—';
}

export function Readiness(){
  const [linkage,setLinkage]=useState<InventoryLinkageReport|undefined>(undefined);
  const [linkageMessage,setLinkageMessage]=useState('');
  const [linkageBusy,setLinkageBusy]=useState('');
  const [candidateItem,setCandidateItem]=useState<InventoryLinkageItem|null>(null);
  const [candidateQuery,setCandidateQuery]=useState('');
  const [candidateResults,setCandidateResults]=useState<InventoryLinkageCandidate[]>([]);
  const [candidateSearching,setCandidateSearching]=useState(false);
  const [candidateSaving,setCandidateSaving]=useState('');
  const [candidateError,setCandidateError]=useState('');
  const [ecommActionBusy,setEcommActionBusy]=useState('');
  useEffect(()=>{
    api.inventoryLinkage()
      .then(setLinkage)
      .catch(error=>setLinkageMessage(error instanceof Error?error.message:'No se pudo cargar la vinculación.'));
  },[]);
  const readyLinkage=useMemo(
    ()=>(linkage?.items||[]).filter(item=>item.status==='READY_TO_LINK'),
    [linkage],
  );
  const pendingEcomm=useMemo(
    ()=>(linkage?.items||[]).filter(item=>item.status==='PENDING_ECOMM_CATALOG'),
    [linkage],
  );
  const linkageGroups=useMemo(()=>{
    const groups=new Map<string,InventoryLinkageItem[]>();
    for(const item of linkage?.items||[]){
      const gtin=String(item.gtin_raw||'').trim();
      const key=gtin?`GTIN:${gtin}`:`MLA:${item.external_id||Math.random()}`;
      const current=groups.get(key)||[];
      current.push(item);
      groups.set(key,current);
    }
    return Array.from(groups.entries()).map(([key,groupItems])=>{
      const normalizedTitles=new Set(
        groupItems.map(item=>String(item.title||'').toLowerCase().replace(/\s+/g,' ').trim()).filter(Boolean),
      );
      return {
        key,
        gtin:String(groupItems[0]?.gtin_raw||'').trim(),
        title:groupItems[0]?.title||'Producto sin título',
        brand:groupItems[0]?.brand||'',
        items:groupItems,
        hasTitleVariants:normalizedTitles.size>1,
      };
    });
  },[linkage]);
  if(linkage===undefined&&!linkageMessage)return <div className="auth-loading">Preparando vinculación…</div>;
  if(linkage===undefined&&linkageMessage)return <><header><div><p className="eyebrow">VINCULAR CON MERCADO LIBRE</p><h1>Relacionar publicaciones con el inventario</h1></div></header><div className="notice warning">{linkageMessage}</div></>;

  async function decideLinkage(item:InventoryLinkageItem,decision:'CONFIRMED'|'REJECTED'){
    const externalId=String(item.external_id||'');
    const ecommId=String(item.matched_product?.ecomm_id||'');
    if(!externalId||!ecommId)return;
    setLinkageBusy(externalId);
    setLinkageMessage('');
    try{
      const saved=await api.saveInventoryLinkageDecision(externalId,decision,ecommId);
      setLinkage(current=>{
        if(!current)return current;
        const wasReady=item.status==='READY_TO_LINK';
        const nowReady=saved.status==='READY_TO_LINK';
        const wasOffline=item.status==='REVIEW_OFFLINE_CANDIDATE';
        const wasTitle=item.status==='REVIEW_TITLE_CANDIDATE';
        return {
          ...current,
          items:current.items.map(candidate=>candidate.external_id===saved.external_id?saved:candidate),
          summary:{
            ...current.summary,
            ready_to_link:current.summary.ready_to_link+(nowReady&&!wasReady?1:0),
            confirmed_by_human:current.summary.confirmed_by_human+(decision==='CONFIRMED'&&!wasReady?1:0),
            review_required:current.summary.review_required-(nowReady&&!wasReady?1:0),
            offline_candidates:current.summary.offline_candidates-(decision==='CONFIRMED'&&wasOffline?1:0),
            title_candidates:current.summary.title_candidates-(decision==='CONFIRMED'&&wasTitle?1:0),
          },
        };
      });
      setLinkageMessage(decision==='CONFIRMED'
        ? 'Coincidencia confirmada. La publicación pasó a Lista para vincular.'
        : 'Candidato rechazado. La publicación permanece en revisión.');
    }catch(error){
      setLinkageMessage(error instanceof Error?error.message:'No se pudo guardar la decisión.');
    }finally{
      setLinkageBusy('');
    }
  }

  async function loadManualCandidates(item:InventoryLinkageItem,query=''){
    const externalId=String(item.external_id||'');
    if(!externalId)return;
    setCandidateSearching(true);
    setCandidateError('');
    try{
      const result=await api.inventoryLinkageCandidates(externalId,query,10);
      setCandidateResults(result.candidates);
    }catch(error){
      setCandidateError(error instanceof Error?error.message:'No se pudieron buscar candidatos.');
      setCandidateResults([]);
    }finally{
      setCandidateSearching(false);
    }
  }

  async function openManualCandidateSearch(item:InventoryLinkageItem){
    setCandidateItem(item);
    setCandidateQuery('');
    setCandidateResults([]);
    setCandidateError('');
    await loadManualCandidates(item,'');
  }

  async function confirmManualCandidate(candidate:InventoryLinkageCandidate){
    if(!candidateItem?.external_id||!candidate.ecomm_id)return;
    setCandidateSaving(String(candidate.ecomm_id));
    setCandidateError('');
    try{
      const saved=await api.saveInventoryManualAssignment(
        String(candidateItem.external_id),
        String(candidate.ecomm_id),
        'Asignación manual confirmada desde la búsqueda de candidatos de KIKI Tech.',
      );
      setLinkage(current=>{
        if(!current)return current;
        return {
          ...current,
          items:current.items.map(item=>item.external_id===saved.external_id?saved:item),
          summary:{
            ...current.summary,
            ready_to_link:current.summary.ready_to_link+1,
            confirmed_by_human:current.summary.confirmed_by_human+1,
            review_required:Math.max(0,current.summary.review_required-1),
            no_ecomm_match:Math.max(0,current.summary.no_ecomm_match-1),
          },
        };
      });
      setLinkageMessage('Producto Ecomm asignado manualmente. La publicación pasó a Lista para vincular.');
      setCandidateItem(null);
      setCandidateResults([]);
      setCandidateQuery('');
    }catch(error){
      setCandidateError(error instanceof Error?error.message:'No se pudo guardar la asignación manual.');
    }finally{
      setCandidateSaving('');
    }
  }

  async function markPendingEcomm(){
    if(!candidateItem?.external_id)return;
    const externalId=String(candidateItem.external_id);
    setCandidateSaving('__pending_ecomm__');
    setCandidateError('');
    try{
      const saved=await api.markInventoryPendingEcomm(
        externalId,
        'Se revisaron los candidatos del catálogo Ecomm actual y ninguno corresponde a esta publicación.',
      );
      setLinkage(current=>{
        if(!current)return current;
        return {
          ...current,
          items:current.items.map(item=>item.external_id===saved.external_id?saved:item),
          summary:{
            ...current.summary,
            no_ecomm_match:Math.max(0,current.summary.no_ecomm_match-1),
            pending_ecomm_catalog:current.summary.pending_ecomm_catalog+1,
          },
        };
      });
      setLinkageMessage('La publicación quedó en Pendientes de catálogo Ecomm. No se vinculó nada.');
      setCandidateItem(null);
      setCandidateResults([]);
      setCandidateQuery('');
    }catch(error){
      setCandidateError(error instanceof Error?error.message:'No se pudo guardar el pendiente de Ecomm.');
    }finally{
      setCandidateSaving('');
    }
  }

  async function savePendingEcommAction(item:InventoryLinkageItem,action:InventoryLinkageEcommAction){
    const externalId=String(item.external_id||'');
    if(!externalId)return;
    setEcommActionBusy(externalId);
    setLinkageMessage('');
    try{
      const saved=await api.saveInventoryEcommAction(
        externalId,
        action,
        ecommActionDescriptions[action],
      );
      setLinkage(current=>{
        if(!current)return current;
        const oldKey=pendingSummaryKey(item.ecomm_action);
        const newKey=pendingSummaryKey(action);
        const summary={...current.summary};
        if(oldKey&&oldKey!==newKey)summary[oldKey]=Math.max(0,summary[oldKey]-1);
        if(newKey&&oldKey!==newKey)summary[newKey]+=1;
        return {
          ...current,
          items:current.items.map(candidate=>candidate.external_id===saved.external_id?saved:candidate),
          summary,
        };
      });
      setLinkageMessage(`Acción Ecomm guardada: ${ecommActionLabels[action]}.`);
    }catch(error){
      setLinkageMessage(error instanceof Error?error.message:'No se pudo guardar la acción Ecomm.');
    }finally{
      setEcommActionBusy('');
    }
  }

  function exportReadyLinkage(){
    if(!readyLinkage.length)return;
    const rows=[
      ['MLA','GTIN','Producto EDIMA','Marca EDIMA','ID Ecomm','Producto Ecomm','SKU Ecomm','Método','Confirmación','Fecha confirmación','Motivo'],
      ...readyLinkage.map(item=>[
        item.external_id||'',
        item.gtin_raw||'',
        item.title||'',
        item.brand||'',
        item.matched_product?.ecomm_id||'',
        item.matched_product?.name||'',
        item.matched_product?.sku||'',
        item.match_method||'',
        item.decision_source==='HUMAN_KIKI'?'Confirmación humana KIKI':'Coincidencia automática por identificadores',
        item.decision_at?new Date(item.decision_at).toLocaleString('es-AR'):'',
        item.reason||'',
      ]),
    ];
    const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=`kiki-listas-para-vincular-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function exportPendingEcomm(){
    if(!pendingEcomm.length)return;
    const rows=[
      ['MLA','GTIN','Producto EDIMA','Marca','Acción Ecomm','Estado','Motivo','Fecha revisión'],
      ...pendingEcomm.map(item=>[
        item.external_id||'',
        item.gtin_raw||'',
        item.title||'',
        item.brand||'',
        item.ecomm_action?ecommActionLabels[item.ecomm_action]:'Sin clasificar',
        'Pendiente de catálogo Ecomm',
        item.reason||'',
        item.decision_at?new Date(item.decision_at).toLocaleString('es-AR'):'',
      ]),
    ];
    const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=`kiki-pendientes-catalogo-ecomm-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return <><header><div><p className="eyebrow">VINCULAR CON MERCADO LIBRE</p><h1>Relacionar publicaciones con el inventario</h1><p>Este circuito es para publicaciones que ya existen en Mercado Libre y necesitan quedar asociadas al producto correcto de Ecomm.</p></div></header>
  <div className="notice warning"><strong>No modifica sistemas externos.</strong> KIKI identifica, propone y guarda decisiones; la vinculación externa se ejecutará en una etapa posterior.</div>
  <section className="panel"><div className="panel-title-row"><div><h2>Vinculación de inventario EDIMA</h2><p>Cruza las publicaciones de Mercado Libre con el catálogo de Ecomm-App usando el MLA exacto y el GTIN como evidencia.</p></div></div>
    {!linkage?<p>Consultando el último reporte EDIMA…</p>:!linkage.available?<div className="notice"><strong>EDIMA todavía no está cargado.</strong><p>{linkage.message}</p><p>Subilo desde <strong>Importaciones → EDIMA · Vinculación inventario ML</strong>.</p></div>:<>
      <section className="cards readiness-cards"><article><span>Publicaciones EDIMA</span><strong>{linkage.summary.total_publications.toLocaleString('es-AR')}</strong></article><article><span>Vinculadas</span><strong>{linkage.summary.linked.toLocaleString('es-AR')}</strong></article><article><span>Sin vincular</span><strong>{linkage.summary.unlinked.toLocaleString('es-AR')}</strong></article><article><span>Listas para vincular</span><strong>{linkage.summary.ready_to_link.toLocaleString('es-AR')}</strong></article><article><span>Confirmadas por vos</span><strong>{linkage.summary.confirmed_by_human.toLocaleString('es-AR')}</strong></article><article><span>Requieren revisión</span><strong>{linkage.summary.review_required.toLocaleString('es-AR')}</strong></article><article><span>Pendientes de Ecomm</span><strong>{linkage.summary.pending_ecomm_catalog.toLocaleString('es-AR')}</strong></article><article><span>GTIN únicos sin vincular</span><strong>{linkage.summary.distinct_unlinked_gtins.toLocaleString('es-AR')}</strong></article></section>
      <p className="evidence-note">{linkage.policy.safe_match}</p>
      <p className="result-count">Calidad del reporte: <strong>{linkage.summary.data_quality_invalid_gtin_total.toLocaleString('es-AR')}</strong> publicaciones con GTIN inválido o no utilizable · <strong>{linkage.summary.data_quality_multiple_gtin_total.toLocaleString('es-AR')}</strong> con más de un código · <strong>{linkage.summary.title_candidates.toLocaleString('es-AR')}</strong> con candidato sugerido por título · <strong>{linkage.summary.offline_candidates.toLocaleString('es-AR')}</strong> con candidato de evidencia offline · <strong>{linkage.summary.presentation_conflict.toLocaleString('es-AR')}</strong> con conflicto de presentación.</p>
      {linkageMessage&&<div className="notice">{linkageMessage}</div>}
      <section className="linkage-ready-queue">
        <div className="panel-title-row">
          <div><h3>Cola operativa · Listas para vincular</h3><p>Estas coincidencias ya tienen evidencia suficiente o confirmación humana. Todavía no se ejecuta ningún cambio externo.</p></div>
          <button onClick={exportReadyLinkage} disabled={!readyLinkage.length}>Exportar CSV ({readyLinkage.length})</button>
        </div>
        {readyLinkage.length===0?<p className="evidence-note">Todavía no hay publicaciones listas para vincular.</p>:<div className="table-wrap ready-linkage-table-wrap"><table className="ready-linkage-table"><thead><tr><th>Publicación</th><th>Producto EDIMA</th><th>Producto Ecomm</th><th>Evidencia</th></tr></thead><tbody>{readyLinkage.map((item,index)=><tr key={item.external_id||index}><td><strong className="mono">{item.external_id||'—'}</strong><small className="linkage-meta">GTIN: <span className="mono">{item.gtin_raw||'—'}</span></small></td><td><strong>{item.title||'—'}</strong>{item.brand&&<small className="linkage-meta">Marca: {item.brand}</small>}</td><td><strong>{item.matched_product?.name||'—'}</strong><small className="linkage-meta">ID Ecomm: <span className="mono">{item.matched_product?.ecomm_id||'—'}</span> · SKU: <span className="mono">{item.matched_product?.sku||'—'}</span></small></td><td><strong>{item.decision_source==='HUMAN_KIKI'?'Confirmación humana':'Coincidencia por identificadores'}</strong><small className="linkage-meta">{linkageMethodLabel(item.match_method)}</small>{item.decision_at&&<small className="linkage-meta">{new Date(item.decision_at).toLocaleString('es-AR')}</small>}</td></tr>)}</tbody></table></div>}
      </section>
      <section className="linkage-ready-queue pending-ecomm-queue">
        <div className="panel-title-row">
          <div><h3>Pendientes de catálogo Ecomm</h3><p>Ya revisaste estos casos y no encontraste un producto Ecomm que corresponda. El siguiente paso es darlo de alta/corregirlo en Ecomm o importar un inventario actualizado.</p></div>
          <button onClick={exportPendingEcomm} disabled={!pendingEcomm.length}>Exportar CSV ({pendingEcomm.length})</button>
        </div>
        {pendingEcomm.length===0?<p className="evidence-note">Todavía no marcaste publicaciones como pendientes de catálogo Ecomm.</p>:<>
          <div className="ecomm-action-summary">
            <span>Alta nueva <strong>{linkage.summary.pending_ecomm_create_new}</strong></span>
            <span>Corregir existente <strong>{linkage.summary.pending_ecomm_correct_existing}</strong></span>
            <span>Pack / presentación <strong>{linkage.summary.pending_ecomm_special_presentation}</strong></span>
            <span>Seguir investigando <strong>{linkage.summary.pending_ecomm_keep_researching}</strong></span>
          </div>
          <div className="pending-ecomm-list">{pendingEcomm.map((item,index)=><article className="pending-ecomm-item" key={item.external_id||index}><div className="pending-ecomm-info"><strong>{item.title||'Producto sin título'}</strong><small className="linkage-meta">{item.external_id||'—'} · GTIN <span className="mono">{item.gtin_raw||'—'}</span>{item.brand?` · ${item.brand}`:''}</small>{item.ecomm_action&&<small className="linkage-meta"><strong>Acción definida:</strong> {ecommActionLabels[item.ecomm_action]}</small>}</div><div className="ecomm-action-buttons">{(Object.keys(ecommActionLabels) as InventoryLinkageEcommAction[]).map(action=><button key={action} className={item.ecomm_action===action?'active-action':'secondary'} onClick={()=>void savePendingEcommAction(item,action)} disabled={ecommActionBusy===item.external_id} title={ecommActionDescriptions[action]}>{ecommActionBusy===item.external_id?'Guardando…':ecommActionLabels[action]}</button>)}</div></article>)}</div>
        </>}
      </section>
      <div className="linkage-groups">
        {linkageGroups.map(group=><section className="linkage-group" key={group.key}>
          <div className="linkage-group-header">
            <div>
              <p className="eyebrow">PRODUCTO / GTIN</p>
              <h4>{group.title}</h4>
              <small className="linkage-meta">GTIN: <span className="mono">{group.gtin||'—'}</span>{group.brand?` · Marca: ${group.brand}`:''}</small>
            </div>
            <span className="linkage-group-count">{group.items.length} {group.items.length===1?'publicación ML':'publicaciones ML'}</span>
          </div>
          {group.items.length>1&&<div className={`linkage-group-note ${group.hasTitleVariants?'warning':''}`}>{group.hasTitleVariants?'⚠ Mismo GTIN con títulos o presentaciones diferentes. Revisá cada MLA antes de confirmar.':'Mismo producto/GTIN presente en varias publicaciones de Mercado Libre.'}</div>}
          <div className="table-wrap linkage-group-table-wrap"><table className="linkage-group-table"><thead><tr><th>Publicación</th><th>Coincidencia Ecomm</th><th>Estado</th><th>Acción / motivo</th></tr></thead><tbody>{group.items.map((item,index)=><tr key={item.external_id||index}><td><strong className="mono">{item.external_id||'—'}</strong>{group.hasTitleVariants&&<small className="linkage-meta">{item.title||'—'}</small>}</td><td>{item.matched_product?<><strong>{item.matched_product.name||'Producto Ecomm'}</strong><small className="linkage-meta">SKU: <span className="mono">{item.matched_product.sku||'—'}</span></small><small className="linkage-meta">Método: {linkageMethodLabel(item.match_method)}</small></>:<span>—</span>}</td><td><span className={`badge ${item.status==='READY_TO_LINK'?'READY_CORE_DATA':'REVIEW_REQUIRED'}`}>{linkageLabels[item.status]}</span>{item.decision_status==='REJECTED'&&<small className="decision-note">Rechazado previamente</small>}{item.decision_status==='STALE'&&<small className="decision-note">Decisión anterior desactualizada</small>}</td><td><div className="linkage-action-cell">{['REVIEW_TITLE_CANDIDATE','REVIEW_OFFLINE_CANDIDATE'].includes(item.status)&&item.matched_product?.ecomm_id?<div className="linkage-actions"><button onClick={()=>decideLinkage(item,'CONFIRMED')} disabled={linkageBusy===item.external_id}>{linkageBusy===item.external_id?'Guardando…':'Confirmar'}</button><button className="danger-outline" onClick={()=>decideLinkage(item,'REJECTED')} disabled={linkageBusy===item.external_id}>Rechazar</button></div>:item.status==='NO_ECOMM_MATCH'?<div className="linkage-actions"><button onClick={()=>openManualCandidateSearch(item)}>Buscar candidato</button></div>:item.decision_status==='CONFIRMED'?<strong>Confirmado</strong>:null}{item.offline_evidence?.note&&<small className="linkage-meta">Referencia offline: {item.offline_evidence.note}</small>}<small className="linkage-reason">{item.reason}</small></div></td></tr>)}</tbody></table></div>
        </section>)}
      </div>
      <p className="evidence-note">{linkage.policy.description}</p>
    </>}
  </section>
  {candidateItem&&<div className="candidate-modal-overlay" role="presentation" onClick={()=>setCandidateItem(null)}><section className="candidate-modal" role="dialog" aria-modal="true" aria-label="Buscar producto Ecomm" onClick={event=>event.stopPropagation()}><div className="candidate-modal-header"><div><p className="eyebrow">ASIGNACIÓN MANUAL</p><h3>Buscar producto Ecomm</h3><p><strong>{candidateItem.title||'Publicación EDIMA'}</strong></p><small className="linkage-meta">{candidateItem.external_id||'—'} · GTIN {candidateItem.gtin_raw||'—'}</small></div><button className="danger-outline" onClick={()=>setCandidateItem(null)}>Cerrar</button></div><form className="candidate-search-form" onSubmit={event=>{event.preventDefault();void loadManualCandidates(candidateItem,candidateQuery)}}><input autoFocus placeholder="Buscar por producto, SKU, EAN o ID Ecomm" value={candidateQuery} onChange={event=>setCandidateQuery(event.target.value)}/><button type="submit" disabled={candidateSearching}>{candidateSearching?'Buscando…':'Buscar'}</button></form>{candidateError&&<div className="notice warning">{candidateError}</div>}<p className="evidence-note">KIKI muestra sugerencias del catálogo Ecomm. Marca, cantidad, presentación y variante/sabor deben coincidir. Si cambia algo como Clásico vs Avellana, no confirmes.</p><div className="candidate-results">{candidateSearching&&candidateResults.length===0?<p>Buscando candidatos…</p>:candidateResults.length===0?<p>No encontramos candidatos con suficiente similitud. Probá buscar por una palabra, SKU, EAN o ID interno.</p>:candidateResults.map(candidate=><article className="candidate-card" key={candidate.ecomm_id||candidate.sku||candidate.name}><div><strong>{candidate.name||'Producto Ecomm'}</strong><small className="linkage-meta">ID: <span className="mono">{candidate.ecomm_id||'—'}</span> · SKU: <span className="mono">{candidate.sku||'—'}</span></small><small className="linkage-meta">Marca: {candidate.brand||'—'} · EAN: <span className="mono">{candidate.ean||'—'}</span> · Stock: {candidate.stock??'—'}</small><small className="linkage-meta">{candidate.reasons.join(' · ')||'Coincidencia manual'}</small></div><button onClick={()=>confirmManualCandidate(candidate)} disabled={candidateSaving===candidate.ecomm_id}>{candidateSaving===candidate.ecomm_id?'Guardando…':'Elegir y confirmar'}</button></article>)}</div><div className="candidate-no-match"><div><strong>¿Ninguno corresponde?</strong><p>Marcá este caso como pendiente de catálogo Ecomm. No crea productos ni modifica Ecomm.</p></div><button className="secondary" onClick={()=>void markPendingEcomm()} disabled={candidateSaving==='__pending_ecomm__'}>{candidateSaving==='__pending_ecomm__'?'Guardando…':'Ninguno coincide · enviar a Ecomm'}</button></div></section></div>}
  <section className="panel guided-help">
    <h2>¿Te falta EAN, marca u otro dato para publicar?</h2>
    <p>Esos problemas ya no se resuelven acá. KIKI los concentra en <strong>Resolver pendientes</strong>, donde cada producto tiene una acción concreta.</p>
    <Link className="guided-link" to="/work">Ir a Resolver pendientes</Link>
  </section>
</>;
}
