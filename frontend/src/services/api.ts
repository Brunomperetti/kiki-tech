import type {BulkGtinNotApplicablePayload, BulkGtinNotApplicableResult, CatalogContinuityDecision, CatalogContinuityItem, CatalogContinuityReport, EnrichmentReport, EnrichmentReviewItem, EnrichmentReviewQueue, EnrichmentReviewStatus, ExternalResearchItem, ExternalResearchPayload, ExternalResearchQueue, FinalPublicationQueueItem, FinalPublicationQueueReport, ImportJob, InventoryLinkageCandidateResponse, InventoryLinkageItem, InventoryLinkageReport, MercadoLibreStatus, MetadataBatchResult, PrepublicationImageItem, PrepublicationImagePayload, PrepublicationImageQueue, PrepublicationMetadataItem, PrepublicationMetadataPayload, PrepublicationMetadataQueue, PrepublicationReport, ReadinessReport, Result, Summary} from '../types/catalog';
import type {ReconciliationReviewDecision, ReconciliationReviewItem, ReconciliationReviewQueue} from '../types/reconciliation-review';
import type {DuplicateReviewDecision, DuplicateReviewGroup, DuplicateReviewQueue} from '../types/duplicate-review';
import type {EcommAppStatus,EcommAppPreview,EcommAppLookup,EcommCatalogAudit,EcommStageStatus} from '../types/ecomm-app';

const base = import.meta.env.DEV
  ? (import.meta.env.VITE_API_URL || 'http://localhost:8000')
  : '';
let csrfToken = '';

type AuthResponse = {authenticated: boolean; username: string; csrf_token: string};

function sleep(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (method !== 'GET' && method !== 'HEAD' && path !== '/api/auth/login') {
    headers.set('X-CSRF-Token', csrfToken);
  }

  const attempts = method === 'GET' || method === 'HEAD' ? 3 : 1;
  let lastNetworkError: unknown = null;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(`${base}${path}`, {...options, headers, credentials: 'include'});
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || 'No pudimos completar la operación.');
      }
      return response.json();
    } catch (error) {
      const isNetworkFailure = error instanceof TypeError;
      if (!isNetworkFailure || attempt === attempts) {
        if (isNetworkFailure) {
          throw new Error('No pudimos conectar con el servidor de KIKI. Esperá unos segundos y reintentá.');
        }
        throw error;
      }
      lastNetworkError = error;
      await sleep(attempt * 1200);
    }
  }

  throw lastNetworkError instanceof Error
    ? lastNetworkError
    : new Error('No pudimos conectar con el servidor de KIKI.');
}

function rememberAuth(auth: AuthResponse): AuthResponse {
  csrfToken = auth.csrf_token;
  return auth;
}

export type TiendanubeAiEditorialDraft = {
  draft_id: number;
  product_key: string;
  original_name: string;
  title: string;
  description: string;
  questions: string[];
  evidence: {field:string;value:string;source:string}[];
  status: string;
  review_status: 'PENDING_REVIEW'|'APPROVED_INTERNAL'|'REJECTED_INTERNAL';
  review_note: string;
  history: {event:string;at:string;note:string}[];
  source_current: boolean;
  model: string;
  created_at: string|null;
  policy: string;
};

