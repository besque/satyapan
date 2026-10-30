import { useEffect, useState } from 'react'
import { api, withToken } from '../api'
import { B, fmtDate, pct } from '../ui'

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

function presets() {
  const t = new Date()
  const q = Math.floor(t.getMonth() / 3)
  return [
    ['This month', iso(new Date(t.getFullYear(), t.getMonth(), 1)), iso(t)],
    ['Last month', iso(new Date(t.getFullYear(), t.getMonth() - 1, 1)), iso(new Date(t.getFullYear(), t.getMonth(), 0))],
    ['This quarter', iso(new Date(t.getFullYear(), q * 3, 1)), iso(t)],
    ['Last 90 days', iso(new Date(t.getTime() - 89 * 86400000)), iso(t)],
    ['Last 12 months', iso(new Date(t.getFullYear() - 1, t.getMonth(), t.getDate() + 1)), iso(t)],
  ]
}

export default function Reports() {
  const ps = presets()
  const [range, setRange] = useState<[string, string]>([ps[3][1], ps[3][2]])
  const [d, setD] = useState<any>(null)
  useEffect(() => { setD(null); api(`/api/reports?frm=${range[0]}&to=${range[1]}`).then(setD) }, [range])
  const csv = (t: string) => withToken(`/api/reports.csv?table=${t}&frm=${range[0]}&to=${range[1]}`)
  const maxM = Math.max(1, ...(d?.monthly || []).flatMap((m: any) => [m.received, m.disposed]))
  return (
    <div>
      <div className="titlebar">
        <div><h1>Reports</h1><div className="sub">{fmtDate(range[0])} to {fmtDate(range[1])}</div></div>
        <div className="row noprint">
          <div className="seg">{ps.map(([l, a, b]) => <button key={l} className={range[0] === a && range[1] === b ? 'on' : ''} onClick={() => setRange([a, b])}>{l}</button>)}</div>
          <input type="date" value={range[0]} onChange={(e) => setRange([e.target.value, range[1]])} />
          <input type="date" value={range[1]} onChange={(e) => setRange([range[0], e.target.value])} />
          <button className="btn" onClick={() => window.print()}>Print</button>
        </div>
      </div>
      {!d ? <div className="empty"><span className="spinner" /></div> : <>
        <div className="counts static">
          <div><span className="v">{d.totals.received}</span><span className="l">Received</span></div>
          <div><span className="v">{d.totals.disposed}</span><span className="l">Disposed</span></div>
          <div><span className="v">{d.totals.disposal_rate}%</span><span className="l">Disposal rate (disposed ÷ received)</span></div>
          <div><span className="v">{d.totals.open_at_end}</span><span className="l">Open at end of period</span></div>
          <div><span className="v">{d.totals.overlaps}</span><span className="l">Overlaps found</span></div>
        </div>
        <div className="grid g2" style={{ marginBottom: 14 }}>
          <div className="box"><div className="bh"><h2>Received and disposed, by month</h2><span className="legend"><span><i className="sw rec" />received</span><span><i className="sw dis" />disposed</span></span></div>
            <div className="bb"><div className="cols">{d.monthly.map((m: any) => <div key={m.month} className="col">
              <div className="pair"><i className="rec" style={{ height: `${(m.received / maxM) * 100}%` }} title={`${m.received} received`} /><i className="dis" style={{ height: `${(m.disposed / maxM) * 100}%` }} title={`${m.disposed} disposed`} /></div>
              <span className="small">{m.month.split(' ')[0]}</span></div>)}</div></div></div>
          <Simple title="Ageing of cases open at end of period" rows={d.ageing} csv={csv('ageing')} />
        </div>
        <Stat title="Bureau-wise" rows={d.bureau} csv={csv('bureau')} bureau />
        <Stat title="Region-wise" rows={d.region} csv={csv('region')} />
        <Stat title="By nature of complaint" rows={d.category} csv={csv('category')} />
        <Stat title="Institution-wise (most cases)" rows={d.institution} csv={csv('institution')} />
        <div className="box" style={{ marginBottom: 14 }}>
          <div className="bh"><h2>Overlapping and duplicate cases</h2><a className="small noprint" href={csv('overlaps')}>Download CSV</a></div>
          <div className="tablewrap"><table className="t small"><thead><tr><th>Kind</th><th className="num">Raised</th><th className="num">Closed by officers</th><th className="num">Still open</th></tr></thead>
            <tbody>{d.overlaps.map((r: any) => <tr key={r.name}><td>{r.name}</td><td className="num">{r.raised}</td><td className="num">{r.resolved}</td><td className="num">{r.open}</td></tr>)}</tbody></table></div>
        </div>
      </>}
    </div>
  )
}

function Stat({ title, rows, csv, bureau }: { title: string; rows: any[]; csv: string; bureau?: boolean }) {
  return (
    <div className="box" style={{ marginBottom: 14 }}>
      <div className="bh"><h2>{title}</h2><a className="small noprint" href={csv}>Download CSV</a></div>
      <div className="tablewrap"><table className="t small">
        <thead><tr><th>{bureau ? 'Bureau / Cell' : 'Name'}</th><th className="num">Received</th><th className="num">Disposed</th><th className="num">Disposed in time</th>
          <th className="num">Avg. days to dispose</th><th className="num">Open at end</th><th className="num">Of which beyond timeline</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.name}><td>{bureau ? <B b={r.name} /> : r.name}</td><td className="num">{r.received}</td><td className="num">{r.disposed}</td>
          <td className="num">{pct(r.in_time_pct)}</td><td className="num">{r.avg_days ?? '—'}</td><td className="num">{r.open}</td>
          <td className="num" style={{ color: r.overdue ? 'var(--red)' : undefined }}>{r.overdue}</td></tr>)}</tbody>
      </table></div>
    </div>
  )
}

function Simple({ title, rows, csv }: { title: string; rows: any[]; csv: string }) {
  const max = Math.max(1, ...rows.map((r) => r.n))
  return (
    <div className="box"><div className="bh"><h2>{title}</h2><a className="small noprint" href={csv}>Download CSV</a></div>
      <div className="bb">{rows.map((r) => <div key={r.name} className="hbar"><span className="k">{r.name}</span><span className="track"><i style={{ width: `${(r.n / max) * 100}%` }} /></span><span className="n">{r.n}</span></div>)}</div></div>
  )
}
