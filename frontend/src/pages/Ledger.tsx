import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Tip, titleCase } from '../ui'

export default function Ledger() {
  const { pid } = useParams()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [d, setD] = useState<any>(null)
  const [inst, setInst] = useState<any>(null)
  useEffect(() => { api(`/api/ledger?q=${encodeURIComponent(q)}`).then(setD) }, [q])
  useEffect(() => { if (pid) api(`/api/ledger/${pid}`).then(setInst); else setInst(null) }, [pid])
  const c = d?.corpus
  const years: string[] = inst ? inst.approvals.map((a: any) => a.academic_year) : []
  const keyOf = (x: any) => `${x.level}|${x.course}`
  const courses: string[] = inst ? Array.from(new Set(inst.approvals.flatMap((a: any) => a.courses.filter((x: any) => x.intake_curr).map(keyOf)))) as string[] : []
  const cell = (y: string, key: string) => inst.approvals.find((x: any) => x.academic_year === y)?.courses.find((x: any) => keyOf(x) === key)?.intake_curr
  return (
    <div>
      <div className="titlebar"><div><h1>Institution records <Tip>Approval history built from AICTE approval letters that colleges publish on their own websites (a mandatory disclosure). Each row links to the public file it came from.</Tip></h1>
        {c && <div className="sub">{d.institutions.length} institutions · {c.letters} approval letters · {c.years[0]} to {c.years[c.years.length - 1]}
          {c.cross_year && <> · consecutive letters agree in {c.cross_year.checks - c.cross_year.issues} of {c.cross_year.checks} cases</>}</div>}</div>
        <input placeholder="Search name or Permanent ID" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} /></div>
      <div className="grid" style={{ gridTemplateColumns: '340px minmax(0,1fr)' }}>
        <div className="box" style={{ maxHeight: '75vh', overflow: 'auto' }}>
          <div className="tablewrap"><table className="t small"><tbody>{d?.institutions.filter((i: any) => i.name).map((i: any) => (
            <tr key={i.permanent_id} className="click" onClick={() => nav(`/ledger/${i.permanent_id}`)} style={pid === i.permanent_id ? { outline: '2px solid var(--accent)' } : undefined}>
              <td><b>{titleCase(i.name)}</b><div className="faint">{i.state} · {i.letters} letter{i.letters > 1 ? 's' : ''}</div></td></tr>))}</tbody></table></div>
        </div>
        <div>
          {!inst ? <div className="box empty">Choose an institution.</div> : <div className="grid">
            <div className="box"><div className="bb"><h2>{titleCase(inst.institution.name)}</h2>
              <div className="sub">Permanent ID {inst.institution.permanent_id} · {inst.institution.inst_type} · established {inst.institution.est_year}</div>
              <div className="small muted">{titleCase(inst.institution.address)}</div></div></div>
            <div className="box" style={{ overflow: 'auto' }}><div className="bh"><h3>Approved intake by year</h3></div>
              <div className="tablewrap"><table className="t small"><thead><tr><th>Course</th>{years.map((y) => <th key={y} className="num">{y}</th>)}</tr></thead>
                <tbody>{courses.map((k) => <tr key={k}><td>{titleCase(k.split('|')[1])} <span className="faint">({k.split('|')[0].includes('POST') ? 'PG' : k.split('|')[0].includes('DIPLOMA') ? 'Diploma' : 'UG'})</span></td>
                  {years.map((y) => <td key={y} className="num">{cell(y, k) || <span className="faint">–</span>}</td>)}</tr>)}</tbody></table></div></div>
            <div className="box"><div className="bh"><h3>Letters</h3></div>
              <div className="tablewrap"><table className="t small"><thead><tr><th>Year</th><th>Approved on</th><th>Deficiencies noted</th><th>File</th></tr></thead>
                <tbody>{inst.approvals.map((a: any) => <tr key={a.id}><td>{a.academic_year}</td><td>{a.date_of_approval || '—'}</td>
                  <td>{a.deficiencies.filter((x: any) => x.status === 'Yes').map((x: any) => x.particular).join(', ') || <span className="faint">None</span>}</td>
                  <td>{a.source_url ? <a href={a.source_url} target="_blank" rel="noreferrer">Open</a> : '—'}</td></tr>)}</tbody></table></div></div>
          </div>}
        </div>
      </div>
    </div>
  )
}
