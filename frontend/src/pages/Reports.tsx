import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, withToken } from '../api'
import { useClock } from '../App'
import { AppLink, Counts, fmtDate, Loading, nameOf, Tip } from '../ui'

export default function Reports() {
  const [d, setD] = useState<any>(null)
  const { clock } = useClock()
  useEffect(() => { api('/api/reports').then(setD) }, [])
  if (!d) return <Loading />
  const o = d.overview, c = o.counts
  const csv = (t: string) => withToken(`/api/reports.csv?table=${t}`)
  const Box = ({ title, table, children, tip }: any) => <div className="box"><div className="bh"><h2>{title}{tip && <Tip>{tip}</Tip>}</h2>{table && <a className="small noprint" href={csv(table)}>Download CSV</a>}</div>{children}</div>
  return <div>
    <div className="titlebar"><div><h1>Reports</h1><div className="sub">Approval cycle {clock?.ay} as on {fmtDate(clock?.today)}</div></div>
      <div className="row noprint"><a className="btn" href={csv('applications')}>All applications (CSV)</a><button className="btn" onClick={() => window.print()}>Print</button></div></div>
    <Counts items={[
      { k: 'a', v: c.applications, l: 'Applications' }, { k: 'd', v: c.approved, l: 'Approved', color: 'green' }, { k: 'l', v: c.lod, l: 'Deficiency / rejected (final)' },
      { k: 'p', v: c.in_process, l: 'In process' }, { k: 'r', v: c.will_miss + c.fast_track + c.at_risk, l: 'Not on track', color: 'red' },
      { k: 's', v: `${Math.round((o.split.aicte / Math.max(1, o.split.aicte + o.split.institution)) * 100)}%`, l: 'of all waiting time was with AICTE' }]} />
    <Box title="Stage-wise pendency" table="stages" tip="Applications waiting at each stage now, how long they have waited, and how many are past the time allowed or not on track for the calendar date.">
      <div className="tablewrap"><table className="t small"><thead><tr><th>Stage</th><th className="num">Waiting</th><th className="num">Median days</th><th className="num">Longest</th><th className="num">Past time allowed</th><th className="num">Not on track</th><th className="num">Of which with institution</th></tr></thead>
        <tbody>{o.stages.map((s: any) => <tr key={s.stage}><td>{s.label}</td><td className="num">{s.open}</td><td className="num">{s.median_days}</td><td className="num">{s.max_days}</td>
          <td className="num" style={{ color: s.overdue ? 'var(--red)' : undefined }}>{s.overdue}</td><td className="num">{s.at_risk}</td><td className="num">{s.with_institution}</td></tr>)}</tbody></table></div></Box>
    <Box title="Region-wise processing" table="regions" tip="Median days are counted per application, separately for time with AICTE (offices, committees, Executive Committee) and time with the institution.">
      <div className="tablewrap"><table className="t small"><thead><tr><th>Region</th><th className="num">Applications</th><th className="num">Decided</th><th className="num">In process</th><th className="num">Not on track</th><th className="num">Late with AICTE</th><th className="num">EVCs to fix</th><th className="num">Median days with AICTE</th><th className="num">with institution</th></tr></thead>
        <tbody>{o.regions.map((r: any) => <tr key={r.region}><td>{r.region} <span className="faint">({r.office})</span></td><td className="num">{r.applications}</td><td className="num">{r.decided}</td><td className="num">{r.in_process}</td>
          <td className="num">{r.risk}</td><td className="num">{r.overdue}</td><td className="num">{r.evc_to_schedule}</td><td className="num">{r.days_aicte ?? '—'}</td><td className="num">{r.days_inst ?? '—'}</td></tr>)}</tbody></table></div></Box>
    <div className="grid g2">
      <Box title="EVC status" table="evc">
        <div className="tablewrap"><table className="t small"><thead><tr><th>Region</th><th className="num">To fix</th><th className="num">Video awaited</th><th className="num">Fixed</th><th className="num">Held</th><th className="num">Deficient</th><th className="num">Median days</th></tr></thead>
          <tbody>{d.evc.map((r: any) => <tr key={r.region}><td>{r.region}</td><td className="num">{r.to_schedule}</td><td className="num">{r.video_awaited}</td><td className="num">{r.scheduled}</td><td className="num">{r.held}</td><td className="num">{r.deficient}</td><td className="num">{r.median_days ?? '—'}</td></tr>)}</tbody></table></div></Box>
      <Box title="Undertakings, certificates and deposits" table="compliance">
        <div className="tablewrap"><table className="t small"><thead><tr><th>Kind</th><th className="num">Total</th><th className="num">Verified</th><th className="num">To verify</th><th className="num">Due soon</th><th className="num">Late</th><th className="num">Later</th></tr></thead>
          <tbody>{d.compliance.map((r: any) => <tr key={r.kind}><td>{r.kind}</td><td className="num">{r.total}</td><td className="num">{r.verified}</td><td className="num">{r.to_verify}</td><td className="num">{r.due_soon}</td>
            <td className="num" style={{ color: r.overdue ? 'var(--red)' : undefined }}>{r.overdue}</td><td className="num">{r.upcoming}</td></tr>)}</tbody></table></div>
        <div className="bb small muted">Earlier cycles: {d.real.with_deficiencies} undertakings read from {d.real.letters} published approval letters (<Link to="/compliance?src=public">see them</Link>).</div></Box>
    </div>
    <Box title="Overdue cases" table="overdue">
      <div className="tablewrap"><table className="t small"><thead><tr><th>Application</th><th>Waiting on</th><th>With</th><th>Due</th><th className="num">Days over</th><th>Against the calendar</th></tr></thead>
        <tbody>{d.overdue.map((r: any) => <tr key={r.id}><td><AppLink id={r.id} /> {nameOf(r.institution)}<div className="faint">{r.region}</div></td><td>{r.task}</td><td>{r.holder_label}</td><td>{fmtDate(r.due_on)}</td>
          <td className="num">{r.overdue}</td><td>{r.risk_label}</td></tr>)}</tbody></table></div></Box>
    <Box title="Escalations this cycle">
      <div className="tablewrap"><table className="t small"><thead><tr><th>Level</th><th>To</th><th className="num">Count</th></tr></thead>
        <tbody>{d.escalations.map((r: any, i: number) => <tr key={i}><td>{r.level === 3 ? 'Senior management' : 'Head of office'}</td><td>{r.to}</td><td className="num">{r.count}</td></tr>)}</tbody></table></div></Box>
  </div>
}
