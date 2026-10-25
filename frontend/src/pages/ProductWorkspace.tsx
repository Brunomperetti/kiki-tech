import {FormEvent,useEffect,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from '../components/KikiIcon';
import type {EcommApiCatalog,EcommApiProductEdit,EcommEditableFields,EcommEditStatus,EcommSavedEdits} from '../types/ecomm-app';
import '../workspace.css';

const blank:EcommEditableFields={brand:'',title:'',description:'',proposed_gtin:'',note:''};
const label=(status:string)=>status==='READY_FOR_REVIEW'?'Lista para revisión':status==='DRAFT'?'Borrador guardado':'Sin editar';
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

  async function loadSaved(){
    try{setSaved(await api.ecommSavedEdits());}
    catch(e){setError(fail(e))}
  }
  async function loadCatalog(search:string,page:number){
    setLoading(true);setError('');
    try{setCatalog(await api.ecommApiCatalog(search,page,15));setCatalogPage(page);}
    catch(e){setCatalog(null);setError(fail(e));}
    finally{setLoading(false)}
  }
  useEffect(()=>{void loadSaved();void loadCatalog('',1)},[]);
  useEffect(()=>{
    if(!targetId){setEdit(null);setFields({...blank});setMessage('');return}
    let active=true;setLoadingEdit(true);setMessage('');setError('');
    api.ecommGetEdit(targetId).then(data=>{
      if(!active)return;
      setEdit(data);
      setFields({...blank,...data.fields});
      setStatus(data.status==='READY_FOR_REVIEW'?'READY_FOR_REVIEW':'DRAFT');
      setShowHistory(false);
    }).catch(e=>{if(active){setEdit(null);setError(fail(e))}})
      .finally(()=>{if(active)setLoadingEdit(false)});
    return ()=>{active=false};
  },[targetId]);

  function open(id:string){setParams({id});}
  function search(e:FormEvent){e.preventDefault();void loadCatalog(query.trim(),1)}
  function change<K extends keyof EcommEditableFields>(key:K,value:EcommEditableFields[K]){
    setMessage('');setFields(x=>({...x,[key]:value}))
  }
  async function persist(nextStatus:EcommEditStatus){
    if(!edit||saving||edit.source_sku_changed)return;
    setSaving(true);setError('');setMessage('');
    try{
      const next=await api.ecommSaveEdit(edit.ecomm_id,fields,nextStatus,edit.version);
      setEdit(next);setFields({...blank,...next.fields});setStatus(next.status==='READY_FOR_REVIEW'?'READY_FOR_REVIEW':'DRAFT');
      setMessage('Guardado en KIKI Tech. La ficha permanece disponible cuando vuelvas a entrar.');
      await loadSaved();
    }catch(e){setError(fail(e));}
    finally{setSaving(false)}
  }
  const dirty=!!edit&&(JSON.stringify({...blank,...edit.fields})!==JSON.stringify(fields)
    || (edit.status!=='NOT_STARTED'&&status!==edit.status));
  return <div className="kiki-workspace">
    <header className="kiki-home-header">
      <div>
        <p className="eyebrow">KIKI TECH · TRABAJO DIARIO</p>
        <h1>Mejorar productos</h1>
        <p>Buscá productos de la API Ecomm-App, completá sus datos comerciales y guardá las mejoras
          en KIKI Tech. Los cambios quedan registrados con historial y no modifican las tiendas.</p>
      </div>
      <Link className="kiki-workspace-back" to="/"><KikiIcon name="home" size={17}/> Inicio</Link>
    </header>

    <div className="kiki-workspace-policy" role="note"><KikiIcon name="shield" size={20}/>
      <span><strong>Las ediciones se guardan en PostgreSQL de KIKI.</strong>
        Ecomm-App aporta la identidad del producto por API de lectura.
        Mercado Libre, Tiendanube y el stock no se modifican automáticamente.</span>
    </div>
    {error&&<div className="kiki-workspace-alert" role="alert">{error}</div>}
    {message&&<div className="kiki-workspace-saved" role="status"><KikiIcon name="check" size={19}/>{message}</div>}
    <div className="kiki-workspace-kpis">
      <div><strong>{saved?.summary.total_saved.toLocaleString('es-AR')??'—'}</strong><span>Fichas guardadas</span></div>
      <div><strong>{saved?.summary.drafts.toLocaleString('es-AR')??'—'}</strong><span>Borradores</span></div>
      <div><strong>{saved?.summary.ready_for_review.toLocaleString('es-AR')??'—'}</strong><span>Preparadas para revisión</span></div>
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
          {saved?.items.map(row=><button type="button" key={row.ecomm_id}
            className={'kiki-workspace-product '+(targetId===row.ecomm_id?'selected':'')}
            onClick={()=>open(row.ecomm_id)}>
            <span className="kiki-workspace-product-top"><strong>SKU {row.sku}</strong><small>{label(row.status)}</small></span>
            <span>{row.title||row.product_name}</span>
            <KikiIcon name="arrow-right" size={15}/>
          </button>)}
          {!saved?.items.length&&<p className="kiki-workspace-empty">Todavía no hay fichas guardadas. Buscá un producto del catálogo API y empezá a mejorarlo.</p>}
          {saved&&saved.total>saved.items.length&&<p className="kiki-workspace-small">
            Se muestran las primeras {saved.items.length} fichas. Próximamente agregaremos filtros avanzados.
          </p>}
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
          </div>
          <div className="kiki-workspace-source"><strong><KikiIcon name="link" size={15}/> Referencia Ecomm-App API (sin modificar)</strong>
            <p>GTIN original: {text(edit.source.gtin)} · Stock capturado: {text(edit.source.stock_at_capture)}
              · Captura: {date(edit.source.captured_at)}</p>
          </div>
          {edit.source_sku_changed&&<p className="kiki-workspace-alert" role="alert">
            Este ID tenía otro SKU cuando guardaron la ficha. Para evitar aplicar cambios al producto equivocado,
            el guardado quedó bloqueado hasta revisar la identidad con Ecomm-App.</p>}
          <div className="kiki-workspace-form">
            <label>Marca comercial
              <input value={fields.brand} onChange={e=>change('brand',e.target.value)} maxLength={120}
                placeholder="Ej.: Vitamin Way"/></label>
            <label>Título mejorado para el catálogo
              <input value={fields.title} onChange={e=>change('title',e.target.value)} maxLength={180}
                placeholder="Título claro con marca, producto y presentación"/></label>
            <label>Descripción comercial
              <textarea value={fields.description} onChange={e=>change('description',e.target.value)}
                maxLength={3000} rows={5} placeholder="Redactá la descripción verificada del producto"/></label>
            <label>GTIN propuesto (opcional)
              <input value={fields.proposed_gtin} onChange={e=>change('proposed_gtin',e.target.value)}
                maxLength={14} inputMode="numeric" placeholder="8, 12, 13 o 14 dígitos"/></label>
            <p className="kiki-workspace-small">El GTIN es una propuesta interna, no reemplaza el código original de la API.
              Se valida el dígito verificador al guardar y se debe contrastar con el envase.</p>
            <label>Observaciones y evidencia
              <textarea value={fields.note} onChange={e=>change('note',e.target.value)}
                maxLength={1200} rows={3} placeholder="Qué revisaron, de dónde salió la información o qué falta confirmar"/></label>
          </div>
          <div className="kiki-workspace-footer">
            <div><strong>Estado: {label(edit.status)}</strong><small>
              {edit.available?'Última edición: '+date(edit.updated_at):'Primera edición · todavía no guardada'}
            </small></div>
            <button type="button" disabled={saving||edit.source_sku_changed} onClick={()=>void persist('DRAFT')}>
              {saving?'Guardando…':'Guardar borrador'}</button>
            <button type="button" disabled={saving||edit.source_sku_changed} className="primary"
              onClick={()=>void persist('READY_FOR_REVIEW')}>
              {saving?'Guardando…':'Enviar a revisión interna'}</button>
          </div>
          {dirty&&<p className="kiki-workspace-small">Tenés cambios en el formulario. Guardalos antes de abrir otro producto.</p>}
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
