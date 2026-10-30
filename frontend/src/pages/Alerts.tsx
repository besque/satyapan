import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { fmtShort, Loading, nameOf } from '../ui'

const KIND: Record<string, [string, string]> = {
  reminder: ['Reminder', 'blue'], due_soon: ['Due soon', 'blue'], overdue: ['Overdue', 'orange'], escalated: ['Escalated', 'red'],
  at_risk: ['Calendar risk', 'red'], expired: ['Expired', 'red'], 'not submitted': ['Not submitted', 'red'], notice: ['Notice', 'grey'], info: ['For action', 'orange'],
}
const CHAN: Record<string, string> = { portal: 'portal', email: 'e-mail', sms: 'SMS' }

export default function Alerts() {
  const u = useUser()
  const [d, setD] = useState<any>(null)
  const [scope, setScope] = useState('mine')
  const [only, setOnly] = useState('')
  const load = () => api(`/api/alerts?scope=${scope}`).then(setD)
  useEffect(() => { setD(null); load() }, [scope])
  const read = async (ids: number[] = []) => { await api('/api/alerts/read', { method: 'POST', json: { ids } }); load() }
  if (!d) return <Loading />
  const rows = d.rows.filter((r: any) => !only || r.kind === only)
  const kinds = Array.from(new Set(d.rows.map((r: any) => r.kind))) as string[]
  return <div>
    <div className="titlebar"><div><h1>{u.role === 'institution' ? 'Notices from AICTE' : 'Alerts and notices'}</h1>
      <div className="sub">Every reminder, notice and escalation as sent, with its date and channels · {d.unread} unread</div></div>
      <div className="row">
        {(u.role === 'head' || u.role === 'admin') && <div className="seg"><button className={scope === 'mine' ? 'on' : ''} onClick={() => setScope('mine')}>Mine</button><button className={scope === 'all' ? 'on' : ''} onClick={() => setScope('all')}>Everything sent</button></div>}
        <select value={only} onChange={(e) => setOnly(e.target.value)}><option value="">All kinds</option>{kinds.map((k) => <option key={k} value={k}>{KIND[k]?.[0] || k}</option>)}</select>
        <button className="btn" onClick={() => read()}>Mark all read</button></div></div>
    <div className="box">
      {rows.map((r: any) => <Link key={r.id} to={r.app_id ? `/app/${r.app_id}` : r.item_id ? `/item/${r.item_id}` : '#'} className={`noterow ${r.read ? '' : 'unread'}`} onClick={() => !r.read && read([r.id])}>
        <span className="small faint">{fmtShort(r.on_date)}</span>
        <span><span className={`pill ${KIND[r.kind]?.[1] || 'grey'}`}>{KIND[r.kind]?.[0] || r.kind}</span></span>
        <span className="txt small">{r.text}</span>
        <span className="small faint">to {nameOf(r.to_label)}<br />by {r.channels.map((c: string) => CHAN[c] || c).join(', ')}</span>
      </Link>)}
      {!rows.length && <div className="empty">Nothing here.</div>}
    </div>
  </div>
}
