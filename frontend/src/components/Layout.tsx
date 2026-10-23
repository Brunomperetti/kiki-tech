import {NavLink,Outlet,useLocation} from 'react-router-dom';
import {api} from '../services/api';
import {KikiIcon} from './KikiIcon';

const advancedPaths = ['/products','/work','/work/details','/enrichment',
  '/external-research','/images','/metadata','/review','/duplicate-review',
  '/imports','/readiness','/prepublication','/tiendanube'];

export function Layout(){
  const location=useLocation();
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
        <NavLink to="/cases"><span className="kiki-nav-icon"><KikiIcon name="search"/></span>Casos para revisar</NavLink>
        <NavLink to="/channels"><span className="kiki-nav-icon"><KikiIcon name="store"/></span>Canales de venta</NavLink>
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
  </div>;
}
