import {useState} from 'react';
import {api} from '../services/api';
import type {EcommMlBrandEvidence as Report} from '../types/ecomm-app';

const method=(key:string)=>({
  UNIQUE_EXACT_ML_SKU:'SKU exacto y único',
  UNIQUE_VALID_ML_GTIN:'GTIN válido y único',
  UNIQUE_VALID_EDIMA_GTIN:'GTIN válido y único del reporte EDIMA',
  UNIQUE_HISTORICAL_MLA_REFERENCE:'Referencia MLA histórica única',
}[key]||key);
const source=(key:string)=>({
  MERCADOLIBRE_API:'Snapshot API Mercado Libre',
  MERCADOLIBRE:'Excel Mercado Libre',
  EDIMA_LINKAGE:'Reporte EDIMA',
}[key]||key);
const updated=(date:string|null)=>date?
  new Date(date).toLocaleString('es-AR',{timeZone:'America/Argentina/Cordoba',hour12:false}):
  'No disponible';

export function EcommMlBrandEvidence(){
  const [report,setReport]=useState<Report|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  async function inspect(){
    setLoading(true);setError('');
    try{setReport(await api.ecommMlBrandEvidence())}
    catch(e){setError(e instanceof Error?e.message:'No se pudo comparar la evidencia de Mercado Libre.')}
    finally{setLoading(false)}
  }
  const s=report?.summary;
  const sources=report?.sources;
  return <details className="kiki-ecomm-ml-brands">
    <summary>Buscar marcas en Mercado Libre y EDIMA (sin aplicarlas)</summary>
    <p>Investigamos si los productos sin marca en el Excel de Ecomm-App tienen publicaciones con una marca informada. Usamos identificadores únicos; un MLA compartido o un SKU de familia no es suficiente para confirmar fabricante.</p>
    <button type="button" disabled={loading} onClick={()=>void inspect()}>
      {loading?'Revisando publicaciones…':'Investigar marcas de Mercado Libre (solo lectura)'}
    </button>
    {error&&<p role="alert" className="kiki-ecomm-notice">{error}</p>}
    {report&&<section className="kiki-ecomm-ml-brand-results">
      {!report.available&&<p role="note">No hay datos de publicaciones ML ni reporte EDIMA cargados. Importá un reporte para realizar el análisis; no se inventaron marcas.</p>}
      <h4>Marcas disponibles en las fuentes ya cargadas</h4>
      <div className="kiki-ecomm-commercial-metrics">
        <div><strong>{s?.missing_historical_brand??0}</strong><small>Productos sin marca histórica</small></div>
        <div><strong>{sources?.ml_rows??0}</strong><small>Filas de {source(sources?.ml_source||'MERCADOLIBRE_API')}</small></div>
        <div><strong>{sources?.ml_rows_with_brand??0}</strong><small>Filas ML con atributo de marca</small></div>
        <div><strong>{sources?.edima_rows_with_brand??0}</strong><small>Filas EDIMA con marca, de {sources?.edima_rows??0}</small></div>
        <div><strong>{s?.unique_brand_review_leads??0}</strong><small>Candidatos de marca para revisar, no confirmados</small></div>
      </div>
      <p>Observaciones: {s?.ambiguous_identifiers??0} filas con identificadores ambiguos; {s?.conflicting_listing_brands??0} marcas contradictorias entre filas de publicación; {s?.conflicting_brands_per_ecomm_id??0} productos con marcas distintas; {s?.combo_leads??0} candidatos son combos.</p>
      <p className="kiki-ecomm-hint">{report.policy}</p>
      <details>
        <summary>Ver fuentes y fechas de la información</summary>
        <p>Snapshot de Mercado Libre: {updated(report.source_dates.ml_snapshot)} · Reporte EDIMA: {updated(report.source_dates.edima)}</p>
        <p>Excel Ecomm-App: {updated(report.source_dates.ecomm_historical)} · Copia API Ecomm: {updated(report.source_dates.ecomm_api_stage)}</p>
        <p>Esta prueba no consulta publicaciones ML en vivo. Los atributos de marca presentes en futuras sincronizaciones API podrán incorporarse, pero la cobertura depende de los datos reales de Mercado Libre.</p>
      </details>
      <details>
        <summary>Investigar candidatos de marca ({report.candidates.length} ejemplos)</summary>
        {report.candidates.length===0?<p>No hay candidatos con evidencia suficientemente identificable en estas copias. Revisá si EDIMA incluye marcas y si el snapshot ML dispone de ese atributo.</p>:report.candidates.map(item=><article className="kiki-ecomm-commercial-row" key={item.ecomm_id}>
          <strong>{item.ecomm_name||'Producto sin título'} · ID Ecomm {item.ecomm_id}</strong>
          <small>SKU Ecomm: {item.ecomm_sku} · Publicación {item.mla}</small>
          <p><strong>Marca publicada:</strong> {item.ml_brand} <span>({source(item.ml_source)})</span></p>
          <small>Identificador: {method(item.match_basis)} · Publicaciones de apoyo: {item.supporting_listings} · Combo: {item.is_combo===true?'Sí':item.is_combo===false?'No':'Sin dato'}</small>
          <small>Publicación ML: {item.ml_title||'Sin título'} · Requiere verificar marca fabricante, presentación y correspondencia real.</small>
        </article>)}
      </details>
      <small>Se muestran como máximo {report.sampling_limit} ejemplos. Ninguna marca fue completada, confirmada ni publicada automáticamente.</small>
    </section>}
  </details>;
}
