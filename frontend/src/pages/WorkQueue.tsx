import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {
  ExternalResearchConfidence,
  ExternalResearchItem,
  ExternalResearchQueue,
  FinalPublicationQueueReport,
  InventoryLinkageReport,
  ReadinessItem,
  ReadinessReport,
} from '../types/catalog';
import type {ReconciliationReviewQueue} from '../types/reconciliation-review';
import type {DuplicateReviewQueue} from '../types/duplicate-review';

type PendingState={
  linkage:InventoryLinkageReport|null;
  reconciliation:ReconciliationReviewQueue|null;
  duplicates:DuplicateReviewQueue|null;
  finalQueue:FinalPublicationQueueReport|null;
  readiness:ReadinessReport|null;
  research:ExternalResearchQueue|null;
};

type CoreIssue='EAN_MISSING'|'BRAND_MISSING';

type EvidenceDraft={
  proposed_ean:string;
  proposed_brand:string;
  source_name:string;
  source_url:string;
  confidence:ExternalResearchConfidence|'';
  notes:string;
};

const emptyDraft:EvidenceDraft={
  proposed_ean:'',
  proposed_brand:'',
  source_name:'',
  source_url:'',
  confidence:'',
  notes:'',
};

function productKey(item:ReadinessItem){
  const product=item.product;
  if(product.ecomm_id)return `ECOMM:${product.ecomm_id}`;
  if(product.sku_variant)return `SKU:${product.sku_variant}`;
  if(product.sku_effective)return `SKU:${product.sku_effective}`;
  if(product.sku)return `SKU:${product.sku}`;
  if(product.ean)return `EAN:${product.ean}`;
  return '';
}

function draftFromResearch(item?:ExternalResearchItem):EvidenceDraft{
  if(!item)return {...emptyDraft};
  return {
    proposed_ean:item.proposed_ean||'',
    proposed_brand:item.proposed_brand||'',
    source_name:item.source_name||'',
    source_url:item.source_url||'',
    confidence:item.confidence||'',
    notes:item.notes||'',
  };
}

