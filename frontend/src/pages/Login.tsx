import { useEffect, useState } from 'react'
import { api, setToken, type User } from '../api'

const ROLE: Record<string, string> = {
  scrutiny_officer: 'Reviews applications and records decisions', verifier: 'Confirms documents with issuing offices',
  admin: 'Manages rules and verification sources',
}

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [d, setD] = useState<any>(null)
  const [inst, setInst] = useState('')
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/demo-users').then((x) => { setD(x); setInst(x.institutions[0]?.permanent_id || '') }) }, [])
  const go = async (id: string) => {
    try {
      const r = await api<{ token: string; user: User }>('/api/login', { method: 'POST', json: { user: id } })
      setToken(r.token); onLogin(r.user)
    } catch (e: any) { setErr(e.message) }
  }
  return (
    <div className="login">
      <div className="box">
        <div className="bh"><h2>Sign in</h2><span className="small faint">demo accounts</span></div>
        <div className="bb">
          <h3 style={{ marginBottom: 8 }}>AICTE staff</h3>
          {d?.staff.map((s: any) => (
            <button key={s.id} className="choice" onClick={() => go(s.id)}>
              <b>{s.name}</b> · {s.title}<div className="small faint">{ROLE[s.role]}</div>
            </button>
          ))}
          <h3 style={{ margin: '16px 0 8px' }}>Institution</h3>
          <div className="row">
            <select value={inst} onChange={(e) => setInst(e.target.value)} style={{ flex: 1, minWidth: 280 }}>
              {d?.institutions.map((i: any) => <option key={i.permanent_id} value={i.permanent_id}>{i.name}</option>)}
            </select>
            <button className="btn primary" onClick={() => go('inst:' + inst)} disabled={!inst}>Sign in</button>
          </div>
          {err && <div className="note bad" style={{ marginTop: 10 }}>{err}</div>}
        </div>
      </div>
      <p className="small faint" style={{ textAlign: 'center' }}>Automated results are advisory. Decisions are taken by authorised officials.</p>
    </div>
  )
}
