import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {
  FinalPublicationQueueReport,
  InventoryLinkageReport,
} from '../types/catalog';
import type {ReconciliationReviewQueue} from '../types/reconciliation-review';
import type {DuplicateReviewQueue} from '../types/duplicate-review';

type PendingState={
  linkage:InventoryLinkageReport|null;
  reconciliation:ReconciliationReviewQueue|null;
  duplicates:DuplicateReviewQueue|null;
  finalQueue:FinalPublicationQueueReport|null;
};

export function WorkQueue(){
  const [data,setData]=useState<PendingState>({linkage:null,reconciliation:null,duplicates:null,finalQueue:null});
  const [error,setError]=useState('');

  useEffect(()=>{
    Promise.allSettled([
      api.inventoryLinkage(),
      api.reconciliationReviewQueue(),
      api.duplicateReviewQueue(),
      api.finalPublicationQueue(),
    ]).then(results=>{
      setData({
        linkage:results[0].status==='fulfilled'?results[0].value:null,
        reconciliation:results[1].status==='fulfilled'?results[1].value:null,
        duplicates:results[2].status==='fulfilled'?results[2].value:null,
        finalQueue:results[3].status==='fulfilled'?results[3].value:null,
      });
      if(results.some(result=>result.status==='rejected')){
        setError('Algunos contadores no pudieron cargarse. Podés seguir trabajando con los disponibles.');
      }
    });
  },[]);

  const linkagePending=data.linkage?.summary.review_required??0;
  const pendingEcomm=data.linkage?.summary.pending_ecomm_catalog??0;
  const reconciliationPending=data.reconciliation?.summary.PENDING??0;
  const duplicatePending=data.duplicates?.summary.PENDING??0;
  const finalReady=data.finalQueue?.summary.READY_FOR_FINAL_REVIEW??0;
  const finalChanged=data.finalQueue?.summary.STALE_APPROVAL??0;
  const totalPending=linkagePending+pendingEcomm+reconciliationPending+duplicatePending+finalReady+finalChanged;

  return <>
    <header><div><p className="eyebrow">TRABAJO PENDIENTE</p><h1>Resolver pendientes</h1><p>KIKI ordena lo que necesita una decisión humana. No hace falta recorrer todos los módulos.</p></div></header>
    {error&&<div className="notice warning">{error}</div>}

    <section className="guided-hero">
      <div><span>Pendientes visibles</span><strong>{totalPending.toLocaleString('es-AR')}</strong><p>Trabajá de arriba hacia abajo. KIKI te lleva al lugar correcto.</p></div>
    </section>

    <section className="guided-work-list">
      <article className="guided-work-card">
        <div className="guided-step-number">1</div>
        <div className="guided-work-copy"><h2>Vincular publicaciones con Ecomm</h2><p>Publicaciones que ya existen en Mercado Libre pero todavía necesitan identificación, revisión o una acción en el catálogo Ecomm.</p><div className="guided-metrics"><span>Revisión <strong>{linkagePending}</strong></span><span>Pendientes Ecomm <strong>{pendingEcomm}</strong></span></div></div>
        <Link className="guided-link" to="/readiness">Continuar</Link>
      </article>

      <article className="guided-work-card">
        <div className="guided-step-number">2</div>
        <div className="guided-work-copy"><h2>Resolver coincidencias dudosas</h2><p>Casos donde KIKI encontró una posible relación entre producto y publicación, pero necesita confirmación humana.</p><div className="guided-metrics"><span>Por revisar <strong>{reconciliationPending}</strong></span></div></div>
        <Link className="guided-link" to="/review">Revisar</Link>
      </article>

      <article className="guided-work-card">
        <div className="guided-step-number">3</div>
        <div className="guided-work-copy"><h2>Revisar posibles duplicados</h2><p>Productos de Ecomm que comparten identificadores y podrían ser duplicados, variantes o productos distintos.</p><div className="guided-metrics"><span>Grupos pendientes <strong>{duplicatePending}</strong></span></div></div>
        <Link className="guided-link" to="/duplicate-review">Revisar</Link>
      </article>

      <article className="guided-work-card">
        <div className="guided-step-number">4</div>
        <div className="guided-work-copy"><h2>Aprobar productos para el lote ML</h2><p>Productos que ya pasaron controles y están esperando aprobación final, o cuya información cambió después de una aprobación.</p><div className="guided-metrics"><span>Para aprobar <strong>{finalReady}</strong></span><span>Cambiaron <strong>{finalChanged}</strong></span></div></div>
        <Link className="guided-link" to="/prepublication">Ir a publicar en ML</Link>
      </article>
    </section>

    <section className="panel guided-help">
      <h2>Regla simple</h2>
      <p><strong>Si ya existe en Mercado Libre:</strong> trabajalo en “Vincular con ML”. <strong>Si todavía no existe:</strong> trabajalo en “Publicar en ML”. KIKI mantiene separados los dos circuitos.</p>
    </section>
  </>;
}