export const api = {
  me: () => request<AuthResponse>('/api/auth/me').then(rememberAuth),
  login: (username: string, password: string) => request<AuthResponse>('/api/auth/login', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password}),
  }).then(rememberAuth),
  logout: () => request<{authenticated: boolean}>('/api/auth/logout', {method: 'POST'}).finally(() => { csrfToken = ''; }),
  dashboard: () => request<Summary>('/api/dashboard'),
  products: (query = '') => request<Result[]>(`/api/products${query}`),
  reconciliationReviewQueue: () => request<ReconciliationReviewQueue>('/api/reconciliation-review'),
  saveReconciliationReviewDecision: (productKey: string, decision: ReconciliationReviewDecision, note?: string) => request<ReconciliationReviewItem>('/api/reconciliation-review', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({product_key: productKey, decision, note: note || null}),
  }),
  duplicateReviewQueue: () => request<DuplicateReviewQueue>('/api/duplicate-review'),
  saveDuplicateReviewDecision: (groupKey: string, decision: DuplicateReviewDecision, note?: string) => request<DuplicateReviewGroup>('/api/duplicate-review', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({group_key: groupKey, decision, note: note || null}),
  }),
  saveDuplicateVariantsBatch: (groupKeys:string[],reconciliationRunId:number,note:string)=>request<{updated:number;group_keys:string[];decision:'VARIANTS';policy:string}>('/api/duplicate-review/variants-batch',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({group_keys:groupKeys,reconciliation_run_id:reconciliationRunId,note,confirmed:true}),
  }),
  publicationReadiness: () => request<ReadinessReport>('/api/publication-readiness'),
  catalogContinuity: () => request<CatalogContinuityReport>('/api/catalog-continuity'),
  saveCatalogContinuityDecision: (conflictKey: string, decision: CatalogContinuityDecision, note?: string) => request<CatalogContinuityItem>('/api/catalog-continuity/decision', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({conflict_key: conflictKey, decision, note: note || null}),
  }),
  inventoryLinkage: () => request<InventoryLinkageReport>('/api/inventory-linkage'),
  saveInventoryLinkageDecision: (externalId: string, decision: 'CONFIRMED'|'REJECTED', ecommId: string, note?: string) => request<InventoryLinkageItem>('/api/inventory-linkage/decision', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({external_id: externalId, decision, ecomm_id: ecommId, note: note || null}),
  }),
  inventoryLinkageCandidates: (externalId: string, search = '', limit = 8) => request<InventoryLinkageCandidateResponse>(`/api/inventory-linkage/candidates?external_id=${encodeURIComponent(externalId)}&search=${encodeURIComponent(search)}&limit=${limit}`),
  saveInventoryManualAssignment: (externalId: string, ecommId: string, note?: string) => request<InventoryLinkageItem>('/api/inventory-linkage/manual-assignment', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({external_id: externalId, ecomm_id: ecommId, note: note || null}),
  }),
  markInventoryPendingEcomm: (externalId: string, note?: string) => request<InventoryLinkageItem>('/api/inventory-linkage/pending-ecomm', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({external_id: externalId, note: note || null}),
  }),
  saveInventoryEcommAction: (externalId: string, action: string, note?: string) => request<InventoryLinkageItem>('/api/inventory-linkage/ecomm-action', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({external_id: externalId, action, note: note || null}),
  }),
  enrichmentPilot: (limit = 20) => request<EnrichmentReport>(`/api/enrichment-pilot?limit=${limit}`),
  bulkApproveBrandProposals: (product_keys:string[]) => request<{requested:number;processed:number;status:string}>('/api/enrichment-review-decisions/bulk-brand', {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_keys}),
  }),
  brandNotApplicable: (product_keys:string[],reason:string) => request<{requested:number;processed:number;status:string}>('/api/enrichment-review-decisions/brand-not-applicable',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_keys,reason}),
  }),
  internalDecisionHistory: () => request<{total:number;items:{product_key:string;product:{name?:string;sku?:string};status:string;proposed_brand?:string|null;note?:string|null;updated_at?:string|null;history:{status:string;at?:string;note?:string;reason?:string;action?:string}[]}[]}>('/api/enrichment-decisions/history'),
  revokeInternalDecision: (product_key:string,reason:string) => request<{product_key:string;status:string;previous_status:string}>('/api/enrichment-decisions/revoke',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_key,reason}),
  }),
  enrichmentReviewQueue: () => request<EnrichmentReviewQueue>('/api/enrichment-review-queue'),
  saveEnrichmentDecision: (productKey: string, status: EnrichmentReviewStatus, note?: string) => request<EnrichmentReviewItem>('/api/enrichment-review-decisions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({product_key: productKey, status, note: note || null}),
  }),
  gtinCandidates: (key:string) => request<{candidates:{ean:string;matched_name:string;matched_sku?:string;matched_brand?:string;reason:string}[];message:string}>(`/api/gtin-candidates/${encodeURIComponent(key)}`),
  gtinBatchPilot: (product_keys:string[]) => request<{requested:number;external_checked:number;summary:Record<string,number>;items:{product_key:string;product_name?:string;sku?:string;status:string;candidates:{ean:string;source_url?:string;matched_name?:string}[];external_message?:string}[]}>('/api/gtin-batch-pilot',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_keys}),
  }),
  externalGtinCandidates: (key:string) => request<{candidates:{ean:string;matched_name:string;matched_brand:string;quantity:string;source_name:string;source_url:string;reason:string}[];message:string;unavailable?:boolean}>(`/api/external-gtin-candidates/${encodeURIComponent(key)}`),
  externalResearchQueue: () => request<ExternalResearchQueue>('/api/enrichment-external-research'),
  saveExternalResearch: (payload: ExternalResearchPayload) => request<ExternalResearchItem>('/api/enrichment-external-research', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }),
  bulkMarkGtinNotApplicable: (payload: BulkGtinNotApplicablePayload) => request<BulkGtinNotApplicableResult>('/api/enrichment-external-research/bulk-gtin-not-applicable', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }),
  prepublication: () => request<PrepublicationReport>('/api/prepublication'),
  finalPublicationQueue: () => request<FinalPublicationQueueReport>('/api/prepublication/final-queue'),
  saveFinalPublicationApproval: (productKey: string, action: 'APPROVE'|'REVOKE', note?: string) => request<FinalPublicationQueueItem>('/api/prepublication/final-queue', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({product_key: productKey, action, note: note || null}),
  }),
  prepublicationMetadata: () => request<PrepublicationMetadataQueue>('/api/prepublication/metadata'),
  analyzePrepublicationMetadata: (productKey: string) => request<PrepublicationMetadataItem>('/api/prepublication/metadata/analyze', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({product_key: productKey}),
  }),
  validateConditionalMetadata: (productKey: string) => request<PrepublicationMetadataItem>('/api/prepublication/metadata/validate-conditional', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({product_key: productKey}),
  }),
  analyzePendingMetadata: (limit = 10) => request<MetadataBatchResult>('/api/prepublication/metadata/analyze-pending', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({limit}),
  }),
  savePrepublicationMetadata: (payload: PrepublicationMetadataPayload) => request<PrepublicationMetadataItem>('/api/prepublication/metadata', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }),
  prepublicationImages: () => request<PrepublicationImageQueue>('/api/prepublication/images'),
  savePrepublicationImages: (payload: PrepublicationImagePayload) => request<PrepublicationImageItem>('/api/prepublication/images', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  }),
  tiendanubeBulkPreview: (source_keys:string[]) => request<{count:number;items:{source_key:string;name:string;sku:string;candidate_count:number}[];action:string;policy:string}>('/api/tiendanube/matches/bulk-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_keys})}),
  tiendanubeBulkReject: (source_keys:string[],note:string) => request<{updated:number;status:string;policy:string}>('/api/tiendanube/matches/bulk-reject',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_keys,note})}),
  tiendanubeMatchDecision: (source_key:string,status:'APPROVED'|'REJECTED',target_ecomm_id:string|null,note:string) => request<{status:string;source_key:string;history_count:number}>('/api/tiendanube/match-decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_key,status,target_ecomm_id,note})}),
  tiendanubeAiDraft: (product_key:string) => request<TiendanubeAiEditorialDraft>('/api/tiendanube/ai/draft',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_key})}),
  tiendanubeAiSaved: (product_key:string) => request<{available:boolean;draft:TiendanubeAiEditorialDraft|null}>('/api/tiendanube/ai/saved?product_key='+encodeURIComponent(product_key)),
  tiendanubeAiReview: (draft_id:number,action:'APPROVE'|'REJECT',note:string) => request<TiendanubeAiEditorialDraft>('/api/tiendanube/ai/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({draft_id,action,note,confirmed:true})}),
  tiendanubeAiOfflinePreview: (product_key:string) => request<{product_key:string;original_title:string;title:string;description:string;questions:string[];evidence:{field:string;value:string;source:string}[];status:string;policy:string}>('/api/tiendanube/ai/offline-preview?product_key='+encodeURIComponent(product_key)),
  tiendanubeSeoGuidelineAudit: (product_key:string) => request<{product_key:string;audit:{alerts:{field:string;reason:string}[];missing:string[];description_words:number;status:string;policy:string};source:string;policy:string}>('/api/tiendanube/seo-guideline-audit?product_key='+encodeURIComponent(product_key)),
  tiendanubeCommercialProposals: () => request<{available:boolean;summary:{proposals:number;title_suggestions:number;description_research_needed:number};items:{product_key:string;original_name:string;proposed_title:string;title_changed:boolean;brand_review_required:boolean;review_type:string;other_brands_in_title:string[];description_action:string;verified_product_facts:{field:string;value:string;source:string}[];reasons:string[];status:string}[];policy:string}>('/api/tiendanube/commercial-proposals'),
  tiendanubeAssistedMatches: () => request<{available:boolean;summary:{sku_unmatched:number;with_proposals:number;without_proposals:number};items:{tiendanube_sku:string;tiendanube_name:string;tiendanube_brand:string;tiendanube_slug:string;source_key:string;decision:{status:string;target_ecomm_id:string|null;note:string;history:{at:string;status:string;note:string;target_ecomm_id:string|null}[]}|null;status:string;candidates:{ecomm_id:string;sku:string;name:string;brand:string;similarity:number;confidence:string;evidence:string}[]}[];policy?:string}>('/api/tiendanube/assisted-matches'),
  tiendanubeDuplicateSkus: () => request<{available:boolean;summary:Record<string,number>;groups:{sku:string;count:number;status:string;reason:string;items:{name:string;slug:string;sku:string;variant:{property:string;value:string}[];stock:string|null;price:string|null}[]}[];policy?:string}>('/api/tiendanube/duplicate-skus'),
  tiendanubePriceStockAudit: () => request<{available:boolean;summary:Record<string,number>;ml_available?:boolean;ml_source?:string|null;ml_snapshot_at?:string|null;items:{sku:string;name:string;ecomm_id:string;tiendanube_price:string|null;ecomm_list_price:string|null;price_difference:string|null;tiendanube_stock:string|null;ecomm_stock:string|null;stock_difference:string|null;price_state:string;stock_state:string;ml_status?:string;ml_status_label?:string;ml_listing_count?:number;ml_listing_ids?:string[];ml_offers?:{external_id:string;title:string;price:string|null;listing_status:string}[];ml_price?:string|null;ml_stock?:number|null}[];policy?:string}>('/api/tiendanube/price-stock-audit'),
  tiendanubeQualityAudit: () => request<{available:boolean;summary:Record<string,number>;items:{key:string;name:string;sku:string;variant_rows:number;issues:string[];priority:string;image_status:string;gtin_conflicts?:{gtin:string;occurrences:number;repeated_within_product:boolean;other_products:{key:string;name:string;sku:string;brand:string;variant:{property:string;value:string}[]}[]}[]}[];policy?:string}>('/api/tiendanube/quality-audit'),
  tiendanubeImageAudit: () => request<{available:boolean;summary:Record<string,number>;items:{product_id:string;name:string;sku:string;status:string;image_count:number;image_urls:string[];tiendanube_slug:string|null}[];policy?:string}>('/api/tiendanube/images/audit'),
  uploadTiendanubeImages: (file:File) => {const form=new FormData();form.append('file',file);return request<{images:number;product_ids:number;policy:string}>('/api/tiendanube/images/import-csv',{method:'POST',body:form})},
  tiendanubeReport: () => request<{available:boolean;summary:Record<string,number>;items:{slug:string;name:string;sku:string;ean_raw:string;brand:string;price:string|null;stock:string|null;status:string;matched_ecomm_id:string|null}[];policy?:string}>('/api/tiendanube/reconciliation'),
  uploadTiendanube: (file:File) => {const form=new FormData();form.append('file',file);return request<{records:number;products:number;status:string}>('/api/tiendanube/import-csv',{method:'POST',body:form});},
  ecommAppStatus: () => request<EcommAppStatus>('/api/ecomm-app/status'),
  ecommAppPreview: () => request<EcommAppPreview>('/api/ecomm-app/preview',{method:'POST'}),
  ecommAppLookup: (skus:string[]) => request<EcommAppLookup>('/api/ecomm-app/lookup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({skus})}),
  ecommAppCatalogAudit: (startPage:number) => request<EcommCatalogAudit>('/api/ecomm-app/catalog-audit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start_page:startPage})}),
  ecommStageStatus: () => request<EcommStageStatus>('/api/ecomm-app/stage/status'),
  ecommStageNext: () => request<EcommStageStatus>('/api/ecomm-app/stage/next',{method:'POST'}),
  imports: () => request<ImportJob[]>('/api/imports'),
  analyze: (source = 'AUTO') => request<unknown>(`/api/reconciliations?ml_source=${source}`, {method: 'POST'}),
  mlStatus: () => request<MercadoLibreStatus>('/api/mercadolibre/status'),
  mlAuthUrl: () => request<{url: string}>('/api/mercadolibre/auth-url', {method: 'POST'}),
  mlSync: () => request<{listing_count: number; synced_at: string}>('/api/mercadolibre/sync', {method: 'POST'}),
  upload: (source: string, file: File) => {
    const data = new FormData(); data.append('file', file);
    return request(`/api/imports/${source}`, {method: 'POST', body: data});
  },
};
