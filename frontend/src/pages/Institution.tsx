import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useClock } from '../App'
import { AppLink, Cite, fmtDate, fmtShort, Holder, Loading, nameOf, Risk, Source, Tip } from '../ui'

export default function Institution() {
  const { pid } = useParams()
  const nav = useNavigate()
  const { clock } = useClock()
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  useEffect(() => { setD(null); api(`/api/institutions/${pid}`).then(setD).catch((e) => setErr(e.message)) }, [pid])
  if (err) return <div className="note bad">{err}</div>
  if (!d) return <Loading />
  const i = d.institution
  const real = i.source === 'public'
  return <div>
    <div className="crumbs"><Link to="/institutions">Institutions</Link> › {i.pid}</div>
    <div className="titlebar"><div><h1>{nameOf(i.name)} <Source s={i.source} /></h1>
      <div className="sub">Permanent ID {i.pid} · {[i.city, i.state].filter(Boolean).join(', ')} · {i.region} region · {i.inst_type}{i.trust ? ` · ${nameOf(i.trust)}` : ''}</div></div></div>
    <div className="split">
      <div className="stack">
        {d.applications.length > 0 && <div className="box"><div className="bh"><h2>Applications this cycle</h2></div>
          <table className="t small"><tbody>{d.applications.map((r: any) => <tr key={r.id} className="click" onClick={() => nav(`/app/${r.id}`)}>
            <td><AppLink id={r.id} /> {r.nature_label}</td><td>{r.phase ? r.task : r.status_label}</td>
            <td><Holder kind={r.holder_kind} label={r.holder_label} days={r.with_days} /></td><td><Risk r={r.risk} spare={r.spare} /></td></tr>)}</tbody></table></div>}
        <div className="box"><div className="bh"><h2>Undertakings, renewals and deposits</h2></div>
          {d.items.length ? <table className="t small"><tbody>{d.items.map((x: any) => <tr key={x.id} className="click" onClick={() => nav(`/item/${x.id}`)}>
            <td><b>{x.title}</b>{x.detail && <div className="faint">{x.detail}</div>}{x.source === 'public' && x.extra?.comply_within && <div className="faint">letter: comply within {x.extra.comply_within}</div>}</td>
            <td>{fmtDate(x.due_on)}</td><td><span className={`pill ${x.state.color}`}>{x.state.label}</span></td></tr>)}</tbody></table>
            : <div className="empty">None.</div>}</div>
        <div className="box"><div className="bh"><h2>Approval letters on record</h2>{real && <span className="small faint">public copies posted by the institution; each linked to its source</span>}</div>
          {d.letters.length ? <div className="tablewrap"><table className="t small">
            <thead><tr><th>Year</th><th>Letter</th><th>Issued</th><th>Deficiencies noted</th><th>Comply within</th></tr></thead>
            <tbody>{d.letters.map((l: any) => <tr key={l.id}><td>{l.ay}</td>
              <td>{l.kind}{l.application_no && <div className="faint mono">{l.application_no}</div>}{l.source_url && <div><a href={l.source_url} target="_blank" rel="noreferrer">source</a></div>}</td>
              <td>{fmtShort(l.issued_on)}</td><td>{l.deficiencies.length ? l.deficiencies.join('; ') : <span className="faint">none</span>}</td>
              <td>{l.courses?.comply_within ? `${l.courses.comply_within.n} ${l.courses.comply_within.unit}` : '—'}</td></tr>)}</tbody></table></div>
            : <div className="empty">None on record.</div>}</div>
      </div>
      <div className="stack">
        {d.lease && <div className="box"><div className="bh"><h2>Lease rule <Tip>EoA is not issued from the academic year in which the remaining (live) lease is no more than the duration of the longest course, unless the lease is extended by 30 years.</Tip></h2><Cite c={{ key: 'CL_2_1_E', ref: 'Cl. 2.1 (e)' }} /></div>
          <dl className="kv"><dt>Lease ends</dt><dd>{fmtDate(d.lease.lease_until)}</dd><dt>Longest course</dt><dd>{d.lease.max_years} years</dd>
            <dt>EoA blocked from</dt><dd><b style={{ color: 'var(--red)' }}>{d.lease.blocked_ay}</b> <span className="faint">(live lease {d.lease.live_years} years at its start)</span></dd>
            <dt>Extend by</dt><dd>{fmtDate(d.lease.submit_by)} <span className="faint">(that year's application window)</span></dd></dl></div>}
        <div className="box"><div className="bh"><h2>Certificates</h2></div>
          {d.documents.length ? d.documents.map((x: any) => <div key={x.id} className="noterow" style={{ gridTemplateColumns: '1fr' }}>
            <div className="spread"><b className="small">{x.label}</b><span className={`pill ${x.state.color}`}>{x.state.label}</span></div>
            <div className="small faint">{x.issued_on && `issued ${fmtDate(x.issued_on)}`}{x.valid_until && ` · valid until ${fmtDate(x.valid_until)}`} {x.cite && <Cite c={x.cite} />}</div>
            {x.note && <div className="small">{x.note}</div>}{x.source_url && <a className="small" href={x.source_url} target="_blank" rel="noreferrer">posted copy</a>}
            {x.valid_until && clock && <Validity from={x.issued_on} to={x.valid_until} today={clock.today} />}
          </div>) : <div className="empty">None on record.</div>}</div>
        <div className="box"><div className="bh"><h2>Courses</h2><span className="small faint">longest {i.max_years} years</span></div>
          <table className="t small"><tbody>{(i.programmes || []).map((p: any, k: number) => <tr key={k}><td>{nameOf(p.course)}<div className="faint">{nameOf(p.level)}</div></td><td className="num">{p.years} y</td><td className="num">{p.intake ?? '—'}</td></tr>)}</tbody></table></div>
      </div>
    </div>
  </div>
}

function Validity({ from, to, today }: { from?: string; to: string; today: string }) {
  const t = (s: string) => new Date(s + 'T00:00:00').getTime()
  const a = from ? t(from) : t(to) - 365 * 86400000, b = t(to), n = t(today)
  const lo = Math.min(a, n) , hi = Math.max(b, n) + 30 * 86400000
  const p = (x: number) => ((x - lo) / (hi - lo)) * 100
  const color = n > b ? 'red' : b - n < 90 * 86400000 ? 'orange' : 'green'
  return <div className="vbar" style={{ marginTop: 4 }} title={`valid ${fmtShort(from || '')} to ${fmtShort(to)}`}>
    <span className="track"><i className={color} style={{ left: `${p(a)}%`, width: `${p(b) - p(a)}%` }} />
      <i className="grey" style={{ left: `${p(n)}%`, width: 2, background: 'var(--ink)' }} /></span></div>
}
