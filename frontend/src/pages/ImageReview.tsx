import {useEffect,useMemo,useState} from 'react';
import {api} from '../services/api';
import type {ImageMatchBasis,ImageReviewStatus,ImageSourceType,PrepublicationImageItem,PrepublicationImagePayload,PrepublicationImageQueue} from '../types/catalog';
import '../image-review.css';

type Draft={
  source_type:ImageSourceType|'';
  source_name:string;
  source_url:string;
  image_urls:string;
  match_basis:ImageMatchBasis|'';
  exact_match:boolean;
  authorized_for_use:boolean;
  notes:string;
};

function draftFrom(item:PrepublicationImageItem):Draft{
  return {
    source_type:item.source_type||'',
    source_name:item.source_name||'',
    source_url:item.source_url||'',
    image_urls:(item.image_urls||[]).join('\n'),
    match_basis:item.match_basis||'',
    exact_match:item.exact_match,
    authorized_for_use:item.authorized_for_use,
    notes:item.notes||'',
  };
}

function statusLabel(status:ImageReviewStatus){
  if(status==='READY_FOR_REVIEW')return 'Lista para revisar';
  if(status==='APPROVED')return 'Imágenes aprobadas';
  if(status==='REJECTED')return 'Descartada';
  return 'Borrador';
}

function sourceLabel(source:ImageSourceType|''|null|undefined){
  if(source==='OWN_ML')return 'Publicación propia de KIKI';
  if(source==='ML_CATALOG')return 'Catálogo de Mercado Libre';
  if(source==='MANUFACTURER')return 'Fabricante / marca oficial';
  if(source==='OTHER_SELLER')return 'Otro vendedor de Mercado Libre';
  if(source==='OTHER')return 'Otra fuente autorizada';
  return 'Sin fuente';
}

