import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useClock, useUser } from '../App'
import { AppLink, Counts, Due, fmtDate, fmtShort, Holder, Loading, nameOf, Risk, SplitBar, Tip } from '../ui'

export default function Home() {
  const u = useUser()
  if (u.role === 'institution') return <InstitutionHome />
  if (u.role === 'head' || u.role === 'admin') return <Overview />
  return <Work />
}

function StepTable({ rows, empty, showHolder }: { rows: any[]; empty: string; showHolder?: boolean }) {
  const nav = useNavigate()
  if (!rows.length) return <div className="empty">{empty}</div>
  return <div className="tablewrap"><table className="t cards">
    <thead><tr><th>What is needed</th><th>Application</th>{showHolder && <th>With</th>}<th>Due</th><th>Against the calendar <Tip>Whether the application can still be decided by the Academic Calendar date, counting back from that date through the stages still to come.</Tip></th></tr></thead>
    <tbody>{rows.map((r) => <tr key={r.id} className="click" onClick={() => nav(`/app/${r.id}`)}>
      <td><b>{r.task}</b>{r.esc_level >= 2 && <div className="small" style={{ color: 'var(--red)' }}>{r.esc_level >= 3 ? 'Escalated to senior management' : 'Escalated to head of office'}</div>}
        {r.meeting_on && r.phase !== 'to_schedule' && <div className="small faint">{r.mode} meeting {fmtShort(r.meeting_on)}</div>}</td>
      <td><AppLink id={r.id} /> {nameOf(r.institution)}<div className="small faint">{r.nature_label} · {r.region}</div></td>
      {showHolder && <td><Holder kind={r.holder_kind} label={r.holder_kind === 'institution' ? 'Institution' : r.holder_label} days={r.with_days} /></td>}
      <td><Due due={r.due_on} overdue={r.overdue} left={r.days_left} /></td>
      <td><Risk r={r.risk} spare={r.risk === 'fast_track' || r.risk === 'will_miss' ? r.spare_fast ?? r.spare : r.spare} />
        {r.hold_by && r.phase === 'to_schedule' && <div className="small faint">hold by {fmtShort(r.hold_by)}</div>}</td>
    </tr>)}</tbody>
  </table></div>
}

function ItemTable({ rows, empty }: { rows: any[]; empty: string }) {
  const nav = useNavigate()
  if (!rows.length) return <div className="empty">{empty}</div>
  return <div className="tablewrap"><table className="t cards">
    <thead><tr><th>Item</th><th>Institution</th><th>State</th></tr></thead>
    <tbody>{rows.map((i) => <tr key={i.id} className="click" onClick={() => nav(`/item/${i.id}`)}>
      <td><b>{i.title}</b><div className="small faint">{i.kind_label}{i.detail ? ` · ${i.detail}` : ''}</div></td>
      <td>{nameOf(i.institution)}<div className="small faint">{i.region}</div></td>
      <td><span className={`pill ${i.state.color}`}>{i.state.label}</span></td></tr>)}</tbody>
  </table></div>
}

