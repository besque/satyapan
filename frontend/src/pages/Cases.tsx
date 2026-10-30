import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { B, CaseLink, Due, Kind, Meter, Status, fmtDate } from '../ui'

const FIELDS = ['q', 'bureau', 'region', 'category', 'status', 'state', 'frm', 'to'] as const

export default function Cases() {
  const u = useUser()
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [meta, setMeta] = useState<any>(null)
  const [d, setD] = useState<any>(null)
  const [q, setQ] = useState(sp.get('q') || '')
  useEffect(() => { api('/api/meta').then(setMeta) }, [])
  useEffect(() => {
    const p = new URLSearchParams()
    FIELDS.forEach((f) => { const v = sp.get(f); if (v) p.set(f, v) })
    setD(null)
    api(`/api/cases?${p}`).then(setD)
  }, [sp])
  useEffect(() => { const t = setTimeout(() => set('q', q), 300); return () => clearTimeout(t) }, [q])
  function set(k: string, v: string) {
    const n = new URLSearchParams(sp)
    if (v) n.set(k, v); else n.delete(k)
    if ((sp.get(k) || '') !== v) setSp(n, { replace: true })
  }
  const sel = (k: string, label: string, opts: [string, string][]) => (
    <label className="flt"><span>{label}</span>
      <select value={sp.get(k) || ''} onChange={(e) => set(k, e.target.value)}>
        <option value="">All</option>{opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select></label>)
  const any = FIELDS.some((f) => sp.get(f))
  return (
    <div>
      <div className="titlebar">
        <div><h1>Cases</h1><div className="sub">Every complaint and case across Bureaus and Cells</div></div>
        <div className="row">
          {(u.role === 'officer' || u.role === 'management') && <Link className="btn primary" to="/register">Register complaint</Link>}
        </div>
      </div>
      <div className="filters box">
        <label className="flt grow"><span>Search</span><input placeholder="Case no., CPGRAMS no., institution, Permanent ID, subject" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        {meta && <>
          {sel('bureau', 'Bureau / Cell', meta.bureaus.map((b: any) => [b.id, `${b.id} · ${b.name}`]))}
          {sel('region', 'Region', meta.regions.map((r: string) => [r, r]))}
          {sel('category', 'Nature', meta.categories.map((c: any) => [c.id, c.label]))}
          {sel('status', 'Status', [['open', 'All open'], ...meta.statuses.map((s: any) => [s.id, s.label])])}
          {sel('state', 'Show only', [['overdue', 'Beyond timeline'], ['due_soon', 'Due soon'], ['escalated', 'Escalated'], ['overlap', 'With an overlap alert'], ['unconfirmed', 'Institution to confirm']])}
          <label className="flt"><span>Received from</span><input type="date" value={sp.get('frm') || ''} onChange={(e) => set('frm', e.target.value)} /></label>
          <label className="flt"><span>to</span><input type="date" value={sp.get('to') || ''} onChange={(e) => set('to', e.target.value)} /></label>
        </>}
        {any && <button className="btn sm" style={{ alignSelf: 'flex-end' }} onClick={() => { setQ(''); setSp(new URLSearchParams()) }}>Clear</button>}
      </div>
      <div className="box">
        <div className="bh"><span className="small muted">{d ? `${d.total} case${d.total === 1 ? '' : 's'}` : 'Loading…'}</span></div>
        <div className="tablewrap"><table className="t cards">
          <thead><tr><th>Case</th><th style={{ width: '24%' }}>Institution</th><th>Bureau</th><th>Nature</th><th>Status</th><th>Last action</th><th>Timeline</th></tr></thead>
          <tbody>{d?.rows.map((r: any) => (
            <tr key={r.id} className="click" onClick={() => nav(`/case/${r.id}`)}>
              <td><CaseLink id={r.id} /><div className="small faint">{fmtDate(r.received_on)}{r.lang === 'hi' ? ' · Hindi' : ''}</div>
                {r.alerts.length > 0 && <div>{r.alerts.map((a: any) => <Kind key={a.id} k={a.kind} short />)}</div>}</td>
              <td>{r.institution ? <><b>{r.institution}</b><div className="small faint">{r.city} · {r.permanent_id}</div></> :
                <><span className="pill orange">To confirm</span><div className="small faint">“{r.inst_text}”</div></>}</td>
              <td><B b={r.bureau} /><div className="small faint">{r.officer}</div></td>
              <td className="small">{r.category_label}</td>
              <td><Status s={r.status} esc={r.esc_level} /></td>
              <td className="small">{r.last_action}<div className="faint">{fmtDate(r.last_action_on)}</div></td>
              <td><Due t={r.timeline} /><div><Meter t={r.timeline} /></div></td>
            </tr>))}</tbody>
        </table></div>
        {d && !d.rows.length && <div className="empty">No cases match.</div>}
      </div>
    </div>
  )
}
