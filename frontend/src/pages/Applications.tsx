import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, withToken } from '../api'
import { useUser } from '../App'
import { AppLink, Counts, Due, fmtShort, Holder, Loading, nameOf, Risk, Tip } from '../ui'

export default function Applications() {
  const nav = useNavigate()
  const u = useUser()
  const [rows, setRows] = useState<any[] | null>(null)
  const [meta, setMeta] = useState<any>(null)
  const [f, setF] = useState({ q: '', region: '', nature: '', stage: '', holder: '' })
  const [risk, setRisk] = useState('open')
  useEffect(() => { api('/api/meta').then(setMeta) }, [])
  useEffect(() => { api('/api/applications').then(setRows) }, [])
  const base = useMemo(() => (rows || []).filter((r) => {
    const ql = f.q.toLowerCase()
    return (!ql || `${r.id} ${r.institution} ${r.pid} ${r.city || ''}`.toLowerCase().includes(ql)) && (!f.region || r.region === f.region)
      && (!f.nature || r.nature === f.nature) && (!f.stage || r.stage === f.stage) && (!f.holder || r.holder_kind === f.holder)
  }), [rows, f])
  if (!rows || !meta) return <Loading />
  const live = base.filter((r) => r.phase)
  const shown = risk === 'all' ? base : risk === 'open' ? live : risk === 'decided' ? base.filter((r) => !r.phase) : live.filter((r) => r.risk === risk)
  const set = (k: string, v: string) => setF({ ...f, [k]: v })
  return <div>
    <div className="titlebar"><div><h1>Applications</h1><div className="sub">{u.role === 'ro' ? `${u.region} region` : 'All regions'} · {rows.length} this cycle</div></div>
      <a className="btn noprint" href={withToken('/api/reports.csv?table=applications')}>Download CSV</a></div>
    <Counts on={risk} set={setRisk} items={[
      { k: 'open', v: live.length, l: 'In process' },
      { k: 'will_miss', v: live.filter((r) => r.risk === 'will_miss').length, l: 'Will miss the date', color: 'darkred' },
      { k: 'fast_track', v: live.filter((r) => r.risk === 'fast_track').length, l: 'Need fast-tracking', color: 'red' },
      { k: 'at_risk', v: live.filter((r) => r.risk === 'at_risk').length, l: 'At risk', color: 'orange' },
      { k: 'on_track', v: live.filter((r) => r.risk === 'on_track').length, l: 'On track', color: 'green' },
      { k: 'decided', v: base.length - live.length, l: 'Decided' },
      { k: 'all', v: base.length, l: 'All' }]} />
    <div className="box filters">
      <label className="flt grow">Search<input placeholder="Application no., institution, Permanent ID or city" value={f.q} onChange={(e) => set('q', e.target.value)} /></label>
      {u.role !== 'ro' && <label className="flt">Region<select value={f.region} onChange={(e) => set('region', e.target.value)}><option value="">All</option>{meta.regions.map((r: string) => <option key={r}>{r}</option>)}</select></label>}
      <label className="flt">Nature of application<select value={f.nature} onChange={(e) => set('nature', e.target.value)}><option value="">All</option>{meta.natures.map((n: any) => <option key={n.id} value={n.id}>{n.label}</option>)}</select></label>
      <label className="flt">Stage<select value={f.stage} onChange={(e) => set('stage', e.target.value)}><option value="">All</option>{meta.stages.map((s: any) => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
      <label className="flt">With<select value={f.holder} onChange={(e) => set('holder', e.target.value)}><option value="">Anyone</option><option value="aicte">AICTE</option><option value="institution">Institution</option></select></label>
    </div>
    <div className="box"><div className="tablewrap"><table className="t cards">
      <thead><tr><th>Application</th><th>Nature</th><th>Where it is</th><th>With <Tip>Who holds the ball now, and for how many days. Delays are counted against the holder.</Tip></th><th>Due</th><th>Against the calendar</th></tr></thead>
      <tbody>{shown.map((r) => <tr key={r.id} className="click" onClick={() => nav(`/app/${r.id}`)}>
        <td><AppLink id={r.id} /> <b>{nameOf(r.institution)}</b><div className="small faint">{r.city} · {r.region}</div></td>
        <td className="small">{r.nature_label}</td>
        <td>{r.phase ? <>{r.task}{r.meeting_on && r.phase !== 'to_schedule' && <div className="small faint">meeting {fmtShort(r.meeting_on)}</div>}</> : <span className={`st ${r.status === 'approved' ? 'green' : 'orange'}`}>{r.status_label}</span>}
          {!r.phase && r.decided_on && <div className="small faint">{fmtShort(r.decided_on)}</div>}</td>
        <td><Holder kind={r.holder_kind} label={r.holder_kind === 'institution' ? 'Institution' : r.holder_label} days={r.with_days} /></td>
        <td>{r.phase ? <Due due={r.due_on} overdue={r.overdue} left={r.days_left} /> : <span className="faint">—</span>}</td>
        <td><Risk r={r.risk} spare={r.risk === 'fast_track' || r.risk === 'will_miss' ? r.spare_fast ?? r.spare : r.spare} /></td>
      </tr>)}</tbody>
    </table></div>{!shown.length && <div className="empty">No applications match.</div>}</div>
  </div>
}
