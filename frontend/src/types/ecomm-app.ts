export interface EcommAppStatus {
  configured:boolean;
  mode:'READ_ONLY';
  scope_required:string;
  description:string;
}

export interface EcommAppPreviewList {
  shape_recognized:boolean;
  count:number|null;
  envelope_keys:string[];
  warning:string|null;
  samples:{
    id?:string|number|null;
    name?:string|null;
    code?:string|null;
    description?:string|null;
    variant_count?:number;
    available_fields:string[];
    variants?:{
      sku?:string|null;
      barcode?:string|null;
      total_stock?:number|string|null;
      available_fields:string[];
      warehouse_sample:{id?:number|string|null;stock?:number|string|null}[];
    }[];
  }[];
}
export interface EcommAppPreview {
  connected:true;
  mode:'READ_ONLY_PREVIEW';
  warehouse_preview:EcommAppPreviewList;
  product_preview:EcommAppPreviewList;
  note:string;
}
export interface EcommAppLookup {
  mode:'READ_ONLY_SKU_LOOKUP';
  requested_skus:string[];
  product_preview:EcommAppPreviewList;
  note:string;
}
