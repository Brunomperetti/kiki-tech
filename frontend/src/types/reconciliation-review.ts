import type {Listing, Product} from './catalog';

export type ReconciliationReviewDecision='PENDING'|'CONFIRMED_MATCH'|'NOT_MATCH';

export interface ReconciliationReviewHistoryEntry {
  decision: ReconciliationReviewDecision;
  at: string;
  note?: string|null;
  reason?: string|null;
  matched_listing_ids?: string[];
}

export interface ReconciliationReviewItem {
  product_key: string;
  product: Product;
  listing: Listing;
  matched_listing_count: number;
  matched_listing_ids: string[];
  match_method?: string|null;
  confidence?: number|null;
  reason?: string|null;
  review_decision: ReconciliationReviewDecision;
  note?: string|null;
  updated_at?: string|null;
  history: ReconciliationReviewHistoryEntry[];
  history_count: number;
}

export interface ReconciliationReviewQueue {
  reconciliation_run_id: number;
  summary: {
    total: number;
    PENDING: number;
    CONFIRMED_MATCH: number;
    NOT_MATCH: number;
  };
  policy: {mode: string; description: string};
  items: ReconciliationReviewItem[];
}
