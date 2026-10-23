import {useEffect,useMemo,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {GuidedBrandReview} from '../components/GuidedBrandReview';
import {GuidedCoreReview} from '../components/GuidedCoreReview';
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
  const [searchParams] = useSearchParams();
  const requestedFocus = searchParams.get('focus');
  const focus = ['data','brands','memory','ml','all'].includes(requestedFocus||'') ? requestedFocus : 'menu';
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
  const [coreIssue,setCoreIssue]=useState<CoreIssue>(searchParams.get('issue')==='ean'?'EAN_MISSING':'BRAND_MISSING');
  const [coreSearch,setCoreSearch]=useState('');
  const [corePage,setCorePage]=useState(1);
  const [brandPage,setBrandPage]=useState(1);
  const [guidedBrandMode,setGuidedBrandMode]=useState(true);
  const [guidedCoreMode,setGuidedCoreMode]=useState(true);
  const [verifiedPage,setVerifiedPage]=useState(1);
  const requestedProductSearch = searchParams.get('q')||'';
  useEffect(()=>{setCoreSearch(requestedProductSearch);setBrandPage(1);setVerifiedPage(1);},[requestedProductSearch,focus]);
  const requestedIssue=searchParams.get('issue');
  useEffect(()=>{setCoreIssue(requestedIssue==='ean'?'EAN_MISSING':'BRAND_MISSING');setCorePage(1)},[requestedIssue]);
  const PAGE_SIZE=50;
  const [likelyExceptionsOnly,setLikelyExceptionsOnly]=useState(false);
  const [resolutionItem,setResolutionItem]=useState<ReadinessItem|null>(null);
  const [draft,setDraft]=useState<EvidenceDraft>({...emptyDraft});
  const [evidenceBusy,setEvidenceBusy]=useState(false);
  const [evidenceError,setEvidenceError]=useState('');
  const [loading,setLoading]=useState(false);
  const [continuityBusy,setContinuityBusy]=useState('');
  const [decisionAudit,setDecisionAudit]=useState<{total:number;items:{product_key:string;product:{name?:string;sku?:string};status:string;proposed_brand?:string|null;note?:string|null;updated_at?:string|null;history:{status:string;at?:string;note?:string;reason?:string;action?:string}[]}[]}|null>(null);
  const [auditOpen,setAuditOpen]=useState(false);
  const [auditQuery,setAuditQuery]=useState('');
  const [auditBusy,setAuditBusy]=useState('');
  const [auditError,setAuditError]=useState('');
  const [brandProposals,setBrandProposals]=useState<EnrichmentReviewQueue|null>(null);
  const [selectedBrandKeys,setSelectedBrandKeys]=useState<Set<string>>(new Set());
  const [unbrandedKeys,setUnbrandedKeys]=useState<Set<string>>(new Set());
  const [showUnbrandedList,setShowUnbrandedList]=useState(true);
  const [unbrandedReason,setUnbrandedReason]=useState('Productos comercializados genéricos, sueltos o fraccionados sin marca comercial.');
  const [unbrandedBusy,setUnbrandedBusy]=useState(false);
  const [unbrandedError,setUnbrandedError]=useState('');
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
    const audit=await api.internalDecisionHistory().catch(()=>null);
    setDecisionAudit(audit);
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
    if(field==='BRAND_MISSING'&&(brandProposals?.items||[]).some(proposal=>proposal.product_key===key&&proposal.review_status==='BRAND_NOT_APPLICABLE'))return true;
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
    [rawBrandItems,researchByKey,brandProposals],
  );

  const likelyUnbranded=useMemo(()=>pendingBrandItems.filter(item=>
    /\b(SUELTO|SUELTA|GRANEL|FRACCIONAD[OA])\b/i.test(item.product.name||'')
  ),[pendingBrandItems]);

  async function confirmUnbranded(){
    const eligibleKeys=new Set(likelyUnbranded.map(productKey));
    const keys=[...unbrandedKeys].filter(key=>eligibleKeys.has(key));
    if(!keys.length)return;
    if(unbrandedReason.trim().length<15){setUnbrandedError('Explicá el motivo con al menos 15 caracteres.');return;}
    if(!window.confirm(`¿Confirmar que estos ${keys.length} productos no tienen marca comercial? Esta decisión no resuelve sus EAN ni autoriza publicarlos.`))return;
    setUnbrandedBusy(true);setUnbrandedError('');
    try{
      const result=await api.brandNotApplicable(keys,unbrandedReason.trim());
      setBrandProposals(await api.enrichmentReviewQueue());
      setUnbrandedKeys(new Set());
      setSuccess(`${result.processed} productos documentados como Marca no aplica. El EAN sigue pendiente cuando corresponda.`);
    }catch(err){setUnbrandedError(err instanceof Error?err.message:'No se guardó la excepción de marca.');}
    finally{setUnbrandedBusy(false);}
  }

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
    item.product.name,item.product.sku,item.product.sku_variant,item.product.sku_effective,item.internal_evidence.brand_candidate,
  ].some(value=>String(value||'').toLocaleLowerCase().includes(brandSearch))),[proposedBrands,brandSearch]);
  const filteredApprovedBrands=useMemo(()=>approvedBrandProposals.filter(item=>[
    item.product.name,item.product.sku,item.product.sku_variant,item.proposed_brand,
  ].some(value=>String(value||'').toLocaleLowerCase().includes(brandSearch))),[approvedBrandProposals,brandSearch]);
  const selectableBrands=useMemo(()=>filteredProposedBrands.filter(item=>["HIGH","MEDIUM"].includes(item.internal_evidence.confidence)),[filteredProposedBrands]);
  const highConfidenceBrands=useMemo(
    ()=>proposedBrands.filter(item=>item.internal_evidence.confidence==='HIGH'),
    [proposedBrands],
  );

  async function revokeAuditDecision(key:string){
    const reason=window.prompt('Motivo de la corrección (mínimo 10 caracteres):');
    if(reason===null)return;
    if(reason.trim().length<10){setAuditError('Escribí un motivo de al menos 10 caracteres.');return;}
    if(!window.confirm('¿Reabrir esta decisión de marca? La historia quedará conservada.'))return;
    setAuditBusy(key);setAuditError('');
    try{
      await api.revokeInternalDecision(key,reason.trim());
      const [audit,brands]=await Promise.all([api.internalDecisionHistory(),api.enrichmentReviewQueue()]);
      setDecisionAudit(audit);setBrandProposals(brands);
      setSuccess('La decisión volvió a revisión y conservó el historial.');
    }catch(err){setAuditError(err instanceof Error?err.message:'No se pudo corregir la decisión.');}
    finally{setAuditBusy('');}
  }

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
    const selected=proposedBrands.filter(item=>selectedBrandKeys.has(item.product_key));
    const high=selected.filter(item=>item.internal_evidence.confidence==='HIGH').length;
    const medium=selected.filter(item=>item.internal_evidence.confidence==='MEDIUM').length;
    if(selected.length!==keys.length){setBrandError('La selección contiene propuestas que ya no están pendientes. Actualizá la página.');return;}
    if(!window.confirm(`¿Aprobar ${keys.length} propuestas? Alta: ${high} · Media: ${medium}. Revisá especialmente las de confianza media. NO quedan verificadas para publicación.`))return;
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
      item.product.sku_variant,
      item.product.sku_effective,
      item.product.name,
      item.product.brand,
      item.product.ean,
    ].some(value=>String(value||'').toLowerCase().includes(term)));
  },[coreIssue,coreSearch,likelyExceptionsOnly,pendingEanItems,pendingBrandItems]);

  const brandCandidateKeys=useMemo(
    ()=>new Set((brandProposals?.items||[])
      .filter(item=>item.missing_fields.includes('Marca')&&Boolean(item.internal_evidence.brand_candidate))
      .map(item=>item.product_key)),
    [brandProposals],
  );
  const guidedCoreEntries=useMemo(()=>activeCoreItems.map((item,index)=>{
    const productIdentity=productKey(item);
    return {
      key:[productIdentity||`unidentified-row-${index}`,item.product.sku_variant||'',item.product.sku||'',item.product.ean||'',item.product.name||''].join('|'),
      item,
      hasBrandSuggestion:Boolean(productIdentity&&brandCandidateKeys.has(productIdentity)),
      researchStarted:Boolean(productIdentity&&researchByKey.get(productIdentity)),
    };
  }),[activeCoreItems,brandCandidateKeys,researchByKey]);

  const visibleBrandProposals=filteredProposedBrands.slice((brandPage-1)*PAGE_SIZE,brandPage*PAGE_SIZE);
  const visibleApprovedBrands=filteredApprovedBrands.slice((verifiedPage-1)*PAGE_SIZE,verifiedPage*PAGE_SIZE);
  const visibleCoreItems=activeCoreItems.slice((corePage-1)*PAGE_SIZE,corePage*PAGE_SIZE);
  const brandTotalPages=Math.max(1,Math.ceil(filteredProposedBrands.length/PAGE_SIZE));
  const verifiedTotalPages=Math.max(1,Math.ceil(filteredApprovedBrands.length/PAGE_SIZE));
  const coreTotalPages=Math.max(1,Math.ceil(activeCoreItems.length/PAGE_SIZE));
  useEffect(()=>setBrandPage(p=>Math.min(p,brandTotalPages)),[brandTotalPages]);
  useEffect(()=>setVerifiedPage(p=>Math.min(p,verifiedTotalPages)),[verifiedTotalPages]);
  useEffect(()=>setCorePage(p=>Math.min(p,coreTotalPages)),[coreTotalPages]);

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

  function verifyBrandProposal(item:EnrichmentReviewItem){
    const source=(data.readiness?.items||[]).find(row=>productKey(row)===item.product_key);
    if(!source){setBrandError('El producto ya no está disponible en el catálogo actual.');return;}
    setCoreIssue('BRAND_MISSING');
    openResolution(source);
    setDraft(current=>({...current,proposed_brand:item.proposed_brand||item.internal_evidence.brand_candidate||'',confidence:'',source_name:'',source_url:'',notes:''}));
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

  useEffect(()=>{
    if(focus==='brands'&&coreIssue!=='BRAND_MISSING'){
      setCoreIssue('BRAND_MISSING');
    }
  },[focus,coreIssue]);

  useEffect(()=>{
    if(loading||!data.readiness)return;
    if(focus!=='brands')return;
    const frame=window.requestAnimationFrame(()=>{
      document.getElementById('revisar-marcas')?.scrollIntoView({block:'start'});
    });
    return ()=>window.cancelAnimationFrame(frame);
  },[loading,data.readiness,focus,coreIssue]);

  return <>
    <header><div><p className="eyebrow">REVISIÓN DETALLADA</p><h1>Herramientas para resolver pendientes</h1><p>Acá están las funciones y decisiones detalladas del catálogo.</p><Link className="secondary-link" to="/work">← Volver al centro de tareas</Link></div></header>
    {error&&<div className="notice warning"><strong>{error}</strong><div style={{marginTop:10}}><button onClick={()=>void load()} disabled={loading}>{loading?'Reintentando…':'Reintentar conexión'}</button></div></div>}
    {success&&<div className="notice success">{success}</div>}

    <section className="kiki-review-picker" aria-label="Elegí el tipo de revisión">
      <div><p className="eyebrow">ELEGÍ QUÉ NECESITÁS HACER</p>
        <h2>{focus==='menu'?'Una tarea por vez.':focus==='data'?'Datos centrales':focus==='brands'?'Revisión de marcas':focus==='memory'?'Historial y decisiones':focus==='ml'?'Vinculaciones y preparación':'Todas las herramientas'}</h2>
        <p>No necesitás recorrer todos los controles: elegí una tarea y KIKI muestra las herramientas relacionadas. Los conteos pueden superponerse; no se suman como productos únicos.</p>
      </div>
      <nav aria-label="Tipos de revisión">
        <Link className={focus==='data'?'is-active':''} to="/work/details?focus=data">Datos centrales</Link>
        <Link className={focus==='brands'?'is-active':''} to="/work/details?focus=brands">Marcas</Link>
        <Link className={focus==='ml'?'is-active':''} to="/work/details?focus=ml">Mercado Libre</Link>
        <Link className={focus==='memory'?'is-active':''} to="/work/details?focus=memory">Historial</Link>
        <Link className={focus==='all'?'is-active':''} to="/work/details?focus=all">Ver todas</Link>
      </nav>
    </section>
    {focus==='menu'&&<p className="kiki-review-picker-hint">Para empezar, seleccioná uno de los temas de arriba. Las herramientas que ya conocés siguen disponibles y las decisiones guardadas no cambian.</p>}

    <div className={focus==='memory'||focus==='all'?'':'kiki-focus-hidden'}>
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

    <section className="panel decision-audit-panel">
      <div className="panel-title-row"><div><p className="eyebrow">MEMORIA DE KIKI</p><h2>Decisiones tomadas</h2><p>Consultá las marcas aprobadas como propuestas y los casos «Marca no aplica». Las decisiones internas no modifican Ecomm ni Mercado Libre.</p></div>
        <button className="secondary" onClick={()=>setAuditOpen(value=>!value)}>{auditOpen?'Ocultar decisiones':'Ver decisiones'} ({decisionAudit?.total??'—'})</button>
      </div>
      {auditOpen&&<>
        <input placeholder="Buscar producto, SKU o motivo" value={auditQuery} onChange={event=>setAuditQuery(event.target.value)}/>
        {auditError&&<div className="notice warning">{auditError}</div>}
        {decisionAudit===null?<p>No se pudo cargar el historial. Reintentá actualizar la página.</p>:
          <div className="decision-audit-list">{decisionAudit.items.filter(item=>[
            item.product?.name,item.product?.sku,item.note,item.proposed_brand,item.product_key,
          ].some(value=>String(value||'').toLocaleLowerCase().includes(auditQuery.toLocaleLowerCase()))).map(item=><article key={item.product_key}>
            <strong>{item.product?.name||item.product_key}</strong>
            <small>SKU {item.product?.sku||'—'} · {item.status==='BRAND_NOT_APPLICABLE'?'Marca no aplica':item.status==='APPROVED_PROPOSAL'?'Propuesta interna aprobada':item.status} · {item.updated_at?new Date(item.updated_at).toLocaleString('es-AR'):''}</small>
            {item.proposed_brand&&<p>Marca propuesta: {item.proposed_brand}</p>}
            {item.note&&<p>Motivo: {item.note}</p>}
            <details><summary>Ver historial ({item.history.length})</summary>{item.history.map((event,index)=><p key={index}>{event.at||''} · {event.status} · {event.reason||event.note||''}</p>)}</details>
            {['BRAND_NOT_APPLICABLE','APPROVED_PROPOSAL'].includes(item.status)&&<button className="secondary" disabled={Boolean(auditBusy)} onClick={()=>void revokeAuditDecision(item.product_key)}>Corregir decisión</button>}
          </article>)}</div>}
      </>}
    </section>
    </div>
    <div className={focus==='data'||focus==='brands'||focus==='all'?'':'kiki-focus-hidden'}>
    <section className={focus==='brands'?'panel core-pendings kiki-brand-only':'panel core-pendings'} id="datos-centrales">
      {focus==='brands'&&<div className="kiki-guided-brand-filter">
        <label>Buscar una candidata de marca<input type="search" value={coreSearch} onChange={event=>{setCoreSearch(event.target.value);setBrandPage(1);setVerifiedPage(1)}} placeholder="Producto, SKU o marca…" /></label>
        {coreSearch&&<button className="secondary" type="button" onClick={()=>{setCoreSearch('');setBrandPage(1);setVerifiedPage(1)}}>Mostrar todas las candidatas</button>}
      </div>}
      <div className="panel-title-row"><div><p className="eyebrow">DATOS PARA PUBLICAR</p><h2>{focus==='brands'?'Marcas pendientes de validación':'Completar datos centrales'}</h2><p>{focus==='brands'?'Revisá una marca propuesta, comprobá la fuente y avanzá al siguiente producto.':'Estos productos de Ecomm todavía no pueden avanzar porque les falta información básica. Acá ya podés resolver el dato, no solo verlo.'}</p></div></div>

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
      {focus==='data'&&<div className="kiki-data-mode-selector" role="group" aria-label="Forma de resolver los datos">
        <button type="button" className={guidedCoreMode?'is-active':''} aria-pressed={guidedCoreMode} onClick={()=>setGuidedCoreMode(true)}>Resolver de a uno</button>
        <button type="button" className={!guidedCoreMode?'is-active':''} aria-pressed={!guidedCoreMode} onClick={()=>setGuidedCoreMode(false)}>Ver lista y lotes</button>
      </div>}
      {focus==='data'&&guidedCoreMode&&!readinessAvailable&&<div className="notice warning" role="status">{loading?'Consultando productos pendientes…':'No se pudo consultar el catálogo de productos pendientes. Actualizá o reintentá más tarde; esto no significa que los pendientes sean cero.'}</div>}
      {focus==='data'&&guidedCoreMode&&readinessAvailable&&<GuidedCoreReview key={coreIssue} issue={coreIssue} entries={guidedCoreEntries} onResolve={openResolution} busy={evidenceBusy||brandBusy}/>}
      <div className={focus==='data'&&guidedCoreMode?'kiki-focus-hidden':''}>
      {coreIssue==='BRAND_MISSING'&&likelyUnbranded.length>0&&<section className="gtin-pilot-panel">
        <h3>Posibles productos sin marca comercial</h3>
        <p>KIKI detectó {likelyUnbranded.length} títulos con «suelto», «granel» o «fraccionado». Es solo una sugerencia: confirmá que se venden sin marca propia ni del proveedor.</p>
        <div className="bulk-selection-bar">
          <strong>{unbrandedKeys.size} seleccionados de {likelyUnbranded.length}</strong>
          <button className="secondary" disabled={unbrandedBusy} onClick={()=>setUnbrandedKeys(new Set(likelyUnbranded.slice(0,200).map(productKey).filter(Boolean)))}>Seleccionar {Math.min(200,likelyUnbranded.length)} sugeridos</button>
          <button className="secondary" disabled={unbrandedBusy} onClick={()=>setUnbrandedKeys(new Set())}>Limpiar</button>
        </div>
        <button type="button" className="secondary" onClick={()=>setShowUnbrandedList(value=>!value)}>{showUnbrandedList?'Ocultar lista':'Ver y revisar productos'} ({likelyUnbranded.length})</button>
        {showUnbrandedList&&<div className="unbranded-review-list">
          {likelyUnbranded.map(item=>{
            const key=productKey(item);
            return <label className="unbranded-review-row" key={key}>
              <input type="checkbox" disabled={unbrandedBusy} checked={unbrandedKeys.has(key)} onChange={event=>setUnbrandedKeys(current=>{
                const next=new Set(current);
                if(event.target.checked&&next.size<200)next.add(key);
                else if(!event.target.checked)next.delete(key);
                return next;
              })}/>
              <span><strong>{item.product.name||'Producto sin nombre'}</strong><small>SKU {item.product.sku||item.product.sku_effective||'—'} · Stock {item.product.stock??'—'}</small></span>
            </label>;
          })}
        </div>}
        {unbrandedKeys.size>0&&<div className="core-resolution-form">
          <label className="core-resolution-notes">Motivo que se guardará por producto<textarea value={unbrandedReason} onChange={event=>setUnbrandedReason(event.target.value)}/></label>
          <button disabled={unbrandedBusy} onClick={()=>void confirmUnbranded()}>Confirmar «Marca no aplica» ({unbrandedKeys.size})</button>
        </div>}
        {unbrandedError&&<div className="notice warning">{unbrandedError}</div>}
      </section>}
      {coreIssue==='BRAND_MISSING'&&<section className="core-brand-proposals" id="revisar-marcas">
        <div className="core-list-toolbar">
          <div><h3>Marcas sugeridas por KIKI</h3><p>Candidatas del catálogo interno, con evidencia y nivel de confianza. Aprobar una propuesta no equivale a verificarla ni habilita publicación.</p></div>
        </div>
        {brandError&&<div className="notice warning">{brandError}</div>}
        {brandProposals===null?<p>Las sugerencias no están disponibles en este momento.</p>:<>
          <p>{filteredProposedBrands.length} candidatas sin revisión inicial · {approvedBrandProposals.length} aceptadas internamente que aún necesitan fuente · {highConfidenceBrands.length} coincidencias de confianza alta en el catálogo, no verificadas externamente.</p>
          {focus==='brands'&&<div className="kiki-brand-mode-selector"><button type="button" className={guidedBrandMode?'is-active':''} aria-pressed={guidedBrandMode} onClick={()=>setGuidedBrandMode(true)}>Revisar de a una</button><button type="button" className={!guidedBrandMode?'is-active':''} aria-pressed={!guidedBrandMode} onClick={()=>setGuidedBrandMode(false)}>Ver lista y lotes</button></div>}
          {focus==='brands'&&guidedBrandMode&&<GuidedBrandReview items={filteredProposedBrands} busy={brandBusy||evidenceBusy} onVerify={verifyBrandProposal} onKeepCandidate={approveBrand}/>}
          {(focus!=='brands'||!guidedBrandMode)&&<>
          {selectableBrands.length>0&&<div className="bulk-selection-bar">
            <strong>{selectedBrandKeys.size} seleccionadas</strong>
            <button className="secondary" disabled={brandBusy} onClick={()=>setSelectedBrandKeys(new Set(selectableBrands.map(item=>item.product_key)))}>Seleccionar alta y media (filtradas)</button>
            <button className="secondary" disabled={brandBusy} onClick={()=>setSelectedBrandKeys(new Set())}>Limpiar</button>
            <button disabled={brandBusy||selectedBrandKeys.size===0} onClick={()=>void approveSelectedBrands()}>Aprobar propuestas seleccionadas</button>
          </div>}
          <div className="brand-proposal-list">
            {visibleBrandProposals.map(item=><article className="brand-proposal-card" key={item.product_key}>
              {['HIGH','MEDIUM'].includes(item.internal_evidence.confidence)&&<label className="core-select"><input type="checkbox" checked={selectedBrandKeys.has(item.product_key)} onChange={()=>setSelectedBrandKeys(current=>{const next=new Set(current);if(next.has(item.product_key))next.delete(item.product_key);else next.add(item.product_key);return next;})}/> Seleccionar</label>}
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
          </>}
          {approvedBrandProposals.length>0&&<section className="brand-verify-section">
            <h3>Propuestas aceptadas · falta verificar la fuente ({approvedBrandProposals.length})</h3>
            <p>Estas marcas fueron aprobadas como candidatas, pero aún no resuelven el pendiente. Revisá la ficha del fabricante o proveedor antes de confirmarlas.</p>
            <div className={focus==='brands'&&guidedBrandMode?'kiki-brand-approved-compact':'brand-proposal-list'}>{(focus==='brands'&&guidedBrandMode?visibleApprovedBrands.slice(0,3):visibleApprovedBrands).map(item=><article className="brand-proposal-card" key={item.product_key}>
              <div className="brand-proposal-details"><strong>{item.product.name||'Producto sin nombre'}</strong><div className="brand-proposal-meta"><span>Marca propuesta: <b>{item.proposed_brand}</b></span><span>Pendiente de fuente verificable</span></div></div>
              <button className="secondary" onClick={()=>verifyBrandProposal(item)}>Verificar marca</button>
            </article>)}</div>
            {(focus!=='brands'||!guidedBrandMode)&&<Pagination page={verifiedPage} total={filteredApprovedBrands.length} pageSize={PAGE_SIZE} onChange={setVerifiedPage}/>}
            {focus==='brands'&&guidedBrandMode&&approvedBrandProposals.length>3&&<button className="secondary" type="button" onClick={()=>setGuidedBrandMode(false)}>Ver todas las candidatas aceptadas ({approvedBrandProposals.length})</button>}
          </section>}
        </>}
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
            {coreIssue==='BRAND_MISSING'&&likelyUnbranded.some(candidate=>productKey(candidate)===key)&&<label className="core-select"><input type="checkbox" checked={unbrandedKeys.has(key)} onChange={()=>setUnbrandedKeys(previous=>{const next=new Set(previous);if(next.has(key))next.delete(key);else next.add(key);return next;})}/><span>Sin marca</span></label>}
            {selectable&&<label className="core-select"><input type="checkbox" checked={selectedGtinKeys.has(key)} onChange={()=>toggleGtinSelection(key)}/><span>Seleccionar</span></label>}
            <div><strong>{item.product.name||'Producto sin nombre'}</strong><small>SKU {item.product.sku||item.product.sku_effective||'—'} · Stock {item.product.stock??'—'}{item.product.brand?` · Marca ${item.product.brand}`:''}</small><div className="core-row-badges">{coreIssue==='EAN_MISSING'&&likelyGtinException(item)&&<span className="core-suggestion-badge">Posible excepción GTIN</span>}{research&&!['EVIDENCE_ACCEPTED','GTIN_NOT_APPLICABLE'].includes(research.research_status)&&<span className="core-draft-badge">Investigación iniciada</span>}</div></div>
            <button onClick={()=>openResolution(item)}>{research?'Continuar':'Resolver'} {coreIssue==='EAN_MISSING'?'EAN':'marca'}</button>
          </article>;
        })}
        {activeCoreItems.length===0&&<div className="prepub-empty"><strong>No quedan productos pendientes para este control.</strong></div>}
      </div><Pagination page={corePage} total={activeCoreItems.length} pageSize={PAGE_SIZE} onChange={setCorePage}/></>}
      </div>
    </section>

    </div>
    <div className={focus==='ml'||focus==='all'?'':'kiki-focus-hidden'}>
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
        <Link className="guided-link" to="/prepublication">Revisar preparación ML</Link>
      </article>
    </section>

    <section className="panel guided-help">
      <h2>Regla simple</h2>
      <p><strong>Si ya existe en Mercado Libre:</strong> trabajalo en “Vincular con ML”. <strong>Si todavía no existe:</strong> completá sus datos y trabajalo en “Preparar para ML” (sin publicar automáticamente).</p>
    </section>

    </div>
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
          <p>Confirmá marca, presentación y fuente verificable antes de aceptar. KIKI conserva la evidencia y no modifica Ecomm-App ni Mercado Libre.</p>
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


