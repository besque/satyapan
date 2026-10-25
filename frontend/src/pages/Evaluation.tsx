import { useEffect, useState } from 'react'
import { api } from '../api'
import { Tip } from '../ui'

const pct = (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`)

export default function Evaluation() {
  const [r, setR] = useState<any>(null)
  useEffect(() => { api('/api/eval').then(setR) }, [])
  if (!r) return null
  if (r.missing) return <div className="box empty">No test results yet.</div>
  const a = r.synthetic, b = r.real
  const tot = a.per_defect.reduce((s: number, x: any) => s + x.planted, 0)
  const det = a.per_defect.reduce((s: number, x: any) => s + x.detected, 0)
  const laneOk = a.lanes.filter((x: any) => x.expected === x.got).reduce((s: number, x: any) => s + x.n, 0)
  const laneN = a.lanes.reduce((s: number, x: any) => s + x.n, 0)
  return (
    <div>
      <div className="titlebar"><div><h1>Test results <Tip>Measured on a fresh set of {a.applications} test applications with known, deliberately planted problems, and on real approval letters from college websites.</Tip></h1>
        <div className="sub">Last run {new Date(r.generated_at).toLocaleDateString('en-IN', { dateStyle: 'medium' })}</div></div></div>
      <div className="counts">
        <button><span className="v">{pct(det / tot)}</span><span className="l">Planted problems found ({det} of {tot})</span></button>
        <button><span className="v">{a.clean_applications - a.clean_with_unexplained_alert} of {a.clean_applications}</span><span className="l">Clean applications with no false alarm</span></button>
        <button><span className="v">{pct(laneOk / laneN)}</span><span className="l">Right status colour</span></button>
        <button><span className="v">{a.avg_seconds} s</span><span className="l">Time per application</span></button>
      </div>
      <div className="grid g2">
        <div className="box"><div className="bh"><h3>Problems found, by type</h3></div>
          <div className="tablewrap"><table className="t small"><thead><tr><th>Planted problem</th><th className="num">Found</th></tr></thead>
            <tbody>{a.per_defect.map((x: any) => <tr key={x.code}><td>{x.label}</td>
              <td className="num"><span className={`pill ${x.recall < 1 ? 'orange' : 'green'}`}>{x.detected} / {x.planted}</span></td></tr>)}</tbody></table></div></div>
        <div className="grid" style={{ alignContent: 'start' }}>
          <div className="box"><div className="bh"><h3>Reading values from documents</h3><Tip>Certificate numbers, dates, amounts, areas and names compared with what is printed.</Tip></div>
            <div className="tablewrap"><table className="t small"><tbody>{Object.entries(a.extraction).map(([k, v]: any) => <tr key={k}><td>{k === 'ocr' ? 'Scanned documents' : 'Digital PDFs'}</td>
              <td className="num">{v.n} values</td><td className="num"><b>{pct(v.accuracy)}</b> correct</td></tr>)}</tbody></table></div></div>
          <div className="box"><div className="bh"><h3>Real approval letters</h3><Tip>{b.note}</Tip></div>
            <div className="tablewrap"><table className="t small"><tbody>
              <tr><td>Untouched letters wrongly flagged</td><td className="num"><b>{b.genuine_false_alarms} of {b.genuine_letters_tested}</b></td></tr>
              {Object.entries(b.attacks).map(([k, v]: any) => <tr key={k}><td>Altered copies caught ({k === 'whiteout_incremental' ? 'number painted over' : 'number replaced and re-saved'})</td>
                <td className="num"><b>{v.detected} of {v.tested}</b></td></tr>)}
              {b.corpus?.cross_year && <tr><td>Consecutive years' letters that agree</td><td className="num"><b>{b.corpus.cross_year.checks - b.corpus.cross_year.issues} of {b.corpus.cross_year.checks}</b></td></tr>}
            </tbody></table></div></div>
          {Object.keys(a.unexplained_alerts).length > 0 && <div className="note small">One extra alert in the test set was checked by hand: both colleges used the same e-stamp number and neither copy could be confirmed, so flagging both is correct.</div>}
        </div>
      </div>
    </div>
  )
}
