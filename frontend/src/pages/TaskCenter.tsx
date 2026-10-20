import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';

type Readiness = Awaited<ReturnType<typeof api.publicationReadiness>>;
type Linkage = Awaited<ReturnType<typeof api.inventoryLinkage>>;
type FinalQueue = Awaited<ReturnType<typeof api.finalPublicationQueue>>;
type Brands = Awaited<ReturnType<typeof api.enrichmentReviewQueue>>;
type Quality = Awaited<ReturnType<typeof api.tiendanubeQualityAudit>>;
type Commercial = Awaited<ReturnType<typeof api.tiendanubeCommercialProposals>>;

type State={
  readiness:Readiness|null;
  linkage:Linkage|null;
  finalQueue:FinalQueue|null;
  brands:Brands|null;
  quality:Quality|null;
  commercial:Commercial|null;
};
type Channel='ECOMM'|'ML'|'TN';
type Task={
  id:string;
  channel:Channel;
  title:string;
  description:string;
  count:number|null;
  unit:string;
  href:string;
  cta:string;
  examples:string[];
  priority:number;
  caution?:string;
};
const empty:State={readiness:null,linkage:null,finalQueue:null,brands:null,quality:null,commercial:null};
const number=(n:number|null)=>n===null?'—':n.toLocaleString('es-AR');
const twoNames=(items:string[])=>items.filter(Boolean).slice(0,2);
const channelName:Record<Channel,string>={ECOMM:'Ecomm-App',ML:'Mercado Libre',TN:'Tiendanube'};

/** Counts belong to separate workflows and may refer to the same products.
 * Never sum them into an invented unique backlog or business priority score. */
export function buildTaskCenter(data:State):Task[]{
  const r=data.readiness;
  const l=data.linkage;
  const q=data.finalQueue;
  const b=data.brands;
  const tn=data.quality;
  const commercial=data.commercial;
  const rAvailable=Boolean(r&&r.reconciliation_run_id>0);
  const lAvailable=Boolean(l?.available);
  const tnAvailable=Boolean(tn?.available);
  const commercialAvailable=Boolean(commercial?.available);
  return [
    {
      id:'core',channel:'ECOMM',priority:1,
      title:'Completar datos de productos',
      description:'Revisá información que impide preparar correctamente las fichas para Mercado Libre: marca, identificadores u otros datos centrales.',
      count:rAvailable?r!.summary.REVIEW_REQUIRED:null,unit:'productos en revisión',
      href:'/work/details?focus=data',cta:'Resolver datos',
      examples:twoNames((r?.items||[]).filter(x=>x.readiness_status==='REVIEW_REQUIRED').map(x=>x.product.name||x.product.sku||'')),
      caution:'El indicador proviene de la preparación ML y puede coincidir con otras tareas.',
    },
    {
      id:'linkage',channel:'ML',priority:2,
      title:'Revisar vínculos con el inventario',
      description:'Hay publicaciones existentes cuya relación con el catálogo Ecomm-App necesita comprobación.',
      count:lAvailable?l!.summary.review_required:null,unit:'casos a revisar',
      href:'/readiness',cta:'Revisar vínculos',
      examples:twoNames((l?.items||[]).filter(x=>x.status!=='READY_TO_LINK').map(x=>x.title||x.external_id||'')),
      caution:'No confirma vinculación ni cambia inventario externo.',
    },
    {
      id:'tn-quality',channel:'TN',priority:3,
      title:'Verificar datos de Tiendanube',
      description:'Identificá fichas con datos faltantes o códigos que requieren revisión antes de optimizarlas.',
      count:tnAvailable?tn!.summary.requiring_review??null:null,unit:'fichas con observaciones',
      href:'/tiendanube',cta:'Revisar catálogo TN',
      examples:twoNames((tn?.items||[]).filter(x=>x.issues.length>0).sort((a,c)=>(a.priority==='HIGH'?0:1)-(c.priority==='HIGH'?0:1)).map(x=>x.name||x.sku)),
      caution:'Es un diagnóstico del CSV; no verifica automáticamente datos del fabricante ni imágenes.',
    },
    {
      id:'brand',channel:'ECOMM',priority:4,
      title:'Revisar marcas sugeridas',
      description:'KIKI propone marcas basadas en evidencia disponible. Confirmalas solamente cuando corresponda.',
      count:b&&b.reconciliation_run_id>0?b.summary.PENDING:null,unit:'propuestas pendientes',
      href:'/work/details?focus=brands',cta:'Revisar marcas',
      examples:twoNames((b?.items||[]).filter(x=>x.review_status==='PENDING').map(x=>x.product.name||x.product.sku||'')),
      caution:'Pueden ser productos que ya figuran en la revisión de datos centrales.',
    },
    {
      id:'final',channel:'ML',priority:5,
      title:'Revisar productos preparados para ML',
      description:'Comprobá qué productos pueden recibir una aprobación interna para un futuro lote y cuáles necesitan nueva validación.',
      count:q?rCount(q.summary.READY_FOR_FINAL_REVIEW,q.summary.STALE_APPROVAL):null,unit:'preparaciones para revisar',
      href:'/prepublication',cta:'Ver preparación ML',
      examples:twoNames((q?.items||[]).filter(x=>x.queue_status==='READY_FOR_FINAL_REVIEW'||x.queue_status==='STALE_APPROVAL').map(x=>x.product?.name||x.preview?.title||'')),
      caution:'Aprobar internamente no publica productos en Mercado Libre.',
    },
    {
      id:'tn-copy',channel:'TN',priority:6,
      title:'Mejorar títulos y descripciones',
      description:'Revisá sugerencias comerciales generadas desde los datos del CSV y accedé a los borradores de KIKI AI.',
      count:commercialAvailable?commercial!.summary.proposals:null,unit:'propuestas comerciales',
      href:'/tiendanube',cta:'Revisar propuestas TN',
      examples:twoNames((commercial?.items||[]).map(x=>x.original_name)),
      caution:'Estas cifras son propuestas del catálogo, no borradores generados por OpenAI.',
    },
  ];
}