export function ImageReview(){
  const [queue,setQueue]=useState<PrepublicationImageQueue|null>(null);
  const [drafts,setDrafts]=useState<Record<string,Draft>>({});
  const [search,setSearch]=useState('');
  const [status,setStatus]=useState<ImageReviewStatus|''>('');
  const [busy,setBusy]=useState('');
  const [message,setMessage]=useState('');
  const [success,setSuccess]=useState('');

  async function load(){
    try{
      const data=await api.prepublicationImages();
      setQueue(data);
      setDrafts(current=>{
        const next={...current};
        for(const item of data.items){if(!next[item.product_key])next[item.product_key]=draftFrom(item)}
        return next;
      });
      setMessage('');
    }catch(error){setMessage(error instanceof Error?error.message:'No se pudo cargar la revisión de imágenes.')}
  }

  useEffect(()=>{void load()},[]);

  const items=useMemo(()=>{
    const term=search.trim().toLowerCase();
    return (queue?.items||[]).filter(item=>{
      if(status&&item.image_status!==status)return false;
      if(!term)return true;
      return [item.product.sku,item.product.name,item.verified_core_data.brand,item.verified_core_data.ean,item.source_name].some(value=>String(value||'').toLowerCase().includes(term));
    });
  },[queue,search,status]);

  function setField<K extends keyof Draft>(key:string,field:K,value:Draft[K]){
    setDrafts(current=>{
      const base=current[key]||draftFrom(queue!.items.find(item=>item.product_key===key)!);
      const next={...base,[field]:value};
      if(field==='source_type'){
        const source=value as ImageSourceType|'';
        if(!base.source_name.trim())next.source_name=source?sourceLabel(source):'';
      }
      return {...current,[key]:next};
    });
  }

  async function save(item:PrepublicationImageItem,nextStatus:ImageReviewStatus){
    const draft=drafts[item.product_key]||draftFrom(item);
    const imageUrls=draft.image_urls.split(/\r?\n|,/).map(value=>value.trim()).filter(Boolean);
    const payload:PrepublicationImagePayload={
      product_key:item.product_key,
      status:nextStatus,
      source_type:draft.source_type||undefined,
      source_name:draft.source_name.trim()||(draft.source_type?sourceLabel(draft.source_type):undefined),
      source_url:draft.source_url||undefined,
      image_urls:imageUrls,
      match_basis:draft.match_basis||undefined,
      exact_match:draft.exact_match,
      authorized_for_use:draft.authorized_for_use,
      notes:draft.notes||undefined,
    };
    setBusy(item.product_key);setMessage('');setSuccess('');
    try{
      await api.savePrepublicationImages(payload);
      setSuccess(nextStatus==='APPROVED'?'Imágenes aprobadas dentro de KIKI Tech. No se publicó nada.':'Revisión de imágenes guardada.');
      setDrafts(current=>{const next={...current};delete next[item.product_key];return next});
      await load();
    }catch(error){
      setMessage(error instanceof Error?error.message:'No se pudo guardar la revisión de imágenes.');
      window.scrollTo({top:0,behavior:'smooth'});
    }
    finally{setBusy('')}
  }

  if(message&&!queue)return <><header><div><p className="eyebrow">IMÁGENES</p><h1>Fuentes de imágenes</h1></div></header><div className="notice warning">{message}</div></>;
  if(!queue)return <div className="auth-loading">Preparando revisión de imágenes…</div>;
  const s=queue.summary;

  return <>
    <header><div><p className="eyebrow">MVP3.8 · PRE-PUBLICACIÓN</p><h1>Fuentes de imágenes + aprobación</h1><p>Registrá de dónde sale cada imagen y verificá la presentación exacta antes de usarla.</p></div></header>
    {message&&<div className="notice warning">{message}</div>}
    {success&&<div className="notice success">{success}</div>}
    <div className="notice warning"><strong>No copia ni publica imágenes automáticamente.</strong> Una publicación de otro vendedor puede servir como referencia, pero nunca puede aprobarse como fuente de uso.</div>

    <section className="cards image-cards">
      <article><span>Productos</span><strong>{s.total.toLocaleString('es-AR')}</strong></article>
      <article><span>Pendientes</span><strong>{s.pending.toLocaleString('es-AR')}</strong></article>
      <article><span>Listas para revisar</span><strong>{s.READY_FOR_REVIEW.toLocaleString('es-AR')}</strong></article>
      <article><span>Imágenes aprobadas</span><strong>{s.approved.toLocaleString('es-AR')}</strong></article>
      <article><span>Descartadas</span><strong>{s.REJECTED.toLocaleString('es-AR')}</strong></article>
    </section>

    <section className="panel image-policy">
      <h2>Orden de fuentes recomendado</h2>
      <div className="image-source-grid">
        <div><strong>1 · Publicación propia</strong><small>La fuente más segura cuando coincide exactamente.</small></div>
        <div><strong>2 · Catálogo ML</strong><small>Usar cuando el producto y GTIN coinciden.</small></div>
        <div><strong>3 · Fabricante oficial</strong><small>Requiere confirmar autorización de uso.</small></div>
        <div className="warning-source"><strong>Referencia · Otro vendedor</strong><small>No se aprueba ni se reutiliza automáticamente.</small></div>
      </div>
      {!queue.mercadolibre_connected&&<p>Mercado Libre todavía no está conectado.</p>}
    </section>

    <section className="panel">
      <div className="filters image-filters">
        <input placeholder="Buscar SKU, producto, marca o EAN" value={search} onChange={e=>setSearch(e.target.value)}/>
        <select value={status} onChange={e=>setStatus(e.target.value as ImageReviewStatus|'')}>
          <option value="">Todos los estados</option><option value="DRAFT">Borradores</option><option value="READY_FOR_REVIEW">Listas para revisar</option><option value="APPROVED">Aprobadas</option><option value="REJECTED">Descartadas</option>
        </select>
      </div>
      <p className="result-count">Mostrando <strong>{items.length.toLocaleString('es-AR')}</strong> de {s.total.toLocaleString('es-AR')} productos</p>

      <div className="image-review-list">{items.map(item=>{
        const draft=drafts[item.product_key]||draftFrom(item);
        const isBusy=busy===item.product_key;
        const otherSeller=draft.source_type==='OTHER_SELLER';
        return <article className="image-review-item" key={item.product_key}>
          <div className="image-review-head">
            <div><span className={`image-status ${item.image_status}`}>{statusLabel(item.image_status)}</span><h2>{item.product.name||'Producto sin nombre'}</h2><p>SKU {item.product.sku||'—'} · Stock {item.product.stock??'—'} · Marca {item.verified_core_data.brand||'—'} · EAN {item.verified_core_data.ean||'—'}</p></div>
            {item.history_count>0&&<small>{item.history_count} movimiento{item.history_count===1?'':'s'}</small>}
          </div>

          <div className="image-review-form">
            <label>Tipo de fuente<select value={draft.source_type} onChange={e=>setField(item.product_key,'source_type',e.target.value as ImageSourceType|'')}><option value="">Seleccionar</option><option value="OWN_ML">Publicación propia de KIKI</option><option value="ML_CATALOG">Catálogo de Mercado Libre</option><option value="MANUFACTURER">Fabricante / marca oficial</option><option value="OTHER_SELLER">Otro vendedor de Mercado Libre</option><option value="OTHER">Otra fuente autorizada</option></select></label>
            <label>Fuente<input value={draft.source_name} placeholder={sourceLabel(draft.source_type)} onChange={e=>setField(item.product_key,'source_name',e.target.value)}/></label>
            <label>URL de la fuente<input type="url" value={draft.source_url} placeholder="https://…" onChange={e=>setField(item.product_key,'source_url',e.target.value)}/></label>
            <label>Coincidencia<select value={draft.match_basis} onChange={e=>setField(item.product_key,'match_basis',e.target.value as ImageMatchBasis|'')}><option value="">Seleccionar</option><option value="GTIN_EXACT">GTIN/EAN exacto</option><option value="OWN_LISTING">Publicación propia verificada</option><option value="MANUAL_EXACT">Verificación manual exacta</option></select></label>
            <label className="image-url-field">URLs de imágenes<textarea value={draft.image_urls} placeholder={'Una URL por línea\nhttps://…'} onChange={e=>setField(item.product_key,'image_urls',e.target.value)}/></label>
            <label className="image-notes">Observaciones<textarea value={draft.notes} placeholder="Presentación, tamaño, pack/unidad, advertencias…" onChange={e=>setField(item.product_key,'notes',e.target.value)}/></label>
          </div>

          <div className="image-confirmations">
            <label><input type="checkbox" checked={draft.exact_match} onChange={e=>setField(item.product_key,'exact_match',e.target.checked)}/> Confirmé que corresponde exactamente al producto y presentación.</label>
            <label><input type="checkbox" checked={draft.authorized_for_use} onChange={e=>setField(item.product_key,'authorized_for_use',e.target.checked)}/> Confirmé que KIKI puede usar estas imágenes.</label>
          </div>
          {otherSeller&&<div className="notice warning compact"><strong>Solo referencia.</strong> Las imágenes de otro vendedor no pueden aprobarse como fuente de uso.</div>}

          {item.image_urls.length>0&&<div className="image-preview-strip">{item.image_urls.slice(0,6).map(url=><a href={url} target="_blank" rel="noreferrer" key={url}><img src={url} alt="Imagen candidata" loading="lazy"/></a>)}</div>}

          <div className="image-actions"><button className="secondary" disabled={isBusy} onClick={()=>void save(item,'DRAFT')}>Guardar borrador</button><button disabled={isBusy} onClick={()=>void save(item,'READY_FOR_REVIEW')}>Lista para revisar</button><button className="accept" disabled={isBusy||otherSeller} onClick={()=>void save(item,'APPROVED')}>Aprobar imágenes</button><button className="ghost danger" disabled={isBusy} onClick={()=>void save(item,'REJECTED')}>Descartar</button></div>
        </article>;
      })}</div>
      <p className="evidence-note">{queue.policy.description}</p>
    </section>
  </>;
}