export function WorkQueue(){
  const [data,setData]=useState<PendingState>({
    linkage:null,
    reconciliation:null,
    duplicates:null,
    finalQueue:null,
    readiness:null,
    research:null,
  });
  const [error,setError]=useState('');
  const [success,setSuccess]=useState('');
  const [coreIssue,setCoreIssue]=useState<CoreIssue>('EAN_MISSING');
  const [coreSearch,setCoreSearch]=useState('');
  const [resolutionItem,setResolutionItem]=useState<ReadinessItem|null>(null);
  const [draft,setDraft]=useState<EvidenceDraft>({...emptyDraft});
  const [evidenceBusy,setEvidenceBusy]=useState(false);
  const [evidenceError,setEvidenceError]=useState('');
  const [loading,setLoading]=useState(false);

  async function load(){
    setLoading(true);
    const results=await Promise.allSettled([
      api.inventoryLinkage(),
      api.reconciliationReviewQueue(),
      api.duplicateReviewQueue(),
      api.finalPublicationQueue(),
      api.publicationReadiness(),
      api.externalResearchQueue(),
    ]);
    setData({
      linkage:results[0].status==='fulfilled'?results[0].value:null,
      reconciliation:results[1].status==='fulfilled'?results[1].value:null,
      duplicates:results[2].status==='fulfilled'?results[2].value:null,
      finalQueue:results[3].status==='fulfilled'?results[3].value:null,
      readiness:results[4].status==='fulfilled'?results[4].value:null,
      research:results[5].status==='fulfilled'?results[5].value:null,
    });
    if(results.some(result=>result.status==='rejected')){
      setError('No pudimos conectar con todos los servicios de KIKI. Los valores no cargados se muestran como no disponibles, no como cero.');
    }else{
      setError('');
    }
    setLoading(false);
  }

  useEffect(()=>{void load()},[]);

  const researchByKey=useMemo(
    ()=>new Map((data.research?.items||[]).map(item=>[item.product_key,item])),
    [data.research],
  );

  function evidenceResolved(item:ReadinessItem,field:CoreIssue){
    const key=productKey(item);
    const research=key?researchByKey.get(key):undefined;
    if(research?.research_status!=='EVIDENCE_ACCEPTED')return false;
    return field==='EAN_MISSING'?Boolean(research.proposed_ean):Boolean(research.proposed_brand);
  }

  const rawEanItems=useMemo(
    ()=>(data.readiness?.items||[]).filter(item=>item.reason_codes.includes('EAN_MISSING')),
    [data.readiness],
  );
  const rawBrandItems=useMemo(
    ()=>(data.readiness?.items||[]).filter(item=>item.reason_codes.includes('BRAND_MISSING')),
    [data.readiness],
  );
  const pendingEanItems=useMemo(
    ()=>rawEanItems.filter(item=>!evidenceResolved(item,'EAN_MISSING')),
    [rawEanItems,researchByKey],
  );
  const pendingBrandItems=useMemo(
    ()=>rawBrandItems.filter(item=>!evidenceResolved(item,'BRAND_MISSING')),
    [rawBrandItems,researchByKey],
  );

  const activeCoreItems=useMemo(()=>{
    const source=coreIssue==='EAN_MISSING'?pendingEanItems:pendingBrandItems;
    const term=coreSearch.trim().toLowerCase();
    if(!term)return source;
    return source.filter(item=>[
      item.product.sku,
      item.product.name,
      item.product.brand,
      item.product.ean,
    ].some(value=>String(value||'').toLowerCase().includes(term)));
  },[coreIssue,coreSearch,pendingEanItems,pendingBrandItems]);

  const corePendingKeys=useMemo(()=>{
    const keys=new Set<string>();
    for(const item of [...pendingEanItems,...pendingBrandItems]){
      const key=productKey(item);
      if(key)keys.add(key);
    }
    return keys;
  },[pendingEanItems,pendingBrandItems]);

  const readinessAvailable=data.readiness!==null;
  const linkageAvailable=data.linkage!==null;
  const reconciliationAvailable=data.reconciliation!==null;
  const duplicatesAvailable=data.duplicates!==null;
  const finalQueueAvailable=data.finalQueue!==null;

  const metric=(available:boolean,value:number)=>available?value.toLocaleString('es-AR'):'—';

  const linkagePending=data.linkage?.summary.review_required??0;
  const pendingEcomm=data.linkage?.summary.pending_ecomm_catalog??0;
  const reconciliationPending=data.reconciliation?.summary.PENDING??0;
  const duplicatePending=data.duplicates?.summary.PENDING??0;
  const finalReady=data.finalQueue?.summary.READY_FOR_FINAL_REVIEW??0;
  const finalChanged=data.finalQueue?.summary.STALE_APPROVAL??0;
  const priceInvalid=data.readiness?.reason_summary.find(item=>item.code==='PRICE_INVALID')?.count??0;
  const totalPending=corePendingKeys.size+linkagePending+reconciliationPending+duplicatePending+finalReady+finalChanged;

  function openResolution(item:ReadinessItem){
    const key=productKey(item);
    const existing=key?researchByKey.get(key):undefined;
    setResolutionItem(item);
    setDraft({
      ...draftFromResearch(existing),
      proposed_ean:existing?.proposed_ean||item.product.ean||'',
      proposed_brand:existing?.proposed_brand||item.product.brand||'',
    });
    setEvidenceError('');
    setSuccess('');
  }

  function setField(field:keyof EvidenceDraft,value:string){
    setDraft(current=>({...current,[field]:value}));
  }

  async function ensureExternalResearch(item:ReadinessItem){
    const key=productKey(item);
    if(!key)throw new Error('Este producto no tiene una identidad estable para guardar la investigación.');
    if(researchByKey.has(key))return key;
    await api.saveEnrichmentDecision(
      key,
      'EXTERNAL_RESEARCH',
      'Enviado desde Resolver pendientes para completar datos centrales.',
    );
    return key;
  }

  async function saveEvidence(status:'DRAFT'|'EVIDENCE_ACCEPTED'){
    if(!resolutionItem)return;
    setEvidenceBusy(true);
    setEvidenceError('');
    setSuccess('');
    try{
      const key=await ensureExternalResearch(resolutionItem);
      if(status==='EVIDENCE_ACCEPTED'){
        if(!draft.source_name.trim()||!draft.source_url.trim()){
          throw new Error('Para aceptar el dato necesitás indicar una fuente y su URL.');
        }
        if(!draft.confidence||draft.confidence==='LOW'){
          throw new Error('Para aceptar evidencia elegí confianza Alta o Media.');
        }
        if(coreIssue==='EAN_MISSING'&&!draft.proposed_ean.trim()){
          throw new Error('Ingresá el EAN/GTIN que verificaste.');
        }
        if(coreIssue==='BRAND_MISSING'&&!draft.proposed_brand.trim()){
          throw new Error('Ingresá la marca que verificaste.');
        }
      }
      await api.saveExternalResearch({
        product_key:key,
        status,
        proposed_ean:draft.proposed_ean.trim()||undefined,
        proposed_brand:draft.proposed_brand.trim()||undefined,
        source_name:draft.source_name.trim()||undefined,
        source_url:draft.source_url.trim()||undefined,
        confidence:draft.confidence||undefined,
        notes:draft.notes.trim()||undefined,
      });
      const research=await api.externalResearchQueue();
      setData(current=>({...current,research}));
      if(status==='EVIDENCE_ACCEPTED'){
        setSuccess('Dato validado dentro de KIKI. Ya no queda pendiente para este control y podrá alimentar Pre-publicación.');
        setResolutionItem(null);
      }else{
        setSuccess('Borrador guardado. Podés retomarlo después desde Resolver pendientes o Investigación externa.');
      }
    }catch(err){
      setEvidenceError(err instanceof Error?err.message:'No se pudo guardar la evidencia.');
    }finally{
      setEvidenceBusy(false);
    }
  }

  async function copyResearchQuery(){
    if(!resolutionItem)return;
    const query=[
      resolutionItem.product.name,
      resolutionItem.product.brand,
      coreIssue==='EAN_MISSING'?'EAN GTIN código de barras':'marca fabricante',
      'presentación exacta',
    ].filter(Boolean).join(' ');
    try{
      await navigator.clipboard.writeText(query);
      setSuccess('Búsqueda sugerida copiada.');
    }catch{
      setEvidenceError('No se pudo copiar la búsqueda.');
    }
  }

  return <>
    <header><div><p className="eyebrow">TRABAJO PENDIENTE</p><h1>Resolver pendientes</h1><p>KIKI ordena lo que necesita una decisión humana. No hace falta recorrer todos los módulos.</p></div></header>
    {error&&<div className="notice warning"><strong>{error}</strong><div style={{marginTop:10}}><button onClick={()=>void load()} disabled={loading}>{loading?'Reintentando…':'Reintentar conexión'}</button></div></div>}
    {success&&<div className="notice success">{success}</div>}

    <section className="guided-hero">
      <div><span>Productos/casos que necesitan atención</span><strong>{readinessAvailable||linkageAvailable||reconciliationAvailable||duplicatesAvailable||finalQueueAvailable?totalPending.toLocaleString('es-AR'):'—'}</strong><p>Trabajá de arriba hacia abajo. KIKI te lleva al lugar correcto.</p></div>
    </section>

    <section className="panel core-pendings">
      <div className="panel-title-row"><div><p className="eyebrow">DATOS PARA PUBLICAR</p><h2>Completar datos centrales</h2><p>Estos productos de Ecomm todavía no pueden avanzar porque les falta información básica. Acá ya podés resolver el dato, no solo verlo.</p></div></div>

      <div className="core-pending-summary">
        <button className={coreIssue==='EAN_MISSING'?'active':''} onClick={()=>{setCoreIssue('EAN_MISSING');setCoreSearch('')}}>
          <span>Falta EAN/GTIN</span>
          <strong>{metric(readinessAvailable,pendingEanItems.length)}</strong>
          <small>{readinessAvailable?`${(rawEanItems.length-pendingEanItems.length).toLocaleString('es-AR')} resueltos con evidencia`:'Datos no disponibles'}</small>
        </button>
        <button className={coreIssue==='BRAND_MISSING'?'active':''} onClick={()=>{setCoreIssue('BRAND_MISSING');setCoreSearch('')}}>
          <span>Falta marca</span>
          <strong>{metric(readinessAvailable,pendingBrandItems.length)}</strong>
          <small>{readinessAvailable?`${(rawBrandItems.length-pendingBrandItems.length).toLocaleString('es-AR')} resueltos con evidencia`:'Datos no disponibles'}</small>
        </button>
        <div className="core-static-card"><span>Precio inválido</span><strong>{metric(readinessAvailable,priceInvalid)}</strong><small>Se corrige en el catálogo Ecomm de origen</small></div>
        <Link className="core-static-card core-link-card" to="/duplicate-review"><span>SKU duplicado</span><strong>{metric(duplicatesAvailable,duplicatePending)}</strong><small>Ir a revisión de duplicados →</small></Link>
      </div>

      <div className="core-list-toolbar">
        <div><h3>{coreIssue==='EAN_MISSING'?'Productos sin EAN/GTIN':'Productos sin marca'}</h3><p>{coreIssue==='EAN_MISSING'?'Validá el código de la presentación exacta con una fuente confiable.':'Validá la marca real del producto con una fuente confiable.'}</p></div>
        <input placeholder="Buscar por SKU o producto" value={coreSearch} onChange={event=>setCoreSearch(event.target.value)}/>
      </div>

      {!readinessAvailable?<div className="notice warning"><strong>Los productos no pudieron cargarse.</strong><p>Esto es un problema de conexión con el backend; no significa que los pendientes se hayan borrado.</p></div>:<>
      <p className="result-count">Mostrando <strong>{Math.min(activeCoreItems.length,50).toLocaleString('es-AR')}</strong> de {activeCoreItems.length.toLocaleString('es-AR')} pendientes{activeCoreItems.length>50?' · usá el buscador para encontrar uno específico':''}</p>
      <div className="core-action-list">
        {activeCoreItems.slice(0,50).map(item=>{
          const key=productKey(item);
          const research=key?researchByKey.get(key):undefined;
          return <article key={key||item.product.sku||item.product.name}>
            <div><strong>{item.product.name||'Producto sin nombre'}</strong><small>SKU {item.product.sku||item.product.sku_effective||'—'} · Stock {item.product.stock??'—'}{item.product.brand?` · Marca ${item.product.brand}`:''}</small>{research&&research.research_status!=='EVIDENCE_ACCEPTED'&&<span className="core-draft-badge">Investigación iniciada</span>}</div>
            <button onClick={()=>openResolution(item)}>{research?'Continuar':'Resolver'} {coreIssue==='EAN_MISSING'?'EAN':'marca'}</button>
          </article>;
        })}
        {activeCoreItems.length===0&&<div className="prepub-empty"><strong>No quedan productos pendientes para este control.</strong></div>}
      </div></>}
    </section>

    <section className="guided-work-list">
      <article className="guided-work-card">
        <div className="guided-step-number">1</div>
        <div className="guided-work-copy"><h2>Vincular publicaciones con Ecomm</h2><p>Publicaciones que ya existen en Mercado Libre pero todavía necesitan identificación, revisión o una acción en el catálogo Ecomm.</p><div className="guided-metrics"><span>Revisión <strong>{metric(linkageAvailable,linkagePending)}</strong></span><span>Pendientes Ecomm <strong>{metric(linkageAvailable,pendingEcomm)}</strong></span></div></div>
        <Link className="guided-link" to="/readiness">Continuar</Link>
      </article>

      <article className="guided-work-card">
        <div className="guided-step-number">2</div>
        <div className="guided-work-copy"><h2>Resolver coincidencias dudosas</h2><p>Casos donde KIKI encontró una posible relación entre producto y publicación, pero necesita confirmación humana.</p><div className="guided-metrics"><span>Por revisar <strong>{metric(reconciliationAvailable,reconciliationPending)}</strong></span></div></div>
        <Link className="guided-link" to="/review">Revisar</Link>
      </article>

      <article className="guided-work-card">
        <div className="guided-step-number">3</div>
        <div className="guided-work-copy"><h2>Revisar posibles duplicados</h2><p>Productos de Ecomm que comparten identificadores y podrían ser duplicados, variantes o productos distintos.</p><div className="guided-metrics"><span>Grupos pendientes <strong>{metric(duplicatesAvailable,duplicatePending)}</strong></span></div></div>
        <Link className="guided-link" to="/duplicate-review">Revisar</Link>
      </article>

      <article className="guided-work-card">
        <div className="guided-step-number">4</div>
        <div className="guided-work-copy"><h2>Aprobar productos para el lote ML</h2><p>Productos que ya pasaron controles y están esperando aprobación final, o cuya información cambió después de una aprobación.</p><div className="guided-metrics"><span>Para aprobar <strong>{metric(finalQueueAvailable,finalReady)}</strong></span><span>Cambiaron <strong>{metric(finalQueueAvailable,finalChanged)}</strong></span></div></div>
        <Link className="guided-link" to="/prepublication">Ir a publicar en ML</Link>
      </article>
    </section>

    <section className="panel guided-help">
      <h2>Regla simple</h2>
      <p><strong>Si ya existe en Mercado Libre:</strong> trabajalo en “Vincular con ML”. <strong>Si todavía no existe:</strong> completá sus datos y trabajalo en “Publicar en ML”.</p>
    </section>

    {resolutionItem&&<div className="candidate-modal-overlay" role="presentation" onClick={()=>setResolutionItem(null)}>
      <section className="candidate-modal core-resolution-modal" role="dialog" aria-modal="true" aria-label="Resolver dato del producto" onClick={event=>event.stopPropagation()}>
        <div className="candidate-modal-header">
          <div><p className="eyebrow">RESOLVER DATO</p><h3>{coreIssue==='EAN_MISSING'?'Completar EAN / GTIN':'Completar marca'}</h3><p><strong>{resolutionItem.product.name||'Producto sin nombre'}</strong></p><small className="linkage-meta">SKU {resolutionItem.product.sku||resolutionItem.product.sku_effective||'—'} · Stock {resolutionItem.product.stock??'—'}</small></div>
          <button className="danger-outline" onClick={()=>setResolutionItem(null)}>Cerrar</button>
        </div>

        {evidenceError&&<div className="notice warning">{evidenceError}</div>}
        <div className="core-resolution-guide">
          <strong>No adivinamos datos.</strong>
          <p>Usá fabricante oficial, GS1, etiqueta/ficha verificable o un distribuidor confiable de la presentación exacta. KIKI valida el formato del GTIN antes de aceptarlo.</p>
        </div>

        <div className="core-resolution-form">
          <label>EAN / GTIN<input inputMode="numeric" value={draft.proposed_ean} placeholder="Ej. 7791234567890" onChange={event=>setField('proposed_ean',event.target.value)}/></label>
          <label>Marca<input value={draft.proposed_brand} placeholder="Marca verificada" onChange={event=>setField('proposed_brand',event.target.value)}/></label>
          <label>Fuente<input value={draft.source_name} placeholder="Fabricante, GS1, proveedor…" onChange={event=>setField('source_name',event.target.value)}/></label>
          <label>URL de evidencia<input type="url" value={draft.source_url} placeholder="https://…" onChange={event=>setField('source_url',event.target.value)}/></label>
          <label>Confianza<select value={draft.confidence} onChange={event=>setField('confidence',event.target.value)}><option value="">Sin definir</option><option value="HIGH">Alta</option><option value="MEDIUM">Media</option><option value="LOW">Baja</option></select></label>
          <label className="core-resolution-notes">Observaciones<textarea value={draft.notes} placeholder="Presentación, tamaño, sabor, pack, por qué corresponde…" onChange={event=>setField('notes',event.target.value)}/></label>
        </div>

        <div className="core-resolution-actions">
          <button className="secondary" onClick={()=>void copyResearchQuery()} disabled={evidenceBusy}>Copiar búsqueda sugerida</button>
          <Link className="secondary-link" to="/external-research">Investigación avanzada</Link>
          <button className="secondary" onClick={()=>void saveEvidence('DRAFT')} disabled={evidenceBusy}>{evidenceBusy?'Guardando…':'Guardar borrador'}</button>
          <button onClick={()=>void saveEvidence('EVIDENCE_ACCEPTED')} disabled={evidenceBusy}>{evidenceBusy?'Validando…':'Aceptar evidencia'}</button>
        </div>
      </section>
    </div>}
  </>;
}
