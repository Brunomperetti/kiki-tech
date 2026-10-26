import {useEffect,useState} from 'react';
import {Link,NavLink,Outlet,useLocation} from 'react-router-dom';
import '../guide.css';
import {api} from '../services/api';
import {KikiIcon} from './KikiIcon';

const advancedPaths = ['/products','/work','/work/details','/enrichment',
  '/external-research','/images','/metadata','/review','/duplicate-review',
  '/imports','/readiness','/prepublication','/tiendanube'];


type ContextHelp={title:string;steps:string[];reminder:string};
const contextHelp=(pathname:string):ContextHelp=>{
  if(pathname==='/workspace')return {
    title:'Mejorar productos · cómo guardar',
    steps:[
      'Buscá el SKU o abrí una ficha guardada.',
      'Revisá las sugerencias; «Usar este título» todavía NO guarda.',
      'Pulsá «Guardar borrador» y comprobá el historial.'
    ],
    reminder:'Sin pulsar Guardar borrador o Enviar a revisión interna, la ficha no conserva los cambios nuevos.'
  };
  if(pathname==='/queue')return {
    title:'Cola de mejoras · cómo empezar',
    steps:[
      'Elegí el filtro «Simples aptos para IA» o «Borradores».',
      'Marcá hasta tres variantes simples y prepará la selección gratis.',
      'Generá IA solo si aceptás consumir solicitudes; luego revisá cada propuesta y guardá la ficha.'
    ],
    reminder:'Seleccionar o generar IA no equivale a guardar la ficha comercial.'
  };
  if(pathname==='/pilot')return {
    title:'Catálogo por API · qué muestra',
    steps:['Buscá SKU, ID o nombre del producto.','Comprobá cuándo fue capturado el catálogo.',
      'Podés consultar un SKU en vivo sin actualizar el stock guardado.'],
    reminder:'La copia API no es un inventario sincronizado en tiempo real.'
  };
  if(pathname==='/cases'||pathname==='/channels')return {
    title:'Canales · cómo interpretarlos',
    steps:['Ecomm-App es la fuente principal de identidad por API.',
      'Mercado Libre usa su última captura mientras no se reautorice la cuenta.',
      'Tiendanube conserva datos CSV importados.'],
    reminder:'Ni las coincidencias ni los borradores confirman una publicación o modifican los canales.'
  };
  return {
    title:'KIKI Tech · primeros pasos',
    steps:['Empezá por la Cola de mejoras para encontrar tareas.',
      'Usá Mejorar productos para editar y guardar en KIKI.',
      'Consultá la Guía interactiva si no sabés por dónde continuar.'],
    reminder:'Los cambios editoriales se guardan en KIKI PostgreSQL, no en Ecomm-App, ML ni Tiendanube.'
  };
};

export function Layout(){
  const location=useLocation();
  const [helpOpen,setHelpOpen]=useState(false);
  const help=contextHelp(location.pathname);
  useEffect(()=>{setHelpOpen(false)},[location.pathname]);
  useEffect(()=>{
    if(!helpOpen)return;
    const onKey=(event:KeyboardEvent)=>{if(event.key==='Escape')setHelpOpen(false)};
    window.addEventListener('keydown',onKey);
    return ()=>window.removeEventListener('keydown',onKey);
  },[helpOpen]);
  const activeAdvanced=advancedPaths.includes(location.pathname);
  async function logout(){await api.logout();window.location.assign('/')}
  return <div className="shell kiki-shell">
    <aside className="kiki-sidebar">
      <NavLink className="brand kiki-brand" to="/" aria-label="KIKI Tech - Inicio">
        <span>K</span><div>KIKI Tech<small>Gestión inteligente del catálogo</small></div>
      </NavLink>
      <p className="kiki-nav-kicker">TU ESPACIO DE TRABAJO</p>
      <nav className="primary-nav kiki-primary-nav" aria-label="Navegación principal">
        <NavLink to="/" end><span className="kiki-nav-icon"><KikiIcon name="home"/></span>Inicio</NavLink>
        <NavLink to="/pilot"><span className="kiki-nav-icon"><KikiIcon name="layers"/></span>Catálogo por API</NavLink>
        <NavLink to="/workspace"><span className="kiki-nav-icon"><KikiIcon name="check"/></span>Mejorar productos</NavLink>
        <NavLink to="/queue"><span className="kiki-nav-icon"><KikiIcon name="chart"/></span>Cola de mejoras</NavLink>
        <NavLink to="/cases"><span className="kiki-nav-icon"><KikiIcon name="search"/></span>Casos para revisar</NavLink>
        <NavLink to="/channels"><span className="kiki-nav-icon"><KikiIcon name="store"/></span>Canales de venta</NavLink>
        <NavLink to="/guia"><span className="kiki-nav-icon"><KikiIcon name="help"/></span>Guía para usar KIKI</NavLink>
      </nav>
      <details className="advanced-nav kiki-advanced-nav" key={activeAdvanced?'opened':'closed'}
        open={activeAdvanced?true:undefined}>
        <summary><KikiIcon name="archive" size={17}/> Herramientas y datos históricos</summary>
        <p className="kiki-nav-note">Estas pantallas todavía usan datos importados y no equivalen al catálogo API.</p>
        <nav aria-label="Herramientas avanzadas y datos históricos">
          <NavLink to="/products">Productos históricos (Excel)</NavLink>
          <NavLink to="/work">Tareas históricas (Excel)</NavLink>
          <NavLink to="/work/details">Revisión detallada histórica</NavLink>
          <NavLink to="/readiness">Vinculación histórica ML</NavLink>
          <NavLink to="/prepublication">Preparación histórica ML</NavLink>
          <NavLink to="/tiendanube">Tiendanube (CSV)</NavLink>
          <NavLink to="/enrichment">Marcas y datos históricos</NavLink>
          <NavLink to="/external-research">Investigación externa</NavLink>
          <NavLink to="/images">Imágenes</NavLink>
          <NavLink to="/metadata">Categorías y atributos</NavLink>
          <NavLink to="/review">Coincidencias históricas</NavLink>
          <NavLink to="/duplicate-review">Duplicados históricos</NavLink>
          <NavLink to="/imports">Importaciones y diagnóstico</NavLink>
        </nav>
      </details>
      <div className="kiki-sidebar-footer">
        <div className="readonly"><KikiIcon name="shield" size={17}/> <strong>Modo de consulta</strong>
          <small>KIKI no publica ni modifica stock de los canales desde las nuevas pantallas API.</small>
        </div>
        <button className="logout" onClick={logout}>Cerrar sesión</button>
      </div>
    </aside>
    <main id="main-content"><Outlet/></main>
    <button type="button" className="kiki-help-button" aria-expanded={helpOpen}
      aria-controls="kiki-context-help"
      onClick={()=>setHelpOpen(value=>!value)}>
      <KikiIcon name="help" size={20}/> {helpOpen?'Cerrar ayuda':'¿Necesitás ayuda?'}
    </button>
    {helpOpen&&<section id="kiki-context-help" className="kiki-help-popup"
      aria-label="Ayuda para esta pantalla">
      <header><h2>{help.title}</h2>
        <button aria-label="Cerrar ayuda" type="button" onClick={()=>setHelpOpen(false)}>
          ×
        </button></header>
      <ol>{help.steps.map(line=><li key={line}>{line}</li>)}</ol>
      <div className="kiki-help-popup-badge">{help.reminder}</div>
      <Link to="/guia"><KikiIcon name="help" size={16}/> Abrir guía completa
        <KikiIcon name="arrow-right" size={15}/></Link>
    </section>}
  </div>;
}