function Work() {
  const u = useUser()
  const [d, setD] = useState<any>(null)
  const [flt, setFlt] = useState('all')
  useEffect(() => { api('/api/work').then(setD) }, [])
  if (!d) return <Loading />
  const c = d.counts
  const rows = d.steps.filter((r: any) => flt === 'all' || (flt === 'overdue' ? r.overdue > 0 : flt === 'this_week' ? r.days_left !== null && r.days_left <= 7 : r.risk === flt))
  const whom = u.role === 'ro' ? `the ${u.title}` : u.role === 'committee' ? 'the committees you sit on' : u.role === 'ec' ? 'the Executive Committee' : 'the Regulation Bureau'
  return <div>
    <div className="titlebar"><div><h1>My work</h1><div className="sub">Everything waiting on {whom}, most urgent first</div></div></div>
    <Counts on={flt} set={setFlt} items={[
      { k: 'all', v: d.steps.length, l: 'Waiting on you' },
      { k: 'will_miss', v: c.will_miss, l: 'Will miss the date', color: 'darkred' },
      { k: 'fast_track', v: c.fast_track, l: 'Need fast-tracking', color: 'red' },
      { k: 'at_risk', v: c.at_risk, l: 'At risk', color: 'orange' },
      { k: 'overdue', v: d.steps.filter((r: any) => r.overdue > 0).length, l: 'Past the time allowed' },
      { k: 'this_week', v: c.this_week, l: 'Due this week' }]} />
    <div className="box"><div className="bh"><h2>Applications waiting on you</h2><span className="small faint">{rows.length} shown</span></div>
      <StepTable rows={rows} empty="Nothing is waiting on you." /></div>
    {d.items.length > 0 && <div className="box"><div className="bh"><h2>Submitted by institutions, for you to verify</h2></div><ItemTable rows={d.items} empty="" /></div>}
    {d.watch.length > 0 && <div className="box"><div className="bh"><h2>{u.role === 'ro' ? 'EVCs of your region, held by others' : 'Waiting on institutions, and late committees'}</h2>
      <span className="small faint">{u.role === 'ro' ? 'you convene these' : 'late institutions are not counted against you'}</span></div>
      <StepTable rows={d.watch} empty="" showHolder /></div>}
  </div>
}

