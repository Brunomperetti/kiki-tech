import React, {FormEvent, useEffect, useState} from 'react';
import ReactDOM from 'react-dom/client';
import {BrowserRouter, Route, Routes} from 'react-router-dom';
import {Layout} from './components/Layout';
import {Dashboard} from './pages/Dashboard';
import {Products} from './pages/Products';
import {Review} from './pages/Review';
import {Imports} from './pages/Imports';
import {Readiness} from './pages/Readiness';
import {Enrichment} from './pages/Enrichment';
import {ExternalResearch} from './pages/ExternalResearch';
import {api} from './services/api';
import './styles.css';

function Login({onLogin}: {onLogin: () => void}) {
  const [username, setUsername] = useState(''); const [password, setPassword] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await api.login(username, password); onLogin(); }
    catch (err) { setError(err instanceof Error ? err.message : 'No se pudo iniciar sesión.'); }
    finally { setBusy(false); }
  }
  return <main className="login-page"><section className="login-card">
    <div className="brand login-brand"><span>K</span><div>KIKI Tech<small>Acceso interno seguro</small></div></div>
    <div><p className="eyebrow">ADMINISTRACIÓN</p><h1>Bienvenido</h1><p className="muted">Ingresá para gestionar el catálogo de KIKI.</p></div>
    <form onSubmit={submit} className="login-form">
      <label>Usuario<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required autoFocus /></label>
      <label>Contraseña<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
      {error && <p className="login-error" role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? 'Verificando…' : 'Iniciar sesión'}</button>
    </form><p className="secure-note">Sesión privada · Mercado Libre en modo lectura</p>
  </section></main>;
}

function App() {
  const [state, setState] = useState<'loading'|'anonymous'|'authenticated'>('loading');
  useEffect(() => { api.me().then(() => setState('authenticated')).catch(() => setState('anonymous')); }, []);
  if (state === 'loading') return <div className="auth-loading">Verificando sesión…</div>;
  if (state === 'anonymous') return <Login onLogin={() => setState('authenticated')} />;
  return <BrowserRouter><Routes><Route element={<Layout/>}><Route path="/" element={<Dashboard/>}/><Route path="/products" element={<Products/>}/><Route path="/readiness" element={<Readiness/>}/><Route path="/enrichment" element={<Enrichment/>}/><Route path="/external-research" element={<ExternalResearch/>}/><Route path="/review" element={<Review/>}/><Route path="/imports" element={<Imports/>}/></Route></Routes></BrowserRouter>;
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
