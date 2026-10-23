import {useEffect, useRef, useState} from 'react';
import {api} from '../services/api';
import type {EcommAppPreviewList, EcommAppStatus, EcommAppPreview, EcommAppLookup, EcommCatalogAudit, EcommStageStatus, EcommStageComparison} from '../types/ecomm-app';
import {EcommAdoptionReadiness} from './EcommAdoptionReadiness';
import {EcommHybridInspector} from './EcommHybridInspector';
import '../ecomm-app.css';

const comboLabel=(flag:boolean|null|undefined)=>flag===true?'Sí':flag===false?'No':'No informado';


function PreviewList({data,label}:{data:EcommAppPreviewList;label:string}){
  return <section className="kiki-ecomm-result">
    <h4>{label}</h4>
    {data.warning&&<p role="note" className="kiki-ecomm-notice">{data.warning}</p>}
    <p>Registros devueltos en esta consulta: <strong>{data.count??'Formato por confirmar'}</strong></p>
    {data.envelope_keys.length>0&&<small>Campos de respuesta: {data.envelope_keys.join(', ')}</small>}
    {data.samples.map((item,i)=><article className="kiki-ecomm-sample" key={i}>
      <strong>{item.code||item.name||item.description||'Registro '+(i+1)}</strong>
      {item.description&&item.code&&<p>{item.description}</p>}
      {item.code&&<p><strong>Producto padre (code):</strong> {item.code}</p>}
      {typeof item.variant_count==='number'&&<p><strong>Variantes dentro de este producto:</strong> {item.variant_count} · <strong>Combo declarado por API:</strong> {comboLabel(item.is_combo)}</p>}
      {item.id!=null&&<p>ID de depósito: {item.id}</p>}
      <small>Campos presentes: {item.available_fields.join(', ')||'Sin campos'}</small>
      {(item.variants||[]).map((variant,j)=><div className="kiki-ecomm-variant" key={j}>
        <p><strong>SKU de variante:</strong> {variant.sku||'No informado'} · <strong>ID variante:</strong> {variant.id??'No informado'}</p>
        {variant.variant_description&&<p><strong>Presentación:</strong> {variant.variant_description}</p>}
        <p><strong>Combo de variante (API):</strong> {comboLabel(variant.is_combo)} · <strong>GTIN:</strong> {variant.barcode||'No informado'} · <strong>Stock total:</strong> {variant.total_stock??'No informado'}</p>
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
  const [busy,setBusy]=useState<'preview'|'lookup'|'audit'|''>('');
  const [error,setError]=useState('');
  const [preview,setPreview]=useState<EcommAppPreview|null>(null);
  const [lookup,setLookup]=useState<EcommAppLookup|null>(null);
  const [skuText,setSkuText]=useState('');
  const [audit,setAudit]=useState<EcommCatalogAudit|null>(null);
  const [stage,setStage]=useState<EcommStageStatus|null>(null);
  const [stageBusy,setStageBusy]=useState(false);
  const [stageError,setStageError]=useState('');
  const [comparison,setComparison]=useState<EcommStageComparison|null>(null);
  const [comparisonBusy,setComparisonBusy]=useState(false);
  const [comparisonError,setComparisonError]=useState('');
  const [extraFilter,setExtraFilter]=useState<'ALL'|'COMBO'|'REGULAR'|'UNKNOWN'>('ALL');
  const [showAllExtras,setShowAllExtras]=useState(false);
  const stageStop=useRef(false);
  const stageRunning=useRef(false);

  useEffect(()=>{
    let active=true;
    api.ecommAppStatus()
      .then(data=>{if(active)setStatus(data)})
      .catch(e=>{if(active)setError(e instanceof Error?e.message:'No se pudo consultar el estado de Ecomm-App.')})
      .finally(()=>{if(active)setChecking(false)});
    api.ecommStageStatus().then(data=>{if(active)setStage(data)}).catch(()=>{});
    return ()=>{active=false;stageStop.current=true};
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

  async function auditPages(page:number){
    setBusy('audit');setError('');
    try{setAudit(await api.ecommAppCatalogAudit(page))}
    catch(e){setError(e instanceof Error?e.message:'No se pudo auditar el catálogo.')}
    finally{setBusy('')}
  }

  async function copyStage(){
    if(stageRunning.current) return;
    stageRunning.current=true;
    stageStop.current=false;
    setStageBusy(true);
    setStageError('');
    try{
      // Explicit one-click foreground process. Every successful batch
      // persists separately, so reloading can resume from its cursor.
      for(let batch=0;batch<100&&!stageStop.current;batch++){
        const next=await api.ecommStageNext();
        setStage(next);
        if(next.complete||!next.can_continue)break;
      }
    }catch(e){setStageError(e instanceof Error?e.message:'No se pudo continuar la copia de prueba.')}
    finally{stageRunning.current=false;setStageBusy(false)}
  }

  async function compareCatalogs(){
    setComparisonBusy(true);setComparisonError('');
    try{setComparison(await api.ecommStageCompare())}
    catch(e){setComparisonError(e instanceof Error?e.message:'No se pudo comparar con el catálogo histórico.')}
    finally{setComparisonBusy(false)}
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
        <section className="kiki-ecomm-sku-diagnosis">
          <h4>¿Cuáles de los SKU pedidos encontró realmente la API?</h4>
          {lookup.sku_diagnosis.warning&&<p className="kiki-ecomm-notice">{lookup.sku_diagnosis.warning}</p>}
          <p><strong>Productos padre devueltos:</strong> {lookup.sku_diagnosis.parent_count??'No verificable'} · <strong>Variantes incluidas:</strong> {lookup.sku_diagnosis.variant_count??'No verificable'} · <strong>Otras variantes hermanas:</strong> {lookup.sku_diagnosis.sibling_variant_count??'No verificable'}</p>
          <p className="kiki-ecomm-hint">El número de productos no indica cuántos SKU se encontraron: cada producto puede incluir otras variantes. Nunca sumamos sus stocks automáticamente.</p>
          {lookup.sku_diagnosis.requested.map((item,i)=><article className="kiki-ecomm-requested" key={item.sku+'-'+i}>
            <div className="kiki-ecomm-requested-head">
              <strong>SKU pedido: {item.sku}</strong>
              <span>{item.status==='EXACT_SINGLE'?'Encontrado literalmente':item.status==='MULTIPLE_EXACT'?'Duplicado exacto: revisar':item.status==='UNKNOWN_SHAPE'?'Formato por identificar':'Sin coincidencia literal en la respuesta'}</span>
            </div>
            {item.matches.map((match,j)=><div className="kiki-ecomm-request-match" key={j}>
              <p><strong>Producto padre:</strong> {match.parent_code||'No informado'} · <strong>Combo (API):</strong> {comboLabel(match.parent_is_combo)}</p>
              <p><strong>Variante:</strong> {match.variant_sku} · <strong>ID:</strong> {match.variant_id??'No informado'} · <strong>Combo (API):</strong> {comboLabel(match.variant_is_combo)} · <strong>Stock:</strong> {match.total_stock??'No informado'}</p>
              {match.variant_description&&<p><strong>Presentación:</strong> {match.variant_description}</p>}
            </div>)}
          </article>)}
          <small>Coincidencia literal solo para diagnóstico. No se confirma correspondencia con los SKU históricos de KIKI ni se vincula stock.</small>
        </section>
        <PreviewList data={lookup.product_preview} label="Productos padre y todas sus variantes devueltas"/>
        <small>{lookup.note}</small>
      </div>}
    </details>
    <details className="kiki-ecomm-sku-check">
      <summary>Auditar el catálogo de Ecomm-App por páginas (sin importar)</summary>
      <p>Revisamos como máximo <strong>dos páginas de 50 productos</strong> por consulta. Comprobamos IDs de variantes, SKU, combos y paginación, sin tocar el catálogo actual.</p>
      <button type="button" disabled={!status?.configured||busy!==''} onClick={()=>void auditPages(1)}>
        {busy==='audit'?'Leyendo páginas…':'Auditar las primeras 2 páginas'}
      </button>
      {audit&&<section className="kiki-ecomm-sku-diagnosis">
        <h4>Resultado de la auditoría parcial</h4>
        <p><strong>Páginas consultadas:</strong> {audit.pages.map(x=>x.page).join(' y ')} · <strong>Productos padre:</strong> {audit.totals_in_this_batch.parents} · <strong>Variantes:</strong> {audit.totals_in_this_batch.variants}</p>
        <div className="kiki-ecomm-audit-metrics">
          <span>Padres combo: <b>{audit.totals_in_this_batch.combo_parents}</b></span>
          <span>Variantes combo: <b>{audit.totals_in_this_batch.combo_variants}</b></span>
          <span>Sin ID variante: <b>{audit.totals_in_this_batch.variants_without_id}</b></span>
          <span>Sin SKU: <b>{audit.totals_in_this_batch.variants_without_sku}</b></span>
          <span>Sin dato de stock: <b>{audit.totals_in_this_batch.variants_without_total_stock}</b></span>
          <span>IDs repetidos en este bloque: <b>{audit.totals_in_this_batch.repeated_variant_ids}</b></span>
          <span>SKU repetidos en este bloque: <b>{audit.totals_in_this_batch.repeated_skus}</b></span>
        </div>
        {audit.pages.map(item=><div className="kiki-ecomm-requested" key={item.page}>
          <strong>Página {item.page}: {item.parents} productos</strong>
          <small>Metadatos de paginación: {item.pagination.present?'Disponibles':'No identificados'}</small>
          <small>Campos de paginación: {item.pagination.available_fields.join(', ')||'Ninguno'}</small>
          {Object.keys(item.pagination.values).length>0&&<small>Valores: {Object.entries(item.pagination.values).map(([key,value])=>key+': '+String(value)).join(' · ')}</small>}
        </div>)}
        <p className="kiki-ecomm-hint">{audit.notice}</p>
        {audit.next_page_to_check!=null&&<button type="button" disabled={busy!==''} onClick={()=>void auditPages(audit.next_page_to_check!)}>
          {busy==='audit'?'Leyendo…':'Revisar páginas '+audit.next_page_to_check+' y '+(audit.next_page_to_check+1)}
        </button>}
        <small>Los indicadores muestran únicamente este bloque, no todo el inventario. No guardamos registros ni reemplazamos planillas anteriores.</small>
      </section>}
    </details>
    <details className="kiki-ecomm-sku-check">
      <summary>Crear una copia completa de prueba del catálogo por API</summary>
      <p>Copiamos los productos y variantes en un <strong>espacio independiente de KIKI</strong>. No reemplaza los Excel anteriores, no cambia inventario ni activa la conciliación con estos datos.</p>
      {stage&&<div className="kiki-ecomm-sku-diagnosis" aria-live="polite">
        <h4>{stage.complete?'Copia de prueba terminada · pendiente de comparación':stage.exists?'Copia de prueba en preparación':'Aún no se creó una copia'}</h4>
        <p><strong>Avance:</strong> {stage.pages_saved}{stage.expected_pages!=null?' de '+stage.expected_pages:''} páginas · <strong>Productos copiados:</strong> {stage.quality.parents}{stage.expected_parents!=null?' de '+stage.expected_parents:''} · <strong>Variantes:</strong> {stage.quality.variants}</p>
        <div className="kiki-ecomm-audit-metrics">
          <span>Padres combo: <b>{stage.quality.combo_parents}</b></span>
          <span>Variantes combo: <b>{stage.quality.combo_variants}</b></span>
          <span>Sin ID de variante: <b>{stage.quality.without_variant_id}</b></span>
          <span>Sin SKU: <b>{stage.quality.without_sku}</b></span>
          <span>Sin dato de stock: <b>{stage.quality.without_total_stock}</b></span>
          <span>ID variante repetido: <b>{stage.quality.duplicate_variant_ids}</b></span>
          <span>SKU repetidos: <b>{stage.quality.duplicate_skus}</b></span>
        </div>
        <p className="kiki-ecomm-hint">{stage.warning}</p>
        {stage.has_quality_warnings&&<p className="kiki-ecomm-notice">Hay observaciones de calidad: se requiere inspección antes de utilizar estos datos.</p>}
      </div>}
      {stageError&&<p className="kiki-ecomm-notice" role="alert">{stageError} El progreso ya guardado se conserva; podés continuar desde la página pendiente.</p>}
      {stage?.complete&&<div className="kiki-ecomm-sku-diagnosis">
        <h4>Comparar la copia API con el inventario histórico</h4>
        <p>Comprobamos el ID interno de cada variante y su SKU histórico. Solo mostramos diferencias: no se reemplaza ninguna ficha, stock ni decisión.</p>
        <button type="button" disabled={comparisonBusy||stageBusy} onClick={()=>void compareCatalogs()}>
          {comparisonBusy?'Comparando catálogos…':'Comparar con el Excel histórico (solo lectura)'}
        </button>
        {comparisonError&&<p className="kiki-ecomm-notice" role="alert">{comparisonError}</p>}
        {comparison&&<div className="kiki-ecomm-preview">
          <EcommAdoptionReadiness plan={comparison.adoption_plan}/>
          <EcommHybridInspector comparison={comparison}/>
          <h4>Resultados de coincidencias entre fuentes</h4>
          <div className="kiki-ecomm-audit-metrics">
            <span>Productos históricos: <b>{comparison.totals.historical_products}</b></span>
            <span>Variantes API: <b>{comparison.totals.api_variants}</b></span>
            <span>Coinciden por ID: <b>{comparison.totals.matched_stable_ids}</b></span>
            <span>Mismo ID y SKU: <b>{comparison.totals.same_id_same_sku}</b></span>
            <span>Mismo ID, SKU escrito distinto: <b>{comparison.totals.same_id_format_sku_changed}</b></span>
            <span>Mismo ID, SKU diferente: <b>{comparison.totals.same_id_different_sku}</b></span>
            <span>Históricos sin ID coincidente: <b>{comparison.totals.historical_no_stable_id_match}</b></span>
            <span>Variantes API sin ID histórico: <b>{comparison.totals.api_no_stable_id_match}</b></span>
            <span>Solo API: combo Sí: <b>{comparison.totals.api_only_combo_yes??0}</b></span>
            <span>Solo API: combo No: <b>{comparison.totals.api_only_combo_no??0}</b></span>
            <span>Solo API: combo no informado: <b>{comparison.totals.api_only_combo_unknown??0}</b></span>
            <span>Posibles vínculos solo por SKU: <b>{comparison.totals.candidate_sku_only}</b></span>
            <span>Stock diferente (orientativo): <b>{comparison.totals.stock_differences_informational}</b></span>
            <span>GTIN discordante si ambos presentes: <b>{comparison.totals.gtin_disagreement_when_both_present}</b></span>
            <span>ID histórico repetido: <b>{comparison.totals.duplicate_legacy_ids}</b></span>
          </div>
          <p className="kiki-ecomm-hint">{comparison.warning}</p>
          <details open>
            <summary>Revisar los SKU realmente distintos ({comparison.totals.same_id_different_sku})</summary>
            <p>Conservan el mismo ID interno, pero su SKU cambió más allá de espacios o mayúsculas. Estos casos tienen prioridad de revisión.</p>
            {comparison.samples.sku_changed_same_id.filter(item=>item.change_type==='SUBSTANTIVE').map(item=><div className="kiki-ecomm-requested" key={item.ecomm_id}>
              <strong>ID Ecomm: {item.ecomm_id} · {item.product}</strong>
              <p>SKU anterior: <code>{item.old_sku||'No informado'}</code> → SKU API: <code>{item.api_sku||'No informado'}</code></p>
              <small>Producto padre: {item.api_parent_code||'No informado'} · Combo según API: {comboLabel(item.api_is_combo)}</small>
            </div>)}
          </details>
          <details>
            <summary>Revisar diferencias de escritura ({comparison.totals.same_id_format_sku_changed})</summary>
            <p>El mismo ID interno continúa vigente. La diferencia puede ser de espacios y mayúsculas; no hace falta cambiar automáticamente el SKU histórico.</p>
            {comparison.samples.sku_changed_same_id.filter(item=>item.change_type==='FORMAT_ONLY').map(item=><div className="kiki-ecomm-requested" key={item.ecomm_id}>
              <strong>ID Ecomm: {item.ecomm_id} · {item.product}</strong>
              <p>SKU anterior: <code>{item.old_sku||'No informado'}</code> → SKU API: <code>{item.api_sku||'No informado'}</code></p>
            </div>)}
          </details>
          <details>
            <summary>Revisar el producto histórico sin ID coincidente ({comparison.totals.historical_no_stable_id_match})</summary>
            {comparison.samples.historical_without_id_match.map((item,i)=><p className="kiki-ecomm-requested" key={item.ecomm_id||i}>ID: {item.ecomm_id||'Sin ID'} · SKU: {item.sku||'Sin SKU'} · {item.product}</p>)}
            <small>Sin coincidencia por ID no significa eliminado. Verificar en Ecomm-App antes de modificar nada.</small>
          </details>
          <details>
            <summary>Investigar variantes que solo figuran en la API ({comparison.totals.api_no_stable_id_match})</summary>
            <p>Se identifican por su ID. Pueden ser combos, productos nuevos o registros que no estaban en el Excel anterior. El atributo «Combo» proviene de la API.</p>
            <p><strong>Combo Sí:</strong> {comparison.totals.api_only_combo_yes??0} · <strong>Combo No:</strong> {comparison.totals.api_only_combo_no??0} · <strong>Sin dato de combo:</strong> {comparison.totals.api_only_combo_unknown??0}</p>
            <small>Productos padre con sufijo _m: {comparison.totals.api_only_parent_m_suffix??0} (solo una pista, no una clasificación).</small>
            <label className="kiki-ecomm-filter-label">Mostrar
              <select value={extraFilter} onChange={event=>{setExtraFilter(event.target.value as typeof extraFilter);setShowAllExtras(false)}}>
                <option value="ALL">Todas las variantes sin ID histórico</option>
                <option value="COMBO">Solo combos confirmados</option>
                <option value="REGULAR">Solo no combos</option>
                <option value="UNKNOWN">Combo sin dato</option>
              </select>
            </label>
            {(()=> {
              const rows=comparison.samples.api_without_id_match.filter(item=>extraFilter==='ALL'||(extraFilter==='COMBO'&&item.is_combo===true)||(extraFilter==='REGULAR'&&item.is_combo===false)||(extraFilter==='UNKNOWN'&&item.is_combo==null));
              const shown=showAllExtras?rows:rows.slice(0,12);
              return <div className="kiki-ecomm-focused-list">
                <p>Mostrando {shown.length} de {rows.length} registros disponibles con este filtro{comparison.display_limits.api_only_total>comparison.display_limits.api_only_visible?' (la respuesta completa supera el límite de visualización)':''}.</p>
                {shown.map((item,i)=><div className="kiki-ecomm-requested" key={item.api_id||i}>
                  <strong>SKU: {item.sku||'Sin SKU'} · ID API: {item.api_id||'Sin ID'}</strong>
                  <p>Producto padre: {item.parent_code||'No informado'} · <strong>Combo (API): {comboLabel(item.is_combo)}</strong></p>
                </div>)}
                {rows.length>12&&!showAllExtras&&<button type="button" onClick={()=>setShowAllExtras(true)}>Mostrar las {rows.length} variantes de este filtro</button>}
                {showAllExtras&&rows.length>12&&<button type="button" onClick={()=>setShowAllExtras(false)}>Mostrar solo 12</button>}
              </div>;
            })()}
            <small>No se incorporan estos registros al catálogo operativo ni se vinculan publicaciones.</small>
          </details>
          <details>
            <summary>Ver posibles vínculos por SKU (no confirmados)</summary>
            {comparison.samples.candidate_by_sku.length===0?<p>Sin candidatos solo por SKU en la muestra.</p>:comparison.samples.candidate_by_sku.map((item,i)=><p className="kiki-ecomm-requested" key={i}>ID histórico: {item.historical_id||'No informado'} · {item.historical_sku} → ID API: {item.api_id||'No informado'} · {item.api_sku} ({item.basis==='SAME_SKU_DIFFERENT_ID'?'SKU idéntico, ID distinto':'Coincide solo al ignorar espacios y mayúsculas'})</p>)}
          </details>
          <small>Reporte no editable. No se promueve la copia API como fuente de KIKI ni se sincroniza stock.</small>
        </div>}
      </div>}
      {stage?.complete?<p><strong>Copia terminada.</strong> Sigue siendo independiente del catálogo actual. El próximo paso es comparar IDs y SKU antes de aprobar cualquier cambio.</p>:
        <div className="kiki-ecomm-actions">
          <button type="button" disabled={!status?.configured||stageBusy||busy!==''} onClick={()=>void copyStage()}>
            {stageBusy?'Preparando copia…':stage?.exists?'Continuar copia de prueba':'Preparar copia de prueba (solo lectura)'}
          </button>
          {stageBusy&&<button type="button" onClick={()=>{stageStop.current=true}}>Pausar al terminar el bloque</button>}
        </div>}
      <small>El proceso funciona mientras esta página esté abierta. Se guarda cada bloque de hasta 3 páginas. Si interrumpís la operación, podrás retomarla sin comenzar desde cero.</small>
    </details>
    <small>Esta integración no incluye todavía importación masiva ni vínculos Ecomm–Mercado Libre–Tiendanube. Facturación permanece fuera del alcance.</small>
  </section>;
}
