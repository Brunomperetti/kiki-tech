export type Status='ALREADY_PUBLISHED'|'CANDIDATE_TO_PUBLISH'|'REVIEW_REQUIRED'|'POSSIBLE_DUPLICATE'|'INCOMPLETE_DATA'|'INVALID_SKU'|'INVALID_EAN'|'UNMATCHED_ML_LISTING';
export interface Product {sku?:string;ean?:string;brand?:string;name?:string;stock?:number;price?:number}
export interface Listing {external_id?:string;status?:string;sku?:string;title?:string;url?:string;inventory_linked?:string}
export interface Result {product?:Product;listing?:Listing;matched_listing_count:number;matched_listing_ids:string[];multiple_ml_listings:boolean;status:Status;reason:string;confidence:number;match_method:string;issues:{severity:string;message:string}[]}
export interface ImportDiagnostics {source:string;filename:string;rows_read:number;rows_accepted:number;rows_discarded:number;header_row:number;recognized_columns:Record<string,string>;ignored_columns:string[];warnings:string[];canonical_products?:number;grouped_rows?:number;associated_rows?:number;conflicts?:string[]}
export interface Summary {total_products:number;total_listings:number;total_ecomm_rows?:number;total_ecomm_associated_rows?:number;mercadolibre_source?:string;import_diagnostics?:ImportDiagnostics[];[key:string]:number|string|ImportDiagnostics[]|undefined}
export interface ImportJob {id:number;filename:string;source:string;started_at:string;records:number;processed:number;errors:number;status:string;unknown_columns:string[];diagnostics:ImportDiagnostics}
export interface MercadoLibreStatus {connected:boolean;user_id?:string;token_expiration?:string;token_expired:boolean;last_sync?:string;listing_count:number}
export type ReadinessStatus='READY_CORE_DATA'|'REVIEW_REQUIRED'|'BLOCKED'|'NO_STOCK'|'ALREADY_PUBLISHED';
export interface ReadinessItem {product:Product;reconciliation_status:Status;readiness_status:ReadinessStatus;reason_codes:string[];reasons:string[];issues:{severity:string;code?:string;message:string}[];matched_listing_ids:string[]}
export interface ReadinessReasonSummary {code:string;label:string;count:number}
export interface ReadinessReport {reconciliation_run_id:number;mercadolibre_source?:string;summary:{total_products:number;actionable_with_stock:number;READY_CORE_DATA:number;REVIEW_REQUIRED:number;BLOCKED:number;NO_STOCK:number;ALREADY_PUBLISHED:number};reason_summary:ReadinessReasonSummary[];pending_external_checks:string[];items:ReadinessItem[]}
export type EnrichmentResearchStatus='PENDING_RESEARCH';
export interface EnrichmentProposal {ean?:string|null;brand?:string|null;source_name?:string|null;source_url?:string|null;confidence?:string|null;notes?:string|null}
export interface EnrichmentItem {product:Product;readiness_status:ReadinessStatus;reason_codes:string[];missing_fields:string[];research_status:EnrichmentResearchStatus;proposal:EnrichmentProposal}
export interface EnrichmentReport {reconciliation_run_id:number;mercadolibre_source?:string;summary:{total_eligible:number;missing_ean:number;missing_brand:number;missing_both:number;pilot_size:number;pilot_limit:number};policy:{mode:string;description:string};items:EnrichmentItem[]}
