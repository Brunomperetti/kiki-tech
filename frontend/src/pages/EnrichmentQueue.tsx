import {FormEvent,useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from '../components/KikiIcon';
import type {EcommQueueFilter,EcommQueueRow,EcommWorkQueue,EcommAiSuggestion} from '../types/ecomm-app';
import '../queue.css';

const fmt=(value:number|undefined)=>value===undefined?'—':value.toLocaleString('es-AR');
const day=(raw:string|null)=>raw?new Date(raw).toLocaleString('es-AR'):'Sin fecha';
const chanStatus=(status:string,source:string)=>{
  switch(status){
    case 'SKU_CANDIDATE':return source+': SKU candidato · verificar';
    case 'PACK_REVIEW':return source+': pack por verificar';
    case 'PRESENTATION_CONFLICT':return source+': presentación diferente';
    case 'GTIN_CONFLICT':return source+': códigos en conflicto';
    case 'MULTIPLE_SKU_ROWS':return source+': SKU repetido en canal';
    case 'AMBIGUOUS_API_SKU':return source+': SKU Ecomm ambiguo';
    case 'NO_EXACT_SKU_IN_SNAPSHOT':return source+': sin SKU exacto en copia';
    default:return source+': fuente no disponible';
  }
};

const reason=(flag:EcommQueueFilter)=>({
  all:'Todas',ai_eligible:'Simples aptos para IA',identity:'Identidad a revisar',draft:'Borradores',ready:'En revisión interna',
  untouched:'Sin trabajar',pack:'Packs / combos',
  ready_for_channels:'Listas para canales',needs_completion:'Fichas iniciadas por completar',
  review_due:'Revisión mensual pendiente',
  ml_candidate:'Candidatos en ML',tn_candidate:'Candidatos en TN',
  ml_no_exact:'Sin SKU exacto en copia ML',tn_no_exact:'Sin SKU exacto en copia TN',
  both_candidates:'Candidatos en ambos canales',
  channel_review:'Conflictos de canales para verificar',
  neither_sku_in_snapshots:'Sin SKU exacto en ambas copias',
  missing_source_name:'Nombre ausente en API',
  missing_title:'Fichas iniciadas sin título comercial',
  missing_brand:'Fichas iniciadas sin marca confirmada',
  missing_description:'Fichas iniciadas sin descripción comercial',
  missing_gtin:'Fichas iniciadas: GTIN sin documentar',
}[flag]);
const mainFilters:EcommQueueFilter[]=[
  'all','channel_review','both_candidates','neither_sku_in_snapshots',
  'ml_candidate','tn_candidate',
];
const secondaryFilters:EcommQueueFilter[]=[
  'ml_no_exact','tn_no_exact','identity','draft','ready','ready_for_channels',
  'review_due','untouched','ai_eligible','pack',
];
const startedEditFilters:EcommQueueFilter[]=[
  'needs_completion','missing_source_name',
  'missing_brand','missing_title','missing_description','missing_gtin',
];
const tag=(row:EcommQueueRow)=>row.identity_issue?'Identidad a revisar':
  row.flags.includes('channel_review')?'Verificar coincidencias de canales':
  row.flags.includes('review_due')?'Revisión mensual pendiente':
  row.status==='READY_FOR_CHANNELS'?'Completa y guardada para canales':
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
    'Tipo','Prioridad','Motivo','Estado ML en snapshot','Estado TN en CSV',
    'IDs candidatos ML','Producto candidato TN',
    'Observaciones de origen y edición','Marca propuesta',
    'Título propuesto','Última edición','Fecha de captura Ecomm API'];
  const lines=[header,...rows.map(row=>[
    row.ecomm_id,row.sku,row.product_name,row.status,row.is_combo?'Combo / pack':'Variante',
    row.priority,row.reason,row.channel_coverage.ml.status,row.channel_coverage.tn.status,
    row.channel_coverage.ml.listing_ids.join(' | '),row.channel_coverage.tn.candidate_name||'',
    row.flags.filter(f=>f.startsWith('missing_')).map(reason).join(' | '),
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

type BatchPlanRow={
  row:EcommQueueRow;version:number;reuse:EcommAiSuggestion|null;
};
type BatchResult={ecomm_id:string;sku:string;result:'REUSED'|'CREATED'|'FAILED';
  message:string;draft_id:number|null};

export function EnrichmentQueue(){
  const [data,setData]=useState<EcommWorkQueue|null>(null);
  const [eanSummary,setEanSummary]=useState<Awaited<ReturnType<typeof api.ecommEanSummary>>|null>(null);
  const [filter,setFilter]=useState<EcommQueueFilter>('all');
  const [input,setInput]=useState('');
  const [query,setQuery]=useState('');
  const [page,setPage]=useState(1);
  const [selected,setSelected]=useState<string[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [batchPlan,setBatchPlan]=useState<BatchPlanRow[]|null>(null);
  const [batchRemaining,setBatchRemaining]=useState<number|null>(null);
  const [batchEnabled,setBatchEnabled]=useState(false);
  const [batchBusy,setBatchBusy]=useState(false);
  const [batchError,setBatchError]=useState('');
  const [batchProgress,setBatchProgress]=useState('');
  const [batchResults,setBatchResults]=useState<BatchResult[]>([]);


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
  useEffect(()=>{void api.ecommEanSummary().then(setEanSummary).catch(()=>{});},[]);
  useEffect(()=>{setSelected([])},[filter,query,page]);
  useEffect(()=>{
    // A plan must never silently apply to a new page, filter, or selection.
    setBatchPlan(null);setBatchResults([]);setBatchError('');
    setBatchProgress('');
  },[selected,filter,query,page]);

  function submit(e:FormEvent){e.preventDefault();setPage(1);setQuery(input.trim())}
  function changeFilter(value:EcommQueueFilter){setPage(1);setFilter(value)}
  function check(id:string,checked:boolean){
    if(checked)setSelected(previous=>previous.includes(id)?previous:[...previous,id]);
    else setSelected(previous=>previous.filter(x=>x!==id));
  }

  async function prepareAiBatch(){
    if(batchBusy||!data)return;
    setBatchPlan(null);setBatchResults([]);setBatchError('');setBatchProgress('');
    const picked=data.items.filter(row=>selected.includes(row.ecomm_id));
    if(!picked.length||picked.length>3){
      setBatchError('Seleccioná entre 1 y 3 productos de esta página para preparar las propuestas IA.');
      return;
    }
    if(picked.some(row=>row.identity_issue||row.is_combo||!row.ecomm_id||!row.sku)){
      setBatchError('La generación IA por lotes solo admite productos simples, con ID/SKU únicos. Quitá packs y casos de identidad.');
      return;
    }
    setBatchBusy(true);
    try{
      const plan:BatchPlanRow[]=[];
      let available=0;
      let enabled=false;
      for(const row of picked){
        const [edit,latest]=await Promise.all([
          api.ecommGetEdit(row.ecomm_id),api.ecommAiLatest(row.ecomm_id),
        ]);
        if(edit.source_sku_changed||edit.source.sku!==row.sku||
          edit.source.is_combo===true||edit.version!==row.edit_version){
          throw new Error('La ficha '+row.sku+' cambió o no es una variante simple verificable. Actualizá la cola.');
        }
        enabled=latest.enabled;
        available=latest.remaining_today;
        plan.push({
          row,version:edit.version,
          reuse:latest.draft?.source_current?latest.draft:null,
        });
      }
      setBatchPlan(plan);
      setBatchRemaining(available);
      setBatchEnabled(enabled);
    }catch(err){
      setBatchError(err instanceof Error?err.message:'No se pudo preparar la selección.');
    }finally{setBatchBusy(false)}
  }
  async function generateAiBatch(){
    if(batchBusy||!batchPlan||!batchEnabled)return;
    const needed=batchPlan.filter(x=>!x.reuse).length;
    if(needed>(batchRemaining??0)){
      setBatchError('No quedan solicitudes suficientes hoy para este lote. Reducí la selección.');
      return;
    }
    if(!window.confirm('KIKI preparará '+batchPlan.length+' fichas: '+needed+
      ' solicitud(es) nueva(s) a OpenAI y '+(batchPlan.length-needed)+
      ' reutilizada(s). No se modificarán fichas ni canales. ¿Continuar?'))return;
    setBatchBusy(true);setBatchError('');setBatchResults([]);
    const outcome:BatchResult[]=[];
    for(const [i,item] of batchPlan.entries()){
      setBatchProgress('Procesando '+(i+1)+' de '+batchPlan.length+': SKU '+item.row.sku);
      try{
        const proposal=item.reuse??await api.ecommAiSuggest(item.row.ecomm_id,item.version);
        outcome.push({
          ecomm_id:item.row.ecomm_id,sku:item.row.sku,
          result:item.reuse||proposal.reused?'REUSED':'CREATED',
          message:(proposal.warnings?.length?'La IA marcó advertencias para revisar.':
            'Propuesta interna pendiente de revisión humana.'),
          draft_id:proposal.draft_id,
        });
      }catch(err){
        outcome.push({
          ecomm_id:item.row.ecomm_id,sku:item.row.sku,result:'FAILED',
          message:err instanceof Error?err.message:'Error al generar propuesta.',
          draft_id:null,
        });
      }
      setBatchResults([...outcome]);
    }
    setBatchProgress('');
    setBatchBusy(false);
    setBatchPlan(null);
  }

  const visible=data?.items??[];
  const eligible=visible.filter(row=>!!row.ecomm_id);
  const batchEligible=visible.filter(row=>!row.is_combo&&!row.identity_issue
    &&!!row.ecomm_id&&!!row.sku);
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
    {data?.gtin_data_quality.status==='NO_GTIN_EXPOSED_BY_CAPTURE'&&
      <div className="kiki-queue-quality" role="status">
        <KikiIcon name="alert" size={20}/>
        <div><strong>Cobertura de la API: no se recibieron GTIN para las
          {fmt(data.gtin_data_quality.gtin_unavailable_in_capture)} variantes.</strong>
          <p>La API utilizada no expuso códigos de barras; esto no significa que
            los productos no tengan EAN. KIKI conserva posibles códigos del Excel histórico
            como <strong>evidencia secundaria</strong>, nunca como datos certificados de la API.
            {eanSummary?.legacy_available
              ?' Candidatos por SKU único y validación formal: '+fmt(eanSummary.possible_candidates)+
                 '. Packs y coincidencias ambiguas quedan excluidos.'
              :' No hay una fuente histórica disponible para obtener candidatos.'}
            {' '}Abrí una ficha en Backoffice para ver la evidencia, verificarla y guardarla si corresponde.
            También conviene solicitar al proveedor el endpoint oficial de GTIN.</p>
        </div>
      </div>}

    <div className="kiki-queue-stats">
      <div><span>Variantes API</span><strong>{fmt(summary?.total)}</strong><small>Captura Ecomm-App</small></div>
      <div><span>Sin trabajar</span><strong>{fmt(summary?.untouched)}</strong><small>Sin borrador KIKI</small></div>
      <div><span>En progreso</span><strong>{fmt(summary?.draft)}</strong><small>Con cambios guardados</small></div>
      <div><span>Para revisión</span><strong>{fmt(summary?.ready)}</strong><small>Control editorial interno</small></div>
      <div><span>Listas para canales</span><strong>{fmt(summary?.ready_for_channels)}</strong><small>Fichas comerciales completas en KIKI</small></div>
    </div>

    {data?.channel_coverage&&<section className="kiki-queue-channel-matrix" aria-label="Cobertura por canal y fuentes">
      <div className="kiki-queue-channel-head">
        <div><p className="eyebrow">ECOMM-APP API + MERCADO LIBRE API + TIENDANUBE CSV</p>
          <h2>¿Qué productos tienen coincidencias en los canales?</h2>
          <p>El cruce se hace por variante y SKU único. Las coincidencias son candidatos
            para verificar: no se marcan como publicaciones correctas automáticamente.</p></div>
        <Link to="/channels">Ver fuentes de canales <KikiIcon name="arrow-right" size={15}/></Link>
      </div>
      <div className="kiki-queue-channel-stats">
        <div><strong>{fmt(summary?.ml_candidate)}</strong><span>SKU candidatos en Mercado Libre</span></div>
        <div><strong>{fmt(summary?.tn_candidate)}</strong><span>SKU candidatos en Tiendanube</span></div>
        <div><strong>{fmt(summary?.both_candidates)}</strong><span>Candidatos en ambos canales</span></div>
        <div><strong>{fmt(summary?.channel_review)}</strong><span>Variantes con conflictos o packs por revisar</span></div>
      </div>
      <div className="kiki-queue-channel-sources">
        <div><b>Mercado Libre</b><span>{data.channel_coverage.sources.ml.available
          ?fmt(data.channel_coverage.sources.ml.rows)+' filas del snapshot API · '+day(data.channel_coverage.sources.ml.updated_at)
          :'Copia API no disponible; no se puede concluir si hay publicaciones'}</span></div>
        <div><b>Tiendanube</b><span>{data.channel_coverage.sources.tn.available
          ?fmt(data.channel_coverage.sources.tn.rows)+' filas del CSV · '+day(data.channel_coverage.sources.tn.updated_at)
          :'CSV no disponible; no se puede concluir si hay publicaciones'}</span></div>
      </div>
      <p className="kiki-queue-channel-caution">«Sin SKU exacto en copia» NO significa
        «no publicado». Primero hay que actualizar las fuentes y verificar identidad,
        presentación, variaciones y packs. Ninguna coincidencia habilita publicación automática.</p>
    </section>}

    <section className="kiki-queue-browser">
      <div className="kiki-queue-head">
        <div><p className="eyebrow">PRIORIDADES DE TRABAJO</p><h2>Qué necesita atención</h2>
          <p>Seleccioná un motivo para ver todas las variantes que lo presentan.</p>
        </div>
        <span>{data?'Captura: '+day(data.source_snapshot_at):'Comprobando fuente API…'}</span>
      </div>
      <div className="kiki-queue-source-health">
        <div><strong>{fmt(summary?.source_name_present)} de {fmt(summary?.total)}</strong>
          <span>variantes con nombre original en Ecomm-App API</span></div>
        <div><strong>{fmt(summary?.editorial_started)}</strong>
          <span>fichas comerciales iniciadas dentro de KIKI</span></div>
        <p>Los productos no están vacíos: KIKI conserva el nombre del origen.
          Los campos para enriquecer no son faltantes del proveedor.
          Las fichas sin empezar se muestran una sola vez como «Sin trabajar».</p>
      </div>
      <div className="kiki-queue-chips">
        {mainFilters.map(f=><button type="button" key={f}
          className={'kiki-queue-chip '+(filter===f?'active':'')}
          aria-pressed={filter===f} onClick={()=>changeFilter(f)}>
          {reason(f)}<b>{fmt(f==='all'?summary?.total:summary?.[f])}</b>
        </button>)}
      </div>
      <details className="kiki-queue-editorial-filters" open={secondaryFilters.includes(filter)}>
        <summary>Más filtros: estados de KIKI y revisión por canal</summary>
        <div className="kiki-queue-chips">
          {secondaryFilters.map(f=><button type="button" key={f}
            className={'kiki-queue-chip '+(filter===f?'active':'')}
            aria-pressed={filter===f} onClick={()=>changeFilter(f)}>
            {reason(f)}<b>{fmt(summary?.[f])}</b>
          </button>)}
        </div>
      </details>
      <details className="kiki-queue-editorial-filters" open={startedEditFilters.includes(filter)}>
        <summary>Ver controles editoriales de fichas ya iniciadas</summary>
        <p>Estos contadores solo consideran productos que alguien empezó a editar
          dentro de KIKI. No confunden ausencia de mejoras con ausencia del dato en la API.</p>
        <div className="kiki-queue-chips">
          {startedEditFilters.map(f=><button type="button" key={f}
            className={'kiki-queue-chip '+(filter===f?'active':'')}
            aria-pressed={filter===f} onClick={()=>changeFilter(f)}>
            {reason(f)}<b>{fmt(summary?.[f])}</b>
          </button>)}
        </div>
      </details>
      <div className="kiki-queue-help"><KikiIcon name="help" size={16}/>
        <span>La columna editorial de KIKI y la cobertura de canales son distintas.
          Una ficha que aún no se preparó en KIKI puede tener un candidato publicado
          en Mercado Libre o Tiendanube. Nunca duplicamos una publicación sobre esta evidencia.
          Una ficha puede necesitar completar varios campos.
          La API identifica productos y aporta nombres; las propuestas comerciales
          se elaboran y guardan por separado en KIKI. El estado de GTIN de la copia
          se muestra arriba como calidad de la fuente, no como una tarea falsa por producto.</span>
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
      <section className="kiki-queue-ai-batch" aria-label="Propuestas IA por lotes">
        <div className="kiki-queue-inbox-shortcut">
          <KikiIcon name="clock" size={18}/>
          <span>¿Ya generaste propuestas? Se conservan aunque salgas de esta página.</span>
          <Link to="/propuestas-ia">Ver propuestas IA guardadas <KikiIcon name="arrow-right" size={15}/></Link>
        </div>
        <div className="kiki-queue-ai-header">
          <span className="kiki-queue-ai-symbol"><KikiIcon name="sparkles" size={23}/></span>
          <div><h3>Preparar propuestas IA para varios productos</h3>
            <p>Primera etapa: hasta 3 productos simples por lote. No incluye
              packs, combos ni identidades dudosas. Ninguna propuesta se aplica automáticamente.</p></div>
        </div>
        <div className="kiki-queue-ai-shortcuts">
          <button type="button" className="kiki-queue-ai-shortcut"
            onClick={()=>{setInput('');setQuery('');changeFilter('ai_eligible')}}>
            <KikiIcon name="layers" size={16}/>
            Ver solo productos simples aptos para IA
          </button>
          <button type="button" className="kiki-queue-ai-shortcut"
            disabled={loading||batchBusy||batchEligible.length===0}
            onClick={()=>setSelected(batchEligible.slice(0,3).map(row=>row.ecomm_id))}>
            <KikiIcon name="check" size={16}/>
            Elegir 3 simples de esta página
          </button>
        </div>
        <div className="kiki-queue-ai-actions">
          <button type="button" onClick={()=>void prepareAiBatch()}
            disabled={batchBusy||selected.length===0||selected.length>3}>
            {batchBusy?'Procesando…':'Preparar selección · sin costo IA'}
          </button>
          <span>{selected.length} seleccionado(s) · máximo 3</span>
        </div>
        {selected.length>3&&<p className="kiki-queue-ai-hint">
          Elegí como máximo 3 productos. La selección de 25 es útil para exportar CSV,
          pero no dispara 25 solicitudes pagas.</p>}
        {filter==='ai_eligible'&&<p className="kiki-queue-ai-hint">
          Estos productos no figuran como combo y tienen identidad API estable.
          Eso permite preparar propuestas, pero no confirma marca, GTIN ni datos comerciales.
        </p>}
        {batchError&&<p className="kiki-queue-error" role="alert">{batchError}</p>}
        {batchPlan&&<div className="kiki-queue-ai-plan">
          <strong>Revisión previa del lote</strong>
          <p>{batchPlan.length} fichas seleccionadas ·
            {' '}{batchPlan.filter(x=>!x.reuse).length} solicitud(es) nueva(s) ·
            {' '}{batchPlan.filter(x=>!!x.reuse).length} propuesta(s) reutilizable(s).</p>
          <p>Solicitudes disponibles hoy: {batchRemaining??'—'} de 10.
            El límite del backend prevalece si otro operador también utiliza IA.</p>
          <ul>{batchPlan.map(item=><li key={item.row.ecomm_id}>
            SKU {item.row.sku}: {item.reuse?'propuesta guardada, sin nuevo costo':
              'requiere generar propuesta'}
          </li>)}</ul>
          {!batchEnabled&&<p>La IA no está habilitada actualmente en Render.</p>}
          <button type="button" className="kiki-queue-ai-confirm"
            disabled={batchBusy||!batchEnabled||
              batchPlan.filter(x=>!x.reuse).length>(batchRemaining??0)}
            onClick={()=>void generateAiBatch()}>
            <KikiIcon name="sparkles" size={16}/> Generar propuestas y guardar para revisión
          </button>
        </div>}
        {batchProgress&&<p role="status" className="kiki-queue-ai-hint">{batchProgress}</p>}
        {batchResults.length>0&&<div className="kiki-queue-ai-results">
          <strong>Resultado de la preparación</strong>
          {batchResults.map(result=><div key={result.ecomm_id} className="kiki-queue-ai-result">
            <div><span>SKU {result.sku} · {result.result==='FAILED'?'No generado':
              result.result==='REUSED'?'Propuesta reutilizada':'Propuesta generada'}</span>
              <small>{result.message}</small></div>
            {result.draft_id!==null&&<Link to={'/workspace?id='+encodeURIComponent(result.ecomm_id)}>
              Revisar propuesta <KikiIcon name="arrow-right" size={14}/></Link>}
          </div>)}
          <p className="kiki-queue-ai-hint">Se guardaron únicamente propuestas de IA.
            Para modificar y conservar la ficha comercial, revisá cada propuesta y usá
            Guardar borrador en Mejorar productos.</p>
        </div>}
      </section>
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
            <div className="kiki-queue-channel-tags">
              <span>{chanStatus(row.channel_coverage.ml.status,'ML')}</span>
              <span>{chanStatus(row.channel_coverage.tn.status,'TN')}</span>
            </div>
            <p className="kiki-queue-explain">{row.reason}</p>
            {row.channel_coverage.ml.listing_ids.length>0&&
              <small>Identificadores ML candidatos: {row.channel_coverage.ml.listing_ids.join(', ')}</small>}
            {row.channel_coverage.ml.status==='SKU_CANDIDATE'&&
              <small>Compará el título y la presentación antes de aceptar la vinculación.</small>}
            <div className="kiki-queue-tags">
              {row.flags.filter(f=>f!=='untouched'&&f!=='draft'&&f!=='ready'&&f!=='identity'&&f!=='missing_gtin').slice(0,5)
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
