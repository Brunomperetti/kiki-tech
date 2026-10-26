import {FormEvent,useEffect,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from '../components/KikiIcon';
import type {EcommMlCase,EcommMlCases,EcommMlPreviewStatus} from '../types/ecomm-app';
import '../cases.css';

const statuses:{key:EcommMlPreviewStatus;name:string;why:string;group:'risk'|'review'|'lead'}[]=[
  {key:'PRESENTATION_CONFLICT',name:'Presentación diferente',why:'El SKU coincide, pero las presentaciones necesitan revisión',group:'risk'},
  {key:'PACK_QUANTITY_EQUIVALENCE_REVIEW',name:'Pack con posible equivalencia',why:'Las cantidades podrían expresarse por unidad o por total',group:'review'},
  {key:'INVALID_ML_GTIN',name:'GTIN de ML a revisar',why:'El código de ML no supera la validación disponible',group:'risk'},
  {key:'SKU_NOT_IN_API',name:'SKU que no aparece en Ecomm',why:'No encontramos una variante API con ese SKU exacto',group:'risk'},
  {key:'NO_ML_SKU',name:'Publicación sin SKU',why:'No hay identificador de producto para comparar',group:'risk'},
  {key:'PRODUCT_SKU_ONLY',name:'SKU exacto, falta corroborar',why:'Hay un único ID candidato pero no prueba definitiva',group:'lead'},
  {key:'GTIN_CONFLICT',name:'GTIN contradictorio',why:'SKU exacto con códigos GTIN válidos diferentes',group:'risk'},
  {key:'SHARED_GTIN',name:'GTIN compartido',why:'Un GTIN está asociado a varias variantes API',group:'review'},
  {key:'DUPLICATE_API_SKU',name:'SKU duplicado en Ecomm',why:'El mismo SKU identifica más de una variante',group:'risk'},
  {key:'SKU_ONLY_REVIEW',name:'SKU de variante exacto',why:'Falta corroboración adicional de la variante',group:'lead'},
  {key:'SKU_GTIN_AGREE_REVIEW',name:'SKU y GTIN compatibles',why:'Son pistas compatibles pero no equivalen a una vinculación aprobada',group:'lead'},
  {key:'INVALID_ECOMM_GTIN',name:'GTIN de Ecomm a revisar',why:'El código de Ecomm no supera la validación disponible',group:'risk'},
  {key:'NO_EXPLICIT_VARIANT_SKU',name:'Variación sin SKU propio',why:'No usamos el SKU padre para identificar una variación',group:'risk'},
];
const fmt=(x:number)=>x.toLocaleString('es-AR');
const date=(x:string|null)=>{
  if(!x)return 'Sin fecha';
  const parsed=new Date(x);
  return Number.isNaN(parsed.valueOf())?'Sin fecha':parsed.toLocaleString('es-AR');
};
const val=(s:string|null|undefined)=>s?.trim()||'No informado';
const label=(status:string)=>statuses.find(x=>x.key===status)?.name||status;
const group=(status:string)=>statuses.find(x=>x.key===status)?.group||'review';
const msg=(e:unknown)=>e instanceof Error?e.message:'Error al consultar la información.';
const summaryText=(item:EcommMlCase)=>
  `KIKI TECH · REVISIÓN DE CASO (SOLO LECTURA)
Estado: ${label(item.status)}
Mercado Libre: ${item.mla} · SKU: ${val(item.ml_variant_sku||item.ml_product_sku)}
Producto ML: ${item.ml_title}
Ecomm API: ID ${val(item.api_ecomm_id)} · SKU ${val(item.api_sku)}
Producto Ecomm: ${val(item.api_name)}
¿Combo?: ${item.api_is_combo===true?'Sí':item.api_is_combo===false?'No':'Sin dato'}
Motivo: ${item.reason}
FUENTES: Copias API guardadas, sin actualización en tiempo real.
No representa una aprobación, vinculación ni modificación de stock.`;

export function CaseExplorer(){
  const [params,setParams]=useSearchParams();
  const status=params.get('status')||'PRESENTATION_CONFLICT';
  const q=params.get('q')||'';
  const page=Math.max(1,Number(params.get('page')||1)||1);
  const [entry,setEntry]=useState(q);
  const [report,setReport]=useState<EcommMlCases|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [selected,setSelected]=useState<string|null>(null);
  const [copyStatus,setCopyStatus]=useState('');

  function navigate(nextStatus:string,nextQ:string,nextPage:number){
    setParams({status:nextStatus,q:nextQ,page:String(nextPage)});
  }
  useEffect(()=>{
    setEntry(q);
    setLoading(true);setError('');
    let active=true;
    api.ecommMlCases(status,q,page,20).then(data=>{
      if(active){setReport(data);setSelected(null)}
    }).catch(e=>{
      if(active){setReport(null);setError(msg(e))}
    }).finally(()=>{if(active)setLoading(false)});
    return ()=>{active=false};
  },[status,q,page]);

  const items=report?.cases.items||[];
  const current=items.find(x=>x.mla===selected)||items[0]||null;
  const total=report?.cases.total||0;
  const from=total>0?(page-1)*20+1:0;
  const to=Math.min(total,page*20);
  const chosen=statuses.find(x=>x.key===status);
  const allCount=report?.summary.ml_api_rows??null;

  function submit(e:FormEvent){e.preventDefault();navigate(status,entry.trim(),1)}
  async function copy(){
    if(!current)return;
    setCopyStatus('');
    try{
      await navigator.clipboard.writeText(summaryText(current));
      setCopyStatus('Resumen copiado para compartir.');
    }catch{
      setCopyStatus('No se pudo copiar automáticamente. Podés seleccionar el texto del caso.');
    }
  }
  return <div className="kiki-cases">
    <header className="kiki-home-header kiki-cases-header">
      <div>
        <p className="eyebrow">KIKI TECH · INTELIGENCIA DE CATÁLOGO</p>
        <h1>Centro de casos reales</h1>
        <p>Encontrá una publicación, compará sus identificadores y entendé qué detectó KIKI.
          Todo proviene de las copias API, sin modificar ningún producto.</p>
      </div>
      <Link className="kiki-case-back" to="/"><KikiIcon name="home" size={16}/> Volver al inicio</Link>
    </header>
    <div className="kiki-cases-steps" aria-label="Cómo utilizar el centro de casos">
      <div><span>01</span><strong>Elegí un problema</strong><small>Filtrá los casos del diagnóstico.</small></div>
      <div><span>02</span><strong>Compará ambas fichas</strong><small>Identificá la evidencia y el riesgo.</small></div>
      <div><span>03</span><strong>Verificá en Ecomm</strong><small>Consultá el SKU directo por API si es necesario.</small></div>
    </div>
    <div className="kiki-cases-freshness" role="note">
      <KikiIcon name="clock" size={19}/>
      <span><strong>Datos para evaluación.</strong> Ecomm: {date(report?.ecomm_last_capture_at||null)} ·
        Mercado Libre: {date(report?.ml_snapshot_updated_at||null)}.
        La conexión de ML debe renovarse antes de operar o publicar.</span>
    </div>
    {error&&<div className="notice warning" role="alert">No pudimos cargar los casos: {error}</div>}
    <section className="kiki-cases-browser">
      <div className="kiki-cases-browser-head">
        <div><p className="eyebrow">EXPLORAR EL DIAGNÓSTICO</p>
          <h2>De los datos a los problemas concretos</h2>
          <p>Los conteos corresponden a filas ML; no equivalen a productos listos para publicar.</p>
        </div>
        <div className="kiki-cases-allcount">{allCount===null?'—':fmt(allCount)}<small>filas del análisis</small></div>
      </div>
      <form className="kiki-cases-search" onSubmit={submit}>
        <label htmlFor="case-search">Buscar SKU, publicación, ID Ecomm o título</label>
        <div><input id="case-search" maxLength={80} value={entry}
          onChange={e=>setEntry(e.target.value)} placeholder="Ej.: 2500400 o Magnesio"/>
          <button type="submit"><KikiIcon name="search" size={17}/> Buscar</button></div>
      </form>
      <div className="kiki-cases-filters" role="group" aria-label="Filtrar casos por diagnóstico">
        {statuses.map(c=><button type="button" key={c.key}
          className={'kiki-cases-chip '+(c.key===status?'active':'')}
          aria-pressed={c.key===status}
          onClick={()=>navigate(c.key,q,1)}>
          <span className={'case-indicator '+c.group}/>
          {c.name}
          <b>{report?fmt(report.summary[c.key]):'·'}</b>
        </button>)}
      </div>
      <div className="kiki-cases-selection">
        <span className={'case-indicator '+(chosen?.group||'review')}/>
        <div><strong>{chosen?.name||'Casos del catálogo'}</strong>
          <p>{chosen?.why||'Seleccioná un motivo para explorar los casos.'}</p></div>
        <span>{loading?'Consultando…':`${fmt(from)}–${fmt(to)} de ${fmt(total)}`}</span>
      </div>
      <div className="kiki-cases-two-col">
        <div className="kiki-cases-list" aria-label="Casos encontrados">
          {loading&&<p className="kiki-cases-empty">Cargando casos y evidencia…</p>}
          {!loading&&items.length===0&&<p className="kiki-cases-empty">No se encontraron casos con este filtro.
            Probá con otro motivo o buscá un SKU distinto.</p>}
          {!loading&&items.map(item=><button type="button" key={item.mla}
            onClick={()=>{setSelected(item.mla);setCopyStatus('')}}
            className={'kiki-cases-item '+(current?.mla===item.mla?'active':'')}>
            <span className="kiki-cases-item-top"><strong>{val(item.ml_variant_sku||item.ml_product_sku)}</strong>
              <small>{item.mla}</small></span>
            <span className="kiki-cases-item-name">{item.ml_title}</span>
            <span className="kiki-cases-item-bottom">
              {item.api_ecomm_id?'Coincidencia por SKU · ID '+item.api_ecomm_id:'Sin ID Ecomm confirmado'}
              <KikiIcon name="arrow-right" size={15}/></span>
          </button>)}
          <div className="kiki-cases-pages">
            <button type="button" disabled={loading||page<=1}
              onClick={()=>navigate(status,q,page-1)}>← Anterior</button>
            <span>Página {page}</span>
            <button type="button" disabled={loading||page*20>=total}
              onClick={()=>navigate(status,q,page+1)}>Siguiente →</button>
          </div>
        </div>
        <aside className="kiki-cases-detail" aria-live="polite">
          {current?<div className="kiki-cases-detail-inner">
            <span className={'kiki-cases-detail-badge '+group(current.status)}>
              <KikiIcon name="alert" size={16}/>{label(current.status)}
            </span>
            <h3>¿Qué encontró KIKI?</h3>
            <p className="kiki-case-explanation">{current.reason}</p>
            <div className="kiki-cases-compare">
              <div>
                <span className="kiki-cases-label">MERCADO LIBRE</span>
                <h4>{current.ml_title}</h4>
                <dl><dt>Publicación</dt><dd>{val(current.mla)}</dd>
                  <dt>SKU informado</dt><dd>{val(current.ml_variant_sku||current.ml_product_sku)}</dd>
                  <dt>GTIN</dt><dd>{val(current.ml_gtin)}</dd></dl>
              </div>
              <div>
                <span className="kiki-cases-label">ECOMM-APP · API</span>
                <h4>{val(current.api_name)}</h4>
                <p className="kiki-cases-variant">{current.api_variant_description||''}</p>
                <dl><dt>ID variante</dt><dd>{val(current.api_ecomm_id)}</dd>
                  <dt>SKU</dt><dd>{val(current.api_sku)}</dd>
                  <dt>GTIN</dt><dd>{val(current.api_gtin)}</dd>
                  <dt>¿Combo?</dt><dd>{current.api_is_combo===true?'Sí':current.api_is_combo===false?'No':'No informado'}</dd></dl>
              </div>
            </div>
            <div className="kiki-cases-detail-actions">
              {current.api_sku&&<Link className="kiki-case-primary"
                to={'/pilot?sku='+encodeURIComponent(current.api_sku)+'#catalogo'}>
                <KikiIcon name="search" size={17}/> Consultar en Ecomm API
              </Link>}
              {current.api_ecomm_id&&<Link className="kiki-case-primary"
                to={'/workspace?id='+encodeURIComponent(current.api_ecomm_id)}>
                <KikiIcon name="check" size={17}/> Revisar y mejorar ficha candidata en KIKI
              </Link>}
              <button type="button" onClick={()=>void copy()}>
                <KikiIcon name="layers" size={17}/> Copiar resumen del caso
              </button>
            </div>
            {copyStatus&&<p role="status" className="kiki-cases-copy">{copyStatus}</p>}
            <p className="kiki-cases-disclaimer"><KikiIcon name="shield" size={16}/>
              Abrir una ficha candidata no confirma la identidad entre ML y Ecomm-App.
              Verificá SKU, presentación y composición antes de guardar. Los cambios se
              conservan solo dentro de KIKI: no corrigen automáticamente una publicación
              de Mercado Libre ni modifican Ecomm-App, GTIN, precios o stock.
            </p>
          </div>:<div className="kiki-cases-empty">
            <KikiIcon name="search" size={28}/><p>Elegí un caso para ver las fichas lado a lado.</p>
          </div>}
        </aside>
      </div>
    </section>
  </div>;
}
