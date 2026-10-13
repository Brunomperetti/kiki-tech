import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {
  CatalogContinuityDecision,
  CatalogContinuityItem,
  CatalogContinuityReport,
  ExternalResearchConfidence,
  ExternalResearchItem,
  ExternalResearchQueue,
  EnrichmentReviewItem,
  EnrichmentReviewQueue,
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
  continuity:CatalogContinuityReport|null;
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

function likelyGtinException(item:ReadinessItem){
  const name=String(item.product.name||'').toUpperCase();
  return ['SUELTA','SUELTO','GRANEL','FRACCIONADO','FRACCIONADA','ARTESANAL','CASERO','CASERA']
    .some(word=>name.includes(word));
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
    continuity:null,
  });
  const [error,setError]=useState('');
  const [success,setSuccess]=useState('');
  const [coreIssue,setCoreIssue]=useState<CoreIssue>('EAN_MISSING');
  const [coreSearch,setCoreSearch]=useState('');
  const [corePage,setCorePage]=useState(1);
  const [brandPage,setBrandPage]=useState(1);
  const [verifiedPage,setVerifiedPage]=useState(1);
  const PAGE_SIZE=50;
  const [likelyExceptionsOnly,setLikelyExceptionsOnly]=useState(false);
  const [resolutionItem,setResolutionItem]=useState<ReadinessItem|null>(null);
  const [draft,setDraft]=useState<EvidenceDraft>({...emptyDraft});
  const [evidenceBusy,setEvidenceBusy]=useState(false);
  const [evidenceError,setEvidenceError]=useState('');
  const [gtinSuggestions,setGtinSuggestions]=useState<{candidates:{ean:string;matched_name:string;matched_sku?:string;matched_brand?:string;reason:string}[];message:string}|null>(null);
  const [gtinBusy,setGtinBusy]=useState(false);
  const [pilotBusy,setPilotBusy]=useState(false);
  const [pilotError,setPilotError]=useState('');
  const [pilotResult,setPilotResult]=useState<{requested:number;external_checked:number;summary:Record<string,number>;items:{product_key:string;product_name?:string;sku?:string;status:string;candidates:{ean:string;source_url?:string;matched_name?:string}[];external_message?:string}[]}|null>(null);
  const [externalGtinBusy,setExternalGtinBusy]=useState(false);
  const [externalGtin,setExternalGtin]=useState<{candidates:{ean:string;matched_name:string;matched_brand:string;quantity:string;source_name:string;source_url:string;reason:string}[];message:string;unavailable?:boolean}|null>(null);
  const [loading,setLoading]=useState(false);
  const [continuityBusy,setContinuityBusy]=useState('');
  const [brandProposals,setBrandProposals]=useState<EnrichmentReviewQueue|null>(null);
  const [selectedBrandKeys,setSelectedBrandKeys]=useState<Set<string>>(new Set());
  const [brandBusy,setBrandBusy]=useState(false);
  const [brandError,setBrandError]=useState('');
  const [selectedGtinKeys,setSelectedGtinKeys]=useState<Set<string>>(new Set());
  const [bulkGtinOpen,setBulkGtinOpen]=useState(false);
  const [bulkGtinBusy,setBulkGtinBusy]=useState(false);
  const [bulkGtinError,setBulkGtinError]=useState('');
  const [bulkGtinDraft,setBulkGtinDraft]=useState({
    source_name:'',
    source_url:'',
    confidence:'' as ExternalResearchConfidence|'',
    notes:'',
  });

  async function load(){
    setLoading(true);
    setError('');

    const readinessResult=await Promise.allSettled([
      api.publicationReadiness(),
      api.externalResearchQueue(),
    ]);
    const brands=await api.enrichmentReviewQueue().catch(()=>null);
    setBrandProposals(brands);
    const readiness=readinessResult[0].status==='fulfilled'?readinessResult[0].value:null;
    const research=readinessResult[1].status==='fulfilled'?readinessResult[1].value:null;
    setData(current=>({...current,readiness,research}));

    const continuity=await api.catalogContinuity().catch(()=>null);
    setData(current=>({...current,continuity}));

    const linkage=await api.inventoryLinkage().catch(()=>null);
    setData(current=>({...current,linkage}));

    const reconciliation=await api.reconciliationReviewQueue().catch(()=>null);
    setData(current=>({...current,reconciliation}));

    const duplicates=await api.duplicateReviewQueue().catch(()=>null);
    setData(current=>({...current,duplicates}));

    const finalQueue=await api.finalPublicationQueue().catch(()=>null);
    setData(current=>({...current,finalQueue}));

    if(
      readiness===null
      || research===null
      || continuity===null
      || linkage===null
      || reconciliation===null
      || duplicates===null
      || finalQueue===null
    ){
      setError('No pudimos conectar con todos los servicios de KIKI. Los valores no cargados se muestran como no disponibles, no como cero.');
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
    if(!research)return false;
    if(field==='EAN_MISSING'){
      return (
        (research.research_status==='EVIDENCE_ACCEPTED'&&Boolean(research.proposed_ean))
        || research.research_status==='GTIN_NOT_APPLICABLE'
      );
    }
    return (
      ['EVIDENCE_ACCEPTED','GTIN_NOT_APPLICABLE'].includes(research.research_status)
      && Boolean(research.proposed_brand)
    );
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

  const proposedBrands=useMemo(
    ()=> (brandProposals?.items||[]).filter(item=>
      item.missing_fields.includes('Marca')
      && Boolean(item.internal_evidence.brand_candidate)
      && item.review_status==='PENDING'
    ),[brandProposals],
  );
  const approvedBrandProposals=useMemo(()=> (brandProposals?.items||[]).filter(item=>item.review_status==='APPROVED_PROPOSAL' && Boolean(item.proposed_brand) && item.missing_fields.includes('Marca') && !researchByKey.get(item.product_key)?.proposed_brand),[brandProposals,researchByKey]);
  const brandSearch=coreSearch.trim().toLocaleLowerCase();
  const filteredProposedBrands=useMemo(()=>proposedBrands.filter(item=>[
    item.product.name,item.product.sku,item.product.sku_effective,item.internal_evidence.brand_candidate,
  ].some(value=>String(value||'').toLocaleLowerCase().includes(brandSearch))),[proposedBrands,brandSearch]);
  const filteredApprovedBrands=useMemo(()=>approvedBrandProposals.filter(item=>[
    item.product.name,item.product.sku,item.proposed_brand,
  ].some(value=>String(value||'').toLocaleLowerCase().includes(brandSearch))),[approvedBrandProposals,brandSearch]);
  const highConfidenceBrands=useMemo(
    ()=>proposedBrands.filter(item=>item.internal_evidence.confidence==='HIGH'),
    [proposedBrands],
  );

  async function approveBrand(item:EnrichmentReviewItem){
    setBrandBusy(true);setBrandError('');setSuccess('');
    try{
      await api.saveEnrichmentDecision(item.product_key,'APPROVED_PROPOSAL','Propuesta interna aceptada; pendiente de validar fuente verificable.');
      setBrandProposals(await api.enrichmentReviewQueue());
      setSelectedBrandKeys(current=>new Set([...current].filter(key=>key!==item.product_key)));
      setSuccess('Propuesta interna de marca guardada. Para usarla como dato verificado, confirmá su fuente en Resolver marca.');
    }catch(err){setBrandError(err instanceof Error?err.message:'No se pudo aprobar la propuesta.')}
    finally{setBrandBusy(false);}
  }

  async function approveSelectedBrands(){
    const keys=[...selectedBrandKeys];
    if(!keys.length)return;
    if(!window.confirm(`¿Aprobar ${keys.length} propuestas internas de confianza alta? No quedan verificadas para publicación.`))return;
    setBrandBusy(true);setBrandError('');setSuccess('');
    try{
      const result=await api.bulkApproveBrandProposals(keys);
      setBrandProposals(await api.enrichmentReviewQueue());
      setSelectedBrandKeys(new Set());
      setSuccess(`${result.processed} propuestas internas guardadas con evidencia e historial individual. Falta verificar su fuente para completar las marcas.`);
    }catch(err){setBrandError(err instanceof Error?err.message:'No se pudo aprobar el lote.')}
    finally{setBrandBusy(false);}
  }

  const suggestedExceptionItems=useMemo(
    ()=>pendingEanItems.filter(likelyGtinException),
    [pendingEanItems],
  );
  const likelyExceptionCount=suggestedExceptionItems.length;

  const activeCoreItems=useMemo(()=>{
    let source=coreIssue==='EAN_MISSING'?pendingEanItems:pendingBrandItems;
    if(coreIssue==='EAN_MISSING'&&likelyExceptionsOnly){
      source=source.filter(likelyGtinException);
    }
    const term=coreSearch.trim().toLowerCase();
    if(!term)return source;
    return source.filter(item=>[
      item.product.sku,
      item.product.name,
      item.product.brand,
      item.product.ean,
    ].some(value=>String(value||'').toLowerCase().includes(term)));
  },[coreIssue,coreSearch,likelyExceptionsOnly,pendingEanItems,pendingBrandItems]);

  const visibleBrandProposals=filteredProposedBrands.slice((brandPage-1)*PAGE_SIZE,brandPage*PAGE_SIZE);
  const visibleApprovedBrands=filteredApprovedBrands.slice((verifiedPage-1)*PAGE_SIZE,verifiedPage*PAGE_SIZE);
  const visibleCoreItems=activeCoreItems.slice((corePage-1)*PAGE_SIZE,corePage*PAGE_SIZE);
  const brandTotalPages=Math.max(1,Math.ceil(filteredProposedBrands.length/PAGE_SIZE));
  const verifiedTotalPages=Math.max(1,Math.ceil(filteredApprovedBrands.length/PAGE_SIZE));
  const coreTotalPages=Math.max(1,Math.ceil(activeCoreItems.length/PAGE_SIZE));
  useEffect(()=>setBrandPage(p=>Math.min(p,brandTotalPages)),[brandTotalPages]);
  useEffect(()=>setVerifiedPage(p=>Math.min(p,verifiedTotalPages)),[verifiedTotalPages]);
  useEffect(()=>setCorePage(p=>Math.min(p,coreTotalPages)),[coreTotalPages]);

  const corePendingKeys=useMemo(()=>{
    const keys=new Set<string>();
    for(const item of [...pendingEanItems,...pendingBrandItems]){
      const key=productKey(item);
      if(key)keys.add(key);
    }
    return keys;
  },[pendingEanItems,pendingBrandItems]);

  const continuityAvailable=data.continuity!==null;
  const readinessAvailable=data.readiness!==null;
  const linkageAvailable=data.linkage!==null;
  const reconciliationAvailable=data.reconciliation!==null;
  const duplicatesAvailable=data.duplicates!==null;
  const finalQueueAvailable=data.finalQueue!==null;

  const metric=(available:boolean,value:number)=>available?value.toLocaleString('es-AR'):'—';

  const continuityConflicts=(data.continuity?.summary.conflicts??0)+(data.continuity?.summary.stale_decisions??0);
  const continuityConflictItems=(data.continuity?.items||[]).filter(item=>['CONFLICT','STALE_DECISION'].includes(item.state));

  const linkagePending=data.linkage?.summary.review_required??0;
  const pendingEcomm=data.linkage?.summary.pending_ecomm_catalog??0;
  const reconciliationPending=data.reconciliation?.summary.PENDING??0;
  const duplicatePending=data.duplicates?.summary.PENDING??0;
  const finalReady=data.finalQueue?.summary.READY_FOR_FINAL_REVIEW??0;
  const finalChanged=data.finalQueue?.summary.STALE_APPROVAL??0;
  const priceInvalid=data.readiness?.reason_summary.find(item=>item.code==='PRICE_INVALID')?.count??0;
  const totalPending=corePendingKeys.size+continuityConflicts+linkagePending+reconciliationPending+duplicatePending+finalReady+finalChanged;

  async function saveContinuityDecision(item:CatalogContinuityItem,decision:CatalogContinuityDecision){
    setContinuityBusy(item.conflict_key);
    setSuccess('');
    try{
      await api.saveCatalogContinuityDecision(
        item.conflict_key,
        decision,
        decision==='USE_KIKI'
          ?'Se conserva el dato validado previamente en KIKI frente al valor actual de Ecomm.'
          :'Se acepta el valor actual de Ecomm para este campo.',
      );
      const [continuity,finalQueue]=await Promise.all([
        api.catalogContinuity(),
        api.finalPublicationQueue().catch(()=>data.finalQueue),
      ]);
      setData(current=>({...current,continuity,finalQueue:finalQueue||current.finalQueue}));
      setSuccess(decision==='USE_KIKI'
        ?'Decisión guardada: KIKI conserva el dato validado.'
        :'Decisión guardada: KIKI usará el dato actual de Ecomm.');
    }catch(err){
      setError(err instanceof Error?err.message:'No se pudo resolver el conflicto entre KIKI y Ecomm.');
    }finally{
      setContinuityBusy('');
    }
  }

  function toggleGtinSelection(key:string){
    setSelectedGtinKeys(current=>{
      const next=new Set(current);
      if(next.has(key))next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAllSuggestedGtin(){
    setSelectedGtinKeys(new Set(suggestedExceptionItems.map(productKey).filter(Boolean)));
    setLikelyExceptionsOnly(true);
  }

  function clearGtinSelection(){
    setSelectedGtinKeys(new Set());
  }

  async function saveBulkGtinExceptions(){
    const productKeys=Array.from(selectedGtinKeys);
    if(!productKeys.length){
      setBulkGtinError('Seleccioná al menos un producto.');
      return;
    }
    if(!bulkGtinDraft.source_name.trim()||!bulkGtinDraft.source_url.trim()){
      setBulkGtinError('Indicá la fuente común y su URL.');
      return;
    }
    if(!bulkGtinDraft.confidence||bulkGtinDraft.confidence==='LOW'){
      setBulkGtinError('Para resolver el lote elegí confianza Alta o Media.');
      return;
    }
    if(!bulkGtinDraft.notes.trim()){
      setBulkGtinError('Explicá por qué este lote no tendría GTIN propio.');
      return;
    }

    setBulkGtinBusy(true);
    setBulkGtinError('');
    setSuccess('');
    try{
      const result=await api.bulkMarkGtinNotApplicable({
        product_keys:productKeys,
        source_name:bulkGtinDraft.source_name.trim(),
        source_url:bulkGtinDraft.source_url.trim(),
        confidence:bulkGtinDraft.confidence,
        notes:bulkGtinDraft.notes.trim(),
      });
      const [research,continuity]=await Promise.all([
        api.externalResearchQueue(),
        api.catalogContinuity().catch(()=>data.continuity),
      ]);
      setData(current=>({...current,research,continuity:continuity||current.continuity}));
      setSelectedGtinKeys(new Set());
      setBulkGtinOpen(false);
      setSuccess(`${result.processed} productos quedaron documentados como “GTIN no aplica”. Mercado Libre validará después si cada categoría admite la excepción.`);
    }catch(err){
      setBulkGtinError(err instanceof Error?err.message:'No se pudo resolver el lote.');
    }finally{
      setBulkGtinBusy(false);
    }
  }

  async function runGtinPilot(){
    const keys=activeCoreItems.slice(0,20).map(productKey).filter(Boolean);
    if(!keys.length){setPilotError('No hay productos para investigar.');return;}
    setPilotBusy(true);setPilotError('');setPilotResult(null);
    try{setPilotResult(await api.gtinBatchPilot(keys));}
    catch(err){setPilotError(err instanceof Error?err.message:'Falló la investigación piloto.');}
    finally{setPilotBusy(false);}
  }

  function openResolution(item:ReadinessItem){
    const key=productKey(item);
    const existing=key?researchByKey.get(key):undefined;
    setResolutionItem(item);
    setGtinSuggestions(null);
    setExternalGtin(null);
    setDraft({
      ...draftFromResearch(existing),
      proposed_ean:existing?.proposed_ean||item.product.ean||'',
      proposed_brand:existing?.proposed_brand||item.product.brand||'',
    });
    setEvidenceError('');
    setSuccess('');
  }

  function verifyBrandProposal(item:EnrichmentReviewItem){
    const source=(data.readiness?.items||[]).find(row=>productKey(row)===item.product_key);
    if(!source){setBrandError('El producto ya no está disponible en el catálogo actual.');return;}
    setCoreIssue('BRAND_MISSING');
    openResolution(source);
    setDraft(current=>({...current,proposed_brand:item.proposed_brand||item.internal_evidence.brand_candidate||'',confidence:'',source_name:'',source_url:'',notes:''}));
  }

  async function findGtinSuggestions(){
    if(!resolutionItem)return;
    setGtinBusy(true);setEvidenceError('');
    try{
      setGtinSuggestions(await api.gtinCandidates(productKey(resolutionItem)));
    }catch(err){setEvidenceError(err instanceof Error?err.message:'No se pudo consultar el catálogo interno.');}
    finally{setGtinBusy(false);}
  }

  async function findExternalGtin(){
    if(!resolutionItem)return;
    setExternalGtinBusy(true);setEvidenceError('');
    try{
      setExternalGtin(await api.externalGtinCandidates(productKey(resolutionItem)));
    }catch(err){setEvidenceError(err instanceof Error?err.message:'No se pudo consultar la fuente externa.');}
    finally{setExternalGtinBusy(false);}
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

  async function saveEvidence(status:'DRAFT'|'EVIDENCE_ACCEPTED'|'GTIN_NOT_APPLICABLE'){
    if(!resolutionItem)return;
    setEvidenceBusy(true);
    setEvidenceError('');
    setSuccess('');
    try{
      const key=await ensureExternalResearch(resolutionItem);
      if(status==='EVIDENCE_ACCEPTED'||status==='GTIN_NOT_APPLICABLE'){
        if(!draft.source_name.trim()||!draft.source_url.trim()){
          throw new Error('Para aceptar el dato necesitás indicar una fuente y su URL.');
        }
        if(!draft.confidence||draft.confidence==='LOW'){
          throw new Error('Para aceptar evidencia elegí confianza Alta o Media.');
        }
      }
      if(status==='EVIDENCE_ACCEPTED'){
        if(coreIssue==='EAN_MISSING'&&!draft.proposed_ean.trim()){
          throw new Error('Ingresá el EAN/GTIN que verificaste.');
        }
        if(coreIssue==='BRAND_MISSING'&&!draft.proposed_brand.trim()){
          throw new Error('Ingresá la marca que verificaste.');
        }
      }
      if(status==='GTIN_NOT_APPLICABLE'){
        if(coreIssue!=='EAN_MISSING'){
          throw new Error('La excepción de GTIN solo corresponde al control de EAN/GTIN.');
        }
        if(draft.proposed_ean.trim()){
          throw new Error('Para marcar que GTIN no aplica, dejá vacío el campo EAN/GTIN.');
        }
        if(!draft.notes.trim()){
          throw new Error('Explicá en Observaciones por qué el producto no tendría GTIN propio.');
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
      }else if(status==='GTIN_NOT_APPLICABLE'){
        setSuccess('Excepción de GTIN documentada. KIKI la validará después contra los requisitos de la categoría de Mercado Libre.');
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
      <div><span>Productos/casos que necesitan atención</span><strong>{readinessAvailable||continuityAvailable||linkageAvailable||reconciliationAvailable||duplicatesAvailable||finalQueueAvailable?totalPending.toLocaleString('es-AR'):'—'}</strong><p>Trabajá de arriba hacia abajo. KIKI te lleva al lugar correcto.</p></div>
    </section>

    <section className="panel catalog-continuity-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">MEMORIA DE KIKI</p><h2>Datos validados que se conservan al actualizar Ecomm</h2><p>Cuando subís un Ecomm nuevo, KIKI mantiene las correcciones ya verificadas. Solo te consulta si el nuevo dato de origen contradice algo validado.</p></div>
      </div>
      {!continuityAvailable?<div className="notice warning">No pudimos comparar el catálogo nuevo con los datos validados de KIKI.</div>:<>
        <div className="continuity-summary">
          <span>Productos con datos validados <strong>{data.continuity!.summary.validated_products.toLocaleString('es-AR')}</strong></span>
          <span>Ecomm vacío · KIKI conserva <strong>{data.continuity!.summary.kiki_only.toLocaleString('es-AR')}</strong></span>
          <span>Ya coinciden con Ecomm <strong>{data.continuity!.summary.aligned.toLocaleString('es-AR')}</strong></span>
          <span className={continuityConflicts?'warning':''}>Conflictos a decidir <strong>{continuityConflicts.toLocaleString('es-AR')}</strong></span>
        </div>
        {data.continuity!.summary.missing_from_current_ecomm>0&&<div className="notice warning"><strong>{data.continuity!.summary.missing_from_current_ecomm} productos validados ya no aparecen en el Ecomm actual.</strong> KIKI conserva su historial; conviene revisar si fueron eliminados, cambiaron de ID o dejaron de venderse.</div>}
        {continuityConflictItems.length===0?<div className="continuity-ok"><strong>Sin conflictos de datos.</strong><span>Podés cargar reportes nuevos de Ecomm sin perder lo que ya validaron en KIKI.</span></div>:<div className="continuity-conflicts">
          {continuityConflictItems.map(item=><article key={item.conflict_key}>
            <div className="continuity-conflict-title"><div><strong>{item.product.name||'Producto sin nombre'}</strong><small>SKU {item.product.sku||'—'} · {item.field_label}</small></div><span>{item.state==='STALE_DECISION'?'Ecomm volvió a cambiar':'Revisar'}</span></div>
            <div className="continuity-values">
              <div><small>Ecomm actual</small><strong>{item.ecomm_value||'Vacío'}</strong></div>
              <div><small>KIKI validado</small><strong>{item.kiki_value||'—'}</strong>{item.source_name&&<small>Fuente: {item.source_name}</small>}</div>
            </div>
            <div className="continuity-actions"><button onClick={()=>void saveContinuityDecision(item,'USE_KIKI')} disabled={continuityBusy===item.conflict_key}>{continuityBusy===item.conflict_key?'Guardando…':'Conservar KIKI'}</button><button className="secondary" onClick={()=>void saveContinuityDecision(item,'USE_ECOMM')} disabled={continuityBusy===item.conflict_key}>Usar Ecomm</button>{item.source_url&&<a href={item.source_url} target="_blank" rel="noreferrer">Ver evidencia</a>}</div>
          </article>)}
        </div>}
        <p className="evidence-note">{data.continuity!.policy.description}</p>
      </>}
    </section>

    <section className="panel core-pendings">
      <div className="panel-title-row"><div><p className="eyebrow">DATOS PARA PUBLICAR</p><h2>Completar datos centrales</h2><p>Estos productos de Ecomm todavía no pueden avanzar porque les falta información básica. Acá ya podés resolver el dato, no solo verlo.</p></div></div>

      <div className="core-pending-summary">
        <button className={coreIssue==='EAN_MISSING'?'active':''} onClick={()=>{setCoreIssue('EAN_MISSING');setCoreSearch('');setCorePage(1);setLikelyExceptionsOnly(false)}}>
          <span>Falta EAN/GTIN</span>
          <strong>{metric(readinessAvailable,pendingEanItems.length)}</strong>
          <small>{readinessAvailable?`${(rawEanItems.length-pendingEanItems.length).toLocaleString('es-AR')} resueltos con evidencia`:'Datos no disponibles'}</small>
        </button>
        <button className={coreIssue==='BRAND_MISSING'?'active':''} onClick={()=>{setCoreIssue('BRAND_MISSING');setCoreSearch('');setCorePage(1);setLikelyExceptionsOnly(false)}}>
          <span>Falta marca</span>
          <strong>{metric(readinessAvailable,pendingBrandItems.length)}</strong>
          <small>{readinessAvailable?`${(rawBrandItems.length-pendingBrandItems.length).toLocaleString('es-AR')} resueltos con evidencia`:'Datos no disponibles'}</small>
        </button>
        <div className="core-static-card"><span>Precio inválido</span><strong>{metric(readinessAvailable,priceInvalid)}</strong><small>Se corrige en el catálogo Ecomm de origen</small></div>
        <Link className="core-static-card core-link-card" to="/duplicate-review"><span>SKU duplicado</span><strong>{metric(duplicatesAvailable,duplicatePending)}</strong><small>Ir a revisión de duplicados →</small></Link>
      </div>

      <div className="core-list-toolbar">
        <div><h3>{coreIssue==='EAN_MISSING'?'Productos sin EAN/GTIN':'Productos sin marca'}</h3><p>{coreIssue==='EAN_MISSING'?'Validá el código de la presentación exacta con una fuente confiable.':'Validá la marca real del producto con una fuente confiable.'}</p></div>
        <input placeholder="Buscar por SKU o producto" value={coreSearch} onChange={event=>{setCoreSearch(event.target.value);setCorePage(1);setBrandPage(1);setVerifiedPage(1)}}/>
      </div>
      {coreIssue==='BRAND_MISSING'&&<section className="core-brand-proposals">
        <div className="core-list-toolbar">
          <div><h3>Marcas sugeridas por KIKI</h3><p>Candidatas del catálogo interno, con evidencia y nivel de confianza. Aprobar una propuesta no equivale a verificarla ni habilita publicación.</p></div>
        </div>
        {brandError&&<div className="notice warning">{brandError}</div>}
        {brandProposals===null?<p>Las sugerencias no están disponibles en este momento.</p>:<>
          <p>{filteredProposedBrands.length} propuestas pendientes · {highConfidenceBrands.length} de confianza alta en el catálogo</p>
          {highConfidenceBrands.length>0&&<div className="bulk-selection-bar">
            <strong>{selectedBrandKeys.size} seleccionadas</strong>
            <button className="secondary" disabled={brandBusy} onClick={()=>setSelectedBrandKeys(new Set(highConfidenceBrands.map(item=>item.product_key)))}>Seleccionar alta confianza</button>
            <button className="secondary" disabled={brandBusy} onClick={()=>setSelectedBrandKeys(new Set())}>Limpiar</button>
            <button disabled={brandBusy||selectedBrandKeys.size===0} onClick={()=>void approveSelectedBrands()}>Aprobar propuestas seleccionadas</button>
          </div>}
          <div className="brand-proposal-list">
            {visibleBrandProposals.map(item=><article className="brand-proposal-card" key={item.product_key}>
              {item.internal_evidence.confidence==='HIGH'&&<label className="core-select"><input type="checkbox" checked={selectedBrandKeys.has(item.product_key)} onChange={()=>setSelectedBrandKeys(current=>{const next=new Set(current);if(next.has(item.product_key))next.delete(item.product_key);else next.add(item.product_key);return next;})}/> Seleccionar</label>}
              <div className="brand-proposal-details">
                <strong>{item.product.name||'Producto sin nombre'}</strong>
                <div className="brand-proposal-meta"><span>Marca sugerida: <b>{item.internal_evidence.brand_candidate}</b></span><span>Confianza {item.internal_evidence.confidence==='HIGH'?'alta':'media'}</span><span>Origen: catálogo interno</span></div>
                <p>{item.internal_evidence.reason}</p>
                {item.internal_evidence.related_sku&&<small>SKU de referencia: {item.internal_evidence.related_sku}</small>}
              </div>
              <button className="secondary" disabled={brandBusy} onClick={()=>void approveBrand(item)}>Aceptar propuesta</button>
            </article>)}
          </div>
          <Pagination page={brandPage} total={filteredProposedBrands.length} pageSize={PAGE_SIZE} onChange={setBrandPage} />
          {approvedBrandProposals.length>0&&<section className="brand-verify-section">
            <h3>Propuestas aceptadas · falta verificar la fuente ({approvedBrandProposals.length})</h3>
            <p>Estas marcas fueron aprobadas como candidatas, pero aún no resuelven el pendiente. Revisá la ficha del fabricante o proveedor antes de confirmarlas.</p>
            <div className="brand-proposal-list">{visibleApprovedBrands.map(item=><article className="brand-proposal-card" key={item.product_key}>
              <div className="brand-proposal-details"><strong>{item.product.name||'Producto sin nombre'}</strong><div className="brand-proposal-meta"><span>Marca propuesta: <b>{item.proposed_brand}</b></span><span>Pendiente de fuente verificable</span></div></div>
              <button className="secondary" onClick={()=>verifyBrandProposal(item)}>Verificar marca</button>
            </article>)}</div>
            <Pagination page={verifiedPage} total={filteredApprovedBrands.length} pageSize={PAGE_SIZE} onChange={setVerifiedPage}/>
          </section>}
        </>}
      </section>}
      {coreIssue==='EAN_MISSING'&&readinessAvailable&&<section className="gtin-pilot-panel">
        <div><h3>Piloto de investigación · 20 productos</h3><p>Evalúa los primeros 20 de la búsqueda actual. Examina el catálogo interno y consulta hasta 5 en Open Food Facts. No modifica códigos ni los aprueba.</p></div>
        <button disabled={pilotBusy||activeCoreItems.length===0} onClick={()=>void runGtinPilot()}>{pilotBusy?'Investigando…':'Investigar primeros 20'}</button>
        {pilotError&&<div className="notice warning">{pilotError}</div>}
        {pilotResult&&<div className="gtin-pilot-results">
          <p>Analizados: {pilotResult.requested} · Consulta externa: {pilotResult.external_checked} · Con candidatos: {pilotResult.summary.candidate||0} · Sin candidatos: {pilotResult.summary.no_candidate||0} · Fuente no disponible: {pilotResult.summary.source_unavailable||0} · Fuente externa no consultada: {pilotResult.summary.external_not_checked||0}</p>
          <div className="gtin-pilot-items">{pilotResult.items.map(item=><article key={item.product_key}>
            <strong>{item.product_name||item.product_key}</strong>
            <small>SKU {item.sku||'—'} · {item.status==='candidate'?'Candidato para revisar':item.status==='source_unavailable'?'Fuente no disponible':item.status==='needs_product_data'?'Faltan datos':'Sin candidato confirmado'}</small>
            {item.candidates.map(candidate=><div key={candidate.ean}><code>{candidate.ean}</code> {candidate.matched_name||''} {candidate.source_url&&<a href={candidate.source_url} target="_blank" rel="noopener noreferrer">Ver fuente ↗</a>}</div>)}
          </article>)}</div>
        </div>}
      </section>}
      {coreIssue==='EAN_MISSING'&&readinessAvailable&&<div className="gtin-triage">
        <div><strong>KIKI detectó {likelyExceptionCount.toLocaleString('es-AR')} posibles casos sin GTIN propio</strong><p>Señal conservadora basada en palabras como “suelta”, “granel”, “fraccionado” o “artesanal”. Podés revisarlos y resolverlos juntos cuando realmente comparten la misma justificación.</p></div>
        <div className="gtin-triage-actions">
          <button className={likelyExceptionsOnly?'active-action':'secondary'} onClick={()=>setLikelyExceptionsOnly(current=>!current)}>{likelyExceptionsOnly?'Ver todos':'Revisar sugeridos'}</button>
          {likelyExceptionCount>0&&<button onClick={selectAllSuggestedGtin}>Seleccionar {likelyExceptionCount.toLocaleString('es-AR')}</button>}
        </div>
      </div>}
      {coreIssue==='EAN_MISSING'&&selectedGtinKeys.size>0&&<div className="bulk-selection-bar">
        <strong>{selectedGtinKeys.size.toLocaleString('es-AR')} seleccionados</strong>
        <span>Solo usá la acción masiva si la misma evidencia y el mismo motivo aplican a todo el grupo.</span>
        <div><button className="secondary" onClick={clearGtinSelection}>Limpiar</button><button onClick={()=>{setBulkGtinError('');setBulkGtinOpen(true)}}>GTIN no aplica en lote</button></div>
      </div>}

      {!readinessAvailable?<div className="notice warning"><strong>Los productos no pudieron cargarse.</strong><p>Esto es un problema de conexión con el backend; no significa que los pendientes se hayan borrado.</p></div>:<>
      <p className="result-count">Mostrando <strong>{activeCoreItems.length?((corePage-1)*PAGE_SIZE+1).toLocaleString('es-AR'):0}–{Math.min(corePage*PAGE_SIZE,activeCoreItems.length).toLocaleString('es-AR')}</strong> de {activeCoreItems.length.toLocaleString('es-AR')} pendientes</p>
      <div className="core-action-list">
        {visibleCoreItems.map(item=>{
          const key=productKey(item);
          const research=key?researchByKey.get(key):undefined;
          const selectable=coreIssue==='EAN_MISSING'&&likelyGtinException(item)&&Boolean(key);
          return <article key={key||item.product.sku||item.product.name} className={selectable&&selectedGtinKeys.has(key)?'selected-core-item':''}>
            {selectable&&<label className="core-select"><input type="checkbox" checked={selectedGtinKeys.has(key)} onChange={()=>toggleGtinSelection(key)}/><span>Seleccionar</span></label>}
            <div><strong>{item.product.name||'Producto sin nombre'}</strong><small>SKU {item.product.sku||item.product.sku_effective||'—'} · Stock {item.product.stock??'—'}{item.product.brand?` · Marca ${item.product.brand}`:''}</small><div className="core-row-badges">{coreIssue==='EAN_MISSING'&&likelyGtinException(item)&&<span className="core-suggestion-badge">Posible excepción GTIN</span>}{research&&!['EVIDENCE_ACCEPTED','GTIN_NOT_APPLICABLE'].includes(research.research_status)&&<span className="core-draft-badge">Investigación iniciada</span>}</div></div>
            <button onClick={()=>openResolution(item)}>{research?'Continuar':'Resolver'} {coreIssue==='EAN_MISSING'?'EAN':'marca'}</button>
          </article>;
        })}
        {activeCoreItems.length===0&&<div className="prepub-empty"><strong>No quedan productos pendientes para este control.</strong></div>}
      </div><Pagination page={corePage} total={activeCoreItems.length} pageSize={PAGE_SIZE} onChange={setCorePage}/></>}
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

    {bulkGtinOpen&&<div className="candidate-modal-overlay" role="presentation" onClick={()=>!bulkGtinBusy&&setBulkGtinOpen(false)}>
      <section className="candidate-modal core-resolution-modal" role="dialog" aria-modal="true" aria-label="Resolver GTIN en lote" onClick={event=>event.stopPropagation()}>
        <div className="candidate-modal-header">
          <div><p className="eyebrow">ACCIÓN MASIVA</p><h3>Marcar {selectedGtinKeys.size.toLocaleString('es-AR')} productos como GTIN no aplica</h3><p>La decisión se guarda producto por producto, con la misma fuente, motivo e historial.</p></div>
          <button className="danger-outline" onClick={()=>setBulkGtinOpen(false)} disabled={bulkGtinBusy}>Cerrar</button>
        </div>
        {bulkGtinError&&<div className="notice warning">{bulkGtinError}</div>}
        <div className="notice warning"><strong>Confirmación importante.</strong><p>La detección de KIKI es una sugerencia por el título. Confirmá el lote solo si revisaste que todos son productos sueltos, a granel, fraccionados o presentaciones sin GTIN propio. La excepción todavía deberá ser compatible con la categoría de Mercado Libre.</p></div>
        <div className="bulk-preview-list">
          {suggestedExceptionItems.filter(item=>selectedGtinKeys.has(productKey(item))).slice(0,8).map(item=><span key={productKey(item)}>{item.product.name} · SKU {item.product.sku||item.product.sku_effective||'—'}</span>)}
          {selectedGtinKeys.size>8&&<small>+ {(selectedGtinKeys.size-8).toLocaleString('es-AR')} productos más</small>}
        </div>
        <div className="core-resolution-form">
          <label>Fuente común<input value={bulkGtinDraft.source_name} placeholder="Ej. catálogo/proveedor que respalda el criterio" onChange={event=>setBulkGtinDraft(current=>({...current,source_name:event.target.value}))}/></label>
          <label>URL de evidencia<input type="url" value={bulkGtinDraft.source_url} placeholder="https://…" onChange={event=>setBulkGtinDraft(current=>({...current,source_url:event.target.value}))}/></label>
          <label>Confianza<select value={bulkGtinDraft.confidence} onChange={event=>setBulkGtinDraft(current=>({...current,confidence:event.target.value as ExternalResearchConfidence}))}><option value="">Sin definir</option><option value="HIGH">Alta</option><option value="MEDIUM">Media</option></select></label>
          <label className="core-resolution-notes">Motivo común<textarea value={bulkGtinDraft.notes} placeholder="Ej. Productos comercializados sueltos/fraccionados por peso, sin GTIN propio para esta presentación." onChange={event=>setBulkGtinDraft(current=>({...current,notes:event.target.value}))}/></label>
        </div>
        <div className="core-resolution-actions">
          <button className="secondary" onClick={()=>setBulkGtinOpen(false)} disabled={bulkGtinBusy}>Cancelar</button>
          <button className="gtin-exception-action" onClick={()=>void saveBulkGtinExceptions()} disabled={bulkGtinBusy}>{bulkGtinBusy?'Aplicando…':`Confirmar ${selectedGtinKeys.size.toLocaleString('es-AR')} productos`}</button>
        </div>
      </section>
    </div>}

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

        {coreIssue==='EAN_MISSING'&&<div className="gtin-candidates">
          <button className="secondary" type="button" disabled={gtinBusy} onClick={()=>void findGtinSuggestions()}>{gtinBusy?'Buscando…':'Buscar EAN en KIKI'}</button>
          {gtinSuggestions&&<div><p>{gtinSuggestions.message}</p>
            {gtinSuggestions.candidates.map(candidate=><article key={candidate.ean}>
              <strong>GTIN candidato: {candidate.ean}</strong>
              <p>{candidate.matched_name} · SKU {candidate.matched_sku||'—'} · {candidate.matched_brand||'Marca desconocida'}</p>
              <small>{candidate.reason}</small>
              <button className="secondary" type="button" onClick={()=>setDraft(current=>({...current,proposed_ean:candidate.ean,confidence:'',source_name:'',source_url:''}))}>Usar como borrador</button>
            </article>)}
          </div>}
        </div>}
        {coreIssue==='EAN_MISSING'&&<div className="gtin-candidates">
          <button type="button" className="secondary" disabled={externalGtinBusy} onClick={()=>void findExternalGtin()}>{externalGtinBusy?'Buscando en fuente externa…':'Investigar EAN en Open Food Facts'}</button>
          <small>Base colaborativa de alimentos: las coincidencias son candidatas, no certificación de fabricante. La consulta se realiza solo al tocar el botón.</small>
          {externalGtin&&<div><p>{externalGtin.message}</p>
            {externalGtin.candidates.map(candidate=><article key={candidate.ean}>
              <strong>GTIN posible: {candidate.ean}</strong>
              <p>{candidate.matched_name} · {candidate.matched_brand||'Sin marca'} · {candidate.quantity||'Presentación no declarada'}</p>
              <small>{candidate.reason}</small>
              <a href={candidate.source_url} target="_blank" rel="noopener noreferrer">Ver ficha de origen ↗</a>
              <button className="secondary" type="button" onClick={()=>setDraft(current=>({...current,proposed_ean:candidate.ean,source_name:'',source_url:'',confidence:'',notes:'Candidato Open Food Facts: '+candidate.source_url+'. Verificar con fabricante antes de aceptar.'}))}>Copiar candidato a borrador (sin verificar)</button>
            </article>)}
          </div>}
        </div>}
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
          {coreIssue==='EAN_MISSING'&&<button className="gtin-exception-action" onClick={()=>void saveEvidence('GTIN_NOT_APPLICABLE')} disabled={evidenceBusy}>{evidenceBusy?'Guardando…':'No tiene GTIN / no aplica'}</button>}
          <button onClick={()=>void saveEvidence('EVIDENCE_ACCEPTED')} disabled={evidenceBusy}>{evidenceBusy?'Validando…':'Aceptar evidencia'}</button>
        </div>
      </section>
    </div>}
  </>;
}
function Pagination({page,total,pageSize,onChange}:{page:number;total:number;pageSize:number;onChange:(page:number)=>void}){
  const pages=Math.max(1,Math.ceil(total/pageSize));
  if(total<=pageSize)return null;
  const current=Math.min(page,pages);
  return <nav className="work-pagination" aria-label="Paginación de productos">
    <span>Mostrando {((current-1)*pageSize+1).toLocaleString('es-AR')}–{Math.min(current*pageSize,total).toLocaleString('es-AR')} de {total.toLocaleString('es-AR')} · Página {current} de {pages}</span>
    <div><button type="button" className="secondary" disabled={current===1} onClick={()=>onChange(current-1)}>← Anterior</button>
    <button type="button" className="secondary" disabled={current===pages} onClick={()=>onChange(current+1)}>Siguiente →</button></div>
  </nav>;
}