function Overview() {
  const nav = useNavigate()
  const [d, setD] = useState<any>(null)
  const { clock } = useClock()
  useEffect(() => { api('/api/overview').then(setD) }, [])
  if (!d) return <Loading />
  const c = d.counts
  const maxOpen = Math.max(1, ...d.stages.map((s: any) => s.open))
  return <div>
    <div className="titlebar"><div><h1>Overview</h1></div>
      <div className="row"><Link className="btn" to="/applications">All applications</Link><Link className="btn" to="/reports">Reports</Link></div></div>
    <Counts items={[
      { k: 'p', v: c.in_process, l: `In process (of ${c.applications})` },
      { k: 'w', v: c.will_miss, l: 'Will miss the date', color: 'darkred' },
      { k: 'f', v: c.fast_track, l: 'Need fast-tracking', color: 'red' },
      { k: 'r', v: c.at_risk, l: 'At risk', color: 'orange' },
      { k: 'oa', v: c.overdue_aicte, l: 'Late with AICTE' },
      { k: 'oi', v: c.overdue_inst, l: 'Late with institutions' },
      { k: 'd', v: c.approved, l: 'Approved so far', color: 'green' }]} />
    <div className="box"><div className="bh"><h2>Will not make the date without action</h2><span className="small faint">counted back from {fmtDate(clock?.last_date_approval)} through the stages still to come</span></div>
      {d.at_risk.length ? <div className="tablewrap"><table className="t cards">
        <thead><tr><th>Application</th><th>Waiting on</th><th>With</th><th>Against the calendar</th></tr></thead>
        <tbody>{d.at_risk.map((r: any) => <tr key={r.id} className="click" onClick={() => nav(`/app/${r.id}`)}>
          <td><AppLink id={r.id} /> {nameOf(r.institution)}<div className="small faint">{r.nature_label} · {r.region}</div></td>
          <td>{r.task}{r.meeting_on && r.phase !== 'to_schedule' && <div className="small faint">{r.stage_label} fixed for {fmtShort(r.meeting_on)}</div>}
            <div><Due due={r.due_on} overdue={r.overdue} left={r.days_left} /></div></td>
          <td><Holder kind={r.holder_kind} label={r.holder_kind === 'institution' ? 'Institution' : r.holder_label} days={r.with_days} /></td>
          <td><Risk r={r.risk} plain /><div className="small muted">{r.why}</div></td></tr>)}</tbody></table></div>
        : <div className="empty">Every application can still make the date.</div>}</div>
    <div className="grid g2">
      <div className="box"><div className="bh"><h2>Where applications are waiting</h2><span className="legend"><span><i className="sw aicte" />count</span></span></div>
        <div className="bb">{d.stages.map((s: any) => <div key={s.stage} className="hbar" title={`${s.open} open; median ${s.median_days} days at this stage; ${s.overdue} past the time allowed`}>
          <span className="k">{s.label}</span><span className="track"><i style={{ width: `${(s.open / maxOpen) * 100}%` }} /></span><span className="n">{s.open}</span></div>)}
          {d.bottleneck && <div className="note" style={{ marginTop: 10 }}>Slowest stage now: <b>{d.bottleneck.label}</b>, median {d.bottleneck.median_days} days waiting ({d.bottleneck.open} applications, {d.bottleneck.overdue} past the time allowed).</div>}</div></div>
      <div className="box"><div className="bh"><h2>Who held the ball <Tip>Every day of every application is counted against whoever held it: an AICTE office or committee, or the institution. Delays are attributed fairly, and escalations go only to the holder.</Tip></h2></div>
        <div className="bb"><SplitBar aicte={Math.round(d.split.aicte / Math.max(1, d.split.apps))} institution={Math.round(d.split.institution / Math.max(1, d.split.apps))} />
          <div className="small muted" style={{ margin: '6px 0 10px' }}>Average days per application, across all {d.split.apps} this cycle. By office:</div>
          {d.split.offices.map((o: any) => <div key={o.office} className="hbar"><span className="k">{o.office}</span>
            <span className="track"><i className={o.office === 'Institutions' ? 'inst' : ''} style={{ width: `${(o.days / Math.max(1, d.split.offices[0].days)) * 100}%` }} /></span><span className="n">{o.per_app}</span></div>)}</div></div>
    </div>
    <div className="box"><div className="bh"><h2>Region-wise</h2></div>
      <div className="tablewrap"><table className="t small">
        <thead><tr><th>Region</th><th className="num">Applications</th><th className="num">Decided</th><th className="num">In process</th><th className="num">Not on track</th><th className="num">Late with AICTE</th>
          <th className="num">EVCs to fix</th><th className="num">Median wait for EVC date</th><th className="num">Median days with AICTE</th><th className="num">with institution</th></tr></thead>
        <tbody>{d.regions.map((r: any) => <tr key={r.region}><td>{r.region} <span className="faint">({r.office})</span></td><td className="num">{r.applications}</td><td className="num">{r.decided}</td>
          <td className="num">{r.in_process}</td><td className="num" style={{ color: r.risk ? 'var(--red)' : undefined }}>{r.risk}</td><td className="num">{r.overdue}</td>
          <td className="num">{r.evc_to_schedule}</td><td className="num">{r.evc_wait_median ?? '—'}</td><td className="num">{r.days_aicte ?? '—'}</td><td className="num">{r.days_inst ?? '—'}</td></tr>)}</tbody>
      </table></div></div>
    <div className="grid g2">
      <div className="box"><div className="bh"><h2>Compliance after approval</h2><Link className="small" to="/compliance">Open</Link></div>
        <Counts items={[
          { k: 'u', v: d.compliance.undertakings_overdue, l: 'Undertakings overdue', color: d.compliance.undertakings_overdue ? 'red' : undefined },
          { k: 'e', v: d.compliance.documents_expired, l: 'Certificates expired', color: d.compliance.documents_expired ? 'red' : undefined },
          { k: 's', v: d.compliance.documents_expiring, l: 'Expiring in 30 days', color: 'orange' },
          { k: 'p', v: d.compliance.deposits_late, l: 'Deposits late' },
          { k: 'v', v: d.compliance.to_verify, l: 'To verify' }]} /></div>
      <div className="box"><div className="bh"><h2>Recent escalations</h2><Link className="small" to="/alerts">All alerts</Link></div>
        {d.escalations.length ? d.escalations.slice(0, 7).map((a: any) => <Link key={a.id} to={a.app_id ? `/app/${a.app_id}` : `/item/${a.item_id}`} className="noterow" style={{ gridTemplateColumns: '70px 1fr' }}>
          <span className="small faint">{fmtShort(a.on_date)}</span><span className="small">{a.text}</span></Link>) : <div className="empty">None.</div>}</div>
    </div>
  </div>
}

