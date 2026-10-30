import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { fmtTime } from '../ui'

const KIND: Record<string, [string, string]> = { coordination: ['Overlap', 'red'], timeline: ['Timeline', 'orange'], transfer: ['Transfer', 'violet'] }
const ROLE: Record<string, string> = { officer: 'Officer', section_head: 'Section head', bureau_head: 'Bureau head', management: 'Senior management' }

export default function Alerts() {
  const u = useUser()
  const [d, setD] = useState<any>(null)
  const [only, setOnly] = useState('')
  const load = () => api('/api/notifications').then(setD)
  useEffect(() => { load() }, [])
  const read = async (ids: number[] = []) => { await api('/api/notifications/read', { method: 'POST', json: { ids } }); load() }
  const rows = (d?.rows || []).filter((r: any) => !only || r.kind === only)
  return (
    <div>
      <div className="titlebar">
        <div><h1>Alerts</h1><div className="sub">For {u.bureau ? `${u.bureau} (all levels: officer, section head, bureau head)` : 'senior management'} · {d?.unread ?? '…'} unread</div></div>
        <div className="row">
          <div className="seg">{[['', 'All'], ['coordination', 'Overlaps'], ['timeline', 'Timelines'], ['transfer', 'Transfers']].map(([k, l]) =>
            <button key={k} className={only === k ? 'on' : ''} onClick={() => setOnly(k)}>{l}</button>)}</div>
          <button className="btn" onClick={() => read()}>Mark all read</button>
        </div>
      </div>
      <div className="box">
        {rows.map((r: any) => (
          <Link key={r.id} to={r.coord_id ? `/coordination/${r.coord_id}` : `/case/${r.case_id}`} className={`noterow ${r.read ? '' : 'unread'}`} onClick={() => !r.read && read([r.id])}>
            <span className={`pill ${KIND[r.kind]?.[1] || 'grey'}`}>{KIND[r.kind]?.[0] || r.kind}</span>
            <span>{r.text}</span>
            <span className="small faint">{ROLE[r.to_role] || r.to_role} · {fmtTime(r.created_at)}</span>
          </Link>))}
        {d && !rows.length && <div className="empty">No alerts.</div>}
      </div>
    </div>
  )
}
