import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {EnrichmentItem,EnrichmentReport} from '../types/catalog';
import '../enrichment.css';

function csvCell(value:unknown){
  const text=String(value??'').replace(/"/g,'""');
  return `"${text}"`;
}

function matchesSearch(item:EnrichmentItem,term:string){
  if(!term)return true;
  return [item.product.sku,item.product.ean,item.product.brand,item.product.name]
    .some(value=>String(value||'').toLowerCase().includes(term));
}

export function Enrichment(){
  const [report,setReport]=useState<EnrichmentReport|null>(null);
  const [search,setSearch]=useState('');
  const [missing,setMissing]=useState('');
  const [message,setMessage]=useState('');

  useEffect(()=>{api.enrichmentPilot(20).then(setReport).catch(error=>setMessage(error.message))},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (report?.items||[]).filter(item=>{
      if(!matchesSearch(item,term))return false;
      if(missing==='EAN'&&!item.missing_fields.includes('EAN/GTIN'))return false;
      if(missing==='BRAND'&&!item.missing_fields.includes('Marca'))return false;
      if(missing==='BOTH'&&item.missing_fields.length!==2)return false;
      return true;
    });
  },[report,search,missing]);

  if(message)return <><header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Piloto EAN y marca</h1></div></header><div className="notice warning">{message}</div></>;
  if(!report)return <div className="auth-loading">Preparando piloto de enriquecimiento…</div>;

  const s=report.summary;

  function exportPilot(){
    const rows=[
      ['SKU','Producto','EAN actual','Marca actual','Stock','Precio','Faltantes','Estado investigación','EAN propuesto','Marca propuesta','Fuente','URL fuente','Confianza','Observaciones'],
      ...report!.items.map(item=>[
        item.product.sku||'',
        item.product.name||'',
        item.product.ean||'',
        item.product.brand||'',
        item.product.stock??'',
        item.product.price??'',
        item.missing_fields.join(' | '),
        'Pendiente',
        '',
        '',
        '',
        '',
        '',
        '',
      ]),
    ];
    const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=`kiki-enriquecimiento-piloto-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return <>
    <header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Piloto EAN y marca</h1><p>Primera muestra controlada de productos con stock que necesitan completar datos antes de avanzar.</p></div></header>
    <div className="notice warning"><strong>No modifica ningún sistema.</strong> Esta etapa solo arma una cola de investigación. Los datos propuestos deberán tener una fuente verificable antes de aprobarse.</div>

    <section className="cards enrichment-cards">
      <article><span>Productos elegibles</span><strong>{s.total_eligible.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta EAN/GTIN</span><strong>{s.missing_ean.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta marca</span><strong>{s.missing_brand.toLocaleString('es-AR')}</strong></article>
      <article><span>Faltan ambos</span><strong>{s.missing_both.toLocaleString('es-AR')}</strong></article>
      <article><span>Piloto actual</span><strong>{s.pilot_size.toLocaleString('es-AR')}</strong><small>de {s.pilot_limit}</small></article>
    </section>

    <section className="panel enrichment-plan">
      <div><h2>Prueba controlada: {s.pilot_size} productos</h2><p>Se priorizan productos a los que les faltan EAN y marca al mismo tiempo y, dentro de cada grupo, los de mayor stock. Así investigamos primero los casos con mayor impacto operativo.</p></div>
      <button onClick={exportPilot}>Exportar piloto CSV</button>
    </section>

    <section className="panel">
      <div className="filters">
        <input placeholder="Buscar por SKU, producto, EAN o marca" value={search} onChange={event=>setSearch(event.target.value)}/>
        <select value={missing} onChange={event=>setMissing(event.target.value)}>
          <option value="">Todos los faltantes</option>
          <option value="EAN">Falta EAN/GTIN</option>
          <option value="BRAND">Falta marca</option>
          <option value="BOTH">Faltan ambos</option>
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> del piloto</p>
      <div className="table-wrap"><table><thead><tr><th>SKU</th><th>Producto</th><th>EAN actual</th><th>Marca actual</th><th>Stock</th><th>Precio</th><th>Faltantes</th><th>Investigación</th></tr></thead><tbody>
        {items.map((item,index)=><tr key={`${item.product.sku||item.product.name||'item'}-${index}`}>
          <td className="mono">{item.product.sku||'—'}</td>
          <td>{item.product.name||'—'}</td>
          <td className="mono">{item.product.ean||'—'}</td>
          <td>{item.product.brand||'—'}</td>
          <td>{item.product.stock??'—'}</td>
          <td>{item.product.price!==undefined&&item.product.price!==null?Number(item.product.price).toLocaleString('es-AR',{style:'currency',currency:'ARS'}):'—'}</td>
          <td><div className="missing-tags">{item.missing_fields.map(field=><span key={field}>{field}</span>)}</div></td>
          <td><span className="research-pending">Pendiente</span></td>
        </tr>)}
      </tbody></table></div>
    </section>

    <section className="panel"><h2>Qué hacemos con este CSV</h2><p>Investigamos los 20 productos en fuentes confiables, completamos EAN/GTIN y/o marca propuestos junto con la fuente, URL y nivel de confianza. Después incorporaremos esas propuestas a KIKI Tech para revisarlas antes de cualquier cambio externo.</p></section>
  </>;
}
