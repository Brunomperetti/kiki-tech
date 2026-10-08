import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {InventoryLinkageReport,InventoryLinkageStatus,ReadinessItem,ReadinessReport,ReadinessStatus} from '../types/catalog';
import '../readiness.css';

const linkageLabels:Record<InventoryLinkageStatus,string>={
  READY_TO_LINK:'Lista para vincular',
  REVIEW_AMBIGUOUS:'Revisar GTIN ambiguo',
  REVIEW_MULTIPLE_GTIN:'Revisar múltiples GTIN',
  REVIEW_IDENTIFIER_CONFLICT:'Revisar conflicto MLA/GTIN',
  REVIEW_TITLE_CANDIDATE:'Revisar candidato por título',
  INVALID_GTIN:'GTIN inválido',
  NO_ECOMM_MATCH:'Sin coincidencia Ecomm',
};

const labels:Record<ReadinessStatus,string>={
  READY_CORE_DATA:'Datos centrales OK',
  REVIEW_REQUIRED:'Revisar',
  BLOCKED:'Bloqueado',
  EXCLUDED_BULK:'Fuera del masivo actual',
  NO_STOCK:'Sin stock',
  ALREADY_PUBLISHED:'Ya publicado',
};

function matchesSearch(item:ReadinessItem,term:string){
  if(!term)return true;
  return [item.product.sku,item.product.ean,item.product.name].some(value=>String(value||'').toLowerCase().includes(term));
}

