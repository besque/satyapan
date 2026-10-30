import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { B, CaseLink, Due, Kind, KIND, Status, Tip, fmtDate } from '../ui'

const ORDER = ['PGRC', 'RB', 'ARC', 'AB', 'RO']
const DAY = 86400000

export default function Institution() {
  const { pid } = useParams()
  const nav = useNavigate()
  const [d, setD] = useState<any>(null)
  const [showClosed, setShowClosed] = useState(false)
  useEffect(() => { setD(null); api(`/api/institutions/${pid}`).then(setD) }, [pid])
  if (!d) return <div className="empty"><span className="spinner" /></div>
  const openAlerts = d.alerts.filter((a: any) => a.status === 'open' || a.status === 'acknowledged')
  const cases = d.cases.filter((c: any) => showClosed || c.status !== 'disposed')
  return (
    <div>
      <div className="crumbs"><Link to="/institutions">Institutions</Link> › {d.name}</div>
      <div className="titlebar"><div>
        <h1>{d.name}</h1>
        <div className="sub">{d.city}, {d.state} · {d.region} Region · Permanent ID {d.permanent_id} · {d.inst_type} · {d.society}
          {d.aliases.length > 0 && <> · formerly {d.aliases.join(', ')}</>}</div>
      </div></div>

      {openAlerts.length > 0 && <div style={{ marginBottom: 14 }}>{openAlerts.map((a: any) => (
        <Link key={a.id} to={`/coordination/${a.id}`} className={`banner ${KIND[a.kind].color}`}>
          <span><Kind k={a.kind} /> <b>{a.title}</b> <span className="small">· {a.bureaus.join(', ')}{a.lead ? ` · lead suggested: ${a.lead}` : ''}</span></span>
          <span className="small">{a.why}</span>
        </Link>))}</div>}

      <div className="box" style={{ marginBottom: 14 }}>
        <div className="bh"><h2>Who is doing what, when <Tip>One row per bureau. Each bar is a case, from receipt to disposal (or today). Dots are actions; hover for details, click to open the case. Overlapping bars in different rows are the cases that need coordination.</Tip></h2>
          <span className="legend"><span><i className="sw open" />open</span><span><i className="sw done" />disposed</span><span><i className="sw moved" />moved to another bureau</span><span><i className="sw flag" />in a coordination item</span></span></div>
        <Swimlanes d={d} onOpen={(id) => nav(`/case/${id}`)} />
      </div>

      <div className="grid g2" style={{ gridTemplateColumns: 'minmax(0,2fr) minmax(0,1fr)' }}>
        <div className="box">
          <div className="bh"><h2>Cases</h2><label className="small"><input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> include disposed</label></div>
          <div className="tablewrap"><table className="t cards">
            <thead><tr><th>Case</th><th>Bureau</th><th>Nature</th><th>Status</th><th>Last action</th><th>Timeline</th></tr></thead>
            <tbody>{cases.map((c: any) => (
              <tr key={c.id} className="click" onClick={() => nav(`/case/${c.id}`)}>
                <td><CaseLink id={c.id} /><div className="small faint">{fmtDate(c.received_on)}</div>{c.alerts.map((a: any) => <Kind key={a.id} k={a.kind} short />)}</td>
                <td><B b={c.bureau} /></td><td className="small">{c.category_label}</td>
                <td><Status s={c.status} esc={c.esc_level} /></td>
                <td className="small">{c.last_action}<div className="faint">{fmtDate(c.last_action_on)}</div></td>
                <td><Due t={c.timeline} /></td>
              </tr>))}</tbody>
          </table></div>
          {!cases.length && <div className="empty">No open cases.</div>}
        </div>
        <div className="grid" style={{ gap: 14 }}>
          <div className="box"><div className="bh"><h2>Complaints by nature</h2><span className="small faint">all time</span></div>
            <div className="bb">{d.categories.map(([k, n]: any) => <div key={k} className="hbar"><span className="k">{k}</span>
              <span className="track"><i style={{ width: `${(n / d.categories[0][1]) * 100}%` }} /></span><span className="n">{n}</span></div>)}</div></div>
          {d.alerts.length > openAlerts.length && <div className="box"><div className="bh"><h2>Earlier coordination</h2></div>
            {d.alerts.filter((a: any) => !openAlerts.includes(a)).map((a: any) => <Link key={a.id} to={`/coordination/${a.id}`} className="alertrow">
              <span className={`bar ${KIND[a.kind].color}`} /><span className="a1 small"><b>{a.title}</b></span><span className="a2 small faint">{a.status} · {fmtDate(a.updated_at)}</span></Link>)}</div>}
        </div>
      </div>
    </div>
  )
}

