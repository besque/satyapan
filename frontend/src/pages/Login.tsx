import { useEffect, useState } from 'react'
import { api, setToken, type User } from '../api'

const ROLE: Record<string, string> = {
  officer: 'Handles the cases of the bureau; sees what other bureaus are doing on the same institution',
  management: 'Sees every bureau and region; receives escalations and conflict alerts',
  admin: 'Sets timelines, escalation and matching rules',
}

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [users, setUsers] = useState<any[]>([])
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/demo-users').then(setUsers) }, [])
  const go = async (id: string) => {
    try {
      const r = await api<{ token: string; user: User }>('/api/login', { method: 'POST', json: { user: id } })
      setToken(r.token); onLogin(r.user)
    } catch (e: any) { setErr(e.message) }
  }
  const group = (role: string) => users.filter((u) => u.role === role)
  return (
    <div className="login">
      <div className="box">
        <div className="bh"><h2>Sign in</h2><span className="small faint">demo accounts</span></div>
        <div className="bb">
          {(['officer', 'management', 'admin'] as const).map((r) => group(r).length > 0 && <div key={r} style={{ marginBottom: 12 }}>
            <h3 style={{ marginBottom: 8 }}>{r === 'officer' ? 'Bureau / Cell officers' : r === 'management' ? 'Senior management' : 'Administration'}</h3>
            {group(r).map((s) => (
              <button key={s.id} className="choice" onClick={() => go(s.id)}>
                {s.bureau && <span className={`bz b-${s.bureau}`} style={{ marginRight: 8 }}>{s.bureau}</span>}<b>{s.name}</b> · {s.title}
                <div className="small faint">{ROLE[s.role]}</div>
              </button>
            ))}
          </div>)}
          {err && <div className="note bad" style={{ marginTop: 10 }}>{err}</div>}
        </div>
      </div>
      <p className="small faint" style={{ textAlign: 'center' }}>Automated alerts are advisory. Actions and decisions are taken by authorised officials.</p>
    </div>
  )
}