function csvCell(value:unknown){
  const text=String(value??'').replace(/"/g,'""');
  return `"${text}"`;
}

export function Readiness(){
  const [report,setReport]=useState<ReadinessReport|null>(null);
  const [linkage,setLinkage]=useState<InventoryLinkageReport|null>(null);
  const [status,setStatus]=useState('');
  const [reasonCode,setReasonCode]=useState('');
  const [search,setSearch]=useState('');
  const [message,setMessage]=useState('');
  useEffect(()=>{
    api.publicationReadiness().then(setReport).catch(error=>setMessage(error.message));
    api.inventoryLinkage().then(setLinkage).catch(()=>setLinkage(null));
  },[]);
  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (report?.items||[]).filter(item=>{
      if(status&&item.readiness_status!==status)return false;
      if(reasonCode&&!item.reason_codes.includes(reasonCode))return false;
      return matchesSearch(item,term);
    });
  },[report,status,reasonCode,search]);
  if(message)return <><header><div><p className="eyebrow">PREPARACIÓN MERCADO LIBRE</p><h1>Validador de publicación</h1></div></header><div className="notice warning">{message}</div></>;
  if(!report)return <div className="auth-loading">Preparando validación…</div>;
  const s=report.summary;

  function selectReason(code:string){
    setReasonCode(current=>current===code?'':code);
    setStatus('');
  }

  function exportReview(){
    const term=search.trim().toLowerCase();
    const exportItems=report!.items.filter(item=>{
      if(!['REVIEW_REQUIRED','BLOCKED'].includes(item.readiness_status))return false;
      if(reasonCode&&!item.reason_codes.includes(reasonCode))return false;
      return matchesSearch(item,term);
    });
    const rows=[
      ['SKU','Producto','EAN/GTIN','Stock','Precio','Estado','Códigos','Motivos'],
      ...exportItems.map(item=>[
        item.product.sku||'',
        item.product.name||'',
        item.product.ean||'',
        item.product.stock??'',
        item.product.price??'',
        labels[item.readiness_status],
        item.reason_codes.join(' | '),
        item.reasons.join(' | '),
      ]),
    ];
    const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(';')).join('\r\n');
    const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download=`kiki-revision-ml-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return <><header><div><p className="eyebrow">PREPARACIÓN MERCADO LIBRE</p><h1>Validador de publicación</h1><p>Clasifica el catálogo antes de cualquier futura escritura en Mercado Libre.</p></div></header>
  <div className="notice warning"><strong>No publica nada.</strong> Esta etapa ordena los productos según qué tan preparados están para avanzar. “Datos centrales OK” todavía no significa “listo para publicar”.</div>
  <section className="cards readiness-cards"><article><span>Datos centrales OK</span><strong>{s.READY_CORE_DATA.toLocaleString('es-AR')}</strong></article><article><span>Requieren revisión</span><strong>{s.REVIEW_REQUIRED.toLocaleString('es-AR')}</strong></article><article><span>Bloqueados</span><strong>{s.BLOCKED.toLocaleString('es-AR')}</strong></article><article><span>Fuera del masivo actual</span><strong>{s.EXCLUDED_BULK.toLocaleString('es-AR')}</strong></article><article><span>Sin stock</span><strong>{s.NO_STOCK.toLocaleString('es-AR')}</strong></article><article><span>Ya publicados</span><strong>{s.ALREADY_PUBLISHED.toLocaleString('es-AR')}</strong></article></section>
  <section className="panel"><div className="panel-title-row"><div><h2>Vinculación de inventario EDIMA</h2><p>Cruza las publicaciones de Mercado Libre con el catálogo de Ecomm-App usando el MLA exacto y el GTIN como evidencia.</p></div></div>
    {!linkage?<p>Consultando el último reporte EDIMA…</p>:!linkage.available?<div className="notice"><strong>EDIMA todavía no está cargado.</strong><p>{linkage.message}</p><p>Subilo desde <strong>Importaciones → EDIMA · Vinculación inventario ML</strong>.</p></div>:<>
      <section className="cards readiness-cards"><article><span>Publicaciones EDIMA</span><strong>{linkage.summary.total_publications.toLocaleString('es-AR')}</strong></article><article><span>Vinculadas</span><strong>{linkage.summary.linked.toLocaleString('es-AR')}</strong></article><article><span>Sin vincular</span><strong>{linkage.summary.unlinked.toLocaleString('es-AR')}</strong></article><article><span>Listas para vincular</span><strong>{linkage.summary.ready_to_link.toLocaleString('es-AR')}</strong></article><article><span>Requieren revisión</span><strong>{linkage.summary.review_required.toLocaleString('es-AR')}</strong></article><article><span>GTIN únicos sin vincular</span><strong>{linkage.summary.distinct_unlinked_gtins.toLocaleString('es-AR')}</strong></article></section>
      <p className="evidence-note">{linkage.policy.safe_match}</p>
      <p className="result-count">Calidad del reporte: <strong>{linkage.summary.data_quality_invalid_gtin_total.toLocaleString('es-AR')}</strong> publicaciones con GTIN inválido o no utilizable · <strong>{linkage.summary.data_quality_multiple_gtin_total.toLocaleString('es-AR')}</strong> con más de un código · <strong>{linkage.summary.title_candidates.toLocaleString('es-AR')}</strong> con candidato sugerido por título.</p>
      <div className="table-wrap"><table><thead><tr><th>Publicación ML</th><th>Producto</th><th>GTIN EDIMA</th><th>Producto Ecomm</th><th>SKU Ecomm</th><th>Método</th><th>Estado</th><th>Motivo</th></tr></thead><tbody>{linkage.items.map((item,index)=><tr key={item.external_id||index}><td className="mono">{item.external_id||'—'}</td><td>{item.title||'—'}</td><td className="mono">{item.gtin_raw||'—'}</td><td>{item.matched_product?.name||'—'}</td><td className="mono">{item.matched_product?.sku||'—'}</td><td>{item.match_method==='RECONCILIATION_MLA'?'MLA conciliado':item.match_method==='ECOMM_MLA'?'MLA en Ecomm':item.match_method==='GTIN_EXACT'?'GTIN exacto':item.match_method==='TITLE_EXACT'?'Título exacto':item.match_method==='TITLE_HIGH_CONFIDENCE'?'Título sugerido':item.match_method||'—'}</td><td><span className={`badge ${item.status==='READY_TO_LINK'?'READY_CORE_DATA':'REVIEW_REQUIRED'}`}>{linkageLabels[item.status]}</span></td><td>{item.reason}</td></tr>)}</tbody></table></div>
      <p className="evidence-note">{linkage.policy.description}</p>
    </>}
  </section>
  <details className="notice"><summary><strong>¿Cómo leer estos estados?</strong></summary><p>“Ya publicados” salen del flujo de alta. “Sin stock” se apartan temporalmente y no se priorizan mientras no tengan unidades disponibles. “Fuera del masivo actual” son productos que no están necesariamente mal: una regla comercial vigente indica que ciertos SKU asociados o combos no se incluyen todavía en el alta masiva. “Requieren revisión” y “Bloqueados” necesitan una corrección o una decisión. “Datos centrales OK” son candidatos con stock informado y positivo, marca y EAN/GTIN presentes y sin bloqueos conocidos de conciliación. No significa que deban tener a la vez SKU de variante y SKU de producto, ni que ya estén listos para Mercado Libre: después todavía deben validar imágenes, categoría, atributos, preview y confirmación humana.</p></details>
  <details className="notice"><summary><strong>Regla SKU del masivo actual</strong></summary><p>{report.bulk_policy.description}</p><p>En simple: si un EAN tiene un único SKU base numérico de 4 dígitos, los SKU numéricos de 5 o más dígitos asociados a ese mismo EAN se consideran combos/asociados y quedan fuera del masivo por ahora. Si el EAN no tiene un único SKU base de 4 dígitos, KIKI Tech lo manda a revisión en vez de decidir solo.</p></details>
  <section className="panel"><div className="panel-title-row"><div><h2>Motivos que requieren atención</h2><p>Hacé clic en un motivo para ver únicamente los productos afectados.</p></div><button onClick={exportReview}>Exportar revisión CSV</button></div><div className="reason-grid">{report.reason_summary.map(reason=><button key={reason.code} className={`reason-card ${reasonCode===reason.code?'active':''}`} onClick={()=>selectReason(reason.code)}><span>{reason.label}</span><strong>{reason.count.toLocaleString('es-AR')}</strong></button>)}</div>{reasonCode&&<button className="text-button" onClick={()=>setReasonCode('')}>Limpiar filtro por motivo</button>}</section>
  <section className="panel"><h2>Controles que todavía faltan</h2><p>{report.pending_external_checks.join(' · ')}</p></section>
  <section className="panel"><div className="filters"><input placeholder="Buscar por SKU, EAN o producto" value={search} onChange={event=>setSearch(event.target.value)}/><select value={status} onChange={event=>setStatus(event.target.value)}><option value="">Todos los estados</option>{Object.entries(labels).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></div><p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> productos{reasonCode?' para el motivo seleccionado':''}</p><div className="table-wrap"><table><thead><tr><th>SKU</th><th>Producto</th><th>EAN</th><th>Stock</th><th>Precio</th><th>Preparación</th><th>Motivo</th></tr></thead><tbody>{items.map((item,index)=><tr key={`${item.product.sku||item.product.ean||'item'}-${index}`}><td className="mono">{item.product.sku||'—'}</td><td>{item.product.name||'—'}</td><td className="mono">{item.product.ean||'—'}</td><td>{item.product.stock??'—'}</td><td>{item.product.price!==undefined&&item.product.price!==null?Number(item.product.price).toLocaleString('es-AR',{style:'currency',currency:'ARS'}):'—'}</td><td><span className={`badge ${item.readiness_status}`}>{labels[item.readiness_status]}</span></td><td>{item.reasons.join(' ')||'—'}</td></tr>)}</tbody></table></div></section></>;
}
