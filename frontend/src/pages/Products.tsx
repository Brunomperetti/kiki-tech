import {useEffect,useMemo,useState} from 'react';
import {ProductDetail} from '../components/ProductDetail';
import {api} from '../services/api';
import type {Result,Status} from '../types/catalog';
import type {TiendanubeCatalogRow} from '../utils/catalogProductView';
import {productIdentity,reconciliationLabel} from '../utils/catalogProductView';

const PAGE_SIZE=25;
const filters: {value:Status;label:string}[]=[
  {value:'ALREADY_PUBLISHED',label:'Encontrados en ML'},
  {value:'CANDIDATE_TO_PUBLISH',label:'Candidatos para preparar'},
  {value:'REVIEW_REQUIRED',label:'Necesitan revisión'},
  {value:'POSSIBLE_DUPLICATE',label:'Posibles duplicados'},
  {value:'INCOMPLETE_DATA',label:'Datos incompletos'},
  {value:'INVALID_SKU',label:'Problemas de SKU'},
  {value:'INVALID_EAN',label:'Problemas de código'},
  {value:'UNMATCHED_ML_LISTING',label:'Publicaciones ML sin asociación'},
];

export function Products(){
  const [items,setItems]=useState<Result[]>([]);
  const [search,setSearch]=useState('');
  const [status,setStatus]=useState<Status|''>('');
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [page,setPage]=useState(1);
  const [selected,setSelected]=useState<Result|null>(null);
  const [tnState,setTnState]=useState<'idle'|'loading'|'ready'|'error'>('idle');
  const [tnRows,setTnRows]=useState<TiendanubeCatalogRow[]>([]);
  const [tnAvailable,setTnAvailable]=useState(false);

  useEffect(()=>{
    let active=true;
    const timer=window.setTimeout(()=>{
      const params=new URLSearchParams();
      if(search.trim())params.set('search',search.trim());
      if(status)params.set('status',status);
      setLoading(true);
      setError('');
      void api.products(`?${params.toString()}`).then(rows=>{
        if(!active)return;
        setItems(rows);
        setPage(1);
        setSelected(null);
      }).catch(e=>{
        if(!active)return;
        setError(e instanceof Error?e.message:'No pudimos consultar el catálogo.');
        setItems([]);
      }).finally(()=>{if(active)setLoading(false)});
    },search?300:0);
    return ()=>{active=false;window.clearTimeout(timer)};
  },[search,status]);

  useEffect(()=>{
    // One read-only CSV request per visit to Productos, only when a ficha opens.
    // Do not cancel it when the selected product changes during loading.
    if(!selected||tnState!=='idle')return;
    setTnState('loading');
    void api.tiendanubeReport().then(response=>{
      setTnRows(response.items||[]);
      setTnAvailable(response.available===true);
      setTnState('ready');
    }).catch(()=>setTnState('error'));
  },[selected,tnState]);

  const pages=Math.ceil(items.length/PAGE_SIZE);
  const visible=useMemo(()=>items.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE),[items,page]);
  const format=(value:unknown)=>value==null||value===''?'—':String(value);

  return <div className="kiki-catalog">
    <header className="kiki-home-header">
      <div><p className="eyebrow">KIKI TECH · CATÁLOGO</p><h1>Encontrá cualquier producto.</h1><p>Buscá por nombre, SKU o EAN. Abrí su ficha para ver Ecomm, Mercado Libre, Tiendanube y propuestas de IA.</p></div>
    </header>

    <div className="kiki-catalog-filters">
      <label>Buscar en el catálogo conciliado
        <input type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Nombre del producto, SKU o código de barras…" />
      </label>
      <label>Estado del análisis
        <select value={status} onChange={e=>setStatus(e.target.value as Status|'')}>
          <option value="">Todos</option>
          {filters.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
    </div>

    <div className="kiki-catalog-summary" aria-live="polite">
      <strong>{loading?'Buscando…':error?'No se pudo consultar':`${items.length.toLocaleString('es-AR')} resultados`}</strong>
      <span>Resultados de la última conciliación Ecomm–ML; los datos de Tiendanube se consultan al abrir cada ficha.</span>
    </div>
    {error&&<div className="notice warning" role="alert">{error}</div>}

    <div className={selected?'kiki-catalog-workspace is-open':'kiki-catalog-workspace'}>
      <section className="kiki-catalog-results" aria-label="Resultados de productos">
        {loading?<div className="kiki-catalog-empty">Consultando el catálogo…</div>:items.length===0?<div className="kiki-catalog-empty">No encontramos resultados con esos filtros. Podés probar otro nombre o código.</div>:<>
          <div className="kiki-catalog-list">
            {visible.map((item,index)=>{
              const actualIndex=(page-1)*PAGE_SIZE+index;
              const key=productIdentity(item,actualIndex);
              const active=selected===item;
              return <article key={key} className={active?'kiki-catalog-row is-selected':'kiki-catalog-row'}>
                <div className="kiki-catalog-item">
                  <strong>{item.product?.name||item.listing?.title||'Sin nombre'}</strong>
                  <span>SKU: {format(item.product?.sku_variant||item.product?.sku_effective||item.product?.sku)} · EAN: {format(item.product?.ean)}</span>
                  <small>{reconciliationLabel(item.status)}</small>
                </div>
                <button type="button" className="kiki-detail-open" onClick={()=>setSelected(item)} aria-pressed={active}>{active?'Ficha abierta':'Ver ficha →'}</button>
              </article>;
            })}
          </div>
          <div className="kiki-catalog-pages">
            <span>Página {page} de {pages}</span>
            <div><button type="button" className="secondary" disabled={page===1} onClick={()=>setPage(n=>Math.max(1,n-1))}>← Anterior</button><button type="button" className="secondary" disabled={page>=pages} onClick={()=>setPage(n=>Math.min(pages,n+1))}>Siguiente →</button></div>
          </div>
        </>}
      </section>
      {selected&&<ProductDetail result={selected} tiendanubeLoaded={tnState==='ready'||tnState==='error'} tiendanubeAvailable={tnAvailable&&tnState==='ready'} tiendanubeRows={tnRows} onClose={()=>setSelected(null)}/>}
    </div>
    <p className="kiki-home-footnote">KIKI solo propone asociaciones basadas en la información disponible. Una coincidencia exacta de SKU no confirma por sí sola el vínculo de inventario ni la identidad de una variante. Ninguna acción de esta pantalla modifica canales externos.</p>
  </div>;
}
