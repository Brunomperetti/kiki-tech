import type {Listing,Product} from './catalog';

export type DuplicateReviewDecision='PENDING'|'DUPLICATE_CONFIRMED'|'DISTINCT_PRODUCTS'|'VARIANTS';

export interface DuplicateReviewProduct {
  product_key:string;
  product:Product & {sku_aliases?:string[];ean_aliases?:string[]};
  listing:Listing & {ean?:string;price?:number};
  matched_listing_count:number;
  matched_listing_ids:string[];
  match_method?:string;
  reason?:string;
}

export interface DuplicateReviewHistoryEntry {
  decision:DuplicateReviewDecision;
  at:string;
  note?:string|null;
  shared_identifiers?:string[];
  product_keys?:string[];
}

export interface SkuFamilyPair {
  sku_a:string;
  sku_b:string;
  rule:'SAME_SKU'|'PREFIX_4'|'PREFIX_3'|'PREFIX_2_SPECIAL'|'NO_RULE'|'NOT_NUMERIC';
  related:boolean;
  explanation:string;
}

export interface SkuFamilyDiagnosis {
  status:'FAMILY_CANDIDATE'|'REVIEW_REQUIRED';
  headline:string;
  matches:number;
  comparisons:number;
  pairs:SkuFamilyPair[];
  policy:string;
}

export interface DuplicateReviewGroup {
  group_key:string;
  family_diagnosis?:SkuFamilyDiagnosis;
  shared_identifiers:string[];
  product_keys:string[];
  products:DuplicateReviewProduct[];
  review_decision:DuplicateReviewDecision;
  note?:string|null;
  updated_at?:string|null;
  history:DuplicateReviewHistoryEntry[];
  history_count:number;
}

export interface DuplicateReviewQueue {
  reconciliation_run_id:number;
  summary:{
    groups_total:number;
    products_affected:number;
    PENDING:number;
    DUPLICATE_CONFIRMED:number;
    DISTINCT_PRODUCTS:number;
    VARIANTS:number;
  };
  policy:{mode:string;description:string};
  items:DuplicateReviewGroup[];
}
