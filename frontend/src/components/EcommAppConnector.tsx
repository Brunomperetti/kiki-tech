import {useEffect, useState} from 'react';
import {api} from '../services/api';
import type {EcommAppPreviewList, EcommAppStatus, EcommAppPreview, EcommAppLookup} from '../types/ecomm-app';
import '../ecomm-app.css';

function PreviewList({data,label}:{data:EcommAppPreviewList;label:string}){
  return <section className="kiki-ecomm-result">
    <h4>{label}</h4>
    {data.warning&&<p role="note" className="kiki-ecomm-notice">{data.warning}</p>}
    <p>Registros devueltos en esta consulta: <strong>{data.count??'Formato por confirmar'}</strong></p>
    {data.envelope_keys.length>0&&<small>Campos de respuesta: {data.envelope_keys.join(', ')}</small>}
    {data.samples.map((item,i)=><article className="kiki-ecomm-sample" key={i}>
      <strong>{item.code||item.name||item.description||'Registro '+(i+1)}</strong>
      {item.description&&item.code&&<p>{item.description}</p>}
      {item.id!=null&&<p>ID de depósito: {item.id}</p>}
      <small>Campos presentes: {item.available_fields.join(', ')||'Sin campos'}</small>
      {(item.variants||[]).map((variant,j)=><div className="kiki-ecomm-variant" key={j}>
        <p><strong>SKU:</strong> {variant.sku||'No informado'} · <strong>GTIN:</strong> {variant.barcode||'No informado'} · <strong>Stock total:</strong> {variant.total_stock??'No informado'}</p>
        {variant.warehouse_sample.length>0&&<p>Depósitos: {variant.warehouse_sample.map(w=>`${w.id??'?'} (${w.stock??'sin dato'})`).join(' · ')}</p>}
        <small>Campos de variante: {variant.available_fields.join(', ')}</small>
      </div>)}
      {typeof item.variant_count==='number'&&item.variant_count>5&&<small>Se muestran solo 5 de {item.variant_count} variantes.</small>}
    </article>)}
  </section>;
}

export function EcommAppConnector(){
  const [status,setStatus]=useState<EcommAppStatus|null>(null);
  const [checking,setChecking]=useState(true);
  const [busy,setBusy]=useState<'preview'|'lookup'|''>('');
  const [error,setError]=useState('');
  const [preview,setPreview]=useState<EcommAppPreview|null>(null);
  const [lookup,setLookup]=useState<EcommAppLookup|null>(null);
  const [skuText,setSkuText]=useState('');

  useEffect(()=>{
    let active=true;
    api.ecommAppStatus()
      .then(data=>{if(active)setStatus(data)})
      .catch(e=>{if(active)setError(e instanceof Error?e.message:'No se pudo consultar el estado de Ecomm-App.')})
      .finally(()=>{if(active)setChecking(false)});
    return ()=>{active=false};
  },[]);

  async function testConnection(){
    setBusy('preview');setError('');setPreview(null);
    try{setPreview(await api.ecommAppPreview())}
    catch(e){setError(e instanceof Error?e.message:'No se pudo consultar Ecomm-App.')}
    finally{setBusy('')}
  }
  async function querySkus(){
    const skus=skuText.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean);
    if(skus.length<1||skus.length>3){setError('Ingresá entre 1 y 3 SKU separados por comas.');return}
    if(new Set(skus).size!==skus.length){setError('Ingresá SKU sin repetir.');return}
    setBusy('lookup');setError('');setLookup(null);
    try{setLookup(await api.ecommAppLookup(skus))}
    catch(e){setError(e instanceof Error?e.message:'No se pudo consultar esos SKU.')}
    finally{setBusy('')}
  }

  return <section className="panel kiki-ecomm-connection">
    <div className="kiki-ecomm-head">
      <div><h2>Ecomm-App · Conexión directa de inventario</h2>
        <p>Primera etapa: comprobar el acceso y leer unos pocos productos y depósitos. <strong>No importa ni reemplaza el catálogo de KIKI.</strong></p></div>
      <span className="kiki-ecomm-mode">Solo lectura</span>
    </div>
    {checking?<p>Comprobando configuración…</p>:status?.configured?
      <p>La clave está configurada en el servidor. Falta comprobar que Ecomm-App la acepte con permiso <code>inventario:leer</code>.</p>:
      <p className="kiki-ecomm-notice">Pendiente: agregá <code>ECOMM_APP_API_TOKEN</code> en las variables de entorno del <strong>backend de Render</strong>. No pegues la clave acá ni en GitHub.</p>}
    {error&&<div className="notice warning" role="alert">{error}</div>}
    <div className="kiki-ecomm-actions">
      <button type="button" disabled={!status?.configured||busy!==''} onClick={()=>void testConnection()}>
        {busy==='preview'?'Consultando…':'Probar conexión y leer 3 productos'}
      </button>
    </div>
    {preview&&<div className="kiki-ecomm-preview">
      <p className="kiki-ecomm-ok">Ecomm-App respondió a las consultas de inventario y depósitos.</p>
      <div className="kiki-ecomm-results">
        <PreviewList data={preview.warehouse_preview} label="Depósitos activos"/>
        <PreviewList data={preview.product_preview} label="Muestra de productos y variantes"/>
      </div>
      <small>{preview.note}</small>
    </div>}
    <details className="kiki-ecomm-sku-check">
      <summary>Opcional: consultar hasta 3 SKU concretos</summary>
      <p>El servicio oficial consulta el stock por SKU mediante un POST de <strong>solo lectura</strong>, sin cambiar nada en Ecomm-App.</p>
      <label>SKU separados por coma o salto de línea
        <textarea rows={2} value={skuText} onChange={e=>setSkuText(e.target.value)}
          placeholder="VITANERALVAINILLA, VITANERALCHOCOLATE"/>
      </label>
      <button type="button" disabled={!status?.configured||busy!==''} onClick={()=>void querySkus()}>
        {busy==='lookup'?'Consultando…':'Consultar SKU sin modificar stock'}
      </button>
      {lookup&&<div className="kiki-ecomm-preview">
        <PreviewList data={lookup.product_preview} label="Respuesta de stock por SKU"/>
        <small>{lookup.note}</small>
      </div>}
    </details>
    <small>Esta integración no incluye todavía importación masiva ni vínculos Ecomm–Mercado Libre–Tiendanube. Facturación permanece fuera del alcance.</small>
  </section>;
}
