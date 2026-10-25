export type User = { id: string; name: string; role: string; title?: string; permanent_id?: string }

let token: string | null = localStorageGet('satyapan.token')

function localStorageGet(k: string): string | null {
  try { return localStorage.getItem(k) } catch { return null }
}
function localStorageSet(k: string, v: string | null) {
  try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* private mode */ }
}

export function setToken(t: string | null) { token = t; localStorageSet('satyapan.token', t) }
export function getToken() { return token }

export class ApiError extends Error {
  status: number; body: any
  constructor(status: number, body: any) { super(typeof body?.detail === 'string' ? body.detail : (body?.detail?.message || `HTTP ${status}`)); this.status = status; this.body = body }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: any } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) }
  if (token) headers['X-Token'] = token
  let body = opts.body
  if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.json) }
  const r = await fetch(path, { ...opts, headers, body })
  const txt = await r.text()
  const data = txt ? JSON.parse(txt) : null
  if (!r.ok) throw new ApiError(r.status, data)
  return data as T
}

/** URLs for <img> need the token as a query parameter. */
export const img = (path: string) => `${path}${path.includes('?') ? '&' : '?'}t=${encodeURIComponent(token || '')}`
