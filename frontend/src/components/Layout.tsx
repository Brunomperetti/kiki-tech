import {NavLink,Outlet} from 'react-router-dom';
import {api} from '../services/api';

export function Layout(){
  async function logout(){await api.logout();window.location.assign('/')}
  return <div className="shell"><aside>
    <div className="brand"><span>K</span><div>KIKI Tech<small>Centro de control</small></div></div>

    <nav className="primary-nav">
      <NavLink to="/">Inicio</NavLink>
      <NavLink to="/work">Resolver pendientes</NavLink>
      <NavLink to="/readiness">Vincular con ML</NavLink>
      <NavLink to="/prepublication">Publicar en ML</NavLink>
      <NavLink to="/tiendanube">Tiendanube</NavLink>
    </nav>

    <details className="advanced-nav">
      <summary>Herramientas avanzadas</summary>
      <nav>
        <NavLink to="/products">Productos</NavLink>
        <NavLink to="/enrichment">Enriquecimiento</NavLink>
        <NavLink to="/external-research">Investigación externa</NavLink>
        <NavLink to="/images">Imágenes</NavLink>
        <NavLink to="/metadata">Categoría y atributos</NavLink>
        <NavLink to="/review">Revisión de coincidencias</NavLink>
        <NavLink to="/duplicate-review">Duplicados Ecomm</NavLink>
        <NavLink to="/imports">Importaciones</NavLink>
      </nav>
    </details>

    <div className="readonly">● Modo seguro<br/><small>Sin cambios externos</small></div>
    <button className="logout" onClick={logout}>Cerrar sesión</button>
  </aside><main><Outlet/></main></div>
}
