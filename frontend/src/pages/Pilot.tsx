import {useEffect,useMemo,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {Summary,ReadinessReport,MercadoLibreStatus} from '../types/catalog';
import type {EcommStageStatus} from '../types/ecomm-app';
import '../pilot.css';

type Sources={
  summary:Summary|null;
  readiness:ReadinessReport|null;
  stage:EcommStageStatus|null;
  ml:MercadoLibreStatus|null;
  tn:Awaited<ReturnType<typeof api.tiendanubeReport>>|null;
  history:Awaited<ReturnType<typeof api.internalDecisionHistory>>|null;
};
const initial:Sources={summary:null,readiness:null,stage:null,ml:null,tn:null,history:null};
const asNum=(n?:number|null)=>n==null?'No disponible':n.toLocaleString('es-AR');
function sourceName(summary:Summary|null){
  return summary?.import_diagnostics?.find(x=>x.source==='ECOMM_APP');
}
function dateLabel(value?:string|null){
  if(!value)return 'No hay fecha de sincronización disponible';
  const date=new Date(value);
  return Number.isNaN(date.valueOf())?'Fecha no disponible':date.toLocaleString('es-AR');
}
function statusText(ok:boolean|null){
  return ok===true?'Disponible':ok===false?'Pendiente':'No se pudo comprobar';
}
function sourceClass(ok:boolean|null){
  return ok===true?'is-ok':ok===false?'is-caution':'is-unknown';
}

export function Pilot(){
  const [sources,setSources]=useState<Sources>(initial);
  const [loading,setLoading]=useState(true);
  const [errors,setErrors]=useState<string[]>([]);
  const [loadedAt,setLoadedAt]=useState<Date|null>(null);

  async function refresh(){
    setLoading(true);
    const results=await Promise.allSettled([
      api.dashboard(),
      api.publicationReadiness(),
      api.ecommStageStatus(),
      api.mlStatus(),
      api.tiendanubeReport(),
      api.internalDecisionHistory(),
    ] as const);
    const get=<T,>(i:number):T|null=>{
      const r=results[i];
      return r.status==='fulfilled'?r.value as T:null;
    };
    setSources({
      summary:get<Summary>(0),
      readiness:get<ReadinessReport>(1),
      stage:get<EcommStageStatus>(2),
      ml:get<MercadoLibreStatus>(3),
      tn:get<Awaited<ReturnType<typeof api.tiendanubeReport>>>(4),
      history:get<Awaited<ReturnType<typeof api.internalDecisionHistory>>>(5),
    });
    setErrors(results.flatMap((r,i)=>r.status==='rejected'?
      [(['Resumen Ecomm','Revisión de productos','Copia API Ecomm','Conexión ML','CSV Tiendanube','Historial interno'][i])+' no respondió.']:[]));
    setLoadedAt(new Date());
    setLoading(false);
  }
  useEffect(()=>{void refresh()},[]);
  const excel=sourceName(sources.summary);
  const haveExcel=sources.summary?Boolean(excel):null;
  const haveReview=sources.readiness?Boolean(sources.readiness.reconciliation_run_id>0):null;
  const stageReady=sources.stage?Boolean(sources.stage.exists&&sources.stage.complete):null;
  const mlConnected=sources.ml?Boolean(sources.ml.connected&&!sources.ml.token_expired):null;
  const tnReady=sources.tn?Boolean(sources.tn.available):null;

  const example=useMemo(()=>{
    const pending=(sources.readiness?.items||[]).filter(x=>
      x.readiness_status==='REVIEW_REQUIRED' &&
      (x.reason_codes.includes('BRAND_MISSING')||x.reason_codes.includes('EAN_MISSING'))
    );
    const simple=pending.find(x=>{
      const name=String(x.product.name||'').toLocaleLowerCase();
      return (x.product.stock??0)>0 &&
        Boolean(x.product.sku_variant||x.product.sku_effective||x.product.sku)&&
        !/(pack|combo|kit|x\s*[2-9]\b|x\s*10\b)/.test(name);
    });
    return simple??pending.find(x=>Boolean(x.product.sku_variant||x.product.sku_effective||x.product.sku))??null;
  },[sources.readiness]);

  const exampleSku=example?.product.sku_variant||example?.product.sku_effective||example?.product.sku||'';
  const exampleSearch=exampleSku||example?.product.name||'';
  const exampleIssue=example?.reason_codes.includes('BRAND_MISSING')?'brand':'ean';
  const exampleHref='/work/details?focus=data&issue='+exampleIssue+(exampleSearch?'&q='+encodeURIComponent(exampleSearch):'');
  const canWalkThrough=haveExcel===true&&haveReview===true;
  return <div className="kiki-pilot">
    <header className="kiki-home-header">
      <div>
        <p className="eyebrow">KIKI TECH · PRUEBA CON EL CLIENTE</p>
        <h1>Probemos KIKI con productos reales.</h1>
        <p>Un recorrido corto para comprobar lo que funciona, mostrar los pendientes y dejar una decisión registrada. No se publica ni modifica nada en los canales de venta.</p>
      </div>
      <button className="kiki-refresh" type="button" onClick={()=>void refresh()} disabled={loading}>
        {loading?'Verificando…':'↻ Verificar nuevamente'}
      </button>
    </header>

    {errors.length>0&&<div role="alert" className="notice warning">
      <strong>Parte de la información no respondió.</strong>
      <p>{errors.join(' ')} No interpretes los datos ausentes como cero ni tomes decisiones hasta que vuelvan a cargar.</p>
    </div>}
    <section className="kiki-pilot-sources" aria-label="Estado de fuentes para la demostración">
      <h2>1. Comprobar las fuentes</h2>
      <p>Esto se consulta al abrir o actualizar la página. Los números provienen de las fuentes guardadas en KIKI, no son un stock en vivo.</p>
      <div className="kiki-pilot-source-grid">
        <article>
          <span className={'kiki-pilot-state '+sourceClass(haveExcel)}>{statusText(haveExcel)}</span>
          <strong>Catálogo Ecomm histórico</strong>
          <b>{loading?'Consultando…':haveExcel?asNum(sources.summary?.total_products):'Sin confirmar'}</b>
          <small>{excel?.filename||'No se detectó Excel operativo'}</small>
        </article>
        <article>
          <span className={'kiki-pilot-state '+sourceClass(stageReady)}>{statusText(stageReady)}</span>
          <strong>Copia API Ecomm-App</strong>
          <b>{loading?'Consultando…':sources.stage?.complete?'Copia completa':'En diagnóstico'}</b>
          <small>{sources.stage? 
            `${sources.stage.pages_saved}/${sources.stage.expected_pages??'?'} páginas guardadas · no es la fuente operativa`:
            'Copia no verificable'}</small>
        </article>
        <article>
          <span className={'kiki-pilot-state '+sourceClass(mlConnected)}>{statusText(mlConnected)}</span>
          <strong>Mercado Libre</strong>
          <b>{loading?'Consultando…':sources.ml?asNum(sources.ml.listing_count):'Sin verificar'}</b>
          <small>API {mlConnected?'conectada':'sin conexión comprobada'} · último registro: {dateLabel(sources.ml?.last_sync)}</small>
        </article>
        <article>
          <span className={'kiki-pilot-state '+sourceClass(tnReady)}>{statusText(tnReady)}</span>
          <strong>Tiendanube</strong>
          <b>{loading?'Consultando…':tnReady?asNum(sources.tn?.summary.products):'Sin verificar'}</b>
          <small>CSV guardado, no conexión en tiempo real</small>
        </article>
      </div>
      {loadedAt&&<small className="kiki-pilot-last">Estado consultado: {loadedAt.toLocaleString('es-AR')}. La conexión de Ecomm-App es de lectura; no sincroniza stock ni precios automáticamente.</small>}
    </section>

    <section className="kiki-pilot-steps" aria-label="Prueba guiada">
      <h2>2. Hacer una prueba de punta a punta</h2>
      <p>Usá un producto real conocido por Guillermo. El ejemplo se selecciona de los pendientes actuales y es una sugerencia de navegación, no una aprobación ni un diagnóstico de identidad.</p>
      <div className="kiki-pilot-steps-grid">
        <article>
          <span className="kiki-pilot-step">01 · Encontrar</span>
          <h3>Buscar un producto</h3>
          <p>Abrí Productos, buscá su SKU y revisá nombre, código, marca y estado frente a Mercado Libre.</p>
          <Link className="kiki-pilot-link" to="/products">Ir a productos →</Link>
        </article>
        <article>
          <span className="kiki-pilot-step">02 · Investigar</span>
          <h3>Resolver un dato pendiente</h3>
          {canWalkThrough&&example?<p>Ejemplo real: <strong>{example.product.name||'Producto sin nombre'}</strong> · SKU {exampleSku}. Verificá su marca o GTIN con el proveedor.</p>:
            <p>{!canWalkThrough?'Falta comprobar catálogo o conciliación antes de mostrar pendientes.':'No hay ejemplo disponible entre los pendientes consultados. Elegí una ficha desde Tareas.'}</p>}
          <Link className="kiki-pilot-link" to={canWalkThrough&&example?exampleHref:'/work/details?focus=data'}>
            {canWalkThrough&&example?'Abrir este pendiente →':'Ver tareas de datos →'}
          </Link>
        </article>
        <article>
          <span className="kiki-pilot-step">03 · Guardar y comprobar</span>
          <h3>Dejar evidencia en KIKI</h3>
          <p>Si hay una fuente verificable, guardá la evidencia como borrador. Volvé a abrir la ficha y comprobá que persista. No aceptes un dato sin haberlo comprobado.</p>
          <Link className="kiki-pilot-link" to="/work/details?focus=data">Continuar la revisión →</Link>
        </article>
        <article>
          <span className="kiki-pilot-step">04 · Ver preparación</span>
          <h3>Evaluar Mercado Libre</h3>
          <p>Mostrá por qué una publicación está lista, bloqueada o necesita revisión, y cómo se prepara internamente. Este paso <strong>no publica</strong> productos.</p>
          <Link className="kiki-pilot-link" to="/prepublication">Ver preparación ML →</Link>
        </article>
      </div>
    </section>

    <section className="kiki-pilot-summary">
      <h2>3. Qué podemos afirmar al finalizar</h2>
      <p><strong>Revisión de productos:</strong> {sources.readiness?.reconciliation_run_id?
        `${asNum(sources.readiness.summary.REVIEW_REQUIRED)} en revisión según el último análisis de preparación ML`:
        'no se pudo verificar una conciliación actual'}.{' '}
        <strong>Historial interno:</strong> {sources.history?asNum(sources.history.total)+' registros recuperables':'no disponible'}. Estos valores pertenecen a flujos distintos y no deben sumarse.</p>
      <p className="kiki-pilot-warning"><strong>Por ahora no prometemos publicación masiva ni stock sincronizado:</strong> la copia API Ecomm sigue separada del Excel operativo; los vínculos ML/GTIN y las familias SKU requieren controles. Cuando aprueben la prueba interna podremos planificar la activación por etapas.</p>
      <div className="kiki-pilot-footer-links">
        <Link to="/work">Ver todas las tareas</Link>
        <Link to="/tiendanube">Revisar Tiendanube</Link>
        <Link to="/imports">Herramientas de importación</Link>
      </div>
    </section>
  </div>;
}
