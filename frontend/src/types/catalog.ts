export type Status='ALREADY_PUBLISHED'|'CANDIDATE_TO_PUBLISH'|'REVIEW_REQUIRED'|'POSSIBLE_DUPLICATE'|'INCOMPLETE_DATA'|'INVALID_SKU'|'INVALID_EAN'|'UNMATCHED_ML_LISTING';
export interface Product {sku?:string;ean?:string;name?:string;stock?:number;price?:number}
export interface Listing {external_id?:string;status?:string;sku?:string;title?:string;url?:string;inventory_linked?:string}
export interface Result {product?:Product;listing?:Listing;matched_listing_count:number;matched_listing_ids:string[];multiple_ml_listings:boolean;status:Status;reason:string;confidence:number;match_method:string;issues:{severity:string;message:string}[]}
export interface ImportDiagnostics {source:string;filename:string;rows_read:number;rows_accepted:number;rows_discarded:number;header_row:number;recognized_columns:Record<string,string>;ignored_columns:string[];warnings:string[];canonical_products?:number;grouped_rows?:number;associated_rows?:number;conflicts?:string[]}
export interface Summary {total_products:number;total_listings:number;total_ecomm_rows?:number;total_ecomm_associated_rows?:number;import_diagnostics?:ImportDiagnostics[];[key:string]:number|ImportDiagnostics[]|undefined}
export interface ImportJob {id:number;filename:string;source:string;started_at:string;records:number;processed:number;errors:number;status:string;unknown_columns:string[];diagnostics:ImportDiagnostics}
