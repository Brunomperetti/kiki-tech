import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {EnrichmentItem,EnrichmentNature,EnrichmentReport,InternalEvidenceConfidence} from '../types/catalog';
import '../enrichment.css';

function csvCell(value:unknown){
  const text=String(value??'').replace(/"/g,'""');
  return `"${text}"`;
}

function matchesSearch(item:EnrichmentItem,term:string){
  if(!term)return true;
  return [
    item.product.sku,
    item.product.ean,
    item.product.brand,
    item.product.name,
    item.nature_label,
    item.internal_evidence.brand_candidate,
    item.internal_evidence.related_name,
  ].some(value=>String(value||'').toLowerCase().includes(term));
}

function evidenceLabel(confidence:InternalEvidenceConfidence){
  if(confidence==='HIGH')return 'Alta';
  if(confidence==='MEDIUM')return 'Media';
  return 'Sin evidencia fuerte';
}

export function Enrichment(){
  const [report,setReport]=useState<EnrichmentReport|null>(null);
  const [search,setSearch]=useState('');
  const [missing,setMissing]=useState('');
  const [nature,setNature]=useState<EnrichmentNature|''>('');
  const [evidence,setEvidence]=useState('');
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
      if(evidence==='CANDIDATE'&&!item.internal_evidence.brand_candidate)return false;
      if(evidence==='HIGH'&&item.internal_evidence.confidence!=='HIGH')return false;
      if(evidence==='MEDIUM'&&item.internal_evidence.confidence!=='MEDIUM')return false;
      if(evidence==='AMBIGUOUS'&&(item.internal_evidence.brand_candidate||item.internal_evidence.candidate_brands.length<2))return false;
      if(evidence==='NONE'&&(item.internal_evidence.brand_candidate||item.internal_evidence.candidate_brands.length>0))return false;
      return true;
    });
  },[report,search,missing,nature,evidence]);

  if(message)return <><header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Clasificación y evidencia interna</h1></div></header><div className="notice warning">{message}</div></>;
  if(!report)return <div className="auth-loading">Preparando clasificación y evidencia interna…</div>;

  const s=report.summary;
  const internal=report.internal_evidence_summary;

  function exportPilot(){
    const rows=[
      ['SKU','Producto','EAN actual','Marca actual','Stock','Precio','Faltantes','Tipo detectado','Base de clasificación','Estrategia sugerida','Marca candidata interna','Confianza evidencia interna','Método evidencia interna','Razón evidencia interna','SKU relacionado','Producto relacionado','EAN relacionado - referencia','Estado investigación','EAN propuesto','Marca propuesta','Fuente','URL fuente','Confianza','Observaciones'],
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
        item.internal_evidence.brand_candidate||'',
        evidenceLabel(item.internal_evidence.confidence),
        item.internal_evidence.method,
        item.internal_evidence.reason,
        item.internal_evidence.related_sku||'',
        item.internal_evidence.related_name||'',
        item.internal_evidence.related_ean||'',
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
    link.download=`kiki-enriquecimiento-evidencia-interna-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return <>
    <header><div><p className="eyebrow">ENRIQUECIMIENTO DE CATÁLOGO</p><h1>Clasificación + evidencia interna</h1><p>Usa lo que KIKI ya sabe de su propio catálogo para orientar la investigación sin completar datos automáticamente.</p></div></header>
    <div className="notice warning"><strong>No modifica ningún sistema.</strong> Una marca candidata o un EAN relacionado son solo pistas internas. Antes de aprobar un dato seguimos exigiendo una fuente verificable de la presentación exacta.</div>

    <section className="cards enrichment-cards">
      <article><span>Productos elegibles</span><strong>{s.total_eligible.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta EAN/GTIN</span><strong>{s.missing_ean.toLocaleString('es-AR')}</strong></article>
      <article><span>Falta marca</span><strong>{s.missing_brand.toLocaleString('es-AR')}</strong></article>
      <article><span>Faltan ambos</span><strong>{s.missing_both.toLocaleString('es-AR')}</strong></article>
      <article><span>Piloto actual</span><strong>{s.pilot_size.toLocaleString('es-AR')}</strong><small>de {s.pilot_limit}</small></article>
    </section>

    <section className="panel">
      <h2>Evidencia del propio catálogo</h2>
      <p className="classification-help">KIKI Tech compara cada faltante con productos y marcas que ya están identificados. No copia esos datos: los usa para decidir qué conviene investigar primero.</p>
      <div className="evidence-grid">
        <article><span>Marcas conocidas</span><strong>{s.known_brands_in_catalog.toLocaleString('es-AR')}</strong><small>marcas ya presentes en otros productos</small></article>
        <article><span>Marca candidata interna</span><strong>{s.internal_brand_candidates.toLocaleString('es-AR')}</strong><small>casos con una pista única suficientemente fuerte</small></article>
        <article><span>Evidencia alta</span><strong>{internal.high.toLocaleString('es-AR')}</strong><small>marca presente en título o similitud muy fuerte</small></article>
        <article><span>Evidencia media</span><strong>{internal.medium.toLocaleString('es-AR')}</strong><small>producto interno parecido; necesita validación</small></article>
        <article><span>Internamente ambiguos</span><strong>{s.internal_evidence_ambiguous.toLocaleString('es-AR')}</strong><small>más de una marca posible: no se elige ninguna</small></article>
      </div>
      <p className="evidence-note">{internal.description}</p>
    </section>

    <section className="panel">
      <h2>Tipos detectados en los {s.total_eligible.toLocaleString('es-AR')} elegibles</h2>
      <p className="classification-help">La naturaleza del producto sigue siendo independiente de la marca candidata. Un pack continúa siendo pack aunque encontremos una marca relacionada.</p>
      <div className="nature-grid">{report.classification_summary.map(group=><button key={group.code} className={`nature-card ${nature===group.code?'active':''}`} onClick={()=>setNature(current=>current===group.code?'':group.code)}><span>{group.label}</span><strong>{group.count.toLocaleString('es-AR')}</strong><small>{group.strategy}</small></button>)}</div>
      {nature&&<button className="text-button" onClick={()=>setNature('')}>Limpiar filtro por tipo</button>}
    </section>

    <section className="panel enrichment-plan">
      <div><h2>Prueba controlada: {s.pilot_size} productos</h2><p>Ahora el piloto combina naturaleza + evidencia interna. Una coincidencia interna sirve para priorizar la búsqueda externa, pero nunca se convierte sola en una propuesta aprobada.</p></div>
      <button onClick={exportPilot}>Exportar piloto con evidencia</button>
    </section>

    <section className="panel">
      <div className="filters enrichment-filters evidence-filters">
        <input placeholder="Buscar por SKU, producto, marca candidata o relacionado" value={search} onChange={event=>setSearch(event.target.value)}/>
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
        <select value={evidence} onChange={event=>setEvidence(event.target.value)}>
          <option value="">Toda evidencia interna</option>
          <option value="CANDIDATE">Con marca candidata</option>
          <option value="HIGH">Confianza alta</option>
          <option value="MEDIUM">Confianza media</option>
          <option value="AMBIGUOUS">Varias marcas posibles</option>
          <option value="NONE">Sin evidencia interna</option>
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> del piloto</p>
      <div className="table-wrap"><table><thead><tr><th>SKU</th><th>Producto</th><th>Stock</th><th>Tipo detectado</th><th>Evidencia interna</th><th>Estrategia</th><th>Investigación</th></tr></thead><tbody>
        {items.map((item,index)=>{
          const ev=item.internal_evidence;
          return <tr key={`${item.product.sku||item.product.name||'item'}-${index}`}>
            <td className="mono">{item.product.sku||'—'}</td>
            <td>{item.product.name||'—'}<div className="missing-tags compact">{item.missing_fields.map(field=><span key={field}>{field}</span>)}</div></td>
            <td>{item.product.stock??'—'}</td>
            <td><span className={`nature-badge ${item.nature_code}`}>{item.nature_label}</span><small className="nature-basis">{item.nature_basis}</small></td>
            <td className="evidence-cell">
              {ev.brand_candidate?<><strong className="evidence-candidate">{ev.brand_candidate}</strong><span className={`evidence-badge ${ev.confidence.toLowerCase()}`}>{evidenceLabel(ev.confidence)}</span></>:ev.candidate_brands.length>1?<><strong>Varias posibles</strong><span className="evidence-badge ambiguous">Revisar</span></>:<span className="evidence-none">Sin evidencia fuerte</span>}
              <small className="evidence-detail">{ev.reason}</small>
              {ev.related_name&&<small className="evidence-related">Relacionado: {ev.related_sku?`${ev.related_sku} · `:''}{ev.related_name}{ev.related_ean?` · EAN ref. ${ev.related_ean}`:''}</small>}
            </td>
            <td className="strategy-cell">{item.research_strategy}</td>
            <td><span className="research-pending">Pendiente</span></td>
          </tr>;
        })}
      </tbody></table></div>
    </section>

    <section className="panel"><h2>Regla de seguridad</h2><p><strong>La evidencia interna no completa campos.</strong> Si KIKI Tech encuentra una marca probable por título o por un producto parecido, la muestra como candidata. El EAN de un producto relacionado se muestra únicamente como referencia y nunca se copia automáticamente, especialmente en packs, variantes o presentaciones distintas.</p></section>
  </>;
}
