import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from '../components/KikiIcon';
import type {MercadoLibreStatus} from '../types/catalog';
import type {EcommMlPreview,EcommStageStatus} from '../types/ecomm-app';
import '../client-ux.css';

const n=(x:number|null|undefined)=>x==null?'—':x.toLocaleString('es-AR');
const date=(raw:string|null|undefined)=>{
  if(!raw)return 'No disponible';
  const d=new Date(raw);
  return Number.isNaN(d.getTime())?'No disponible':d.toLocaleString('es-AR');
};

export function Dashboard(){
  const [ecomm,setEcomm]=useState<EcommStageStatus|null>(null);
  const [ml,setMl]=useState<MercadoLibreStatus|null>(null);
  const [preview,setPreview]=useState<EcommMlPreview|null>(null);
  const [loading,setLoading]=useState(true);
  const [errors,setErrors]=useState<string[]>([]);

  async function load(){
    setLoading(true);setErrors([]);
    const results=await Promise.allSettled([
      api.ecommStageStatus(),api.mlStatus(),api.ecommMlPreview(),
    ] as const);
    setEcomm(results[0].status==='fulfilled'?results[0].value:null);
    setMl(results[1].status==='fulfilled'?results[1].value:null);
    setPreview(results[2].status==='fulfilled'?results[2].value:null);
    setErrors(results.flatMap((r,i)=>r.status==='rejected'
      ?[(['Ecomm-App API','Conexión Mercado Libre','Comparación API'][i])+
        ': '+(r.reason instanceof Error?r.reason.message:'No respondió')]
      :[]));
    setLoading(false);
  }
  useEffect(()=>{void load()},[]);

  const summary=preview?.summary;
  const mlConnected=ml?.connected===true&&!ml.token_expired;
  const bars=preview?[
    {id:'PRODUCT_SKU_ONLY',name:'SKU exacto, falta corroboración',count:summary!.PRODUCT_SKU_ONLY,tone:'mint'},
    {id:'PRESENTATION_CONFLICT',name:'Presentaciones diferentes',count:summary!.PRESENTATION_CONFLICT,tone:'rose'},
    {id:'PACK_QUANTITY_EQUIVALENCE_REVIEW',name:'Packs con posible equivalencia',count:summary!.PACK_QUANTITY_EQUIVALENCE_REVIEW,tone:'violet'},
    {id:'INVALID_ML_GTIN',name:'GTIN ML no válido',count:summary!.INVALID_ML_GTIN,tone:'amber'},
    {id:'SKU_NOT_IN_API',name:'SKU no encontrado en Ecomm',count:summary!.SKU_NOT_IN_API,tone:'slate'},
    {id:'NO_ML_SKU',name:'Publicación sin SKU',count:summary!.NO_ML_SKU,tone:'blue'},
    {id:'OTHERS',name:'Otros estados de revisión',
      count:Math.max(0,summary!.ml_api_rows-(
        summary!.PRODUCT_SKU_ONLY+summary!.PRESENTATION_CONFLICT+
        summary!.PACK_QUANTITY_EQUIVALENCE_REVIEW+summary!.INVALID_ML_GTIN+
        summary!.SKU_NOT_IN_API+summary!.NO_ML_SKU)),tone:'grey'},
  ].filter(b=>b.count>0):[];
  const total=summary?.ml_api_rows||0;

  return <div className="kiki-home kiki-client-home">
    <header className="kiki-home-header">
      <div>
        <p className="eyebrow">KIKI TECH · CENTRO DE CONTROL</p>
        <h1>Tu catálogo, más claro.</h1>
        <p>Explorá los productos de Ecomm-App por API y entendé qué pasa
          con las publicaciones guardadas de Mercado Libre, sin tocar las tiendas.</p>
      </div>
      <button type="button" className="kiki-refresh" disabled={loading} onClick={()=>void load()}>
        <KikiIcon name="refresh" size={16}/> {loading?'Consultando…':'Actualizar'}
      </button>
    </header>

    <div className="kiki-client-status" role="status">
      <span className={'kiki-status-pill '+(ecomm?.complete?'good':'caution')}>
        <KikiIcon name={ecomm?.complete?'check':'alert'} size={15}/>
        {loading?'Validando origen API':ecomm?.complete?'Ecomm API: copia completa':'Ecomm API: comprobar'}
      </span>
      <span className={'kiki-status-pill '+(mlConnected?'good':'caution')}>
        <KikiIcon name={mlConnected?'link':'clock'} size={15}/>
        {mlConnected?'ML conectado':'ML pendiente de conexión'}
      </span>
      <span className="kiki-status-caption">Consultas de solo lectura · No hay publicaciones automáticas</span>
    </div>
    {errors.length>0&&<div role="alert" className="kiki-client-alert">
      <KikiIcon name="alert"/><span>Algunos datos no están disponibles. No se interpretan como cero:
        {errors.join(' · ')}</span>
    </div>}

    <section aria-label="Indicadores desde la API" className="kiki-client-stats">
      <article className="kiki-client-stat">
        <span className="kiki-stat-icon"><KikiIcon name="box"/></span>
        <small>Variantes Ecomm por API</small>
        <strong>{loading?'…':ecomm?.complete?n(ecomm.quality.variants):'—'}</strong>
        <span>{ecomm?.complete?ecomm.pages_saved+'/'+(ecomm.expected_pages??'?')+' páginas capturadas por API':'Copia API no verificada'}</span>
      </article>
      <article className="kiki-client-stat">
        <span className="kiki-stat-icon"><KikiIcon name="store"/></span>
        <small>Filas ML en la copia API</small>
        <strong>{loading?'…':n(summary?.ml_api_rows)}</strong>
        <span>{preview?'Copia guardada, no sincronizada en vivo':'Comparación no disponible'}</span>
      </article>
      <article className="kiki-client-stat kiki-stat-primary">
        <span className="kiki-stat-icon"><KikiIcon name="link"/></span>
        <small>SKU con un candidato único</small>
        <strong>{loading?'…':n(summary?.exact_unique_sku_candidates)}</strong>
        <span>Coincidencias para revisar, no aprobadas</span>
      </article>
      <article className="kiki-client-stat">
        <span className="kiki-stat-icon"><KikiIcon name="alert"/></span>
        <small>Presentaciones a verificar</small>
        <strong>{loading?'…':summary?n(summary.PRESENTATION_CONFLICT+summary.PACK_QUANTITY_EQUIVALENCE_REVIEW):'—'}</strong>
        <span>Incompatibles o packs con posible equivalencia</span>
      </article>
    </section>

    <section className="kiki-client-journey" aria-label="Acciones principales">
      <div className="kiki-client-section-title"><p className="eyebrow">EMPEZÁ POR ACÁ</p>
        <h2>¿Qué querés hacer?</h2></div>
      <div className="kiki-client-actions">
        <Link to="/pilot#catalogo" className="kiki-client-action">
          <span className="kiki-action-icon"><KikiIcon name="search" size={25}/></span>
          <span><strong>Buscar un producto</strong><small>Consultá SKU, ID, combo y stock leído de Ecomm-App.</small></span>
          <KikiIcon name="arrow-right"/>
        </Link>
        <Link to="/pilot#comparacion" className="kiki-client-action">
          <span className="kiki-action-icon"><KikiIcon name="chart" size={25}/></span>
          <span><strong>Analizar Mercado Libre</strong><small>Examiná coincidencias y diferencias entre las dos copias API.</small></span>
          <KikiIcon name="arrow-right"/>
        </Link>
        <Link to="/channels" className="kiki-client-action">
          <span className="kiki-action-icon"><KikiIcon name="store" size={25}/></span>
          <span><strong>Ver canales de venta</strong><small>Consultá el estado de Mercado Libre y Tiendanube.</small></span>
          <KikiIcon name="arrow-right"/>
        </Link>
      </div>
    </section>

    <section className="kiki-client-data-panel">
      <div className="kiki-client-panel-head"><div>
        <p className="eyebrow">DIAGNÓSTICO DE MERCADO LIBRE</p>
        <h2>Así se distribuyen las publicaciones</h2>
        <p>Una fila se cuenta una sola vez, según el motivo principal encontrado.</p></div>
        <Link to="/pilot#comparacion" className="kiki-client-text-link">Ver casos concretos <KikiIcon name="arrow-right" size={17}/></Link>
      </div>
      {preview&&total>0?
        <div className="kiki-client-chart">
          <div className="kiki-client-chart-line" role="img"
            aria-label={bars.map(b=>b.name+': '+n(b.count)).join('; ')}>
            {bars.map(b=><span key={b.id} className={'tone-'+b.tone}
              style={{width:(100*b.count/total)+'%'}} title={b.name+': '+n(b.count)}/>)}
          </div>
          <div className="kiki-client-legend">
            {bars.map(b=><div key={b.id}>
              <span className={'kiki-chart-dot tone-'+b.tone}/><span>{b.name}</span>
              <strong>{n(b.count)}</strong><small>{(100*b.count/total).toLocaleString('es-AR',{maximumFractionDigits:1})}%</small>
            </div>)}
          </div>
        </div>:
        <div className="kiki-client-empty"><KikiIcon name="chart" size={27}/>
          <p>{loading?'Cargando análisis API…':'Sin diagnóstico disponible. La comparación requiere las dos copias API guardadas.'}</p>
          <Link to="/pilot#comparacion">Abrir diagnóstico</Link>
        </div>}
      {preview&&<p className="kiki-client-chart-foot">
        Fuente Ecomm: {date(preview.ecomm_last_capture_at)} · Copia ML: {date(preview.ml_snapshot_updated_at)}.
        No son datos en tiempo real ni confirman vínculos.
      </p>}
    </section>

    <section className="kiki-client-next">
      <div className="kiki-client-next-icon"><KikiIcon name="shield" size={27}/></div>
      <div><h2>Ya se puede explorar KIKI. La publicación sigue protegida.</h2>
        <p>Guillermo y Mercedes pueden buscar productos, consultar la API y recorrer el diagnóstico.
          Los módulos antiguos de Productos, Tareas y preparación siguen dependiendo de Excel;
          los mantenemos separados hasta completar la migración.</p></div>
      <Link to="/pilot" className="kiki-main-action">Abrir centro API <KikiIcon name="arrow-right" size={16}/></Link>
    </section>

    <p className="kiki-home-footnote">La próxima conexión de Mercado Libre debe autorizarla el titular.
      Mientras tanto, KIKI presenta la última copia API de ML como histórica.
      No se modifica inventario, publicaciones ni decisiones guardadas desde estas pantallas.</p>
  </div>;
}
