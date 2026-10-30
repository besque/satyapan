import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useUser } from '../App'
import { B, CaseLink, Due, Kind, KIND, Meter, Status, Tip, fmtDate } from '../ui'

export default function Overview() {
  const u = useUser()
  const nav = useNavigate()
  const [scope, setScope] = useState(u.bureau ? 'mine' : 'all')
  const [d, setD] = useState<any>(null)
  useEffect(() => { setD(null); api(`/api/overview?scope=${scope}`).then(setD) }, [scope])
  const c = d?.counts
  const go = (q: string) => nav(`/cases?${q}${scope === 'mine' && u.bureau ? `&bureau=${u.bureau}` : ''}`)
  const strong = d?.alerts.filter((a: any) => a.kind !== 'parallel') || []
  const info = d?.alerts.filter((a: any) => a.kind === 'parallel') || []
  const maxAge = Math.max(1, ...(d?.ageing || []).map((a: any) => a.n))
  return (
    <div>
      <div className="titlebar">
        <div><h1>Overview</h1><div className="sub">{scope === 'mine' ? `Cases held by ${u.bureau}` : 'All Bureaus, Cells and Regional Offices'} · as on {fmtDate(d?.today)}</div></div>
        {u.bureau && <div className="seg">
          <button className={scope === 'mine' ? 'on' : ''} onClick={() => setScope('mine')}>My bureau ({u.bureau})</button>
          <button className={scope === 'all' ? 'on' : ''} onClick={() => setScope('all')}>All AICTE</button>
        </div>}
      </div>
      {!d ? <div className="empty"><span className="spinner" /> Loading…</div> : <>
        <div className="counts">
          <button onClick={() => go('status=open')}><span className="v">{c.pending + c.under_process + c.transferred}</span><span className="l">Open cases</span></button>
          <button onClick={() => go('status=pending')}><span className="v" style={{ color: 'var(--orange)' }}>{c.pending}</span><span className="l">Pending <Tip>Received but not yet taken up.</Tip></span></button>
          <button onClick={() => go('status=under_process')}><span className="v">{c.under_process}</span><span className="l">Under process</span></button>
          <button onClick={() => go('status=transferred')}><span className="v" style={{ color: 'var(--violet)' }}>{c.transferred}</span><span className="l">Transferred <Tip>Moved to another bureau and not yet taken up there.</Tip></span></button>
          <button onClick={() => go('state=overdue')}><span className="v" style={{ color: 'var(--red)' }}>{c.overdue}</span><span className="l">Beyond timeline <Tip>Open longer than the prescribed timeline for its nature (for example 21 days for grievances, as per DARPG).</Tip></span></button>
          <button onClick={() => go('state=escalated')}><span className="v" style={{ color: 'var(--red)' }}>{c.escalated}</span><span className="l">Escalated <Tip>Overdue by half the timeline or more: sent to the bureau head, then to senior management.</Tip></span></button>
          <button onClick={() => go('status=disposed')}><span className="v" style={{ color: 'var(--green)' }}>{c.disposed}</span><span className="l">Disposed · {c.in_time_rate}% in time</span></button>
        </div>

        <div className="box" style={{ marginBottom: 14 }}>
          <div className="bh"><h2>Needs coordination <Tip>Found automatically by comparing every bureau's cases on the same institution: by institution, by complaint text (language model, Hindi and English) and by the actions taken.</Tip></h2>
            <Link to="/coordination" className="small">All coordination items →</Link></div>
          {strong.length === 0 && <div className="empty">Nothing needs coordination.</div>}
          {strong.slice(0, 8).map((a: any) => (
            <Link key={a.id} to={`/coordination/${a.id}`} className="alertrow">
              <span className={`bar ${KIND[a.kind].color}`} />
              <span className="a1"><Kind k={a.kind} /> <b>{a.title}</b></span>
              <span className="a2">{a.institution} · {a.bureaus.map((b: string) => <B key={b} b={b} />)} {a.lead && <span className="small faint">lead suggested: {a.lead}</span>}</span>
              <span className="a3 small">{a.my_ack === false ? <span className="pill orange">Your bureau has not acknowledged</span> : a.my_ack ? <span className="pill green">Acknowledged</span> : null}<span className="faint"> {fmtDate(a.created_at)}</span></span>
            </Link>
          ))}
          {strong.length > 8 && <div className="small" style={{ padding: '8px 14px' }}><Link to="/coordination">+ {strong.length - 8} more</Link></div>}
          {info.length > 0 && <div className="small faint" style={{ padding: '8px 14px', borderTop: '1px solid var(--line)' }}>
            Also {info.length} institutions with open cases in more than one bureau, <Link to="/coordination?tab=info">for information</Link>.</div>}
        </div>

        <div className="grid g2">
          {u.bureau && scope === 'mine' ? <div className="box">
            <div className="bh"><h2>Needs your attention</h2><Link to={`/cases?bureau=${u.bureau}&status=open`} className="small">All open {u.bureau} cases →</Link></div>
            <div className="tablewrap"><table className="t cards">
              <thead><tr><th>Case</th><th>Institution</th><th>Status</th><th>Timeline</th></tr></thead>
              <tbody>{d.attention.map((r: any) => (
                <tr key={r.id} className="click" onClick={() => nav(`/case/${r.id}`)}>
                  <td><CaseLink id={r.id} />{r.alerts.length > 0 && <div>{r.alerts.map((a: any) => <Kind key={a.id} k={a.kind} short />)}</div>}</td>
                  <td>{r.institution || <span className="faint">To confirm</span>}<div className="small faint">{r.category_label}</div></td>
                  <td><Status s={r.status} esc={r.esc_level} /><div className="small faint">{r.next_action}</div></td>
                  <td><Due t={r.timeline} /><div><Meter t={r.timeline} /></div></td>
                </tr>))}</tbody>
            </table></div>
          </div> : <div className="box">
            <div className="bh"><h2>Workload by bureau</h2></div>
            <BureauTable rows={d.bureaus} go={(b) => nav(`/cases?bureau=${b}&status=open`)} />
          </div>}
          <div className="grid" style={{ gap: 14 }}>
            {u.bureau && scope === 'mine' && <div className="box">
              <div className="bh"><h2>Workload by bureau</h2></div>
              <BureauTable rows={d.bureaus} go={(b) => nav(`/cases?bureau=${b}&status=open`)} />
            </div>}
            <div className="box">
              <div className="bh"><h2>Age of open cases</h2></div>
              <div className="bb">{d.ageing.map((a: any) => (
                <div key={a.label} className="hbar"><span className="k">{a.label}</span><span className="track"><i style={{ width: `${(a.n / maxAge) * 100}%` }} /></span><span className="n">{a.n}</span></div>))}</div>
            </div>
            <div className="box">
              <div className="bh"><h2>Open cases by region</h2></div>
              <div className="tablewrap"><table className="t small">
                <thead><tr><th>Region</th><th className="num">Open</th><th className="num">Beyond timeline</th></tr></thead>
                <tbody>{d.regions.map((r: any) => <tr key={r.region} className="click" onClick={() => nav(`/cases?region=${encodeURIComponent(r.region)}&status=open`)}>
                  <td>{r.region}</td><td className="num">{r.open}</td><td className="num" style={{ color: r.overdue ? 'var(--red)' : undefined }}>{r.overdue}</td></tr>)}</tbody>
              </table></div>
            </div>
          </div>
        </div>
        {c.unconfirmed > 0 && <div className="note" style={{ marginTop: 14 }}>{c.unconfirmed} complaint(s) could not be tied to an institution with certainty. <Link to="/coordination?tab=confirm">Confirm the institution</Link></div>}
        <p className="small faint" style={{ marginTop: 10 }}>Language model: {d.model.backend === 'model' ? d.model.model + ' (runs locally)' : d.model.model}.</p>
      </>}
    </div>
  )
}

function BureauTable({ rows, go }: { rows: any[]; go: (b: string) => void }) {
  return (
    <div className="tablewrap"><table className="t small">
      <thead><tr><th>Bureau / Cell</th><th className="num">Open</th><th className="num">Beyond timeline</th><th className="num">Escalated</th><th className="num">Avg. age</th><th className="num">Disposed (30 d)</th></tr></thead>
      <tbody>{rows.map((b) => <tr key={b.bureau} className="click" onClick={() => go(b.bureau)}>
        <td><B b={b.bureau} /> {b.name}</td><td className="num">{b.open}</td>
        <td className="num" style={{ color: b.overdue ? 'var(--red)' : undefined }}>{b.overdue}</td>
        <td className="num" style={{ color: b.escalated ? 'var(--red)' : undefined }}>{b.escalated}</td>
        <td className="num">{b.avg_age} d</td><td className="num">{b.disposed_30d}</td></tr>)}</tbody>
    </table></div>
  )
}