function rCount(first:number,second:number){return first+second}

export function TaskCenter(){
  const [data,setData]=useState<State>(empty);
  const [loaded,setLoaded]=useState(false);
  const [loading,setLoading]=useState(true);
  const [message,setMessage]=useState('');
  const [filter,setFilter]=useState<'ALL'|Channel>('ALL');

  async function load(){
    setLoading(true);
    setMessage('');
    const result=await Promise.allSettled([
      api.publicationReadiness(),
      api.inventoryLinkage(),
      api.finalPublicationQueue(),
      api.enrichmentReviewQueue(),
      api.tiendanubeQualityAudit(),
      api.tiendanubeCommercialProposals(),
    ]);
    setData({
      readiness:result[0].status==='fulfilled'?result[0].value:null,
      linkage:result[1].status==='fulfilled'?result[1].value:null,
      finalQueue:result[2].status==='fulfilled'?result[2].value:null,
      brands:result[3].status==='fulfilled'?result[3].value:null,
      quality:result[4].status==='fulfilled'?result[4].value:null,
      commercial:result[5].status==='fulfilled'?result[5].value:null,
    });
    if(result.some(x=>x.status==='rejected'))setMessage('Algunas fuentes no respondieron. Mostramos «—» donde no pudimos consultar el estado.');
    setLoaded(true);
    setLoading(false);
  }

  useEffect(()=>{void load().catch(()=>{setLoading(false);setLoaded(true);setMessage('No se pudo consultar el centro de tareas. Reintentá más tarde.')})},[]);
  const tasks=useMemo(()=>buildTaskCenter(data),[data]);
  const scoped=tasks.filter(x=>filter==='ALL'||x.channel===filter);
  const active=scoped.filter(x=>x.count!==null&&x.count>0).sort((a,b)=>a.priority-b.priority);
  const remaining=scoped.filter(x=>x.count===null||x.count===0).sort((a,b)=>a.priority-b.priority);
  const first=active[0];

  return <div className="kiki-work-hub">
    <header className="kiki-home-header">
      <div><p className="eyebrow">KIKI TECH · TAREAS</p><h1>Lo que necesita atención.</h1><p>KIKI reúne los pendientes por tipo de trabajo. Elegí un tema y continuá en su pantalla, sin buscar entre todas las herramientas.</p></div>
      <button type="button" className="kiki-refresh" disabled={loading} onClick={()=>void load()}>{loading?'Consultando…':'↻ Actualizar tareas'}</button>
    </header>
    {message&&<div className="notice warning" role="status">{message}</div>}

    <section className="kiki-work-next" aria-label="Siguiente tarea sugerida">
      <p className="eyebrow">POR DÓNDE EMPEZAR</p>
      {loading&&!loaded?<><h2>Consultando las fuentes…</h2><p>Preparando tareas a partir de los catálogos disponibles.</p></>:first?<div className="kiki-work-next-row">
        <div><h2>{first.title}</h2><p>{first.description}</p><small>{number(first.count)} {first.unit} · Prioridad orientativa por tipo de problema</small></div>
        <Link className="kiki-main-action" to={first.href}>{first.cta} →</Link>
      </div>:<div className="kiki-work-next-row">
        <div><h2>{remaining.some(x=>x.count===null)?'Hay fuentes pendientes de consultar':'No hay tareas registradas en estos flujos'}</h2>
          <p>{remaining.some(x=>x.count===null)?'Revisá el estado de las importaciones. Un dato no disponible no significa que haya cero pendientes.':'No se detectaron pendientes en los flujos consultados. Esto no garantiza que todas las fichas estén verificadas.'}</p></div>
        <Link className="kiki-main-action" to="/channels">Ver canales →</Link>
      </div>}
    </section>

    <section className="kiki-work-board">
      <div className="kiki-panel-heading"><div><p className="eyebrow">VISTA ORGANIZADA</p><h2>Tareas por área</h2></div><Link to="/work/details">Abrir herramientas de revisión →</Link></div>
      <div className="kiki-work-tabs" role="group" aria-label="Filtrar tareas por canal">
        {(['ALL','ECOMM','ML','TN'] as const).map(value=><button type="button" key={value} className={filter===value?'is-active':''} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{value==='ALL'?'Todas':channelName[value]}</button>)}
      </div>
      <p className="kiki-work-note">Los conteos son independientes por proceso: <strong>no se suman</strong> porque un producto puede aparecer en más de una categoría. No son datos en tiempo real.</p>
      {loading&&!loaded?<div className="kiki-work-placeholder">Leyendo los datos disponibles…</div>:<>
        <div className="kiki-work-task-list">
          {active.map(task=><article key={task.id} className="kiki-work-task">
            <div className="kiki-work-task-value"><strong>{number(task.count)}</strong><small>{task.unit}</small></div>
            <div className="kiki-work-task-body"><div className="kiki-work-task-head"><span>{channelName[task.channel]}</span><strong>{task.title}</strong></div>
              <p>{task.description}</p>
              {task.examples.length>0&&<div className="kiki-work-examples"><small>Ejemplos del catálogo</small>{task.examples.map((name,i)=><span key={i}>{name}</span>)}</div>}
              {task.caution&&<small className="kiki-work-caution">{task.caution}</small>}
            </div>
            <Link className="kiki-work-task-link" to={task.href}>{task.cta} →</Link>
          </article>)}
          {active.length===0&&<div className="kiki-work-placeholder">No hay tareas positivas registradas con este filtro. Revisá las fuentes sin datos más abajo.</div>}
        </div>
        <details className="kiki-work-secondary">
          <summary>Otros flujos y estados ({remaining.length})</summary>
          <div className="kiki-work-secondary-items">{remaining.map(task=><div key={task.id} className="kiki-work-secondary-row">
            <div><strong>{task.title}</strong><small>{task.count===null?'Estado no disponible':task.count===0?'Sin pendientes en este flujo':'Pendientes'}</small></div><Link to={task.href}>Consultar →</Link>
          </div>)}</div>
        </details>
      </>}
    </section>
    <p className="kiki-home-footnote">Este centro orienta el trabajo con reglas de prioridad generales; no verifica automáticamente fuentes externas, márgenes comerciales ni urgencia real de cada producto. Las aprobaciones continúan siendo humanas e internas.</p>
  </div>;
}
