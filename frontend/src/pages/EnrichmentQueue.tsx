import {FormEvent,useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from '../components/KikiIcon';
import type {EcommQueueFilter,EcommQueueRow,EcommWorkQueue} from '../types/ecomm-app';
import '../queue.css';

const fmt=(value:number|undefined)=>value===undefined?'—':value.toLocaleString('es-AR');
const day=(raw:string|null)=>raw?new Date(raw).toLocaleString('es-AR'):'Sin fecha';
const reason=(flag:EcommQueueFilter)=>({
  all:'Todas',identity:'Identidad a revisar',draft:'Borradores',ready:'En revisión interna',
  untouched:'Sin trabajar',pack:'Packs / combos',
  missing_title:'Sin título propuesto',missing_brand:'Sin marca en KIKI',
  missing_description:'Sin descripción propuesta',missing_gtin:'Sin GTIN informado',
}[flag]);
const filters:EcommQueueFilter[]=[
  'all','identity','draft','untouched','pack','ready','missing_brand',
  'missing_title','missing_description','missing_gtin',
];
const tag=(row:EcommQueueRow)=>row.identity_issue?'Identidad a revisar':
  row.status==='READY_FOR_REVIEW'?'Lista para revisión interna':
  row.status==='DRAFT'?'Borrador guardado':
  row.is_combo?'Pack por verificar':'Sin trabajar';

function safeCell(value:string|number|boolean|null|undefined){
  const normalized=String(value??'').replace(/[\r\n]+/g,' ').trim();
  // Prevent accidental spreadsheet formula interpretation on CSV opening.
  const guarded=/^[=+\-@\t]/.test(normalized)?"'"+normalized:normalized;
  return '"'+guarded.replace(/"/g,'""')+'"';
}
function exportQueue(rows:EcommQueueRow[]){
  if(!rows.length)return;
  const header=['ID Ecomm API','SKU','Producto Ecomm API','Estado KIKI',
    'Tipo','Prioridad','Motivo','Campos pendientes en KIKI','Marca propuesta',
    'Título propuesto','Última edición','Fecha de captura Ecomm API'];
  const lines=[header,...rows.map(row=>[
    row.ecomm_id,row.sku,row.product_name,row.status,row.is_combo?'Combo / pack':'Variante',
    row.priority,row.reason,row.flags.filter(f=>f.startsWith('missing_')).map(reason).join(' | '),
    row.proposed_brand,row.proposed_title,row.last_edited_at||'',row.captured_at||''
  ])];
  const csv='\uFEFF'+lines.map(cells=>cells.map(safeCell).join(';')).join('\r\n');
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'});
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');anchor.href=url;
  anchor.download='kiki-casos-api-revision-'+new Date().toISOString().slice(0,10)+'.csv';
  document.body.appendChild(anchor);anchor.click();anchor.remove();
  URL.revokeObjectURL(url);
}

export function EnrichmentQueue(){
  const [data,setData]=useState<EcommWorkQueue|null>(null);
  const [filter,setFilter]=useState<EcommQueueFilter>('all');
  const [input,setInput]=useState('');
  const [query,setQuery]=useState('');
  const [page,setPage]=useState(1);
  const [selected,setSelected]=useState<string[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');

  async function load(nextFilter:EcommQueueFilter,term:string,nextPage:number){
    setLoading(true);setError('');
    try{setData(await api.ecommWorkQueue(nextFilter,term,nextPage,25));}
    catch(err){
      setData(null);
      setError(err instanceof Error?err.message:'No se pudo obtener la cola API.');
    }
    finally{setLoading(false);}
  }
  useEffect(()=>{void load(filter,query,page);},[filter,query,page]);
  useEffect(()=>{setSelected([])},[filter,query,page]);
  function submit(e:FormEvent){e.preventDefault();setPage(1);setQuery(input.trim())}
  function changeFilter(value:EcommQueueFilter){setPage(1);setFilter(value)}
  function check(id:string,checked:boolean){
    if(checked)setSelected(previous=>previous.includes(id)?previous:[...previous,id]);
    else setSelected(previous=>previous.filter(x=>x!==id));
  }
  const visible=data?.items??[];
  const eligible=visible.filter(row=>!!row.ecomm_id);
  const selectedRows=visible.filter(row=>selected.includes(row.ecomm_id));
  const pageAll=eligible.length>0&&eligible.every(row=>selected.includes(row.ecomm_id));
  const summary=data?.summary;
  return <div className="kiki-queue">
    <header className="kiki-home-header">
      <div>
        <p className="eyebrow">KIKI TECH · ENRIQUECIMIENTO ORGANIZADO</p>
        <h1>Cola de mejoras</h1>
        <p>KIKI identifica y ordena automáticamente las fichas del catálogo API.
          Elegí qué revisar primero, agrupá casos y continuá trabajando sobre
          los datos persistentes de KIKI Tech.</p>
      </div>
      <button type="button" className="kiki-queue-refresh" onClick={()=>void load(filter,query,page)}
        disabled={loading}><KikiIcon name="refresh" size={16}/>{loading?'Analizando…':'Actualizar cola'}</button>
    </header>
    <div className="kiki-queue-notice">
      <KikiIcon name="shield" size={21}/>
      <div><strong>Análisis automático, decisiones controladas.</strong>
        <p>Esta pantalla clasifica una copia capturada por API; no consulta stock en vivo,
          no inventa GTIN ni genera IA masivamente. La selección y el CSV son para organización:
          no aprueban productos ni modifican Ecomm-App, Mercado Libre o Tiendanube.</p></div>
    </div>
    {error&&<div className="kiki-queue-error" role="alert">{error}</div>}

    <div className="kiki-queue-stats">
      <div><span>Variantes API</span><strong>{fmt(summary?.total)}</strong><small>Captura Ecomm-App</small></div>
      <div><span>Sin trabajar</span><strong>{fmt(summary?.untouched)}</strong><small>Sin borrador KIKI</small></div>
      <div><span>En progreso</span><strong>{fmt(summary?.draft)}</strong><small>Con cambios guardados</small></div>
      <div><span>Preparadas</span><strong>{fmt(summary?.ready)}</strong><small>Solo revisión interna</small></div>
    </div>

    <section className="kiki-queue-browser">
      <div className="kiki-queue-head">
        <div><p className="eyebrow">PRIORIDADES DE TRABAJO</p><h2>Qué necesita atención</h2>
          <p>Seleccioná un motivo para ver todas las variantes que lo presentan.</p>
        </div>
        <span>{data?'Captura: '+day(data.source_snapshot_at):'Comprobando fuente API…'}</span>
      </div>
      <div className="kiki-queue-chips">
        {filters.map(f=><button type="button" key={f}
          className={'kiki-queue-chip '+(filter===f?'active':'')}
          aria-pressed={filter===f} onClick={()=>changeFilter(f)}>
          {reason(f)}<b>{fmt(f==='all'?summary?.total:summary?.[f])}</b>
        </button>)}
      </div>
      <div className="kiki-queue-help"><KikiIcon name="help" size={16}/>
        <span>Los indicadores de motivos se superponen: una ficha puede ser un pack,
          no tener GTIN informado y también necesitar título. «Sin marca» significa
          que KIKI todavía no tiene una marca propuesta, no que el fabricante carezca de ella.</span>
      </div>
      <form onSubmit={submit} className="kiki-queue-search">
        <label htmlFor="queue-search">Buscá por SKU, ID, nombre o propuesta guardada</label>
        <div><input id="queue-search" value={input} onChange={e=>setInput(e.target.value)}
          maxLength={80} placeholder="Ej.: 2500400"/>
          <button type="submit" disabled={loading}><KikiIcon name="search" size={17}/> Buscar</button>
        </div>
      </form>
      <div className="kiki-queue-selection" aria-label="Herramientas para organizar casos">
        <label><input type="checkbox" checked={pageAll} disabled={loading||eligible.length===0}
          onChange={e=>setSelected(e.target.checked?eligible.map(row=>row.ecomm_id):[])}/>
          Seleccionar todos los de esta página</label>
        <span>{selected.length} seleccionados</span>
        <button type="button" onClick={()=>exportQueue(selectedRows)}
          disabled={!selectedRows.length}><KikiIcon name="archive" size={16}/> Exportar selección CSV</button>
      </div>
      <div className="kiki-queue-list" aria-live="polite">
        {loading&&<p className="kiki-queue-placeholder">Revisando fichas del catálogo Ecomm por API…</p>}
        {!loading&&visible.map(row=><article key={row.ecomm_id+'-'+row.sku}
          className={'kiki-queue-item '+(row.identity_issue?'identity':'')}>
          <label className="kiki-queue-checkbox" aria-label={'Seleccionar SKU '+row.sku}>
            <input type="checkbox" checked={selected.includes(row.ecomm_id)}
              disabled={!row.ecomm_id}
              onChange={e=>check(row.ecomm_id,e.target.checked)}/>
          </label>
          <div className="kiki-queue-item-body">
            <div className="kiki-queue-item-top">
              <span className="kiki-queue-sku">SKU {row.sku||'No informado'} · ID {row.ecomm_id||'Sin ID'}</span>
              <span className={'kiki-queue-tag '+(row.identity_issue?'caution':row.status==='READY_FOR_REVIEW'?'review':'')}>
                {tag(row)}
              </span>
            </div>
            <h3>{row.product_name||'Producto sin nombre'}</h3>
            {row.proposed_title&&<p className="kiki-queue-proposed">Título KIKI: {row.proposed_title}</p>}
            <p className="kiki-queue-explain">{row.reason}</p>
            <div className="kiki-queue-tags">
              {row.flags.filter(f=>f!=='untouched'&&f!=='draft'&&f!=='ready'&&f!=='identity').slice(0,5)
                .map(flag=><span key={flag}>{reason(flag)}</span>)}
            </div>
          </div>
          <div className="kiki-queue-item-action">
            {row.ecomm_id?<Link to={'/workspace?id='+encodeURIComponent(row.ecomm_id)}>
              Abrir ficha <KikiIcon name="arrow-right" size={16}/></Link>
              :<span>Sin ID para editar</span>}
            <small>Prioridad {row.priority===0?'Alta':row.priority===1?'Continuar':
              row.priority===2?'Revisar pack':'Normal'}</small>
          </div>
        </article>)}
        {!loading&&data?.total===0&&<p className="kiki-queue-placeholder">
          No hay variantes en este filtro. Podés seleccionar otra categoría o modificar la búsqueda.
        </p>}
      </div>
      <div className="kiki-queue-pagination">
        <button disabled={loading||page<=1} type="button" onClick={()=>setPage(p=>p-1)}>
          ← Anterior</button>
        <span>Página {page} · {fmt(data?.total)} resultados filtrados</span>
        <button disabled={loading||!data||page*25>=data.total} type="button" onClick={()=>setPage(p=>p+1)}>
          Siguiente →</button>
      </div>
    </section>
  </div>
}