function InstitutionHome() {
  const nav = useNavigate()
  const [d, setD] = useState<any>(null)
  useEffect(() => { api('/api/work').then(setD) }, [])
  if (!d) return <Loading />
  const i = d.institution
  const owe = [...d.owe_steps.map((r: any) => ({ key: r.id, what: r.task, app: r.id, due: r.due_on, overdue: r.overdue, left: r.days_left, to: `/app/${r.id}`,
      why: `Your application (${r.nature_label}) cannot move until you do this.${r.risk && r.risk !== 'on_track' ? ` Against the last date for approval: ${r.risk_label.toLowerCase()}.` : ''}` })),
    ...d.owe_items.map((x: any) => ({ key: x.id, what: x.title, app: x.app_id, due: x.due_on, state: x.state, why: x.consequence, to: `/item/${x.id}` }))]
  return <div>
    <div className="titlebar"><div><h1>{nameOf(i.name)}</h1><div className="sub">Permanent ID {i.pid} · {i.city}, {i.state} · {i.region} region</div></div></div>
    <div className="box"><div className="bh"><h2>What you owe AICTE, and by when</h2><span className="small faint">everything AICTE is waiting for from you</span></div>
      {owe.length ? <div className="tablewrap"><table className="t cards"><thead><tr><th>What</th><th>By</th><th>Why it matters</th><th /></tr></thead>
        <tbody>{owe.map((o) => <tr key={o.key} className="click" onClick={() => nav(o.to)}>
          <td><b>{o.what}</b>{o.app && <div className="small faint">Application {o.app}</div>}</td>
          <td>{o.state ? <span className={`pill ${o.state.color}`}>{o.state.label}</span> : <Due due={o.due} overdue={o.overdue} left={o.left} />}<div className="small faint">{fmtDate(o.due)}</div></td>
          <td className="small">{o.why}</td><td><button className="btn sm primary">Open</button></td></tr>)}</tbody></table></div>
        : <div className="empty">Nothing is pending from you right now.</div>}</div>
    <div className="box"><div className="bh"><h2>Your applications</h2></div>
      <div className="tablewrap"><table className="t cards"><thead><tr><th>Application</th><th>Where it is</th><th>With</th></tr></thead>
        <tbody>{d.applications.map((r: any) => <tr key={r.id} className="click" onClick={() => nav(`/app/${r.id}`)}>
          <td><AppLink id={r.id} /> {r.nature_label}<div className="small faint">submitted {fmtDate(r.submitted_on)}</div></td>
          <td>{r.phase ? r.task : r.status_label}</td><td><Holder kind={r.holder_kind} label={r.holder_kind === 'institution' ? 'You' : r.holder_label} days={r.with_days} /></td></tr>)}</tbody></table></div></div>
    <div className="grid g2">
      <div className="box"><div className="bh"><h2>Certificates on record</h2></div>
        {d.documents.length ? <div className="tablewrap"><table className="t small"><tbody>{d.documents.map((x: any) => <tr key={x.id}><td>{x.label}</td><td><span className={`pill ${x.state.color}`}>{x.state.label}</span></td></tr>)}</tbody></table></div>
          : <div className="empty">None on record yet. Certificates are recorded once the institution is approved.</div>}</div>
      <div className="box"><div className="bh"><h2>Notices from AICTE</h2></div>
        {d.notices.map((n: any) => <div key={n.id} className="noterow" style={{ gridTemplateColumns: '70px 1fr' }}><span className="small faint">{fmtShort(n.on_date)}</span><span className="small">{n.text}</span></div>)}</div>
    </div>
  </div>
}
