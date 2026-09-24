export type Status='ALREADY_PUBLISHED'|'CANDIDATE_TO_PUBLISH'|'REVIEW_REQUIRED'|'POSSIBLE_DUPLICATE'|'INCOMPLETE_DATA'|'INVALID_SKU'|'INVALID_EAN'|'UNMATCHED_ML_LISTING';
export interface Product {sku?:string;ean?:string;name?:string;stock?:number;price?:number}
export interface Listing {external_id?:string;title?:string;url?:string}
export interface Result {product?:Product;listing?:Listing;status:Status;reason:string;confidence:number;match_method:string;issues:{severity:string;message:string}[]}
export interface Summary {total_products:number;total_listings:number;[key:string]:number}
export interface ImportJob {id:number;filename:string;source:string;started_at:string;records:number;processed:number;errors:number;status:string;unknown_columns:string[]}
