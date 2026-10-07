import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {MetadataReviewStatus,PrepublicationMetadataItem,PrepublicationMetadataQueue} from '../types/catalog';
import '../metadata-review.css';

const statusLabels:Record<MetadataReviewStatus,string>={
  DRAFT:'Sin analizar',
  READY_FOR_REVIEW:'Lista para revisar',
  APPROVED:'Categoría aprobada',
  REJECTED:'Descartada',
};

export function MetadataReview(){
  const [queue,setQueue]=useState<PrepublicationMetadataQueue|null>(null);
  const [search,setSearch]=useState('');
  const [status,setStatus]=useState('');
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState('');
  const [categories,setCategories]=useState<Record<string,string>>({});
  const [notes,setNotes]=useState<Record<string,string>>({});
  const [itemFeedback,setItemFeedback]=useState<Record<string,{kind:'success'|'error';text:string}>>({});

  async function load(){
    try{
      const data=await api.prepublicationMetadata();
      setQueue(data);
      setError('');
    }catch(err){
      setError(err instanceof Error?err.message:'No se pudo cargar categoría y atributos.');
    }
  }

  useEffect(()=>{load()},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (queue?.items||[]).filter(item=>{
      if(status&&item.metadata_status!==status)return false;
      if(!term)return true;
      return [
        item.product.sku,
        item.product.name,
        item.verified_core_data.brand,
        item.verified_core_data.ean,
        item.category_name,
        item.domain_name,
      ].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[queue,search,status]);

  function selectedCategory(item:PrepublicationMetadataItem){
    return categories[item.product_key]||item.category_id||item.candidates[0]?.category_id||'';
  }

  function noteFor(item:PrepublicationMetadataItem){
    return notes[item.product_key]??item.notes??'';
  }

  async function analyze(productKey:string){
    setBusy(productKey);setMessage('');setError('');
    try{
      await api.analyzePrepublicationMetadata(productKey);
      setMessage('Mercado Libre devolvió categorías candidatas y atributos.');
      await load();
    }catch(err){setError(err instanceof Error?err.message:'No se pudo analizar el producto.')}
    finally{setBusy('')}
  }

  async function analyzePending(){
    setBusy('batch');setMessage('');setError('');
    try{
      const result=await api.analyzePendingMetadata(10);
      setMessage(result.errors.length?'Analizados '+result.analyzed+'. '+result.errors.length+' casos necesitan reintento.':'Analizados '+result.analyzed+' productos.');
      await load();
    }catch(err){setError(err instanceof Error?err.message:'No se pudo analizar el lote.')}
    finally{setBusy('')}
  }

  async function validateConditional(item:PrepublicationMetadataItem){
    const busyKey='conditional:'+item.product_key;
    setBusy(busyKey);setMessage('');setError('');
    setItemFeedback(current=>({...current,[item.product_key]:{kind:'success',text:'Consultando a Mercado Libre…'}}));
    try{
      const result=await api.validateConditionalMetadata(item.product_key);
      const text=result.conditional_validation_status==='VALIDATED'&&result.conditional_pending.length===0
        ? (result.conditional_required.length?'Mercado Libre validó los atributos condicionales y los requeridos ya están cubiertos.':'Mercado Libre validó los atributos condicionales: no exige datos adicionales para este borrador.')
        : 'Mercado Libre validó las condiciones. Quedan '+result.conditional_pending.length+' atributo(s) condicional(es) por completar.';
      setItemFeedback(current=>({...current,[item.product_key]:{kind:'success',text}}));
      await load();
    }catch(err){
      const text=err instanceof Error?err.message:'No se pudieron validar los atributos condicionales.';
      setItemFeedback(current=>({...current,[item.product_key]:{kind:'error',text}}));
    }finally{setBusy('')}
  }

  async function save(item:PrepublicationMetadataItem,next:MetadataReviewStatus){
    setBusy(item.product_key);setMessage('');setError('');
    try{
      await api.savePrepublicationMetadata({
        product_key:item.product_key,
        status:next,
        category_id:selectedCategory(item)||undefined,
        notes:noteFor(item)||undefined,
      });
      setMessage(next==='APPROVED'?'Categoría aprobada dentro de KIKI Tech. No se publicó nada.':'Decisión guardada.');
      await load();
    }catch(err){setError(err instanceof Error?err.message:'No se pudo guardar la decisión.')}
    finally{setBusy('')}
  }

  if(error&&!queue)return <><header><div><p className="eyebrow">MERCADO LIBRE · SOLO LECTURA</p><h1>Categoría y atributos</h1></div></header><div className="notice warning">{error}</div></>;
  if(!queue)return <div className="auth-loading">Preparando categoría y atributos…</div>;
  const s=queue.summary;

  return <>
    <header><div><p className="eyebrow">PRE-PUBLICACIÓN · METADATOS ML</p><h1>Categoría y atributos</h1><p>Mercado Libre propone la categoría y KIKI Tech muestra qué atributos exige antes de una futura publicación.</p></div></header>

    <div className="notice warning"><strong>No publica nada.</strong> El predictor de Mercado Libre genera propuestas. La categoría se confirma manualmente y los datos quedan guardados solo dentro de KIKI Tech.</div>
    {!queue.mercadolibre_connected&&<div className="notice warning">Mercado Libre no está conectado. Conectalo desde Resumen antes de analizar categorías.</div>}
    {message&&<div className="notice success">{message}</div>}
    {error&&<div className="notice warning">{error}</div>}

    <section className="cards metadata-cards">
      <article><span>Productos</span><strong>{s.total.toLocaleString('es-AR')}</strong></article>
      <article><span>Sin analizar</span><strong>{s.DRAFT.toLocaleString('es-AR')}</strong></article>
      <article><span>Para revisar</span><strong>{s.READY_FOR_REVIEW.toLocaleString('es-AR')}</strong></article>
      <article><span>Categorías aprobadas</span><strong>{s.APPROVED.toLocaleString('es-AR')}</strong></article>
      <article><span>Atributos completos</span><strong>{s.attributes_complete.toLocaleString('es-AR')}</strong></article>
      <article><span>Atributos pendientes</span><strong>{s.attributes_pending.toLocaleString('es-AR')}</strong></article>
    </section>

    <section className="panel metadata-intro">
      <div className="panel-title-row"><div><h2>Cómo funciona</h2><p>KIKI Tech envía el título al predictor oficial de Mercado Libre, trae hasta 3 categorías candidatas y consulta los atributos declarados para la categoría seleccionada.</p></div><button onClick={analyzePending} disabled={!queue.mercadolibre_connected||busy==='batch'}>{busy==='batch'?'Analizando…':'Analizar pendientes (10)'}</button></div>
      <details><summary><strong>¿Qué significa “atributo pendiente”?</strong></summary><p>Mercado Libre puede exigir datos específicos según la categoría. KIKI Tech completa automáticamente solo lo que ya tiene validado, por ejemplo Marca, EAN/GTIN o SKU. Cuando un atributo tiene la regla conditional_required, KIKI Tech consulta el validador oficial con el borrador del ítem para saber si realmente es obligatorio antes del preview.</p><p>Contexto provisional usado para validar: {queue.policy.conditional_validation_defaults.currency_id}, compra inmediata, condición nueva y tipo {queue.policy.conditional_validation_defaults.listing_type_id}. Esto no publica nada y se volverá a validar si el borrador final cambia.</p></details>
    </section>

    <section className="panel">
      <div className="filters metadata-filters">
        <input placeholder="Buscar SKU, producto, marca, EAN o categoría" value={search} onChange={e=>setSearch(e.target.value)}/>
        <select value={status} onChange={e=>setStatus(e.target.value)}>
          <option value="">Todos los estados</option>
          {Object.entries(statusLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> de {s.total.toLocaleString('es-AR')} productos</p>

      <div className="metadata-list">{items.map(item=>{
        const required=item.attributes.filter(attribute=>attribute.required);
        const conditional=item.attributes.filter(attribute=>attribute.conditional_required);
        const selected=selectedCategory(item);
        return <article className="metadata-item" key={item.product_key}>
          <div className="metadata-head"><div><h2>{item.product.name||'Producto sin nombre'}</h2><p>SKU {item.product.sku||'—'} · EAN {item.verified_core_data.ean||item.product.ean||'—'} · Stock {item.product.stock??'—'}</p></div><span className={'metadata-status '+item.metadata_status}>{statusLabels[item.metadata_status]}</span></div>

          {item.candidates.length===0?
            <div className="metadata-empty"><p>Todavía no se consultó el predictor de Mercado Libre para este producto.</p><button onClick={()=>analyze(item.product_key)} disabled={!queue.mercadolibre_connected||busy===item.product_key}>{busy===item.product_key?'Analizando…':'Analizar con Mercado Libre'}</button></div>
          :
            <>
              <div className="metadata-grid">
                <label>Categoría propuesta<select value={selected} onChange={e=>setCategories(current=>({...current,[item.product_key]:e.target.value}))}>{item.candidates.map(candidate=><option key={candidate.category_id} value={candidate.category_id}>{candidate.category_name} · {candidate.category_id}</option>)}</select></label>
                <div><small>Dominio</small><strong>{item.candidates.find(candidate=>candidate.category_id===selected)?.domain_name||item.domain_name||'—'}</strong></div>
                <div><small>Atributos obligatorios</small><strong>{required.length}</strong></div>
                <div><small>Obligatorios pendientes</small><strong>{item.required_missing.length}</strong></div>
              </div>

              <details className="attribute-details" open={item.metadata_status==='READY_FOR_REVIEW'}>
                <summary><strong>Ver atributos de la categoría</strong></summary>
                {required.length===0?<p>No aparecen atributos con tag obligatorio en la respuesta actual de esta categoría.</p>:<div className="attribute-list">{required.map(attribute=><div key={attribute.id} className={attribute.verified_value?'resolved':'missing'}><span>{attribute.name}<small>{attribute.id}</small></span><strong>{attribute.verified_value||'Falta completar'}</strong>{attribute.suggested_value&&!attribute.verified_value&&<em>Sugerencia ML: {attribute.suggested_value}</em>}</div>)}</div>}
                {conditional.length>0&&item.conditional_validation_status==='PENDING'&&<p className="conditional-note">{conditional.length} atributo(s) tienen obligatoriedad condicional. Aprobá la categoría y validalos con Mercado Libre antes del preview.</p>}
                {conditional.length>0&&item.conditional_validation_status==='VALIDATED'&&<p className="conditional-note">{item.conditional_required.length===0?'Validación condicional completa: Mercado Libre no exige atributos adicionales para este borrador.':'Mercado Libre exige '+item.conditional_required.map(attribute=>attribute.name||attribute.id).join(', ')+(item.conditional_pending.length?' · faltan '+item.conditional_pending.length+' por completar.':' · todos ya están cubiertos con datos validados.')}</p>}
              </details>

              <label className="metadata-note">Nota opcional<textarea value={noteFor(item)} onChange={e=>setNotes(current=>({...current,[item.product_key]:e.target.value}))} placeholder="Por qué confirmás o descartás esta categoría"/></label>

              <div className="metadata-actions">
                <button onClick={()=>save(item,'APPROVED')} disabled={busy===item.product_key}>{busy===item.product_key?'Guardando…':'Aprobar categoría'}</button>
                {item.metadata_status==='APPROVED'&&conditional.length>0&&<button className="secondary" onClick={()=>validateConditional(item)} disabled={busy==='conditional:'+item.product_key}>{busy==='conditional:'+item.product_key?'Validando…':item.conditional_validation_status==='VALIDATED'?'Revalidar condicionales':'Validar atributos condicionales'}</button>}
                <button className="secondary" onClick={()=>analyze(item.product_key)} disabled={busy===item.product_key}>Volver a analizar</button>
                <button className="danger-outline" onClick={()=>save(item,'REJECTED')} disabled={busy===item.product_key}>Descartar propuesta</button>
              </div>
              {itemFeedback[item.product_key]&&<p className={itemFeedback[item.product_key].kind==='error'?'metadata-result pending':'metadata-result complete'}><strong>{itemFeedback[item.product_key].kind==='error'?'No se pudo validar: ':'Resultado: '}</strong>{itemFeedback[item.product_key].text}</p>}
              {item.metadata_status==='APPROVED'&&<p className={(item.required_missing.length||item.conditional_pending.length||item.conditional_validation_status==='PENDING')?'metadata-result pending':'metadata-result complete'}>{item.required_missing.length?'Categoría aprobada. Todavía faltan '+item.required_missing.length+' atributo(s) obligatorio(s).':item.conditional_validation_status==='PENDING'?'Categoría aprobada. Falta consultar a Mercado Libre cuáles atributos condicionales aplican a este borrador.':item.conditional_pending.length?'Mercado Libre confirmó '+item.conditional_pending.length+' atributo(s) condicional(es) obligatorios que todavía faltan completar.':'Categoría aprobada y atributos obligatorios validados para avanzar al preview.'}</p>}
            </>
          }
        </article>;
      })}</div>
      <p className="evidence-note">{queue.policy.description} {queue.policy.conditional_attributes}</p>
    </section>
  </>;
}