function Swimlanes({ d, onOpen }: { d: any; onOpen: (id: string) => void }) {
  const lanes = useMemo(() => {
    const all = Object.values(d.lanes).flat() as any[]
    const t1 = new Date(d.today + 'T00:00:00').getTime() + 5 * DAY
    const first = Math.min(...all.map((s) => new Date(s.from + 'T00:00:00').getTime()), t1 - 120 * DAY)
    const t0 = Math.max(first, t1 - 300 * DAY) - 5 * DAY
    const x = (s: string) => Math.max(0, Math.min(100, ((new Date(s + 'T00:00:00').getTime() - t0) / (t1 - t0)) * 100))
    const rows = ORDER.filter((b) => d.lanes[b]).map((b) => {
      const segs = [...d.lanes[b]].sort((a, c) => a.from.localeCompare(c.from))
      const tracks: number[] = []
      const placed = segs.filter((s) => new Date(s.to + 'T00:00:00').getTime() >= t0).map((s) => {
        const l = x(s.from), r = Math.max(x(s.to), l + 0.8)
        let k = tracks.findIndex((end) => end < l - 0.3)
        if (k === -1) { k = tracks.length; tracks.push(r) } else tracks[k] = r
        return { ...s, l, w: r - l, k }
      })
      return { b, placed, n: Math.max(1, tracks.length) }
    })
    const months: { x: number; label: string }[] = []
    const m = new Date(t0); m.setDate(1); m.setMonth(m.getMonth() + 1)
    while (m.getTime() < t1) { months.push({ x: x(m.toISOString().slice(0, 10)), label: m.toLocaleDateString('en-IN', { month: 'short' }) }); m.setMonth(m.getMonth() + 1) }
    return { rows, months, today: x(d.today), x }
  }, [d])
  if (!lanes.rows.length) return <div className="empty">No cases.</div>
  return (
    <div className="swim">
      <div className="swim-axis">{lanes.months.map((m) => <span key={m.x} style={{ left: `${m.x}%` }}>{m.label}</span>)}</div>
      {lanes.rows.map((row) => (
        <div key={row.b} className="swim-row">
          <div className="swim-h"><B b={row.b} /><span className="small faint">{d.bureaus[row.b]}</span></div>
          <div className="swim-track" style={{ height: row.n * 22 + 8 }}>
            {lanes.months.map((m) => <i key={m.x} className="grid-l" style={{ left: `${m.x}%` }} />)}
            <i className="today" style={{ left: `${lanes.today}%` }} title="Today" />
            {row.placed.map((s: any, i: number) => (
              <button key={i} className={`seg ${s.moved_to ? 'moved' : s.status === 'disposed' ? 'done' : 'open'} ${s.alerts.length ? 'flag' : ''}`}
                style={{ left: `${s.l}%`, width: `${s.w}%`, top: 4 + s.k * 22 }} onClick={() => onOpen(s.case)}
                title={`${s.case} · ${s.label}\n${fmtDate(s.from)} – ${s.moved_to ? 'moved to ' + s.moved_to : s.status === 'disposed' ? fmtDate(s.to) : 'open'}\n${s.events.map((e: any) => `${fmtDate(e.ts)}: ${e.label}`).join('\n')}`}>
                {s.events.map((e: any, j: number) => {
                  const p = s.w > 0 ? ((lanes.x(e.ts) - s.l) / s.w) * 100 : 0
                  return <span key={j} className={`ev ${e.kind}`} style={{ left: `${Math.max(0, Math.min(100, p))}%` }} />
                })}
                <span className="seg-l">{s.w > 7 ? s.label : ''}</span>
              </button>))}
          </div>
        </div>))}
    </div>
  )
}
