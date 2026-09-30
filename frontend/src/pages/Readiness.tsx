import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {ReadinessReport,ReadinessStatus} from '../types/catalog';

const labels:Record<ReadinessStatus,string>={
  READY_CORE_DATA:'Datos centrales OK',
  REVIEW_REQUIRED:'Revisar',
  BLOCKED:'Bloqueado',
  NO_STOCK:'Sin stock',
  ALREADY_PUBLISHED:'Ya publicado',
};

export function Readiness(){
  const [report,setReport]=useState<ReadinessReport|null>(null);
  const [status,setStatus]=useState('');
  const [search,setSearch]=useState('');
  const [message,setMessage]=useState('');
  useEffect(()=>{api.publicationReadiness().then(setReport).catch(error=>setMessage(error.message))},[]);
  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (report?.items||[]).filter(item=>{
      if(status&&item.readiness_status!==status)return false;
      if(!term)return true;
      return [item.product.sku,item.product.ean,item.product.name].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[report,status,search]);
  if(message)return <><header><div><p className="eyebrow">PREPARACIÓN MERCADO LIBRE</p><h1>Validador de publicación</h1></div></header><div className="notice warning">{message}</div></>;
  if(!report)return <div className="auth-loading">Preparando validación…</div>;
  const s=report.summary;
  return <><header><div><p className="eyebrow">PREPARACIÓN MERCADO LIBRE</p><h1>Validador de publicación</h1><p>Clasifica el catálogo antes de cualquier futura escritura en Mercado Libre.</p></div></header>
  <div className="notice warning"><strong>No publica nada.</strong> “Datos centrales OK” significa que Ecomm y la conciliación no muestran bloqueos conocidos. Todavía faltan validar imágenes, categoría y atributos de Mercado Libre.</div>
  <section className="cards readiness-cards"><article><span>Datos centrales OK</span><strong>{s.READY_CORE_DATA.toLocaleString('es-AR')}</strong></article><article><span>Requieren revisión</span><strong>{s.REVIEW_REQUIRED.toLocaleString('es-AR')}</strong></article><article><span>Bloqueados</span><strong>{s.BLOCKED.toLocaleString('es-AR')}</strong></article><article><span>Sin stock</span><strong>{s.NO_STOCK.toLocaleString('es-AR')}</strong></article><article><span>Ya publicados</span><strong>{s.ALREADY_PUBLISHED.toLocaleString('es-AR')}</strong></article></section>
  <section className="panel"><h2>Controles que todavía faltan</h2><p>{report.pending_external_checks.join(' · ')}</p></section>
  <section className="panel"><div className="filters"><input placeholder="Buscar por SKU, EAN o producto" value={search} onChange={event=>setSearch(event.target.value)}/><select value={status} onChange={event=>setStatus(event.target.value)}><option value="">Todos los estados</option>{Object.entries(labels).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></div><p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> productos</p><div className="table-wrap"><table><thead><tr><th>SKU</th><th>Producto</th><th>EAN</th><th>Stock</th><th>Precio</th><th>Preparación</th><th>Motivo</th></tr></thead><tbody>{items.map((item,index)=><tr key={`${item.product.sku||item.product.ean||'item'}-${index}`}><td className="mono">{item.product.sku||'—'}</td><td>{item.product.name||'—'}</td><td className="mono">{item.product.ean||'—'}</td><td>{item.product.stock??'—'}</td><td>{item.product.price!==undefined&&item.product.price!==null?Number(item.product.price).toLocaleString('es-AR',{style:'currency',currency:'ARS'}):'—'}</td><td><span className={`badge ${item.readiness_status}`}>{labels[item.readiness_status]}</span></td><td>{item.reasons.join(' ')||'—'}</td></tr>)}</tbody></table></div></section></>;
}
