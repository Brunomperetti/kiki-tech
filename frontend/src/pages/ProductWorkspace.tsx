import {FormEvent,useEffect,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from '../components/KikiIcon';
import {CommercialBackofficeFields,assessCommercialReadiness} from '../components/CommercialBackofficeFields';
import type {EcommApiCatalog,EcommApiProductEdit,EcommEditableFields,EcommEditStatus,EcommSavedEdits,EcommAiLatest,EcommAiSuggestion,EcommApiBrandHints} from '../types/ecomm-app';
import '../workspace.css';

const blank:EcommEditableFields={
  brand:'',manufacturer:'',title:'',short_title:'',short_description:'',
  description:'',details:'',presentation:'',category:'',subcategory:'',
  seo_title:'',seo_description:'',seo_keywords:'',proposed_gtin:'',note:'',
  attributes:[],media:[],sources:[],
};
const label=(status:string)=>status==='READY_FOR_CHANNELS'?'Lista para canales (interno)':status==='READY_FOR_REVIEW'?'Lista para revisión':status==='DRAFT'?'Borrador guardado':'Sin editar';
const fail=(e:unknown)=>e instanceof Error?e.message:'No se pudo completar la consulta.';
const date=(v:string|null)=>v?new Date(v).toLocaleString('es-AR'):'Sin fecha';
const text=(v:string|null|number|undefined)=>v===null||v===undefined||v===''?'No informado':String(v);

export function ProductWorkspace(){
  const [params,setParams]=useSearchParams();
  const targetId=params.get('id')||'';
  const [query,setQuery]=useState('');
  const [catalog,setCatalog]=useState<EcommApiCatalog|null>(null);
  const [catalogPage,setCatalogPage]=useState(1);
  const [saved,setSaved]=useState<EcommSavedEdits|null>(null);
  const [edit,setEdit]=useState<EcommApiProductEdit|null>(null);
  const [fields,setFields]=useState<EcommEditableFields>({...blank});
  const [status,setStatus]=useState<EcommEditStatus>('DRAFT');
  const [loading,setLoading]=useState(false);
  const [loadingEdit,setLoadingEdit]=useState(false);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [showHistory,setShowHistory]=useState(false);
  const [filterSaved,setFilterSaved]=useState(false);
  const [savedQuery,setSavedQuery]=useState('');
  const [savedSearch,setSavedSearch]=useState('');
  const [savedStatus,setSavedStatus]=useState('');
  const [savedPage,setSavedPage]=useState(1);
  const [savedLoading,setSavedLoading]=useState(false);
  const [aiInfo,setAiInfo]=useState<EcommAiLatest|null>(null);
  const [aiBusy,setAiBusy]=useState(false);
  const [aiError,setAiError]=useState('');
  const [aiMessage,setAiMessage]=useState('');
  const [brandHints,setBrandHints]=useState<EcommApiBrandHints|null>(null);
  const [brandHintsError,setBrandHintsError]=useState('');



  async function loadSaved(search=savedSearch,filter=savedStatus,page=savedPage){
    setSavedLoading(true);
    try{setSaved(await api.ecommSavedEdits(search,filter,page,25));}
    catch(e){setSaved(null);setError(fail(e))}
    finally{setSavedLoading(false)}
  }
  async function loadCatalog(search:string,page:number){
    setLoading(true);setError('');
    try{setCatalog(await api.ecommApiCatalog(search,page,15));setCatalogPage(page);}
    catch(e){setCatalog(null);setError(fail(e));}
    finally{setLoading(false)}
  }
  useEffect(()=>{void loadCatalog('',1)},[]);
  useEffect(()=>{void loadSaved(savedSearch,savedStatus,savedPage)},[savedSearch,savedStatus,savedPage]);
  useEffect(()=>{
    let active=true;
    setBrandHints(null);setBrandHintsError('');
    if(targetId){
      api.ecommBrandHints(targetId).then(value=>{if(active)setBrandHints(value)})
        .catch(e=>{if(active)setBrandHintsError(fail(e))});
    }
    return ()=>{active=false};
  },[targetId]);
  useEffect(()=>{
    let active=true;
    setAiInfo(null);setAiError('');setAiMessage('');
    if(targetId){
      api.ecommAiLatest(targetId).then(info=>{if(active)setAiInfo(info)})
        .catch(e=>{if(active)setAiError(fail(e))});
    }
    return ()=>{active=false};
  },[targetId]);
  useEffect(()=>{
    if(!targetId){setEdit(null);setFields({...blank});setMessage('');return}
    let active=true;setLoadingEdit(true);setMessage('');setError('');
    api.ecommGetEdit(targetId).then(data=>{
      if(!active)return;
      setEdit(data);
      setFields({...blank,...data.fields});
      setStatus(data.status==='READY_FOR_REVIEW'?'READY_FOR_REVIEW':data.status==='READY_FOR_CHANNELS'?'READY_FOR_CHANNELS':'DRAFT');
      setShowHistory(false);
    }).catch(e=>{if(active){setEdit(null);setError(fail(e))}})
      .finally(()=>{if(active)setLoadingEdit(false)});
    return ()=>{active=false};
  },[targetId]);

  function open(id:string){
    if(id===targetId||saving)return;
    if(dirty&&!window.confirm('Tenés cambios sin guardar. ¿Querés descartarlos y abrir otra ficha?'))return;
    setParams({id});
  }
  function search(e:FormEvent){e.preventDefault();void loadCatalog(query.trim(),1)}
  function change<K extends keyof EcommEditableFields>(key:K,value:EcommEditableFields[K]){
    setMessage('');setFields(x=>({...x,[key]:value}))
  }
  async function persist(nextStatus:EcommEditStatus){
    if(!edit||saving||edit.source_sku_changed)return;
    setSaving(true);setError('');setMessage('');
    try{
      const next=await api.ecommSaveEdit(edit.ecomm_id,fields,nextStatus,edit.version);
      setEdit(next);setFields({...blank,...next.fields});setStatus(next.status==='READY_FOR_REVIEW'?'READY_FOR_REVIEW':next.status==='READY_FOR_CHANNELS'?'READY_FOR_CHANNELS':'DRAFT');
      setMessage('Guardado en KIKI Tech. La ficha permanece disponible cuando vuelvas a entrar.');
      await loadSaved();
      const updatedAi=await api.ecommAiLatest(next.ecomm_id).catch(()=>null);
      if(updatedAi)setAiInfo(updatedAi);
    }catch(e){setError(fail(e));}
    finally{setSaving(false)}
  }
  function useBrandHint(){
    if(!brandHints?.brand||brandHints.status!=='EVIDENCE_FOUND')return;
    if(fields.brand.trim()&&fields.brand.trim().toLocaleLowerCase()!==brandHints.brand.toLocaleLowerCase()
      &&!window.confirm('Ya hay una marca cargada. ¿Querés reemplazarla por la sugerencia de otra fuente?'))return;
    change('brand',brandHints.brand);
    setAiMessage('Marca sugerida colocada en el formulario. Verificá el envase y guardá manualmente la ficha.');
  }
  async function askAi(){
    if(!edit||aiBusy||saving||dirty||edit.source_sku_changed)return;
    setAiBusy(true);setAiError('');setAiMessage('');
    try{
      const draft=await api.ecommAiSuggest(edit.ecomm_id,edit.version);
      setAiInfo(current=>({
        enabled:current?.enabled??true,
        available:true,draft,remaining_today:draft.remaining_today??0,
      }));
      setAiMessage(draft.reused
        ?'KIKI reutilizó la propuesta anterior sin una nueva llamada paga.'
        :'La IA preparó una propuesta. Revisala antes de copiarla al formulario.');
    }catch(e){setAiError(fail(e));}
    finally{setAiBusy(false)}
  }
  function applyAi(field:'title'|'description',proposal:EcommAiSuggestion){
    if(!edit||!proposal.source_current||!proposal[field])return;
    if(fields[field].trim()&&fields[field].trim()!==proposal[field].trim()
      &&!window.confirm('Este campo ya tiene contenido. ¿Querés reemplazarlo por la propuesta IA?'))return;
    setFields(current=>({...current,[field]:proposal[field]}));
    setAiMessage('Sugerencia colocada en el formulario. Revisala y presioná Guardar borrador para conservarla en KIKI.');
    setMessage('');
  }
  const dirty=!!edit&&(JSON.stringify({...blank,...edit.fields})!==JSON.stringify(fields)
    || (edit.status!=='NOT_STARTED'&&status!==edit.status));
  useEffect(()=>{
    if(!dirty)return;
    const beforeUnload=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};
    // Warn before leaving the workspace through the main SPA navigation, too.
    const interceptLink=(e:MouseEvent)=>{
      if(!(e.target instanceof Element))return;
      const anchor=e.target.closest('a[href]');
      if(!(anchor instanceof HTMLAnchorElement))return;
      const url=new URL(anchor.href);
      if(url.origin!==window.location.origin||(
        url.pathname===window.location.pathname&&url.search===window.location.search
      ))return;
      if(!window.confirm('Tenés cambios sin guardar. ¿Querés descartarlos y salir de la ficha?')){
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener('beforeunload',beforeUnload);
    document.addEventListener('click',interceptLink,true);
    return ()=>{
      window.removeEventListener('beforeunload',beforeUnload);
      document.removeEventListener('click',interceptLink,true);
    };
  },[dirty]);
  function applySavedSearch(e:FormEvent){e.preventDefault();setSavedPage(1);setSavedSearch(savedQuery.trim());}
  return <div className="kiki-workspace">
    <header className="kiki-home-header">
      <div>
        <p className="eyebrow">KIKI TECH · TRABAJO DIARIO</p>
        <h1>Backoffice comercial de productos</h1>
        <p>Armá fichas comerciales completas, categorías, SEO, fotografías, videos y fuentes verificables.
          Todo queda guardado en KIKI con historial para preparar futuras publicaciones masivas.</p>
      </div>
      <div className="kiki-workspace-shortcuts">
        <Link className="kiki-workspace-back" to="/queue"><KikiIcon name="chart" size={17}/> Volver a cola de mejoras</Link>
        <Link className="kiki-workspace-back" to="/propuestas-ia"><KikiIcon name="sparkles" size={17}/> Propuestas IA guardadas</Link>
        <Link className="kiki-workspace-back" to="/guia"><KikiIcon name="help" size={17}/> Cómo guardar</Link>
        </div>
    </header>

    <div className="kiki-workspace-policy" role="note"><KikiIcon name="shield" size={20}/>
      <span><strong>Todo el contenido editado se conserva en PostgreSQL de KIKI.</strong>
        Ecomm-App aporta la identidad del producto por API de lectura.
        Mercado Libre, Tiendanube y el stock no se modifican automáticamente.</span>
    </div>
    {error&&<div className="kiki-workspace-alert" role="alert">{error}</div>}
    {message&&<div className="kiki-workspace-saved" role="status"><KikiIcon name="check" size={19}/>{message}</div>}
    <div className="kiki-workspace-kpis">
      <div><strong>{saved?.summary.total_saved.toLocaleString('es-AR')??'—'}</strong><span>Fichas guardadas</span></div>
      <div><strong>{saved?.summary.drafts.toLocaleString('es-AR')??'—'}</strong><span>Borradores</span></div>
      <div><strong>{saved?.summary.ready_for_review.toLocaleString('es-AR')??'—'}</strong><span>Preparadas para revisión</span></div>
      <div><strong>{saved?.summary.ready_for_channels.toLocaleString('es-AR')??'—'}</strong><span>Listas para canales (internas)</span></div>
    </div>
    <div className="kiki-workspace-grid">
      <section className="kiki-workspace-directory">
        <div className="kiki-workspace-panel-heading">
          <h2>1. Elegí un producto</h2>
          <p>Catálogo API o fichas que ya guardaron.</p>
        </div>
        <div className="kiki-workspace-tabs">
          <button aria-pressed={!filterSaved} className={!filterSaved?'active':''}
            onClick={()=>setFilterSaved(false)} type="button">Catálogo API</button>
          <button aria-pressed={filterSaved} className={filterSaved?'active':''}
            onClick={()=>setFilterSaved(true)} type="button">Fichas guardadas</button>
        </div>
        {!filterSaved&&<>
          <form onSubmit={search} className="kiki-workspace-search">
            <label htmlFor="kiki-product-search">SKU, ID o nombre</label>
            <div><input id="kiki-product-search" value={query} onChange={e=>setQuery(e.target.value)}
              placeholder="Ej.: 2500400" maxLength={80}/>
              <button type="submit" disabled={loading} aria-label="Buscar productos"><KikiIcon name="search"/></button></div>
          </form>
          {loading&&<p className="kiki-workspace-empty">Consultando catálogo Ecomm por API…</p>}
          {!loading&&catalog?.items.map((p,i)=><button
            key={(p.ecomm_id||'unknown')+'-'+i} type="button"
            disabled={!p.ecomm_id}
            className={'kiki-workspace-product '+(targetId===p.ecomm_id?'selected':'')}
            onClick={()=>p.ecomm_id&&open(p.ecomm_id)}>
            <span className="kiki-workspace-product-top"><strong>{text(p.sku)}</strong>
              <small>{p.is_combo?'Combo':p.ecomm_id?'ID '+p.ecomm_id:'Sin ID'}</small></span>
            <span>{text(p.product_name)}</span>
            <KikiIcon name="arrow-right" size={15}/>
          </button>)}
          {catalog?.total_matches===0&&<p className="kiki-workspace-empty">No se encontraron productos para ese término.</p>}
          <div className="kiki-workspace-pages">
            <button type="button" disabled={!catalog||loading||catalogPage===1}
              onClick={()=>void loadCatalog(query.trim(),catalogPage-1)}>Anterior</button>
            <span>{catalog?catalog.total_matches.toLocaleString('es-AR'):'—'} encontrados</span>
            <button type="button" disabled={!catalog||loading||catalogPage*15>=catalog.total_matches}
              onClick={()=>void loadCatalog(query.trim(),catalogPage+1)}>Siguiente</button>
          </div>
        </>}
        {filterSaved&&<>
          <form className="kiki-workspace-search" onSubmit={applySavedSearch}>
            <label htmlFor="kiki-saved-search">Buscar entre las fichas guardadas</label>
            <div>
              <input id="kiki-saved-search" value={savedQuery} maxLength={80}
                onChange={e=>setSavedQuery(e.target.value)}
                placeholder="SKU, marca, ID o título"/>
              <button type="submit" disabled={savedLoading} aria-label="Buscar fichas guardadas">
                <KikiIcon name="search"/>
              </button>
            </div>
          </form>
          <label className="kiki-workspace-filter-label" htmlFor="kiki-saved-status">Estado de revisión
            <select id="kiki-saved-status" value={savedStatus}
              onChange={e=>{setSavedStatus(e.target.value);setSavedPage(1)}}>
              <option value="">Todos los estados</option>
              <option value="DRAFT">Borradores</option>
              <option value="READY_FOR_REVIEW">Listas para revisión interna</option>
              <option value="READY_FOR_CHANNELS">Listas para canales</option>
            </select>
          </label>
          {savedLoading&&<p className="kiki-workspace-small" role="status">Cargando fichas guardadas…</p>}
          {saved?.items.map(row=><button type="button" key={row.ecomm_id}
            className={'kiki-workspace-product '+(targetId===row.ecomm_id?'selected':'')}
            onClick={()=>open(row.ecomm_id)}>
            <span className="kiki-workspace-product-top"><strong>SKU {row.sku}</strong><small>{label(row.status)}</small></span>
            <span>{row.title||row.product_name}</span>
            <KikiIcon name="arrow-right" size={15}/>
          </button>)}
          {!savedLoading&&saved?.total===0&&<p className="kiki-workspace-empty">
            No hay fichas para este filtro. Probá otro SKU o elegí «Todos los estados».
          </p>}
          {saved&&<div className="kiki-workspace-pages">
            <button type="button" disabled={savedLoading||savedPage===1}
              onClick={()=>setSavedPage(page=>Math.max(1,page-1))}>Anterior</button>
            <span>Página {savedPage} · {saved.total.toLocaleString('es-AR')} fichas</span>
            <button type="button" disabled={savedLoading||savedPage*25>=saved.total}
              onClick={()=>setSavedPage(page=>page+1)}>Siguiente</button>
          </div>}
        </>}
      </section>
      <section className="kiki-workspace-editor">
        {!targetId&&<div className="kiki-workspace-start"><KikiIcon name="layers" size={36}/>
          <h2>Seleccioná un producto</h2><p>Abrí una ficha del catálogo API y completá marca, título, descripción o GTIN propuesto.</p></div>}
        {targetId&&loadingEdit&&<p className="kiki-workspace-empty">Abriendo la ficha vinculada al ID Ecomm…</p>}
        {targetId&&!loadingEdit&&!edit&&<p className="kiki-workspace-empty">No se pudo abrir la ficha. Revisá el mensaje y seleccioná otro producto.</p>}
        {edit&&!loadingEdit&&<div className="kiki-workspace-editor-body">
          <div className="kiki-workspace-panel-heading">
            <p className="eyebrow">2. EDITAR FICHA EN KIKI TECH</p>
            <h2>{edit.source.product_name}</h2>
            <div className="kiki-workspace-badges"><span>ID Ecomm: {edit.ecomm_id}</span>
              <span>SKU: {edit.source.sku}</span><span>{edit.source.is_combo?'Combo / pack':'Producto / variante'}</span></div>
            <p className="kiki-workspace-small">Completá el contenido abajo. Para registrar una fuente oficial, abrí «Fuentes y control editorial».</p>
          </div>
          <div className="kiki-workspace-source"><strong><KikiIcon name="link" size={15}/> Referencia Ecomm-App API (sin modificar)</strong>
            <p>GTIN original: {text(edit.source.gtin)} · Stock de referencia: {text(edit.source.stock_at_capture)}
              · Captura API: {date(edit.source.captured_at)}. La actualización periódica no modifica las fichas comerciales.</p>
          </div>
          {edit.source_sku_changed&&<p className="kiki-workspace-alert" role="alert">
            Este ID tenía otro SKU cuando guardaron la ficha. Para evitar aplicar cambios al producto equivocado,
            el guardado quedó bloqueado hasta revisar la identidad con Ecomm-App.</p>}
          <section className="kiki-workspace-brand-hints" aria-label="Marcas sugeridas por evidencia de canales">
            <div className="kiki-workspace-brand-title">
              <KikiIcon name="search" size={21}/>
              <div><h3>Marca sugerida por evidencia</h3>
                <p>Sin IA paga: buscamos el mismo SKU exacto en los datos guardados
                  de Tiendanube y Mercado Libre.</p></div>
            </div>
            {brandHintsError&&<p role="alert" className="kiki-workspace-ai-note">
              No se pudieron consultar las marcas: {brandHintsError}</p>}
            {!brandHints&&!brandHintsError&&<p className="kiki-workspace-ai-note">
              Buscando coincidencias verificables…</p>}
            {brandHints&&<>
              <p className="kiki-workspace-brand-reason">{brandHints.reason}</p>
              {brandHints.status==='EVIDENCE_FOUND'&&brandHints.brand&&
                <div className="kiki-workspace-brand-row">
                  <div><small>MARCA DECLARADA POR OTRO CANAL</small><strong>{brandHints.brand}</strong></div>
                  <button type="button" onClick={useBrandHint}>Usar marca</button>
                </div>}
              {brandHints.evidence.length>0&&<details className="kiki-workspace-ai-evidence">
                <summary>Ver {brandHints.evidence.length} fuente(s) y fechas</summary>
                <ul>{brandHints.evidence.map((e,i)=><li key={e.channel+e.source_id+i}>
                  <strong>{e.channel==='TIENDANUBE_CSV'?'Tiendanube CSV':'Mercado Libre API'}:</strong>
                  {' '}{e.brand} · {e.title||e.source_id}
                  <small> · Captura: {e.snapshot_at?date(e.snapshot_at):'Sin fecha'}</small>
                </li>)}</ul>
              </details>}
              <p className="kiki-workspace-ai-note">
                Esta coincidencia no verifica al fabricante. Si hay varias marcas o SKUs ambiguos,
                KIKI no completa el campo automáticamente.
              </p>
            </>}
          </section>
          <section className="kiki-workspace-ai" aria-label="Asistente de inteligencia artificial">
            <div className="kiki-workspace-ai-head">
              <span className="kiki-workspace-ai-icon"><KikiIcon name="sparkles" size={21}/></span>
              <div><h3>KIKI AI · Asistente de fichas</h3>
                <p>Generá propuestas de título y descripción a partir de los datos disponibles,
                  sin cargar todo a mano.</p>
              </div>
            </div>
            <div className="kiki-workspace-ai-tools">
              <button type="button" className="kiki-workspace-ai-run"
                disabled={aiBusy||saving||dirty||edit.source_sku_changed||!aiInfo?.enabled
                  ||(aiInfo?.remaining_today===0&&!aiInfo?.draft?.source_current)}
                onClick={()=>void askAi()}>
                <KikiIcon name="sparkles" size={16}/>
                {aiBusy?'Generando propuesta…':'Sugerir con IA'}
              </button>
              <span>{aiInfo
                ?aiInfo.enabled?('Solicitudes disponibles hoy: '+aiInfo.remaining_today+' de 10')
                  :'IA no habilitada en el servidor'
                :'Consultando estado IA…'}</span>
            </div>
            {dirty&&<p className="kiki-workspace-ai-note">Guardá primero tus cambios manuales para
              que la IA utilice la versión actual de esta ficha.</p>}
            {aiError&&<p className="kiki-workspace-alert" role="alert">{aiError}</p>}
            {aiMessage&&<p role="status" className="kiki-workspace-ai-success">{aiMessage}</p>}
            {aiInfo?.draft&&<div className="kiki-workspace-ai-result">
              <div className="kiki-workspace-ai-result-head">
                <strong>Propuesta IA #{aiInfo.draft.draft_id}</strong>
                <span>{aiInfo.draft.source_current?'Basada en esta versión de la ficha':'Propuesta desactualizada · solo consulta'}</span>
              </div>
              {aiInfo.draft.warnings?.length>0&&<div className="kiki-workspace-ai-safety" role="alert">
                <KikiIcon name="alert" size={18}/>
                <div><strong>Control de calidad de KIKI</strong>
                  <ul>{aiInfo.draft.warnings.map((w,i)=><li key={i}>{w}</li>)}</ul>
                </div>
              </div>}
              <div className="kiki-workspace-ai-field">
                <small>Título sugerido</small>
                <p>{aiInfo.draft.title}</p>
                <button type="button" disabled={!aiInfo.draft.source_current}
                  onClick={()=>applyAi('title',aiInfo.draft!)}>Usar este título</button>
              </div>
              <div className="kiki-workspace-ai-field">
                <small>Descripción sugerida</small>
                <p>{aiInfo.draft.description||'Descripción no disponible: falta evidencia comercial suficiente. No uses una descripción de pack sin corroborar su contenido.'}</p>
                <button type="button" disabled={!aiInfo.draft.source_current||!aiInfo.draft.description}
                  onClick={()=>applyAi('description',aiInfo.draft!)}>Usar esta descripción</button>
              </div>
              {aiInfo.draft.questions.length>0&&<div className="kiki-workspace-ai-questions">
                <strong>Qué falta verificar</strong>
                <ul>{aiInfo.draft.questions.map((q,i)=><li key={i}>{q}</li>)}</ul>
              </div>}
              <details className="kiki-workspace-ai-evidence">
                <summary>Ver datos utilizados por la IA</summary>
                <ul>{aiInfo.draft.evidence.filter(f=>f.value!==null&&f.value!=='').map(f=>
                  <li key={f.field}><strong>{f.field}:</strong> {String(f.value)}
                    <small>{f.source==='KIKI_EDITOR_UNVERIFIED'
                      ?' · dato interno no verificado':' · copia API / referencia interna'}</small>
                  </li>)}</ul>
              </details>
              <p className="kiki-workspace-ai-note">Sugerencia no verificada. Copiarla no guarda,
                aprueba ni publica el producto. No propone GTIN ni composición de combos.</p>
            </div>}
          </section>
          <CommercialBackofficeFields fields={fields} onChange={change}
            readiness={assessCommercialReadiness(fields)}/>
          <div className="kiki-workspace-footer">
            <div><strong>Estado: {label(edit.status)}</strong><small>
              {edit.available?'Última edición: '+date(edit.updated_at):'Primera edición · todavía no guardada'}
            </small></div>
            <button type="button" disabled={saving||edit.source_sku_changed} onClick={()=>void persist('DRAFT')}>
              {saving?'Guardando…':'Guardar borrador'}</button>
            <button type="button" disabled={saving||edit.source_sku_changed}
              onClick={()=>void persist('READY_FOR_REVIEW')}>
              {saving?'Guardando…':'Enviar a revisión interna'}</button>
            <button type="button" disabled={saving||edit.source_sku_changed||!assessCommercialReadiness(fields).ready}
              className="primary" onClick={()=>void persist('READY_FOR_CHANNELS')}>
              {saving?'Guardando…':'Dejar lista para canales'}</button>
          </div>
          {dirty&&<p role="status" className="kiki-workspace-unsaved">
            <KikiIcon name="alert" size={16}/> Tenés cambios sin guardar.
            Guardalos antes de salir o abrir otro producto.
          </p>}
          <button type="button" className="kiki-workspace-history-toggle" onClick={()=>setShowHistory(!showHistory)}>
            <KikiIcon name="clock" size={17}/>{showHistory?'Ocultar historial':'Ver historial de ediciones'} ({edit.history.length})
          </button>
          {showHistory&&<ol className="kiki-workspace-history">{[...edit.history].reverse().map(item=><li key={item.version}>
            <strong>Versión {item.version}</strong> · {date(item.at)} · {label(item.new_status)}
            <small>{Object.keys(item.changes).join(', ')||'Cambio de estado'}</small>
          </li>)}</ol>}
        </div>}
      </section>
    </div>
  </div>;
}
