import { useEffect, useState } from 'react'
import { api } from '../api'
import { useUser } from '../App'
import { ClauseModal, Tip } from '../ui'

const SEV: Record<string, string> = { critical: 'High', high: 'High', medium: 'Medium', low: 'Low' }

export default function Rules() {
  const user = useUser()
  const [rs, setRs] = useState<any>(null)
  const [cite, setCite] = useState<any>(null)
  const [edit, setEdit] = useState<string | null>(null)
  const [params, setParams] = useState('')
  const [reason, setReason] = useState('')
  const [err, setErr] = useState('')
  const load = () => api('/api/rules').then(setRs)
  useEffect(() => { load() }, [])
  const admin = user.role === 'admin'
  const save = async (r: any, patch: any) => {
    setErr('')
    try { await api(`/api/rules/${r.id}`, { method: 'PUT', json: { ...patch, reason } }); setEdit(null); setReason(''); load() } catch (e: any) { setErr(e.message) }
  }
  return (
    <div>
      <div className="titlebar"><div><h1>Rules <Tip>Each check comes from the AICTE Approval Process Handbook 2024-27. Click a clause to open the handbook page.{admin ? ' Changes are recorded in the activity log.' : ''}</Tip></h1>
        <div className="sub">{rs?.rules.length} checks · Approval Process Handbook 2024-27</div></div></div>
      {err && <div className="note bad">{err}</div>}
      <div className="box">
        <div className="tablewrap"><table className="t">
          <thead><tr><th>Check</th><th>Importance</th><th>Handbook clause</th>{admin && <th>Settings</th>}</tr></thead>
          <tbody>{rs?.rules.map((r: any) => <tr key={r.id} style={{ opacity: r.enabled ? 1 : 0.5 }}>
            <td>{r.title}{!r.enabled && <span className="pill grey" style={{ marginLeft: 6 }}>Off</span>}</td>
            <td className="small">{SEV[r.severity]}</td>
            <td><button className="btn sm" onClick={() => setCite({ ...r.cite, loc: r.cite_loc })}>{r.cite.ref}</button></td>
            {admin && <td style={{ minWidth: 220 }}>{edit === r.id ? <div className="grid" style={{ gap: 6 }}>
              <textarea className="mono" value={params} onChange={(e) => setParams(e.target.value)} />
              <input placeholder="Reason for change" value={reason} onChange={(e) => setReason(e.target.value)} />
              <div className="row"><button className="btn sm primary" disabled={reason.length < 5} onClick={() => { try { save(r, { params: JSON.parse(params) }) } catch { setErr('Settings must be valid JSON') } }}>Save</button>
                <button className="btn sm" onClick={() => setEdit(null)}>Cancel</button></div></div>
              : <div className="row">
                {Object.keys(r.params || {}).length > 0 && <button className="btn sm" onClick={() => { setEdit(r.id); setParams(JSON.stringify(r.params, null, 1)) }}>Edit</button>}
                <button className="btn sm" onClick={() => { const why = prompt('Reason?'); if (why && why.length >= 5) api(`/api/rules/${r.id}`, { method: 'PUT', json: { enabled: !r.enabled, reason: why } }).then(load) }}>{r.enabled ? 'Turn off' : 'Turn on'}</button></div>}</td>}
          </tr>)}</tbody>
        </table></div>
      </div>
      {cite && <ClauseModal citation={cite} onClose={() => setCite(null)} />}
    </div>
  )
}
