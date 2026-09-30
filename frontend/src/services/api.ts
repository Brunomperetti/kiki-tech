import type {EnrichmentReport, ImportJob, MercadoLibreStatus, ReadinessReport, Result, Summary} from '../types/catalog';

const base = import.meta.env.VITE_API_URL || 'http://localhost:8000';
let csrfToken = '';

type AuthResponse = {authenticated: boolean; username: string; csrf_token: string};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (method !== 'GET' && method !== 'HEAD' && path !== '/api/auth/login') {
    headers.set('X-CSRF-Token', csrfToken);
  }
  const response = await fetch(`${base}${path}`, {...options, headers, credentials: 'include'});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'No pudimos completar la operación.');
  }
  return response.json();
}

function rememberAuth(auth: AuthResponse): AuthResponse {
  csrfToken = auth.csrf_token;
  return auth;
}

export const api = {
  me: () => request<AuthResponse>('/api/auth/me').then(rememberAuth),
  login: (username: string, password: string) => request<AuthResponse>('/api/auth/login', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password}),
  }).then(rememberAuth),
  logout: () => request<{authenticated: boolean}>('/api/auth/logout', {method: 'POST'}).finally(() => { csrfToken = ''; }),
  dashboard: () => request<Summary>('/api/dashboard'),
  products: (query = '') => request<Result[]>(`/api/products${query}`),
  publicationReadiness: () => request<ReadinessReport>('/api/publication-readiness'),
  enrichmentPilot: (limit = 20) => request<EnrichmentReport>(`/api/enrichment-pilot?limit=${limit}`),
  imports: () => request<ImportJob[]>('/api/imports'),
  analyze: (source = 'AUTO') => request<unknown>(`/api/reconciliations?ml_source=${source}`, {method: 'POST'}),
  mlStatus: () => request<MercadoLibreStatus>('/api/mercadolibre/status'),
  mlAuthUrl: () => request<{url: string}>('/api/mercadolibre/auth-url', {method: 'POST'}),
  mlSync: () => request<{listing_count: number; synced_at: string}>('/api/mercadolibre/sync', {method: 'POST'}),
  upload: (source: string, file: File) => {
    const data = new FormData(); data.append('file', file);
    return request(`/api/imports/${source}`, {method: 'POST', body: data});
  },
};
