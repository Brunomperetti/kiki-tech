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

      <details className="kiki-ecomm-ml-blockers">
        <summary>¿Por qué se descartan tantas coincidencias? Ver motivos</summary>
        <p>Desglosamos las filas de la copia de Mercado Libre con marca disponible. Esto no confirma que sean errores ni desbloquea ningún producto.</p>
        <div className="kiki-ecomm-commercial-metrics">
          <div><strong>{report.diagnostics.counts.ml_rows_with_brand_available}</strong><small>Filas ML con marca propia o de EDIMA</small></div>
          <div><strong>{report.diagnostics.counts.ml_rows_with_matching_edima_mla}</strong><small>Filas ML con MLA presente en EDIMA con marca única</small></div>
          <div><strong>{report.diagnostics.counts.ml_rows_ambiguous}</strong><small>Filas ML descartadas por identificadores ambiguos</small></div>
          <div><strong>{report.diagnostics.counts.distinct_mlas_ambiguous}</strong><small>Publicaciones MLA afectadas (sin repetir)</small></div>
          <div><strong>{report.diagnostics.counts.shared_historical_mla}</strong><small>MLA asociado a varios IDs históricos</small></div>
          <div><strong>{report.diagnostics.counts.shared_sku}</strong><small>SKU que apunta a varios Ecomm</small></div>
          <div><strong>{report.diagnostics.counts.shared_gtin}</strong><small>GTIN con varios propietarios</small></div>
          <div><strong>{report.diagnostics.counts.identity_signal_conflicts}</strong><small>SKU, GTIN o MLA apuntan a IDs distintos</small></div>
          <div><strong>{report.diagnostics.counts.shared_mla_with_unique_variant_sku}</strong><small>MLA compartido pero SKU de variante único: investigar</small></div>
          <div><strong>{report.diagnostics.counts.ml_rows_matching_already_branded_ecomm}</strong><small>Coincidían con Ecomm ya con marca</small></div>
          <div><strong>{report.diagnostics.counts.ml_rows_without_unique_identity}</strong><small>Con marca, pero sin identidad única encontrada</small></div>
          <div><strong>{report.diagnostics.counts.ml_rows_without_brand_in_either_source}</strong><small>Sin marca disponible ni por ML ni EDIMA</small></div>
        </div>
        <p>Otros controles: {report.diagnostics.counts.ml_rows_with_brand_disagreements} filas con marcas API/EDIMA contradictorias; {report.diagnostics.counts.edima_rows_not_in_ml_snapshot} filas EDIMA sin MLA en esta copia ML; {report.diagnostics.counts.ml_rows_pointing_to_missing_brand_ecomm} filas con identidad no ambigua hacia Ecomm sin marca antes de los controles finales.</p>
        <p className="kiki-ecomm-hint">{report.diagnostics.policy}</p>
        <details>
          <summary>Ver ejemplos de coincidencias retenidas ({report.diagnostics.examples.length})</summary>
          {report.diagnostics.examples.length===0?<p>No hay ejemplos de filas ML rechazadas por estas reglas en las copias disponibles.</p>:report.diagnostics.examples.map((x,i)=><article className="kiki-ecomm-commercial-row" key={x.mla+'-'+i}>
            <strong>Publicación {x.mla}</strong>
            <small>SKU informado en ML: {x.ml_sku||'No informado'}</small>
            <p>Motivos: {x.reason_codes.map(code=>({
              SHARED_HISTORICAL_MLA:'MLA compartido por varios IDs Ecomm',
              SHARED_SKU:'SKU relacionado con múltiples fichas Ecomm',
              SHARED_GTIN:'GTIN asociado a varios productos Ecomm',
              IDENTITY_SIGNAL_CONFLICT:'SKU, GTIN y/o MLA apuntan a fichas diferentes',
            }[code]||code)).join(' · ')}</p>
            <small>IDs potenciales: SKU {x.sku_owner_count} · GTIN {x.gtin_owner_count} · MLA histórico {x.historical_mla_owner_count}.</small>
            {x.unique_variant_sku_present&&<small>Hay un SKU de variante único que merece investigación, NO validación automática.</small>}
          </article>)}
        </details>
      </details>

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
