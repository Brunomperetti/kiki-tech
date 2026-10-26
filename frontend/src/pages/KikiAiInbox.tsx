import {FormEvent,useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from '../components/KikiIcon';
import type {EcommAiInboxFilter,EcommAiProposalInbox} from '../types/ecomm-app';
import '../guide.css';

const fmt=(value:number|undefined)=>value===undefined?'—':value.toLocaleString('es-AR');
const when=(value:string|null)=>value?new Date(value).toLocaleString('es-AR'):'Sin fecha';
const tabs:{value:EcommAiInboxFilter;name:string}[]=[
  {value:'all',name:'Todas las propuestas'},
  {value:'without_edit',name:'Sin ficha comercial guardada'},
  {value:'with_edit',name:'Con ficha comercial guardada'},
];
export function KikiAiInbox(){
  const [data,setData]=useState<EcommAiProposalInbox|null>(null);
  const [filter,setFilter]=useState<EcommAiInboxFilter>('all');
  const [search,setSearch]=useState('');
  const [query,setQuery]=useState('');
  const [page,setPage]=useState(1);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');

  useEffect(()=>{
    let active=true;
    setLoading(true);setError('');
    api.ecommAiProposals(query,filter,page,25).then(result=>{
      if(active)setData(result);
    }).catch(err=>{
      if(active){setData(null);setError(err instanceof Error?err.message:'No se pudieron leer las propuestas.');}
    }).finally(()=>{if(active)setLoading(false)});
    return ()=>{active=false};
  },[filter,query,page]);

  function submit(event:FormEvent){event.preventDefault();setPage(1);setQuery(search.trim())}
  function changeFilter(next:EcommAiInboxFilter){setFilter(next);setPage(1)}
  const summary=data?.summary;
  return <div className="kiki-inbox">
    <header className="kiki-home-header">
      <div><p className="eyebrow">KIKI AI · TRABAJO RECUPERABLE</p>
        <h1>Propuestas IA guardadas</h1>
        <p>Encontrá los textos que KIKI generó, volvé a revisarlos y decidí
          qué incorporar a cada ficha. No necesitás recordar los SKU ni generar otra vez.</p></div>
      <div className="kiki-workspace-shortcuts">
        <Link className="kiki-guide-home-link" to="/queue"><KikiIcon name="chart" size={16}/> Volver a cola</Link>
        <Link className="kiki-guide-home-link" to="/guia"><KikiIcon name="help" size={16}/> Ver guía</Link>
      </div>
    </header>
    <section className="kiki-guide-essential">
      <KikiIcon name="shield" size={24}/>
      <div><strong>Una propuesta generada NO es una ficha comercial editada.</strong>
        <p>Las propuestas de OpenAI quedan archivadas por variante Ecomm-App.
          Al abrir una propuesta, KIKI vuelve a comprobar si corresponde a la versión actual.
          Revisá los datos y hacé clic en «Guardar borrador» para conservar los campos
          aceptados en PostgreSQL. Una ficha guardada tampoco demuestra que su IA se haya usado.</p></div>
    </section>
    <div className="kiki-inbox-kpis">
      <article><span>Productos con propuesta IA</span><strong>{fmt(summary?.products_with_ai_proposals)}</strong></article>
      <article><span>Sin ficha comercial guardada</span><strong>{fmt(summary?.products_without_saved_edits)}</strong></article>
      <article><span>Con ficha KIKI guardada</span><strong>{fmt(summary?.products_with_saved_edits)}</strong></article>
    </div>
    <section className="kiki-inbox-panel">
      <div><p className="eyebrow">VOLVÉ A TUS PROPUESTAS</p>
        <h2>Buscá y revisá</h2>
        <p>Se muestra la propuesta más reciente de cada variante. La aplicación conserva
          los borradores originales de IA por separado para auditoría.</p></div>
      <div className="kiki-inbox-filters" role="group" aria-label="Filtrar propuestas">
        {tabs.map(tab=><button type="button" key={tab.value}
          className={filter===tab.value?'active':''}
          aria-pressed={filter===tab.value} onClick={()=>changeFilter(tab.value)}>
          {tab.name} ({fmt(tab.value==='all'?summary?.products_with_ai_proposals:
            tab.value==='with_edit'?summary?.products_with_saved_edits:
            summary?.products_without_saved_edits)})
        </button>)}
      </div>
      <form className="kiki-inbox-search" onSubmit={submit}>
        <label htmlFor="kiki-ai-search">Buscar por SKU, ID, nombre o título generado</label>
        <div><input id="kiki-ai-search" value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="Ej.: Salsa de soja o 9439822" maxLength={80}/>
          <button type="submit" disabled={loading}>
            <KikiIcon name="search" size={16}/> Buscar</button></div>
      </form>
      {loading&&<p className="kiki-inbox-empty" role="status">Buscando propuestas guardadas…</p>}
      {error&&<p className="kiki-inbox-error" role="alert">{error}</p>}
      {!loading&&data?.items.map(item=><article key={item.ecomm_id}
        className="kiki-inbox-row">
        <span className="kiki-inbox-row-icon"><KikiIcon name="sparkles" size={20}/></span>
        <div className="kiki-inbox-row-main">
          <span>SKU {item.sku||'Sin informar'} · ID {item.ecomm_id}</span>
          <h3>{item.product_name||'Producto sin nombre'}</h3>
          <p>Propuesta #{item.latest_draft_id} · Generada: {when(item.created_at)}</p>
          <small>{item.has_saved_product_edit
            ?'Existe una ficha guardada ('+(item.product_edit_status==='DRAFT'
              ?'borrador':'revisión interna')+'). Revisá si usaron la propuesta.'
            :'Todavía no existe una ficha comercial guardada para este producto.'}</small>
        </div>
        <Link to={'/workspace?id='+encodeURIComponent(item.ecomm_id)}>
          Revisar y guardar ficha <KikiIcon name="arrow-right" size={16}/></Link>
      </article>)}
      {!loading&&data?.total===0&&<div className="kiki-inbox-empty">
        No hay propuestas en este filtro. Probá otra búsqueda o volvé a la cola
        para generar una propuesta de un producto simple.
      </div>}
      <div className="kiki-inbox-pages">
        <button type="button" disabled={page<=1||loading}
          onClick={()=>setPage(p=>p-1)}>← Anterior</button>
        <span>Página {page} · {fmt(data?.total)} productos encontrados</span>
        <button type="button" disabled={loading||!data||page*25>=data.total}
          onClick={()=>setPage(p=>p+1)}>Siguiente →</button>
      </div>
      <p className="kiki-guide-disclaimer">
        KIKI no modifica Ecomm-App, Mercado Libre ni Tiendanube desde esta bandeja.
        Abrir una propuesta guardada no consume una nueva solicitud IA.
      </p>
    </section>
  </div>
}
