import { useEffect, useState, type FormEvent } from 'react'
import { api, setToken, type User } from '../api'
import { useBrand } from '../App'

const ORDER = ['head', 'rb', 'ro', 'committee', 'ec', 'institution', 'admin']
const ROLE: Record<string, string> = {
  head: 'Senior management', rb: 'Regulation Bureau', ro: 'Regional Office', committee: 'Expert committee member',
  ec: 'Executive Committee', institution: 'Institution', admin: 'Administrator',
}

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const brand = useBrand()
  const [users, setUsers] = useState<any[]>([])
  const [id, setId] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { api('/api/demo-users').then(setUsers).catch(() => {}) }, [])
  const signIn = async (user: string, password: string) => {
    setBusy(true); setErr('')
    try {
      const r = await api<{ token: string; user: User }>('/api/login', { method: 'POST', json: { user, password } })
      setToken(r.token); onLogin(r.user)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); if (id.trim() && pw) signIn(id, pw) }
  const sorted = [...users].sort((a, b) => ORDER.indexOf(a.role) - ORDER.indexOf(b.role))
  return (
    <div className="signin">
      <form className="box signin-card" onSubmit={submit}>
        <div className="bb">
          <h1 style={{ marginBottom: 16 }}>Sign in to {brand.name}</h1>
          <label className="fld">User ID<input autoFocus value={id} onChange={(e) => setId(e.target.value)} placeholder="User ID, or Permanent ID for institutions" autoComplete="username" /></label>
          <label className="fld">Password<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" /></label>
          {err && <div className="note bad" style={{ marginBottom: 10 }}>{err}</div>}
          <button className="btn primary block" disabled={busy || !id.trim() || !pw}>Sign in</button>
        </div>
      </form>
      {sorted.length > 0 && <div className="box signin-card">
        <div className="bh"><h2>Demo accounts</h2></div>
        {sorted.map((u) => <button key={u.id} className="acct" onClick={() => signIn(u.id, 'demo')} disabled={busy}>
          <span><b>{u.name}</b><span className="small muted"> · {u.role === 'ro' ? `Regional Office, ${u.region}` : ROLE[u.role]}</span></span>
          <span className="mono small faint" style={{ whiteSpace: 'nowrap' }}>{u.login}</span>
        </button>)}
      </div>}
    </div>
  )
}
