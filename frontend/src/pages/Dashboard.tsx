import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {FinalPublicationQueueReport,InventoryLinkageReport,MercadoLibreStatus,Summary,ReadinessReport} from '../types/catalog';

const count=(value?:number|null)=>value==null?'—':value.toLocaleString('es-AR');
const date=(value?:string)=>value?new Date(value).toLocaleString('es-AR'):'Sin registro';

export function Dashboard(){
  const [data,setData]=useState<Summary|null>(null);
  const [ml,setMl]=useState<MercadoLibreStatus|null>(null);
  const [linkage,setLinkage]=useState<InventoryLinkageReport|null>(null);
  const [finalQueue,setFinalQueue]=useState<FinalPublicationQueueReport|null>(null);
  const [readiness,setReadiness]=useState<ReadinessReport|null>(null);
  const [tn,setTn]=useState<Awaited<ReturnType<typeof api.tiendanubeReport>>|null>(null);
  const [tnStatus,setTnStatus]=useState<'loading'|'available'|'unavailable'>('loading');
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [syncing,setSyncing]=useState(false);
  const [message,setMessage]=useState('');

  async function load(){
    setLoading(true);
    const results=await Promise.allSettled([
      api.dashboard(),
      api.mlStatus(),
      api.inventoryLinkage(),
      api.finalPublicationQueue(),
      api.publicationReadiness(),
      api.tiendanubeReport(),
    ]);
    setData(results[0].status==='fulfilled'?results[0].value:null);
    setMl(results[1].status==='fulfilled'?results[1].value:null);
    setLinkage(results[2].status==='fulfilled'?results[2].value:null);
    setFinalQueue(results[3].status==='fulfilled'?results[3].value:null);
    setReadiness(results[4].status==='fulfilled'?results[4].value:null);
    setTn(results[5].status==='fulfilled'?results[5].value:null);
    setTnStatus(results[5].status==='fulfilled'?'available':'unavailable');
    setLoading(false);
  }
  useEffect(()=>{void load().catch(e=>{setLoading(false);setMessage(e instanceof Error?e.message:'No se pudo actualizar el inicio.')})},[]);

  async function analyze(){
    setBusy(true);setMessage('');
    try{await api.analyze('AUTO');await load();setMessage('Catálogo analizado. Los indicadores se actualizaron.')}
    catch(e){setMessage(e instanceof Error?e.message:'No se pudo analizar el catálogo.')}
    finally{setBusy(false)}
  }
  async function connect(){
    try{const {url}=await api.mlAuthUrl();window.location.assign(url)}
    catch(e){setMessage(e instanceof Error?e.message:'No se pudo conectar Mercado Libre.')}
  }
  async function sync(){
    setSyncing(true);setMessage('');
    try{const result=await api.mlSync();await load();setMessage(`Sincronización finalizada: ${result.listing_count} publicaciones.`)}
    catch(e){setMessage(e instanceof Error?e.message:'No se pudo sincronizar Mercado Libre.')}
    finally{setSyncing(false)}
  }

  const ecomm=data?.import_diagnostics?.find(item=>item.source==='ECOMM_APP');
  const mlImport=data?.import_diagnostics?.find(item=>item.source==='MERCADOLIBRE');
  const mlSnapshot=Boolean(mlImport||ml?.last_sync||(data?.total_listings||0)>0);
  const tnImported=tnStatus==='available'&&tn?.available===true;
  const readyCount=finalQueue?.summary.READY_FOR_FINAL_REVIEW;
  const reviewCount=readiness?.summary.REVIEW_REQUIRED;
  const linkageCount=linkage?.available?linkage.summary.review_required:null;
  const next=!ecomm
    ? {eyebrow:'PRIMER PASO',title:'Cargar el catálogo de Ecomm-App',description:'Importá la fuente principal para que KIKI pueda comparar productos y preparar las revisiones.',to:'/imports',cta:'Actualizar información'}
    : reviewCount!=null&&reviewCount>0
    ? {eyebrow:'SIGUIENTE ACCIÓN',title:'Resolver los productos que necesitan revisión',description:'Hay fichas que todavía requieren completar o verificar información antes de avanzar con Mercado Libre.',to:'/work',cta:'Ver tareas pendientes'}
    : readyCount!=null&&readyCount>0
    ? {eyebrow:'SIGUIENTE ACCIÓN',title:'Revisar los productos preparados para ML',description:'Tenés productos listos para una revisión final interna. Todavía no se publican en Mercado Libre.',to:'/prepublication',cta:'Ver productos preparados'}
    : {eyebrow:'SIGUIENTE PASO',title:'Elegí dónde querés trabajar',description:'Consultá las tareas o revisá el estado de Mercado Libre y Tiendanube desde Canales de venta.',to:'/channels',cta:'Ver canales de venta'};
  const kpis=[
    {label:'Productos en Ecomm',value:ecomm?count(data?.total_products):'—',detail:ecomm?'Catálogo importado':'Falta cargar o verificar fuente'},
    {label:'Publicaciones ML',value:mlSnapshot?count(data?.total_listings):'—',detail:'Último catálogo registrado, no en vivo'},
    {label:'Productos Tiendanube',value:tnImported?count(tn?.summary.products):'—',detail:tnStatus==='unavailable'?'No se pudieron consultar':tnImported?'CSV importado':'Sin catálogo disponible'},
    {label:'Para revisar antes de ML',value:count(reviewCount),detail:'Revisión previa a publicación; no todas las tareas'},
  ];

  return <div className="kiki-home">
    <header className="kiki-home-header">
      <div>
        <p className="eyebrow">KIKI TECH · VISTA GENERAL</p>
        <h1>Tu catálogo, en una sola mirada.</h1>
        <p>Lo importante primero: qué tenés, qué necesita atención y dónde continuar.</p>
      </div>
      <button type="button" className="kiki-refresh" disabled={loading} onClick={()=>void load()}>{loading?'Actualizando…':'↻ Actualizar datos'}</button>
    </header>
    {message&&<div className="notice" role="status">{message}</div>}
    {!loading&&!data&&<div className="notice warning" role="alert">No se pudo consultar el resumen del catálogo. Podés volver a intentar con «Actualizar datos». Los valores no disponibles se muestran con —.</div>}

    <section className="kiki-metrics" aria-label="Indicadores del catálogo">
      {kpis.map(item=><article className="kiki-metric" key={item.label}>
        <small>{item.label}</small>
        <strong>{loading?'…':item.value}</strong>
        <span>{item.detail}</span>
      </article>)}
    </section>

    <div className="kiki-home-columns">
      <section className="kiki-feature-panel">
        <p className="eyebrow">{next.eyebrow}</p>
        <h2>{next.title}</h2>
        <p>{next.description}</p>
        <Link className="kiki-main-action" to={next.to}>{next.cta} <span aria-hidden="true">→</span></Link>
      </section>
      <section className="kiki-task-panel">
        <div className="kiki-panel-heading">
          <div><p className="eyebrow">TRABAJO DIARIO</p><h2>Accesos rápidos</h2></div>
          <Link to="/work">Todas las tareas →</Link>
        </div>
        <Link className="kiki-quick-row" to="/work"><span className="kiki-row-symbol" aria-hidden="true">✓</span><span><strong>Resolver pendientes</strong><small>Marcas, códigos y datos que faltan comprobar</small></span><b>→</b></Link>
        <Link className="kiki-quick-row" to="/readiness"><span className="kiki-row-symbol" aria-hidden="true">⇄</span><span><strong>Revisar vinculaciones ML</strong><small>{linkageCount==null?'Consultar estado':`${count(linkageCount)} casos necesitan revisión`}</small></span><b>→</b></Link>
        <Link className="kiki-quick-row" to="/tiendanube"><span className="kiki-row-symbol" aria-hidden="true">✧</span><span><strong>Mejorar fichas Tiendanube</strong><small>Revisar propuestas comerciales de KIKI AI</small></span><b>→</b></Link>
      </section>
    </div>

    <section className="kiki-sources-panel">
      <div className="kiki-panel-heading">
        <div><p className="eyebrow">FUENTES DE INFORMACIÓN</p><h2>Estado de tus catálogos</h2></div>
        <Link to="/channels">Ver canales →</Link>
      </div>
      <div className="kiki-sources-grid">
        <article><div className="kiki-source-head"><strong>Ecomm-App</strong><span className={ecomm?'kiki-source-pill is-ok':'kiki-source-pill'}>{ecomm?'Importado':'Sin confirmar'}</span></div><p>Base de productos para comparar.</p><small>{ecomm?.filename||'No hay una importación registrada en el resumen.'}</small></article>
        <article><div className="kiki-source-head"><strong>Mercado Libre</strong><span className={ml?.connected&&!ml.token_expired?'kiki-source-pill is-ok':'kiki-source-pill'}>{ml===null?'No disponible':ml.connected&&!ml.token_expired?'API conectada':ml.token_expired?'Requiere reconectar':'API sin conectar'}</span></div><p>Publicaciones y vinculación con inventario.</p><small>{mlSnapshot?`Último registro: ${count(data?.total_listings)} publicaciones`:'Sin publicaciones verificables en el resumen.'}</small></article>
        <article><div className="kiki-source-head"><strong>Tiendanube</strong><span className={tnImported?'kiki-source-pill is-ok':'kiki-source-pill'}>{tnStatus==='unavailable'?'No disponible':tnImported?'CSV importado':'Sin CSV'}</span></div><p>Catálogo para conciliar y mejorar fichas.</p><small>{tnImported?`${count(tn?.summary.products)} productos en el CSV · no es conexión en vivo`:'No se confirmó un catálogo importado.'}</small></article>
      </div>
    </section>

    <details className="kiki-diagnostics-panel">
      <summary><span><strong>Diagnóstico y conexiones</strong><small>Opciones técnicas para cuando las necesites</small></span><span aria-hidden="true">⌄</span></summary>
      <div className="kiki-diagnostics-content">
        <p><strong>Ecomm:</strong> {ecomm?.filename||'Sin archivo registrado'} · <strong>Última sincronización ML:</strong> {date(ml?.last_sync)}</p>
        <p><strong>Preparación ML:</strong> {count(readyCount)} para revisión final · {count(finalQueue?.summary.APPROVED_FOR_PUBLICATION)} aprobados internamente. Los indicadores pueden referirse a conjuntos distintos y no deben sumarse.</p>
        <div className="kiki-diagnostic-actions">
          <Link className="secondary-link" to="/imports">Importar datos</Link>
          <button type="button" disabled={busy} onClick={()=>void analyze()}>{busy?'Analizando…':'Reanalizar catálogo'}</button>
          {ml&&(!ml.connected||ml.token_expired)&&<button type="button" className="secondary" onClick={()=>void connect()}>Reconectar Mercado Libre</button>}
          {ml?.connected&&!ml.token_expired&&<button type="button" disabled={syncing} onClick={()=>void sync()}>{syncing?'Sincronizando…':'Sincronizar Mercado Libre'}</button>}
        </div>
      </div>
    </details>
    <p className="kiki-home-footnote">KIKI trabaja con la información importada y las conexiones habilitadas. Aprobar una ficha o preparación no publica automáticamente productos en los canales externos.</p>
  </div>;
}
