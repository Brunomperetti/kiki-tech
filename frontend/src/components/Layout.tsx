import {NavLink,Outlet,useLocation} from 'react-router-dom';
import {api} from '../services/api';

const channelPaths = ['/channels', '/readiness', '/prepublication', '/tiendanube'];

export function Layout(){
  const location = useLocation();
  const channelActive = channelPaths.includes(location.pathname);
  const tasksActive = location.pathname === '/work/details';
  const advancedPaths = ['/enrichment','/external-research','/images','/metadata','/review','/duplicate-review','/imports'];
  const advancedActive = advancedPaths.includes(location.pathname);

  async function logout(){await api.logout();window.location.assign('/')}
  return <div className="shell kiki-shell">
    <aside className="kiki-sidebar">
      <NavLink className="brand kiki-brand" to="/" aria-label="KIKI Tech - Inicio"><span>K</span><div>KIKI Tech<small>Centro de operaciones</small></div></NavLink>
      <p className="kiki-nav-kicker">TRABAJO DIARIO</p>
      <nav className="primary-nav kiki-primary-nav" aria-label="Navegación principal">
        <NavLink to="/" end><span className="kiki-nav-icon" aria-hidden="true">⌂</span>Inicio</NavLink>
        <NavLink to="/products"><span className="kiki-nav-icon" aria-hidden="true">▦</span>Productos</NavLink>
        <NavLink to="/work" className={({isActive})=>isActive||tasksActive?'active':''}><span className="kiki-nav-icon" aria-hidden="true">✓</span>Tareas</NavLink>
        <NavLink to="/channels" className={({isActive})=>isActive||channelActive?'active':''}><span className="kiki-nav-icon" aria-hidden="true">◫</span>Canales de venta</NavLink>
      </nav>

      <details className="advanced-nav kiki-advanced-nav" key={advancedActive?'advanced-current':'advanced-other'} open={advancedActive?true:undefined}>
        <summary>Herramientas y configuración</summary>
        <nav aria-label="Herramientas avanzadas">
          <NavLink to="/work/details">Revisión detallada</NavLink>
          <NavLink to="/imports">Importar archivos</NavLink>
          <NavLink to="/readiness">Vincular con Mercado Libre</NavLink>
          <NavLink to="/prepublication">Preparar para Mercado Libre</NavLink>
          <NavLink to="/tiendanube">Revisar Tiendanube</NavLink>
          <NavLink to="/enrichment">Enriquecimiento de datos</NavLink>
          <NavLink to="/external-research">Investigación externa</NavLink>
          <NavLink to="/images">Imágenes</NavLink>
          <NavLink to="/metadata">Categorías y atributos</NavLink>
          <NavLink to="/review">Revisión de coincidencias</NavLink>
          <NavLink to="/duplicate-review">Duplicados de Ecomm</NavLink>
        </nav>
      </details>

      <div className="kiki-sidebar-footer">
        <div className="readonly"><span className="kiki-status-dot" aria-hidden="true"/> Modo seguro<small>Las aprobaciones son internas. No se publican productos automáticamente.</small></div>
        <button className="logout" onClick={logout}>Cerrar sesión</button>
      </div>
    </aside>
    <main id="main-content"><Outlet/></main>
  </div>
}
