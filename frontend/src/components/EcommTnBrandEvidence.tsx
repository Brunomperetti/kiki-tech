import {useState} from 'react';
import {api} from '../services/api';
import type {EcommTnBrandEvidence as Evidence} from '../types/ecomm-app';

export function EcommTnBrandEvidence(){
  const [report,setReport]=useState<Evidence|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  async function check(){
    setBusy(true);setError('');
    try{setReport(await api.ecommTnBrandEvidence())}
    catch(e){setError(e instanceof Error?e.message:'No se pudo revisar la evidencia de marcas de Tiendanube.')}
    finally{setBusy(false)}
  }
  const s=report?.summary;
  return <details className="kiki-ecomm-tn-brands">
    <summary>Buscar marcas ya informadas en Tiendanube (sin aplicarlas)</summary>
    <p>KIKI busca posibles marcas para productos que no tienen marca en el Excel histórico. Sólo usa coincidencias de SKU únicas y sin cambios importantes respecto de la API. Las marcas propuestas son pistas, no datos confirmados del fabricante.</p>
    <button type="button" disabled={busy} onClick={()=>void check()}>
      {busy?'Revisando catálogo…':'Comparar marcas con Tiendanube (solo lectura)'}
    </button>
    {error&&<p role="alert" className="kiki-ecomm-notice">{error}</p>}
    {report&&(!report.available?<p role="note" className="kiki-ecomm-notice">Todavía no hay un CSV de Tiendanube para cruzar. No se propuso ninguna marca.</p>:<section className="kiki-ecomm-tn-brand-results">
      <h4>Qué podemos revisar con evidencia de Tiendanube</h4>
      <div className="kiki-ecomm-commercial-metrics">
        <div><strong>{s?.missing_brand_unique_id??0}</strong><small>Sin marca histórica entre IDs reconocidos</small></div>
        <div><strong>{s?.candidate_unique_exact_sku??0}</strong><small>Con marca encontrada por SKU único</small></div>
        <div><strong>{s?.no_exact_tn_sku??0}</strong><small>Sin coincidencia literal de SKU</small></div>
        <div><strong>{(s?.ambiguous_ecomm_sku??0)+(s?.ambiguous_tn_sku??0)}</strong><small>SKU ambiguos (no proponer)</small></div>
      </div>
      <p><strong>Requieren otras verificaciones:</strong> {s?.tn_brand_empty??0} coincidencias sin marca en Tiendanube; {s?.api_sku_changed??0} SKU cambiados en la API; {s?.combo_candidate??0} candidatos corresponden a combos y requieren atención adicional.</p>
      <p className="kiki-ecomm-hint">{report.policy}</p>
      <details>
        <summary>Ver candidatos encontrados ({report.candidates.length} ejemplos)</summary>
        {report.candidates.length===0?<p>No se encontraron candidatos con estas reglas de coincidencia segura.</p>:report.candidates.map(x=><article className="kiki-ecomm-commercial-row" key={x.ecomm_id}>
          <strong>{x.ecomm_name||'Producto sin título'} · ID Ecomm {x.ecomm_id}</strong>
          <small>SKU Ecomm: {x.ecomm_sku} · SKU Tiendanube: {x.tn_sku}</small>
          <p><strong>Marca que figura en Tiendanube:</strong> {x.brand_from_tn}</p>
          <small>Referencia Tiendanube: {x.tn_name||x.tn_slug||'Producto sin nombre'} · Combo según API: {x.is_combo===true?'Sí':x.is_combo===false?'No':'No informado'}</small>
          <small>Sin confirmar · No se guardó ninguna marca en Ecomm-App ni en KIKI.</small>
        </article>)}
      </details>
      <small>Solo se muestran hasta {report.sampling_limit??20} ejemplos. Los candidatos y las marcas requieren verificación humana antes de incorporarse a cualquier catálogo.</small>
    </section>)}
  </details>;
}
