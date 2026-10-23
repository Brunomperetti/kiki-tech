import {useState} from 'react';
import {api} from '../services/api';
import type {EcommStageComparison,EcommHybridPreview,EcommLiveStockCheck} from '../types/ecomm-app';

const shown=(value:unknown)=>(value===undefined||value===null||value==='')?'No informado':String(value);
const combo=(value:boolean|null)=>value===true?'Sí':value===false?'No':'No informado';
const identity=(value:EcommHybridPreview['rows'][number]['identity'])=>({
  MATCHED_STABLE_ID:'Mismo ID en ambas fuentes',
  HISTORICAL_ONLY:'Solo en inventario histórico',
  API_ONLY:'Solo en la copia API',
  NOT_FOUND:'ID no encontrado',
  AMBIGUOUS_DUPLICATE_ID:'ID duplicado: no unir',
}[value]);
const skuChange=(value:EcommHybridPreview['rows'][number]['sku_relation'])=>({
  SAME_SKU:'SKU idéntico',
  FORMAT_ONLY:'SKU con escritura diferente',
  SUBSTANTIVE_CHANGE:'SKU cambiado: revisar',
}[value||'SAME_SKU']);

export function EcommHybridInspector({comparison}:{comparison:EcommStageComparison}){
  const [idsText,setIdsText]=useState(()=>{
    const important=comparison.samples.sku_changed_same_id
      .filter(row=>row.change_type==='SUBSTANTIVE')
      .map(row=>row.ecomm_id);
    return important.join('\n');
  });
  const [result,setResult]=useState<EcommHybridPreview|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [live,setLive]=useState<EcommLiveStockCheck|null>(null);
  const [liveBusy,setLiveBusy]=useState(false);
  const [liveError,setLiveError]=useState('');
  const ids=idsText.split(/[\s,;]+/).filter(Boolean);
  const valid=ids.length>0&&ids.length<=5&&ids.every(x=>/^\d+$/.test(x))&&new Set(ids).size===ids.length;

  async function inspect(){
    if(!valid)return;
    setBusy(true);setError('');setResult(null);setLive(null);setLiveError('');
    try{setResult(await api.ecommHybridPreview(ids))}
    catch(e){setError(e instanceof Error?e.message:'No se pudo consultar la simulación.')}
    finally{setBusy(false)}
  }

  async function checkLive(){
    if(!result||liveBusy)return;
    setLiveBusy(true);setLiveError('');setLive(null);
    try{setLive(await api.ecommLiveStockCheck(result.rows.map(row=>row.ecomm_id)))}
    catch(e){setLiveError(e instanceof Error?e.message:'La consulta de stock no pudo completarse.')}
    finally{setLiveBusy(false)}
  }

  return <details className="kiki-ecomm-hybrid">
    <summary>Simular una ficha híbrida por ID (sin actualizar KIKI)</summary>
    <p>Comparamos <strong>nombre, precio, costo y SKU del Excel histórico</strong> con <strong>stock, depósito, SKU y combo de la copia API</strong>. No se crea ni modifica ningún producto.</p>
    <label htmlFor="ecomm-hybrid-id-entry">ID interno de variante Ecomm (uno por línea, hasta cinco)</label>
    <textarea id="ecomm-hybrid-id-entry" rows={3} value={idsText} onChange={e=>{setIdsText(e.target.value);setResult(null);setLive(null);setLiveError('')}} placeholder="Ingresá 1 a 5 IDs internos, uno por línea"/>
    <div className="kiki-ecomm-actions">
      <button type="button" disabled={!valid||busy} onClick={()=>void inspect()}>
        {busy?'Comparando fichas…':'Ver comparación sin modificar datos'}
      </button>
    </div>
    <small>{valid?'La consulta solo lee dos copias ya guardadas.':'Usá de 1 a 5 IDs numéricos distintos.'}</small>
    {error&&<p role="alert" className="kiki-ecomm-notice">{error}</p>}
    {result&&<section className="kiki-ecomm-hybrid-results">
      <h4>¿Qué información podemos conservar?</h4>
      <p><strong>Registros reconocidos por ID:</strong> {result.coverage.matched_unique_ids}. De esos, el Excel tiene precio en {result.coverage.legacy_price_present}, costo en {result.coverage.legacy_cost_present} y marca en {result.coverage.legacy_brand_present}. La copia API tiene stock informado en {result.coverage.api_stock_present}.</p>
      <p className="kiki-ecomm-hint">{result.warning}</p>
      <p><strong>Fecha de captura API:</strong> desde {shown(result.stage_capture_started)} hasta {shown(result.stage_capture_finished)}. No es una consulta de stock en vivo.</p>

      <div className="kiki-ecomm-live-check">
        <h4>Verificar stock en Ecomm-App ahora</h4>
        <p>Consulta puntual a la API oficial. KIKI solo dará por reconocida una respuesta si coinciden <strong>SKU exacto + ID interno</strong> y el total cuadra con los depósitos. Los combos siguen sujetos a controles comerciales.</p>
        <button type="button" disabled={liveBusy||busy} onClick={()=>void checkLive()}>
          {liveBusy?'Consultando Ecomm-App…':'Consultar stock actual (solo lectura)'}
        </button>
        {liveError&&<p role="alert" className="kiki-ecomm-notice">{liveError}</p>}
        {live&&<div className="kiki-ecomm-live-rows" aria-live="polite">
          <p><strong>Momento de consulta:</strong> {new Date(live.checked_at).toLocaleString('es-AR')}</p>
          <p className="kiki-ecomm-hint">{live.warning}</p>
          {live.rows.map(item=><div className="kiki-ecomm-live-record" key={item.ecomm_id}>
            <strong>ID {item.ecomm_id} · {item.sku||'SKU no disponible'}</strong>
            <p><strong>{item.status==='IDENTITY_AND_STOCK_VERIFIED'?'Identidad y suma de depósitos comprobadas':'No validado para sincronización'}</strong>: {item.reason}</p>
            <p>Stock histórico: {shown(item.historical_stock)} · Capturado anteriormente: {shown(item.captured_stock)} · Consultado ahora: {shown(item.current_stock)}</p>
            <small>Depósitos de esta consulta: {item.warehouses?.length?item.warehouses.map(w=>`${shown(w.id)}: ${shown(w.stock)}`).join(' · '):'Sin datos verificables'}</small>
          </div>)}
        </div>}
      </div>
      {result.rows.map(row=><article className="kiki-ecomm-hybrid-record" key={row.ecomm_id}>
        <header><strong>ID Ecomm: {row.ecomm_id}</strong><span>{identity(row.identity)}</span></header>
        {row.sku_relation&&<p><strong>Comparación SKU:</strong> {skuChange(row.sku_relation)}</p>}
        <div className="kiki-ecomm-hybrid-columns">
          <div>
            <h5>Excel histórico · Datos comerciales</h5>
            {row.legacy?<>
              <p><strong>Producto:</strong> {shown(row.legacy.name)}</p>
              <p><strong>SKU anterior:</strong> {shown(row.legacy.sku)}</p>
              <p><strong>Marca:</strong> {shown(row.legacy.brand)}</p>
              <p><strong>Precio de lista:</strong> {shown(row.legacy.list_price)}</p>
              <p><strong>Costo:</strong> {shown(row.legacy.cost)}</p>
              <p><strong>EAN:</strong> {shown(row.legacy.ean)}</p>
              <p><strong>Stock histórico:</strong> {shown(row.legacy.historical_stock)}</p>
            </>:<p>Este ID no figura en el Excel anterior.</p>}
          </div>
          <div>
            <h5>API · Copia de inventario</h5>
            {row.api?<>
              <p><strong>SKU de variante:</strong> {shown(row.api.sku)}</p>
              <p><strong>Producto padre:</strong> {shown(row.api.parent_code)}</p>
              <p><strong>Combo según API:</strong> {combo(row.api.is_combo)}</p>
              <p><strong>Stock capturado:</strong> {shown(row.api.total_stock)}</p>
              <p><strong>Depósitos:</strong> {row.api.warehouses?.length?row.api.warehouses.map(w=>`${shown(w.id)}: ${shown(w.stock)}`).join(' · '):'No informados'}</p>
            </>:<p>Este ID no figura en la copia de la API.</p>}
          </div>
        </div>
        <small>{row.warning}</small>
      </article>)}
    </section>}
  </details>;
}
