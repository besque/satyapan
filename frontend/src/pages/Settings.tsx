import { useEffect, useState } from 'react'
import { api } from '../api'
import { useUser } from '../App'
import { B, Tip, fmtTime } from '../ui'

export default function Settings() {
  const u = useUser()
  const admin = u.role === 'admin'
  const [d, setD] = useState<any>(null)
  const [msg, setMsg] = useState('')
  const load = () => api('/api/settings').then(setD)
  useEffect(() => { load() }, [])
  const put = async (key: string, value: any) => {
    setMsg('')
    try { await api('/api/settings', { method: 'PUT', json: { key, value } }); setMsg('Saved. Timelines and alerts have been recalculated.'); load() } catch (e: any) { setMsg(e.message) }
  }
  if (!d) return <div className="empty"><span className="spinner" /></div>
  const s = d.settings
  return (
    <div>
      <div className="titlebar"><div><h1>Settings</h1><div className="sub">{admin ? 'Changes apply at once and are recorded in the activity log' : 'Read only. The administrator can change these.'}</div></div></div>
      {msg && <div className="note" style={{ marginBottom: 12 }}>{msg}</div>}
      <div className="box" style={{ marginBottom: 14 }}>
        <div className="bh"><h2>Nature of complaint: handling bureau and timeline <Tip>Grievances follow the DARPG timeline of 21 days (OM of 23.08.2024). Other timelines are defaults for AICTE to set as per its instructions.</Tip></h2></div>
        <div className="tablewrap"><table className="t small">
          <thead><tr><th>Nature</th><th>Normally handled by</th><th>Timeline (days)</th><th>Described to the language model as</th></tr></thead>
          <tbody>{Object.entries(s.categories).map(([id, c]: any) => <tr key={id}>
            <td><b>{c.label}</b></td>
            <td>{admin ? <select value={c.bureau} onChange={(e) => put(`categories.${id}.bureau`, e.target.value)}>
              {Object.keys(s.bureaus).map((b) => <option key={b}>{b}</option>)}</select> : <B b={c.bureau} />}</td>
            <td>{admin ? <input type="number" min={1} max={365} defaultValue={c.days} style={{ width: 80 }} onBlur={(e) => +e.target.value !== c.days && put(`categories.${id}.days`, +e.target.value)} /> : c.days}</td>
            <td className="faint">{(c.describe || []).slice(0, 2).join(' / ')}</td>
          </tr>)}</tbody>
        </table></div>
      </div>
      <div className="grid g2">
        <div className="box">
          <div className="bh"><h2>Escalation ladder</h2></div>
          <div className="tablewrap"><table className="t small"><thead><tr><th>When this share of the timeline is used</th><th>Alert</th><th>Goes to</th></tr></thead>
            <tbody>{s.escalation.map((e: any, i: number) => <tr key={i}>
              <td>{admin ? <input type="number" step={0.1} min={0.1} defaultValue={e.at} style={{ width: 70 }}
                onBlur={(ev) => +ev.target.value !== e.at && put('escalation', s.escalation.map((x: any, j: number) => j === i ? { ...x, at: +ev.target.value } : x))} /> : e.at} × timeline</td>
              <td>{e.label}</td><td>{e.to.replace('_', ' ')}</td></tr>)}</tbody></table></div>
          <div className="bb small faint">Institutions get {s.institution_reply_days} days to reply when a bureau seeks comments.</div>
        </div>
        <div className="box">
          <div className="bh"><h2>Matching</h2></div>
          <div className="tablewrap"><table className="t small"><tbody>
            {[['auto_link', 'Link a complaint to an institution automatically at or above this confidence'], ['margin', '…and only if it beats the next institution by this much'],
              ['same_matter', 'Text similarity (language model) that suggests the same matter'], ['pattern_min', 'Different complainants on one issue that make a pattern'],
              ['pattern_window_days', 'Within this many days']].map(([k, l]) => <tr key={k}>
              <td>{l}</td><td>{admin ? <input type="number" step={k.includes('pattern') ? 1 : 0.01} defaultValue={s.matching[k]} style={{ width: 80 }}
                onBlur={(e) => +e.target.value !== s.matching[k] && put(`matching.${k}`, +e.target.value)} /> : s.matching[k]}</td></tr>)}
          </tbody></table></div>
          <div className="bb small faint">Language model: {d.model.model} ({d.model.backend === 'model' ? 'runs on this server, no data leaves it' : 'fallback'}).</div>
        </div>
      </div>
      <div className="box" style={{ marginTop: 14 }}>
        <div className="bh"><h2>Conflicting actions checked</h2></div>
        <div className="tablewrap"><table className="t small"><thead><tr><th>Check</th><th>When one bureau has</th><th>and another has</th><th>Same matter only</th></tr></thead>
          <tbody>{s.conflicts.map((c: any) => <tr key={c.id}><td><b>{c.title}</b><div className="faint">{c.why}</div></td><td>{c.a.join(', ')}</td><td>{c.b.join(', ')}</td><td>{c.same_matter ? 'Yes' : 'No'}</td></tr>)}</tbody></table></div>
      </div>
      {d.overrides.length > 0 && <div className="box" style={{ marginTop: 14 }}><div className="bh"><h2>Changed by administrator</h2></div>
        <div className="tablewrap"><table className="t small"><tbody>{d.overrides.map((o: any) => <tr key={o.key}><td className="mono">{o.key}</td><td className="mono">{o.value}</td><td>{o.updated_by}</td><td>{fmtTime(o.updated_at)}</td></tr>)}</tbody></table></div></div>}
    </div>
  )
}
