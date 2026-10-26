import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api} from '../services/api';
import type {MercadoLibreStatus} from '../types/catalog';
import {KikiIcon} from '../components/KikiIcon';
import '../client-ux.css';

const count=(value?:number|null)=>value==null?'—':value.toLocaleString('es-AR');

export function Channels(){
  const [ml,setMl]=useState<MercadoLibreStatus|null>(null);
  const [tn,setTn]=useState<Awaited<ReturnType<typeof api.tiendanubeReport>>|null>(null);
  const [mlAvailable,setMlAvailable]=useState(false);
  const [tnAvailable,setTnAvailable]=useState(false);
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    let active=true;
    Promise.allSettled([api.mlStatus(),api.tiendanubeReport()]).then(results=>{
      if(!active)return;
      setMl(results[0].status==='fulfilled'?results[0].value:null);
      setTn(results[1].status==='fulfilled'?results[1].value:null);
      setMlAvailable(results[0].status==='fulfilled');
      setTnAvailable(results[1].status==='fulfilled');
      setLoading(false);
    });
    return ()=>{active=false};
  },[]);

  return <div className="kiki-home kiki-channels-page">
    <header className="kiki-home-header"><div>
      <p className="eyebrow">KIKI TECH · CANALES</p>
      <h1>Gestioná cada canal desde un solo lugar.</h1>
      <p>Elegí qué querés hacer. KIKI separa las revisiones internas de los cambios reales en las tiendas.</p>
    </div></header>
    <section className="kiki-channel-cards" aria-label="Canales de venta">
      <article className="kiki-channel-card">
        <div className="kiki-channel-card-top"><div className="kiki-channel-icon" aria-hidden="true">ML</div><span className={ml?.connected&&!ml.token_expired?'kiki-source-pill is-ok':'kiki-source-pill'}>{loading?'Consultando…':!mlAvailable?'Estado no disponible':ml?.connected&&!ml?.token_expired?'API conectada':ml?.token_expired?'Reconectar API':'API sin conectar'}</span></div>
        <h2>Mercado Libre</h2>
        <p>Compará Ecomm-App y Mercado Libre desde sus copias API. Los resultados son candidatos para revisión: no se aplican vínculos ni publicaciones.</p>
        <div className="kiki-channel-actions">
          <Link className="kiki-main-action" to="/cases"><KikiIcon name="chart" size={16}/> Revisar casos reales <span aria-hidden="true">→</span></Link>
          <Link className="secondary-link" to="/readiness">Consultar revisión histórica (Excel)</Link>
        </div>
        <small>Mercado Libre necesita una nueva autorización del dueño para actualizar su copia. Hasta entonces, se muestran resultados históricos.</small>
      </article>
      <article className="kiki-channel-card">
        <div className="kiki-channel-card-top"><div className="kiki-channel-icon" aria-hidden="true">TN</div><span className={tn?.available?'kiki-source-pill is-ok':'kiki-source-pill'}>{loading?'Consultando…':!tnAvailable?'Estado no disponible':tn?.available?'CSV importado':'Sin catálogo CSV'}</span></div>
        <h2>Tiendanube</h2>
        <p>Contrastá productos y revisá las sugerencias de títulos y descripciones de KIKI AI.</p>
        <div className="kiki-channel-metric">{tn?.available?count(tn.summary.products):'—'} <small>productos del CSV importado</small></div>
        <div className="kiki-channel-actions">
          <Link className="kiki-main-action" to="/tiendanube?control=precios#comparar-precios">
            <KikiIcon name="chart" size={16}/> Comparar precios y stock <span aria-hidden="true">→</span>
          </Link>
          <Link className="secondary-link" to="/tiendanube">Otras herramientas de Tiendanube</Link>
        </div>
        <small>Se trabaja sobre datos importados; no se actualiza la tienda automáticamente.</small>
      </article>
    </section>
    <section className="kiki-channel-help">
      <div><p className="eyebrow">¿NECESITÁS ACTUALIZAR LA INFORMACIÓN?</p><h2>Primero cargá las fuentes</h2><p>Ecomm-App se consulta mediante su API. Mercado Libre utiliza una copia API guardada y Tiendanube conserva un CSV importado. Ninguno debe confundirse con stock en tiempo real.</p></div>
      <Link className="secondary-link" to="/pilot#fuentes">Ver estado de fuentes API →</Link>
    </section>
  </div>;
}
