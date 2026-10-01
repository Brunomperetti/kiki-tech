import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {PrepublicationCheckStatus,PrepublicationReport} from '../types/catalog';
import '../prepublication.css';

function checkLabel(status:PrepublicationCheckStatus){
  if(status==='PASSED')return 'OK';
  if(status==='WAITING_IMAGE_DATA')return 'Faltan imágenes';
  if(status==='WAITING_ML_CONNECTION')return 'Esperando conexión ML';
  if(status==='READY_TO_VALIDATE')return 'Listo para validar';
  return 'Bloqueado';
}

export function Prepublication(){
  const [report,setReport]=useState<PrepublicationReport|null>(null);
  const [search,setSearch]=useState('');
  const [source,setSource]=useState('');
  const [error,setError]=useState('');

  useEffect(()=>{api.prepublication().then(data=>{setReport(data);setError('')}).catch(err=>setError(err instanceof Error?err.message:'No se pudo cargar pre-publicación.'))},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (report?.items||[]).filter(item=>{
      if(source&&item.core_source!==source)return false;
      if(!term)return true;
      return [item.product.sku,item.product.name,item.verified_core_data.brand,item.verified_core_data.ean,item.verified_core_data.source_name].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[report,search,source]);

  if(error&&!report)return <><header><div><p className="eyebrow">PRE-PUBLICACIÓN</p><h1>Validación final</h1></div></header><div className="notice warning">{error}</div></>;
  if(!report)return <div className="auth-loading">Preparando pre-publicación…</div>;
  const s=report.summary;

  return <>
    <header><div><p className="eyebrow">MVP3.7 · PRE-PUBLICACIÓN</p><h1>Validación final antes del preview</h1><p>Reúne productos con datos centrales validados y muestra qué controles todavía faltan antes de publicar.</p></div></header>
    <div className="notice warning"><strong>No publica nada.</strong> Esta pantalla es una lista de control. Imágenes, categoría, atributos, preview y confirmación humana siguen siendo obligatorios.</div>

    <section className="cards prepub-cards">
      <article><span>En pre-publicación</span><strong>{s.total.toLocaleString('es-AR')}</strong></article>
      <article><span>Desde Ecomm validado</span><strong>{s.from_ecomm_core.toLocaleString('es-AR')}</strong></article>
      <article><span>Desde evidencia aceptada</span><strong>{s.from_accepted_evidence.toLocaleString('es-AR')}</strong></article>
      <article><span>Imágenes aprobadas</span><strong>{s.approved_images.toLocaleString('es-AR')}</strong></article>
      <article><span>Esperando imágenes</span><strong>{s.waiting_images.toLocaleString('es-AR')}</strong></article>
      <article><span>Listos para preview</span><strong>{s.ready_for_preview.toLocaleString('es-AR')}</strong></article>
    </section>

    <section className="panel prepub-roadmap">
      <h2>Qué falta para publicar</h2>
      <div className="prepub-flow"><span className="done">Datos centrales ✓</span><b>→</b><span>Imágenes</span><b>→</b><span>Categoría ML</span><b>→</b><span>Atributos</span><b>→</b><span>Preview</span><b>→</b><span>Confirmación humana</span></div>
      <p>{report.mercadolibre_connected?'Mercado Libre está conectado: categoría y atributos quedan listos para la próxima validación.':'Mercado Libre todavía no está conectado.'}</p>
    </section>

    <section className="panel">
      <div className="filters prepub-filters">
        <input placeholder="Buscar SKU, producto, marca o EAN" value={search} onChange={e=>setSearch(e.target.value)}/>
        <select value={source} onChange={e=>setSource(e.target.value)}><option value="">Todos los orígenes</option><option value="ECOMM_CORE">Ecomm validado</option><option value="ACCEPTED_EVIDENCE">Evidencia aceptada</option></select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> de {s.total.toLocaleString('es-AR')} productos</p>
      {items.length===0&&<div className="prepub-empty"><strong>Todavía no hay productos para mostrar con este filtro.</strong></div>}
      <div className="prepub-list">{items.map(item=><article className="prepub-item" key={item.product_key}>
        <div className="prepub-head"><div><h2>{item.product.name||'Producto sin nombre'}</h2><p>SKU {item.product.sku||'—'} · Stock {item.product.stock??'—'}</p></div><span className={`prepub-source ${item.core_source}`}>{item.core_source_label}</span></div>
        <div className="prepub-core"><div><small>Marca validada</small><strong>{item.verified_core_data.brand||'—'}</strong></div><div><small>EAN / GTIN</small><strong>{item.verified_core_data.ean||'—'}</strong></div><div><small>Fuente</small>{item.verified_core_data.source_url?<a href={item.verified_core_data.source_url} target="_blank" rel="noreferrer">{item.verified_core_data.source_name||'Ver evidencia'}</a>:<strong>{item.verified_core_data.source_name||'Ecomm-App'}</strong>}</div></div>
        <div className="prepub-checks"><span className={item.checks.core_data}>{checkLabel(item.checks.core_data)}<small>Datos centrales</small></span><span className={item.checks.images}>{checkLabel(item.checks.images)}<small>Imágenes</small></span><span className={item.checks.category}>{checkLabel(item.checks.category)}<small>Categoría ML</small></span><span className={item.checks.attributes}>{checkLabel(item.checks.attributes)}<small>Atributos</small></span><span className={item.checks.preview}>{checkLabel(item.checks.preview)}<small>Preview</small></span></div>
      </article>)}</div>
      <p className="evidence-note">{report.policy.description}</p>
    </section>
  </>;
}
