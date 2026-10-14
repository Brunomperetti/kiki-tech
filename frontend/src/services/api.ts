import type {BulkGtinNotApplicablePayload, BulkGtinNotApplicableResult, CatalogContinuityDecision, CatalogContinuityItem, CatalogContinuityReport, EnrichmentReport, EnrichmentReviewItem, EnrichmentReviewQueue, EnrichmentReviewStatus, ExternalResearchItem, ExternalResearchPayload, ExternalResearchQueue, FinalPublicationQueueItem, FinalPublicationQueueReport, ImportJob, InventoryLinkageCandidateResponse, InventoryLinkageItem, InventoryLinkageReport, MercadoLibreStatus, MetadataBatchResult, PrepublicationImageItem, PrepublicationImagePayload, PrepublicationImageQueue, PrepublicationMetadataItem, PrepublicationMetadataPayload, PrepublicationMetadataQueue, PrepublicationReport, ReadinessReport, Result, Summary} from '../types/catalog';
import type {ReconciliationReviewDecision, ReconciliationReviewItem, ReconciliationReviewQueue} from '../types/reconciliation-review';
import type {DuplicateReviewDecision, DuplicateReviewGroup, DuplicateReviewQueue} from '../types/duplicate-review';

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
