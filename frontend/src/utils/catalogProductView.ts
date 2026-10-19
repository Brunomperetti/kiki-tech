import type {Product,Result} from '../types/catalog';

export type TiendanubeCatalogRow = {
  slug:string;
  name:string;
  sku:string;
  ean_raw:string;
  brand:string;
  price:string|null;
  stock:string|null;
  status:string;
  matched_ecomm_id:string|null;
};

export type TiendanubeCandidate = {
  state:'NO_ECOMM_PRODUCT'|'NOT_AVAILABLE'|'NO_EXACT_MATCH'|'AMBIGUOUS'|'POSSIBLE';
  item:TiendanubeCatalogRow|null;
  detail:string;
};

/** A matching SKU in a CSV is evidence to review, NOT a confirmed channel link. */
export function tiendanubeCandidate(
  product:Product|undefined,
  available:boolean,
  rows:TiendanubeCatalogRow[],
):TiendanubeCandidate {
  if(!product)return {state:'NO_ECOMM_PRODUCT',item:null,detail:'Esta fila todavía no tiene un producto Ecomm asociado.'};
  if(!available)return {state:'NOT_AVAILABLE',item:null,detail:'Todavía no se pudo consultar el CSV de Tiendanube.'};
  const id=String(product.ecomm_id||'').trim();
  const normalized=(value:unknown)=>String(value||'').trim().toLocaleLowerCase('es');
  const skus=new Set([product.sku_variant,product.sku_effective,product.sku].map(normalized).filter(Boolean));
  if(!id||!skus.size)return {state:'NO_EXACT_MATCH',item:null,detail:'Falta un ID Ecomm o SKU de producto suficientemente claro para cruzar los datos con seguridad.'};

  const sameSku=rows.filter(row=>skus.has(normalized(row.sku)));
  if(sameSku.length>1){
    return {state:'AMBIGUOUS',item:null,detail:'El SKU aparece en varias filas de Tiendanube o coincide con distintas presentaciones. Revisá manualmente las variantes antes de vincular.'};
  }
  const item=sameSku[0];
  if(!item)return {state:'NO_EXACT_MATCH',item:null,detail:'No se encontró una coincidencia exacta de SKU en el CSV disponible. Esto no significa que no esté publicado en Tiendanube.'};
  if(item.status!=='MATCHED_SKU'||String(item.matched_ecomm_id||'').trim()!==id){
    return {state:'AMBIGUOUS',item:null,detail:'El SKU existe en el CSV, pero la conciliación no confirma una coincidencia única con este producto Ecomm.'};
  }
  return {state:'POSSIBLE',item,detail:'Una fila del CSV coincide por SKU e ID Ecomm en la conciliación. Es una coincidencia preliminar, no un vínculo confirmado ni una verificación de la variante.'};
}

const statuses:Record<string,string>={
  ALREADY_PUBLISHED:'Encontrado en el análisis ML',
  CANDIDATE_TO_PUBLISH:'Candidato para preparar',
  REVIEW_REQUIRED:'Necesita revisión',
  POSSIBLE_DUPLICATE:'Posible duplicado',
  INCOMPLETE_DATA:'Datos incompletos',
  INVALID_SKU:'Revisar SKU',
  INVALID_EAN:'Revisar código de barras',
  UNMATCHED_ML_LISTING:'Publicación ML sin asociación',
};
export const reconciliationLabel=(status:string)=>statuses[status]||'Estado por revisar';

export function productIdentity(result:Result,index:number):string {
  return String(result.product?.ecomm_id||result.listing?.external_id||result.product?.sku_variant||result.product?.sku||'fila')+':'+index;
}
