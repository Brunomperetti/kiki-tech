import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {Result} from '../types/catalog';
import {reconciliationLabel,tiendanubeCandidate} from '../utils/catalogProductView';
import type {TiendanubeCatalogRow} from '../utils/catalogProductView';

type Props={
  result:Result;
  tiendanubeLoaded:boolean;
  tiendanubeAvailable:boolean;
  tiendanubeRows:TiendanubeCatalogRow[];
  onClose:()=>void;
};

const formatNumber=(value:number|string|undefined|null)=>value===undefined||value===null||value===''?'—':String(value);
const price=(value:number|string|null|undefined)=>value==null||value===''?'—':new Intl.NumberFormat('es-AR',{maximumFractionDigits:2}).format(Number(value));

export function ProductDetail({result,tiendanubeLoaded,tiendanubeAvailable,tiendanubeRows,onClose}:Props){
  const product=result.product;
  const candidate=useMemo(
    ()=>tiendanubeCandidate(product,tiendanubeLoaded&&tiendanubeAvailable,tiendanubeRows),
    [product,tiendanubeLoaded,tiendanubeAvailable,tiendanubeRows],
  );
  const [ai,setAi]=useState<Awaited<ReturnType<typeof api.tiendanubeAiSaved>>|null>(null);
  const [aiBusy,setAiBusy]=useState(false);
  const [aiError,setAiError]=useState(false);
  const aiSlug=candidate.state==='POSSIBLE'?candidate.item?.slug||'':'';

  useEffect(()=>{
    let active=true;
    setAi(null);
    setAiError(false);
    if(!aiSlug)return ()=>{active=false};
    setAiBusy(true);
    api.tiendanubeAiSaved(aiSlug).then(response=>{
      if(active)setAi(response);
    }).catch(()=>{if(active)setAiError(true)}).finally(()=>{if(active)setAiBusy(false)});
    return ()=>{active=false};
  },[aiSlug]);

  const ids=result.matched_listing_ids||[];
  return <section className="kiki-product-detail" aria-label="Ficha del producto seleccionado">
    <header className="kiki-detail-heading">
      <div>
        <p className="eyebrow">FICHA DE PRODUCTO · SOLO LECTURA</p>
        <h2>{product?.name||result.listing?.title||'Producto sin nombre'}</h2>
        <span className="kiki-product-status">{reconciliationLabel(result.status)}</span>
      </div>
      <button type="button" className="kiki-close-detail" onClick={onClose} aria-label="Cerrar ficha">Cerrar ×</button>
    </header>
    <p className="kiki-detail-intro">Esta vista reúne lo disponible en KIKI. Cada canal muestra su propia fuente y sus límites de verificación.</p>

    <div className="kiki-detail-sources">
      <article className="kiki-detail-source">
        <div className="kiki-detail-source-heading"><span className="kiki-detail-source-icon">E</span><h3>Ecomm-App</h3></div>
        {product?<dl className="kiki-details-grid">
          <div><dt>ID de catálogo</dt><dd>{formatNumber(product.ecomm_id)}</dd></div>
          <div><dt>SKU</dt><dd>{formatNumber(product.sku_variant||product.sku_effective||product.sku)}</dd></div>
          <div><dt>EAN</dt><dd>{formatNumber(product.ean)}</dd></div>
          <div><dt>Marca declarada</dt><dd>{formatNumber(product.brand)}</dd></div>
          <div><dt>Stock en snapshot</dt><dd>{formatNumber(product.stock)}</dd></div>
          <div><dt>Precio en snapshot</dt><dd>{product.price==null?'—':`$ ${price(product.price)}`}</dd></div>
        </dl>:<p className="kiki-detail-muted">Esta publicación no tiene un producto Ecomm asociado en la conciliación consultada.</p>}
      </article>

      <article className="kiki-detail-source">
        <div className="kiki-detail-source-heading"><span className="kiki-detail-source-icon">ML</span><h3>Mercado Libre</h3></div>
        {ids.length?<div>
          <p className="kiki-detail-positive">{ids.length} {ids.length===1?'publicación asociada':'publicaciones asociadas'} en el último análisis</p>
          <p className="kiki-detail-muted">Identificadores: {ids.join(', ')}</p>
        </div>:<p className="kiki-detail-muted">No hay una asociación ML confirmada en este resultado. No significa que el producto no esté publicado.</p>}
        {result.listing?.external_id&&<p className="kiki-detail-muted">Publicación del registro: {result.listing.external_id}</p>}
        {result.reason&&<p className="kiki-detail-muted">Diagnóstico: {result.reason}</p>}
        <Link to="/readiness" className="kiki-detail-link">Ir a vinculación ML →</Link>
      </article>

      <article className="kiki-detail-source">
        <div className="kiki-detail-source-heading"><span className="kiki-detail-source-icon">TN</span><h3>Tiendanube</h3></div>
        {!tiendanubeLoaded?<p className="kiki-detail-muted">Cargando el catálogo CSV disponible…</p>:<>
          <p className={candidate.state==='POSSIBLE'?'kiki-detail-positive':'kiki-detail-muted'}>{candidate.state==='POSSIBLE'?'Coincidencia preliminar por SKU':candidate.state==='AMBIGUOUS'?'Requiere revisar coincidencias':'Sin vinculación verificable'}</p>
          <p className="kiki-detail-muted">{candidate.detail}</p>
          {candidate.item&&<dl className="kiki-details-grid">
            <div><dt>Nombre en CSV</dt><dd>{candidate.item.name}</dd></div>
            <div><dt>SKU en CSV</dt><dd>{candidate.item.sku}</dd></div>
            <div><dt>Precio en CSV</dt><dd>{candidate.item.price==null?'—':`$ ${price(candidate.item.price)}`}</dd></div>
            <div><dt>Stock en CSV</dt><dd>{formatNumber(candidate.item.stock)}</dd></div>
          </dl>}
        </>}
        <Link to="/tiendanube" className="kiki-detail-link">Revisar Tiendanube →</Link>
      </article>

      <article className="kiki-detail-source">
        <div className="kiki-detail-source-heading"><span className="kiki-detail-source-icon">AI</span><h3>KIKI AI</h3></div>
        {!tiendanubeLoaded?<p className="kiki-detail-muted">Esperando información del CSV para localizar propuestas…</p>:candidate.state!=='POSSIBLE'?<p className="kiki-detail-muted">Para consultar un borrador de Tiendanube necesitamos identificar una ficha única y sin ambigüedades.</p>:aiBusy?<p className="kiki-detail-muted">Consultando borradores guardados (sin consumir créditos)…</p>:aiError?<p className="kiki-detail-muted">No se pudo consultar el historial de IA.</p>:ai?.available&&ai.draft?<div>
          <p className="kiki-detail-positive">{ai.draft.review_status==='APPROVED_INTERNAL'?'Aprobado internamente':ai.draft.review_status==='REJECTED_INTERNAL'?'Rechazado internamente':'Borrador pendiente de revisión'}</p>
          <p className="kiki-detail-muted">Título propuesto: {ai.draft.title}</p>
          {!ai.draft.source_current&&<p className="kiki-detail-warning">Los datos importados cambiaron desde esta propuesta.</p>}
        </div>:<p className="kiki-detail-muted">No hay una propuesta de IA guardada para esta ficha.</p>}
        <Link to="/tiendanube" className="kiki-detail-link">Gestionar propuestas →</Link>
      </article>
    </div>

    <div className="kiki-detail-note">
      <strong>¿Qué falta para continuar?</strong>
      <p>{result.multiple_ml_listings?'Hay varias publicaciones ML asociadas: revisá los identificadores antes de tomar decisiones.':result.issues?.length?result.issues.map(issue=>issue.message).filter(Boolean).slice(0,2).join(' · '):'Revisá los datos de los canales y las tareas pendientes antes de preparar cambios.'}</p>
      <div className="kiki-detail-actions"><Link className="kiki-main-action" to="/work">Ir a tareas <span aria-hidden="true">→</span></Link><Link className="secondary-link" to="/prepublication">Preparación ML</Link></div>
    </div>
    <p className="kiki-home-footnote">Los precios y stocks corresponden a fuentes distintas y podrían tener fechas o reglas comerciales diferentes. Esta ficha no permite editar ni publicar.</p>
  </section>;
}
