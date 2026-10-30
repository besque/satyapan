import { useEffect, useState } from 'react'
import { api } from '../api'

const OUT: Record<string, string> = {
  auto_correct: 'Linked automatically, correct', auto_wrong: 'Linked automatically, wrong', confirm_top_correct: 'Sent to officer; right one suggested first',
  confirm_top_wrong: 'Sent to officer; right one not first', unmatched: 'Not found',
}
const STYLE: Record<string, string> = {
  full: 'Full name', city: 'Name and city', abbrev: 'Abbreviated (engg, Inst. of Tech.)', acronym: 'Acronym and city (KIT Indore)', misspelt: 'Misspelt',
  lower: 'Loosely written', hindi: 'In Hindi', former: 'Former name',
}

export default function Evaluation() {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/api/eval').then(setD).catch((e) => setErr(e.message)) }, [])
  if (err) return <div className="note bad">{err}</div>
  if (!d) return <div className="empty"><span className="spinner" /></div>
  const im = d.institution_matching, nc = d.nature_of_complaint, sm = d.same_matter
  return (
    <div>
      <div className="titlebar"><div><h1>Test results</h1><div className="sub">{d.note}</div></div></div>
      <div className="counts static">
        <div><span className="v">{im.overall.auto_correct ?? 0}%</span><span className="l">Institution linked automatically and correctly ({im.n} ways of writing)</span></div>
        <div><span className="v" style={{ color: (im.overall.auto_wrong ?? 0) ? 'var(--red)' : 'var(--green)' }}>{im.overall.auto_wrong ?? 0}%</span><span className="l">Linked to the wrong institution</span></div>
        <div><span className="v">{nc.top1}%</span><span className="l">Nature right first time · {nc.top3}% in top 3 ({nc.n} complaints)</span></div>
        <div><span className="v">{sm.precision}% / {sm.recall}%</span><span className="l">Same matter: precision / recall ({sm.pairs} pairs)</span></div>
        <div><span className="v">{sm.cross_language_found}</span><span className="l">Hindi–English pairs of the same matter found</span></div>
      </div>
      <div className="grid g2">
        <div className="box"><div className="bh"><h2>Institution matching, by how the name was written</h2></div>
          <div className="tablewrap"><table className="t small"><thead><tr><th>Written as</th>{Object.keys(OUT).map((k) => <th key={k} className="num">{OUT[k]}</th>)}</tr></thead>
            <tbody>{Object.entries(im.by_style).map(([s, c]: any) => <tr key={s}><td>{STYLE[s] || s}</td>{Object.keys(OUT).map((k) => <td key={k} className="num">{c[k] || 0}</td>)}</tr>)}</tbody></table></div>
          <div className="bb small muted">The system links automatically only when one institution is clearly ahead; otherwise an officer chooses. Sister institutions of one trust in one town are the usual reason for asking.</div>
        </div>
        <div className="box"><div className="bh"><h2>Nature of complaint</h2></div>
          <div className="tablewrap"><table className="t small"><thead><tr><th>Complaint</th><th>Expected</th><th>Model's first choice</th></tr></thead>
            <tbody>{nc.rows.map((r: any, i: number) => <tr key={i}><td>{r.text}</td><td>{r.expected}</td><td style={{ color: r.ok ? 'var(--green)' : 'var(--red)' }}>{r.got} ({Math.round(r.score * 100)}%)</td></tr>)}</tbody></table></div>
          <div className="bb small muted">The model's choice is a suggestion: the officer confirms or changes it. Mistakes are mostly between close natures (fees vs. scholarship).</div>
        </div>
      </div>
      <div className="box" style={{ marginTop: 14 }}><div className="bh"><h2>Same matter: pairs tested (threshold {sm.threshold})</h2></div>
        <div className="tablewrap"><table className="t small"><thead><tr><th>Truth</th><th>Complaint A</th><th>Complaint B</th><th className="num">Score</th><th>Flagged</th></tr></thead>
          <tbody>{sm.rows.map((r: any, i: number) => <tr key={i}><td>{r.truth === 'same' ? 'Same matter' : 'Different'}</td><td>{r.a}</td><td>{r.b}</td><td className="num">{r.score}</td>
            <td style={{ color: r.predicted_same === (r.truth === 'same') ? 'var(--green)' : 'var(--red)' }}>{r.predicted_same ? 'Yes' : 'No'}</td></tr>)}</tbody></table></div>
      </div>
      <p className="small faint">Model: {d.model.model}. Computed in {d.seconds} s on this machine.</p>
    </div>
  )
}
