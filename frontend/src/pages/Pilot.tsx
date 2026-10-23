import {FormEvent,useEffect,useState} from 'react';
import {api} from '../services/api';
import type {MercadoLibreStatus} from '../types/catalog';
import type {EcommApiCatalog,EcommApiCatalogRow,EcommAppLookup,EcommStageStatus} from '../types/ecomm-app';
import '../pilot.css';

type TnReport=Awaited<ReturnType<typeof api.tiendanubeReport>>;
const errorMessage=(e:unknown)=>e instanceof Error?e.message:'No se pudo consultar la fuente.';
const fmt=(value:number|string|null|undefined)=>value==null?'Sin informar':String(value);
const dateLabel=(s:string|null|undefined)=>{
  if(!s)return 'Sin fecha registrada';
  const value=new Date(s);
  return Number.isNaN(value.getTime())?'Fecha no disponible':value.toLocaleString('es-AR');
};

export function Pilot(){
  const [stage,setStage]=useState<EcommStageStatus|null>(null);
  const [catalog,setCatalog]=useState<EcommApiCatalog|null>(null);
  const [ml,setMl]=useState<MercadoLibreStatus|null>(null);
  const [tn,setTn]=useState<TnReport|null>(null);
  const [loading,setLoading]=useState(true);
  const [errors,setErrors]=useState<string[]>([]);
  const [searchInput,setSearchInput]=useState('');
  const [activeQuery,setActiveQuery]=useState('');
  const [page,setPage]=useState(1);
  const [catalogBusy,setCatalogBusy]=useState(false);
  const [catalogError,setCatalogError]=useState('');
  const [live,setLive]=useState<EcommAppLookup|null>(null);
  const [selected,setSelected]=useState<EcommApiCatalogRow|null>(null);
  const [liveBusy,setLiveBusy]=useState(false);
  const [liveError,setLiveError]=useState('');

  async function refresh(){
    setLoading(true);
    const responses=await Promise.allSettled([
      api.ecommStageStatus(),
      api.ecommApiCatalog(activeQuery,page),
      api.mlStatus(),
      api.tiendanubeReport(),
    ] as const);
    const [stageResponse,catalogResponse,mlResponse,tnResponse]=responses;
    setStage(stageResponse.status==='fulfilled'?stageResponse.value:null);
    setCatalog(catalogResponse.status==='fulfilled'?catalogResponse.value:null);
    setMl(mlResponse.status==='fulfilled'?mlResponse.value:null);
    setTn(tnResponse.status==='fulfilled'?tnResponse.value:null);
    setErrors(responses.flatMap((r,i)=>r.status==='rejected'?
      [(['Copia API Ecomm','Catálogo API Ecomm','Mercado Libre','Tiendanube'][i])+': '+errorMessage(r.reason)]:[]));
    setLoading(false);
  }
  useEffect(()=>{void refresh()},[]);

  async function search(q:string,nextPage:number){
    setCatalogBusy(true);
    setCatalogError('');
    setLive(null);
    setSelected(null);
    try{
      const result=await api.ecommApiCatalog(q,nextPage);
      setCatalog(result);
      setActiveQuery(q);
      setPage(nextPage);
    }catch(e){
      setCatalog(null);
      setCatalogError(errorMessage(e));
    }finally{setCatalogBusy(false)}
  }
  function submit(event:FormEvent){
    event.preventDefault();
    void search(searchInput.trim(),1);
  }
  async function checkSku(row:EcommApiCatalogRow){
    if(!row.sku)return;
    setLiveBusy(true);setLive(null);setLiveError('');setSelected(row);
    try{setLive(await api.ecommAppLookup([row.sku]));}
    catch(e){setLiveError(errorMessage(e));}
    finally{setLiveBusy(false)}
  }
  const result=live?.sku_diagnosis?.requested?.[0];
  const exact=result?.status==='EXACT_SINGLE' && result.matches.length===1;
  const verified=exact && String(result.matches[0]?.variant_id)===selected?.ecomm_id;
  const more=catalog?catalog.page*catalog.page_size<catalog.total_matches:false;

  return <div className="kiki-pilot">
    <header className="kiki-home-header">
      <div>
        <p className="eyebrow">KIKI TECH · ECOMM-APP API</p>
        <h1>Catálogo Ecomm-App por API.</h1>
        <p>Desde acá trabajamos <strong>solo con datos de Ecomm-App obtenidos por API</strong>.
          No se leen productos del Excel histórico, no se mezclan identidades y no se publica nada.</p>
      </div>
      <button type="button" className="kiki-refresh" onClick={()=>void refresh()} disabled={loading}>
        {loading?'Consultando…':'↻ Verificar fuentes'}
      </button>
    </header>

    {errors.length>0&&<div role="alert" className="notice warning">
      <strong>Hay fuentes que no respondieron.</strong>
      <p>{errors.join(' · ')} No los interpretes como catálogos vacíos.</p>
    </div>}

    <section className="kiki-pilot-sources">
      <h2>1. Fuente Ecomm-App: API exclusivamente</h2>
      <p>Los productos se consultan desde la copia completa obtenida por API. El stock mostrado corresponde
        a la fecha de captura; no se sincroniza en vivo automáticamente.</p>
      <div className="kiki-pilot-source-grid kiki-api-source-grid">
        <article>
          <span className={'kiki-pilot-state '+(stage?.complete?'is-ok':'is-caution')}>
            {stage?.complete?'Copia completa':'No confirmada'}
          </span>
          <strong>Productos padre Ecomm</strong>
          <b>{loading?'…':stage?.quality?.parents==null?'No disponible':stage.quality.parents.toLocaleString('es-AR')}</b>
          <small>API, no Excel</small>
        </article>
        <article>
          <span className={'kiki-pilot-state '+(stage?.complete?'is-ok':'is-caution')}>Variantes API</span>
          <strong>IDs de variantes</strong>
          <b>{loading?'…':stage?.quality?.variants==null?'No disponible':stage.quality.variants.toLocaleString('es-AR')}</b>
          <small>{stage?stage.pages_saved+'/'+(stage.expected_pages??'?')+' páginas capturadas':'Sin copia verificable'}</small>
        </article>
        <article>
          <span className={'kiki-pilot-state '+(ml?.connected&&!ml.token_expired?'is-ok':'is-caution')}>
            {ml?.connected&&!ml.token_expired?'Conectado':'Sin conexión comprobada'}
          </span>
          <strong>Mercado Libre · otra fuente</strong>
          <b>{ml?.listing_count==null?'No disponible':ml.listing_count.toLocaleString('es-AR')}</b>
          <small>Último snapshot: {dateLabel(ml?.last_sync)}. No se concilia desde esta pantalla.</small>
        </article>
        <article>
          <span className={'kiki-pilot-state '+(tn?.available?'is-ok':'is-caution')}>
            {tn?.available?'CSV disponible':'Sin confirmar'}
          </span>
          <strong>Tiendanube · otra fuente</strong>
          <b>{tn?.available?fmt(tn.summary?.products):'No disponible'}</b>
          <small>Datos de canal por CSV, no de Ecomm-App</small>
        </article>
      </div>
      <small className="kiki-pilot-last">
        Última página API capturada: {dateLabel(catalog?.capture_last_at)}.
        La copia API es de solo lectura y aún no está activada como fuente de la conciliación general.
      </small>
    </section>

    <section className="kiki-pilot-steps">
      <h2>2. Buscar productos en el catálogo API</h2>
      <p>Buscá por SKU exacto o parcial, ID interno, descripción o GTIN. Se mantienen
        separadas las variantes y los combos aunque compartan familia o código de barras.</p>
      <form className="kiki-api-search" onSubmit={submit}>
        <label htmlFor="api-sku-query">SKU, ID o producto</label>
        <input id="api-sku-query" value={searchInput} onChange={e=>setSearchInput(e.target.value)}
          maxLength={80} placeholder="Ej.: 2500400" />
        <button type="submit" disabled={catalogBusy||loading}>{catalogBusy?'Buscando…':'Buscar en API'}</button>
      </form>
      {catalogError&&<p className="kiki-pilot-warning" role="alert">{catalogError}</p>}
      {catalog&&<>
        <p className="kiki-pilot-last">{catalog.total_matches.toLocaleString('es-AR')} variantes coinciden.
          Mostrando página {catalog.page}, hasta {catalog.page_size} resultados. Solo fuente {catalog.source}.</p>
        <div className="kiki-api-table-wrap">
          <table className="kiki-api-table">
            <thead><tr><th>ID Ecomm</th><th>SKU</th><th>Producto</th><th>Combo</th><th>GTIN</th><th>Stock capturado</th><th>Consulta puntual</th></tr></thead>
            <tbody>{catalog.items.map((row,i)=><tr key={(row.ecomm_id||'sin-id')+'-'+i}>
              <td>{fmt(row.ecomm_id)}</td>
              <td><strong>{fmt(row.sku)}</strong></td>
              <td>{fmt(row.product_name)}<small>{row.variant_description||''}</small></td>
              <td>{row.is_combo===null?'Sin dato':row.is_combo?'Sí':'No'}</td>
              <td>{fmt(row.gtin)}</td>
              <td>{fmt(row.stock_at_capture)}</td>
              <td><button type="button" disabled={!row.sku||liveBusy}
                onClick={()=>void checkSku(row)}>Consultar API</button></td>
            </tr>)}</tbody>
          </table>
        </div>
        {catalog.total_matches===0&&<p>No se encontraron productos en la copia API para esta búsqueda.</p>}
        <div className="kiki-api-pages">
          <button type="button" disabled={catalogBusy||catalog.page===1} onClick={()=>void search(activeQuery,catalog.page-1)}>← Anterior</button>
          <button type="button" disabled={catalogBusy||!more} onClick={()=>void search(activeQuery,catalog.page+1)}>Siguiente →</button>
        </div>
      </>}
      {liveBusy&&<p>Consultando el SKU directamente en Ecomm-App…</p>}
      {liveError&&<p className="kiki-pilot-warning" role="alert">La consulta directa falló: {liveError}</p>}
      {selected&&live&&<div className="kiki-api-live-result" role="status">
        <h3>Resultado de Ecomm-App para SKU {fmt(selected.sku)}</h3>
        <p>Estado: <strong>{result?.status||'Sin respuesta identificable'}</strong>.
          ID esperado: {fmt(selected.ecomm_id)}.
          {verified?' La API devolvió una coincidencia exacta con el mismo ID.':
            ' No está verificada la correspondencia exacta de SKU e ID; no aplicar cambios.'}</p>
        {verified&&<p>Stock informado ahora por Ecomm-App: <strong>{fmt(result?.matches[0]?.total_stock)}</strong>.
          Es una lectura puntual; no actualiza stock de KIKI ni de los canales.</p>}
      </div>}
    </section>

    <section className="kiki-pilot-summary">
      <h2>3. Qué falta para operar 100 % con la API</h2>
      <p className="kiki-pilot-warning"><strong>Importante:</strong> las pantallas antiguas de
        Productos, Tareas y Preparación ML todavía usan el catálogo histórico. No las
        utilices para dar por actuales stock, precios ni datos de Ecomm-App.
        El nuevo buscador de esta pantalla NO consulta ese Excel.</p>
      <p>Antes de migrar la conciliación y las aprobaciones necesitamos asegurar
        precio, costo, marca y vínculos comerciales desde fuentes válidas; resolver IDs/SKU
        discrepantes; recapturar la API de forma consistente; y probar las decisiones guardadas.
        No se deduce el contenido de un combo por familia SKU.</p>
      <p>Podemos consultar productos reales por API desde hoy, pero no afirmar todavía
        que el sistema completo opera exclusivamente desde ella.</p>
    </section>
  </div>;
}
