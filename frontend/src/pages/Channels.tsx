import {useEffect,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {api} from '../services/api';
import type {MercadoLibreStatus} from '../types/catalog';
import {KikiIcon} from '../components/KikiIcon';
import '../client-ux.css';

const count=(value?:number|null)=>value==null?'—':value.toLocaleString('es-AR');
const shownDate=(value?:string|null)=>{
  if(!value)return 'Sin sincronización registrada';
  const parsed=new Date(value);
  return Number.isNaN(parsed.valueOf())?'Fecha desconocida':parsed.toLocaleString('es-AR');
};
const messageFor=(error:unknown)=>error instanceof Error?error.message:'No fue posible completar la operación.';

export function Channels(){
  const [params]=useSearchParams();
  const [ml,setMl]=useState<MercadoLibreStatus|null>(null);
  const [tn,setTn]=useState<Awaited<ReturnType<typeof api.tiendanubeReport>>|null>(null);
  const [mlAvailable,setMlAvailable]=useState(false);
  const [tnAvailable,setTnAvailable]=useState(false);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState<'connect'|'sync'|''>('');
  const [error,setError]=useState('');
  const [success,setSuccess]=useState('');
  const returnedFromMl=params.get('mercadolibre')==='connected';

  async function load(){
    setLoading(true);
    const results=await Promise.allSettled([api.mlStatus(),api.tiendanubeReport()]);
    setMl(results[0].status==='fulfilled'?results[0].value:null);
    setTn(results[1].status==='fulfilled'?results[1].value:null);
    setMlAvailable(results[0].status==='fulfilled');
    setTnAvailable(results[1].status==='fulfilled');
    if(results[0].status==='rejected')setError('No se pudo comprobar el estado de Mercado Libre. Reintentá la consulta antes de conectar.');
    setLoading(false);
  }
  useEffect(()=>{void load()},[]);
  async function connect(){
    if(busy||loading)return;
    if(!window.confirm(
      'Esta autorización debe realizarla el titular de la cuenta de Mercado Libre. '+
      'Antes de continuar, comprobá que el navegador tenga iniciada sesión en la cuenta correcta. '+
      'La autorización vinculará esa cuenta con KIKI para leer sus publicaciones; '+
      'no publicará ni modificará productos. ¿Continuar a Mercado Libre?'
    ))return;
    setBusy('connect');setError('');setSuccess('');
    try{
      const response=await api.mlAuthUrl();
      // Only the server constructs the OAuth URL; avoid an unexpected redirect.
      const target=new URL(response.url);
      if(target.protocol!=='https:'||!['auth.mercadolibre.com.ar','auth.mercadolibre.com','www.mercadolibre.com.ar','mercadolibre.com.ar'].includes(target.hostname)){
        throw new Error('La URL de autorización no es un dominio oficial esperado de Mercado Libre.');
      }
      window.location.assign(target.toString());
    }catch(e){
      setError(messageFor(e));
      setBusy('');
    }
  }
  async function sync(){
    if(busy||loading)return;
    setBusy('sync');setError('');setSuccess('');
    try{
      const result=await api.mlSync();
      await load();
      setSuccess('Copia de Mercado Libre actualizada por API: '+count(result.listing_count)+
        ' filas guardadas para diagnóstico. No se modificaron publicaciones, precios ni stock.');
    }catch(e){setError(messageFor(e))}
    finally{setBusy('')}
  }
  const connected=ml?.connected===true&&!ml.token_expired;
  return <div className="kiki-home kiki-channels-page">
    <header className="kiki-home-header"><div>
      <p className="eyebrow">KIKI TECH · CANALES</p>
      <h1>Gestioná cada canal desde un solo lugar.</h1>
      <p>Conectá las fuentes, revisá los casos y guardá las mejoras en KIKI. La publicación externa sigue protegida.</p>
    </div></header>
    {returnedFromMl&&<div className="kiki-ml-feedback" role="status">
      <KikiIcon name="check" size={19}/>
      <span>Mercado Libre devolvió la autorización. Comprobá la cuenta vinculada y después pulsá
        <strong> «Actualizar publicaciones por API»</strong> para renovar el diagnóstico.</span>
    </div>}
    <section className="kiki-channel-cards" aria-label="Canales de venta">
      <article className="kiki-channel-card" id="mercado-libre">
        <div className="kiki-channel-card-top"><div className="kiki-channel-icon" aria-hidden="true">ML</div>
          <span className={connected?'kiki-source-pill is-ok':'kiki-source-pill'}>
            {loading?'Consultando…':!mlAvailable?'Estado no disponible':connected?'Cuenta vinculada':ml?.token_expired?'Revisar conexión':'Sin conectar'}
          </span></div>
        <h2>Mercado Libre</h2>
        <p>La autorización debe completarla el titular desde su propia cuenta. Después, KIKI puede leer nuevamente las publicaciones para compararlas con Ecomm-App API.</p>
        <div className="kiki-ml-connect-panel">
          <strong><KikiIcon name="link" size={17}/> Conexión de Mercado Libre</strong>
          {connected?<p>Cuenta vinculada: <b>{ml?.user_id||'ID no disponible'}</b>.</p>:
            <p>{ml?.token_expired?'La credencial registrada necesita renovación o reconexión.':'El titular debe autorizar su cuenta para actualizar la información.'}</p>}
          <p>Última captura: {shownDate(ml?.last_sync)} · Filas: {count(ml?.listing_count)}.</p>
          <div className="kiki-channel-actions">
            <button type="button" className="kiki-main-action" disabled={loading||!!busy||!mlAvailable}
              onClick={()=>void connect()}>
              <KikiIcon name="link" size={17}/> {busy==='connect'?'Abriendo Mercado Libre…':connected?'Conectar otra vez / cambiar cuenta':'Conectar Mercado Libre'}
              <KikiIcon name="arrow-right" size={16}/>
            </button>
            <button type="button" className="secondary-link" disabled={loading||!!busy||!connected}
              onClick={()=>void sync()}>
              <KikiIcon name="refresh" size={16}/> {busy==='sync'?'Actualizando…':'Actualizar publicaciones por API'}
            </button>
          </div>
          {!connected&&<small>Ingresá a Mercado Libre con la cuenta correcta antes de autorizar. No compartas contraseñas con KIKI.</small>}
          {connected&&<small>La actualización lee el catálogo y guarda una copia interna. No edita publicaciones ni publica productos.</small>}
          {error&&<p role="alert" className="kiki-ml-error">{error}</p>}
          {success&&<p role="status" className="kiki-ml-success">{success}</p>}
        </div>
        <div className="kiki-channel-actions">
          <Link className="kiki-main-action" to="/cases"><KikiIcon name="chart" size={16}/> Revisar casos reales <span aria-hidden="true">→</span></Link>
        </div>
        <small>Las coincidencias entre SKU son candidatas: requieren verificar presentaciones y vinculaciones antes de tomar decisiones.</small>
      </article>
      <article className="kiki-channel-card">
        <div className="kiki-channel-card-top"><div className="kiki-channel-icon" aria-hidden="true">TN</div>
          <span className={tn?.available?'kiki-source-pill is-ok':'kiki-source-pill'}>
            {loading?'Consultando…':!tnAvailable?'Estado no disponible':tn?.available?'CSV y Ecomm API':'Revisar fuentes'}</span></div>
        <h2>Tiendanube</h2>
        <p>Contrastá el CSV de Tiendanube con Ecomm-App API. Revisá precios, stock capturado y propuestas de contenido comercial.</p>
        <div className="kiki-channel-metric">{tn?.available?count(tn.summary.products):'—'} <small>productos del CSV importado</small></div>
        <div className="kiki-channel-actions">
          <Link className="kiki-main-action" to="/tiendanube?control=precios#comparar-precios">
            <KikiIcon name="chart" size={16}/> Comparar precios y stock <span aria-hidden="true">→</span>
          </Link>
          <Link className="secondary-link" to="/tiendanube">Otras herramientas de Tiendanube</Link>
        </div>
        <small>Las fichas editadas se guardan en KIKI. Todavía no se transfieren automáticamente a Tiendanube.</small>
      </article>
    </section>
    <section className="kiki-channel-help">
      <div><p className="eyebrow">TRABAJO OPERATIVO</p><h2>De detectar un problema a guardar la solución</h2>
        <p>Identificá el caso, verificá el producto y abrí su ficha para corregir marca, título y descripción. «Guardar borrador» o «Enviar a revisión interna» conservan los cambios en PostgreSQL de KIKI. Ninguno actualiza canales externos.</p>
      </div>
      <Link className="secondary-link" to="/workspace">Mejorar y guardar fichas →</Link>
    </section>
  </div>;
}
