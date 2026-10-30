export type User = { id: string; name: string; role: string; title?: string; region?: string; pid?: string; offices?: string[] }
export type Brand = { name: string; name_local?: string; tagline: string; meaning?: string }

const KEY = 'approval.token'
function lsGet(k: string): string | null {
  try { return localStorage.getItem(k) } catch { return null }
}
function lsSet(k: string, v: string | null) {
  try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch { /* private mode */ }
}
let token: string | null = lsGet(KEY)

export function setToken(t: string | null) { token = t; lsSet(KEY, t) }
export function getToken() { return token }

export class ApiError extends Error {
  status: number
  constructor(status: number, body: any) { super(typeof body?.detail === 'string' ? body.detail : `HTTP ${status}`); this.status = status }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: any } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) }
  if (token) headers['X-Token'] = token
  let body = opts.body
  if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.json) }
  const r = await fetch(path, { ...opts, headers, body })
  const txt = await r.text()
  let data: any = null
  try { data = txt ? JSON.parse(txt) : null } catch { data = { detail: txt } }
  if (!r.ok) throw new ApiError(r.status, data)
  return data as T
}

export async function upload(file: File): Promise<{ id: string; name: string }> {
  const fd = new FormData()
  fd.append('file', file)
  return api('/api/files', { method: 'POST', body: fd })
}

/** Links that download (CSV, files) carry the token as a query parameter. */
export const withToken = (path: string) => `${path}${path.includes('?') ? '&' : '?'}t=${encodeURIComponent(token || '')}`
