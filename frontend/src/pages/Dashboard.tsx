import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {FinalPublicationQueueReport,InventoryLinkageReport,MercadoLibreStatus,Summary} from '../types/catalog';

const emptyMl:MercadoLibreStatus={connected:false,token_expired:false,listing_count:0};
const date=(value?:string)=>value?new Date(value).toLocaleString('es-AR'):'Nunca';

export function Dashboard(){
  const [data,setData]=useState<Summary>({total_products:0,total_listings:0});
  const [ml,setMl]=useState<MercadoLibreStatus>(emptyMl);
  const [linkage,setLinkage]=useState<InventoryLinkageReport|null>(null);
  const [finalQueue,setFinalQueue]=useState<FinalPublicationQueueReport|null>(null);
  const [busy,setBusy]=useState(false);
  const [syncing,setSyncing]=useState(false);
  const [message,setMessage]=useState('');

  async function load(){
    const results=await Promise.allSettled([
      api.dashboard(),
      api.mlStatus(),
      api.inventoryLinkage(),
      api.finalPublicationQueue(),
    ]);
    if(results[0].status==='fulfilled')setData(results[0].value);
    if(results[1].status==='fulfilled')setMl(results[1].value);
    if(results[2].status==='fulfilled')setLinkage(results[2].value);
    if(results[3].status==='fulfilled')setFinalQueue(results[3].value);
  }

  useEffect(()=>{void load().catch(e=>setMessage(e instanceof Error?e.message:'No se pudo cargar el inicio.'))},[]);

  async function analyze(){
    setBusy(true);setMessage('');
    try{await api.analyze('AUTO');await load();setMessage('Catálogo actualizado y analizado correctamente.')}
    catch(e){setMessage(e instanceof Error?e.message:'Error inesperado')}
    finally{setBusy(false)}
  }

  async function connect(){
    try{const {url}=await api.mlAuthUrl();window.location.assign(url)}
    catch(e){setMessage(e instanceof Error?e.message:'Error inesperado')}
  }

  async function sync(){
    setSyncing(true);setMessage('');
    try{const result=await api.mlSync();await load();setMessage(`Sincronización completada: ${result.listing_count} publicaciones.`)}
    catch(e){setMessage(e instanceof Error?e.message:'Error inesperado')}
    finally{setSyncing(false)}
  }

  const ecomm=data.import_diagnostics?.find(item=>item.source==='ECOMM_APP');
  const linkPending=linkage?.summary.review_required??0;
  const linkReady=linkage?.summary.ready_to_link??0;
  const pendingEcomm=linkage?.summary.pending_ecomm_catalog??0;
  const finalReady=finalQueue?.summary.READY_FOR_FINAL_REVIEW??0;
  const finalApproved=finalQueue?.summary.APPROVED_FOR_PUBLICATION??0;

  return <>
    <header className="guided-header"><div><p className="eyebrow">KIKI TECH</p><h1>¿Qué necesita atención?</h1><p>Entrá, actualizá la información y seguí el próximo paso. No necesitás recorrer todas las herramientas.</p></div><Link className="guided-primary-link" to="/imports">Actualizar información</Link></header>
    {message&&<div className="notice">{message}</div>}

    <section className="guided-dashboard-grid">
      <article className="guided-dashboard-card">
        <span className="guided-card-kicker">1 · EMPEZAR</span>
        <h2>Actualizar información</h2>
        <p>Importá Ecomm/EDIMA o sincronizá Mercado Libre cuando haya acceso.</p>
        <div className="guided-card-stats"><span>Ecomm <strong>{Number(data.total_products||0).toLocaleString('es-AR')}</strong></span><span>ML <strong>{Number(data.total_listings||0).toLocaleString('es-AR')}</strong></span></div>
        <Link to="/imports">Actualizar datos</Link>
      </article>

      <article className="guided-dashboard-card">
        <span className="guided-card-kicker">2 · TRABAJAR</span>
        <h2>Resolver pendientes</h2>
        <p>KIKI reúne las decisiones humanas que todavía faltan y las ordena por tipo.</p>
        <div className="guided-card-stats"><span>Vinculación <strong>{linkPending}</strong></span><span>Pendientes Ecomm <strong>{pendingEcomm}</strong></span></div>
        <Link to="/work">Ver pendientes</Link>
      </article>

      <article className="guided-dashboard-card">
        <span className="guided-card-kicker">3 · VINCULAR</span>
        <h2>Vincular con Mercado Libre</h2>
        <p>Para publicaciones que ya existen en ML y necesitan relacionarse correctamente con Ecomm.</p>
        <div className="guided-card-stats"><span>Listas <strong>{linkReady}</strong></span><span>Revisión <strong>{linkPending}</strong></span></div>
        <Link to="/readiness">Ir a vinculación</Link>
      </article>

      <article className="guided-dashboard-card">
        <span className="guided-card-kicker">4 · PUBLICAR</span>
        <h2>Publicar productos nuevos</h2>
        <p>Para productos de Ecomm que todavía no están en ML. Se preparan, validan y aprueban antes del lote.</p>
        <div className="guided-card-stats"><span>Para aprobar <strong>{finalReady}</strong></span><span>Aprobados <strong>{finalApproved}</strong></span></div>
        <Link to="/prepublication">Ir a publicación</Link>
      </article>
    </section>

    <section className="panel daily-routine">
      <div><p className="eyebrow">RUTINA SIMPLE</p><h2>El uso diario de KIKI en cuatro pasos</h2></div>
      <div className="daily-steps"><span><b>1</b> Actualizar datos</span><span><b>2</b> Resolver lo que KIKI marque</span><span><b>3</b> Aprobar lo que esté listo</span><span><b>4</b> Salir</span></div>
    </section>

    <details className="panel advanced-dashboard">
      <summary><strong>Estado técnico y conexiones</strong><span>Solo cuando necesitás revisar fuentes, sincronización o diagnóstico.</span></summary>
      <div className="advanced-dashboard-content">
        <section className="connection compact-connection"><div><p className="eyebrow">ECOMM-APP</p><h2>{ecomm?'Inventario cargado':'Sin importación'}</h2><div className="connection-details"><span>Archivo <strong>{ecomm?.filename||'—'}</strong></span><span>Filas <strong>{ecomm?.rows_accepted??0}</strong></span><span>Productos <strong>{ecomm?.canonical_products??0}</strong></span></div></div></section>
        <section className="connection compact-connection"><div><p className="eyebrow">MERCADO LIBRE</p><h2>{syncing?'Sincronizando…':!ml.connected?'No conectado':ml.token_expired?'Token vencido':'Conectado'}</h2><div className="connection-details"><span>Publicaciones <strong>{ml.listing_count}</strong></span><span>Última sync <strong>{date(ml.last_sync)}</strong></span><span>Token <strong>{date(ml.token_expiration)}</strong></span></div></div><div>{(!ml.connected||ml.token_expired)&&<button onClick={connect}>Conectar / reconectar</button>} {ml.connected&&!ml.token_expired&&<button onClick={sync} disabled={syncing}>{syncing?'Sincronizando…':'Sincronizar ML'}</button>}</div></section>
        <div className="analysis-actions"><button onClick={analyze} disabled={busy}>{busy?'Analizando…':'Analizar catálogo ahora'}</button></div>
        <h3>Diagnóstico de importación</h3>
        {data.import_diagnostics?.length?data.import_diagnostics.map(item=><div className="diagnostic" key={item.source}><h3>{item.source} <small>{item.filename}</small></h3><div className="diagnostic-counts"><span>Leídas <strong>{item.rows_read}</strong></span><span>Aceptadas <strong>{item.rows_accepted}</strong></span><span>Descartadas <strong>{item.rows_discarded}</strong></span>{item.canonical_products!==undefined&&<span>Canónicos <strong>{item.canonical_products}</strong></span>}</div></div>):<p>Todavía no hay importaciones para diagnosticar.</p>}
      </div>
    </details>
  </>;
}
