import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {EnrichmentItem,EnrichmentNature,EnrichmentReport} from '../types/catalog';
import '../enrichment.css';

function csvCell(value:unknown){
  const text=String(value??'').replace(/"/g,'""');
  return `"${text}"`;
}

function matchesSearch(item:EnrichmentItem,term:string){
  if(!term)return true;
  return [item.product.sku,item.product.ean,item.product.brand,item.product.name,item.nature_label]
    .some(value=>String(value||'').toLowerCase().includes(term));
}

export function Enrichment(){
  const [report,setReport]=useState<EnrichmentReport|null>(null);
  const [search,setSearch]=useState('');
  const [missing,setMissing]=useState('');
  const [nature,setNature]=useState<EnrichmentNature|''>('');
  const [message,setMessage]=useState('');

  useEffect(()=>{api.enrichmentPilot(20).then(setReport).catch(error=>setMessage(error.message))},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (report?.items||[]).filter(item=>{
      if(!matchesSearch(item,term))return false;
      if(missing==='EAN'&&!item.missing_fields.includes('EAN/GTIN'))return false;
      if(missing==='BRAND'&&!item.missing_fields.includes('Marca'))return false;
      if(missing==='BOTH'&&item.missing_fields.length!==2)return false;
      if(nature&&item.nature_code!==nature)return false;
      return true;
    });
  },[report,search,missing,nature]);

  if(message)return <><header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Clasificación y piloto</h1></div></header><div className="notice warning">{message}</div></>;
  if(!report)return <div className="auth-loading">Preparando clasificación de enriquecimiento…</div>;

  const s=report.summary;

  function exportPilot(){
    const rows=[
      ['SKU','Producto','EAN actual','Marca actual','Stock','Precio','Faltantes','Tipo detectado','Base de clasificación','Estrategia sugerida','Estado investigación','EAN propuesto','Marca propuesta','Fuente','URL fuente','Confianza','Observaciones'],
      ...report!.items.map(item=>[
        item.product.sku||'',
        item.product.name||'',
        item.product.ean||'',
        item.product.brand||'',
        item.product.stock??'',
        item.product.price??'',
        item.missing_fields.join(' | '),
        item.nature_label,
        item.nature_basis,
        item.research_strategy,
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
    link.download=`kiki-enriquecimiento-clasificado-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return <>
    <header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Clasificación antes de investigar</h1><p>Separa packs, graneles, artesanales, unidades envasadas y casos ambiguos antes de buscar EAN o marca.</p></div></header>
    <div className="notice warning"><strong>No modifica ningún sistema.</strong> La clasificación es conservadora y orienta la investigación; no reemplaza una fuente verificable ni confirma por sí sola que un producto tenga o no GTIN.</div>

    <section className="cards enrichment-cards">
      <article><span>Productos elegibles</span><strong>{s.total_eligible.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta EAN/GTIN</span><strong>{s.missing_ean.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta marca</span><strong>{s.missing_brand.toLocaleString('es-AR')}</strong></article>
      <article><span>Faltan ambos</span><strong>{s.missing_both.toLocaleString('es-AR')}</strong></article>
      <article><span>Piloto actual</span><strong>{s.pilot_size.toLocaleString('es-AR')}</strong><small>de {s.pilot_limit}</small></article>
    </section>

    <section className="panel">
      <h2>Tipos detectados en los {s.total_eligible.toLocaleString('es-AR')} elegibles</h2>
      <p className="classification-help">Hacé clic en un tipo para filtrar el piloto. Los conteos corresponden a todo el universo elegible, no solo a los 20 de la muestra.</p>
      <div className="nature-grid">{report.classification_summary.map(group=><button key={group.code} className={`nature-card ${nature===group.code?'active':''}`} onClick={()=>setNature(current=>current===group.code?'':group.code)}><span>{group.label}</span><strong>{group.count.toLocaleString('es-AR')}</strong><small>{group.strategy}</small></button>)}</div>
      {nature&&<button className="text-button" onClick={()=>setNature('')}>Limpiar filtro por tipo</button>}
    </section>

    <section className="panel enrichment-plan">
      <div><h2>Prueba controlada: {s.pilot_size} productos</h2><p>Seguimos priorizando faltantes de EAN + marca y mayor stock, pero ahora cada producto sale con una estrategia distinta según su naturaleza. Así evitamos copiar EAN unitarios a packs o inventar marca en productos genéricos.</p></div>
      <button onClick={exportPilot}>Exportar piloto clasificado CSV</button>
    </section>

    <section className="panel">
      <div className="filters enrichment-filters">
        <input placeholder="Buscar por SKU, producto, EAN, marca o tipo" value={search} onChange={event=>setSearch(event.target.value)}/>
        <select value={missing} onChange={event=>setMissing(event.target.value)}>
          <option value="">Todos los faltantes</option>
          <option value="EAN">Falta EAN/GTIN</option>
          <option value="BRAND">Falta marca</option>
          <option value="BOTH">Faltan ambos</option>
        </select>
        <select value={nature} onChange={event=>setNature(event.target.value as EnrichmentNature|'')}>
          <option value="">Todos los tipos</option>
          {report.classification_summary.map(group=><option value={group.code} key={group.code}>{group.label}</option>)}
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> del piloto</p>
      <div className="table-wrap"><table><thead><tr><th>SKU</th><th>Producto</th><th>Stock</th><th>Faltantes</th><th>Tipo detectado</th><th>Estrategia</th><th>Investigación</th></tr></thead><tbody>
        {items.map((item,index)=><tr key={`${item.product.sku||item.product.name||'item'}-${index}`}>
          <td className="mono">{item.product.sku||'—'}</td>
          <td>{item.product.name||'—'}</td>
          <td>{item.product.stock??'—'}</td>
          <td><div className="missing-tags">{item.missing_fields.map(field=><span key={field}>{field}</span>)}</div></td>
          <td><span className={`nature-badge ${item.nature_code}`}>{item.nature_label}</span><small className="nature-basis">{item.nature_basis}</small></td>
          <td className="strategy-cell">{item.research_strategy}</td>
          <td><span className="research-pending">Pendiente</span></td>
        </tr>)}
      </tbody></table></div>
    </section>

    <section className="panel"><h2>Cómo usar esta clasificación</h2><p><strong>Unidad envasada:</strong> buscar fabricante, marca y GTIN exacto. <strong>Pack / kit / combo:</strong> investigar componentes y presentación, sin reutilizar automáticamente el EAN de una unidad. <strong>Granel o artesanal:</strong> validar proveedor y si corresponde una excepción de GTIN. <strong>Genérico / ambiguo:</strong> pedir etiqueta o ficha antes de proponer datos.</p></section>
  </>;
}
